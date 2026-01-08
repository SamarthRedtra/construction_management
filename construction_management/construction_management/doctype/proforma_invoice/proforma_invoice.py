# Copyright (c) 2024, Construction Management
# License: MIT

"""
Proforma Invoice DocType Controller

Manages proforma invoices as a separate document type from Sales Invoice.
Supports multiple BOQ Items per proforma invoice.

Requirements: 7.1, 7.2, 7.3, 7.4, 7.5
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, today
from typing import Optional


def get_project_boq_for_item(boq_item_name: str) -> Optional[str]:
	"""
	Get project_boq from BOQ Item's parent hierarchy.
	
	Traverses: BOQ Item → BOQ Bill → Project BOQ
	
	Args:
		boq_item_name: Name of the BOQ Item
		
	Returns:
		Project BOQ name if found, None if hierarchy is incomplete
		
	Requirements: 5.2
	"""
	if not boq_item_name:
		return None
	
	# First try to get project_boq directly from BOQ Item (it's a fetched field)
	project_boq = frappe.db.get_value("BOQ Item", boq_item_name, "project_boq")
	if project_boq:
		return project_boq
	
	# If not set, traverse the hierarchy: BOQ Item → BOQ Bill → Project BOQ
	parent_bill = frappe.db.get_value("BOQ Item", boq_item_name, "parent_bill")
	if not parent_bill:
		return None
	
	project_boq = frappe.db.get_value("BOQ Bill", parent_bill, "project_boq")
	return project_boq


class ProformaInvoice(Document):
	def validate(self):
		self.validate_project()
		self.validate_items()
		self.calculate_totals()
		self.calculate_retention()
		self.set_description()
	
	def validate_project(self):
		"""Validate project exists and has customer"""
		if not self.project:
			return
		
		customer = frappe.db.get_value("Project", self.project, "customer")
		if customer:
			self.customer = customer
	
	def validate_items(self):
		"""Validate items belong to the project"""
		if not self.items:
			frappe.throw(_("At least one item is required"))
		
		for item in self.items:
			if item.boq_item:
				item_project = frappe.db.get_value("BOQ Item", item.boq_item, "project")
				if item_project and item_project != self.project:
					frappe.throw(
						_("BOQ Item {0} does not belong to Project {1}").format(
							item.boq_item, self.project
						)
					)
				
				# Auto-fetch bill_no if not set
				if not item.bill_no:
					item.bill_no = frappe.db.get_value("BOQ Item", item.boq_item, "parent_bill")
				
				# Calculate item amount
				if not item.rate:
					item.rate = flt(frappe.db.get_value("BOQ Item", item.boq_item, "rate"))
				
				item.amount = flt(item.qty) * flt(item.rate)
	
	def calculate_totals(self):
		"""Calculate total amount from items"""
		self.amount = sum(flt(item.amount) for item in self.items)
	
	def calculate_retention(self):
		"""Calculate retention amount based on project settings"""
		retention_pct = 0
		if self.project:
			retention_pct = flt(frappe.db.get_value("Project", self.project, "retention_percentage"))
		
		self.retention_amount = flt(self.amount) * (retention_pct / 100)
		self.net_amount = flt(self.amount) - flt(self.retention_amount)
	
	def set_description(self):
		"""Auto-set description from items if not provided"""
		if not self.description and self.items:
			if len(self.items) == 1:
				self.description = frappe.db.get_value("BOQ Item", self.items[0].boq_item, "description")
			else:
				self.description = f"Proforma Invoice for {len(self.items)} BOQ Items"
	
	def before_update_after_submit(self):
		"""
		Handle amendments to submitted Proforma Invoice.
		Recalculate totals and update ledger entries.
		
		Requirements: 7.2, 7.5
		"""
		# Recalculate totals
		self.calculate_totals()
		self.calculate_retention()
	
	def on_update_after_submit(self):
		"""
		After amending a submitted Proforma Invoice:
		1. Update BOQ Progress Ledger entries with new amounts
		2. Update related Payment Certificate if exists
		
		Requirements: 7.2, 7.5
		"""
		self.update_ledger_entries_on_revision()
		self.update_related_documents()
	
	def update_ledger_entries_on_revision(self):
		"""
		Update BOQ Progress Ledger entries when proforma is revised.
		Creates reversing entries for old values and new entries for updated values.
		
		Requirements: 7.5
		"""
		if not frappe.db.exists("DocType", "BOQ Progress Ledger"):
			return
		
		from construction_management.api.boq_ledger import create_ledger_entry, recalculate_ledger_for_item
		
		# Get existing ledger entries for this proforma
		existing_entries = frappe.get_all(
			"BOQ Progress Ledger",
			filters={
				"reference_doctype": "Proforma Invoice",
				"reference_name": self.name,
				"source": "Proforma"
			},
			fields=["name", "boq_item", "qty", "amount"]
		)
		
		# Create a map of existing entries by boq_item
		existing_map = {e.boq_item: e for e in existing_entries}
		
		for item in self.items:
			if not item.boq_item:
				continue
			
			existing = existing_map.get(item.boq_item)
			
			if existing:
				# Update the existing ledger row in place (single-row lifecycle)
				frappe.db.set_value(
					"BOQ Progress Ledger",
					existing.name,
					{
						"qty": flt(item.qty),
						"amount": flt(item.amount),
						"proforma_amount": flt(item.amount),
						"posting_date": self.posting_date,
						"remarks": f"Revised Proforma Invoice {self.name}",
						"source": "Proforma",
						"reference_doctype": "Proforma Invoice",
						"reference_name": self.name
					},
					update_modified=False
				)
				del existing_map[item.boq_item]
			else:
				# New item added during revision
				try:
					create_ledger_entry(
						boq_item=item.boq_item,
						qty=flt(item.qty),
						amount=flt(item.amount),
						source="Proforma",
						reference_doctype="Proforma Invoice",
						reference_name=self.name,
						posting_date=self.posting_date,
						remarks=f"Added in revision of Proforma Invoice {self.name}",
						proforma_invoice=self.name,
						proforma_amount=flt(item.amount)
					)
				except Exception as e:
					frappe.log_error(
						f"Error creating ledger for new item in Proforma {self.name}, Item {item.boq_item}: {str(e)}",
						"Proforma Invoice Revision Error"
					)
					raise
			
			recalculate_ledger_for_item(item.boq_item)
		
		# Handle removed items (remaining in existing_map)
		for boq_item, existing in existing_map.items():
			frappe.db.set_value(
				"BOQ Progress Ledger",
				existing.name,
				{
					"qty": 0,
					"amount": 0,
					"proforma_amount": 0,
					"remarks": f"Removed in revision of Proforma Invoice {self.name}",
					"source": "Proforma Reversal"
				},
				update_modified=False
			)
			recalculate_ledger_for_item(boq_item)
	
	def update_related_documents(self):
		"""
		Update related Payment Certificate and other documents when proforma is revised.
		
		Requirements: 7.5
		"""
		# Update Payment Certificate if linked
		if self.payment_certificate:
			pc = frappe.get_doc("Payment Certificate", self.payment_certificate)
			if pc.docstatus == 0:  # Only update if PC is still draft
				pc.proforma_amount = self.amount
				pc.variance = flt(self.amount) - flt(pc.accepted_amount)
				pc.save()
				frappe.db.commit()
	
	def on_submit(self):
		"""
		On submit:
		1. Update status to Submitted
		2. Create BOQ Progress Ledger entries for each item
		3. Reset BOQ Item current_qty
		
		Requirements: 7.2
		"""
		self.db_set("status", "Submitted")
		self.create_ledger_entries()
		self.reset_boq_item_current_qty()
	
	def on_cancel(self):
		"""
		On cancel:
		1. Update status to Cancelled
		2. Create reversing ledger entries
		
		Requirements: 7.3
		"""
		# Check if already converted
		if self.payment_certificate or self.tax_invoice:
			frappe.throw(
				_("Cannot cancel Proforma Invoice that has been converted to Payment Certificate or Tax Invoice")
			)
		
		self.db_set("status", "Cancelled")
		self.create_reversing_ledger_entries()
	
	def create_ledger_entries(self):
		"""
		Create BOQ Progress Ledger entries for each item using centralized function.
		
		Requirements: 5.1, 5.3, 6.3
		"""
		if not frappe.db.exists("DocType", "BOQ Progress Ledger"):
			return
		
		from construction_management.api.boq_ledger import create_ledger_entry, recalculate_ledger_for_item
		
		for item in self.items:
			if not item.boq_item:
				continue
			
			try:
				ledger_entry = frappe.db.get_value(
					"BOQ Progress Ledger",
					{
						"boq_item": item.boq_item,
						"proforma_invoice": self.name
					},
					"name"
				)
				
				if ledger_entry:
					# Update existing PI ledger row (single-row lifecycle)
					frappe.db.set_value(
						"BOQ Progress Ledger",
						ledger_entry,
						{
							"qty": flt(item.qty),
							"amount": flt(item.amount),
							"proforma_amount": flt(item.amount),
							"posting_date": self.posting_date,
							"source": "Proforma",
							"reference_doctype": "Proforma Invoice",
							"reference_name": self.name,
							"remarks": f"Proforma Invoice {self.name}"
						},
						update_modified=False
					)
				else:
					create_ledger_entry(
						boq_item=item.boq_item,
						qty=flt(item.qty),
						amount=flt(item.amount),
						source="Proforma",
						reference_doctype="Proforma Invoice",
						reference_name=self.name,
						posting_date=self.posting_date,
						remarks=f"Proforma Invoice {self.name}",
						proforma_invoice=self.name,
						proforma_amount=flt(item.amount)
					)
				
				recalculate_ledger_for_item(item.boq_item)
			except Exception as e:
				frappe.log_error(
					f"Error creating ledger for Proforma {self.name}, Item {item.boq_item}: {str(e)}",
					"Proforma Invoice Ledger Error"
				)
				raise
	
	def create_reversing_ledger_entries(self):
		"""
		Create reversing BOQ Progress Ledger entries using centralized function.
		
		Requirements: 5.5, 6.3
		"""
		if not frappe.db.exists("DocType", "BOQ Progress Ledger"):
			return
		
		from construction_management.api.boq_ledger import recalculate_ledger_for_item
		
		for item in self.items:
			if not item.boq_item:
				continue
			
			ledger_entry = frappe.db.get_value(
				"BOQ Progress Ledger",
				{
					"boq_item": item.boq_item,
					"proforma_invoice": self.name
				},
				"name"
			)
			
			if ledger_entry:
				frappe.db.set_value(
					"BOQ Progress Ledger",
					ledger_entry,
					{
						"qty": 0,
						"amount": 0,
						"proforma_amount": 0,
						"payment_certificate": None,
						"certified_amount": 0,
						"tax_invoice": None,
						"tax_invoice_amount": 0,
						"remarks": f"Cancellation of Proforma Invoice {self.name}",
						"source": "Proforma Reversal"
					},
					update_modified=False
				)
				recalculate_ledger_for_item(item.boq_item)
	
	def reset_boq_item_current_qty(self):
		"""Reset current_qty on BOQ Items after proforma creation"""
		for item in self.items:
			if item.boq_item:
				frappe.db.set_value("BOQ Item", item.boq_item, "current_qty", 0)
	
	def mark_as_converted(self, payment_certificate: str, tax_invoice: str = None):
		"""
		Mark proforma as converted when Payment Certificate is created.
		Requirements: 7.4
		"""
		self.db_set({
			"status": "Converted",
			"payment_certificate": payment_certificate,
			"tax_invoice": tax_invoice,
			"converted_date": today()
		})


# ============================================
# API Functions
# ============================================

@frappe.whitelist()
def get_pending_proformas(project: str = None, bill_no: str = None) -> list:
	"""
	Get proforma invoices without linked Payment Certificate.
	
	Args:
		project: Optional project filter
		bill_no: Optional bill filter
		
	Returns:
		List of pending proforma invoices
	"""
	filters = {"docstatus": 1, "status": "Submitted"}
	
	if project:
		filters["project"] = project
	
	proformas = frappe.get_all(
		"Proforma Invoice",
		filters=filters,
		fields=[
			"name", "project", "customer",
			"posting_date", "amount", "net_amount", "description",
			"DATEDIFF(CURDATE(), posting_date) as age_days"
		],
		order_by="posting_date desc"
	)
	
	# Add item count
	for p in proformas:
		p["item_count"] = frappe.db.count("Proforma Invoice Item", {"parent": p.name})
	
	return proformas


@frappe.whitelist()
def create_proforma_from_selected_items(
	project: str,
	items: str | list,
	apply_retention: int = 1,
	posting_date: str = None,
	remarks: str = None,
	auto_submit: int = 1
) -> dict:
	"""
	Create Proforma Invoice from selected BOQ Items.
	
	Args:
		project: Project name
		items: List of dicts with boq_item and qty
		apply_retention: Whether to apply retention
		posting_date: Optional posting date
		remarks: Optional remarks
		auto_submit: Whether to auto-submit the proforma (1=yes, 0=no)
		
	Returns:
		dict with status, data or error_message
		
	Requirements: 6.4, 7.1, 7.2
	"""
	import json
	
	try:
		if isinstance(items, str):
			items = json.loads(items)
		
		if not items:
			return {"status": "error", "error_message": _("No items provided")}
		
		auto_submit = int(auto_submit)
		
		proforma = frappe.new_doc("Proforma Invoice")
		proforma.project = project
		proforma.posting_date = posting_date or today()
		proforma.remarks = remarks
		
		total_amount = 0
		bills_included = set()
		
		for item_data in items:
			boq_item_name = item_data.get("boq_item")
			qty = flt(item_data.get("qty", 0))
			
			if qty <= 0:
				continue
			
			# Get BOQ Item details
			boq_item = frappe.get_doc("BOQ Item", boq_item_name)
			
			# Validate balance
			from construction_management.api.boq_ledger import get_to_date_qty
			to_date_qty = get_to_date_qty(boq_item_name)
			balance_qty = flt(boq_item.total_qty) - flt(to_date_qty)
			
			if qty > balance_qty:
				return {
					"status": "error",
					"error_message": _("Quantity ({0}) exceeds available balance ({1}) for item {2}").format(
						qty, balance_qty, boq_item.description[:50]
					)
				}
			
			amount = flt(qty) * flt(boq_item.rate)
			total_amount += amount
			
			# Get bill_no
			bill_no = frappe.db.get_value("BOQ Bill", boq_item.parent_bill, "bill_no")
			bills_included.add(bill_no or boq_item.parent_bill)
			
			# Add item to proforma
			proforma.append("items", {
				"boq_item": boq_item_name,
				"bill_no": boq_item.parent_bill,
				"description": boq_item.description,
				"unit": boq_item.unit,
				"qty": qty,
				"rate": boq_item.rate,
				"amount": amount
			})
		
		if not proforma.items:
			return {"status": "error", "error_message": _("No valid items to invoice")}
		
		# Insert the proforma
		proforma.insert()
		
		# Auto-submit if requested
		if auto_submit:
			proforma.submit()
		
		# Ensure the transaction is committed
		frappe.db.commit()
		# Also set flag to prevent any later rollback
		frappe.flags.commit = True
		
		frappe.logger().info(
			f"Created Proforma Invoice {proforma.name} for project {project}, "
			f"items={len(proforma.items)}, amount={proforma.amount}, submitted={auto_submit}"
		)
		
		return {
			"status": "success",
			"name": proforma.name,
			"project": proforma.project,
			"item_count": len(proforma.items),
			"bills_included": list(bills_included),
			"amount": proforma.amount,
			"retention_amount": proforma.retention_amount,
			"net_amount": proforma.net_amount,
			"doc_status": "Submitted" if auto_submit else "Draft",
			"docstatus": proforma.docstatus
		}
		
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(f"Error creating proforma invoice: {str(e)}", "Proforma Invoice API Error")
		return {"status": "error", "error_message": str(e)}


@frappe.whitelist()
def get_proforma_summary(project: str) -> dict:
	"""
	Get proforma invoice summary for a project.
	
	Args:
		project: Project name
		
	Returns:
		dict with summary statistics
	"""
	summary = frappe.db.sql("""
		SELECT 
			COUNT(*) as total_count,
			SUM(CASE WHEN status = 'Draft' THEN 1 ELSE 0 END) as draft_count,
			SUM(CASE WHEN status = 'Submitted' THEN 1 ELSE 0 END) as pending_count,
			SUM(CASE WHEN status = 'Converted' THEN 1 ELSE 0 END) as converted_count,
			SUM(CASE WHEN status = 'Cancelled' THEN 1 ELSE 0 END) as cancelled_count,
			COALESCE(SUM(CASE WHEN docstatus = 1 THEN amount ELSE 0 END), 0) as total_amount,
			COALESCE(SUM(CASE WHEN status = 'Submitted' THEN amount ELSE 0 END), 0) as pending_amount,
			COALESCE(SUM(CASE WHEN status = 'Converted' THEN amount ELSE 0 END), 0) as converted_amount
		FROM `tabProforma Invoice`
		WHERE project = %s
	""", project, as_dict=True)[0]
	
	return {
		"project": project,
		"total_count": summary.total_count or 0,
		"draft_count": summary.draft_count or 0,
		"pending_count": summary.pending_count or 0,
		"converted_count": summary.converted_count or 0,
		"cancelled_count": summary.cancelled_count or 0,
		"total_amount": flt(summary.total_amount),
		"pending_amount": flt(summary.pending_amount),
		"converted_amount": flt(summary.converted_amount)
	}


@frappe.whitelist()
def revise_proforma_invoice(
	proforma_name: str,
	items: str | list,
	remarks: str = None
) -> dict:
	"""
	Revise a submitted Proforma Invoice with updated quantities/amounts.
	Updates BOQ Progress Ledger and related documents.
	
	Args:
		proforma_name: Name of the Proforma Invoice to revise
		items: List of dicts with boq_item and qty (updated values)
		remarks: Optional revision remarks
		
	Returns:
		dict with status, data or error_message
		
	Requirements: 7.5
	"""
	import json
	
	try:
		if isinstance(items, str):
			items = json.loads(items)
		
		if not items:
			return {"status": "error", "error_message": _("No items provided")}
		
		# Get the proforma
		proforma = frappe.get_doc("Proforma Invoice", proforma_name)
		
		# Check if it can be revised
		if proforma.docstatus != 1:
			return {"status": "error", "error_message": _("Only submitted Proforma Invoices can be revised")}
		
		if proforma.status == "Converted":
			return {"status": "error", "error_message": _("Cannot revise a converted Proforma Invoice")}
		
		# Build a map of new items
		new_items_map = {}
		for item_data in items:
			boq_item_name = item_data.get("boq_item")
			qty = flt(item_data.get("qty", 0))
			if boq_item_name and qty > 0:
				new_items_map[boq_item_name] = qty
		
		# Update existing items and track changes
		items_updated = 0
		for item in proforma.items:
			if item.boq_item in new_items_map:
				new_qty = new_items_map[item.boq_item]
				if flt(item.qty) != new_qty:
					item.qty = new_qty
					item.amount = flt(new_qty) * flt(item.rate)
					items_updated += 1
				del new_items_map[item.boq_item]
		
		# Add any new items
		for boq_item_name, qty in new_items_map.items():
			boq_item = frappe.get_doc("BOQ Item", boq_item_name)
			
			# Validate balance
			from construction_management.api.boq_ledger import get_to_date_qty
			to_date_qty = get_to_date_qty(boq_item_name)
			balance_qty = flt(boq_item.total_qty) - flt(to_date_qty)
			
			if qty > balance_qty:
				return {
					"status": "error",
					"error_message": _("Quantity ({0}) exceeds available balance ({1}) for item {2}").format(
						qty, balance_qty, boq_item.description[:50]
					)
				}
			
			proforma.append("items", {
				"boq_item": boq_item_name,
				"bill_no": boq_item.parent_bill,
				"description": boq_item.description,
				"unit": boq_item.unit,
				"qty": qty,
				"rate": boq_item.rate,
				"amount": flt(qty) * flt(boq_item.rate)
			})
			items_updated += 1
		
		if items_updated == 0:
			return {"status": "error", "error_message": _("No changes detected")}
		
		# Add revision remarks
		if remarks:
			proforma.remarks = f"{proforma.remarks or ''}\n[Revision: {today()}] {remarks}".strip()
		
		# Save with update_after_submit flag
		proforma.flags.ignore_validate_update_after_submit = True
		proforma.save()
		
		# Trigger the update hooks manually
		proforma.run_method("on_update_after_submit")
		
		frappe.db.commit()
		frappe.flags.commit = True
		
		frappe.logger().info(
			f"Revised Proforma Invoice {proforma.name}, "
			f"items_updated={items_updated}, new_amount={proforma.amount}"
		)
		
		return {
			"status": "success",
			"name": proforma.name,
			"items_updated": items_updated,
			"amount": proforma.amount,
			"retention_amount": proforma.retention_amount,
			"net_amount": proforma.net_amount
		}
		
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(f"Error revising proforma invoice: {str(e)}", "Proforma Invoice Revision Error")
		return {"status": "error", "error_message": str(e)}


@frappe.whitelist()
def get_proforma_details(proforma_name: str) -> dict:
	"""
	Get detailed information about a Proforma Invoice including items and ledger entries.
	
	Args:
		proforma_name: Name of the Proforma Invoice
		
	Returns:
		dict with proforma details, items, and ledger entries
	"""
	try:
		proforma = frappe.get_doc("Proforma Invoice", proforma_name)
		
		# Get ledger entries
		ledger_entries = frappe.get_all(
			"BOQ Progress Ledger",
			filters={
				"reference_doctype": "Proforma Invoice",
				"reference_name": proforma_name
			},
			fields=["name", "boq_item", "qty", "amount", "source", "posting_date", "remarks"],
			order_by="posting_date desc, creation desc"
		)
		
		# Get items with BOQ Item details
		items = []
		for item in proforma.items:
			boq_item = frappe.db.get_value(
				"BOQ Item", 
				item.boq_item, 
				["description", "total_qty", "rate", "unit"],
				as_dict=True
			) if item.boq_item else {}
			
			items.append({
				"boq_item": item.boq_item,
				"bill_no": item.bill_no,
				"description": item.description or boq_item.get("description"),
				"unit": item.unit or boq_item.get("unit"),
				"qty": item.qty,
				"rate": item.rate,
				"amount": item.amount,
				"total_qty": boq_item.get("total_qty", 0)
			})
		
		return {
			"status": "success",
			"proforma": {
				"name": proforma.name,
				"project": proforma.project,
				"customer": proforma.customer,
				"posting_date": proforma.posting_date,
				"amount": proforma.amount,
				"retention_amount": proforma.retention_amount,
				"net_amount": proforma.net_amount,
				"status": proforma.status,
				"docstatus": proforma.docstatus,
				"payment_certificate": proforma.payment_certificate,
				"tax_invoice": proforma.tax_invoice,
				"remarks": proforma.remarks
			},
			"items": items,
			"ledger_entries": ledger_entries
		}
		
	except Exception as e:
		frappe.log_error(f"Error getting proforma details: {str(e)}", "Proforma Invoice API Error")
		return {"status": "error", "error_message": str(e)}

# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
import erpnext
from frappe import _
from frappe.utils import cint, flt, today
from erpnext.accounts.doctype.account.account import get_account_currency
from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice
from erpnext.controllers.stock_controller import StockController
from construction_management.overrides.unearned_revenue import (
	find_journal_entry_by_so,
	SO_UNEARNED_EXCLUDED_ITEM_CODES,
)
from erpnext.accounts.utils import update_voucher_outstanding


def _so_base_net_for_boq_item(so_doc, boq_item, excluded_item_codes):
	"""Sum base_net on SO revenue rows for a BOQ Item (excl. retention/advance/variance lines)."""
	if not boq_item:
		return 0.0
	total = 0.0
	for row in so_doc.get("items", []):
		if row.item_code in excluded_item_codes:
			continue
		if row.boq_item != boq_item:
			continue
		total += flt(row.base_net_amount, row.precision("base_net_amount"))
	return total


def _consolidate_income_gl_by_boq_item(gl_map, income_accounts, unbilled_revenue_account):
	"""Merge Sales (income) GLE rows that share the same boq_item into one net credit/debit row.

	Keeps voucher totals balanced while replacing many offsetting Sales lines (revenue + retention/advance + gross-up)
	with a single net line per BOQ item (e.g. three amounts instead of nine).
	"""
	if not gl_map:
		return gl_map

	others = []
	keyed = {}
	for e in gl_map:
		acc = e.get("account")
		boq = e.get("boq_item")
		if (
			acc not in income_accounts
			or not boq
			or (unbilled_revenue_account and acc == unbilled_revenue_account)
		):
			others.append(e)
			continue
		key = (acc, e.get("project"), e.get("cost_center"), boq)
		keyed.setdefault(key, []).append(e)

	result = list(others)
	for _key, rows in keyed.items():
		if len(rows) == 1:
			result.extend(rows)
			continue

		tc = sum(flt(r.get("credit")) for r in rows)
		td = sum(flt(r.get("debit")) for r in rows)
		tci = sum(flt(r.get("credit_in_account_currency")) for r in rows)
		tdi = sum(flt(r.get("debit_in_account_currency")) for r in rows)
		tct = sum(flt(r.get("credit_in_transaction_currency")) for r in rows)
		tdt = sum(flt(r.get("debit_in_transaction_currency")) for r in rows)
		tcr = sum(flt(r.get("credit_in_reporting_currency")) for r in rows)
		tdr = sum(flt(r.get("debit_in_reporting_currency")) for r in rows)

		net = flt(tc - td, 2)
		net_ac = flt(tci - tdi, 2)
		net_tr = flt(tct - tdt, 2)
		net_rep = flt(tcr - tdr, 2)
		if not net and not net_ac:
			continue

		tmpl = frappe._dict(dict(rows[0]))
		for fld in (
			"debit",
			"credit",
			"debit_in_account_currency",
			"credit_in_account_currency",
			"debit_in_transaction_currency",
			"credit_in_transaction_currency",
			"debit_in_reporting_currency",
			"credit_in_reporting_currency",
		):
			tmpl[fld] = 0
		tmpl["voucher_detail_no"] = None

		if net >= 0:
			tmpl["credit"] = net
			tmpl["credit_in_account_currency"] = net_ac
			tmpl["credit_in_transaction_currency"] = net_tr
			if tmpl.get("credit_in_reporting_currency") is not None or net_rep:
				tmpl["credit_in_reporting_currency"] = net_rep
		else:
			tmpl["debit"] = -net
			tmpl["debit_in_account_currency"] = -net_ac if net_ac else -net
			tmpl["debit_in_transaction_currency"] = -net_tr
			if tmpl.get("debit_in_reporting_currency") is not None or net_rep:
				tmpl["debit_in_reporting_currency"] = -net_rep

		result.append(tmpl)

	return result


class SalesInvoiceOverride(SalesInvoice):
	def validate(self):
		super().validate()
		if self.project and not self.custom_is_advanced and self.is_bill_invoice() and self.docstatus == 0:
			self.apply_automatic_deductions()

	def make_item_gl_entries(self, gl_entries):
		"""Mirror ERPNext income posting but set voucher_detail_no so merged GL stays one row per item row.

		Retention/advance lines must still post to the income account (negative amounts book as debits). Skipping
		them breaks double entry: get_gl_entries gross-up adds credit to Sales without the matching deduction debits.
		"""
		enable_discount_accounting = cint(
			frappe.get_single_value("Selling Settings", "enable_discount_accounting")
		)

		for item in self.get("items"):
			if (
				flt(item.base_net_amount, item.precision("base_net_amount"))
				or item.is_fixed_asset
				or enable_discount_accounting
			):
				if self.is_internal_transfer():
					continue

				if item.is_fixed_asset and item.asset:
					self.get_gl_entries_for_fixed_asset(item, gl_entries)
				else:
					income_account = (
						item.income_account
						if (not item.enable_deferred_revenue or self.is_return)
						else item.deferred_revenue_account
					)

					amount, base_amount = self.get_amount_and_base_amount(item, enable_discount_accounting)

					account_currency = get_account_currency(income_account)
					gl_entries.append(
						self.get_gl_dict(
							{
								"account": income_account,
								"against": self.customer,
								"credit": flt(base_amount, item.precision("base_net_amount")),
								"credit_in_account_currency": (
									flt(base_amount, item.precision("base_net_amount"))
									if account_currency == self.company_currency
									else flt(amount, item.precision("net_amount"))
								),
								"credit_in_transaction_currency": flt(amount, item.precision("net_amount")),
								"cost_center": item.cost_center,
								"project": item.project or self.project,
								"voucher_detail_no": item.name,
							},
							account_currency,
							item=item,
						)
					)

		if cint(self.update_stock) and erpnext.is_perpetual_inventory_enabled(self.company):
			gl_entries += StockController.get_gl_entries(self, None)

	def is_bill_invoice(self):
		is_bill_invoice = False
		for item in self.items:
			if item.get("boq_item"):
				is_bill_invoice = True
				break
		return is_bill_invoice

	def get_item_tax_amount(self, item):
		"""Extract tax amount for a specific item from item_wise_tax_details child table"""
		if not self.get("item_wise_tax_details"):
			# Fallback to sum of taxes if child table is empty (though it should be populated on submit)
			return 0
		
		total_tax = 0
		for detail in self.item_wise_tax_details:
			if detail.item_row == item.name:
				total_tax += flt(detail.amount)
		
		return total_tax

	def get_effective_tax_rate(self):
		"""Extract effective tax rate from taxes table"""
		if not self.get("taxes"):
			return 0
		
		total_tax_rate = 0
		for tax_row in self.taxes:
			if tax_row.rate:
				total_tax_rate += flt(tax_row.rate)
		
		return total_tax_rate / 100  # Convert percentage to decimal


	def before_insert(self):
		"""Auto-set BOQ dimensions on Sales Invoice Items"""
		for item in self.items:
			if item.get("boq_item"):
				# Fetch BOQ Item details
				boq_item = frappe.get_doc("BOQ Item", item.boq_item)
				
				# Set dimensions
				item.bill_no = boq_item.parent_bill
				
				# Ensure boq_item is set (it should already be)
				if not item.boq_item:
					item.boq_item = boq_item.name

	def on_submit(self):
		super().on_submit()
		"""Create ledger entries for BOQ items on invoice submit"""
		
		# 1. First Pass: Identify variance item code and total gross BOQ amount
		variance_item_code = None
		if frappe.db.exists("BOQ Settings", self.company):
			variance_item_code = frappe.db.get_value("BOQ Settings", self.company, "varience_item")
			
		# Buckets for allocation
		boq_items = [] # List of base BOQ item rows
		global_deductions = {
			"retention": 0,
			"advance": 0,
			"variance": 0
		}
		item_specific_deductions = {} # {boq_item_id: {"retention": 0, "advance": 0, "variance": 0}}
		
		total_boq_amount = 0

		for item in self.items:
			is_retention = item.item_code == "RETENTION-DEDUCTION"
			is_advance = item.item_code == "ADVANCE-DEDUCTION"
			is_variance = variance_item_code and item.item_code == variance_item_code
			
			if not (is_retention or is_advance or is_variance) and item.get("boq_item"):
				boq_items.append(item)
				total_boq_amount += flt(item.amount)
			elif (is_retention or is_advance or is_variance):
				target_boq_item = item.get("boq_item")
				val = flt(item.amount) # Deductions are usually negative in rate/amount
				
				if target_boq_item:
					if target_boq_item not in item_specific_deductions:
						item_specific_deductions[target_boq_item] = {"retention": 0, "advance": 0, "variance": 0}
					
					if is_retention: item_specific_deductions[target_boq_item]["retention"] += val
					if is_advance: item_specific_deductions[target_boq_item]["advance"] += val
					if is_variance: item_specific_deductions[target_boq_item]["variance"] += val
				else:
					if is_retention: global_deductions["retention"] += val
					if is_advance: global_deductions["advance"] += val
					if is_variance: global_deductions["variance"] += val

		# 2. Second Pass: Create ledger entries with combined deductions
		tax_rate = self.get_effective_tax_rate()
		discount_amount = flt(getattr(self, "discount_amount", 0))
		discount_share = 0
		if discount_amount > 0 and boq_items:
			discount_share = discount_amount / len(boq_items)

		for item in boq_items:
			boq_id = item.boq_item
			gross_amount = flt(item.amount)
			
			# Specific deductions
			spec = item_specific_deductions.get(boq_id, {"retention": 0, "advance": 0, "variance": 0})
			
			# Pro-rated global deductions
			allocated = {"retention": 0, "advance": 0, "variance": 0}
			if total_boq_amount > 0:
				share = gross_amount / total_boq_amount
				allocated["retention"] = global_deductions["retention"] * share
				allocated["advance"] = global_deductions["advance"] * share
				allocated["variance"] = global_deductions["variance"] * share
			
			# Total deductions for this item
			item_retention = spec["retention"] + allocated["retention"]
			item_advance = spec["advance"] + allocated["advance"]
			item_variance = spec["variance"] + allocated["variance"]
			
			# Calculate base amount (after deductions)
			# Note: Retention, Advance, and Variance are captured as negative values from line items.
			base_amount = gross_amount + item_retention + item_advance + item_variance
			
			# Apply additional discount evenly across BOQ items
			if self.apply_discount_on == "Net Total" and discount_share > 0:
				base_amount = max(0, base_amount - discount_share)

			# Get tax rate and calculate tax on the adjusted base amount
			item_tax = base_amount * tax_rate
			
			# Final BOQ Value = Base Amount + Tax (calculated on adjusted amount)
			net_amount = base_amount + item_tax

			if self.apply_discount_on == "Grand Total" and discount_share > 0:
				net_amount = max(0, net_amount - discount_share)
			
			create_boq_ledger_entry(
				self, 
				item, 
				net_amount=net_amount,
				retention=abs(item_retention), # Storing as positive deduction values
				advance=abs(item_advance),
				variance=abs(item_variance)
			)
			update_boq_item_after_invoice(boq_id)
		
		# Update project completion percentage
		if self.project:
			from construction_management.api.project_completion import update_project_completion
			try:
				update_project_completion(self.project)
			except Exception as e:
				frappe.log_error(f"Error updating project completion: {str(e)}")

		# Fix outstanding_amount field:
		# Custom GL entries create multiple Payment Ledger Entries (Net + Retention).
		# We re-trigger update_voucher_outstanding for the main debit_to account.
		update_voucher_outstanding(
			self.doctype, self.name, self.debit_to, "Customer", self.customer
		)

	def on_cancel(self):
		super().on_cancel()
		"""Create reversing ledger entries on invoice cancel and cancel linked PC"""
		for item in self.items:
			if item.get("boq_item"):
				create_boq_reversal_entry(self, item)
				update_boq_item_after_invoice(item.boq_item)
		
		# Cancel linked Payment Certificate if not already being cancelled from there
		if self.custom_payment_certificate and not self.flags.ignore_payment_certificate_cancel:
			pc_doc = frappe.get_doc("Payment Certificate", self.custom_payment_certificate)
			if pc_doc.docstatus == 1:
				pc_doc.flags.ignore_sales_invoice_cancel = True
				pc_doc.cancel()
				frappe.msgprint(_("Linked Payment Certificate {0} cancelled").format(self.custom_payment_certificate))

		# Update project completion percentage
		if self.project:
			from construction_management.api.project_completion import update_project_completion
			try:
				update_project_completion(self.project)
			except Exception as e:
				frappe.log_error(f"Error updating project completion: {str(e)}")

	def on_update(self):
		"""Handle status changes on update"""
		if self.get("custom_is_advanced") and self.docstatus == 1:
			sync_boq_advance_payments_from_invoice(self)

	def apply_automatic_deductions(self):
		"""Automatically apply/recalculate retention and advance deductions if enabled"""
		if not self.project:
			return
			
		# Skip if deductions are already handled (e.g. from Payment Certificate)
		if self.get("custom_payment_certificate") or self.get("custom_proforma_invoice"):
			return

		from construction_management.api.boq_invoice import (
			get_deduction_details,
			get_or_create_retention_item,
			get_or_create_advance_item,
		)
		
		details = get_deduction_details(self.project, self.items, invoice_name=self.name)
		
		if not details.get("enable_progressive_boq"):
			return

		retention_pct = flt(details.get("retention_percentage"))
		advance_pct = flt(details.get("advance_percentage"))
		skip_advance_set = set(details.get("skip_advance_boq_items") or [])

		# Check if per-item deductions exist (pattern: each BOQ item has paired deduction rows)
		has_per_item_deductions = False
		deduction_boq_items = set()
		for item in self.items:
			if item.item_code in ("RETENTION-DEDUCTION", "ADVANCE-DEDUCTION") and item.get("boq_item"):
				has_per_item_deductions = True
				deduction_boq_items.add(item.boq_item)

		if has_per_item_deductions:
			if skip_advance_set:
				self.set(
					"items",
					[
						item
						for item in self.items
						if not (
							item.item_code == "ADVANCE-DEDUCTION"
							and item.get("boq_item") in skip_advance_set
						)
					],
				)

			# Per-item deduction mode: recalculate each deduction row based on its parent BOQ item
			boq_amounts = {}
			for item in self.items:
				if item.get("boq_item") and item.item_code not in ("RETENTION-DEDUCTION", "ADVANCE-DEDUCTION"):
					boq_amounts[item.boq_item] = flt(item.amount)

			for item in self.items:
				if not item.get("boq_item"):
					continue
				parent_amount = boq_amounts.get(item.boq_item, 0)

				if item.item_code == "RETENTION-DEDUCTION" and retention_pct > 0:
					new_retention = flt(parent_amount * retention_pct / 100, 2)
					item.rate = -new_retention
					item.amount = -new_retention
					item.qty = 1
					item.description = f"Retention deduction ({retention_pct}%)"

				elif item.item_code == "ADVANCE-DEDUCTION" and advance_pct > 0:
					if item.boq_item in skip_advance_set:
						continue
					new_advance = flt(parent_amount * advance_pct / 100, 2)
					item.rate = -new_advance
					item.amount = -new_advance
					item.qty = 1
					item.description = f"Advance deduction ({advance_pct}%)"
		else:
			# Global deduction mode (single row for whole invoice)
			default_income_account = frappe.db.get_value("Company", self.company, "default_income_account")
			default_cost_center = self.cost_center or frappe.db.get_value("Company", self.company, "cost_center")
			
			retention_item = "RETENTION-DEDUCTION"
			if details.get("suggested_retention") > 0:
				get_or_create_retention_item()
				found = False
				for item in self.items:
					if item.item_code == retention_item:
						item.rate = -flt(details["suggested_retention"])
						item.amount = -flt(details["suggested_retention"])
						item.qty = 1
						item.description = f"Retention deduction ({retention_pct}%)"
						item.project = self.project
						found = True
						break
				if not found:
					self.append("items", {
						"item_code": retention_item,
						"qty": 1,
						"rate": -flt(details["suggested_retention"]),
						"amount": -flt(details["suggested_retention"]),
						"description": f"Retention deduction ({retention_pct}%)",
						"project": self.project,
						"income_account": default_income_account,
						"cost_center": default_cost_center,
						"uom": "Nos",
						"conversion_factor": 1.0,
						"item_name": "Retention Deduction"
					})
			else:
				self.set("items", [item for item in self.items if item.item_code != retention_item])

			advance_item = "ADVANCE-DEDUCTION"
			if details.get("suggested_advance") > 0:
				get_or_create_advance_item()
				found = False
				for item in self.items:
					if item.item_code == advance_item:
						item.rate = -flt(details["suggested_advance"])
						item.amount = -flt(details["suggested_advance"])
						item.qty = 1
						item.description = "Deduction from advance payment"
						item.project = self.project
						found = True
						break
				if not found:
					self.append("items", {
						"item_code": advance_item,
						"qty": 1,
						"rate": -flt(details["suggested_advance"]),
						"amount": -flt(details["suggested_advance"]),
						"description": "Deduction from advance payment",
						"project": self.project,
						"income_account": default_income_account,
						"cost_center": default_cost_center,
						"uom": "Nos",
						"conversion_factor": 1.0,
						"item_name": "Advance Deduction"
					})
			else:
				self.set("items", [item for item in self.items if item.item_code != advance_item])

		# Recalculate totals to handle the updated items
		self.run_method("calculate_taxes_and_totals")

	def get_gl_entries(self, warehouse_account=None):
		gl_entries = super().get_gl_entries(warehouse_account)

		# If project is not set, keep default ERPNext posting
		if not self.get("project"):
			return gl_entries

		# Fetch BOQ Settings for the company
		if not frappe.db.exists("BOQ Settings", self.company):
			return gl_entries
		boq_settings = frappe.get_doc("BOQ Settings", self.company)
		retention_account = boq_settings.retention_account
		advance_account = boq_settings.advance_account
		variance_account = boq_settings.varience_account_debit
		variance_item_code = boq_settings.varience_item

		if not (retention_account or advance_account or variance_account):
			# Still need to check if unearned revenue is enabled
			if not boq_settings.enable_so_unearned_revenue_jv:
				return gl_entries

		# 4. Unearned reversal per SI row: (matching SO revenue row base_net × unbilled %) — same BOQ Item as SO line
		unearned_reversal_by_item_row = {}
		unearned_reversal_by_boq_item = {}
		unbilled_revenue_acc = boq_settings.so_unearned_revenue_debit_account
		
		if boq_settings.get("enable_so_unearned_revenue_jv") and unbilled_revenue_acc:
			excluded = set(SO_UNEARNED_EXCLUDED_ITEM_CODES)
			if variance_item_code:
				excluded.add(variance_item_code)

			so_list = list(set(item.sales_order for item in self.items if item.sales_order))
			for so_name in so_list:
				if not find_journal_entry_by_so(so_name):
					continue

				so_doc = frappe.get_cached_doc("Sales Order", so_name)
				pct = flt(so_doc.get("custom_unbilled_revenue_percentage") or 100) / 100.0
				if pct <= 0:
					continue

				inv_lines = [
					it
					for it in self.items
					if it.sales_order == so_name and it.item_code not in excluded
				]
				for item in inv_lines:
					if not item.boq_item:
						continue
					so_line_net = _so_base_net_for_boq_item(so_doc, item.boq_item, excluded)
					if so_line_net <= 0:
						continue
					reversal_amount = flt(so_line_net * pct)
					unearned_reversal_by_item_row[item.name] = (
						unearned_reversal_by_item_row.get(item.name, 0) + reversal_amount
					)
					unearned_reversal_by_boq_item[item.boq_item] = (
						unearned_reversal_by_boq_item.get(item.boq_item, 0) + reversal_amount
					)

		applied_unearned_boq_items = set()

		def _get_unearned_reversal_amount(entry):
			voucher_detail_no = entry.get("voucher_detail_no")
			if voucher_detail_no and voucher_detail_no in unearned_reversal_by_item_row:
				return unearned_reversal_by_item_row[voucher_detail_no]

			boq_item = entry.get("boq_item")
			if boq_item and boq_item in unearned_reversal_by_boq_item and boq_item not in applied_unearned_boq_items:
				return unearned_reversal_by_boq_item[boq_item]
			return 0

		def _apply_unearned_reversal(entry, rev_amt):
			if not rev_amt:
				return

			entry["credit"] = flt(entry.get("credit", 0)) - rev_amt

			if "credit_in_account_currency" in entry:
				entry["credit_in_account_currency"] = flt(entry.get("credit_in_account_currency", 0)) - rev_amt
			if "credit_in_transaction_currency" in entry:
				entry["credit_in_transaction_currency"] = flt(
					entry.get("credit_in_transaction_currency", 0)
				) - rev_amt

			boq_item = entry.get("boq_item")
			voucher_detail_no = entry.get("voucher_detail_no")
			if boq_item:
				applied_unearned_boq_items.add(boq_item)

			unearned_entry = self.get_gl_dict(add_party_if_needed({
				"account": unbilled_revenue_acc,
				"credit": rev_amt,
				"project": entry.get("project"),
				"boq_item": boq_item,
				"bill_no": entry.get("bill_no"),
				"cost_center": entry.get("cost_center"),
				"voucher_detail_no": voucher_detail_no,
				"against": self.customer,
				"remarks": f"Unearned revenue reversal for {self.name}",
			}, unbilled_revenue_acc))

			unearned_entry.update({
				"transaction_currency": self.currency,
				"transaction_exchange_rate": self.get("conversion_rate") or 1,
				"credit_in_transaction_currency": rev_amt,
			})
			new_entries.append(unearned_entry)

		deductions = []
		income_accounts = set()
		for item in self.items:
			if item.income_account:
				income_accounts.add(item.income_account)
			
			target_acc = None
			if item.item_code == "RETENTION-DEDUCTION": target_acc = retention_account
			elif item.item_code == "ADVANCE-DEDUCTION": target_acc = advance_account
			elif variance_item_code and item.item_code == variance_item_code: target_acc = variance_account
			
			if target_acc:
				deductions.append({
					"amount": abs(flt(item.base_amount)), # Base currency
					"transaction_amount": abs(flt(item.amount)), # Transaction currency
					"account": target_acc,
					"boq_item": item.boq_item,
					"bill_no": item.bill_no,
					"cost_center": item.cost_center or self.cost_center,
					"project": item.project or self.project,
					"item_code": item.item_code
				})

		if not deductions and not unearned_reversal_by_item_row and not unearned_reversal_by_boq_item:
			return gl_entries

		# 2. Reconstruct entries
		new_entries = []
		processed_deduction_indices = []
		
		def add_party_if_needed(gl_dict, account):
			acc_type = frappe.db.get_value("Account", account, "account_type")
			if acc_type in ["Receivable", "Payable"]:
				gl_dict.update({
					"party_type": "Customer",
					"party": self.customer
				})
			return gl_dict

		for entry in gl_entries:
			# Match income entries (Credits to an account used in items)
			if entry.get("account") in income_accounts and flt(entry.get("credit")) > 0:
				total_gross_up = 0
				total_gross_up_transaction = 0
				for i, d in enumerate(deductions):
					if i in processed_deduction_indices:
						continue
						
					# Loose match: Project + BOQ Item (most reliable)
					match = (d["project"] == entry.get("project") and 
							 d["boq_item"] == entry.get("boq_item"))
					
					# Fallback for parent level entries or if dimensions are slightly inconsistent
					if not match and not entry.get("boq_item") and not d["boq_item"]:
						match = (d["project"] == entry.get("project") and 
								 d["cost_center"] == entry.get("cost_center"))

					if match:
						total_gross_up += d["amount"]
						total_gross_up_transaction += d["transaction_amount"]
						
						# Create separate debit entry
						# For debit entries, get_gl_dict handles conversion if we pass basic info
						# but we want to be explicit about dimensions
						deduction_entry = self.get_gl_dict(add_party_if_needed({
							"account": d["account"],
							"debit": d["amount"],
							"debit_in_account_currency": d["amount"] if entry.get("account_currency") == self.company_currency else d["transaction_amount"],
							"project": d["project"],
							"boq_item": d["boq_item"],
							"bill_no": d["bill_no"],
							"cost_center": d["cost_center"],
							"against": self.customer,
							"remarks": f"{d['item_code']} for {self.name}"
						}, d["account"]))
						
						# Ensure transaction currency fields are set on deduction
						deduction_entry.update({
							"transaction_currency": self.currency,
							"transaction_exchange_rate": self.get("conversion_rate") or 1,
							"debit_in_transaction_currency": d["transaction_amount"]
						})
						
						new_entries.append(deduction_entry)
						processed_deduction_indices.append(i)
				if total_gross_up > 0:
					# Update all currency-specific credit fields for the income entry
					# User wants the Sales credit to include deductions (Gross Delta), 
					# so we always gross up here.
					entry["credit"] = flt(entry.get("credit", 0)) + total_gross_up
					
					if "credit_in_account_currency" in entry:
						if entry.get("account_currency") == self.currency:
							entry["credit_in_account_currency"] = flt(entry.get("credit_in_account_currency", 0)) + total_gross_up
						else:
							entry["credit_in_account_currency"] = flt(entry.get("credit_in_account_currency", 0)) + total_gross_up_transaction
					
					if "credit_in_transaction_currency" in entry:
						entry["credit_in_transaction_currency"] = flt(entry.get("credit_in_transaction_currency", 0)) + total_gross_up_transaction
					
					if "credit_in_reporting_currency" in entry:
						entry["credit_in_reporting_currency"] = flt(entry.get("credit_in_reporting_currency", 0)) + total_gross_up

				# 4b. Unearned: reduce sales by reversal; credit unbilled (by SI row or BOQ item)
				rev_amt = _get_unearned_reversal_amount(entry)
				_apply_unearned_reversal(entry, rev_amt)
			
			# Only append the income entry if it still has a non-zero amount
			# (100% unearned revenue reversal can reduce credit to 0)
			if flt(entry.get("debit"), 2) or flt(entry.get("credit"), 2):
				new_entries.append(entry)

		# 3. Add any unmatched deductions as orphans
		for i, d in enumerate(deductions):
			if i not in processed_deduction_indices:
				# Try to find a fallback income entry to credit
				for entry in new_entries:
					if entry.get("account") in income_accounts and flt(entry.get("credit")) > 0:
						entry["credit"] = flt(entry.get("credit", 0)) + d["amount"]
						if "credit_in_transaction_currency" in entry:
							entry["credit_in_transaction_currency"] = flt(entry.get("credit_in_transaction_currency", 0)) + d["transaction_amount"]
						if "credit_in_account_currency" in entry:
							if entry.get("account_currency") == self.currency:
								entry["credit_in_account_currency"] = flt(entry.get("credit_in_account_currency", 0)) + d["transaction_amount"]
							else:
								entry["credit_in_account_currency"] = flt(entry.get("credit_in_account_currency", 0)) + d["amount"]
						break
				
				# Add the deduction debit entry
				deduction_entry = self.get_gl_dict(add_party_if_needed({
					"account": d["account"],
					"debit": d["amount"],
					"project": d["project"],
					"boq_item": d["boq_item"],
					"bill_no": d["bill_no"],
					"cost_center": d["cost_center"],
					"against": self.customer,
					"remarks": f"{d['item_code']} for {self.name}"
				}, d["account"]))
				
				deduction_entry.update({
					"transaction_currency": self.currency,
					"transaction_exchange_rate": self.get("conversion_rate") or 1,
					"debit_in_transaction_currency": d["transaction_amount"]
				})
				
				new_entries.append(deduction_entry)
		# Final safety: filter out any entries where both debit and credit are 0
		new_entries = [
			e for e in new_entries
			if float(e.get("debit") or 0) or float(e.get("credit") or 0)
		]
		new_entries = _consolidate_income_gl_by_boq_item(
			new_entries,
			income_accounts,
			unbilled_revenue_acc,
		)
		return new_entries



def _has_legacy_lump_boq_advance(si_name: str) -> bool:
	"""Older builds created one BOQ Advance Payment without linking the Payment Entry reference."""
	row = frappe.db.sql(
		"""
		SELECT name FROM `tabBOQ Advance Payment`
		WHERE linked_invoice = %s AND docstatus = 1 AND IFNULL(reference, '') = ''
		LIMIT 1
		""",
		si_name,
	)
	return bool(row)


def create_boq_advance_payment_from_pe_allocation(
	si_name: str,
	payment_entry_name: str,
	allocated_amount: float,
	posting_date=None,
	project=None,
):
	"""
	Create one BOQ Advance Payment per Payment Entry allocation against an advance Sales Invoice.

	The PE allocates against grand total (incl. taxes); BOQ advance pool uses net-like amounts,
	so we apply the same net/grand ratio used in patches/sync_partial_advance_payments.py.
	"""
	si = frappe.get_doc("Sales Invoice", si_name)
	if not si.get("custom_is_advanced") or si.docstatus != 1:
		return

	if _has_legacy_lump_boq_advance(si.name):
		# Older behaviour: one BOQ Advance Payment without `reference`; cancel it before using installments.
		return

	if frappe.db.exists(
		"BOQ Advance Payment",
		{
			"linked_invoice": si.name,
			"reference": payment_entry_name,
			"docstatus": ["!=", 2],
		},
	):
		return

	allocated_amount = flt(allocated_amount)
	if allocated_amount <= 0:
		return

	base_gt = flt(si.base_grand_total)
	base_nt = flt(si.base_net_total)
	if base_gt <= 0:
		return

	ratio = base_nt / base_gt
	precision = frappe.get_precision("BOQ Advance Payment", "amount") or 2
	net_amount = flt(allocated_amount * ratio, precision)
	if net_amount <= 0:
		return

	adv = frappe.new_doc("BOQ Advance Payment")
	adv.project = project or si.project
	adv.amount = net_amount
	adv.linked_invoice = si.name
	adv.reference = payment_entry_name
	adv.date = posting_date or si.posting_date
	adv.remarks = _("Advance installment from Payment Entry {0} against {1}").format(
		payment_entry_name, si.name
	)

	adv.flags.ignore_permissions = True
	adv.insert()
	adv.submit()


def sync_boq_advance_payments_from_invoice(si):
	"""Ensure BOQ Advance Payment rows exist for every submitted PE allocation against this advance SI."""
	if isinstance(si, str):
		si = frappe.get_doc("Sales Invoice", si)
	if not si.get("custom_is_advanced") or si.docstatus != 1:
		return

	rows = frappe.db.sql(
		"""
		SELECT per.parent AS pe_name, per.allocated_amount, pe.posting_date, pe.project
		FROM `tabPayment Entry Reference` per
		INNER JOIN `tabPayment Entry` pe ON pe.name = per.parent
		WHERE per.reference_doctype = 'Sales Invoice'
			AND per.reference_name = %s
			AND pe.docstatus = 1
			AND IFNULL(per.allocated_amount, 0) > 0
		""",
		si.name,
		as_dict=True,
	)

	for row in rows:
		create_boq_advance_payment_from_pe_allocation(
			si.name,
			row.pe_name,
			row.allocated_amount,
			posting_date=row.posting_date,
			project=row.project,
		)


def sync_boq_advance_payments(doc):
	"""Compatibility alias for scripts expecting this name (see fix_advance_pool.py)."""
	sync_boq_advance_payments_from_invoice(doc)


def create_boq_advance_payment_from_invoice(invoice):
	"""Sync installment-wise advances from Payment Entries (replaces single lump-sum on full payment)."""
	sync_boq_advance_payments_from_invoice(invoice)


def create_boq_ledger_entry(invoice, item, net_amount=None, retention=0, advance=0, variance=0):
	"""
	Create or Update a BOQ Progress Ledger entry for an invoice item.
	Updates existing PC/PI ledger entry if found to maintain single-row-per-cycle.
	"""
	from construction_management.api.boq_ledger import create_ledger_entry, recalculate_ledger_for_item
	
	boq_item = item.boq_item
	amount_to_book = net_amount if net_amount is not None else flt(item.amount)
	
	# Try to find an existing ledger entry to update
	ledger_entry = None
	if invoice.custom_payment_certificate:
		ledger_entry = frappe.db.get_value("BOQ Progress Ledger", {
			"payment_certificate": invoice.custom_payment_certificate,
			"boq_item": boq_item,
		}, "name")
	
	if not ledger_entry and invoice.get("custom_proforma_invoice"):
		ledger_entry = frappe.db.get_value("BOQ Progress Ledger", {
			"proforma_invoice": invoice.custom_proforma_invoice,
			"boq_item": boq_item,
		}, "name")

	if not ledger_entry and item.get("sales_order"):
		ledger_entry = frappe.db.get_value("BOQ Progress Ledger", {
			"boq_item": boq_item,
			"reference_doctype": "Sales Order",
			"reference_name": item.sales_order
		}, "name")
		
	if ledger_entry:
		# Update existing entry with Tax Invoice details
		frappe.db.set_value(
			"BOQ Progress Ledger",
			ledger_entry,
			{
				"tax_invoice": invoice.name,
				"tax_invoice_amount": flt(amount_to_book),
				"source": "Invoice",
				"amount": flt(amount_to_book),
				"retention_amount": flt(retention),
				"advance_deduction": flt(advance),
				"variance": flt(variance)
			},
			update_modified=False
		)
		
		recalculate_ledger_for_item(boq_item)
		return

	if invoice.custom_payment_certificate or invoice.get("custom_proforma_invoice") or any(it.get("sales_order") for it in invoice.items):
		frappe.logger().warning(
			f"Missing ledger row for BOQ Item {boq_item} on invoice {invoice.name}; skipping creation to avoid duplication."
		)
		return
	
	existing = frappe.db.get_value(
		"BOQ Progress Ledger",
		{
			"boq_item": boq_item,
			"reference_doctype": "Sales Invoice",
			"reference_name": invoice.name
		},
		"name"
	)
	if existing:
		return
	
	create_ledger_entry(
		boq_item=boq_item,
		qty=flt(item.qty),
		amount=flt(amount_to_book),
		source="Invoice",
		reference_doctype="Sales Invoice",
		reference_name=invoice.name,
		posting_date=invoice.posting_date or today(),
		remarks=f"Invoice {invoice.name}",
		tax_invoice=invoice.name,
		tax_invoice_amount=flt(amount_to_book),
		retention_amount=flt(retention),
		advance_deduction=flt(advance),
		variance=flt(variance)
	)
	
	recalculate_ledger_for_item(boq_item)


def create_boq_reversal_entry(invoice, item):
	"""
	Undo Tax Invoice impact on the existing BOQ Progress Ledger row.
	"""
	from construction_management.api.boq_ledger import recalculate_ledger_for_item
	
	boq_item = item.boq_item
	is_orphan = not invoice.custom_payment_certificate and not invoice.get("custom_proforma_invoice") and not item.get("sales_order")
	
	ledger_entry = None
	if invoice.custom_payment_certificate:
		ledger_entry = frappe.db.get_value(
			"BOQ Progress Ledger",
			{
				"boq_item": boq_item,
				"payment_certificate": invoice.custom_payment_certificate
			},
			"name"
		)
	
	if not ledger_entry and invoice.get("custom_proforma_invoice"):
		ledger_entry = frappe.db.get_value(
			"BOQ Progress Ledger",
			{
				"boq_item": boq_item,
				"proforma_invoice": invoice.custom_proforma_invoice
			},
			"name"
		)
	
	if not ledger_entry and item.get("sales_order"):
		ledger_entry = frappe.db.get_value(
			"BOQ Progress Ledger",
			{
				"boq_item": boq_item,
				"reference_doctype": "Sales Order",
				"reference_name": item.sales_order
			},
			"name"
		)
	
	if not ledger_entry:
		ledger_entry = frappe.db.get_value(
			"BOQ Progress Ledger",
			{
				"boq_item": boq_item,
				"tax_invoice": invoice.name
			},
			"name"
		)
	
	if ledger_entry:
		if is_orphan:
			frappe.flags.allow_boq_ledger_deletion = True
			try:
				frappe.delete_doc("BOQ Progress Ledger", ledger_entry, force=1, ignore_permissions=True)
			finally:
				frappe.flags.allow_boq_ledger_deletion = False
		else:
			# Get original proforma/order amount to restore
			orig_val = frappe.db.get_value("BOQ Progress Ledger", ledger_entry, "proforma_amount")
			
			frappe.db.set_value(
				"BOQ Progress Ledger",
				ledger_entry,
				{
					"tax_invoice": None,
					"tax_invoice_amount": 0,
					"amount": flt(orig_val), # Restore original value
					"remarks": f"Reversal of Invoice {invoice.name}",
					"source": "Order" if item.get("sales_order") else ("Proforma" if invoice.get("custom_proforma_invoice") else "Adjustment")
				},
				update_modified=False
			)
		
		recalculate_ledger_for_item(boq_item)


def update_boq_item_after_invoice(boq_item_name):
	"""
	Update BOQ Item calculated fields after invoice submit/cancel.
	"""
	boq_item = frappe.get_doc("BOQ Item", boq_item_name)
	boq_item.current_qty = 0
	boq_item.calculate_amounts()
	boq_item.update_billing_status()
	boq_item.db_update()
	
	if boq_item.parent_bill:
		bill = frappe.get_doc("BOQ Bill", boq_item.parent_bill)
		bill.calculate_totals()
		bill.db_update()
	
	if boq_item.project_boq:
		project_boq = frappe.get_doc("Project BOQ", boq_item.project_boq)
		project_boq.calculate_totals()
		project_boq.db_update()

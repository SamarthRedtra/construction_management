# Copyright (c) 2026, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class ProjectClosure(Document):
	def validate(self):
		self.calculate_totals()

	def before_submit(self):
		self.status = "Submitted"

	def on_cancel(self):
		self.status = "Cancelled"

	def calculate_totals(self):
		"""Recalculate item totals and financial summaries."""
		# Calculate each item's total
		for item in self.items:
			item.total_amount = flt(item.area_qty) * flt(item.unit_price)

		# Services subtotal
		self.services_subtotal = sum(flt(item.total_amount) for item in self.items)

		# Total actual cost (consolidated)
		self.total_actual_cost = (
			flt(self.actual_material_cost)
			+ flt(self.actual_labour_cost)
			+ flt(self.actual_asset_cost)
			+ flt(self.actual_subcontract_cost)
			+ flt(self.actual_overhead_cost)
			+ flt(self.actual_expense_cost)
		)

		# Gross profit
		self.gross_profit = flt(self.total_revenue) - flt(self.total_actual_cost)
		if flt(self.total_revenue):
			self.gross_profit_percent = (
				flt(self.gross_profit) / flt(self.total_revenue) * 100
			)
		else:
			self.gross_profit_percent = 0


@frappe.whitelist()
def fetch_project_data(project):
	"""
	Fetch all BOQ and DPR data for a project to populate the Project Closure form.

	Args:
		project: Project name

	Returns:
		dict with items, cost breakdowns, and revenue data
	"""
	if not project:
		frappe.throw(_("Project is required"))

	project_doc = frappe.get_doc("Project", project)
	contractor_name = ""
	if getattr(project_doc, "contractor", None):
		contractor_name = frappe.db.get_value("Supplier", project_doc.contractor, "supplier_name") or ""
	engineer_name = ""
	if getattr(project_doc, "custom_project_engineer", None):
		engineer_name = (
			frappe.db.get_value("Employee", project_doc.custom_project_engineer, "employee_name") or ""
		)

	# Get Project BOQ
	project_boq = frappe.db.get_value(
		"Project BOQ",
		{"project": project},
		["name", "total_boq_value"],
		as_dict=True,
	)

	# Get all BOQ Items for this project with bill info and cost/revenue
	boq_items = frappe.db.get_all(
		"BOQ Item",
		filters={"project": project},
		fields=[
			"name",
			"label",
			"parent_bill",
			"total_qty",
			"unit",
			"rate",
			"total_amount",
			"estimated_material_cost",
			"estimated_labour_cost",
			"estimated_asset_cost",
			"estimated_subcontract_cost",
			"estimated_other_cost",
			"total_estimated_cost",
			"cost_to_date",
			"labour_cost",
			"material_cost",
			"subcontract_cost",
			"asset_cost",
			"expense_cost",
			"overhead_cost",
			"to_date_amount",
			"total_retention_amount",
			"total_advance_deducted",
			"margin",
			"billing_status",
		],
		order_by="parent_bill asc, idx asc",
	)

	# Aggregate estimated costs from BOQ items
	total_est_material = total_est_labour = total_est_asset = total_est_subcontract = total_est_other = total_est = 0.0

	# Initialize actual cost accumulators
	total_act_material = total_act_labour = total_act_asset = total_act_subcontract = total_act_overhead = total_act_expense = 0.0

	items = []
	for idx, item in enumerate(boq_items, 1):
		bill_no = ""
		if item.parent_bill:
			bill_no = frappe.db.get_value("BOQ Bill", item.parent_bill, "bill_no") or ""

		# Aggregate estimated costs
		total_est_material += flt(item.estimated_material_cost)
		total_est_labour += flt(item.estimated_labour_cost)
		total_est_asset += flt(item.estimated_asset_cost)
		total_est_subcontract += flt(item.estimated_subcontract_cost)
		total_est_other += flt(item.estimated_other_cost)
		total_est += flt(item.total_estimated_cost)

		# Aggregate actual costs
		total_act_material += flt(item.material_cost)
		total_act_labour += flt(item.labour_cost)
		total_act_asset += flt(item.asset_cost)
		total_act_subcontract += flt(item.subcontract_cost)
		total_act_overhead += flt(item.overhead_cost)
		total_act_expense += flt(item.expense_cost)

		items.append(
			{
				"sr_no": idx,
				"service_description": item.label or item.name,
				"boq_item": item.name,
				"bill_no": bill_no,
				"billing_status": item.billing_status or "Not Billed",
				"area_qty": flt(item.total_qty),
				"uom": item.unit or "",
				"unit_price": flt(item.rate),
				"total_amount": flt(item.total_amount),
				"estimated_material_cost": flt(item.estimated_material_cost),
				"estimated_labour_cost": flt(item.estimated_labour_cost),
				"estimated_asset_cost": flt(item.estimated_asset_cost),
				"estimated_subcontract_cost": flt(item.estimated_subcontract_cost),
				"estimated_other_cost": flt(item.estimated_other_cost),
				"total_estimated_cost": flt(item.total_estimated_cost),
				"cost_to_date": flt(item.cost_to_date),
				"labour_cost": flt(item.labour_cost),
				"material_cost": flt(item.material_cost),
				"subcontract_cost": flt(item.subcontract_cost),
				"asset_cost": flt(item.asset_cost),
				"expense_cost": flt(item.expense_cost),
				"overhead_cost": flt(item.overhead_cost),
				"to_date_amount": flt(item.to_date_amount),
				"retention_amount": flt(item.total_retention_amount),
				"advance_amount": flt(item.total_advance_deducted),
				"margin": flt(item.margin),
			}
		)

	# Calculate total actual cost from components
	total_act = (
		total_act_material
		+ total_act_labour
		+ total_act_asset
		+ total_act_subcontract
		+ total_act_overhead
		+ total_act_expense
	)

	# Get revenue from BOQ Progress Ledger
	total_revenue = (
		frappe.db.sql(
			"""
		SELECT COALESCE(SUM(amount), 0)
		FROM `tabBOQ Progress Ledger`
		WHERE project = %s AND source = 'Invoice'
	""",
			project,
		)[0][0]
		or 0
	)

	# Get retention and advance summary
	from construction_management.api.boq_tree import get_retention_summary, get_advance_summary

	retention_summary = get_retention_summary(project)
	advance_summary = get_advance_summary(project)

	return {
		"project_name": project_doc.project_name or "",
		"contractor_name": contractor_name,
		"engineer_name": engineer_name,
		"project_boq": project_boq.name if project_boq else None,
		"total_boq_value": flt(project_boq.total_boq_value) if project_boq else 0,
		"items": items,
		# Estimated cost (consolidated from BOQ items)
		"estimated_material_cost": total_est_material,
		"estimated_labour_cost": total_est_labour,
		"estimated_asset_cost": total_est_asset,
		"estimated_subcontract_cost": total_est_subcontract,
		"estimated_other_cost": total_est_other,
		"total_estimated_cost": total_est,
		# Actual cost (from BOQ Items aggregation)
		"actual_material_cost": total_act_material,
		"actual_labour_cost": total_act_labour,
		"actual_asset_cost": total_act_asset,
		"actual_subcontract_cost": total_act_subcontract,
		"actual_overhead_cost": total_act_overhead,
		"actual_expense_cost": total_act_expense,
		"total_actual_cost": total_act,
		"total_revenue": flt(total_revenue),
		"retention_pending": flt(retention_summary.get("retention_balance", 0)),
		"advance_balance": flt(advance_summary.get("balance", 0)),
	}

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

		# Total project cost
		self.total_project_cost = (
			flt(self.labour_cost)
			+ flt(self.material_cost)
			+ flt(self.other_cost)
		)

		# Gross profit
		self.gross_profit = flt(self.total_revenue) - flt(self.total_project_cost)
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

	items = []
	for idx, item in enumerate(boq_items, 1):
		bill_no = ""
		if item.parent_bill:
			bill_no = frappe.db.get_value("BOQ Bill", item.parent_bill, "bill_no") or ""

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

	# Get cost breakdown from Daily Progress Records
	cost_data = frappe.db.sql(
		"""
		SELECT
			COALESCE(SUM(labour_cost), 0) as labour_cost,
			COALESCE(SUM(material_cost), 0) as material_cost,
			COALESCE(SUM(asset_cost), 0) as asset_cost,
			COALESCE(SUM(subcontract_cost), 0) as subcontract_cost,
			COALESCE(SUM(expense_cost), 0) as expense_cost,
			COALESCE(SUM(overhead_cost), 0) as overhead_cost,
			COALESCE(SUM(total_cost), 0) as total_cost
		FROM `tabDaily Progress Record`
		WHERE project = %s AND docstatus = 1
	""",
		project,
		as_dict=True,
	)[0]

	# Other cost = asset + subcontract + expense + overhead
	other_cost = (
		flt(cost_data.asset_cost)
		+ flt(cost_data.subcontract_cost)
		+ flt(cost_data.expense_cost)
		+ flt(cost_data.overhead_cost)
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
		"project_boq": project_boq.name if project_boq else None,
		"total_boq_value": flt(project_boq.total_boq_value) if project_boq else 0,
		"items": items,
		"labour_cost": flt(cost_data.labour_cost),
		"material_cost": flt(cost_data.material_cost),
		"other_cost": flt(other_cost),
		"total_project_cost": flt(cost_data.total_cost),
		"total_revenue": flt(total_revenue),
		"retention_pending": flt(retention_summary.get("retention_balance", 0)),
		"advance_balance": flt(advance_summary.get("balance", 0)),
	}

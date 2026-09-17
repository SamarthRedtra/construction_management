import frappe

from construction_management.api.boq_ledger import recalculate_ledger_for_item
from construction_management.overrides.sales_order import create_ledger_entries


TARGET_BOQ_ITEM = "BOQI-2026-00728"


def execute():
	"""Repair cumulative monthly certificates for the affected P-153 BOQ."""
	if not frappe.db.exists("BOQ Item", TARGET_BOQ_ITEM):
		return

	project = frappe.db.get_value("BOQ Item", TARGET_BOQ_ITEM, "project")
	if not project:
		return

	order_names = frappe.db.sql(
		"""
		SELECT DISTINCT so.name, so.transaction_date, so.creation
		FROM `tabSales Order` so
		INNER JOIN `tabSales Order Item` soi ON soi.parent = so.name
		INNER JOIN `tabBOQ Item` bi ON bi.name = soi.boq_item
		WHERE so.docstatus = 1
		  AND bi.project = %s
		ORDER BY so.transaction_date ASC, so.creation ASC
		""",
		project,
		as_dict=True,
	)
	for row in order_names:
		create_ledger_entries(frappe.get_doc("Sales Order", row.name))

	for boq_item in frappe.get_all(
		"BOQ Item", filters={"project": project}, pluck="name"
	):
		recalculate_ledger_for_item(boq_item)


import frappe

from construction_management.construction_management.doctype.boq_item.boq_item import check_rate_history_table


def execute():
	check_rate_history_table()

	columns = {
		"prev_qty": "DECIMAL(18, 6) DEFAULT 0",
		"prev_amount": "DECIMAL(18, 6) DEFAULT 0",
		"balance_qty": "DECIMAL(18, 6) DEFAULT 0",
		"balance_value": "DECIMAL(18, 6) DEFAULT 0",
	}

	for column, definition in columns.items():
		if not frappe.db.has_column("BOQ Rate History", column):
			frappe.db.sql(
				f"ALTER TABLE `tabBOQ Rate History` ADD COLUMN `{column}` {definition}"
			)

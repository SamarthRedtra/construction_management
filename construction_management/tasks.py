# Copyright (c) 2024, Construction Management
# License: MIT

"""
Scheduled tasks for Construction Management app.
"""

import frappe


# These system items are created programmatically to represent deductions/advance
# values only, so any Item Price rows on them should be removed automatically.
SPECIAL_ITEM_PRICE_CLEANUP_CODES = (
	"RETENTION-DEDUCTION",
	"ADVANCE-DEDUCTION",
	"PURCHASE-ADVANCE",
)


def send_task_reminders():
	"""Send daily reminders for pending construction tasks"""
	# Placeholder for task reminder functionality
	pass


def check_overdue_tasks():
	"""Check and flag overdue construction tasks"""
	# Placeholder for overdue task checking
	pass


def send_weekly_report():
	"""Send weekly construction progress report"""
	# Placeholder for weekly report functionality
	pass


def delete_special_item_prices():
	"""Delete Item Price records created for system-managed deduction items."""
	item_prices = frappe.get_all(
		"Item Price",
		filters={"item_code": ["in", SPECIAL_ITEM_PRICE_CLEANUP_CODES]},
		fields=["name", "item_code", "price_list"],
		limit_page_length=0,
	)

	if not item_prices:
		return 0

	deleted_count = 0

	for item_price in item_prices:
		try:
			frappe.delete_doc("Item Price", item_price.name, force=True, ignore_permissions=True)
			deleted_count += 1
		except Exception:
			frappe.log_error(
				title="Special item price cleanup failed",
				message=(
					f"Failed to delete Item Price {item_price.name} for item {item_price.item_code} "
					f"from price list {item_price.price_list}.\n\n{frappe.get_traceback()}"
				),
			)

	if deleted_count:
		frappe.logger().info(
			f"Deleted {deleted_count} item price record(s) for system-managed advance/deduction items"
		)

	return deleted_count

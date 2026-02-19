
import frappe
from construction_management.api.boq_tree import update_boq_item_base

def run():
	# Get a sample BOQ Item
	item_name = frappe.db.get_value("BOQ Item", {"total_qty": [">", 0]}, "name")
	if not item_name:
		print("No BOQ Item found for testing")
		return

	print(f"Testing with BOQ Item: {item_name}")
	
	original_item = frappe.get_doc("BOQ Item", item_name)
	orig_qty = original_item.total_qty
	orig_rate = original_item.rate
	
	print(f"Original Qty: {orig_qty}, Rate: {orig_rate}")
	
	# Test updating Qty
	new_qty = float(orig_qty) + 10
	update_boq_item_base(item_name, total_qty=new_qty)
	
	item = frappe.get_doc("BOQ Item", item_name)
	print(f"New Qty: {item.total_qty}")
	assert float(item.total_qty) == float(new_qty), "Qty update failed"
	
	# Test updating Rate
	new_rate = float(orig_rate) + 5
	update_boq_item_base(item_name, rate=new_rate)
	
	item = frappe.get_doc("BOQ Item", item_name)
	print(f"New Rate: {item.rate}")
	assert float(item.rate) == float(new_rate), "Rate update failed"
	
	# Restore original values
	update_boq_item_base(item_name, total_qty=orig_qty, rate=orig_rate)
	print("Restored original values. Test passed!")

if __name__ == "__main__":
	run()

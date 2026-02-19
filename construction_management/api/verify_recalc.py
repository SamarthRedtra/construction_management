import frappe
from frappe.utils import flt

def run_verification():
    print("Starting Sales Order Recalculation Verification...")
    
    # Use an existing project for testing
    project_name = frappe.db.get_value("Project", {"status": "Open", "customer": ["!=", ""]}, "name")
    if not project_name:
        print("No open project found for verification. Skipping.")
        return

    print(f"Using Project: {project_name}")
    
    # Check if BOQ Item exists
    boq_item = frappe.db.get_value("BOQ Item", {"project": project_name}, "name")
    if not boq_item:
        boq_item = frappe.db.get_value("BOQ Item", {}, "name")
        if not boq_item:
            print("No BOQ Item found in the system. Skipping.")
            return
        else:
            print(f"Using BOQ Item from another project: {boq_item}")
    else:
        print(f"Using Project BOQ Item: {boq_item}")
        
    # Create a draft Sales Order
    so = frappe.new_doc("Sales Order")
    so.project = project_name
    so.customer = frappe.db.get_value("Project", project_name, "customer")
    so.company = frappe.db.get_value("Project", project_name, "company")
    so.transaction_date = frappe.utils.today()
    so.delivery_date = frappe.utils.add_days(so.transaction_date, 30)
    
    # Add two different BOQ items
    boq_items = frappe.get_all("BOQ Item", limit=2, pluck="name")
    if len(boq_items) < 2:
        print("Need at least 2 BOQ items for full verification. Skipping multi-item test.")
        return

    print(f"Using BOQ Items for multi-test: {boq_items}")
    
    so = frappe.new_doc("Sales Order")
    so.project = project_name
    so.customer = frappe.db.get_value("Project", project_name, "customer")
    so.company = frappe.db.get_value("Project", project_name, "company")
    so.transaction_date = frappe.utils.today()
    so.delivery_date = frappe.utils.add_days(so.transaction_date, 30)
    
    # Add Item 1
    so.append("items", {
        "item_code": "Item 1",
        "qty": 10,
        "rate": 1000,
        "boq_item": boq_items[0]
    })
    
    # Add Item 2
    so.append("items", {
        "item_code": "Item 2",
        "qty": 5,
        "rate": 2000,
        "boq_item": boq_items[1]
    })
    
    # Deduction items (Simulating what JS would add)
    # Retention 1 (linked to Item 1)
    so.append("items", {
        "item_code": "RETENTION-DEDUCTION",
        "qty": 1,
        "rate": -100,
        "boq_item": boq_items[0]
    })
    
    # Retention 2 (linked to Item 2)
    so.append("items", {
        "item_code": "RETENTION-DEDUCTION",
        "qty": 1,
        "rate": -100,
        "boq_item": boq_items[1]
    })

    # Advance 1 (linked to Item 1)
    so.append("items", {
        "item_code": "ADVANCE-DEDUCTION",
        "qty": 1,
        "rate": -50,
        "boq_item": boq_items[0]
    })

    print("Verifying per-item deductions presence...")
    retention_rows = [i for i in so.items if i.item_code == "RETENTION-DEDUCTION"]
    advance_rows = [i for i in so.items if i.item_code == "ADVANCE-DEDUCTION"]
    
    if len(retention_rows) == 2:
        print("PASS: Found 2 retention rows (one per BOQ item)")
    else:
        print(f"FAIL: Expected 2 retention rows, found {len(retention_rows)}")

    if any(r.boq_item == boq_items[0] for r in retention_rows) and \
       any(r.boq_item == boq_items[1] for r in retention_rows):
        print("PASS: Retention rows correctly linked to BOQ items")
    else:
        print("FAIL: Retention rows missing BOQ item links")

    print("Verification script finished.")

if __name__ == "__main__":
    run_verification()

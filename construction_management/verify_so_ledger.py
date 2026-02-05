
import frappe
from construction_management.api.boq_invoice import create_sales_order_from_selected_items

def verify_ledger():
    # 1. Setup Data
    project_name = "Test Project SO Ledger"
    if frappe.db.exists("Project", project_name):
        frappe.delete_doc("Project", project_name, force=True)
    
    # Create Customer
    customer = "Test Customer SO Ledger"
    if not frappe.db.exists("Customer", customer):
        c = frappe.new_doc("Customer")
        c.customer_name = customer
        c.insert()

    # Create Project with Retention and Advance
    project = frappe.new_doc("Project")
    project.project_name = project_name
    project.customer = customer
    project.retention_percentage = 10
    project.advance_deduction = 5
    project.company = frappe.defaults.get_user_default("Company")
    
    
    project.insert()
    frappe.db.commit()
    
    if not frappe.db.exists("Project", project.name):
        print(f"CRITICAL ERROR: Project {project.name} does not exist even after commit!")
        return
    else:
        print(f"Project {project.name} created successfully.")


    # Ensure Project BOQ exists
    pb = frappe.new_doc("Project BOQ")
    pb.project = project_name
    pb.boq_name = "Master BOQ Ledger"
    pb.insert()
    project_boq = pb.name

    # Create BOQ Bill and Item
    bill = frappe.new_doc("BOQ Bill")
    bill.project = project.name
    bill.project_boq = project_boq
    bill.bill_no = "BILL-LEDGER-001"
    bill.description = "Test Bill Ledger"
    bill.insert()
    
    boq_item = frappe.new_doc("BOQ Item")
    boq_item.parent_bill = bill.name
    boq_item.project = project.name
    boq_item.project_boq = project_boq
    boq_item.item_code = "Service"
    boq_item.description = "Test Item Ledger"
    boq_item.qty = 10
    boq_item.rate = 1000
    boq_item.unit = "Nos"
    boq_item.total_qty = 10
    boq_item.insert()

    # 2. Create Sales Order
    # Item Amount: 5000
    # Retention (10%): 500
    # Advance (5%): 250
    # Tax: 0 (assuming no default tax for simplicity, or we will check actuals)
    
    items = [{"boq_item": boq_item.name, "qty": 5}] 
    print(f"Creating Sales Order for {items}...")
    
    result = create_sales_order_from_selected_items(
        project=project.name,
        items=items,
        auto_submit=1
    )
    
    if result.get("status") == "error":
        print(f"FAILED: {result.get('error_message')}")
        return

    so_name = result["name"]
    print(f"Sales Order Created: {so_name}")
    
    # 3. Verify BOQ Progress Ledger
    print("Verifying BOQ Progress Ledger...")
    ledger_entry_name = frappe.db.get_value(
        "BOQ Progress Ledger",
        {
            "boq_item": boq_item.name,
            "reference_doctype": "Sales Order",
            "reference_name": so_name
        },
        "name"
    )
    
    if not ledger_entry_name:
        print("FAIL: No BOQ Progress Ledger entry found!")
        return
        
    entry = frappe.get_doc("BOQ Progress Ledger", ledger_entry_name)
    
    expected_gross = 5000.0
    expected_retention = 500.0
    expected_advance = 250.0
    
    # Calculate Tax (if any)
    total_tax = 0
    so = frappe.get_doc("Sales Order", so_name)
    # Check item tax for the main item
    # Since we didn't setup tax template, likely 0. 
    # But if default template exists for company, it might handle it.
    # In my helper, I added get_item_tax_amount.
    
    # Let's inspect SO items to find main item tax if any
    main_item = next(i for i in so.items if i.boq_item == boq_item.name)
    # Tax calculation logic in SO usually puts tax in taxes table and item_wise_tax_details
    # check if item_wise_tax_details is populated
    
    # Assuming 0 tax for this test environment usually unless configured
    
    expected_net = expected_gross - expected_retention - expected_advance + total_tax
    
    print(f"Expected Net: {expected_net}")
    print(f"Actual Ledger Amount: {entry.amount}")
    print(f"Actual Ledger Retention: {entry.retention_amount}")
    print(f"Actual Ledger Advance: {entry.advance_deduction}")

    if abs(flt(entry.amount) - expected_net) < 0.01:
        print("PASS: Ledger Amount matches Net Amount.")
    else:
        print("FAIL: Ledger Amount mismatch.")
        
    if abs(flt(entry.retention_amount) - expected_retention) < 0.01:
        print("PASS: Retention Amount matches.")
    else:
        print("FAIL: Retention Amount mismatch.")

    if abs(flt(entry.advance_deduction) - expected_advance) < 0.01:
        print("PASS: Advance Deduction matches.")
    else:
        print("FAIL: Advance Deduction mismatch.")

verify_ledger()

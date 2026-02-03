import frappe
from frappe.utils import flt, today
from construction_management.api.boq_invoice import create_invoice_from_boq_item
from construction_management.construction_management.doctype.payment_certificate.payment_certificate import create_payment_certificate_from_sales_order
from construction_management.api.boq_ledger import recalculate_ledger_for_item

def setup_test_data():
    # Setup Project
    project_title = "Test Billing Project"
    project_id = frappe.db.get_value("Project", {"project_name": project_title}, "name")
    
    if not project_id:
        project = frappe.new_doc("Project")
        project.project_name = project_title
        project.status = "Open"
        project.customer = "Test Customer"
        project.company = frappe.db.get_value("Company", {}, "name")
        project.insert()
        project_id = project.name
    
    project = frappe.get_doc("Project", project_id)
    if not project.customer:
        project.customer = "Test Customer"
        project.save()
    
    # Setup BOQ Item
    boq_item_description = "Test Billing BOQ Item"
    item = frappe.get_all("BOQ Item", filters={"description": boq_item_description}, limit=1)
    if not item:
        # Create Project BOQ
        project_boq = frappe.new_doc("Project BOQ")
        project_boq.project = project.name
        project_boq.boq_name = "Test BOQ"
        project_boq.status = "Draft"
        project_boq.insert()

        boq_bill = frappe.new_doc("BOQ Bill")
        boq_bill.bill_no = "B-001"
        boq_bill.project = project.name
        boq_bill.project_boq = project_boq.name
        boq_bill.insert()
        
        item = frappe.new_doc("BOQ Item")
        item.description = boq_item_description
        item.project = project.name
        item.project_boq = project_boq.name
        item.parent_bill = boq_bill.name
        item.total_qty = 100
        item.rate = 100
        item.unit = "Nos"
        item.insert()
    else:
        item = frappe.get_doc("BOQ Item", item[0].name)
        
    return project, item

def test_orphan_si_cancellation():
    print("\n--- Testing Orphan SI Cancellation ---")
    project, item = setup_test_data()
    
    # 1. Create SI from BOQ Item
    print("Creating Orphan Sales Invoice...")
    res = create_invoice_from_boq_item(project.name, item.name, 10)
    si_name = res["invoice"]
    si = frappe.get_doc("Sales Invoice", si_name)
    si.submit()
    
    item.reload()
    print(f"Post-Submission - To Date Qty: {item.to_date_qty}, Billing Status: {item.billing_status}")
    
    # 2. Cancel SI
    print("Cancelling Sales Invoice...")
    si.cancel()
    
    item.reload()
    print(f"Post-Cancellation - To Date Qty: {item.to_date_qty}, Billing Status: {item.billing_status}")
    
    if flt(item.to_date_qty) == 0:
        print("SUCCESS: Orphan SI cancellation reverted To Date Qty to 0.")
    else:
        print(f"FAILURE: To Date Qty is {item.to_date_qty}, expected 0.")

def test_pc_si_cancellation():
    print("\n--- Testing PC -> SI Cancellation ---")
    project, item = setup_test_data()
    
    # 1. Create SO
    from construction_management.api.boq_invoice import create_invoice_from_boq_item # Reuse for part of logic or SO helper
    so = frappe.new_doc("Sales Order")
    so.customer = project.customer or frappe.get_all("Customer", limit=1)[0].name
    so.project = project.name
    so.delivery_date = today()
    so.append("items", {
        "item_code": item.linked_item or "Service",
        "qty": 20,
        "rate": 100,
        "delivery_date": today(),
        "boq_item": item.name
    })
    so.submit()
    print(f"Created SO: {so.name}")
    
    # 2. Create PC from SO
    pc_res = create_payment_certificate_from_sales_order(so.name)
    pc = frappe.get_doc("Payment Certificate", pc_res["name"])
    
    # Introduce Variance
    pc.items[0].accepted_amount = 1500 # Original was 2000 (20 * 100)
    pc.submit()
    print(f"Created PC: {pc.name} with accepted_amount 1500 (PC Variance: 500)")
    
    item.reload()
    print(f"Post-PC Submission - To Date Amount: {item.to_date_amount}") # Should be 2000 since PC is draft or order is active
    
    # 3. Tax Invoice is auto-created by PC submission
    si_name = pc.tax_invoice
    print(f"Auto-created SI: {si_name}")
    
    item.reload()
    print(f"Post-SI Submission - To Date Amount: {item.to_date_amount}") # Should be 1500
    
    # 4. Cancel SI
    si = frappe.get_doc("Sales Invoice", si_name)
    si.cancel()
    print("Cancelled Sales Invoice (should auto-cancel PC).")
    
    pc.reload()
    print(f"PC Status: {pc.status}, Docstatus: {pc.docstatus}")
    
    item.reload()
    print(f"Post-SI/PC Cancellation - To Date Amount: {item.to_date_amount}") # Should go back to 2000 (Order amount)
    
    if flt(item.to_date_amount) == 2000:
        print("SUCCESS: PC -> SI chain cancellation behaved correctly.")
    else:
        print(f"FAILURE: Final To Date Amount is {item.to_date_amount}, expected 2000.")

def run_tests():
    try:
        test_orphan_si_cancellation()
        test_pc_si_cancellation()
    finally:
        frappe.db.rollback()

if __name__ == "__main__":
    run_tests()

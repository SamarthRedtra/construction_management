import frappe
from frappe.utils import flt, today

def setup_refined_test_data():
    # Setup Project
    project_title = "Refined Allocation Project"
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

    # Setup 2 BOQ Items
    boq_items = []
    for i in range(1, 3):
        desc = f"Refined Item {i}"
        item_name = frappe.db.get_value("BOQ Item", {"description": desc}, "name")
        if not item_name:
            # Create Project BOQ
            pb_name = frappe.db.get_value("Project BOQ", {"project": project.name}, "name")
            if not pb_name:
                pb = frappe.new_doc("Project BOQ")
                pb.project = project.name
                pb.boq_name = "Refined BOQ"
                pb.status = "Draft"
                pb.insert()
                pb_name = pb.name

            bill_name = frappe.db.get_value("BOQ Bill", {"project": project.name}, "name")
            if not bill_name:
                bill = frappe.new_doc("BOQ Bill")
                bill.bill_no = "RB-001"
                bill.project = project.name
                bill.project_boq = pb_name
                bill.insert()
                bill_name = bill.name
            
            item = frappe.new_doc("BOQ Item")
            item.description = desc
            item.project = project.name
            item.project_boq = pb_name
            item.parent_bill = bill_name
            item.total_qty = 100
            item.rate = 100
            item.unit = "Nos"
            item.insert()
            item_name = item.name
        
        boq_items.append(frappe.get_doc("BOQ Item", item_name))
        
    return project, boq_items

def test_item_wise_allocation():
    print("\n--- Testing Item-wise Ledger Allocation ---")
    project, items = setup_refined_test_data()
    
    # Identify Variance Item
    variance_item_code = frappe.db.get_value("BOQ Settings", project.company, "varience_item")
    if not variance_item_code:
        # Create a dummy variance item if not set
        frappe.db.set_value("BOQ Settings", project.company, "varience_item", "VARIANCE")
        variance_item_code = "VARIANCE"

    si = frappe.new_doc("Sales Invoice")
    si.customer = project.customer
    si.project = project.name
    si.company = project.company
    si.currency = frappe.db.get_value("Company", si.company, "default_currency")
    si.conversion_rate = 1.0
    si.posting_date = today()
    si.debit_to = frappe.get_all("Account", filters={"account_type": "Receivable", "company": project.company}, limit=1)[0].name
    
    default_income_account = frappe.db.get_value("Company", si.company, "default_income_account")

    item_code = frappe.get_all("Item", filters={"is_sales_item": 1}, limit=1)[0].name

    cost_center = frappe.get_all("Cost Center", filters={"company": si.company, "is_group": 0}, limit=1)[0].name

    # 1. Base Items
    # Item 1: 10 qty * 100 = 1000
    # Item 2: 20 qty * 100 = 2000
    # Total Gross: 3000
    si.append("items", {
        "item_code": item_code, 
        "qty": 10, 
        "rate": 100, 
        "boq_item": items[0].name,
        "income_account": default_income_account,
        "cost_center": cost_center
    })
    si.append("items", {
        "item_code": item_code, 
        "qty": 20, 
        "rate": 100, 
        "boq_item": items[1].name,
        "income_account": default_income_account,
        "cost_center": cost_center
    })
    
    # 2. Specific Deductions
    # Retention for Item 1: -100
    si.append("items", {
        "item_code": "RETENTION-DEDUCTION", 
        "qty": 1, 
        "rate": -100, 
        "boq_item": items[0].name,
        "income_account": default_income_account,
        "cost_center": cost_center
    })
    # Variance for Item 2: -500
    si.append("items", {
        "item_code": variance_item_code, 
        "qty": 1, 
        "rate": -500, 
        "boq_item": items[1].name,
        "income_account": default_income_account,
        "cost_center": cost_center
    })
    
    # 3. Global Deduction
    # Advance deduction: -600 (Global)
    # Allocation for Item 1 (1/3 share): -200
    # Allocation for Item 2 (2/3 share): -400
    si.append("items", {
        "item_code": "ADVANCE-DEDUCTION", 
        "qty": 1, 
        "rate": -600,
        "income_account": default_income_account,
        "cost_center": cost_center
    })
    
    si.insert()
    si.submit()
    print(f"Submitted SI: {si.name}")
    
    # Verify Ledger Entries
    # Item 1 Expected: 
    # Gross: 1000
    # Retention: 100 (specific)
    # Advance: 200 (pro-rated)
    # Variance: 0
    # Net in tax_invoice_amount: 1000 - 0 = 1000 (Base Net)
    
    # Item 2 Expected:
    # Gross: 2000
    # Retention: 0
    # Advance: 400 (pro-rated)
    # Variance: 500 (specific)
    # Net in tax_invoice_amount: 2000 - 500 = 1500 (Base Net)
    
    l1 = frappe.get_all("BOQ Progress Ledger", filters={"reference_name": si.name, "boq_item": items[0].name}, 
                        fields=["tax_invoice_amount", "retention_amount", "advance_deduction", "variance"])
    l2 = frappe.get_all("BOQ Progress Ledger", filters={"reference_name": si.name, "boq_item": items[1].name}, 
                        fields=["tax_invoice_amount", "retention_amount", "advance_deduction", "variance"])
    
    print(f"Item 1 Ledger: {l1}")
    print(f"Item 2 Ledger: {l2}")
    
    success = True
    if not (l1 and flt(l1[0].tax_invoice_amount) == 1000 and flt(l1[0].retention_amount) == 100 and flt(l1[0].advance_deduction) == 200):
        print("FAILURE: Item 1 allocation incorrect.")
        success = False
    
    if not (l2 and flt(l2[0].tax_invoice_amount) == 1500 and flt(l2[0].variance) == 500 and flt(l2[0].advance_deduction) == 400):
        print("FAILURE: Item 2 allocation incorrect.")
        success = False
        
    if success:
        print("SUCCESS: Item-wise allocation and global pro-rating verified.")

if __name__ == "__main__":
    try:
        test_item_wise_allocation()
    finally:
        frappe.db.rollback()

import frappe
from construction_management.overrides.sales_invoice import sync_boq_advance_payments

def fix_advance_pool():
    from erpnext.accounts.utils import update_voucher_outstanding
    
    # Find all submitted advance invoices
    advance_invoices = frappe.get_all("Sales Invoice", filters={
        "custom_is_advanced": 1,
        "docstatus": 1
    }, fields=["name", "debit_to", "customer"])

    print(f"Found {len(advance_invoices)} advance invoices to check.")

    for inv in advance_invoices:
        print(f"Processing {inv.name}...")
        
        # 1. Force update of outstanding and paid_amount in DB
        update_voucher_outstanding("Sales Invoice", inv.name, inv.debit_to, "Customer", inv.customer)
        
        # 2. Reload doc to get updated values
        doc = frappe.get_doc("Sales Invoice", inv.name)
        
        # 3. Calculate effective paid amount (since header field might be 0 due to ERPNext inconsistency)
        effective_paid = flt(doc.base_grand_total) - flt(doc.outstanding_amount)
        if effective_paid > flt(doc.paid_amount):
            print(f"  - Fixing Paid Amount: {doc.paid_amount} -> {effective_paid}")
            doc.paid_amount = effective_paid # Temporary set for sync function
            
        print(f"  - Current Status: {doc.status}, Effective Paid: {effective_paid}")
        
        # 4. Sync to BOQ Advance Pool
        sync_boq_advance_payments(doc)
    
    frappe.db.commit()
    print("Correction completed.")

if __name__ == "__main__":
    fix_advance_pool()

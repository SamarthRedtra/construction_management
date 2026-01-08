
import frappe
from frappe.utils import flt

def execute():
    """
    Recalculate Estimated GP for all BOQ Items to ensure DB fields are consistent.
    """
    print("Starting Estimated GP recalculation...")
    
    items = frappe.get_all("BOQ Item", fields=["name", "total_qty", "rate", "total_estimated_cost"])
    
    count = 0
    for item_data in items:
        # Calculate expected values
        potential_total_amount = flt(item_data.total_qty) * flt(item_data.rate)
        if potential_total_amount:
            estimated_gp = potential_total_amount - flt(item_data.total_estimated_cost)
            estimated_gp_percent = (estimated_gp / potential_total_amount * 100)
        else:
            estimated_gp = 0.0
            estimated_gp_percent = 0.0
            
        # Bulk update via SQL for speed
        frappe.db.sql("""
            UPDATE `tabBOQ Item`
            SET estimated_gp = %s, estimated_gp_percent = %s
            WHERE name = %s
        """, (estimated_gp, estimated_gp_percent, item_data.name))
        
        count += 1
        if count % 100 == 0:
            print(f"Processed {count} items...")
            
    frappe.db.commit()
    print(f"Completed. Updated {count} BOQ Items.")

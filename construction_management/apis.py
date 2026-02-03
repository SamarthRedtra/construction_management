import frappe
import pandas as pd
import io
from frappe.utils.file_manager import save_file



def test():
    print("test")
    process_stock_file("/files/OPENING STOCK - WAREHOUSE WISE (1).xlsx")

@frappe.whitelist()
def process_stock_file(file_url):
    """
    Reads an uploaded Excel file from Frappe, transforms it using Pandas,
    and saves the new format back as a file in Frappe.
    """
    try:
        # 1. Fetch the file content from Frappe
        # We find the file document based on the URL provided
        file_doc = frappe.get_doc("File", {"file_url": file_url})
        file_content = file_doc.get_content()

        # 2. Load into Pandas (using io.BytesIO because content is binary)
        # header=3 matches your requirement to skip first 3 rows
        df = pd.read_excel(io.BytesIO(file_content), header=3)

        # 3. Rename columns to match ERPNext/Frappe naming
        df = df.rename(columns={
            'Code': 'item_code',
            'Name': 'item_name',
            'Units': 'stock_uom',
            'Name.1': 'item_group',
            'Price': 'valuation_rate'
        })

        # 4. Identify Warehouse Columns (Indices 4 to 14)
        warehouse_cols = df.columns[4:15]

        # 5. Remove rows where Item Code is empty
        df_clean = df[df['item_code'].notna()]

        # 6. Unpivot (Melt)
        id_vars = ['item_code', 'item_name', 'stock_uom', 'item_group', 'valuation_rate']
        melted_df = df_clean.melt(id_vars=id_vars, value_vars=warehouse_cols, var_name='warehouse', value_name='qty')

        # 7. Clean up Data
        # Remove empty/zero quantities
        melted_df = melted_df.dropna(subset=['qty'])
        melted_df = melted_df[melted_df['qty'] != 0]

        # Clean Warehouse names (remove newlines and whitespace)
        melted_df['warehouse'] = melted_df['warehouse'].str.replace('\n', '', regex=False).str.strip()

        # Calculate Amount
        melted_df['amount'] = melted_df['qty'] * melted_df['valuation_rate']

        # 8. Final Selection and Renaming
        final_df = melted_df[['item_code', 'item_name', 'item_group', 'warehouse', 'qty', 'stock_uom', 'valuation_rate', 'amount']]
        final_df.columns = ['Item Code', 'Item Name', 'Item Group', 'Warehouse', 'Quantity', 'Stock UOM', 'Valuation Rate', 'Amount']

        # 9. Save output to buffer
        output = io.BytesIO()
        # writing to Excel format
        final_df.to_excel(output, index=False)
        output.seek(0)

        # 10. Save the new file back to Frappe
        new_filename = "Processed_Stock_Upload.xlsx"
        saved_file = save_file(
            fname=new_filename,
            content=output.read(),
            dt="Data Import",  # You can attach this to any DocType
            dn="Data Import",  # Or leave dt/dn None to make it a standalone file
            is_private=1
        )

        return {
            "message": "File processed successfully",
            "new_file_url": saved_file.file_url
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Stock File Process Error")
        return {"error": str(e)}
/**
 * Purchase Invoice client script extensions for Construction Management
 * 
 * Note: The parent-level `bill_no` field in Purchase Invoice is ERPNext's 
 * standard "Supplier Invoice No" (Data type) and is NOT related to BOQ Bill.
 * BOQ dimension fields (bill_no, boq_item) are on the child table (items).
 */

frappe.ui.form.on('Purchase Invoice', {
	onload: function (frm) {
		// Setup cascading dimension filters for child table
		if (typeof construction_management !== 'undefined' && construction_management.dimension_utils) {
			construction_management.dimension_utils.setup_child_table_dimension_filters(frm, 'items');
		}
	},

	refresh: function (frm) {
		// Re-setup on refresh to ensure filters are applied after form loads
		if (typeof construction_management !== 'undefined' && construction_management.dimension_utils) {
			construction_management.dimension_utils.setup_child_table_dimension_filters(frm, 'items');
		}
	}
});

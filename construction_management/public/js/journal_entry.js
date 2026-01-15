/**
 * Journal Entry client script extensions for Construction Management
 * 
 * BOQ dimension fields (bill_no, boq_item) are on the child table (accounts).
 */

frappe.ui.form.on('Journal Entry', {
	onload: function (frm) {
		// Setup cascading dimension filters for child table (accounts, not items)
		if (typeof construction_management !== 'undefined' && construction_management.dimension_utils) {
			construction_management.dimension_utils.setup_child_table_dimension_filters(frm, 'accounts');
		}
	},

	refresh: function (frm) {
		// Re-setup on refresh to ensure filters are applied after form loads
		if (typeof construction_management !== 'undefined' && construction_management.dimension_utils) {
			construction_management.dimension_utils.setup_child_table_dimension_filters(frm, 'accounts');
		}
	}
});

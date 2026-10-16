// Controlled catalog filters and fetch for Stock Reconciliation.

function _controlled_catalog_item_query() {
	return {
		query: "erpnext.controllers.queries.item_query",
		filters: {
			is_stock_item: 1,
			disabled: 0,
			controlled_procurement_catalog: 1,
		},
	};
}

frappe.ui.form.on("Stock Reconciliation", {
	onload(frm) {
		frm.set_query("item_code", "items", _controlled_catalog_item_query);
	},

	refresh(frm) {
		frm.set_query("item_code", "items", _controlled_catalog_item_query);
		const is_adjustment = frm.doc.purpose === "Adjustment Entry";
		if (frm.doc.docstatus >= 1 || is_adjustment) return;
		frm.add_custom_button(__("Fetch Items from Controlled Catalog"), () => {
			frm.events.fetch_controlled_catalog_items(frm);
		});
	},

	fetch_controlled_catalog_items(frm) {
		frappe.prompt(
			[
				{
					label: __("Warehouse"),
					fieldname: "warehouse",
					fieldtype: "Link",
					options: "Warehouse",
					reqd: 1,
					get_query: () => ({ filters: { company: frm.doc.company } }),
				},
				{
					label: __("Item Code"),
					fieldname: "item_code",
					fieldtype: "Link",
					options: "Item",
					get_query: _controlled_catalog_item_query,
				},
				{
					label: __("Ignore Empty Stock"),
					fieldname: "ignore_empty_stock",
					fieldtype: "Check",
				},
			],
			(data) => {
				frappe.call({
					method:
						"construction_management.api.controlled_procurement.get_controlled_catalog_stock_reconciliation_items",
					args: {
						warehouse: data.warehouse,
						posting_date: frm.doc.posting_date,
						posting_time: frm.doc.posting_time,
						company: frm.doc.company,
						item_code: data.item_code,
						ignore_empty_stock: data.ignore_empty_stock,
					},
					freeze: true,
					callback(r) {
						if (r.exc || !r.message || !r.message.length) {
							frappe.msgprint(__("No controlled catalogue stock items found for this warehouse."));
							return;
						}
						frm.clear_table("items");
						r.message.forEach((row) => {
							const item = frm.add_child("items");
							$.extend(item, row);
							item.qty = item.qty || 0;
							item.valuation_rate = item.valuation_rate || 0;
							item.use_serial_batch_fields = cint(
								frappe.user_defaults?.use_serial_batch_fields
							);
						});
						frm.refresh_field("items");
					},
				});
			},
			__("Fetch from Controlled Catalog"),
			__("Update")
		);
	},
});

// Copyright (c) 2024, Construction Management
// License: MIT

frappe.ui.form.on('Purchase Receipt', {
	refresh: function(frm) {
		// Setup button click handler for split button
		setup_split_button(frm);
	},
	
	// When Purchase Order is set at parent level, copy to all existing items
	custom_purchase_order: function(frm) {
		if (frm.doc.custom_purchase_order && frm.doc.items) {
			frm.doc.items.forEach(item => {
				frappe.model.set_value(item.doctype, item.name, 'custom_purchase_order', frm.doc.custom_purchase_order);
			});
			frm.refresh_field('items');
		}
	},
	
	split_item_by_project: function(frm) {
		if (!frm.doc.split_item_by_project) {
			frm.set_value('split_quantity', 0);
		}
	},
	
	split_quantity: function(frm) {
		// Validate split quantity
		if (frm.doc.split_quantity && frm.doc.split_quantity <= 0) {
			frappe.msgprint(__('Split Quantity must be greater than 0'));
			frm.set_value('split_quantity', 0);
			return;
		}
	},
	
	split_button: function(frm) {
		split_selected_items(frm);
	}
});

// ============================================
// Purchase Receipt Item - Child Table Events
// ============================================

frappe.ui.form.on('Purchase Receipt Item', {
	// When a new row is added, copy Purchase Order from parent
	items_add: function(frm, cdt, cdn) {
		let row = frappe.get_doc(cdt, cdn);
		if (frm.doc.custom_purchase_order) {
			frappe.model.set_value(cdt, cdn, 'custom_purchase_order', frm.doc.custom_purchase_order);
		}
	},
	
	// When Item Code is selected, validate it exists in linked Purchase Order
	item_code: function(frm, cdt, cdn) {
		let row = frappe.get_doc(cdt, cdn);
		
		// Only validate if Purchase Order is set at parent level
		if (!frm.doc.custom_purchase_order || !row.item_code) {
			return;
		}
		
		// Check if item exists in the linked Purchase Order
		frappe.call({
			method: 'frappe.client.get_list',
			args: {
				doctype: 'Purchase Order Item',
				filters: {
					'parent': frm.doc.custom_purchase_order,
					'item_code': row.item_code
				},
				fields: ['name', 'item_code', 'qty'],
				limit_page_length: 1
			},
			callback: function(r) {
				if (!r.message || r.message.length === 0) {
					// Item not found in Purchase Order - show error and clear the item
					frappe.msgprint({
						title: __('Item Not in Purchase Order'),
						message: __('Item <b>{0}</b> is not present in Purchase Order <b>{1}</b>. Please select an item from the linked Purchase Order.', 
							[row.item_code, frm.doc.custom_purchase_order]),
						indicator: 'red'
					});
					
					// Clear the item code
					frappe.model.set_value(cdt, cdn, 'item_code', '');
					frappe.model.set_value(cdt, cdn, 'item_name', '');
					frappe.model.set_value(cdt, cdn, 'description', '');
					frappe.model.set_value(cdt, cdn, 'qty', 0);
				}
			}
		});
	},
	
	// When Warehouse (Accepted Warehouse) is selected, fetch linked Project
	warehouse: function(frm, cdt, cdn) {
		fetch_project_from_warehouse(frm, cdt, cdn, 'warehouse');
	},
	
	// Also handle rejected warehouse if needed
	rejected_warehouse: function(frm, cdt, cdn) {
		// Optional: fetch project from rejected warehouse too
	},
	
	// When Project is selected, suggest linked Warehouse
	custom_project: function(frm, cdt, cdn) {
		let row = frappe.get_doc(cdt, cdn);
		// Only auto-fill warehouse if not already set
		if (row.custom_project && !row.warehouse) {
			frappe.call({
				method: 'frappe.client.get_list',
				args: {
					doctype: 'Warehouse',
					filters: { 'custom_project': row.custom_project },
					fields: ['name', 'warehouse_name'],
					limit_page_length: 1
				},
				callback: function(r) {
					if (r.message && r.message.length > 0) {
						frappe.model.set_value(cdt, cdn, 'warehouse', r.message[0].name);
						frappe.show_alert({
							message: __('Warehouse {0} auto-selected based on Project', [r.message[0].warehouse_name || r.message[0].name]),
							indicator: 'blue'
						}, 3);
					}
				}
			});
		}
	}
});

// ============================================
// Helper: Fetch Project from Warehouse
// ============================================

function fetch_project_from_warehouse(frm, cdt, cdn, warehouse_field) {
	let row = frappe.get_doc(cdt, cdn);
	let warehouse = row[warehouse_field];
	
	console.log('fetch_project_from_warehouse called:', {warehouse_field, warehouse, row_name: row.name});
	
	if (!warehouse) {
		// Clear project if warehouse is cleared
		console.log('Clearing custom_project as warehouse is empty');
		frappe.model.set_value(cdt, cdn, 'custom_project', '');
		frappe.model.set_value(cdt, cdn, 'project', '');
		return;
	}
	
	// Use server-side method for more reliable fetching
	console.log('Calling server method to get warehouse project');
	frappe.call({
		method: 'construction_management.api.purchase_receipt_utils.get_warehouse_project',
		args: {
			warehouse: warehouse
	},
	callback: function(r) {
		console.log('Server response:', r);
		if (r.message) {
			console.log('Setting project/custom_project to:', r.message);
			frappe.model.set_value(cdt, cdn, 'custom_project', r.message);
			frappe.model.set_value(cdt, cdn, 'project', r.message);
			frappe.show_alert({
				message: __('Project {0} linked from Warehouse and set on the item', [r.message]),
				indicator: 'green'
			}, 3);
		} else {
			console.log('No project linked to this warehouse');
		}
		},
		error: function(err) {
			console.error('Error fetching warehouse project:', err);
		}
	});
}

function setup_split_button(frm) {
	// The button field will trigger the split_button event
	// This is just for any additional setup if needed
}

function split_selected_items(frm) {
	// Validate inputs
	if (!frm.doc.split_item_by_project) {
		frappe.msgprint(__('Please enable "Enable Item Splitting" first'));
		return;
	}
	
	if (!frm.doc.split_quantity || frm.doc.split_quantity <= 0) {
		frappe.msgprint(__('Please enter a valid Split Quantity'));
		return;
	}
	
	if (!frm.doc.items || frm.doc.items.length === 0) {
		frappe.msgprint(__('No items to split'));
		return;
	}
	
	let split_qty = parseFloat(frm.doc.split_quantity);
	
	// Filter items that can be split (qty >= split_qty)
	let items_to_split = frm.doc.items.filter(item => {
		return item.item_code && item.qty && parseFloat(item.qty) >= split_qty;
	});
	
	if (items_to_split.length === 0) {
		frappe.msgprint({
			message: __('No items found with quantity greater than or equal to {0}', [split_qty]),
			indicator: 'orange',
			title: __('No Items to Split')
		});
		return;
	}
	
	// If only one item can be split, split it directly
	if (items_to_split.length === 1) {
		if (split_single_item(frm, items_to_split[0])) {
			frappe.show_alert({
				message: __('Item split successfully'),
				indicator: 'green'
			}, 5);
		}
		return;
	}
	
	// Show dialog to select items to split
	let dialog = new frappe.ui.Dialog({
		title: __('Select Items to Split'),
		fields: [
			{
				fieldtype: 'HTML',
				options: '<div style="margin-bottom: 10px;"><b>Select items to split (Split Quantity: ' + split_qty + '):</b></div>'
			},
			{
				fieldname: 'items_selection',
				fieldtype: 'HTML',
				options: get_items_selection_html(items_to_split, split_qty)
			}
		],
		primary_action_label: __('Split Selected Items'),
		primary_action: function() {
			let selected_items = [];
			
			// Get checked items
			items_to_split.forEach((item, idx) => {
				let checkbox = dialog.fields_dict.items_selection.$wrapper.find(`input[type="checkbox"][data-item-name="${item.name}"]`);
				if (checkbox.length && checkbox.is(':checked')) {
					selected_items.push(item);
				}
			});
			
			if (selected_items.length === 0) {
				frappe.msgprint(__('Please select at least one item to split'));
				return;
			}
			
			// Split selected items - capture item data before processing to avoid reference issues
			let items_to_process = selected_items.map(item => {
				// Create a copy of the item data we need
				return {
					original_name: item.name,
					item_code: item.item_code,
					qty: parseFloat(item.qty || 0),
					// Copy all other fields we need to preserve
					item_data: Object.assign({}, item)
				};
			});
			
			let success_count = 0;
			let error_count = 0;
			
			items_to_process.forEach((item_info) => {
				// Find the item fresh from the form by original name
				let current_item = frm.doc.items.find(i => i.name === item_info.original_name);
				if (current_item && split_single_item(frm, current_item)) {
					success_count++;
				} else {
					error_count++;
				}
			});
			
			dialog.hide();
			
			if (success_count > 0) {
				frappe.show_alert({
					message: __('{0} item(s) split successfully', [success_count]),
					indicator: 'green'
				}, 5);
			}
			
			if (error_count > 0) {
				frappe.msgprint(__('{0} item(s) could not be split', [error_count]));
			}
		}
	});
	
	dialog.show();
}

function get_items_selection_html(items, split_qty) {
	let html = '<div style="max-height: 400px; overflow-y: auto;">';
	
	items.forEach((item, idx) => {
		let qty = parseFloat(item.qty || 0);
		let num_rows = Math.floor(qty / split_qty);
		let remainder = qty % split_qty;
		let split_info = num_rows + ' row(s) with qty ' + split_qty;
		if (remainder > 0) {
			split_info += ', 1 row with qty ' + remainder;
		}
		
		html += `
			<div style="padding: 8px; border-bottom: 1px solid #e0e0e0;">
				<label style="display: flex; align-items: center; cursor: pointer;">
					<input type="checkbox" data-item-name="${item.name}" checked style="margin-right: 8px;">
					<div>
						<b>${item.item_code || 'No Item Code'}</b> - Qty: ${qty}
						<div style="font-size: 11px; color: #757575; margin-top: 2px;">
							Will create: ${split_info}
						</div>
					</div>
				</label>
			</div>
		`;
	});
	
	html += '</div>';
	return html;
}

function split_single_item(frm, row) {
	// Validate row
	if (!row.item_code) {
		frappe.msgprint(__('Selected item has no Item Code'));
		return false;
	}
	
	if (!row.qty || row.qty <= 0) {
		frappe.msgprint(__('Selected item has invalid quantity'));
		return false;
	}
	
	let total_qty = parseFloat(row.qty);
	let split_qty = parseFloat(frm.doc.split_quantity);
	
	if (split_qty > total_qty) {
		frappe.msgprint(__('Split Quantity cannot be greater than Item Quantity for item: {0}', [row.item_code]));
		return false;
	}
	
	// Calculate number of rows and remainder
	let num_rows = Math.floor(total_qty / split_qty);
	let remainder = total_qty % split_qty;
	
	if (num_rows === 0 && remainder === 0) {
		frappe.msgprint(__('Invalid split quantity'));
		return false;
	}
	
	// Store original row data (all fields except qty and calculated fields)
	let fields_to_exclude = ['qty', 'idx', 'name', 'docstatus', 'received_qty', 'received_stock_qty', 'stock_qty', 'amount', 'base_amount', 'net_amount', 'base_net_amount'];
	let original_row_data = {};
	
	// Copy all fields from original row
	for (let field in row) {
		if (!fields_to_exclude.includes(field) && row[field] !== undefined && row[field] !== null) {
			original_row_data[field] = row[field];
		}
	}
	
	// Get current row index in the items array
	let items = frm.doc.items || [];
	let current_idx = items.findIndex(item => item.name === row.name);
	
	if (current_idx === -1) {
		frappe.msgprint(__('Could not find item row'));
		return false;
	}
	
	// Create new rows with split quantities
	let new_rows = [];
	
	// Create rows with split_qty
	for (let i = 0; i < num_rows; i++) {
		let new_row = frappe.model.add_child(frm.doc, 'Purchase Receipt Item', 'items');
		
		// Copy all original fields
		for (let field in original_row_data) {
			new_row[field] = original_row_data[field];
		}
		
		// Set split quantity
		new_row.qty = split_qty;
		new_rows.push(new_row);
	}
	
	// Create row with remainder if exists
	if (remainder > 0) {
		let new_row = frappe.model.add_child(frm.doc, 'Purchase Receipt Item', 'items');
		
		// Copy all original fields
		for (let field in original_row_data) {
			new_row[field] = original_row_data[field];
		}
		
		// Set remainder quantity
		new_row.qty = remainder;
		new_rows.push(new_row);
	}
	
	// Remove the original row
	frappe.model.clear_doc('Purchase Receipt Item', row.name);
	
	// Refresh the items table
	frm.refresh_field('items');
	
	// Trigger calculations
	if (frm.script_manager && frm.script_manager.trigger('calculate_taxes_and_totals')) {
		// Triggered via script manager
	} else {
		// Mark as dirty to trigger recalculation on save
		frm.dirty();
	}
	
	return true;
}

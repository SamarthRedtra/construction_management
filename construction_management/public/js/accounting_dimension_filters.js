/**
 * Reusable utility for cascading Project → Bill No → BOQ Item filters
 * 
 * These filters work on child table fields (items, accounts, etc.) NOT parent fields.
 * The Purchase Invoice's parent-level `bill_no` is a Data field for supplier invoice number
 * and is unrelated to BOQ Bill.
 * 
 * Usage: 
 *   - Call setup_child_table_dimension_filters(frm, 'items') for tables with items
 *   - Call setup_child_table_dimension_filters(frm, 'accounts') for Journal Entry
 */

frappe.provide("construction_management.dimension_utils");

/**
 * Check if a field exists in a child table's grid
 */
construction_management.dimension_utils.child_field_exists = function (frm, table_fieldname, fieldname) {
	const table_field = frm.fields_dict[table_fieldname];
	if (!table_field || !table_field.grid) return false;
	const meta = frappe.meta.get_docfields(table_field.grid.doctype, frm.docname);
	return meta && meta.some(df => df.fieldname === fieldname);
};

/**
 * Check if a parent-level field exists
 */
construction_management.dimension_utils.field_exists = function (frm, fieldname) {
	return frm.fields_dict && frm.fields_dict[fieldname];
};

/**
 * Setup filters for child table dimension fields
 * Handles cascading: project -> bill_no -> boq_item within child rows
 * 
 * @param {Object} frm - The form object  
 * @param {string} table_fieldname - The child table fieldname (e.g., 'items', 'accounts')
 */
construction_management.dimension_utils.setup_child_table_dimension_filters = function (frm, table_fieldname) {
	const utils = construction_management.dimension_utils;

	// Check if the table field exists
	if (!frm.fields_dict[table_fieldname]) {
		console.log(`[CM Dimensions] Table ${table_fieldname} not found on form`);
		return;
	}

	const grid = frm.fields_dict[table_fieldname].grid;
	if (!grid) {
		console.log(`[CM Dimensions] No grid for table ${table_fieldname}`);
		return;
	}

	// Get child doctype name
	const child_doctype = grid.doctype;

	// Check which BOQ dimension fields exist in the child table
	const has_bill_no = utils.child_field_exists(frm, table_fieldname, "bill_no");
	const has_boq_item = utils.child_field_exists(frm, table_fieldname, "boq_item");

	console.log(`[CM Dimensions] Setting up filters for ${table_fieldname}: bill_no=${has_bill_no}, boq_item=${has_boq_item}`);

	// Set query for bill_no (Link to BOQ Bill) in child table
	if (has_bill_no) {
		try {
			frm.set_query("bill_no", table_fieldname, function (doc, cdt, cdn) {
				const row = locals[cdt][cdn];
				const project = row.project || doc.project;
				if (project) {
					return {
						filters: {
							project: project
						}
					};
				}
				return {};
			});
		} catch (e) {
			console.log(`[CM Dimensions] Error setting bill_no query: ${e.message}`);
		}
	}

	// Set query for boq_item in child table
	if (has_boq_item) {
		try {
			frm.set_query("boq_item", table_fieldname, function (doc, cdt, cdn) {
				const row = locals[cdt][cdn];
				// If bill_no is set, filter by parent_bill
				if (row.bill_no) {
					return {
						filters: {
							parent_bill: row.bill_no
						}
					};
				}
				// Otherwise filter by project
				const project = row.project || doc.project;
				if (project) {
					return {
						filters: {
							project: project
						}
					};
				}
				return {};
			});
		} catch (e) {
			console.log(`[CM Dimensions] Error setting boq_item query: ${e.message}`);
		}
	}

	// Setup child table event handlers for auto-population
	utils.setup_child_table_handlers(frm, table_fieldname, child_doctype);
};

/**
 * Setup event handlers for child table row field changes
 * Enables auto-population when boq_item is selected
 */
construction_management.dimension_utils.setup_child_table_handlers = function (frm, table_fieldname, child_doctype) {
	const utils = construction_management.dimension_utils;

	const has_bill_no = utils.child_field_exists(frm, table_fieldname, "bill_no");
	const has_boq_item = utils.child_field_exists(frm, table_fieldname, "boq_item");

	if (!has_boq_item) return;

	// Only register handlers once per doctype
	const handler_key = `__cm_handlers_${child_doctype}`;
	if (frappe.ui.form.handlers[child_doctype] && frappe.ui.form.handlers[child_doctype][handler_key]) {
		return; // Already registered
	}

	// Auto-populate project and bill_no when boq_item is selected in child row
	frappe.ui.form.on(child_doctype, {
		boq_item: function (frm, cdt, cdn) {
			const row = locals[cdt][cdn];
			if (!row.boq_item) return;

			// Only populate if not already set
			if ((has_bill_no && !row.bill_no) || !row.project) {
				frappe.call({
					method: "frappe.client.get_value",
					args: {
						doctype: "BOQ Item",
						filters: { name: row.boq_item },
						fieldname: ["project", "parent_bill"]
					},
					async: false,
					callback: function (r) {
						if (r.message) {
							let changed = false;
							if (!row.project && r.message.project) {
								frappe.model.set_value(cdt, cdn, "project", r.message.project);
								changed = true;
							}
							if (has_bill_no && !row.bill_no && r.message.parent_bill) {
								frappe.model.set_value(cdt, cdn, "bill_no", r.message.parent_bill);
								changed = true;
							}
						}
					}
				});
			}
		},
		bill_no: function (frm, cdt, cdn) {
			const row = locals[cdt][cdn];
			if (!row.bill_no) return;

			// Auto-populate project from bill_no if not set
			if (!row.project) {
				frappe.call({
					method: "frappe.client.get_value",
					args: {
						doctype: "BOQ Bill",
						filters: { name: row.bill_no },
						fieldname: ["project"]
					},
					async: false,
					callback: function (r) {
						if (r.message && r.message.project) {
							frappe.model.set_value(cdt, cdn, "project", r.message.project);
						}
					}
				});
			}

			// Clear boq_item if bill_no changes and boq_item doesn't belong to new bill
			if (has_boq_item && row.boq_item && row.bill_no) {
				frappe.call({
					method: "frappe.client.get_value",
					args: {
						doctype: "BOQ Item",
						filters: { name: row.boq_item },
						fieldname: ["parent_bill"]
					},
					async: false,
					callback: function (r) {
						if (r.message && r.message.parent_bill !== row.bill_no) {
							frappe.model.set_value(cdt, cdn, "boq_item", "");
						}
					}
				});
			}
		}
	});

	// Mark handlers as registered
	if (!frappe.ui.form.handlers[child_doctype]) {
		frappe.ui.form.handlers[child_doctype] = {};
	}
	frappe.ui.form.handlers[child_doctype][handler_key] = true;
};

/**
 * Legacy function - kept for backward compatibility
 * For parent-level fields (rare use case)
 */
construction_management.dimension_utils.setup_accounting_dimension_filters = function (frm) {
	// This is a no-op for most doctypes since BOQ fields are on child tables
	// Can be extended for doctypes that have parent-level BOQ fields
	console.log(`[CM Dimensions] setup_accounting_dimension_filters called for ${frm.doctype}`);
};

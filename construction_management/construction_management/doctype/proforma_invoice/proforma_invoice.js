// Proforma Invoice client script: revision action before PC/Tax exists
frappe.ui.form.on('Proforma Invoice', {
	refresh(frm) {
		// Show Revise button only when submitted and not converted to PC/Tax
		if (
			frm.doc.docstatus === 1 &&
			!frm.doc.payment_certificate &&
			!frm.doc.tax_invoice
		) {
			frm.add_custom_button(__('Revise Proforma'), () => {
				show_revise_dialog(frm);
			}, __('Actions'));
		}

		// Hide Cancel option (not allowed)
		if (frm.doc.docstatus === 1) {
			$(frm.page.wrapper)
				.find('button[data-label="Cancel"], button[data-original-title="Cancel"]')
				.hide();
		}
	}
});

function show_revise_dialog(frm) {
	// Prepare rows with existing qty
	const itemRows = (frm.doc.items || []).map((row) => {
		return {
			boq_item: row.boq_item,
			description: row.description || row.boq_item,
			qty: row.qty,
			rate: row.rate
		};
	});

	if (!itemRows.length) {
		frappe.msgprint(__('No items to revise.'));
		return;
	}

	const fields = [{
		fieldname: 'items',
		fieldtype: 'Table',
		label: __('Items'),
		in_place_edit: true,
		reqd: 1,
		fields: [
			{
				fieldtype: 'Data',
				fieldname: 'boq_item',
				label: __('BOQ Item'),
				in_list_view: 1,
                read_only: true
			},
			{
				fieldtype: 'Data',
				fieldname: 'description',
				label: __('Description'),
				in_list_view: 1,
				width: '40%',
                read_only: true
			},
			{
				fieldtype: 'Float',
				fieldname: 'qty',
				label: __('Qty'),
				in_list_view: 1
			},
			{
				fieldtype: 'Currency',
				fieldname: 'rate',
				label: __('Rate'),
				in_list_view: 1
			}
		],
		data: itemRows
	}];

	const d = new frappe.ui.Dialog({
		title: __('Revise Proforma'),
		fields: fields,
		primary_action_label: __('Submit Revision'),
		// Allow inline grid editing even for submitted parent
		static: false,
		primary_action(values) {
			const revised = values.items || [];
			if (!revised.length) {
				frappe.msgprint(__('Please provide revised quantities.'));
				return;
			}

			const payload = revised
				.filter(r => r.boq_item)
				.map(r => ({ boq_item: r.boq_item, qty: r.qty, rate: r.rate }));

			if (!payload.length) {
				frappe.msgprint(__('No BOQ items found in revision.'));
				return;
			}

			frappe.call({
				method: 'construction_management.construction_management.doctype.proforma_invoice.proforma_invoice.revise_proforma_invoice',
				args: {
					proforma_name: frm.doc.name,
					items: payload
				},
				freeze: true,
				freeze_message: __('Revising Proforma and updating BOQ Ledger...'),
				callback: (r) => {
					if (r.message && r.message.status === 'success') {
						frappe.show_alert({ message: __('Proforma revised'), indicator: 'green' });
						d.hide();
						frm.reload_doc();
					} else {
						frappe.msgprint(r.message?.error_message || __('Revision failed'));
					}
				}
			});
		}
	});

	d.show();
}


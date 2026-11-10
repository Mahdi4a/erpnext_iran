// A lease that is submitted can be ended early; nothing already invoiced changes.
frappe.ui.form.on('Mall Lease', {
	refresh(frm) {
		if (frm.doc.docstatus !== 1 || frm.doc.terminated_on || ['Expired', 'Cancelled'].includes(frm.doc.status)) return;
		frm.add_custom_button(__('Terminate Lease'), () => {
			frappe.prompt(
				[{ fieldname: 'on_date', label: __('Terminated On'), fieldtype: 'Date', default: frappe.datetime.get_today(), reqd: 1 }],
				async (v) => {
					await frappe.xcall('erpnext_iran.mall.terminate_lease', { lease: frm.doc.name, on_date: v.on_date });
					frm.reload_doc();
				},
				__('Terminate Lease'),
				__('Terminate')
			);
		});
	},
});

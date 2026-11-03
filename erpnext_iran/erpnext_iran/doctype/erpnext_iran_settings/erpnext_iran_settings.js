frappe.ui.form.on('ERPNext Iran Settings', {
	refresh(frm) {
		const run = (method, message) => () =>
			frappe.call({ method: `erpnext_iran.naming.${method}` }).then((r) => {
				const changed = r.message || [];
				frappe.msgprint(changed.length ? `${message}: ${changed.join(', ')}` : __('Nothing to change'));
			});
		frm.add_custom_button(__('Add Jalali Series'), run('add_jalali_series', __('Jalali series added to')), __('Document Numbers'));
		frm.add_custom_button(__('Remove Jalali Series'), run('remove_jalali_series', __('Jalali series removed from')), __('Document Numbers'));
	},
});

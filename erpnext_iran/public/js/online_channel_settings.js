frappe.ui.form.on('Online Channel Settings', {
	refresh(frm) {
		frm.add_custom_button(__('Push Items, Prices and Stock Now'), () => {
			frappe.call({
				method: 'erpnext_iran.woocommerce.sync_now',
				freeze: true,
				callback: (r) => {
					const m = r.message || {};
					frappe.msgprint(__('Updated {0}, created {1}, errors {2}', [m.updated || 0, m.created || 0, (m.errors || []).length]) + ((m.errors || []).length ? '<br>' + frappe.utils.escape_html(m.errors[0]) : ''));
				},
			});
		});
	},
});

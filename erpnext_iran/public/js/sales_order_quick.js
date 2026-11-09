// Orders that come by direct message, Telegram or phone: type the mobile number and the customer is found or
// made. The channel is chosen on the form (or by the list's route options).
frappe.ui.form.on('Sales Order', {
	quick_mobile(frm) {
		const mobile = (frm.doc.quick_mobile || '').trim();
		if (!mobile) return;
		frappe.call({
			method: 'erpnext_iran.pos_customer.customer_for_mobile',
			args: { mobile },
			freeze: true,
			callback: (r) => {
				if (!r.message) return;
				frm.set_value('customer', r.message.customer);
				frappe.show_alert({
					message: r.message.created ? __('New customer {0}', [r.message.customer]) : __('Customer {0}', [r.message.customer]),
					indicator: 'green',
				});
			},
		});
	},
});

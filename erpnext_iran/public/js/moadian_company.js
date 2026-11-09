frappe.ui.form.on("Company", {
	moadian_test_connection(frm) {
		frappe.call({
			method: "erpnext_iran.moadian.test_connection",
			args: { company: frm.doc.name },
			freeze: true,
			freeze_message: __("Contacting the tax authority"),
			callback: ({ message }) => {
				frappe.show_alert({ message: __("Connected. Server key {0}", [message]), indicator: "green" });
			},
		});
	},
});

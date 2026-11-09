frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		if (frm.doc.docstatus === 2 && frm.doc.moadian_status === "Accepted" && !frm.doc.moadian_cancel_tax_id) {
			frm.add_custom_button(__("Cancel in Moadian"), () => call_moadian(frm, "cancel_in_moadian"), __("Moadian"));
		}
		if (frm.doc.docstatus !== 1) return;
		const status = frm.doc.moadian_status;
		if (status === "Not Sent" || status === "Rejected") {
			frm.add_custom_button(__("Send to Moadian"), () => call_moadian(frm, "send_invoice"), __("Moadian"));
		} else if (status === "Sent") {
			frm.add_custom_button(__("Check Moadian Status"), () => call_moadian(frm, "check_status"), __("Moadian"));
		}
	},
});

function call_moadian(frm, method) {
	frappe.call({
		method: `erpnext_iran.moadian_send.${method}`,
		args: { invoice_name: frm.doc.name },
		freeze: true,
		callback: () => frm.reload_doc(),
	});
}

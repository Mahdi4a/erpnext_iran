const MOADIAN_STATUS = {
	"Not Sent": { color: "gray", text: __("Not sent to Moadian yet") },
	Sent: { color: "orange", text: __("Sent to Moadian, waiting for the answer") },
	Accepted: { color: "green", text: __("Accepted by Moadian") },
	Rejected: { color: "red", text: __("Rejected by Moadian") },
};

let moadian_layout = null;

frappe.ui.form.on("Sales Invoice", {
	async refresh(frm) {
		if (!frm.doc.moadian_enabled) return;
		moadian_layout = moadian_layout || (await frappe.xcall("erpnext_iran.moadian.pattern_layout"));
		await set_default_pattern(frm);
		show_pattern_fields(frm);
		show_moadian_banner(frm);
		add_moadian_buttons(frm);
	},
	company(frm) {
		if (frm.is_new() && frm.doc.moadian_enabled) set_default_pattern(frm);
	},
	moadian_pattern(frm) {
		if (moadian_layout) show_pattern_fields(frm);
	},
});

async function set_default_pattern(frm) {
	if (!frm.is_new() || frm.doc.moadian_pattern || !frm.doc.company) return;
	const { message } = await frappe.db.get_value("Company", frm.doc.company, "moadian_default_pattern");
	if (message && message.moadian_default_pattern) {
		await frm.set_value("moadian_pattern", message.moadian_default_pattern);
	}
}

function show_pattern_fields(frm) {
	const layout = moadian_layout[(frm.doc.moadian_pattern || "").split(" ")[0]] || { header: [], item: [] };
	const all = Object.values(moadian_layout);
	const every = (kind) => [...new Set(all.flatMap((pattern) => pattern[kind]))];
	every("header").forEach((code) => frm.toggle_display(`moadian_${code}`, layout.header.includes(code)));
	const grid = frm.fields_dict.items.grid;
	every("item").forEach((code) => grid.update_docfield_property(`moadian_${code}`, "hidden", !layout.item.includes(code)));
	grid.refresh();
	frm.toggle_display("moadian_moadian_errors_section", layout.header.length > 0);
}

function show_moadian_banner(frm) {
	if (frm.doc.docstatus === 0) return;
	const status = MOADIAN_STATUS[frm.doc.moadian_status] || MOADIAN_STATUS["Not Sent"];
	const detail = frm.doc.moadian_tax_id ? ` &middot; ${__("Tax ID")}: <b>${frm.doc.moadian_tax_id}</b>` : "";
	const errors = frm.doc.moadian_errors ? `<br><small>${frappe.utils.escape_html(frm.doc.moadian_errors)}</small>` : "";
	frm.dashboard.set_headline_alert(`<b>${status.text}</b>${detail}${errors}`, status.color);
}

function add_moadian_buttons(frm) {
	const status = frm.doc.moadian_status;
	if (frm.doc.docstatus === 2 && status === "Accepted" && !frm.doc.moadian_cancel_tax_id) {
		frm.add_custom_button(__("Cancel in Moadian"), () => call_moadian(frm, "cancel_in_moadian"), __("Moadian"));
	}
	if (frm.doc.docstatus !== 1) return;
	if (status === "Not Sent" || status === "Rejected") {
		frm.add_custom_button(__("Send to Moadian"), () => call_moadian(frm, "send_invoice"), __("Moadian"));
	} else if (status === "Sent") {
		frm.add_custom_button(__("Check Moadian Status"), () => call_moadian(frm, "check_status"), __("Moadian"));
	}
}

function call_moadian(frm, method) {
	frappe.call({
		method: `erpnext_iran.moadian_send.${method}`,
		args: { invoice_name: frm.doc.name },
		freeze: true,
		callback: () => frm.reload_doc(),
	});
}

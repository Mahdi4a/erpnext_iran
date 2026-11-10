frappe.query_reports["Mall Arrears"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company"), reqd: 1 },
		{ fieldname: "as_on", label: __("As On"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "tenant", label: __("Tenant"), fieldtype: "Link", options: "Customer" },
	],
};

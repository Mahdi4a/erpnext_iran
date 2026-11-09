frappe.query_reports["Prescription Register"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company"), reqd: 1 },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.month_start(), reqd: 1 },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "controlled_only", label: __("Controlled Drugs Only"), fieldtype: "Check", default: 0 },
		{ fieldname: "prescriber", label: __("Prescriber"), fieldtype: "Data" },
	],
};

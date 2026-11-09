frappe.query_reports["Holding Summary"] = {
	filters: [
		{ fieldname: "company", label: __("Company or Group"), fieldtype: "Link", options: "Company", description: __("A group company brings in all the companies below it. Empty: every company.") },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.month_start(), reqd: 1 },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
	],
};

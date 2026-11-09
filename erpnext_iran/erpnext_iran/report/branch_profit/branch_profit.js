frappe.query_reports["Branch Profit"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company"), reqd: 1 },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.month_start(), reqd: 1 },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "branch", label: __("Branch"), fieldtype: "Link", options: "Store Branch" },
		{ fieldname: "group_by", label: __("Group By"), fieldtype: "Select", options: "Branch\nBranch and Day\nBranch and Item Group", default: "Branch" },
	],
};

frappe.query_reports["Rent Roll"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company"), reqd: 1 },
		{ fieldname: "floor", label: __("Floor"), fieldtype: "Data" },
		{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: "\nVacant\nLeased\nMaintenance" },
		{ fieldname: "ending_within", label: __("Lease Ends Within (days)"), fieldtype: "Int" },
	],
};

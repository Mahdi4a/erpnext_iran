frappe.query_reports["Mall Occupancy"] = {
	filters: [{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company"), reqd: 1 }],
};

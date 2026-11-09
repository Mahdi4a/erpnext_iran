frappe.query_reports["Stock Matrix"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company"), reqd: 1 },
		{ fieldname: "warehouse", label: __("Warehouse"), fieldtype: "Link", options: "Warehouse", get_query: () => ({ filters: { company: frappe.query_report.get_filter_value("company"), is_group: 0 } }) },
		{ fieldname: "style", label: __("Style"), fieldtype: "Link", options: "Item", get_query: () => ({ filters: { has_variants: 1 } }) },
		{ fieldname: "season", label: __("Season"), fieldtype: "Select", options: "\nبهار\nتابستان\nپاییز\nزمستان\nهمه فصل" },
		{ fieldname: "only_in_stock", label: __("Hide Colours With No Stock"), fieldtype: "Check", default: 0 },
	],
};

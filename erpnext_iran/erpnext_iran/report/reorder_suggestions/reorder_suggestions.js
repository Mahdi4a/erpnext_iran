frappe.query_reports["Reorder Suggestions"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company"), reqd: 1 },
		{ fieldname: "warehouse", label: __("Warehouse"), fieldtype: "Link", options: "Warehouse", get_query: () => ({ filters: { company: frappe.query_report.get_filter_value("company"), is_group: 0 } }) },
		{ fieldname: "item_group", label: __("Item Group"), fieldtype: "Link", options: "Item Group" },
		{ fieldname: "sales_days", label: __("Look at Sales of the Last (days)"), fieldtype: "Int", default: 30, reqd: 1 },
		{ fieldname: "lead_days", label: __("Delivery Takes (days)"), fieldtype: "Int", default: 3, reqd: 1 },
		{ fieldname: "safety_days", label: __("Keep a Reserve of (days)"), fieldtype: "Int", default: 2, reqd: 1 },
		{ fieldname: "only_needed", label: __("Only What Needs Ordering"), fieldtype: "Check", default: 1 },
	],
	onload(report) {
		report.page.add_inner_button(__('Make Material Request'), async () => {
			const rows = (frappe.query_report.data || []).filter((row) => row.to_order > 0);
			if (!rows.length) return frappe.msgprint(__('There is nothing to order.'));
			const name = await frappe.xcall('erpnext_iran.erpnext_iran.report.reorder_suggestions.reorder_suggestions.make_material_request', {
				company: frappe.query_report.get_filter_value('company'),
				rows,
				delivery_days: frappe.query_report.get_filter_value('lead_days'),
			});
			frappe.set_route('Form', 'Material Request', name);
		});
	},
};

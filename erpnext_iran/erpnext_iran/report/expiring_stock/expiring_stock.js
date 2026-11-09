frappe.query_reports["Expiring Stock"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company"), reqd: 1 },
		{ fieldname: "warehouse", label: __("Warehouse"), fieldtype: "Link", options: "Warehouse", get_query: () => ({ filters: { company: frappe.query_report.get_filter_value("company"), is_group: 0 } }) },
		{ fieldname: "item_group", label: __("Item Group"), fieldtype: "Link", options: "Item Group" },
		{ fieldname: "days", label: __("Expires Within (days)"), fieldtype: "Int", default: 7 },
		{ fieldname: "show_all", label: __("Show Batches That Are Fine Too"), fieldtype: "Check", default: 0 },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === 'status' && data) {
			const color = { Expired: 'red', 'Expires Soon': 'orange', OK: 'green' }[data.status] || 'gray';
			return `<span class="indicator-pill ${color}">${data.status_label}</span>`;
		}
		return value;
	},
	onload(report) {
		report.page.add_inner_button(__('Write Off Expired Stock'), () => {
			const warehouse = frappe.query_report.get_filter_value('warehouse');
			const company = frappe.query_report.get_filter_value('company');
			if (!warehouse) return frappe.msgprint(__('Choose a warehouse first.'));
			frappe.confirm(__('Make a draft stock issue for all expired stock in {0}?', [warehouse]), async () => {
				const name = await frappe.xcall('erpnext_iran.grocery.write_off_expired', { company, warehouse });
				frappe.set_route('Form', 'Stock Entry', name);
			});
		});
	},
};

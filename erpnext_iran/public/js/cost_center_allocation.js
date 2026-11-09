// "Fill by sales share": the percentages of a shared cost, worked out from what each branch sold.
frappe.ui.form.on('Cost Center Allocation', {
	refresh(frm) {
		if (frm.doc.docstatus !== 0) return;
		frm.add_custom_button(__('Fill by Sales Share'), () => {
			if (!frm.doc.company || !frm.doc.main_cost_center) {
				frappe.msgprint(__('Choose the company and the main cost centre first.'));
				return;
			}
			frappe.prompt(
				[
					{ fieldname: 'from_date', label: __('Sales From'), fieldtype: 'Date', default: frappe.datetime.add_months(frappe.datetime.get_today(), -3), reqd: 1 },
					{ fieldname: 'to_date', label: __('Sales To'), fieldtype: 'Date', default: frappe.datetime.get_today(), reqd: 1 },
				],
				async (values) => {
					const rows = await frappe.xcall('erpnext_iran.allocation.suggest_sales_share', {
						company: frm.doc.company,
						main_cost_center: frm.doc.main_cost_center,
						...values,
					});
					frm.clear_table('allocation_percentages');
					rows.forEach((row) => frm.add_child('allocation_percentages', { cost_center: row.cost_center, percentage: row.percentage }));
					frm.refresh_field('allocation_percentages');
					frappe.show_alert({ message: __('{0} branches filled', [rows.length]), indicator: 'green' });
				},
				__('Share by Sales'),
				__('Fill')
			);
		});
	},
});

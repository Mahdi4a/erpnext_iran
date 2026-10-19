frappe.listview_settings['Fiscal Year'] = Object.assign(frappe.listview_settings['Fiscal Year'] || {}, {
	onload(listview) {
		listview.page.add_inner_button(__('Create Jalali Fiscal Year'), () => {
			const [jy] = iran_base.gregorianToJalali(...new Date().toISOString().slice(0, 10).split('-').map(Number));
			frappe.prompt(
				[
					{
						fieldname: 'jalali_year',
						label: __('Jalali Year'),
						fieldtype: 'Int',
						default: jy,
						reqd: 1,
						description: __('Runs from 1 Farvardin to the end of Esfand'),
					},
					{
						fieldname: 'company',
						label: __('Company'),
						fieldtype: 'Link',
						options: 'Company',
						description: __('Needed when it overlaps an existing Fiscal Year'),
					},
				],
				(values) => {
					frappe.call({
						method: 'erpnext_iran.jalali.create_fiscal_year',
						args: { jalali_year: values.jalali_year, company: values.company },
						callback: (r) => {
							frappe.show_alert({ message: __('Fiscal Year {0} is ready', [r.message]), indicator: 'green' });
							listview.refresh();
						},
					});
				},
				__('Create Jalali Fiscal Year')
			);
		});
	},
});

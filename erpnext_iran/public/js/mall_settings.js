// Invoices of a Jalali month for every lease. Months already invoiced are skipped, so it can be pressed again.
frappe.ui.form.on('Mall Settings', {
	refresh(frm) {
		const jalali = frappe.boot.erpnext_iran && frappe.boot.erpnext_iran.jalali_today;
		frm.add_custom_button(__('Make the Invoices of a Month'), () => {
			frappe.prompt(
				[
					{ fieldname: 'jalali_year', label: __('Year'), fieldtype: 'Int', reqd: 1, default: jalali ? jalali[0] : undefined, description: __('For example 1405') },
					{ fieldname: 'jalali_month', label: __('Month'), fieldtype: 'Int', reqd: 1, default: jalali ? jalali[1] : undefined, description: __('1 Farvardin ... 12 Esfand') },
					{ fieldname: 'kind', label: __('Invoices'), fieldtype: 'Select', options: 'rent\nturnover', default: 'rent', description: __('rent: rent and service charge. turnover: the share of the tenant\'s sales, once the turnover is entered.') },
				],
				async (v) => {
					const out = await frappe.xcall('erpnext_iran.mall.generate_invoices', v);
					frappe.msgprint(__('{0}: {1} made, {2} already done', [frappe.utils.escape_html(out.period), out.made.length, out.skipped]));
				},
				__('Make the Invoices of a Month'),
				__('Make')
			);
		});
	},
});

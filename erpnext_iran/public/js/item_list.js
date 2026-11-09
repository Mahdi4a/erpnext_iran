// The clothing pack on the Item list: make a whole style (every size and colour, with barcodes and the price) in one step,
// and put a season's styles on clearance.
frappe.listview_settings['Item'] = Object.assign(frappe.listview_settings['Item'] || {}, {
	onload(listview) {
		const values = (attribute) => frappe.db.get_list('Item Attribute Value', { filters: { parent: attribute }, fields: ['attribute_value', 'abbr'], order_by: 'idx', limit: 200, parent_doctype: 'Item Attribute' })
			.then((rows) => rows.map((row) => ({ value: row.attribute_value, description: row.abbr })));
		const seasons = '\nبهار\nتابستان\nپاییز\nزمستان\nهمه فصل';

		listview.page.add_inner_button(__('Make Clothing Style'), () => {
			const dialog = new frappe.ui.Dialog({
				title: __('Make Clothing Style'),
				fields: [
					{ fieldname: 'style_code', label: __('Style Code'), fieldtype: 'Data', reqd: 1, description: __('Letters, digits and dashes, for example SHIRT-101') },
					{ fieldname: 'style_name', label: __('Name'), fieldtype: 'Data', reqd: 1 },
					{ fieldname: 'item_group', label: __('Item Group'), fieldtype: 'Link', options: 'Item Group', reqd: 1 },
					{ fieldname: 'season', label: __('Season'), fieldtype: 'Select', options: seasons },
					{ fieldname: 'rate', label: __('Price'), fieldtype: 'Currency', reqd: 1 },
					{ fieldname: 'sizes', label: __('Sizes'), fieldtype: 'MultiSelectPills', reqd: 1, get_data: () => values('Size') },
					{ fieldname: 'colours', label: __('Colours'), fieldtype: 'MultiSelectPills', reqd: 1, get_data: () => values('Colour') },
				],
				primary_action_label: __('Make'),
				async primary_action(v) {
					const names = (pills) => (pills || []).map((p) => (typeof p === 'string' ? p : p.value));
					dialog.hide();
					const result = await frappe.xcall('erpnext_iran.apparel.make_style', { ...v, sizes: names(v.sizes), colours: names(v.colours) });
					frappe.msgprint({ title: __('Style made'), indicator: 'green', message: __('{0}: {1} items with barcodes', [frappe.utils.escape_html(result.template), result.variants.length]) });
					listview.refresh();
				},
			});
			dialog.show();
		});

		listview.page.add_inner_button(__('Season Clearance'), () => {
			frappe.prompt(
				[
					{ fieldname: 'season', label: __('Season'), fieldtype: 'Select', options: seasons, reqd: 1 },
					{ fieldname: 'discount_percent', label: __('Discount (%)'), fieldtype: 'Percent', reqd: 1 },
					{ fieldname: 'valid_from', label: __('From'), fieldtype: 'Date', default: frappe.datetime.get_today(), reqd: 1 },
					{ fieldname: 'valid_upto', label: __('Until'), fieldtype: 'Date', reqd: 1 },
				],
				async (v) => {
					const name = await frappe.xcall('erpnext_iran.apparel.season_clearance', v);
					frappe.set_route('Form', 'Pricing Rule', name);
				},
				__('Season Clearance'),
				__('Make Pricing Rule')
			);
		});
	},
});

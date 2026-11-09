// A drug with no stock: the others with the same generic name, the ones in stock first.
frappe.ui.form.on('Item', {
	refresh(frm) {
		if (frm.is_new() || !frm.doc.generic_name) return;
		frm.add_custom_button(__('Generic Alternatives'), async () => {
			const rows = await frappe.xcall('erpnext_iran.pharmacy.alternatives', { item_code: frm.doc.name });
			if (!rows.length) return frappe.msgprint(__('No other drug has the generic name {0}.', [frappe.utils.escape_html(frm.doc.generic_name)]));
			const body = rows.map((r) => `<tr><td><a href="/desk/item/${encodeURIComponent(r.item_code)}">${frappe.utils.escape_html(r.item_name || r.item_code)}</a></td>
				<td>${frappe.utils.escape_html(r.strength)}</td><td>${frappe.utils.escape_html(r.form)}</td>
				<td style="text-align:end">${format_number(r.stock, null, 0)}</td><td style="text-align:end">${r.price ? format_currency(r.price) : ''}</td></tr>`).join('');
			frappe.msgprint({
				title: __('Generic Alternatives'),
				wide: true,
				message: `<table class="table table-bordered"><thead><tr><th>${__('Item')}</th><th>${__('Strength')}</th><th>${__('Form')}</th><th>${__('In Stock')}</th><th>${__('Price')}</th></tr></thead><tbody>${body}</tbody></table>`,
			});
		}, __('Pharmacy'));
	},
});

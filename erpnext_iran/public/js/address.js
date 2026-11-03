// The cities of the chosen province are offered in the City box of an Iranian address. The box still
// takes any text, because a place may be missing from the list.
frappe.ui.form.on('Address', {
	refresh(frm) {
		erpnext_iran_cities(frm);
	},
	iran_province(frm) {
		erpnext_iran_cities(frm);
	},
});

function erpnext_iran_cities(frm) {
	if (!frm.doc.iran_province) return;
	frappe.call({
		method: 'erpnext_iran.cities.get_cities',
		args: { province: frm.doc.iran_province },
		callback(r) {
			frm.set_df_property('iran_city', 'options', r.message || []);
			frm.refresh_field('iran_city');
		},
	});
}

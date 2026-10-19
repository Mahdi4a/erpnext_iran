const CHEQUE_ACTIONS = {
	'Received:In Hand': ['deposit', 'endorse'],
	'Received:Deposited': ['clear', 'bounce'],
	'Issued:Issued': ['clear', 'bounce'],
};

const CHEQUE_LABELS = {
	deposit: __('Deposit'),
	endorse: __('Endorse to Supplier'),
	clear: __('Mark Cleared'),
	bounce: __('Mark Bounced'),
};

frappe.ui.form.on('Iran Cheque', {
	onload(frm) {
		if (frm.is_new() && !frm.doc.company) {
			frm.set_value('company', frappe.defaults.get_user_default('Company'));
		}
	},
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;
		(CHEQUE_ACTIONS[`${frm.doc.cheque_type}:${frm.doc.status}`] || []).forEach((action) => {
			frm.add_custom_button(CHEQUE_LABELS[action], () => run_cheque_action(frm, action), __('Status'));
		});
	},
	cheque_type(frm) {
		frm.set_value('party_type', frm.doc.cheque_type === 'Issued' ? 'Supplier' : 'Customer');
	},
});

function run_cheque_action(frm, action) {
	const fields = [{ fieldname: 'posting_date', label: __('Date'), fieldtype: 'Date', default: frappe.datetime.get_today(), reqd: 1 }];
	if (action === 'clear') {
		fields.push({
			fieldname: 'bank_account',
			label: __('Bank Account'),
			fieldtype: 'Link',
			options: 'Bank Account',
			default: frm.doc.bank_account,
			reqd: 1,
			get_query: () => ({ filters: { is_company_account: 1, company: frm.doc.company } }),
		});
	}
	if (action === 'endorse') {
		fields.push({ fieldname: 'endorsed_to', label: __('Supplier'), fieldtype: 'Link', options: 'Supplier', reqd: 1 });
	}
	frappe.prompt(
		fields,
		(values) => {
			frappe.call({
				method: 'erpnext_iran.erpnext_iran.doctype.iran_cheque.iran_cheque.make_action',
				args: { name: frm.doc.name, action, ...values },
				freeze: true,
				callback: () => frm.reload_doc(),
			});
		},
		CHEQUE_LABELS[action]
	);
}

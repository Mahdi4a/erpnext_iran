// Keys for a till with a line at it. The stock POS wants a click for almost every step.
//   F9     go to payment               F2 / F3 / F4   pay the whole amount with the 1st / 2nd / 3rd payment mode
//   Enter  complete a paid sale        F8             start a new invoice (an unfinished one stays as a draft)
//   F7     search a customer by name or phone
// A sale is also submitted without the "Permanently Submit?" question when the POS Profile says so.
(function () {
	const pos = () => window.cur_pos;
	const visible = ($el) => $el && $el.length && $el.is(':visible');
	const onPosPage = () => pos() && visible($('.point-of-sale-app'));
	const onPayment = () => onPosPage() && visible(pos().payment && pos().payment.$component);
	const onItems = () => onPosPage() && visible(pos().item_selector && pos().item_selector.$component);

	function total() {
		const doc = pos().frm.doc;
		return cint(frappe.sys_defaults.disable_rounded_total) ? doc.grand_total : doc.rounded_total || doc.grand_total;
	}

	function payAllWith(index) {
		const payment = pos().payment;
		const modes = pos().frm.doc.payments.map((row) => row.mode_of_payment);
		const mode = modes[index];
		if (!mode) return;
		modes.forEach((name) => {
			const control = payment[`${payment.sanitize_mode_of_payment(name)}_control`];
			if (control) control.set_value(name === mode ? total() : 0);
		});
		payment.selected_mode = payment[`${payment.sanitize_mode_of_payment(mode)}_control`];
		payment.highlight_selected_mode();
	}

	function complete() {
		const doc = pos().frm.doc;
		if (!doc.items.length || total() - doc.paid_amount > 0) {
			frappe.show_alert({ message: __('The paid amount is less than the total.'), indicator: 'orange' });
			frappe.utils.play_sound('error');
			return;
		}
		pos().payment.$component.find('.submit-order-btn').click();
	}

	const keys = {
		F9: () => onItems() && pos().cart.$component.find('.checkout-btn').first().click(),
		F2: () => onPayment() && payAllWith(0),
		F3: () => onPayment() && payAllWith(1),
		F4: () => onPayment() && payAllWith(2),
		F8: () => onPosPage() && pos().page.btn_primary.click(),
		F7: () => onItems() && pos().cart.customer_field.set_focus(),
		Enter: () => onPayment() && complete(),
	};

	document.addEventListener(
		'keydown',
		(event) => {
			const action = keys[event.key];
			if (!action || event.ctrlKey || event.altKey || event.metaKey || !onPosPage()) return;
			// Enter inside a text box belongs to that box, except in the amount boxes of the payment screen
			if (event.key === 'Enter' && $(event.target).is('textarea, [data-fieldname="remark"] input')) return;
			if (event.key === 'Enter' && !onPayment()) return;
			event.preventDefault();
			action();
		},
		true
	);

	// Skip "Permanently Submit?" on the payment screen when the profile allows it
	const confirm = frappe.confirm;
	frappe.confirm = function (message, ifyes, ifno) {
		const skip = onPayment() && pos().settings.skip_submit_confirmation && /Submit|ثبت/.test(String(message));
		if (skip && typeof ifyes === 'function') return ifyes();
		return confirm.apply(this, arguments);
	};

	window.erpnext_iran = Object.assign(window.erpnext_iran || {}, { posKeys: Object.keys(keys) });
})();

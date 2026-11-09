// Keys for a till with a line at it. The stock POS wants a click for almost every step.
//   F9     go to payment               F2 / F3 / F4   pay the whole amount with the 1st / 2nd / 3rd payment mode
//   Enter  complete a paid sale, and then start the next one          F8   new invoice (an unfinished one stays a draft)
//   F7     search a customer by name or phone
// A sale is also submitted without the "Permanently Submit?" question when the POS Profile says so.
(function () {
	const pos = () => window.cur_pos;
	const visible = ($el) => $el && $el.length && $el.is(':visible');
	const onPosPage = () => pos() && visible($('.point-of-sale-app'));
	const onPayment = () => onPosPage() && visible(pos().payment && pos().payment.$component);
	const onItems = () => onPosPage() && visible(pos().item_selector && pos().item_selector.$component);

	const onSummary = () =>
		onPosPage() && visible(pos().order_summary && pos().order_summary.$component.find('.new-btn'));

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

	// The customer card hides the search box. F7 removes the card and puts the cursor in the box.
	function changeCustomer() {
		const cart = pos().cart;
		cart.$customer_section.find('.reset-customer-btn').click();
		setTimeout(() => cart.customer_field.set_focus(), 250);
	}

	// A scan with no customer chosen (F7 was pressed and nobody was picked) goes to the walk-in customer
	function installWalkInFallback() {
		const Controller = window.erpnext && erpnext.PointOfSale && erpnext.PointOfSale.Controller;
		if (!Controller) return false;
		if (Controller.prototype._iran_walk_in) return true;
		Controller.prototype._iran_walk_in = true;
		const update = Controller.prototype.on_cart_update;
		Controller.prototype.on_cart_update = async function (args) {
			const fallback = this.settings.customer;
			if (!this.frm.doc.customer && fallback) {
				await this.cart.customer_field.set_value(fallback);
				await new Promise((resolve) => setTimeout(resolve, 600));
			}
			return update.call(this, args);
		};
		return true;
	}
	const walkInTimer = setInterval(() => installWalkInFallback() && clearInterval(walkInTimer), 1000);

	let completing = 0;

	function complete() {
		const doc = pos().frm.doc;
		if (Date.now() - completing < 4000) return;
		if (!doc.items.length || total() - doc.paid_amount > 0) {
			frappe.show_alert({ message: __('The paid amount is less than the total.'), indicator: 'orange' });
			frappe.utils.play_sound('error');
			return;
		}
		completing = Date.now();
		pos().payment.$component.find('.submit-order-btn').click();
	}

	const keys = {
		F9: () => onItems() && pos().cart.$component.find('.checkout-btn').first().click(),
		F2: () => onPayment() && payAllWith(0),
		F3: () => onPayment() && payAllWith(1),
		F4: () => onPayment() && payAllWith(2),
		F8: () => onPosPage() && pos().page.btn_primary.click(),
		F7: () => onItems() && changeCustomer(),
		Enter: () => (onPayment() ? complete() : onSummary() && pos().order_summary.$component.find('.new-btn').click()),
	};

	document.addEventListener(
		'keydown',
		(event) => {
			const action = keys[event.key];
			if (!action || event.ctrlKey || event.altKey || event.metaKey || !onPosPage()) return;
			// Enter inside a text box belongs to that box, except in the amount boxes of the payment screen
			if (event.key === 'Enter' && $(event.target).is('textarea, [data-fieldname="remark"] input')) return;
			if (event.key === 'Enter' && (!(onPayment() || onSummary()) || $('.modal.show').length)) return;
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

	// A strip that always shows the keys, so a new cashier does not have to remember them
	function showLegend() {
		if (!onPosPage()) return;
		const modes = pos().frm.doc.payments.map((row) => row.mode_of_payment);
		const items = [
			['F9', __('Checkout')],
			...modes.slice(0, 3).map((mode, index) => [`F${index + 2}`, mode]),
			['Enter', __('Complete Order') + ' / ' + __('New Order')],
			['F8', __('New Invoice')],
			['F7', __('Customer')],
		];
		const html = items.map(([key, label]) => `<span><kbd>${key}</kbd> ${frappe.utils.escape_html(label)}</span>`).join('');
		let $bar = $('.iran-pos-keys');
		if (!$bar.length) {
			$bar = $('<div class="iran-pos-keys"></div>').insertAfter('.point-of-sale-app');
			$('<style>.iran-pos-keys{display:flex;flex-wrap:wrap;gap:6px 18px;padding:8px 4px;font-size:12px;color:var(--text-muted)}.iran-pos-keys kbd{font-weight:600}</style>').appendTo('head');
		}
		if ($bar.html() !== html) $bar.html(html);
	}
	setInterval(showLegend, 1500);

	window.erpnext_iran = Object.assign(window.erpnext_iran || {}, { posKeys: Object.keys(keys) });
})();

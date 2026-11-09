// Keys for a till with a line at it. The stock POS wants a click for almost every step.
//   F9     go to payment               F2 / F3 / F4   pay the whole amount with the 1st / 2nd / 3rd payment mode
//   Enter  complete a paid sale, and then start the next one          F8   new invoice (an unfinished one stays a draft)
//   F7     search a customer by name or phone
// The customer is asked for last: the payment screen opens with a mobile number box that has the cursor.
//   11 digits  find the customer (or make one) and show the club points     Enter  done with the box, Enter again completes
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

	// A scan on the payment screen (the customer remembered one more thing) goes back to the items and adds it.
	// onScan only listens on the items screen; it announces every scan as a 'scan' event on the document.
	document.addEventListener('scan', async (event) => {
		if (!onPayment()) return;
		const code = event.detail && event.detail.scanCode;
		if (!code) return;
		$('.iran-pos-phone').val('').data('done', ''); // the digits of the scan went into the mobile box if it had the cursor
		pos().payment.edit_cart();
		const deadline = Date.now() + 3000;
		while (Date.now() < deadline && !onItems()) await new Promise((resolve) => setTimeout(resolve, 50));
		await new Promise((resolve) => setTimeout(resolve, 150)); // the items screen finishes its own set-up
		if (window.onScan && onItems()) onScan.simulate(document, code);
	});

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

	// ---- the mobile number box on the payment screen ----
	const digits = (value) =>
		String(value || '')
			.replace(/[۰-۹]/g, (d) => '۰۱۲۳۴۵۶۷۸۹'.indexOf(d))
			.replace(/[٠-٩]/g, (d) => '٠١٢٣٤٥٦٧٨٩'.indexOf(d))
			.trim();
	const isMobile = (value) => /^(\+?98|0098|0)?9\d{9}$/.test(digits(value).replace(/[\s-]/g, ''));

	async function useMobile($box, $note) {
		const mobile = digits($box.val());
		$note.css('color', '').text(__('Looking up…'));
		try {
			const result = await frappe.xcall('erpnext_iran.pos_customer.customer_for_mobile', { mobile });
			await pos().cart.customer_field.set_value(result.customer);
			const deadline = Date.now() + 3000;
			while (Date.now() < deadline && !(pos().customer_details && pos().customer_details.customer === result.customer)) {
				await new Promise((resolve) => setTimeout(resolve, 50));
			}
			$box.data('done', result.customer);
			$note
				.css('color', 'var(--green-600, #278f5e)')
				.text(result.created ? __('New customer {0}', [result.customer]) : __('Customer {0}', [result.customer]));
		} catch (error) {
			$box.data('done', '');
			$note.css('color', 'var(--red-500, #e24c4c)').text(__('Mobile number not accepted'));
		}
	}

	function addMobileBox(payment) {
		const $left = payment.$component.find('.payment-container-left');
		$left.find('.iran-pos-phone-wrap').remove();
		const $wrap = $(`<div class="iran-pos-phone-wrap" style="margin: 0 0 12px">
			<input type="text" inputmode="numeric" autocomplete="off" class="form-control iran-pos-phone"
				style="font-size: 18px; direction: ltr; text-align: center"
				placeholder="${__('Customer mobile number')} (09…)">
			<div class="iran-pos-phone-note small text-muted" style="margin-top: 4px; min-height: 18px">
				${__('Enter with no number keeps the walk-in customer')}
			</div>
		</div>`);
		$left.find('.payment-section').first().after($wrap);
		const $box = $wrap.find('input');
		const $note = $wrap.find('.iran-pos-phone-note');
		let running = Promise.resolve();

		$box.on('input', () => {
			$box.data('done', '');
			if (isMobile($box.val())) {
				running = useMobile($box, $note);
				window.erpnext_iran = Object.assign(window.erpnext_iran || {}, { mobileLookup: running });
			}
		});
		$box.on('keydown', async (event) => {
			// the stock POS types every key into the selected payment amount; this box keeps its keys
			event.stopPropagation();
			if (event.key !== 'Enter') return;
			event.preventDefault();
			if (digits($box.val()) && isMobile($box.val()) && !$box.data('done')) await running;
			$box.blur();
		});
		setTimeout(() => $box.trigger('focus'), 150);
	}

	function installMobileBox() {
		const Payment = window.erpnext && erpnext.PointOfSale && erpnext.PointOfSale.Payment;
		if (!Payment) return false;
		if (Payment.prototype._iran_mobile) return true;
		Payment.prototype._iran_mobile = true;
		const checkout = Payment.prototype.checkout;
		Payment.prototype.checkout = function () {
			const result = checkout.apply(this, arguments);
			setTimeout(() => addMobileBox(this), 50);
			return result;
		};
		return true;
	}
	const mobileTimer = setInterval(() => installMobileBox() && clearInterval(mobileTimer), 1000);

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
			// the offline till has its own keys
			if (window.erpnext_iran && erpnext_iran.offlineTillOpen) return;
			// Enter in the mobile number box is handled by the box itself
			if (event.key === 'Enter' && $(event.target).is('.iran-pos-phone')) return;
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

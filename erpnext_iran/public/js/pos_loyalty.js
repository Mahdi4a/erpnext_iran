// Shows the loyalty points of the customer under the name on the POS, where the cashier already looks.
// The stock POS fetches them but only uses them on the payment screen. The walk-in customer has none.
(function () {
	function chip(info) {
		if (!info || info.loyalty_points == null) return '';
		const points = flt(info.loyalty_points);
		const value = points * flt(info.conversion_factor);
		const money = value ? ` ≈ ${format_currency(value)}` : '';
		return `<div class="customer-desc iran-loyalty" style="color: var(--green-600, #278f5e); font-weight: 600">
			${__('Club points')}: ${format_number(points, null, 0)}${money}
		</div>`;
	}

	function patch() {
		const pos = window.erpnext && erpnext.PointOfSale;
		if (!pos || !pos.ItemCart) return false;
		if (pos.ItemCart.prototype._iran_loyalty) return true;
		pos.ItemCart.prototype._iran_loyalty = true;

		const update = pos.ItemCart.prototype.update_customer_section;
		pos.ItemCart.prototype.update_customer_section = function () {
			const result = update.apply(this, arguments);
			this.$customer_section.find('.iran-loyalty').remove();
			const html = chip(this.customer_info);
			if (html) this.$customer_section.find('.customer-name-desc').append(html);
			return result;
		};
		return true;
	}

	// Payment screen: the stock redeem card hides its limit and ignores the numpad, so it was
	// unusable in a queue. Show the points on the card and redeem the most that fits in one tap.
	// The most that may be redeemed on this invoice: the points' worth, capped by the Settings percentage.
	function allowed_amount(doc, points, factor) {
		const percent = flt(((frappe.boot.erpnext_iran || {}).loyalty_max_percent)) || 100;
		const due = flt(doc.rounded_total || doc.grand_total);
		const cap = percent < 100 ? (due * percent) / 100 : due;
		return Math.floor(Math.min(flt(points) * factor, cap, due) / factor) * factor;
	}

	function redeem_all(payment) {
		const frm = payment.events.get_frm();
		const doc = frm.doc;
		const { loyalty_points, conversion_factor } = payment.events.get_customer_details();
		const factor = flt(conversion_factor);
		const control = payment['loyalty-amount_control'];
		if (!control || !flt(loyalty_points) || !factor) return;
		const whole = allowed_amount(doc, loyalty_points, factor);
		if (whole <= 0) {
			frappe.show_alert({ message: __('Not enough points to redeem'), indicator: 'orange' });
			return;
		}
		// the cash row follows through rebalance(), which runs whenever the loyalty amount changes
		control.set_value(whole);
	}

	// Whatever changes the loyalty amount (button, numpad, a refused number that resets it to 0),
	// the payment rows must add up to total - loyalty, or the sale is overpaid / left open.
	function rebalance(payment) {
		const doc = payment.events.get_frm().doc;
		const rows = doc.payments || [];
		if (!rows.length) return;
		const due = flt(doc.rounded_total || doc.grand_total);
		const target = Math.max(0, due - flt(doc.loyalty_amount));
		const paid = rows.reduce((sum, row) => sum + flt(row.amount), 0);
		const show = () => rows.forEach((row) => {
			const mode = payment.sanitize_mode_of_payment(row.mode_of_payment);
			payment.$payment_modes.find(`.${mode}-amount`).html(flt(row.amount) > 0 ? format_currency(row.amount, doc.currency) : '');
		});
		if (Math.abs(paid - target) < 0.005) return show();
		let left = target;
		const amounts = rows.map((row) => {
			const keep = Math.max(0, Math.min(flt(row.amount), left));
			left -= keep;
			return keep;
		});
		amounts[0] += left; // a shortfall goes back to the first (default) mode, as the stock POS does
		rows.forEach((row, i) => {
			if (amounts[i] !== flt(row.amount)) frappe.model.set_value(row.doctype, row.name, 'amount', amounts[i]);
		});
		show();
	}

	function patch_payment() {
		const pos = window.erpnext && erpnext.PointOfSale;
		if (!pos || !pos.Payment) return false;
		if (pos.Payment.prototype._iran_loyalty) return true;
		pos.Payment.prototype._iran_loyalty = true;

		// The stock numpad is a calculator: digits enter from the right and the last
		// `currency_precision` digits are decimals, so 5 0 0 0 becomes 50.00. Rials have no
		// decimals, so while a key is handled the precision falls back to the number format's.
		const clicked = pos.Payment.prototype.on_numpad_clicked;
		pos.Payment.prototype.on_numpad_clicked = function () {
			const info = get_number_format_info(frappe.sys_defaults.number_format);
			if (info.precision !== 0) return clicked.apply(this, arguments);
			const saved = frappe.sys_defaults.currency_precision;
			frappe.sys_defaults.currency_precision = 0;
			try {
				return clicked.apply(this, arguments);
			} finally {
				frappe.sys_defaults.currency_precision = saved;
			}
		};

		const changed = pos.Payment.prototype.bind_loyalty_amount_event;
		pos.Payment.prototype.bind_loyalty_amount_event = function () {
			const result = changed.apply(this, arguments);
			setTimeout(() => rebalance(this), 120);
			setTimeout(() => rebalance(this), 450); // the stock handler finishes asynchronously
			return result;
		};

		const render = pos.Payment.prototype.render_loyalty_points_payment_mode;
		pos.Payment.prototype.render_loyalty_points_payment_mode = function () {
			// The stock control rejects any number above "points x factor"; hand it the capped points.
			const events = this.events;
			const real = events.get_customer_details;
			const doc = events.get_frm().doc;
			events.get_customer_details = () => {
				const d = real.call(events) || {};
				if (!d.loyalty_points || !flt(d.conversion_factor)) return d;
				const points = allowed_amount(doc, d.loyalty_points, flt(d.conversion_factor)) / flt(d.conversion_factor);
				return Object.assign({}, d, { loyalty_points: points });
			};
			let result;
			try {
				result = render.apply(this, arguments);
			} finally {
				events.get_customer_details = real;
			}
			const info = real.call(events) || {};
			const card = this.$payment_modes.find('.loyalty-card');
			card.find('.iran-loyalty-line').remove();
			if (!card.length || !flt(info.loyalty_points)) return result;
			const worth = flt(info.loyalty_points) * flt(info.conversion_factor);
			const percent = flt((frappe.boot.erpnext_iran || {}).loyalty_max_percent) || 100;
			const limit = percent < 100 ? ` · ${__('max')} ${format_number(percent, null, 0)}%` : '';
			const line = $(`<div class="iran-loyalty-line" style="margin-top:4px">
				<span style="color: var(--green-600, #278f5e); font-weight: 600">
					${__('Club points')}: ${format_number(info.loyalty_points, null, 0)} ≈ ${format_currency(worth)}${limit}
				</span>
				<button type="button" class="btn btn-xs btn-default iran-redeem-all" style="margin-inline-start:8px">
					${__('Use points')} (F6)
				</button>
			</div>`);
			line.find('button').on('click', (e) => {
				e.stopPropagation();
				redeem_all(this);
			});
			card.append(line);
			return result;
		};

		document.addEventListener('keydown', (e) => {
			if (e.key !== 'F6') return;
			const payment = window.cur_pos && cur_pos.payment;
			if (!payment || !payment.$component || !payment.$component.is(':visible')) return;
			e.preventDefault();
			redeem_all(payment);
		});
		return true;
	}

	const timer = setInterval(() => {
		const a = patch();
		const b = patch_payment();
		if (a && b) clearInterval(timer);
	}, 1000);
})();

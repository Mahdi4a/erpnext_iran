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
	function redeem_all(payment) {
		const frm = payment.events.get_frm();
		const doc = frm.doc;
		const { loyalty_points, conversion_factor } = payment.events.get_customer_details();
		const factor = flt(conversion_factor);
		const control = payment['loyalty-amount_control'];
		if (!control || !flt(loyalty_points) || !factor) return;
		const due = flt(doc.rounded_total || doc.grand_total);
		const whole = Math.floor(Math.min(flt(loyalty_points) * factor, due) / factor) * factor;
		if (whole <= 0) {
			frappe.show_alert({ message: __('Not enough points to redeem'), indicator: 'orange' });
			return;
		}
		control.set_value(whole);
		// ERPNext reduces what is left to pay; make the first cash row match so nothing is overpaid.
		setTimeout(() => {
			const rows = doc.payments || [];
			let left = due - whole;
			rows.forEach((row) => {
				const keep = Math.max(0, Math.min(flt(row.amount), left));
				if (keep !== flt(row.amount)) frappe.model.set_value(row.doctype, row.name, 'amount', keep);
				// the tile keeps its old number unless it is told
				const mode = payment.sanitize_mode_of_payment(row.mode_of_payment);
				const shown = keep > 0 ? format_currency(keep, doc.currency) : '';
				payment.$payment_modes.find(`.${mode}-amount`).html(shown);
				left -= keep;
			});
		}, 600);
	}

	function patch_payment() {
		const pos = window.erpnext && erpnext.PointOfSale;
		if (!pos || !pos.Payment) return false;
		if (pos.Payment.prototype._iran_loyalty) return true;
		pos.Payment.prototype._iran_loyalty = true;

		const render = pos.Payment.prototype.render_loyalty_points_payment_mode;
		pos.Payment.prototype.render_loyalty_points_payment_mode = function () {
			const result = render.apply(this, arguments);
			const info = this.events.get_customer_details() || {};
			const card = this.$payment_modes.find('.loyalty-card');
			card.find('.iran-loyalty-line').remove();
			if (!card.length || !flt(info.loyalty_points)) return result;
			const worth = flt(info.loyalty_points) * flt(info.conversion_factor);
			const line = $(`<div class="iran-loyalty-line" style="margin-top:4px">
				<span style="color: var(--green-600, #278f5e); font-weight: 600">
					${__('Club points')}: ${format_number(info.loyalty_points, null, 0)} ≈ ${format_currency(worth)}
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

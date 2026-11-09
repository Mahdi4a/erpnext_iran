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

	const timer = setInterval(() => {
		if (patch()) clearInterval(timer);
	}, 1000);
})();

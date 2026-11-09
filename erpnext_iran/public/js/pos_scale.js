// A label from a shop scale (EAN-13 with the weight or price inside) scanned at the POS adds the item with
// that quantity. The scanned code is turned into the barcode registered for the item (see scale.py) and the
// number on the label is kept to set the quantity when the item reaches the cart.
(function () {
	const MAX_AGE = 3000;
	let pending = null;

	const settings = () => (frappe.boot.erpnext_iran || {}).scale;

	function checkDigit(first12) {
		let total = 0;
		for (let i = 0; i < 12; i++) total += Number(first12[i]) * (i % 2 ? 3 : 1);
		return String((10 - (total % 10)) % 10);
	}

	function parse(code) {
		const s = settings();
		if (!s || !/^\d{13}$/.test(code) || !code.startsWith(s.prefix)) return null;
		if (checkDigit(code.slice(0, 12)) !== code[12]) return null;
		const start = s.prefix.length;
		const plu = code.substr(start, s.plu_digits);
		const value = parseInt(code.slice(start + s.plu_digits, 12), 10);
		const body = s.prefix + plu + '0'.repeat(s.value_digits);
		const barcode = body + checkDigit(body);
		if (!(s.items || []).includes(barcode)) return null;
		return { barcode, value };
	}

	function quantity(value, rate) {
		const s = settings();
		const qty = s.mode === 'Price' ? value / flt(rate) : value / s.weight_divisor;
		return Math.round(qty * 1000) / 1000;
	}

	function patch() {
		const pos = window.erpnext && erpnext.PointOfSale;
		if (!pos || !pos.ItemSelector || !pos.Controller) return false;
		if (pos.ItemSelector.prototype._iran_scale) return true;
		pos.ItemSelector.prototype._iran_scale = true;

		const setSearch = pos.ItemSelector.prototype.set_search_value;
		pos.ItemSelector.prototype.set_search_value = function (value) {
			const label = parse(String(value || ''));
			if (label) {
				pending = { value: label.value, at: Date.now() };
				value = label.barcode;
			} else if (value) {
				pending = null;
			}
			return setSearch.call(this, value);
		};

		const update = pos.Controller.prototype.on_cart_update;
		pos.Controller.prototype.on_cart_update = async function (args) {
			const label = pending && Date.now() - pending.at < MAX_AGE ? pending : null;
			if (!label || args.field !== 'qty' || args.value !== '+1') return update.call(this, args);

			pending = null;
			const qty = quantity(label.value, args.item.rate);
			if (!qty) return update.call(this, args);

			const row = this.get_item_from_frm(args.item);
			if ($.isEmptyObject(row)) {
				args.value = qty;
				return update.call(this, args);
			}
			await frappe.model.set_value(row.doctype, row.name, 'qty', flt(row.qty) + qty);
			this.update_cart_html(row);
			return row;
		};
		return true;
	}

	const timer = setInterval(() => {
		if (patch()) clearInterval(timer);
	}, 1000);
	window.erpnext_iran = Object.assign(window.erpnext_iran || {}, { parseScaleLabel: parse });
})();

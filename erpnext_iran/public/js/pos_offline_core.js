// The logic of the offline till that needs no browser: finding an item from a scan, scale labels, the total, the
// sale that is queued. Kept apart from the screen so it can be tested with node (tests/js/).
(function (root) {
	const PERSIAN = '۰۱۲۳۴۵۶۷۸۹';
	const ARABIC = '٠١٢٣٤٥٦٧٨٩';

	function digits(value) {
		return String(value == null ? '' : value)
			.replace(/[۰-۹]/g, (d) => PERSIAN.indexOf(d))
			.replace(/[٠-٩]/g, (d) => ARABIC.indexOf(d));
	}

	// 09XXXXXXXXX from any usual spelling, or null (the same rules as iran_base try_normalize_mobile)
	function normalizeMobile(value) {
		let d = digits(value).replace(/\D/g, '');
		if (d.startsWith('0098')) d = d.slice(4);
		else if (d.startsWith('98') && d.length === 12) d = d.slice(2);
		if (d.length === 10 && d.startsWith('9')) d = '0' + d;
		return d.length === 11 && d.startsWith('09') ? d : null;
	}

	function normalizeText(value) {
		return digits(value).replace(/ي/g, 'ی').replace(/ك/g, 'ک').toLowerCase().trim();
	}

	function checkDigit(first12) {
		let total = 0;
		for (let i = 0; i < 12; i++) total += Number(first12[i]) * (i % 2 ? 3 : 1);
		return String((10 - (total % 10)) % 10);
	}

	// A label from a shop scale as {barcode, value}, or null. Only a label that points to an item registered with a
	// PLU counts; a shop's own labels that also start with the prefix are ordinary barcodes.
	function parseScaleLabel(code, scale) {
		if (!scale || !/^\d{13}$/.test(code) || !code.startsWith(scale.prefix)) return null;
		if (checkDigit(code.slice(0, 12)) !== code[12]) return null;
		const start = scale.prefix.length;
		const plu = code.substr(start, scale.plu_digits);
		const value = parseInt(code.slice(start + scale.plu_digits, 12), 10);
		const body = scale.prefix + plu + '0'.repeat(scale.value_digits);
		const barcode = body + checkDigit(body);
		return (scale.items || []).includes(barcode) ? { barcode, value } : null;
	}

	function labelQuantity(value, rate, scale) {
		const qty = scale.mode === 'Price' ? value / Number(rate) : value / scale.weight_divisor;
		return Number.isFinite(qty) ? Math.round(qty * 1000) / 1000 : 0;
	}

	function buildIndex(items) {
		const byBarcode = new Map();
		const byCode = new Map();
		for (const item of items || []) {
			byCode.set(item.item_code, item);
			for (const barcode of item.barcodes || []) byBarcode.set(String(barcode), item);
		}
		return { items: items || [], byBarcode, byCode };
	}

	// What a scanned or typed code means: {item, qty} (qty is null for an ordinary scan), or null.
	function resolveScan(code, index, scale) {
		code = digits(code).trim();
		if (!code) return null;
		const label = parseScaleLabel(code, scale);
		if (label) {
			const item = index.byBarcode.get(label.barcode);
			if (item) {
				const qty = labelQuantity(label.value, item.rate, scale);
				return qty > 0 ? { item, qty } : null;
			}
		}
		const item = index.byBarcode.get(code) || index.byCode.get(code);
		return item ? { item, qty: null } : null;
	}

	function search(text, index, limit) {
		const needle = normalizeText(text);
		if (!needle) return [];
		const found = [];
		for (const item of index.items) {
			if (normalizeText(item.item_name).includes(needle) || normalizeText(item.item_code).includes(needle)) {
				found.push(item);
				if (found.length >= (limit || 8)) break;
			}
		}
		return found;
	}

	// The cart is a plain array of lines; every change returns a new one.
	function addLine(cart, item, qty) {
		qty = qty == null ? 1 : qty;
		const at = cart.findIndex((line) => line.item_code === item.item_code);
		if (at >= 0) {
			return cart.map((line, i) => (i === at ? { ...line, qty: Math.round((line.qty + qty) * 1000) / 1000 } : line));
		}
		return cart.concat({
			item_code: item.item_code,
			item_name: item.item_name,
			uom: item.uom,
			qty,
			rate: item.rate,
			list_rate: item.rate,
		});
	}

	function setQty(cart, index, qty) {
		qty = Number(qty);
		if (!(qty > 0)) return cart.filter((_line, i) => i !== index);
		return cart.map((line, i) => (i === index ? { ...line, qty: Math.round(qty * 1000) / 1000 } : line));
	}

	// Net, tax and the rounded total. Only "On Net Total" taxes can be worked out here; exact says whether the
	// template had nothing else.
	function totals(cart, taxes) {
		const net = cart.reduce((sum, line) => sum + line.qty * line.rate, 0);
		let tax = 0;
		for (const row of (taxes && taxes.rows) || []) if (!row.included) tax += (net * row.rate) / 100;
		return { net, tax, total: Math.round(net + tax), exact: !taxes || taxes.exact !== false };
	}

	function pad(n) {
		return String(n).padStart(2, '0');
	}

	function formatSoldAt(date) {
		return (
			`${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
			`${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
		);
	}

	// 24 hex digits from a source of randomness (crypto in the browser), grouped for reading
	function makeSaleId(randomBytes) {
		const bytes = randomBytes(12);
		const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
		return `${hex.slice(0, 8)}-${hex.slice(8, 16)}-${hex.slice(16)}`;
	}

	function buildSale({ id, snapshot, cart, mode, customer, mobile, now }) {
		return {
			id,
			pos_profile: snapshot.pos_profile,
			mode,
			customer: customer || '',
			mobile: mobile || '',
			sold_at: formatSoldAt(now),
			offline_total: totals(cart, snapshot.taxes).total,
			items: cart.map((line) => ({
				item_code: line.item_code,
				qty: line.qty,
				rate: line.rate,
				list_rate: line.list_rate,
			})),
		};
	}

	// Who the mobile box means: a known customer, a number that becomes a customer when the sale is sent, or nothing
	function findCustomer(value, customers) {
		const mobile = normalizeMobile(value);
		if (!mobile) return null;
		const known = (customers || []).find((c) => c.mobile === mobile || c.name === mobile);
		return known ? { kind: 'known', mobile, customer: known } : { kind: 'new', mobile };
	}

	function summary(queue) {
		const out = { pending: 0, refused: 0, done: 0 };
		for (const entry of queue) out[entry.status] = (out[entry.status] || 0) + 1;
		return out;
	}

	// Seconds to wait before sending again after n failures: 5, 10, 20 ... at most 2 minutes
	function retryDelay(attempts) {
		return Math.min(120, 5 * 2 ** Math.max(0, attempts - 1));
	}

	const api = {
		digits, normalizeMobile, normalizeText, checkDigit, parseScaleLabel, labelQuantity, buildIndex,
		resolveScan, search, addLine, setQty, totals, formatSoldAt, makeSaleId, buildSale, findCustomer, summary, retryDelay,
	};
	if (typeof module !== 'undefined' && module.exports) module.exports = api;
	else {
		root.erpnext_iran = Object.assign(root.erpnext_iran || {}, { offlineCore: api });
	}
})(typeof window !== 'undefined' ? window : globalThis);

const assert = require('assert');
const core = require('../../public/js/pos_offline_core.js');

const scale = { prefix: '2', plu_digits: 6, value_digits: 5, mode: 'Weight', weight_divisor: 1000, items: ['2000123000008'] };
const apple = { item_code: 'APPLE-1', item_name: 'سیب قرمز', uom: 'Kg', rate: 800000, barcodes: ['2000123000008'] };
const widget = { item_code: 'TST-RET-1', item_name: 'کالای آزمایشی', uom: 'Nos', rate: 100000, barcodes: ['6260000000019'] };
const index = core.buildIndex([apple, widget]);
let n = 0;
const test = (name, fn) => { fn(); n++; };

test('mobile numbers in every spelling', () => {
	for (const v of ['09121234567', '+989121234567', '00989121234567', '9121234567', '۰۹۱۲۱۲۳۴۵۶۷', '0912 123 4567'])
		assert.strictEqual(core.normalizeMobile(v), '09121234567', v);
	for (const v of ['', '0912', '02112345678', '12345678901', null]) assert.strictEqual(core.normalizeMobile(v), null, String(v));
});

test('check digit matches a known EAN-13', () => {
	assert.strictEqual(core.checkDigit('626000000001'), '9');
	assert.strictEqual(core.checkDigit('400638133393'), '1');
});

test('a scale label gives the item and the weight', () => {
	const hit = core.resolveScan('2000123003504', index, scale); // 0.35 kg
	assert.strictEqual(hit.item.item_code, 'APPLE-1');
	assert.strictEqual(hit.qty, 0.35);
	assert.strictEqual(core.resolveScan('2000123012001', index, scale).qty, 1.2);
});

test('a label of the shop that also starts with 2 is not a weight', () => {
	assert.strictEqual(core.parseScaleLabel('2999999999993', scale), null);
	const own = core.buildIndex([{ item_code: 'OWN', item_name: 'own', rate: 5, barcodes: ['2999999999993'] }]);
	const hit = core.resolveScan('2999999999993', own, scale);
	assert.strictEqual(hit.item.item_code, 'OWN');
	assert.strictEqual(hit.qty, null);
});

test('a bad check digit is not a label', () => {
	assert.strictEqual(core.parseScaleLabel('2000123003505', scale), null);
});

test('price mode turns the value into a quantity', () => {
	assert.strictEqual(core.labelQuantity(400000, 800000, { mode: 'Price' }), 0.5);
});

test('ordinary barcode, item code, Persian digits, unknown', () => {
	assert.strictEqual(core.resolveScan('6260000000019', index, scale).item.item_code, 'TST-RET-1');
	assert.strictEqual(core.resolveScan('TST-RET-1', index, scale).item.item_code, 'TST-RET-1');
	assert.strictEqual(core.resolveScan('6260000000019'.replace(/\d/g, (d) => '۰۱۲۳۴۵۶۷۸۹'[d]), index, scale).item.item_code, 'TST-RET-1');
	assert.strictEqual(core.resolveScan('123', index, scale), null);
	assert.strictEqual(core.resolveScan('  ', index, scale), null);
});

test('searching by name ignores Arabic letter variants', () => {
	assert.deepStrictEqual(core.search('سيب', index).map((i) => i.item_code), ['APPLE-1']);
	assert.deepStrictEqual(core.search('tst', index).map((i) => i.item_code), ['TST-RET-1']);
	assert.deepStrictEqual(core.search('', index), []);
});

test('the same item scanned twice is one line with two', () => {
	let cart = core.addLine([], widget);
	cart = core.addLine(cart, widget);
	assert.strictEqual(cart.length, 1);
	assert.strictEqual(cart[0].qty, 2);
	cart = core.addLine(cart, apple, 0.35);
	cart = core.addLine(cart, apple, 0.35);
	assert.strictEqual(cart[1].qty, 0.7);
});

test('setting a quantity to zero removes the line', () => {
	const cart = core.addLine(core.addLine([], widget), apple, 0.5);
	assert.strictEqual(core.setQty(cart, 0, 0).length, 1);
	assert.strictEqual(core.setQty(cart, 1, 2)[1].qty, 2);
});

test('totals: rounded, with and without tax', () => {
	const cart = core.addLine(core.addLine([], widget, 2), apple, 0.35);
	assert.strictEqual(core.totals(cart).total, 480000);
	assert.strictEqual(core.totals(cart, { rows: [{ rate: 10, included: 0 }], exact: true }).total, 528000);
	assert.strictEqual(core.totals(cart, { rows: [{ rate: 10, included: 1 }], exact: true }).total, 480000);
	assert.strictEqual(core.totals(cart, { rows: [], exact: false }).exact, false);
	assert.strictEqual(core.totals([{ qty: 3, rate: 33333.33 }]).total, 100000);
});

test('the sale carries what the server needs and nothing it should not decide', () => {
	const snapshot = { pos_profile: 'P', taxes: { rows: [], exact: true } };
	const sale = core.buildSale({
		id: 'abc', snapshot, cart: core.addLine([], widget), mode: 'کارت‌خوان', mobile: '09121234567', customer: '',
		now: new Date(2026, 10, 9, 9, 5, 7),
	});
	assert.strictEqual(sale.sold_at, '2026-11-09 09:05:07');
	assert.strictEqual(sale.offline_total, 100000);
	assert.deepStrictEqual(sale.items, [{ item_code: 'TST-RET-1', qty: 1, rate: 100000, list_rate: 100000 }]);
	assert.strictEqual(sale.mode, 'کارت‌خوان');
});

test('sale ids are unique, long enough and use the characters the server accepts', () => {
	const rand = (len) => Uint8Array.from({ length: len }, () => Math.floor(Math.random() * 256));
	const ids = new Set(Array.from({ length: 500 }, () => core.makeSaleId(rand)));
	assert.strictEqual(ids.size, 500);
	for (const id of ids) assert.match(id, /^[A-Za-z0-9-]{8,64}$/);
});

test('mobile box: known, new, invalid', () => {
	const customers = [{ name: '0000', mobile: '', points: 9, factor: 1000 }, { name: 'Ali', mobile: '09121234567' }];
	assert.strictEqual(core.findCustomer('09121234567', customers).customer.name, 'Ali');
	assert.strictEqual(core.findCustomer('+989121234567', customers).kind, 'known');
	assert.strictEqual(core.findCustomer('09351112233', customers).kind, 'new');
	assert.strictEqual(core.findCustomer('0912', customers), null);
});

test('queue summary and retry delay', () => {
	assert.deepStrictEqual(core.summary([{ status: 'pending' }, { status: 'pending' }, { status: 'refused' }]), { pending: 2, refused: 1, done: 0 });
	assert.deepStrictEqual([1, 2, 3, 4, 10].map(core.retryDelay), [5, 10, 20, 40, 120]);
});

console.log(`ok ${n} tests`);

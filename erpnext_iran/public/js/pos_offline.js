// The offline till. While the POS is online it keeps a copy of the items, prices, customers and payment modes in
// the browser. When the connection drops, a plain till takes over the screen: scan, mobile number, card or cash,
// Enter. Each sale is stored in the browser (IndexedDB) with an id and sent to the server when the connection is
// back; the server makes one invoice per id, so a sale sent twice is still one invoice. A sale the server refuses
// stays in the browser and is listed under the "offline sales" pill, with the reason.
//
// Not possible offline: redeeming club points, a manager's discount approval, discounts and pricing-rule
// promotions, new customers other than by mobile number (they are made when the sale is sent), and loading the
// POS page itself - it must have been open when the connection dropped.
(function () {
	const core = () => window.erpnext_iran && erpnext_iran.offlineCore;
	const SNAPSHOT_MAX_AGE = 10 * 60 * 1000;
	const PING_EVERY = 5000;

	const state = {
		online: true,
		snapshot: null,
		index: null,
		cart: [],
		mode: null,
		mobile: null, // {kind, mobile, customer}
		queue: [],
		syncing: false,
		nextTry: 0,
		attempts: 0,
		loginNeeded: false,
		lastComplete: 0,
		tillOpen: false,
	};

	// ---------------------------------------------------------------- storage

	let dbPromise = null;
	function db() {
		if (!dbPromise) {
			dbPromise = new Promise((resolve, reject) => {
				const request = indexedDB.open('iran_pos_offline', 1);
				request.onupgradeneeded = () => {
					request.result.createObjectStore('meta');
					request.result.createObjectStore('queue', { keyPath: 'id' });
				};
				request.onsuccess = () => resolve(request.result);
				request.onerror = () => reject(request.error);
			});
		}
		return dbPromise;
	}
	async function run(store, mode, work) {
		const database = await db();
		return new Promise((resolve, reject) => {
			const transaction = database.transaction(store, mode);
			let result;
			const request = work(transaction.objectStore(store));
			if (request) request.onsuccess = () => (result = request.result);
			transaction.oncomplete = () => resolve(result);
			transaction.onerror = transaction.onabort = () => reject(transaction.error);
		});
	}
	const meta = { get: (key) => run('meta', 'readonly', (s) => s.get(key)), set: (key, value) => run('meta', 'readwrite', (s) => s.put(value, key)) };
	const store = {
		all: () => run('queue', 'readonly', (s) => s.getAll()),
		put: (entry) => run('queue', 'readwrite', (s) => s.put(entry)),
		remove: (id) => run('queue', 'readwrite', (s) => s.delete(id)),
	};

	async function loadQueue() {
		state.queue = (await store.all()) || [];
		state.queue.sort((a, b) => a.created - b.created);
		paintPill();
	}

	// ---------------------------------------------------------------- the copy of the shop

	function useSnapshot(snapshot) {
		state.snapshot = snapshot;
		state.index = core().buildIndex(snapshot.items);
		state.mode = (snapshot.modes.find((m) => m.default) || snapshot.modes[0] || {}).mode_of_payment || null;
	}

	const onPosPage = () => /point-of-sale/.test(location.pathname);

	async function refreshSnapshot(force) {
		if (!state.online || !window.indexedDB) return;
		const profile = window.cur_pos && cur_pos.pos_profile;
		if (!profile) return;
		const fresh = state.snapshot && state.snapshot.pos_profile === profile && Date.now() - (state.snapshot.saved_at || 0) < SNAPSHOT_MAX_AGE;
		if (fresh && !force) return;
		try {
			const snapshot = await frappe.xcall('erpnext_iran.offline.snapshot', { pos_profile: profile });
			snapshot.saved_at = Date.now();
			await meta.set('snapshot', snapshot);
			if (!state.tillOpen) useSnapshot(snapshot); // never swap the prices under a sale in progress
			else state.pendingSnapshot = snapshot;
		} catch (error) {
			/* the next round tries again */
		}
	}

	// ---------------------------------------------------------------- connection

	async function ping() {
		if (navigator.onLine === false) return false;
		try {
			const controller = new AbortController();
			const timer = setTimeout(() => controller.abort(), 4000);
			const response = await fetch('/api/method/ping', { cache: 'no-store', credentials: 'same-origin', signal: controller.signal });
			clearTimeout(timer);
			return response.ok;
		} catch (error) {
			return false;
		}
	}

	let misses = 0;
	async function checkConnection() {
		const ok = await ping();
		misses = ok ? 0 : misses + 1;
		const online = ok || misses < 2; // one lost ping is not an outage
		if (online !== state.online) setOnline(online);
	}

	function setOnline(online) {
		state.online = online;
		if (!online) {
			if (onPosPage()) openTill();
		} else {
			state.attempts = 0;
			state.nextTry = 0;
			sync();
			if (state.tillOpen && !state.cart.length) leaveTill();
		}
		paintPill();
		paintTill();
	}

	// ---------------------------------------------------------------- sending

	async function sync() {
		if (state.syncing || !state.online || Date.now() < state.nextTry) return;
		const waiting = state.queue.filter((entry) => entry.status === 'pending');
		if (!waiting.length) return;
		state.syncing = true;
		paintPill();
		try {
			for (let from = 0; from < waiting.length; from += 20) {
				const batch = waiting.slice(from, from + 20);
				const results = await frappe.xcall('erpnext_iran.offline.submit_sales', { sales: JSON.stringify(batch.map((e) => e.sale)) });
				for (const result of results || []) {
					const entry = batch.find((e) => e.id === result.id);
					if (!entry) continue;
					if (result.status === 'refused') Object.assign(entry, { status: 'refused', reason: result.reason, at: Date.now() });
					else Object.assign(entry, { status: 'done', invoice: result.invoice, warning: result.warning || '', at: Date.now() });
					await store.put(entry);
				}
			}
			state.attempts = 0;
			state.loginNeeded = false;
		} catch (error) {
			state.attempts += 1;
			state.nextTry = Date.now() + core().retryDelay(state.attempts) * 1000;
			state.loginNeeded = !!(error && (error.status === 401 || error.status === 403));
		} finally {
			state.syncing = false;
			await loadQueue();
		}
	}

	// ---------------------------------------------------------------- the pill

	function paintPill() {
		let $pill = $('.iran-offline-pill');
		const count = core().summary(state.queue);
		let text = '';
		let color = '';
		if (!state.online) {
			text = __('Offline') + ` — ${count.pending} ` + __('sales waiting');
			color = 'var(--red-500, #e24c4c)';
		} else if (count.refused) {
			text = `${count.refused} ` + __('offline sales refused — tap to see');
			color = 'var(--orange-500, #e79913)';
		} else if (state.loginNeeded && count.pending) {
			text = `${count.pending} ` + __('sales waiting — log in again to send');
			color = 'var(--orange-500, #e79913)';
		} else if (count.pending || state.syncing) {
			text = __('Sending') + ` ${count.pending} ` + __('sales…');
			color = 'var(--blue-500, #4f8ff7)';
		}
		if (!text) return $pill.remove();
		if (!$pill.length) {
			$pill = $('<button type="button" class="iran-offline-pill"></button>').appendTo('body').on('click', showReport);
		}
		$pill.text(text).css('background', color);
	}

	function showReport() {
		const rows = state.queue
			.slice()
			.reverse()
			.map((entry) => {
				const time = frappe.utils.escape_html(entry.sale.sold_at);
				const status = { pending: __('Waiting'), refused: __('Refused'), done: __('Sent') }[entry.status] || entry.status;
				const detail = entry.status === 'refused' ? entry.reason : entry.status === 'done' ? `${entry.invoice || ''} ${entry.warning || ''}` : entry.lastError || '';
				return `<tr><td>${time}</td><td>${format_currency(entry.sale.offline_total)}</td><td><b>${status}</b></td>
					<td>${frappe.utils.escape_html(detail || '')}</td><td><code>${frappe.utils.escape_html(entry.id.slice(0, 8))}</code></td></tr>`;
			})
			.join('');
		const dialog = new frappe.ui.Dialog({
			title: __('Offline sales'),
			size: 'large',
			fields: [{ fieldtype: 'HTML', fieldname: 'report' }],
			primary_action_label: __('Retry refused'),
			primary_action: async () => {
				for (const entry of state.queue.filter((e) => e.status === 'refused')) {
					entry.status = 'pending';
					await store.put(entry);
				}
				state.nextTry = 0;
				dialog.hide();
				await loadQueue();
				sync();
			},
			secondary_action_label: __('Download'),
			secondary_action: () => {
				const blob = new Blob([JSON.stringify(state.queue, null, 1)], { type: 'application/json' });
				const link = document.createElement('a');
				link.href = URL.createObjectURL(blob);
				link.download = 'offline-sales.json';
				link.click();
			},
		});
		dialog.fields_dict.report.$wrapper.html(
			rows
				? `<table class="table table-bordered"><thead><tr><th>${__('Time')}</th><th>${__('Total')}</th><th>${__('Status')}</th><th>${__('Details')}</th><th>${__('ID')}</th></tr></thead><tbody>${rows}</tbody></table>`
				: `<p class="text-muted">${__('No offline sales.')}</p>`
		);
		dialog.show();
	}

	// ---------------------------------------------------------------- the till

	function ensureStyle() {
		if ($('#iran-offline-style').length) return;
		$(`<style id="iran-offline-style">
			.iran-offline-pill{position:fixed;inset-inline-start:16px;bottom:16px;z-index:2000;border:0;border-radius:999px;padding:8px 16px;color:#fff;font-weight:600;box-shadow:0 2px 8px rgba(0,0,0,.25)}
			.iran-till{position:fixed;inset:0;z-index:1900;background:var(--bg-color,#f4f5f6);display:none;flex-direction:column;padding:16px;gap:12px;overflow:auto}
			.iran-till.open{display:flex}
			.iran-till-bar{display:flex;gap:12px;align-items:center;justify-content:space-between}
			.iran-till-bar .badge-off{background:var(--red-500,#e24c4c);color:#fff;border-radius:6px;padding:4px 10px;font-weight:600}
			.iran-till-main{display:flex;gap:16px;flex:1;min-height:0;flex-wrap:wrap}
			.iran-till-left{flex:2;min-width:320px;display:flex;flex-direction:column;gap:8px}
			.iran-till-right{flex:1;min-width:280px;display:flex;flex-direction:column;gap:10px}
			.iran-till input.form-control{font-size:18px}
			.iran-till table{width:100%;background:var(--card-bg,#fff)}
			.iran-till td,.iran-till th{padding:6px 8px;border-bottom:1px solid var(--border-color,#e2e2e2)}
			.iran-till .total{font-size:34px;font-weight:700;text-align:center;background:var(--card-bg,#fff);border-radius:8px;padding:10px}
			.iran-till .mode{display:flex;gap:8px;flex-wrap:wrap}
			.iran-till .mode button{flex:1;padding:10px;font-size:16px}
			.iran-till .mode button.on{outline:3px solid var(--primary,#171717)}
			.iran-till .hint{font-size:12px;color:var(--text-muted)}
			.iran-till .done-btn{padding:14px;font-size:20px}
			.iran-till-results{position:absolute;z-index:5;background:var(--card-bg,#fff);border:1px solid var(--border-color,#ccc);border-radius:6px;max-height:240px;overflow:auto;min-width:280px}
			.iran-till-results div{padding:6px 10px;cursor:pointer}.iran-till-results div:hover{background:var(--control-bg,#f0f0f0)}
			body:has(.iran-till.open) .modal{z-index:2100}body:has(.iran-till.open) .modal-backdrop{z-index:2090}
		</style>`).appendTo('head');
	}

	function till() {
		let $till = $('.iran-till');
		if ($till.length) return $till;
		ensureStyle();
		$till = $(`<div class="iran-till" dir="${document.dir || 'ltr'}">
			<div class="iran-till-bar"><div><span class="badge-off">${__('OFFLINE')}</span> <b class="profile"></b>
				<span class="text-muted waiting"></span></div><div class="hint">F2/F3 ${__('payment mode')} · F7 ${__('mobile')} · Enter ${__('complete')} · Esc ${__('clear')}</div></div>
			<div class="alert alert-warning notice" style="display:none;margin:0"></div>
			<div class="iran-till-main">
				<div class="iran-till-left">
					<div style="position:relative"><input class="form-control scan" autocomplete="off" placeholder="${__('Scan or type an item')}">
						<div class="iran-till-results" style="display:none"></div></div>
					<table><thead><tr><th>${__('Item')}</th><th style="width:110px">${__('Qty')}</th><th>${__('Rate')}</th><th>${__('Amount')}</th><th></th></tr></thead><tbody class="lines"></tbody></table>
				</div>
				<div class="iran-till-right">
					<div class="total">0</div>
					<div class="hint tax-hint"></div>
					<input class="form-control mobile" inputmode="numeric" autocomplete="off" style="direction:ltr;text-align:center" placeholder="${__('Customer mobile number')} (09…)">
					<div class="hint who"></div>
					<div class="mode"></div>
					<button class="btn btn-primary done-btn">${__('Complete Sale')} (Enter)</button>
					<div class="hint">${__('The sale is kept in this browser and sent when the connection is back. Club points cannot be redeemed and discounts cannot be given offline.')}</div>
				</div>
			</div></div>`).appendTo('body');

		const $scan = $till.find('.scan');
		$scan.on('keydown', (event) => {
			if (event.key !== 'Enter') return;
			event.preventDefault();
			const value = $scan.val();
			if (!value.trim()) return completeSale();
			$scan.val('');
			handleCode(value);
		});
		$scan.on('input', () => paintResults($scan.val()));
		$till.on('click', '.iran-till-results div', function () {
			addItem(state.index.byCode.get($(this).data('code')));
			$scan.val('');
			paintResults('');
			$scan.trigger('focus');
		});
		$till.on('change', '.qty-input', function () {
			state.cart = core().setQty(state.cart, Number($(this).data('i')), $(this).val());
			paintTill();
		});
		$till.on('click', '.remove', function () {
			state.cart = core().setQty(state.cart, Number($(this).data('i')), 0);
			paintTill();
		});
		$till.on('click', '.mode button', function () {
			state.mode = $(this).data('mode');
			paintTill();
		});
		$till.on('click', '.done-btn', completeSale);
		const $mobile = $till.find('.mobile');
		$mobile.on('input', () => {
			state.mobile = core().findCustomer($mobile.val(), (state.snapshot || {}).customers);
			paintWho();
		});
		$mobile.on('keydown', (event) => {
			if (event.key === 'Enter') {
				event.preventDefault();
				$scan.trigger('focus');
			}
		});
		// the stock POS under the till must not see these keys (onScan, F-keys)
		$till.on('keydown keypress keyup', (event) => event.stopPropagation());
		$till.on('keydown', (event) => {
			const modes = (state.snapshot || {}).modes || [];
			const at = { F2: 0, F3: 1, F4: 2 }[event.key];
			if (at !== undefined && modes[at]) {
				event.preventDefault();
				state.mode = modes[at].mode_of_payment;
				paintTill();
			} else if (event.key === 'F7') {
				event.preventDefault();
				$mobile.trigger('focus');
			} else if (event.key === 'Escape' && state.cart.length && window.confirm(__('Clear this sale?'))) {
				resetSale();
			} else if (event.key === 'Enter' && !$(event.target).is('.scan, .mobile, .qty-input')) {
				event.preventDefault();
				completeSale();
			}
		});
		// a click outside the boxes brings the cursor back to the scan box
		$till.on('click', (event) => {
			if (!$(event.target).is('input, button, .iran-till-results div')) $scan.trigger('focus');
		});
		return $till;
	}

	function notice(message, kind) {
		const $note = till().find('.notice');
		$note.attr('class', `alert alert-${kind || 'warning'} notice`).text(message).toggle(!!message);
		if (message && kind !== 'danger') setTimeout(() => $note.hide(), 3500);
	}

	function handleCode(value) {
		const hit = core().resolveScan(value, state.index, state.snapshot.scale);
		if (hit) return addItem(hit.item, hit.qty);
		const found = core().search(value, state.index, 1);
		if (found.length) return addItem(found[0]);
		notice(`${__('Not found')}: ${value}`, 'danger');
		frappe.utils.play_sound && frappe.utils.play_sound('error');
	}

	function addItem(item, qty) {
		if (!item) return;
		if (!(item.rate > 0)) return notice(`${item.item_name}: ${__('no price, it cannot be sold offline')}`, 'danger');
		state.cart = core().addLine(state.cart, item, qty);
		paintTill();
	}

	function paintResults(text) {
		const $box = till().find('.iran-till-results');
		const found = text.trim().length > 1 && !/^\d+$/.test(text.trim()) ? core().search(text, state.index, 8) : [];
		$box.toggle(found.length > 0).html(found.map((i) => `<div data-code="${frappe.utils.escape_html(i.item_code)}">${frappe.utils.escape_html(i.item_name)} — ${format_currency(i.rate)}</div>`).join(''));
	}

	function paintWho() {
		const $who = till().find('.who');
		const who = state.mobile;
		if (!who) return $who.text(till().find('.mobile').val() ? __('Not a valid mobile number') : __('Empty: the walk-in customer'));
		if (who.kind === 'new') return $who.text(`${__('New customer')} ${who.mobile} — ${__('made when the sale is sent')}`);
		const c = who.customer;
		const points = c.points == null ? '' : ` · ${__('Club points')}: ${format_number(c.points, null, 0)} ≈ ${format_currency(c.points * (c.factor || 0))} (${__('cannot be redeemed offline')})`;
		$who.text(`${c.customer_name || c.name}${points}`);
	}

	function paintTill() {
		if (!state.tillOpen) return;
		const $till = till();
		const snap = state.snapshot || {};
		const sums = core().totals(state.cart, snap.taxes);
		$till.find('.profile').text(snap.pos_profile || '');
		const count = core().summary(state.queue);
		$till.find('.waiting').text(`${count.pending} ${__('sales waiting')}`);
		$till.find('.lines').html(
			state.cart.map((line, i) => `<tr><td>${frappe.utils.escape_html(line.item_name)}</td>
				<td><input class="form-control qty-input" data-i="${i}" value="${line.qty}" inputmode="decimal"></td>
				<td>${format_currency(line.rate)}</td><td>${format_currency(line.qty * line.rate)}</td>
				<td><button class="btn btn-xs btn-default remove" data-i="${i}">✕</button></td></tr>`).join('')
		);
		$till.find('.total').text(format_currency(sums.total));
		$till.find('.tax-hint').text(sums.exact ? '' : __('The taxes of this profile are not all known here; the invoice total may differ.'));
		$till.find('.mode').html(
			(snap.modes || []).map((m, i) => `<button class="btn btn-default ${m.mode_of_payment === state.mode ? 'on' : ''}" data-mode="${frappe.utils.escape_html(m.mode_of_payment)}">F${i + 2} ${frappe.utils.escape_html(m.mode_of_payment)}</button>`).join('')
		);
		paintWho();
		paintPill();
	}

	function resetSale() {
		state.cart = [];
		state.mobile = null;
		till().find('.mobile, .scan').val('');
		const snap = state.snapshot || {};
		state.mode = (snap.modes.find((m) => m.default) || snap.modes[0] || {}).mode_of_payment || null;
		paintTill();
		till().find('.scan').trigger('focus');
	}

	function randomBytes(n) {
		const bytes = new Uint8Array(n);
		(window.crypto || window.msCrypto).getRandomValues(bytes);
		return bytes;
	}

	async function completeSale() {
		if (Date.now() - state.lastComplete < 2500) return; // a second Enter must not make a second sale
		if (!state.cart.length) return notice(__('Nothing to sell yet'), 'warning');
		if (!state.mode) return notice(__('Choose a payment mode'), 'danger');
		if (state.mobile === null && till().find('.mobile').val().trim()) return notice(__('The mobile number is not valid'), 'danger');
		state.lastComplete = Date.now();

		const who = state.mobile;
		const sale = core().buildSale({
			id: core().makeSaleId(randomBytes),
			snapshot: state.snapshot,
			cart: state.cart,
			mode: state.mode,
			customer: who && who.kind === 'known' ? who.customer.name : state.snapshot.walk_in,
			mobile: who && who.kind === 'new' ? who.mobile : '',
			now: new Date(),
		});
		try {
			await store.put({ id: sale.id, sale, status: 'pending', created: Date.now(), attempts: 0 });
		} catch (error) {
			state.lastComplete = 0;
			return notice(__('This browser could not keep the sale. Do not clear it; write it down.'), 'danger');
		}
		if (state.snapshot.print_receipt) printReceipt(sale);
		notice(`${__('Sale saved on this till')}: ${format_currency(sale.offline_total)}`, 'success');
		resetSale();
		await loadQueue();
		paintTill();
		sync();
		if (state.online) leaveTill(); // the connection came back while this sale was being made
	}

	function printReceipt(sale) {
		const rows = sale.items
			.map((l) => `<tr><td>${frappe.utils.escape_html(((state.index.byCode.get(l.item_code) || {}).item_name) || l.item_code)}</td><td>${l.qty}</td><td style="text-align:end">${format_currency(l.qty * l.rate)}</td></tr>`)
			.join('');
		const html = `<html dir="${document.dir || 'ltr'}"><body style="font:12px sans-serif;width:72mm;margin:0">
			<h3 style="margin:4px 0">${frappe.utils.escape_html(state.snapshot.pos_profile)}</h3>
			<div>${frappe.utils.escape_html(sale.sold_at)}</div><div>${__('Temporary receipt')} · ${sale.id.slice(0, 8)}</div><hr>
			<table style="width:100%;font-size:12px">${rows}</table><hr>
			<b>${__('Total')}: ${format_currency(sale.offline_total)}</b> · ${frappe.utils.escape_html(sale.mode)}</body></html>`;
		const frame = document.createElement('iframe');
		frame.style.cssText = 'position:fixed;width:0;height:0;border:0';
		document.body.appendChild(frame);
		frame.contentDocument.write(html);
		frame.contentDocument.close();
		setTimeout(() => {
			try {
				frame.contentWindow.print();
			} finally {
				setTimeout(() => frame.remove(), 3000);
			}
		}, 200);
	}

	function openTill() {
		if (state.tillOpen) return;
		if (!state.snapshot) {
			frappe.msgprint({
				title: __('Offline'),
				indicator: 'red',
				message: __('There is no connection and this till has no local copy of the shop. Open the POS once while online; it keeps the copy from then on.'),
			});
			return;
		}
		state.tillOpen = true;
		window.erpnext_iran.offlineTillOpen = true;
		resetSale();
		till().addClass('open');
		paintTill();
		setTimeout(() => till().find('.scan').trigger('focus'), 100);
	}

	// Back online with nothing in the till: hand the screen back to the stock POS, reloaded, since its own requests
	// failed while the connection was down.
	function leaveTill() {
		closeTill();
		frappe.show_alert({ message: __('Back online'), indicator: 'green' });
		setTimeout(() => location.reload(), 800);
	}

	function closeTill() {
		state.tillOpen = false;
		window.erpnext_iran.offlineTillOpen = false;
		till().removeClass('open');
		if (state.pendingSnapshot) {
			useSnapshot(state.pendingSnapshot);
			state.pendingSnapshot = null;
		}
	}

	// ---------------------------------------------------------------- start

	async function start() {
		if (!window.indexedDB || !core()) return; // nothing to keep sales in: stay the stock POS
		window.erpnext_iran = Object.assign(window.erpnext_iran || {}, { offlineTillOpen: false });
		try {
			const saved = await meta.get('snapshot');
			if (saved) useSnapshot(saved);
			await loadQueue();
		} catch (error) {
			return;
		}
		window.addEventListener('offline', checkConnection);
		window.addEventListener('online', checkConnection);
		window.addEventListener('beforeunload', (event) => {
			if (state.tillOpen && state.cart.length) {
				event.preventDefault();
				event.returnValue = '';
			}
		});
		setInterval(checkConnection, PING_EVERY);
		setInterval(() => {
			sync();
			refreshSnapshot(false);
			if (state.tillOpen && !onPosPage()) closeTill();
		}, 10000);
		setTimeout(() => {
			sync();
			refreshSnapshot(false);
		}, 3000);
		// the POS opens a few seconds after the page: take the copy as soon as its profile is known
		const wait = setInterval(() => {
			if (window.cur_pos && cur_pos.pos_profile) {
				clearInterval(wait);
				refreshSnapshot(true);
			}
		}, 1500);
		window.erpnext_iran.offline = { state, sync, showReport, openTill, closeTill, refreshSnapshot, checkConnection };
	}

	$(start);
})();

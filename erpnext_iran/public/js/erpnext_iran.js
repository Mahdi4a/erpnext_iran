// Persian digits for displayed numbers when "Use Persian Digits" is ticked in ERPNext Iran Settings.
// Only the read-only formatters are wrapped. Inputs keep 0-9, because the number parser of the
// desk does not read Persian digits and a value typed back would be lost.
(function () {
	const PERSIAN = '۰۱۲۳۴۵۶۷۸۹';

	function persian(text) {
		// Digits in tag attributes (class names, data-*) must stay as they are
		return String(text).replace(/(^|>)([^<]*)/g, (match, edge, content) => edge + content.replace(/\d/g, (d) => PERSIAN[d]));
	}

	function wrapFormatters() {
		if (!(frappe.boot.erpnext_iran && frappe.boot.erpnext_iran.persian_digits)) return;
		['Currency', 'Float', 'Int', 'Percent'].forEach((type) => {
			const original = frappe.form.formatters[type];
			if (!original || original._persian) return;
			const wrapped = function () {
				const result = original.apply(this, arguments);
				return result == null ? result : persian(result);
			};
			wrapped._persian = true;
			frappe.form.formatters[type] = wrapped;
		});
	}

	// Date and Datetime columns, read-only: '2025-03-21' shows as '1404-01-01'
	function wrapDateFormatters() {
		if (!(frappe.boot.erpnext_iran && frappe.boot.erpnext_iran.show_jalali_dates)) return;
		const persianDigits = frappe.boot.erpnext_iran.persian_digits;
		const formatters = {
			Date: (value) => iran_base.formatJalali(value, persianDigits),
			Datetime: (value) => {
				const local = moment(frappe.datetime.convert_to_user_tz(value)).format('YYYY-MM-DD HH:mm');
				const text = iran_base.formatJalali(local, false) + local.slice(10);
				return persianDigits ? iran_base.toPersianDigits(text) : text;
			},
		};
		Object.keys(formatters).forEach((type) => {
			const original = frappe.form.formatters[type];
			if (!original || original._jalali) return;
			const wrapped = function (value) {
				return value ? formatters[type](value) : original.apply(this, arguments);
			};
			wrapped._jalali = true;
			frappe.form.formatters[type] = wrapped;
		});
	}

	$(document).on('startup', wrapFormatters);
	$(document).on('startup', wrapDateFormatters);
	window.erpnext_iran = Object.assign(window.erpnext_iran || {}, { persianDigits: persian });
})();

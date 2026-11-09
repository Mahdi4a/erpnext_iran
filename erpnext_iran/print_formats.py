"""Persian right-to-left print formats for the documents that go to a customer or a supplier.

Iran Sales Invoice is a standard format of its own (print_format/iran_sales_invoice). The ones
here share one layout and are made from a description of each document, so a change to the
layout is made once. They are kept up to date on every migrate."""

from __future__ import annotations

import frappe

from erpnext_iran.pos_receipt import build_receipt_html

STYLE = """<style>
	.iran-doc { direction: rtl; text-align: right; font-family: Vazirmatn, Tahoma, "Noto Naskh Arabic", "DejaVu Sans", sans-serif; font-size: 11px; color: #111; }
	.iran-doc table { width: 100%; border-collapse: collapse; }
	.iran-doc th, .iran-doc td { border: 1px solid #444; padding: 4px 6px; vertical-align: top; }
	.iran-doc th { background: #eee; text-align: center; font-weight: bold; }
	.iran-doc .head td { border: none; padding: 0 0 8px; }
	.iran-doc .title { text-align: center; font-size: 18px; font-weight: bold; }
	.iran-doc .box { border: 1px solid #444; margin-bottom: 8px; }
	.iran-doc .box h4 { margin: 0; padding: 3px 6px; background: #eee; border-bottom: 1px solid #444; font-size: 12px; }
	.iran-doc .box .row { padding: 5px 6px; }
	.iran-doc .num { text-align: left; direction: ltr; white-space: nowrap; }
	.iran-doc .center { text-align: center; }
	.iran-doc .totals { width: 50%; margin-right: 0; margin-left: auto; }
	.iran-doc .sign td { height: 70px; text-align: center; }
	.iran-doc .muted { color: #666; }
</style>"""

MONEY = '{%- macro money(value) -%}{{ "{:,.0f}".format(value or 0) | iran_digits }}{%- endmacro -%}'

# party_doctype: who the other side is; "company_is_seller" tells which box comes first
DOCUMENTS = {
	"Purchase Invoice": {
		"title": "صورت‌حساب خرید کالا و خدمات",
		"number_label": "شماره صورت‌حساب",
		"party_doctype": "Supplier",
		"party": "supplier",
		"party_name": "supplier_name",
		"company_is_seller": False,
		"dates": [("تاریخ", "posting_date"), ("سررسید", "due_date")],
	},
	"Quotation": {
		"title": "پیش‌فاکتور فروش",
		"number_label": "شماره پیش‌فاکتور",
		"party_doctype": "Customer",
		"party": "party_name",
		"party_name": "customer_name",
		"company_is_seller": True,
		"dates": [("تاریخ", "transaction_date"), ("اعتبار تا", "valid_till")],
	},
	"Sales Order": {
		"title": "سفارش فروش",
		"number_label": "شماره سفارش",
		"party_doctype": "Customer",
		"party": "customer",
		"party_name": "customer_name",
		"company_is_seller": True,
		"dates": [("تاریخ", "transaction_date"), ("تاریخ تحویل", "delivery_date")],
	},
	"Delivery Note": {
		"title": "حواله تحویل کالا",
		"number_label": "شماره حواله",
		"party_doctype": "Customer",
		"party": "customer",
		"party_name": "customer_name",
		"company_is_seller": True,
		"dates": [("تاریخ", "posting_date")],
	},
}


def _party_box(config: dict, heading: str, party_side: bool) -> str:
	if party_side:
		party, name = config["party"], config["party_name"]
		ids = (
			"{% if party.economic_code %} &nbsp;|&nbsp; شماره اقتصادی: <span dir=\"ltr\">{{ party.economic_code | iran_digits }}</span>{% endif %}"
			"{% if party.national_id %} &nbsp;|&nbsp; کد ملی: <span dir=\"ltr\">{{ party.national_id | iran_digits }}</span>{% endif %}"
			"{% if party.legal_id %} &nbsp;|&nbsp; شناسه ملی: <span dir=\"ltr\">{{ party.legal_id | iran_digits }}</span>{% endif %}"
			"{% if doc.contact_mobile %} &nbsp;|&nbsp; تلفن: {{ doc.contact_mobile | iran_digits }}{% endif %}"
		)
		address = "{% if doc.address_display %}<div>نشانی: {{ doc.address_display }}</div>{% endif %}"
		who = "{{ (doc." + name + " or doc." + party + ") | e }}"
	else:
		ids = (
			"{% if company.tax_id %} &nbsp;|&nbsp; شماره اقتصادی: {{ company.tax_id | iran_digits }}{% endif %}"
			"{% if company.phone_no %} &nbsp;|&nbsp; تلفن: {{ company.phone_no | iran_digits }}{% endif %}"
		)
		address = (
			"{% set company_address = doc.company_address_display or doc.billing_address_display %}"
			"{% if company_address %}<div>نشانی: {{ company_address }}</div>{% endif %}"
		)
		who = "{{ doc.company | e }}"
	return (
		f'<div class="box"><h4>{heading}</h4><div class="row">'
		f"نام شخص حقیقی / حقوقی: <b>{who}</b>{ids}{address}</div></div>"
	)


def build_document_html(doctype: str) -> str:
	config = DOCUMENTS[doctype]
	party = config["party"]
	party_lookup = (
		'{%- set party_key = doc.get("' + party + '") or "" -%}'
		'{%- set party = frappe.db.get_value("' + config["party_doctype"] + '", party_key, '
		'["national_id", "legal_id", "economic_code"], as_dict=True) or {} -%}'
	)
	dates = "".join(
		f'{{% if doc.get("{field}") %}}<div>{label}: <b dir="ltr">{{{{ doc.{field} | jalali_date | iran_digits }}}}</b></div>{{% endif %}}'
		for label, field in config["dates"]
	)
	seller_first = config["company_is_seller"]
	seller = _party_box(config, "مشخصات فروشنده", party_side=not seller_first)
	buyer = _party_box(config, "مشخصات خریدار", party_side=seller_first)
	return f"""{{%- set company = frappe.get_cached_doc("Company", doc.company) -%}}
{party_lookup}
{MONEY}
{STYLE}
<div class="iran-doc">
	<table class="head"><tr>
		<td style="width: 30%">{{% if doc.docstatus == 0 %}}<span class="muted">{{{{ _("Draft") }}}}</span>{{% endif %}}</td>
		<td class="title">{config["title"]}</td>
		<td style="width: 30%"><div>{config["number_label"]}: <b dir="ltr">{{{{ doc.name | iran_digits }}}}</b></div>{dates}</td>
	</tr></table>
	{seller}
	{buyer}
	<table>
		<thead><tr>
			<th style="width: 4%">ردیف</th><th>شرح کالا یا خدمات</th><th style="width: 8%">تعداد</th><th style="width: 8%">واحد</th>
			<th style="width: 13%">مبلغ واحد</th><th style="width: 13%">تخفیف</th><th style="width: 15%">مبلغ کل پس از تخفیف</th>
		</tr></thead>
		<tbody>
			{{% for row in doc.items %}}
			<tr>
				<td class="center">{{{{ loop.index | iran_digits }}}}</td>
				<td>{{{{ row.item_name | e }}}}{{% if row.description and row.description != row.item_name %}}<div class="muted">{{{{ row.description }}}}</div>{{% endif %}}</td>
				<td class="center">{{{{ row.get_formatted("qty", doc) | iran_digits }}}}</td>
				<td class="center">{{{{ row.uom | e }}}}</td>
				<td class="num">{{{{ money(row.rate) }}}}</td>
				<td class="num">{{{{ money(row.discount_amount * row.qty if row.discount_amount else 0) }}}}</td>
				<td class="num">{{{{ money(row.amount) }}}}</td>
			</tr>
			{{% endfor %}}
		</tbody>
	</table>
	<table class="totals" style="margin-top: 8px">
		<tr><td>جمع کل</td><td class="num">{{{{ money(doc.net_total) }}}}</td></tr>
		{{% if doc.discount_amount %}}<tr><td>تخفیف کل</td><td class="num">{{{{ money(doc.discount_amount) }}}}</td></tr>{{% endif %}}
		{{% for tax in doc.taxes %}}
		<tr><td>{{{{ "مالیات بر ارزش افزوده" if tax.description == "VAT" else (tax.description or tax.account_head) | e }}}}{{% if tax.rate %}} ({{{{ tax.rate | iran_digits }}}}٪){{% endif %}}</td><td class="num">{{{{ money(tax.tax_amount) }}}}</td></tr>
		{{% endfor %}}
		<tr><th>مبلغ قابل پرداخت ({{{{ doc.currency }}}})</th><th class="num">{{{{ money(doc.rounded_total or doc.grand_total) }}}}</th></tr>
	</table>
	{{% if doc.in_words %}}<div style="margin-top: 6px">مبلغ به حروف: <b>{{{{ doc.in_words | iran_digits }}}}</b></div>{{% endif %}}
	{{% if doc.terms or doc.remarks %}}<div class="box" style="margin-top: 8px"><h4>توضیحات</h4><div class="row">{{{{ doc.terms or doc.remarks }}}}</div></div>{{% endif %}}
	<table class="sign" style="margin-top: 14px"><tr><td>مهر و امضای فروشنده</td><td>مهر و امضای خریدار</td></tr></table>
</div>
"""


def build_payment_entry_html() -> str:
	return f"""{MONEY}
{STYLE}
{{%- set receive = doc.payment_type == "Receive" -%}}
{{%- set amount = doc.received_amount if receive else doc.paid_amount -%}}
{{%- set currency = doc.paid_to_account_currency if receive else doc.paid_from_account_currency -%}}
<div class="iran-doc">
	<table class="head"><tr>
		<td style="width: 30%">{{% if doc.docstatus == 0 %}}<span class="muted">{{{{ _("Draft") }}}}</span>{{% endif %}}</td>
		<td class="title">{{{{ "سند دریافت وجه" if receive else "سند پرداخت وجه" }}}}</td>
		<td style="width: 30%"><div>شماره سند: <b dir="ltr">{{{{ doc.name | iran_digits }}}}</b></div><div>تاریخ: <b dir="ltr">{{{{ doc.posting_date | jalali_date | iran_digits }}}}</b></div></td>
	</tr></table>
	<table>
		<tr><th style="width: 22%">شرکت</th><td>{{{{ doc.company | e }}}}</td></tr>
		{{% if doc.party %}}<tr><th>{{{{ "پرداخت‌کننده" if receive else "دریافت‌کننده" }}}}</th><td>{{{{ (doc.party_name or doc.party) | e }}}}</td></tr>{{% endif %}}
		<tr><th>روش پرداخت</th><td>{{{{ (doc.mode_of_payment or "") | e }}}}</td></tr>
		{{% if doc.reference_no %}}<tr><th>شماره مرجع / چک</th><td dir="ltr" style="text-align: right">{{{{ doc.reference_no | iran_digits }}}}{{% if doc.reference_date %}} &nbsp;|&nbsp; {{{{ doc.reference_date | jalali_date | iran_digits }}}}{{% endif %}}</td></tr>{{% endif %}}
		<tr><th>مبلغ ({{{{ currency }}}})</th><td class="num"><b>{{{{ money(amount) }}}}</b></td></tr>
		{{% if doc.in_words %}}<tr><th>مبلغ به حروف</th><td>{{{{ doc.in_words | iran_digits }}}}</td></tr>{{% endif %}}
		{{% if doc.remarks %}}<tr><th>توضیحات</th><td>{{{{ doc.remarks }}}}</td></tr>{{% endif %}}
	</table>
	<table class="sign" style="margin-top: 14px"><tr><td>امضای {{{{ "دریافت‌کننده" if receive else "پرداخت‌کننده" }}}}</td><td>امضای تأییدکننده</td></tr></table>
</div>
"""


def formats() -> dict[str, tuple[str, str]]:
	"""Print Format name -> (document type, html)"""
	result = {f"Iran {doctype}": (doctype, build_document_html(doctype)) for doctype in DOCUMENTS}
	result["Iran Payment Entry"] = ("Payment Entry", build_payment_entry_html())
	result["Iran POS Receipt"] = ("Sales Invoice", build_receipt_html())
	return result


def ensure_print_formats():
	for name, (doctype, html) in formats().items():
		if frappe.db.exists("Print Format", name):
			doc = frappe.get_doc("Print Format", name)
		else:
			doc = frappe.new_doc("Print Format")
			doc.name = name
		doc.update(
			{
				"doc_type": doctype,
				"module": "Erpnext Iran",
				"standard": "No",
				"custom_format": 1,
				"print_format_type": "Jinja",
				"default_print_language": "fa",
				"html": html,
				"disabled": 0,
				"font_size": 11,
				"margin_top": 10,
				"margin_bottom": 10,
				"margin_left": 10,
				"margin_right": 10,
				"align_labels_right": 1,
				"line_breaks": 0,
				"show_section_headings": 0,
				"raw_printing": 0,
				"absolute_value": 0,
			}
		)
		doc.flags.ignore_permissions = True
		doc.save()

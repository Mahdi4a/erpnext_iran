"""The receipt a shop prints for a POS sale: 80 mm wide, right to left, in Persian, with the Jalali date."""

from __future__ import annotations

STYLE = """<style>
	@page { size: 80mm auto; margin: 2mm; }
	.iran-receipt { direction: rtl; text-align: right; width: 72mm; font-family: Vazirmatn, Tahoma, "DejaVu Sans", sans-serif; font-size: 11px; color: #000; }
	.iran-receipt .c { text-align: center; }
	.iran-receipt .big { font-size: 15px; font-weight: bold; }
	.iran-receipt table { width: 100%; border-collapse: collapse; }
	.iran-receipt td, .iran-receipt th { padding: 2px 0; vertical-align: top; }
	.iran-receipt th { border-bottom: 1px solid #000; font-weight: bold; }
	.iran-receipt .n { text-align: left; direction: ltr; white-space: nowrap; }
	.iran-receipt .line { border-top: 1px dashed #000; margin: 4px 0; }
	.iran-receipt .total td { font-size: 13px; font-weight: bold; }
</style>"""

MONEY = '{%- macro money(value) -%}{{ "{:,.0f}".format(value or 0) | iran_digits }}{%- endmacro -%}'

BODY = """
<div class="iran-receipt">
	<div class="c big">{{ doc.company | e }}</div>
	{% if doc.pos_profile %}<div class="c">{{ doc.pos_profile | e }}</div>{% endif %}
	<div class="line"></div>
	<table>
		<tr><td>شماره فیش</td><td class="n">{{ doc.name | iran_digits }}</td></tr>
		<tr><td>تاریخ</td><td class="n">{{ doc.posting_date | jalali_date }} {{ (doc.get_formatted("posting_time") or "")[:5] | iran_digits }}</td></tr>
		<tr><td>صندوقدار</td><td>{{ (frappe.db.get_value("User", doc.owner, "full_name") or doc.owner) | e }}</td></tr>
		{% if doc.customer_name and doc.customer_name != doc.customer %}<tr><td>مشتری</td><td>{{ doc.customer_name | e }}</td></tr>{% endif %}
	</table>
	<div class="line"></div>
	<table>
		<tr><th>کالا</th><th>تعداد</th><th>مبلغ</th></tr>
		{% for row in doc.items %}
		<tr>
			<td>{{ row.item_name | e }}<br><span class="n">{{ money(row.rate) }}</span></td>
			<td class="c">{{ ("%g" | format(row.qty)) | iran_digits }}</td>
			<td class="n">{{ money(row.amount) }}</td>
		</tr>
		{% endfor %}
	</table>
	<div class="line"></div>
	<table>
		{% if doc.discount_amount %}<tr><td>تخفیف</td><td class="n">{{ money(doc.discount_amount) }}</td></tr>{% endif %}
		{% for tax in doc.taxes %}<tr><td>{{ tax.description | e }}</td><td class="n">{{ money(tax.tax_amount) }}</td></tr>{% endfor %}
		<tr class="total"><td>مبلغ قابل پرداخت</td><td class="n">{{ money(doc.rounded_total or doc.grand_total) }}</td></tr>
	</table>
	{% if doc.payments %}
	<div class="line"></div>
	<table>
		{% for pay in doc.payments %}{% if pay.amount %}<tr><td>{{ pay.mode_of_payment | e }}</td><td class="n">{{ money(pay.amount) }}</td></tr>{% endif %}{% endfor %}
		{% if doc.change_amount %}<tr><td>باقی‌مانده به مشتری</td><td class="n">{{ money(doc.change_amount) }}</td></tr>{% endif %}
	</table>
	{% endif %}
	<div class="line"></div>
	<div class="c">از خرید شما سپاسگزاریم</div>
</div>
"""


def build_receipt_html() -> str:
	return STYLE + MONEY + BODY

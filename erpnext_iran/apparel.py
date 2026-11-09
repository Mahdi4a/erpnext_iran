"""The clothing pack: a style with all its sizes and colours in one step, and the end of the season.

A garment is sold as "this shirt, in blue, size M", and each of those is an item with its own barcode and its own
stock. ERPNext has the machinery (a template item with Size and Colour, and a variant for every combination);
what a shop wants is to type the style once and have every variant made with a barcode to stick on it and a
price. The matrix and sell-through reports and the season clearance are in the same pack.
"""

from __future__ import annotations

import re

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

SIZE, COLOUR = "Size", "Colour"
SEASONS = ("بهار", "تابستان", "پاییز", "زمستان", "همه فصل")
STYLE_CODE = re.compile(r"^[A-Za-z0-9-]{2,30}$")
MAX_VARIANTS = 150
DEFAULT_SIZES = [("S", "S"), ("M", "M"), ("L", "L"), ("XL", "XL"), ("XXL", "XXL"), ("3XL", "3XL")]
DEFAULT_COLOURS = [
	("سیاه", "SYH"), ("سفید", "SFD"), ("قرمز", "GHM"), ("آبی", "ABI"), ("سرمه‌ای", "SRM"), ("خاکستری", "KHK"),
	("سبز", "SBZ"), ("زرد", "ZRD"), ("نارنجی", "NRJ"), ("بنفش", "BNF"), ("قهوه‌ای", "GHV"), ("کرم", "KRM"), ("صورتی", "SRT"),
]


def ensure_attributes():
	"""Size and Colour with the usual values; values somebody added or changed are left alone."""
	for attribute, values in ((SIZE, DEFAULT_SIZES), (COLOUR, DEFAULT_COLOURS)):
		doc = frappe.get_doc("Item Attribute", attribute) if frappe.db.exists("Item Attribute", attribute) else frappe.new_doc("Item Attribute")
		if doc.is_new():
			doc.attribute_name = attribute
		have_values = {row.attribute_value for row in doc.item_attribute_values}
		have_abbr = {row.abbr for row in doc.item_attribute_values}
		changed = doc.is_new()
		for value, abbr in values:
			if value in have_values or abbr in have_abbr:
				continue
			doc.append("item_attribute_values", {"attribute_value": value, "abbr": abbr})
			changed = True
		if changed:
			doc.flags.ignore_permissions = True
			doc.save()


# ------------------------------------------------------------------ barcodes


def next_barcodes(count: int) -> list[str]:
	"""EAN-13 codes for new variants: a prefix reserved for a shop's own use, a running number, the check digit."""
	from iran_base.settings import get_setting

	from erpnext_iran.scale import ean13_check_digit

	prefix = str(get_setting("apparel_barcode_prefix", "ERPNext Iran Settings") or "29")
	if not prefix.isdigit() or not 1 <= len(prefix) <= 6:
		frappe.throw(_("The barcode prefix must be one to six digits"))
	room = 12 - len(prefix)
	last = frappe.db.sql(
		"select max(cast(substr(barcode, %s, %s) as unsigned)) from `tabItem Barcode` where barcode like %s and length(barcode) = 13",
		(len(prefix) + 1, room, f"{prefix}%"),
	)[0][0]
	number = int(last or 0)
	codes = []
	for _unused in range(count):
		number += 1
		if len(str(number)) > room:
			frappe.throw(_("The barcode numbers under the prefix {0} are used up").format(prefix))
		body = prefix + str(number).zfill(room)
		codes.append(body + ean13_check_digit(body))
	return codes


def inherit_season(doc, method=None):
	"""Item validate: a variant has its template's season. ERPNext copies only the fields listed in Item Variant
	Settings to a variant, so a custom field like this one would stay empty."""
	if doc.get("variant_of") and not doc.get("season"):
		doc.season = frappe.db.get_value("Item", doc.variant_of, "season")


# ------------------------------------------------------------------ making a style


def clean_choices(values, attribute: str) -> list[str]:
	"""The chosen values as the attribute names them. A value may be written by its name or by its short code
	(S for Small), whichever the shop is used to."""
	values = frappe.parse_json(values) if isinstance(values, str) else values
	chosen = list(dict.fromkeys(str(v).strip() for v in (values or []) if str(v).strip()))
	rows = frappe.get_all("Item Attribute Value", {"parent": attribute}, ["attribute_value", "abbr"])
	by_name = {r.attribute_value: r.attribute_value for r in rows}
	by_abbr = {r.abbr.lower(): r.attribute_value for r in rows}
	resolved, unknown = [], []
	for value in chosen:
		name = by_name.get(value) or by_abbr.get(value.lower())
		(resolved if name else unknown).append(name or value)
	if unknown:
		frappe.throw(_("{0}: {1} is not one of its values. Add it to the attribute first.").format(attribute, ", ".join(unknown)))
	if not resolved:
		frappe.throw(_("Choose at least one {0}").format(attribute))
	return list(dict.fromkeys(resolved))


@frappe.whitelist(methods=["POST"])
def make_style(
	style_code: str, style_name: str, item_group: str, sizes, colours, rate: float, season: str | None = None,
	price_list: str | None = None, brand: str | None = None, stock_uom: str = "Nos",
) -> dict:
	"""A template item, one variant for every size and colour with a barcode, and the price of each."""
	from erpnext.controllers.item_variant import create_variant

	frappe.has_permission("Item", "create", throw=True)
	style_code = (style_code or "").strip()
	if not STYLE_CODE.match(style_code):
		frappe.throw(_("The style code is 2 to 30 letters, digits or dashes"))
	if frappe.db.exists("Item", style_code):
		frappe.throw(_("{0} already exists").format(style_code))
	if flt(rate) <= 0:
		frappe.throw(_("The price must be more than zero"))
	if season and season not in SEASONS:
		frappe.throw(_("Season must be one of {0}").format("، ".join(SEASONS)))
	if not frappe.db.exists("Item Group", item_group):
		frappe.throw(_("Item Group {0} does not exist").format(item_group))
	ensure_attributes()
	sizes, colours = clean_choices(sizes, SIZE), clean_choices(colours, COLOUR)
	if len(sizes) * len(colours) > MAX_VARIANTS:
		frappe.throw(_("{0} sizes x {1} colours is more than {2} items; make the style in two parts").format(len(sizes), len(colours), MAX_VARIANTS))
	price_list = price_list or frappe.db.get_single_value("Selling Settings", "selling_price_list")

	template = frappe.new_doc("Item")
	template.update(
		{
			"item_code": style_code,
			"item_name": style_name or style_code,
			"item_group": item_group,
			"stock_uom": stock_uom,
			"is_stock_item": 1,
			"has_variants": 1,
			"variant_based_on": "Item Attribute",
			"brand": brand,
			"season": season,
		}
	)
	template.append("attributes", {"attribute": SIZE})
	template.append("attributes", {"attribute": COLOUR})
	template.insert()

	combos = [(s, c) for c in colours for s in sizes]
	codes = next_barcodes(len(combos))
	made = []
	for (size, colour), barcode in zip(combos, codes, strict=True):
		variant = create_variant(template.name, {SIZE: size, COLOUR: colour})
		variant.append("barcodes", {"barcode": barcode, "barcode_type": "EAN"})
		variant.insert()
		if price_list:
			frappe.get_doc({"doctype": "Item Price", "item_code": variant.name, "price_list": price_list, "price_list_rate": flt(rate)}).insert()
		made.append({"item_code": variant.name, "size": size, "colour": colour, "barcode": barcode})
	return {"template": template.name, "variants": made}


# ------------------------------------------------------------------ the end of the season


@frappe.whitelist(methods=["POST"])
def season_clearance(season: str, discount_percent: float, valid_from: str, valid_upto: str, company: str | None = None) -> str:
	"""One Pricing Rule taking a percentage off every style of the season, between two dates. Styles are listed by
	their template, which ERPNext applies to all variants."""
	frappe.has_permission("Pricing Rule", "create", throw=True)
	if season not in SEASONS:
		frappe.throw(_("Season must be one of {0}").format("، ".join(SEASONS)))
	if not 0 < flt(discount_percent) <= 90:
		frappe.throw(_("The discount must be more than 0 and at most 90 percent"))
	if getdate(valid_upto) < getdate(valid_from):
		frappe.throw(_("The end date is before the start date"))
	items = frappe.get_all("Item", {"season": season, "variant_of": ["is", "not set"], "disabled": 0}, pluck="name")
	if not items:
		frappe.throw(_("No item is marked for the season {0}").format(season))
	rule = frappe.new_doc("Pricing Rule")
	rule.update(
		{
			"title": f"{season} clearance {valid_from}",
			"apply_on": "Item Code",
			"selling": 1,
			"price_or_product_discount": "Price",
			"rate_or_discount": "Discount Percentage",
			"discount_percentage": flt(discount_percent),
			"valid_from": valid_from,
			"valid_upto": valid_upto,
			"company": company or frappe.defaults.get_user_default("Company"),
			"priority": 5,
		}
	)
	for name in items:
		rule.append("items", {"item_code": name})
	rule.insert()
	return rule.name

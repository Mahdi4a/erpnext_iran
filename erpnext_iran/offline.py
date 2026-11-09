"""The offline till: what the browser keeps a copy of, and how a sale made without a connection reaches the books.

snapshot()     everything the till needs to sell with no server: items with barcodes and prices, the customers
               that can be found by mobile with their club points, the payment modes and the taxes.
submit_sales() the sales the browser queued. Each carries an id the browser made, stored on the invoice, so a
               sale sent twice (a lost reply, two tabs) is one invoice. A sale the rules refuse (stock, discount
               limit, a closed shift) comes back as refused with the reason and stays in the browser queue.
"""

import re
from contextlib import contextmanager
from datetime import datetime, timedelta

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, now_datetime, strip_html_tags, today

MAX_SALES_PER_CALL = 50
MAX_LINES = 200
ID_PATTERN = re.compile(r"^[A-Za-z0-9-]{8,64}$")
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


# ---------------------------------------------------------------- the copy the browser keeps


@frappe.whitelist()
def snapshot(pos_profile: str) -> dict:
	frappe.has_permission("POS Profile", "read", doc=pos_profile, throw=True)
	# the copy carries every customer's mobile and points (prices reach the POS through Item for any cashier)
	for doctype in ("Item", "Customer"):
		frappe.has_permission(doctype, "read", throw=True)
	profile = frappe.get_cached_doc("POS Profile", pos_profile)

	from erpnext_iran.scale import get_scale_settings, registered_barcodes, item_barcode

	scale = get_scale_settings()
	scale["items"] = [item_barcode(plu, scale) for plu in registered_barcodes() if len(plu) == scale["plu_digits"]]

	return {
		"pos_profile": profile.name,
		"company": profile.company,
		"currency": profile.currency,
		"walk_in": profile.customer,
		"print_receipt": cint(profile.get("print_receipt_on_order_complete")),
		"modes": [
			{"mode_of_payment": row.mode_of_payment, "default": cint(row.default)} for row in profile.payments
		],
		"taxes": tax_rows(profile),
		"scale": scale,
		"items": item_rows(profile),
		"customers": customer_rows(),
		"generated_at": now_datetime().strftime(TIME_FORMAT),
	}


def tax_rows(profile) -> dict:
	"""Only 'On Net Total' rows can be worked out in the browser. Anything else makes the offline total an estimate."""
	if not profile.get("taxes_and_charges"):
		return {"rows": [], "exact": True}
	template = frappe.get_cached_doc("Sales Taxes and Charges Template", profile.taxes_and_charges)
	rows = [
		{"rate": flt(row.rate), "included": cint(row.included_in_print_rate)}
		for row in template.taxes
		if row.charge_type == "On Net Total"
	]
	return {"rows": rows, "exact": len(rows) == len(template.taxes)}


def item_rows(profile) -> list[dict]:
	filters = {"disabled": 0, "is_sales_item": 1, "has_variants": 0, "is_fixed_asset": 0}
	groups = None
	if profile.get("item_groups"):
		from erpnext.accounts.doctype.pos_profile.pos_profile import get_item_groups

		groups = get_item_groups(profile.name)
		filters["item_group"] = ["in", groups]

	items = frappe.get_all(
		"Item", filters=filters, fields=["name as item_code", "item_name", "stock_uom as uom", "scale_plu"]
	)
	wanted = {item.item_code for item in items}

	prices = {}
	for price in frappe.get_all(
		"Item Price",
		filters={"price_list": profile.selling_price_list, "selling": 1},
		fields=["item_code", "uom", "price_list_rate", "valid_from", "valid_upto"],
		order_by="valid_from asc",
	):
		if price.item_code not in wanted:
			continue
		if price.valid_from and getdate(price.valid_from) > getdate(today()):
			continue
		if price.valid_upto and getdate(price.valid_upto) < getdate(today()):
			continue
		prices[price.item_code] = flt(price.price_list_rate)

	barcodes: dict[str, list[str]] = {}
	for row in frappe.get_all("Item Barcode", fields=["parent", "barcode"]):
		if row.parent in wanted and row.barcode:
			barcodes.setdefault(row.parent, []).append(row.barcode)

	return [
		{
			"item_code": item.item_code,
			"item_name": item.item_name,
			"uom": item.uom,
			"rate": prices.get(item.item_code, 0),
			"barcodes": barcodes.get(item.item_code, []),
			"scale_plu": item.scale_plu or "",
		}
		for item in items
	]


def customer_rows() -> list[dict]:
	"""Customers a cashier may meet by mobile: those with a mobile, a number for a name, or a club programme."""
	factors = dict(frappe.get_all("Loyalty Program", fields=["name", "conversion_factor"], as_list=True))
	rows = frappe.db.sql(
		"""
		select c.name, c.customer_name, c.mobile_no, ifnull(c.loyalty_program, '') as loyalty_program,
			ifnull(lp.points, 0) as points
		from `tabCustomer` c
		left join (
			select customer, sum(loyalty_points) as points from `tabLoyalty Point Entry`
			where expiry_date is null or expiry_date >= %s group by customer
		) lp on lp.customer = c.name
		where c.disabled = 0
			and (ifnull(c.mobile_no, '') != '' or ifnull(c.loyalty_program, '') != '' or c.name regexp '^09[0-9]{9}$')
		limit 100000
		""",
		today(),
		as_dict=True,
	)
	return [
		{
			"name": row.name,
			"customer_name": row.customer_name,
			"mobile": row.mobile_no or (row.name if re.fullmatch(r"09\d{9}", row.name or "") else ""),
			"points": cint(row.points) if row.loyalty_program else None,
			"factor": flt(factors.get(row.loyalty_program)),
		}
		for row in rows
	]


# ---------------------------------------------------------------- the queued sales


class RefusedSale(Exception):
	"""A sale that can never be accepted as sent; it goes back to the till with the reason."""


def clean_sale(sale) -> dict:
	"""The queued sale as the server will use it, or RefusedSale. Pure: no database."""
	if not isinstance(sale, dict):
		raise RefusedSale(_("Not a sale"))
	sale_id = str(sale.get("id") or "")
	if not ID_PATTERN.match(sale_id):
		raise RefusedSale(_("The sale has no valid id"))

	lines = sale.get("items")
	if not isinstance(lines, list) or not lines or len(lines) > MAX_LINES:
		raise RefusedSale(_("A sale needs between 1 and {0} lines").format(MAX_LINES))
	cleaned = []
	for line in lines:
		try:
			qty, rate = flt(line.get("qty")), flt(line.get("rate"))
			list_rate = flt(line.get("list_rate")) or rate
			code = str(line.get("item_code") or "")
		except AttributeError:
			raise RefusedSale(_("A line of the sale is malformed")) from None
		if not code or qty <= 0 or qty > 1_000_000 or rate < 0:
			raise RefusedSale(_("Line {0}: item, quantity or rate is not valid").format(len(cleaned) + 1))
		cleaned.append({"item_code": code, "qty": qty, "rate": rate, "list_rate": list_rate})

	try:
		sold_at = datetime.strptime(str(sale.get("sold_at") or ""), TIME_FORMAT)
	except ValueError:
		raise RefusedSale(_("The sale has no valid date and time")) from None
	if sold_at > datetime.now() + timedelta(days=1):
		raise RefusedSale(_("The sale is dated in the future: {0}").format(sale.get("sold_at")))

	mobile = ""
	if sale.get("mobile"):
		from iran_base.utils.sms import try_normalize_mobile

		mobile = try_normalize_mobile(sale["mobile"])
		if not mobile:
			raise RefusedSale(_("{0} is not a valid mobile number").format(sale["mobile"]))

	return {
		"id": sale_id,
		"pos_profile": str(sale.get("pos_profile") or ""),
		"mode": str(sale.get("mode") or ""),
		"customer": str(sale.get("customer") or ""),
		"mobile": mobile,
		"sold_at": sold_at,
		"offline_total": flt(sale.get("offline_total")),
		"items": cleaned,
	}


def existing_invoice(sale_id: str) -> str | None:
	return frappe.db.get_value("Sales Invoice", {"offline_sale_id": sale_id}, "name")


@frappe.whitelist(methods=["POST"])
def submit_sales(sales) -> list[dict]:
	sales = frappe.parse_json(sales)
	if not isinstance(sales, list) or len(sales) > MAX_SALES_PER_CALL:
		frappe.throw(_("Send at most {0} sales at a time").format(MAX_SALES_PER_CALL))
	return [submit_one(sale) for sale in sales]


def submit_one(raw) -> dict:
	sale_id = str(raw.get("id") or "") if isinstance(raw, dict) else ""
	result = {"id": sale_id}
	try:
		sale = clean_sale(raw)
		if name := existing_invoice(sale["id"]):
			return {**result, "status": "duplicate", "invoice": name}

		doc = build_invoice(sale)
		with negative_stock_allowed():
			doc.insert()
			doc.submit()
		frappe.db.commit()
		out = {**result, "status": "ok", "invoice": doc.name}
		total = flt(doc.rounded_total) or flt(doc.grand_total)
		if sale["offline_total"] and abs(total - sale["offline_total"]) > 0.5:
			out["warning"] = _("The till showed {0} and the invoice is {1}").format(sale["offline_total"], total)
		return out
	except frappe.UniqueValidationError:
		frappe.db.rollback()
		return {**result, "status": "duplicate", "invoice": existing_invoice(sale_id)}
	except (RefusedSale, frappe.ValidationError, frappe.PermissionError, frappe.DoesNotExistError) as error:
		frappe.db.rollback()
		frappe.clear_messages()
		return {**result, "status": "refused", "reason": strip_html_tags(str(error)).strip()}


FLAG = "iran_offline_negative_stock"


@contextmanager
def negative_stock_allowed():
	"""The goods of an offline sale are already gone; the books follow. Only for the call that makes the invoice.

	The flag lives on frappe.flags, which belongs to this request alone, so a sale rung up at the same moment on
	another thread of the same server still gets ERPNext's stock check."""
	if cint(frappe.db.get_single_value("ERPNext Iran Settings", "offline_refuse_negative_stock")):
		yield
		return
	install()
	frappe.flags[FLAG] = True
	try:
		yield
	finally:
		frappe.flags[FLAG] = False


def install(*args, **kwargs):
	"""Lets ERPNext's negative stock check ask the flag above. Put in once per process; safe to call again."""
	from erpnext.stock import stock_ledger

	original = stock_ledger.is_negative_stock_allowed
	if getattr(original, "_iran_offline", False):
		return

	def allowed(**kwargs):
		return bool(frappe.flags.get(FLAG)) or original(**kwargs)

	allowed._iran_offline = True
	stock_ledger.is_negative_stock_allowed = allowed


def effective_list_rate(server_rate, line: dict) -> float:
	"""The list price a sold rate is compared with: the server's, and the till's own only when the server has none."""
	return max(flt(server_rate) or line["list_rate"], line["rate"])


def build_invoice(sale: dict):
	if not (sale["pos_profile"] and frappe.db.exists("POS Profile", sale["pos_profile"])):
		raise RefusedSale(_("POS Profile {0} does not exist").format(sale["pos_profile"]))
	profile = frappe.get_cached_doc("POS Profile", sale["pos_profile"])
	if profile.get("disabled"):
		raise RefusedSale(_("POS Profile {0} is disabled").format(profile.name))
	if sale["mode"] not in {row.mode_of_payment for row in profile.payments}:
		raise RefusedSale(_("{0} is not a payment mode of {1}").format(sale["mode"], profile.name))

	customer = profile.customer
	if sale["mobile"]:
		from erpnext_iran.pos_customer import customer_for_mobile

		customer = customer_for_mobile(sale["mobile"])["customer"]
	elif sale["customer"] and frappe.db.exists("Customer", sale["customer"]):
		customer = sale["customer"]
	if not customer:
		raise RefusedSale(_("The sale has no customer and the POS Profile has no default one"))

	doc = frappe.new_doc("Sales Invoice")
	doc.update(
		{
			"company": profile.company,
			"customer": customer,
			"is_pos": 1,
			"pos_profile": profile.name,
			"update_stock": 1,
			"set_warehouse": profile.warehouse,
			"cost_center": profile.cost_center,
			"selling_price_list": profile.selling_price_list,
			"currency": profile.currency,
			"set_posting_time": 1,
			"posting_date": sale["sold_at"].date(),
			"posting_time": sale["sold_at"].strftime("%H:%M:%S"),
			"ignore_pricing_rule": 1,
			"offline_sale_id": sale["id"],
			"remarks": _("Sold offline at the till, id {0}").format(sale["id"]),
		}
	)
	for line in sale["items"]:
		doc.append(
			"items",
			{
				"item_code": line["item_code"],
				"qty": line["qty"],
				"warehouse": profile.warehouse,
				"cost_center": profile.cost_center,
			},
		)
	if profile.get("taxes_and_charges"):
		doc.taxes_and_charges = profile.taxes_and_charges
	doc.set_missing_values()

	# The customer paid the price the till showed: keep that rate, and show any difference to the list price as a
	# discount, so the cashier discount limit judges it like any other sale. The list price is the server's own:
	# the till could send any "list price" and make a cut price look like no discount at all.
	for row, line in zip(doc.items, sale["items"], strict=True):
		list_rate = effective_list_rate(row.price_list_rate, line)
		row.price_list_rate = list_rate
		row.discount_percentage = (list_rate - line["rate"]) / list_rate * 100 if list_rate else 0
		row.rate = line["rate"]
	doc.calculate_taxes_and_totals()
	doc.append("payments", {"mode_of_payment": sale["mode"], "amount": flt(doc.rounded_total) or flt(doc.grand_total)})
	return doc

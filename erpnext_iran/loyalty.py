"""Club points: how much of one invoice may be paid with them."""

import frappe
from frappe import _
from frappe.utils import flt


def max_redeem_percent() -> float:
	"""The share (0-100] of an invoice that points may pay. Empty or 0 means no limit."""
	from iran_base.settings import get_setting

	value = flt(get_setting("loyalty_max_redeem_percent", "ERPNext Iran Settings"))
	return value if 0 < value < 100 else 100.0


def validate_redeem_limit(doc, method=None):
	"""Sales Invoice validate: the POS already stops this, the server must too (API, desk form)."""
	if not doc.get("redeem_loyalty_points") or not flt(doc.get("loyalty_amount")):
		return
	percent = max_redeem_percent()
	if percent >= 100:
		return
	total = flt(doc.get("rounded_total") or doc.get("grand_total"))
	allowed = total * percent / 100
	if flt(doc.loyalty_amount) > allowed + 0.5:
		frappe.throw(
			_("Club points can pay at most {0}% of an invoice ({1}). This invoice redeems {2}.").format(
				percent, frappe.format_value(allowed, {"fieldtype": "Currency"}), frappe.format_value(doc.loyalty_amount, {"fieldtype": "Currency"})
			),
			title=_("Club Points Limit"),
		)


@frappe.whitelist()
def points_preview(customer: str, company: str, amount: float) -> dict:
	"""The points a customer would earn on this payment: the same rule as ERPNext applies on submit, which is
	the amount paid in money (points that pay part of the bill earn nothing)."""
	from erpnext.accounts.doctype.loyalty_program.loyalty_program import get_loyalty_program_details_with_points
	from frappe.utils import cint, today

	frappe.has_permission("Customer", doc=customer, throw=True)
	program = frappe.db.get_value("Customer", customer, "loyalty_program")
	if not program:
		return {"points": 0, "tier": None, "enrolled": 0}
	amount = max(0.0, flt(amount))
	details = get_loyalty_program_details_with_points(
		customer,
		loyalty_program=program,  # the function does not look it up on its own for the tier rules
		company=company,
		current_transaction_amount=amount,
		expiry_date=today(),
		include_expired_entry=True,
	)
	return {
		"points": cint(amount / (flt(details.get("collection_factor")) or 1.0)),
		"tier": details.get("tier_name"),
		"enrolled": 1,
	}

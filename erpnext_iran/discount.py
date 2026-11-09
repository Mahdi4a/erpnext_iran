"""A limit on the discount a cashier may give, and a manager who can lift it for one sale.

The limit is on the POS Profile (percent of the listed prices). Discounts made by Pricing Rules are the
shop's own promotions and do not count. Over the limit, the sale needs a manager's approval: the manager types
their user and password on the till, which gives a short-lived token the invoice carries. The check is on
submit, so the cashier can still build the basket freely.
"""

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import flt

MANAGER_ROLES = {"System Manager", "Sales Manager", "Accounts Manager"}
TOKEN_SECONDS = 30 * 60


def is_manager(user: str) -> bool:
	return user == "Administrator" or bool(MANAGER_ROLES & set(frappe.get_roles(user)))


def discount_percent(doc) -> float:
	"""The share of the listed price the customer was given off, leaving out Pricing Rule discounts."""
	listed = given = 0.0
	for row in doc.get("items") or []:
		line = flt(row.get("price_list_rate")) * flt(row.get("qty"))
		listed += line
		if line and not row.get("pricing_rules"):
			given += max(0.0, line - flt(row.get("rate")) * flt(row.get("qty")))
	given += max(0.0, flt(doc.get("discount_amount")))
	return given / listed * 100 if listed else 0.0


def limit_for(doc) -> float:
	"""The cashier's limit (percent); 100 or empty means none."""
	if not (doc.get("is_pos") and doc.get("pos_profile")):
		return 100.0
	value = flt(frappe.db.get_value("POS Profile", doc.pos_profile, "cashier_discount_limit"))
	return value if 0 < value < 100 else 100.0


def token_key(token: str) -> str:
	return f"iran_discount_approval:{token}"


def check_discount(doc, method=None):
	"""Sales Invoice before_submit."""
	limit = limit_for(doc)
	percent = discount_percent(doc)
	if percent <= limit + 0.0001 or is_manager(frappe.session.user):
		return
	approver = doc.get("discount_approval_token") and frappe.cache.get_value(token_key(doc.discount_approval_token))
	if approver:
		doc.discount_approved_by = approver
		return
	frappe.throw(
		_("The discount is {0}%, more than the {1}% a cashier may give. A manager must approve it.").format(
			round(percent, 1), limit
		),
		title=_("Manager Approval Needed"),
	)


@frappe.whitelist()
@rate_limit(limit=10, seconds=300)
def approve_discount(manager: str, password: str) -> dict:
	"""A manager's user and password on the till. Nothing is returned that outlives half an hour."""
	from frappe.utils.password import check_password

	# A wrong password must not be a 401: the desk reads that as an expired session and logs the cashier out.
	manager = (manager or "").strip()
	if not manager or not frappe.db.get_value("User", {"name": manager, "enabled": 1}):
		frappe.throw(_("User or password is wrong"))
	try:
		check_password(manager, password)
	except frappe.AuthenticationError:
		frappe.throw(_("User or password is wrong"))
	if not is_manager(manager):
		frappe.throw(_("{0} is not a manager and cannot approve a discount").format(manager))
	token = frappe.generate_hash(length=24)
	frappe.cache.set_value(token_key(token), manager, expires_in_sec=TOKEN_SECONDS)
	return {"token": token, "user": manager}

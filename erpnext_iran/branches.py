"""One Store Branch makes everything a shop of a chain needs: a warehouse, a cost center, a POS Profile
with the payment modes of an Iranian shop, and optionally its own price list. Nothing that exists is
overwritten, so a branch whose warehouse was made by hand is simply linked."""

from __future__ import annotations

import frappe
from frappe import _

STORES_GROUP_NAMES = ("Stores", "مغازه‌ها")
POS_MODES = ("Cash", "کارت‌خوان")
DEFAULT_MODE = "کارت‌خوان"  # most customers pay by card reader, so the total is already on it when the cashier presses Enter
WALK_IN_CUSTOMER = "مشتری حضوری"

# Settings for a till where a line is waiting: a scan goes straight into the cart, the receipt prints when
# the sale is paid, and "New Invoice" keeps an unfinished sale as a draft (a hold) instead of asking.
FAST_TILL = {
	"auto_add_item_to_cart": 1,
	"skip_submit_confirmation": 1,
	"print_receipt_on_order_complete": 1,
	"action_on_new_invoice": "Save Changes and Load New Invoice",
	"print_format": "Iran POS Receipt",
	"letter_head": "",  # a letterhead does not fit 80 mm paper
}


def create_branch_records(branch):
	"""Fills the warehouse, cost center, price list and POS Profile of a Store Branch before it is saved."""
	company = branch.company
	branch.warehouse = ensure_warehouse(branch.branch_name, company)
	branch.cost_center = ensure_cost_center(branch.branch_name, company)
	branch.price_list = ensure_price_list(branch.branch_name, company, branch.separate_price_list)
	branch.pos_profile = ensure_pos_profile(branch)


def sync_disabled(branch):
	"""A closed branch cannot be sold from: its POS Profile and warehouse are disabled with it."""
	disabled = 1 if branch.disabled else 0
	if branch.pos_profile and frappe.db.get_value("POS Profile", branch.pos_profile, "disabled") != disabled:
		frappe.db.set_value("POS Profile", branch.pos_profile, "disabled", disabled)
	if branch.warehouse and frappe.db.get_value("Warehouse", branch.warehouse, "disabled") != disabled:
		frappe.db.set_value("Warehouse", branch.warehouse, "disabled", disabled)


def ensure_warehouse(name: str, company: str) -> str:
	existing = frappe.db.get_value("Warehouse", {"warehouse_name": name, "company": company})
	if existing:
		return existing

	parent = None
	for group in STORES_GROUP_NAMES:
		parent = frappe.db.get_value("Warehouse", {"warehouse_name": group, "company": company, "is_group": 1})
		if parent:
			break
	warehouse = frappe.new_doc("Warehouse")
	warehouse.update({"warehouse_name": name, "company": company, "parent_warehouse": parent})
	warehouse.flags.ignore_permissions = True
	warehouse.insert()
	return warehouse.name


def ensure_cost_center(name: str, company: str) -> str:
	existing = frappe.db.get_value("Cost Center", {"cost_center_name": name, "company": company})
	if existing:
		return existing

	root = frappe.db.get_value("Cost Center", {"company": company, "parent_cost_center": ["is", "not set"]})
	cost_center = frappe.new_doc("Cost Center")
	cost_center.update({"cost_center_name": name, "company": company, "parent_cost_center": root})
	cost_center.flags.ignore_permissions = True
	cost_center.insert()
	return cost_center.name


def ensure_price_list(name: str, company: str, separate: int | bool) -> str:
	"""The branch's own list, or the head office's Standard Selling when the branch has none."""
	if not separate:
		return "Standard Selling"

	title = _("{0} - Prices").format(name)
	if frappe.db.exists("Price List", title):
		return title

	price_list = frappe.new_doc("Price List")
	price_list.update(
		{
			"price_list_name": title,
			"enabled": 1,
			"selling": 1,
			"currency": frappe.get_cached_value("Company", company, "default_currency"),
		}
	)
	price_list.flags.ignore_permissions = True
	price_list.insert()
	return price_list.name


def ensure_mode_account(mode: str, company: str) -> str | None:
	"""The account a Mode of Payment posts to in this company. Cash takes the company's cash account and the
	other modes its bank account. Returns None when the company has none to give, so the mode is skipped."""
	if not frappe.db.exists("Mode of Payment", mode):
		return None

	account_field = "default_cash_account" if mode == "Cash" else "default_bank_account"
	account = frappe.get_cached_value("Company", company, account_field)
	if not account:
		return None

	doc = frappe.get_doc("Mode of Payment", mode)
	if not any(row.company == company for row in doc.accounts):
		doc.append("accounts", {"company": company, "default_account": account})
		doc.flags.ignore_permissions = True
		doc.save()
	return mode


def ensure_walk_in_customer() -> str:
	"""The customer a sale goes to when the cashier does not ask for a name. Without it the POS refuses to
	add an item until a customer is chosen, which stops the line at the till."""
	if frappe.db.exists("Customer", WALK_IN_CUSTOMER):
		return WALK_IN_CUSTOMER

	customer = frappe.new_doc("Customer")
	customer.update(
		{
			"customer_name": WALK_IN_CUSTOMER,
			"customer_type": "Individual",
			"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}),
			"territory": frappe.db.get_value("Territory", {"is_group": 0}),
		}
	)
	customer.flags.ignore_permissions = True
	customer.insert()
	return customer.name


def keep_walk_in_out_of_loyalty(doc, method=None):
	"""The walk-in customer is everybody and nobody: it must not collect points that the next person in
	the line could spend. ERPNext opts a customer in to an automatic loyalty program on save, so this
	runs after it and takes the customer out again."""
	if doc.get("customer_name") == WALK_IN_CUSTOMER:
		doc.loyalty_program = None
		doc.loyalty_program_tier = None


@frappe.whitelist()
def get_loyalty_programs(customer):
	"""Replaces ERPNext's call of the same name, which the invoice form makes when a customer is chosen and
	which opts the customer in to a loyalty program with a plain database write (so the validation above never
	sees it). The walk-in customer gets no program there either."""
	from erpnext.accounts.doctype.sales_invoice.sales_invoice import get_loyalty_programs as original

	if frappe.db.get_value("Customer", customer, "customer_name") == WALK_IN_CUSTOMER:
		return []
	return original(customer)


def ensure_pos_profile(branch) -> str:
	name = _("{0} - POS").format(branch.branch_name)
	if frappe.db.exists("POS Profile", name):
		if not frappe.db.get_value("POS Profile", name, "customer"):
			frappe.db.set_value("POS Profile", name, "customer", ensure_walk_in_customer())
		return name

	company = frappe.get_cached_doc("Company", branch.company)
	modes = [mode for mode in POS_MODES if ensure_mode_account(mode, branch.company)]
	if not modes:
		frappe.throw(
			_("Company {0} has no default cash or bank account, so the POS cannot take a payment.").format(
				branch.company
			)
		)

	profile = frappe.new_doc("POS Profile")
	profile.update(
		{
			"name": name,
			"company": branch.company,
			"customer": ensure_walk_in_customer(),
			"warehouse": branch.warehouse,
			"cost_center": branch.cost_center,
			"selling_price_list": branch.price_list,
			"currency": company.default_currency,
			"write_off_account": company.write_off_account or company.round_off_account,
			"write_off_cost_center": branch.cost_center,
			"write_off_limit": 0,
			**FAST_TILL,
			"payments": [
				{"mode_of_payment": mode, "default": 1 if mode == DEFAULT_MODE else 0}
				for mode in modes
			],
		}
	)
	profile.flags.ignore_permissions = True
	profile.insert()
	return profile.name

"""One Store Branch makes everything a shop of a chain needs: a warehouse, a cost center, a POS Profile
with the payment modes of an Iranian shop, and optionally its own price list. Nothing that exists is
overwritten, so a branch whose warehouse was made by hand is simply linked."""

from __future__ import annotations

import frappe
from frappe import _

STORES_GROUP_NAMES = ("Stores", "مغازه‌ها")
POS_MODES = ("Cash", "کارت‌خوان")


def create_branch_records(branch):
	"""Fills the warehouse, cost center, price list and POS Profile of a Store Branch before it is saved."""
	company = branch.company
	branch.warehouse = ensure_warehouse(branch.branch_name, company)
	branch.cost_center = ensure_cost_center(branch.branch_name, company)
	branch.price_list = ensure_price_list(branch.branch_name, company, branch.separate_price_list)
	branch.pos_profile = ensure_pos_profile(branch)


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


def ensure_pos_profile(branch) -> str:
	name = _("{0} - POS").format(branch.branch_name)
	if frappe.db.exists("POS Profile", name):
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
			"warehouse": branch.warehouse,
			"cost_center": branch.cost_center,
			"selling_price_list": branch.price_list,
			"currency": company.default_currency,
			"write_off_account": company.write_off_account or company.round_off_account,
			"write_off_cost_center": branch.cost_center,
			"write_off_limit": 0,
			"payments": [
				{"mode_of_payment": mode, "default": 1 if index == 0 else 0}
				for index, mode in enumerate(modes)
			],
		}
	)
	profile.flags.ignore_permissions = True
	profile.insert()
	return profile.name

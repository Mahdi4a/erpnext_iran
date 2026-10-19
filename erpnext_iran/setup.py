from __future__ import annotations

import frappe

DEFAULT_VAT_RATE = 10
TEMPLATE_TITLE = "Iran VAT"
ACCOUNT_NAME = "Value Added Tax"


def vat_rate() -> float:
	"""The VAT percentage. Set `iran_vat_rate` in site_config.json; the law changes, so it is not hard-coded."""
	return float(frappe.conf.get("iran_vat_rate") or DEFAULT_VAT_RATE)


def ensure_vat_account(company: str) -> str | None:
	abbr = frappe.get_cached_value("Company", company, "abbr")
	name = f"{ACCOUNT_NAME} - {abbr}"
	if frappe.db.exists("Account", name):
		return name

	parent = frappe.db.get_value(
		"Account", {"company": company, "account_type": "Tax", "is_group": 1}, "name"
	) or frappe.db.get_value("Account", {"company": company, "account_name": "Duties and Taxes"}, "name")
	if not parent:
		return None

	return (
		frappe.get_doc(
			{
				"doctype": "Account",
				"account_name": ACCOUNT_NAME,
				"parent_account": parent,
				"company": company,
				"account_type": "Tax",
				"is_group": 0,
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def ensure_vat_templates(company: str):
	"""A Sales and a Purchase Taxes template that adds VAT on the net total. Never overwrites an edited one."""
	account = ensure_vat_account(company)
	if not account:
		return

	for doctype in ("Sales Taxes and Charges Template", "Purchase Taxes and Charges Template"):
		if frappe.db.exists(doctype, {"title": TEMPLATE_TITLE, "company": company}):
			continue
		frappe.get_doc(
			{
				"doctype": doctype,
				"title": TEMPLATE_TITLE,
				"company": company,
				"taxes": [
					{
						"charge_type": "On Net Total",
						"account_head": account,
						"description": "VAT",
						"rate": vat_rate(),
					}
				],
			}
		).insert(ignore_permissions=True)


def on_company_update(doc, method=None):
	"""A company made after this app was installed gets the VAT templates as well.

	The chart of accounts is created while the company is saved, so this runs after it and
	does nothing when there is no tax account to hang the template on yet.
	"""
	ensure_vat_templates(doc.name)

"""Makes the Iran chart of accounts selectable when a company is created.

ERPNext only looks for chart templates in its own folders, so the lookup functions are wrapped
here instead of copying the JSON into ERPNext. `get_chart` is called from Python while the
company is saved, so it is wrapped once per process; `get_charts_for_country` is called from the
company form and is replaced through `override_whitelisted_methods`.
"""

from __future__ import annotations

import json
from pathlib import Path

import frappe

CHART_NAME = "Iran - Chart of Accounts"
CHART_FILE = Path(__file__).parent / "charts" / "ir_chart_of_accounts.json"


def load_chart() -> dict:
	return json.loads(CHART_FILE.read_text(encoding="utf-8"))


def patch_get_chart():
	"""Teach ERPNext's `get_chart` about the Iran chart. Safe to call many times."""
	from erpnext.accounts.doctype.account.chart_of_accounts import chart_of_accounts

	original = chart_of_accounts.get_chart
	if getattr(original, "_erpnext_iran", False):
		return

	def get_chart(chart_template, existing_company=None):
		if chart_template == CHART_NAME and not existing_company:
			return load_chart()["tree"]
		return original(chart_template, existing_company)

	get_chart._erpnext_iran = True
	# Whitelisted like the original, so the chart importer page can still call it.
	chart_of_accounts.get_chart = frappe.whitelist()(get_chart)


@frappe.whitelist()
def get_charts_for_country(country, with_standard=False):
	from erpnext.accounts.doctype.account.chart_of_accounts import chart_of_accounts

	patch_get_chart()
	charts = chart_of_accounts.get_charts_for_country(country, with_standard)
	if country == "Iran" and CHART_NAME not in charts:
		charts.insert(0, CHART_NAME)
	return charts


def before_company_save(doc, method=None):
	"""Runs before ERPNext creates the accounts, which is when `get_chart` is used."""
	if doc.get("chart_of_accounts") == CHART_NAME:
		patch_get_chart()

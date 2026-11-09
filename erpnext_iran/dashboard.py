"""The shop manager's dashboard: today's takings, the month, branches, best sellers and low stock, on one page.

Everything is a standard Frappe Number Card / Dashboard Chart on a public Workspace, so the manager can move,
resize or add to it from the desk. They are made again (not overwritten when they already exist and were
edited) on migrate."""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import cint

WORKSPACE = "Shop Dashboard"
TODAY = "frappe.datetime.get_today()"
MONTH = "frappe.datetime.month_start()"
THIS_MONTH = f"[{MONTH}, {TODAY}]"  # one JS expression: Between takes a single value that is a list
ROLES = ("Sales Manager", "Accounts Manager", "System Manager", "Stock Manager")


@frappe.whitelist()
def low_stock_count() -> int:
	"""Items that are out of stock or at/below their safety stock in some warehouse (Number Card method).
	A plain number: an object makes the card format it as money."""
	row = frappe.db.sql(
		"""select count(*) from `tabBin` bin
		join `tabItem` item on item.name = bin.item_code
		where item.disabled = 0 and item.is_stock_item = 1 and bin.actual_qty <= ifnull(item.safety_stock, 0)"""
	)
	return cint(row[0][0])


NUMBER_CARDS = [
	{
		"label": "Today's Sales",
		"document_type": "Sales Invoice",
		"function": "Sum",
		"aggregate_function_based_on": "base_grand_total",
		"filters": [["Sales Invoice", "docstatus", "=", 1]],
		"dynamic": [["Sales Invoice", "posting_date", "=", TODAY]],
		"color": "#29CD42",
		"show_percentage_stats": 1,
		"stats_time_interval": "Daily",
	},
	{
		"label": "Today's Invoices",
		"document_type": "Sales Invoice",
		"function": "Count",
		"filters": [["Sales Invoice", "docstatus", "=", 1], ["Sales Invoice", "is_return", "=", 0]],
		"dynamic": [["Sales Invoice", "posting_date", "=", TODAY]],
		"color": "#449CF0",
		"show_percentage_stats": 1,
		"stats_time_interval": "Daily",
	},
	{
		"label": "This Month's Sales",
		"document_type": "Sales Invoice",
		"function": "Sum",
		"aggregate_function_based_on": "base_grand_total",
		"filters": [["Sales Invoice", "docstatus", "=", 1]],
		"dynamic": [["Sales Invoice", "posting_date", "Between", THIS_MONTH]],
		"color": "#29CD42",
		"show_percentage_stats": 1,
		"stats_time_interval": "Monthly",
	},
	{
		"label": "Returns Today",
		"document_type": "Sales Invoice",
		"function": "Count",
		"filters": [["Sales Invoice", "docstatus", "=", 1], ["Sales Invoice", "is_return", "=", 1]],
		"dynamic": [["Sales Invoice", "posting_date", "=", TODAY]],
		"color": "#FF5858",
	},
	{
		"label": "Online Orders Today",
		"document_type": "Sales Order",
		"function": "Count",
		"filters": [["Sales Order", "docstatus", "=", 1], ["Sales Order", "sales_channel", "in", ["Website", "Instagram", "Telegram", "WhatsApp", "Phone"]]],
		"dynamic": [["Sales Order", "transaction_date", "=", TODAY]],
		"color": "#7575ff",
	},
	{"label": "Low Stock Items", "type": "Custom", "method": "erpnext_iran.dashboard.low_stock_count", "color": "#FFA00A"},
]

CHARTS = [
	{
		"chart_name": "Sales, Last 30 Days",
		"chart_type": "Sum",
		"document_type": "Sales Invoice",
		"based_on": "posting_date",
		"value_based_on": "base_grand_total",
		"timespan": "Last Month",
		"time_interval": "Daily",
		"timeseries": 1,
		"filters": [["Sales Invoice", "docstatus", "=", 1]],
		"type": "Line",
		"color": "#29CD42",
	},
	{
		"chart_name": "Sales by Branch, This Month",
		"chart_type": "Group By",
		"document_type": "Sales Invoice",
		"group_by_type": "Sum",
		"group_by_based_on": "cost_center",
		"aggregate_function_based_on": "base_grand_total",
		"number_of_groups": 12,
		"filters": [["Sales Invoice", "docstatus", "=", 1], ["Sales Invoice", "cost_center", "is", "set"]],
		"dynamic": [["Sales Invoice", "posting_date", "Between", THIS_MONTH]],
		"type": "Bar",
	},
	{
		"chart_name": "Best Selling Items, This Month",
		"chart_type": "Group By",
		"document_type": "Sales Invoice Item",
		"parent_document_type": "Sales Invoice",
		"group_by_type": "Sum",
		"group_by_based_on": "item_name",
		"aggregate_function_based_on": "base_net_amount",
		"number_of_groups": 10,
		"filters": [["Sales Invoice Item", "docstatus", "=", 1]],
		"dynamic": [["Sales Invoice Item", "creation", "Between", THIS_MONTH]],
		"type": "Bar",
	},
	{
		"chart_name": "Sales by Channel, This Month",
		"chart_type": "Group By",
		"document_type": "Sales Order",
		"group_by_type": "Sum",
		"group_by_based_on": "sales_channel",
		"aggregate_function_based_on": "base_grand_total",
		"number_of_groups": 8,
		"filters": [["Sales Order", "docstatus", "=", 1]],
		"dynamic": [["Sales Order", "transaction_date", "Between", THIS_MONTH]],
		"type": "Donut",
	},
]


def _block(kind: str, name: str, col: int, key: str) -> dict:
	return {"id": frappe.generate_hash(length=10), "type": kind, "data": {key: name, "col": col}}


def ensure_number_card(spec: dict) -> str:
	name = spec["label"]
	if frappe.db.exists("Number Card", name):
		return name
	card = frappe.new_doc("Number Card")
	card.update(
		{
			"label": name,
			"type": spec.get("type", "Document Type"),
			"is_public": 1,
			"show_percentage_stats": spec.get("show_percentage_stats", 0),
			"stats_time_interval": spec.get("stats_time_interval", "Daily"),
			"color": spec.get("color"),
			"method": spec.get("method"),
			"document_type": spec.get("document_type"),
			"function": spec.get("function"),
			"aggregate_function_based_on": spec.get("aggregate_function_based_on"),
			"filters_json": json.dumps(spec.get("filters", [])),
			"dynamic_filters_json": json.dumps(spec.get("dynamic", [])),
		}
	)
	card.flags.ignore_permissions = True
	card.insert()
	# Frappe fills the company currency in; only the money cards should show it
	money = spec.get("function") in ("Sum", "Average") and spec.get("type", "Document Type") == "Document Type"
	frappe.db.set_value("Number Card", card.name, "currency", card.currency if money else "")
	return card.name


def ensure_chart(spec: dict) -> str:
	name = spec["chart_name"]
	if frappe.db.exists("Dashboard Chart", name):
		return name
	chart = frappe.new_doc("Dashboard Chart")
	data = {k: v for k, v in spec.items() if k not in ("filters", "dynamic")}
	chart.update(data)
	chart.is_public = 1
	chart.filters_json = json.dumps(spec.get("filters", []))
	chart.dynamic_filters_json = json.dumps(spec.get("dynamic", []))
	for role in ROLES:
		chart.append("roles", {"role": role})
	chart.flags.ignore_permissions = True
	chart.insert()
	return chart.name


def ensure_dashboard():
	"""Cards, charts and the workspace that shows them. Safe to run again; existing ones are left as edited."""
	if not frappe.db.exists("DocType", "Sales Invoice") or not frappe.get_meta("Sales Order").has_field("sales_channel"):
		return
	cards = [ensure_number_card(spec) for spec in NUMBER_CARDS]
	charts = [ensure_chart(spec) for spec in CHARTS]

	if frappe.db.exists("Workspace", WORKSPACE):
		return
	content = [
		{"id": frappe.generate_hash(length=10), "type": "header", "data": {"text": f'<span class="h4"><b>{_("Shop Dashboard")}</b></span>', "col": 12}},
	]
	content += [_block("number_card", card, 4, "number_card_name") for card in cards]
	content += [_block("chart", chart, 6, "chart_name") for chart in charts]
	content.append({"id": frappe.generate_hash(length=10), "type": "header", "data": {"text": f'<span class="h5"><b>{_("Shortcuts")}</b></span>', "col": 12}})
	shortcuts = [
		("Point of Sale", "Page", "point-of-sale"),
		("Branch Profit", "Report", "Branch Profit"),
		("Sales Invoice", "DocType", "Sales Invoice"),
		("Sales Order", "DocType", "Sales Order"),
		("Item", "DocType", "Item"),
	]
	content += [_block("shortcut", label, 3, "shortcut_name") for label, _t, _l in shortcuts]

	workspace = frappe.new_doc("Workspace")
	workspace.update({"label": WORKSPACE, "title": WORKSPACE, "public": 1, "module": "Erpnext Iran", "content": json.dumps(content), "icon": "chart"})
	for card in cards:
		workspace.append("number_cards", {"label": card, "number_card_name": card})
	for chart in charts:
		workspace.append("charts", {"label": chart, "chart_name": chart})
	for label, kind, target in shortcuts:
		row = {"label": label, "type": kind, "link_to": target}
		if kind == "Report":
			row["report_ref_doctype"] = "Sales Invoice"
		if kind == "DocType":
			row["doc_view"] = "List"
		workspace.append("shortcuts", row)
	for role in ROLES:
		workspace.append("roles", {"role": role})
	workspace.flags.ignore_permissions = True
	workspace.insert()

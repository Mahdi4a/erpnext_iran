"""Sharing a cost that belongs to everybody (head office rent, advertising, the accountant) between the branches.

ERPNext does the sharing itself: a submitted Cost Center Allocation tells it to split what is booked to a "main"
cost centre among others by percentage, from a date on. What it does not do is work the percentages out. This
suggests them from each branch's share of the sales in a period, which is the usual fair rule for a chain.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt


def distribute(amounts: dict[str, float]) -> dict[str, float]:
	"""Percentages with two decimals that add up to exactly 100 (largest remainder), or an equal split when
	nobody sold anything."""
	if not amounts:
		return {}
	total = sum(max(flt(v), 0) for v in amounts.values())
	weights = {k: (max(flt(v), 0) / total if total else 1 / len(amounts)) for k, v in amounts.items()}
	cents = {k: int(w * 10000) for k, w in weights.items()}
	short = 10000 - sum(cents.values())
	for key in sorted(weights, key=lambda k: weights[k] * 10000 - cents[k], reverse=True)[:short]:
		cents[key] += 1
	return {k: v / 100 for k, v in cents.items()}


def branch_sales(company: str, from_date, to_date, exclude: str | None = None) -> dict[str, float]:
	"""Net sales of every open branch of the company in the period, by cost centre (zero included)."""
	centres = [
		cost_center
		for cost_center in frappe.get_all("Store Branch", {"company": company, "disabled": 0}, pluck="cost_center")
		if cost_center and cost_center != exclude
	]
	if not centres:
		return {}
	sales = dict.fromkeys(centres, 0.0)
	for row in frappe.db.sql(
		"""select item.cost_center, sum(item.base_net_amount) as net
		from `tabSales Invoice Item` item join `tabSales Invoice` si on si.name = item.parent
		where si.docstatus = 1 and si.company = %(company)s and si.posting_date between %(from_date)s and %(to_date)s
			and item.cost_center in %(centres)s group by item.cost_center""",
		{"company": company, "from_date": from_date, "to_date": to_date, "centres": tuple(centres)},
		as_dict=True,
	):
		sales[row.cost_center] = flt(row.net)
	return sales


@frappe.whitelist()
def suggest_sales_share(company: str, main_cost_center: str, from_date: str, to_date: str) -> list[dict]:
	"""[{cost_center, sales, percentage}] for the branches with sales in the period."""
	frappe.has_permission("Cost Center Allocation", "read", throw=True)
	if frappe.db.get_value("Cost Center", main_cost_center, "company") != company:
		frappe.throw(_("The main cost centre {0} does not belong to {1}").format(main_cost_center, company))
	sales = branch_sales(company, from_date, to_date, exclude=main_cost_center)
	if not sales:
		frappe.throw(_("{0} has no open branch other than the main cost centre").format(company))
	earning = {cc: v for cc, v in sales.items() if v > 0} or sales  # a branch that sold nothing pays nothing
	share = distribute(earning)
	return [{"cost_center": cc, "sales": earning[cc], "percentage": share[cc]} for cc in share]


@frappe.whitelist(methods=["POST"])
def make_allocation(main_cost_center: str, valid_from: str, from_date: str, to_date: str) -> str:
	"""A draft Cost Center Allocation with the suggested percentages, to be looked at and submitted."""
	frappe.has_permission("Cost Center Allocation", "create", throw=True)
	company = frappe.db.get_value("Cost Center", main_cost_center, "company")
	if not company:
		frappe.throw(_("Cost centre {0} does not exist").format(main_cost_center))
	# ERPNext lets two allocations of one cost centre start on the same day, and then it is anybody's guess which
	# one splits the cost
	if frappe.db.exists("Cost Center Allocation", {"main_cost_center": main_cost_center, "valid_from": valid_from, "docstatus": ["<", 2]}):
		frappe.throw(_("{0} already has an allocation starting on {1}. Change that one or pick another date.").format(main_cost_center, valid_from))
	doc = frappe.new_doc("Cost Center Allocation")
	doc.update({"company": company, "main_cost_center": main_cost_center, "valid_from": valid_from})
	for row in suggest_sales_share(company, main_cost_center, from_date, to_date):
		doc.append("allocation_percentages", {"cost_center": row["cost_center"], "percentage": row["percentage"]})
	doc.insert()
	return doc.name

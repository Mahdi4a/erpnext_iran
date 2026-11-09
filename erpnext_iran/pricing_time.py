"""Pricing Rules that only apply on some days of the week and some hours of the day.

ERPNext rules have a date range only. A shop wants "dairy -10% from 10 to 12" or "Thursdays -5%". The rule gets
day check boxes and a from/to time; empty means always. Rules are filtered when ERPNext picks the rules for an
item, so the POS, the order form and the API all behave the same.
"""

from datetime import datetime, time, timedelta

import frappe
from frappe import _

# check box fieldname -> datetime.weekday() (Monday 0 .. Sunday 6), in the order of the Persian week
DAYS = (
	("iran_sat", 5, "Saturday"),
	("iran_sun", 6, "Sunday"),
	("iran_mon", 0, "Monday"),
	("iran_tue", 1, "Tuesday"),
	("iran_wed", 2, "Wednesday"),
	("iran_thu", 3, "Thursday"),
	("iran_fri", 4, "Friday"),
)


def _as_time(value) -> time | None:
	if value in (None, "", 0):
		return None
	if isinstance(value, timedelta):
		seconds = int(value.total_seconds()) % 86400
		return time(seconds // 3600, seconds % 3600 // 60, seconds % 60)
	if isinstance(value, time):
		return value
	return datetime.strptime(str(value).split(".")[0], "%H:%M:%S").time()


def rule_applies(rule, moment: datetime) -> bool:
	"""True when the rule has no day or hour limit, or the moment is inside them."""
	days = [weekday for field, weekday, _day in DAYS if rule.get(field)]
	if days and moment.weekday() not in days:
		return False

	start, end = _as_time(rule.get("iran_from_time")), _as_time(rule.get("iran_to_time"))
	if not start and not end:
		return True
	now = moment.time()
	if start and end and start > end:  # a night window, 22:00 to 02:00
		return now >= start or now < end
	return (not start or now >= start) and (not end or now < end)


def _moment(doc) -> datetime:
	"""The invoice's own date and time when it has them and is not today's, else now."""
	now = frappe.utils.now_datetime()
	posting_date = doc and doc.get("posting_date")
	if not posting_date or frappe.utils.getdate(posting_date) == now.date():
		return now
	posting_time = _as_time(doc.get("posting_time")) or time(0, 0)
	return datetime.combine(frappe.utils.getdate(posting_date), posting_time)


def install(*args, **kwargs):
	"""Put the day/hour check behind ERPNext's own rule filter. Safe to call again."""
	from erpnext.accounts.doctype.pricing_rule import utils

	if getattr(utils.filter_pricing_rule_based_on_condition, "_iran_time", False):
		return
	original = utils.filter_pricing_rule_based_on_condition

	def filtered(pricing_rules, doc=None):
		rules = original(pricing_rules, doc)
		moment = _moment(doc)
		return [rule for rule in rules if rule_applies(rule, moment)]

	filtered._iran_time = True
	utils.filter_pricing_rule_based_on_condition = filtered


def validate_pricing_rule(doc, method=None):
	if doc.get("iran_from_time") and doc.get("iran_to_time") and doc.iran_from_time == doc.iran_to_time:
		frappe.throw(_("From Time and To Time of a Pricing Rule cannot be the same"))


install()

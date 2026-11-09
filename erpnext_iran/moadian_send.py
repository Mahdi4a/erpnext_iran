"""Send a Sales Invoice to Moadian and follow what the tax authority made of it."""

from __future__ import annotations

import json

import frappe
from frappe.model.naming import getseries
from frappe.utils import get_datetime, now_datetime

from erpnext_iran import moadian
from erpnext_iran.moadian_client import MoadianClient
from erpnext_iran.moadian_taxid import tax_id

STATUS_OF_RESULT = {"SUCCESS": "Accepted", "FAILED": "Rejected"}


def next_serial(memory_id: str) -> int:
	"""One counter per tax memory: the serial is part of the tax ID, so it never repeats."""
	return int(getseries(f"MOADIAN-{memory_id}-", 10))


def error_text(result: dict) -> str:
	messages = [f"{item['code']}: {item['message']}" for item in (result.get("data") or {}).get("error", [])]
	return "\n".join(messages)


@frappe.whitelist()
def send_invoice(invoice_name: str) -> str:
	invoice = frappe.get_doc("Sales Invoice", invoice_name)
	invoice.check_permission("write")
	if invoice.docstatus != 1 or invoice.moadian_status in ("Sent", "Accepted"):
		frappe.throw("Only a submitted invoice that was not sent yet can go to Moadian.")
	data = moadian.get_payload(invoice_name)
	if data["missing"]:
		frappe.throw("<br>".join(data["missing"]), title="Missing Moadian data")

	memory_id = frappe.get_cached_value("Company", invoice.company, "moadian_memory_id")
	invoice.moadian_serial = invoice.moadian_serial or next_serial(memory_id)
	payload = data["payload"]
	payload.pop("unverified", None)
	payload["header"]["taxid"] = tax_id(memory_id, payload["header"]["indatim"], invoice.moadian_serial)
	payload["header"]["inno"] = str(invoice.moadian_serial)

	_, reference_number = MoadianClient(invoice.company).send(payload)
	invoice.db_set(
		{
			"moadian_serial": invoice.moadian_serial,
			"moadian_tax_id": payload["header"]["taxid"],
			"moadian_reference_number": reference_number,
			"moadian_status": "Sent",
			"moadian_sent_at": now_datetime(),
			"moadian_errors": "",
		}
	)
	return reference_number


def cancellation_payload(invoice, serial: int) -> dict:
	"""Subject 3: names the invoice it cancels and carries no items (RC_IITP.IS_V7.9, section 5-3)."""
	original = moadian.get_payload(invoice.name)["payload"]["header"]
	header = {
		"indatim": moadian.to_millis(now_datetime().date(), now_datetime().time()),
		"inty": original["inty"],
		"inno": str(serial),
		"inp": original["inp"],
		"ins": 3,
		"tins": original["tins"],
		"irtaxid": invoice.moadian_tax_id,
	}
	return {"header": header, "body": [], "payments": []}


@frappe.whitelist()
def cancel_in_moadian(invoice_name: str) -> str:
	"""Tell Moadian that an invoice it accepted is void. Run it after the invoice is cancelled."""
	invoice = frappe.get_doc("Sales Invoice", invoice_name)
	invoice.check_permission("write")
	if invoice.moadian_status != "Accepted" or invoice.moadian_cancel_tax_id:
		frappe.throw("Only an invoice Moadian accepted, and not yet cancelled there, can be cancelled.")
	memory_id = frappe.get_cached_value("Company", invoice.company, "moadian_memory_id")
	payload = cancellation_payload(invoice, next_serial(memory_id))
	payload["header"]["taxid"] = tax_id(memory_id, payload["header"]["indatim"], int(payload["header"]["inno"]))
	_, reference_number = MoadianClient(invoice.company).send(payload)
	invoice.db_set(
		{"moadian_cancel_tax_id": payload["header"]["taxid"], "moadian_cancel_reference_number": reference_number}
	)
	return reference_number


def cancel_after_erp_cancel(doc, event=None):
	"""Hook: an invoice Moadian accepted is cancelled there too, in the background."""
	if doc.get("moadian_status") == "Accepted":
		frappe.enqueue(cancel_in_moadian, invoice_name=doc.name, enqueue_after_commit=True)


@frappe.whitelist()
def check_status(invoice_name: str) -> str:
	invoice = frappe.get_doc("Sales Invoice", invoice_name)
	invoice.check_permission("read")
	result = MoadianClient(invoice.company).inquire(
		invoice.moadian_reference_number, get_datetime(invoice.moadian_sent_at)
	)
	status = STATUS_OF_RESULT.get(result["status"], "Sent")
	invoice.db_set({"moadian_status": status, "moadian_errors": error_text(result)})
	return status


def auto_send_on_submit(doc, event=None):
	"""Hook: send in the background when the company asked for it."""
	if doc.get("moadian_enabled") and frappe.get_cached_value("Company", doc.company, "moadian_auto_send"):
		frappe.enqueue(auto_send, invoice_name=doc.name, enqueue_after_commit=True)


def auto_send(invoice_name: str):
	"""Send; on failure keep the reason on the invoice so the user sees it and the hourly job retries."""
	try:
		send_invoice(invoice_name)
	except Exception as error:
		frappe.db.set_value("Sales Invoice", invoice_name, "moadian_errors", str(error)[:1000])
		frappe.log_error(title=f"Moadian send of {invoice_name}")


def retry_unsent_invoices():
	"""Invoices of the last week that never got through, for the companies that send by themselves."""
	companies = frappe.get_all("Company", {"moadian_enabled": 1, "moadian_auto_send": 1}, pluck="name")
	names = frappe.get_all(
		"Sales Invoice",
		{
			"docstatus": 1,
			"company": ("in", companies),
			"moadian_status": "Not Sent",
			"posting_date": (">", frappe.utils.add_days(now_datetime(), -7)),
		},
		pluck="name",
	)
	for name in names:
		auto_send(name)


def check_sent_invoices():
	"""Hourly: ask about every invoice Moadian has not answered yet. A week is the API's reach."""
	names = frappe.get_all(
		"Sales Invoice",
		{"moadian_status": "Sent", "moadian_sent_at": (">", frappe.utils.add_days(now_datetime(), -7))},
		pluck="name",
	)
	for name in names:
		try:
			check_status(name)
		except Exception:
			frappe.log_error(title=f"Moadian status of {name}")
	retry_unsent_invoices()

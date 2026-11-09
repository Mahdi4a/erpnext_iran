"""The customer of a shop sale is asked for last: after the goods are rung up and the total is said,
the cashier asks for a mobile number. This finds the customer of that number, or makes one."""

import frappe
from frappe import _
from iran_base.utils.sms import try_normalize_mobile


def find_customer(number: str) -> str | None:
	return frappe.db.get_value("Customer", {"mobile_no": number, "disabled": 0}, "name") or (
		number if frappe.db.exists("Customer", {"name": number, "disabled": 0}) else None
	)


@frappe.whitelist(methods=["POST"])
def customer_for_mobile(mobile: str) -> dict:
	frappe.has_permission("Customer", "read", throw=True)  # finding a customer by mobile shows whether they exist
	number = try_normalize_mobile(mobile)
	if not number:
		frappe.throw(_("{0} is not a valid mobile number").format(frappe.bold(mobile)))

	if name := find_customer(number):
		return {"customer": name, "created": 0}

	frappe.has_permission("Customer", "create", throw=True)
	customer = frappe.new_doc("Customer")
	customer.customer_name = number
	customer.customer_type = "Individual"
	customer.customer_group = frappe.db.get_single_value("Selling Settings", "customer_group") or "Individual"
	customer.territory = frappe.db.get_single_value("Selling Settings", "territory") or "All Territories"
	customer.insert()

	contact = frappe.new_doc("Contact")
	contact.first_name = number
	contact.append("phone_nos", {"phone": number, "is_primary_mobile_no": 1})
	contact.append("links", {"link_doctype": "Customer", "link_name": customer.name})
	contact.flags.ignore_permissions = True
	contact.insert()
	frappe.db.set_value("Customer", customer.name, "mobile_no", number)  # so the next search by mobile finds it
	return {"customer": customer.name, "created": 1}

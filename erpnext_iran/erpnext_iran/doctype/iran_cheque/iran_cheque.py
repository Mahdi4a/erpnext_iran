import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, today
from iran_base.utils.numbers import to_latin_digits

from erpnext_iran import cheques

LOCKED_AFTER_SUBMIT = ("cheque_type", "company", "amount", "party_type", "party")


class IranCheque(Document):
	def validate(self):
		self.sayad_id = to_latin_digits(self.sayad_id or "").strip()
		if self.sayad_id and not (self.sayad_id.isdigit() and len(self.sayad_id) == 16):
			frappe.throw(_("Sayad ID must be 16 digits"), title=_("Invalid Cheque"))
		if (self.cheque_type == "Received") != (self.party_type == "Customer"):
			frappe.throw(
				_("A received cheque comes from a Customer and an issued cheque goes to a Supplier"),
				title=_("Invalid Cheque"),
			)
		if self.amount is None or self.amount <= 0:
			frappe.throw(_("Amount must be greater than zero"), title=_("Invalid Cheque"))
		if getdate(self.due_date) < getdate(self.issue_date):
			frappe.throw(_("Due Date cannot be before Issue Date"), title=_("Invalid Cheque"))

	def on_submit(self):
		self.db_set("status", cheques.INITIAL_STATUS[self.cheque_type])
		self.add_posting("submit", cheques.post(self, "submit", self.issue_date))

	def before_cancel(self):
		if self.status not in cheques.INITIAL_STATUS.values():
			frappe.throw(
				_("A cheque that is {0} cannot be cancelled. Post the next step instead.").format(_(self.status)),
				title=_("Not Allowed"),
			)

	def on_cancel(self):
		# Read from the database: the postings are added without saving this document
		for name in frappe.get_all("Iran Cheque Posting", {"parent": self.name}, pluck="journal_entry"):
			journal_entry = frappe.get_doc("Journal Entry", name)
			if journal_entry.docstatus == 1:
				journal_entry.cancel()
		self.db_set("status", "Cancelled")

	def add_posting(self, status_label, journal_entry):
		frappe.get_doc(
			{
				"doctype": "Iran Cheque Posting",
				"parent": self.name,
				"parenttype": "Iran Cheque",
				"parentfield": "postings",
				"status": status_label,
				"posting_date": today(),
				"journal_entry": journal_entry,
			}
		).insert(ignore_permissions=True)

	def apply_action(self, action, posting_date=None, bank_account=None, endorsed_to=None):
		if self.docstatus != 1:
			frappe.throw(_("Submit the cheque first"), title=_("Not Allowed"))
		new_status = cheques.next_status(self.cheque_type, self.status, action)

		if action == "clear" and not (bank_account or self.bank_account):
			frappe.throw(_("Choose the Bank Account the cheque is cleared in"), title=_("Bank Account Missing"))
		if action == "endorse" and not endorsed_to:
			frappe.throw(_("Choose the Supplier the cheque is endorsed to"), title=_("Supplier Missing"))

		bank_account = bank_account or self.bank_account
		journal_entry = cheques.post(self, action, posting_date, bank_account, endorsed_to)

		updates = {"status": new_status}
		if bank_account and action == "clear":
			updates["bank_account"] = bank_account
		if endorsed_to:
			updates["endorsed_to"] = endorsed_to
		self.db_set(updates)
		self.add_posting(new_status, journal_entry)
		return journal_entry


@frappe.whitelist()
def make_action(name: str, action: str, posting_date=None, bank_account=None, endorsed_to=None):
	cheque = frappe.get_doc("Iran Cheque", name)
	cheque.check_permission("submit")
	journal_entry = cheque.apply_action(action, posting_date, bank_account, endorsed_to)
	return {"status": cheque.status, "journal_entry": journal_entry}

import frappe
from frappe import _
from frappe.model.document import Document


class MallTurnover(Document):
	def validate(self):
		if not 1 <= int(self.jalali_month or 0) <= 12:
			frappe.throw(_("The month is from 1 (Farvardin) to 12 (Esfand)"))
		if (self.turnover or 0) < 0:
			frappe.throw(_("The turnover cannot be negative"))
		if frappe.db.get_value("Mall Lease", self.lease, "docstatus") != 1:
			frappe.throw(_("Turnover is entered against a submitted lease"))
		if frappe.db.exists("Mall Turnover", {"lease": self.lease, "jalali_year": self.jalali_year, "jalali_month": self.jalali_month, "name": ["!=", self.name or ""]}):
			frappe.throw(_("The turnover of that month is already entered for this lease"))

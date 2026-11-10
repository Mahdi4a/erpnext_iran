import frappe
from frappe import _
from frappe.model.document import Document


class MallUnit(Document):
	def validate(self):
		if (self.area or 0) <= 0:
			frappe.throw(_("The area must be more than zero"))

import frappe
from frappe.model.document import Document

from erpnext_iran import mall


class MallLease(Document):
	def validate(self):
		mall.validate_lease(self)

	def on_submit(self):
		mall.on_lease_change(self)

	def on_cancel(self):
		mall.on_lease_change(self)

	def on_update_after_submit(self):
		mall.on_lease_change(self)

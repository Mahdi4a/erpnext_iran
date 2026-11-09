import frappe
from frappe.model.document import Document

from erpnext_iran.payments import save_dollar_rate


class ERPNextIranSettings(Document):
	def on_update(self):
		if self.usd_rate_irr and self.has_value_changed("usd_rate_irr"):
			save_dollar_rate(self.usd_rate_irr)

		from erpnext_iran.grocery import on_settings_update

		on_settings_update(self)

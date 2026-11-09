from frappe.model.document import Document

from erpnext_iran import tara


class TaraSettings(Document):
	"""The methods Payment Request calls on the controller of a payment gateway."""

	def validate_transaction_currency(self, currency):
		tara.validate_currency(currency)

	def get_payment_url(self, **kwargs):
		return tara.get_payment_url(self, **kwargs)

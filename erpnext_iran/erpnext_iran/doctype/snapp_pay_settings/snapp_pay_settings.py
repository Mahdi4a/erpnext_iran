from frappe.model.document import Document

from erpnext_iran import snapppay


class SnappPaySettings(Document):
	"""The methods Payment Request calls on the controller of a payment gateway."""

	def validate_transaction_currency(self, currency):
		snapppay.validate_currency(currency)

	def get_payment_url(self, **kwargs):
		return snapppay.get_payment_url(self, **kwargs)

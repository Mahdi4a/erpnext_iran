from frappe.model.document import Document

from erpnext_iran import zarinpal


class ZarinpalSettings(Document):
	"""The methods Payment Request calls on the controller of a payment gateway."""

	def validate_transaction_currency(self, currency):
		zarinpal.validate_currency(currency)

	def get_payment_url(self, **kwargs):
		return zarinpal.get_payment_url(self, **kwargs)

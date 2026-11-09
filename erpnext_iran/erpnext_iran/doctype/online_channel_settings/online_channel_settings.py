import frappe
from frappe.model.document import Document
from frappe.utils import get_url


class OnlineChannelSettings(Document):
	def validate(self):
		if not self.get_password("catalog_token", raise_exception=False):
			self.catalog_token = frappe.generate_hash(length=32)
		token = self.get_password("catalog_token", raise_exception=False) or self.catalog_token
		self.catalog_url = get_url(f"/api/method/erpnext_iran.channels.catalog_feed?token={token}")
		self.woo_webhook_url = get_url("/api/method/erpnext_iran.woocommerce.webhook")

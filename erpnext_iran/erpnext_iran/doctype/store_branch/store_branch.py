from frappe.model.document import Document

from erpnext_iran.branches import create_branch_records, sync_disabled


class StoreBranch(Document):
	def before_insert(self):
		create_branch_records(self)

	def on_update(self):
		sync_disabled(self)

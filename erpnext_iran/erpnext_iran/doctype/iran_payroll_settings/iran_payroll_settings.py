from frappe.model.document import Document


class IranPayrollSettings(Document):
	def validate(self):
		import frappe
		from frappe import _

		years = [row.jalali_year for row in self.years]
		if len(years) != len(set(years)):
			frappe.throw(_("A year is listed twice in Rates by Year"))

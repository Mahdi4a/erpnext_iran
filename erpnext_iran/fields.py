"""Custom fields added next to ERPNext's own, so no core DocType is changed."""

PARTY_FIELDS = [
	{
		"fieldname": "iran_section",
		"label": "Iran Tax Identifiers",
		"fieldtype": "Section Break",
		"insert_after": "tax_category",
		"collapsible": 0,
	},
	{
		"fieldname": "national_id",
		"label": "National ID (کد ملی)",
		"fieldtype": "Data",
		"insert_after": "iran_section",
		"description": "10 digits, for an individual",
	},
	{
		"fieldname": "legal_id",
		"label": "Legal ID (شناسه ملی)",
		"fieldtype": "Data",
		"insert_after": "national_id",
		"description": "11 digits, for a company",
	},
	{
		"fieldname": "economic_code",
		"label": "Economic Code (کد اقتصادی)",
		"fieldtype": "Data",
		"insert_after": "legal_id",
		"description": "12 or 14 digits",
	},
]

BANK_FIELDS = [
	{
		"fieldname": "sheba_code",
		"label": "Sheba Bank Code (کد بانک در شبا)",
		"fieldtype": "Data",
		"insert_after": "bank_name",
		"length": 3,
		"unique": 1,
		"description": "The three digits after IR and the two check digits of a Sheba",
	},
]

PROVINCES = [
	"آذربایجان شرقی", "آذربایجان غربی", "اردبیل", "اصفهان", "البرز", "ایلام", "بوشهر", "تهران",
	"چهارمحال و بختیاری", "خراسان جنوبی", "خراسان رضوی", "خراسان شمالی", "خوزستان", "زنجان",
	"سمنان", "سیستان و بلوچستان", "فارس", "قزوین", "قم", "کردستان", "کرمان", "کرمانشاه",
	"کهگیلویه و بویراحمد", "گلستان", "گیلان", "لرستان", "مازندران", "مرکزی", "هرمزگان", "همدان", "یزد",
]  # fmt: skip

ADDRESS_FIELDS = [
	{
		"fieldname": "iran_province",
		"label": "Province (استان)",
		"fieldtype": "Select",
		"options": "\n" + "\n".join(PROVINCES),
		"insert_after": "state",
		"depends_on": "eval:doc.country=='Iran'",
		"description": "Copied to State/Province when the country is Iran",
	},
	{
		"fieldname": "iran_city",
		"label": "City (شهر)",
		"fieldtype": "Autocomplete",
		"insert_after": "iran_province",
		"depends_on": "eval:doc.country=='Iran'",
		"description": "The cities of the province are suggested. Copied to City when the country is Iran",
	},
]

from erpnext_iran.moadian_extras import HEADER_EXTRAS, ITEM_EXTRAS, custom_fields  # noqa: E402

CUSTOM_FIELDS = {"Customer": PARTY_FIELDS, "Supplier": PARTY_FIELDS, "Bank": BANK_FIELDS, "Address": ADDRESS_FIELDS}

# Moadian (سامانه مؤدیان) fields. Every label says "unverified": the names and codes follow the
# public Moadian invoice description as remembered, not an official document the project holds.
PATTERN_OPTIONS = "\n1 - Sale\n2 - Foreign currency sale\n3 - Gold, jewellery and platinum\n4 - Contracting\n5 - Utility bills\n6 - Air ticket\n7 - Export\n8 - Waybill\n9 - Oil products\n11 - Securities (bourse)\n13 - Insurance services\n14 - Chain sale"

MOADIAN_UNVERIFIED = "Unverified against the official Moadian documentation."

SALES_INVOICE_MOADIAN_FIELDS = [
	{
		"fieldname": "moadian_section",
		"label": "Moadian (سامانه مؤدیان)",
		"fieldtype": "Section Break",
		"insert_after": "utm_content",
		"collapsible": 1,
		"depends_on": "eval:doc.moadian_enabled",
	},
	{
		"fieldname": "moadian_enabled",
		"label": "Moadian Enabled",
		"fieldtype": "Check",
		"fetch_from": "company.moadian_enabled",
		"read_only": 1,
		"hidden": 1,
		"no_copy": 1,
		"insert_after": "moadian_section",
	},
	{
		"fieldname": "moadian_invoice_type",
		"label": "Invoice Type (inty)",
		"fieldtype": "Select",
		"options": "\n1 - Type 1 (buyer fully identified)\n2 - Type 2 (buyer optional)",
		"insert_after": "moadian_enabled",
		"description": "Type 1 puts the buyer in the buyer's Moadian wallet as a tax credit. Type 2 does not.",
	},
	{
		"fieldname": "moadian_pattern",
		"label": "Invoice Pattern (inp)",
		"fieldtype": "Select",
		"options": PATTERN_OPTIONS,
		"insert_after": "moadian_invoice_type",
		"description": "The pattern decides which fields Moadian asks for.",
	},
	{
		"fieldname": "moadian_subject",
		"label": "Invoice Subject (ins)",
		"fieldtype": "Select",
		"options": "\n1 - Original sale\n2 - Correction",
		"default": "1 - Original sale",
		"insert_after": "moadian_pattern",
		"description": "A sales return is sent as a return automatically. A cancellation has its own button.",
	},
	{
		"fieldname": "moadian_col",
		"fieldtype": "Column Break",
		"insert_after": "moadian_subject",
	},
	{
		"fieldname": "moadian_buyer_type",
		"label": "Buyer Type (tob)",
		"fieldtype": "Select",
		"options": "\n1 - Individual\n2 - Company\n3 - Civil partnership\n4 - Foreign national\n5 - Final consumer",
		"default": "2 - Company",
		"insert_after": "moadian_col",
		"description": "Unverified against the official Moadian documentation.",
	},
	{
		"fieldname": "moadian_settlement_method",
		"label": "Settlement Method (setm)",
		"fieldtype": "Select",
		"options": "\n1 - Cash\n2 - Credit\n3 - Cash and credit",
		"default": "1 - Cash",
		"insert_after": "moadian_buyer_type",
		"description": "Cash and credit takes the paid amount of the invoice as the cash part.",
	},
	{
		"fieldname": "moadian_tax_id",
		"label": "Tax ID (taxid)",
		"fieldtype": "Data",
		"read_only": 1,
		"no_copy": 1,
		"insert_after": "moadian_settlement_method",
		"description": "Filled when the invoice is sent to Moadian.",
	},
	{
		"fieldname": "moadian_reference_number",
		"label": "Reference Number",
		"fieldtype": "Data",
		"read_only": 1,
		"no_copy": 1,
		"insert_after": "moadian_tax_id",
	},
	{
		"fieldname": "moadian_status",
		"label": "Moadian Status",
		"fieldtype": "Select",
		"options": "Not Sent\nSent\nAccepted\nRejected",
		"default": "Not Sent",
		"read_only": 1,
		"in_list_view": 1,
		"in_standard_filter": 1,
		"no_copy": 1,
		"insert_after": "moadian_reference_number",
	},
	{
		"fieldname": "moadian_reference_invoice",
		"label": "Reference Invoice (for a correction)",
		"fieldtype": "Link",
		"options": "Sales Invoice",
		"insert_after": "moadian_status",
		"description": "The invoice this one corrects. A sales return is linked automatically.",
	},
	{
		"fieldname": "moadian_cancel_tax_id",
		"label": "Cancellation Tax ID",
		"fieldtype": "Data",
		"read_only": 1,
		"no_copy": 1,
		"insert_after": "moadian_reference_invoice",
	},
	{
		"fieldname": "moadian_cancel_reference_number",
		"label": "Cancellation Reference Number",
		"fieldtype": "Data",
		"read_only": 1,
		"no_copy": 1,
		"insert_after": "moadian_cancel_tax_id",
	},
	{
		"fieldname": "moadian_serial",
		"label": "Moadian Serial (inno)",
		"fieldtype": "Int",
		"read_only": 1,
		"no_copy": 1,
		"insert_after": "moadian_cancel_reference_number",
	},
	{
		"fieldname": "moadian_sent_at",
		"label": "Sent At",
		"fieldtype": "Datetime",
		"read_only": 1,
		"no_copy": 1,
		"insert_after": "moadian_serial",
	},
	{
		"fieldname": "moadian_errors",
		"label": "Moadian Errors",
		"fieldtype": "Long Text",
		"read_only": 1,
		"no_copy": 1,
		"insert_after": "moadian_sent_at",
	},
]

ITEM_MOADIAN_FIELDS = [
	{
		"fieldname": "moadian_sstid",
		"label": "Goods or Service ID (شناسه کالا یا خدمت)",
		"fieldtype": "Data",
		"insert_after": "stock_uom",
		"description": "13 digits from the official goods and services list. " + MOADIAN_UNVERIFIED,
	},
]

UOM_MOADIAN_FIELDS = [
	{
		"fieldname": "moadian_unit_code",
		"label": "Moadian Unit Code (mu)",
		"fieldtype": "Data",
		"insert_after": "uom_name",
		"description": "The code of the official unit list. " + MOADIAN_UNVERIFIED,
	},
]

COMPANY_MOADIAN_FIELDS = [
	{
		"fieldname": "moadian_company_section",
		"label": "Moadian (سامانه مؤدیان)",
		"fieldtype": "Section Break",
		"insert_after": "address_html",
		"description": "Send the invoices of this company to the tax authority. Get the memory ID and the signing certificate from your account in the Moadian portal (tp.tax.gov.ir), then press Test Connection.",
	},
	{
		"fieldname": "moadian_enabled",
		"label": "Send Invoices to Moadian",
		"fieldtype": "Check",
		"insert_after": "moadian_company_section",
	},
	{
		"fieldname": "moadian_auto_send",
		"label": "Send Automatically When an Invoice Is Submitted",
		"fieldtype": "Check",
		"default": "1",
		"depends_on": "moadian_enabled",
		"insert_after": "moadian_enabled",
	},
	{
		"fieldname": "moadian_default_pattern",
		"label": "Business Type (Invoice Pattern)",
		"fieldtype": "Select",
		"options": PATTERN_OPTIONS,
		"default": "1 - Sale",
		"depends_on": "moadian_enabled",
		"insert_after": "moadian_auto_send",
		"description": "The pattern new invoices start with. It can be changed on an invoice.",
	},
	{
		"fieldname": "moadian_company_column",
		"fieldtype": "Column Break",
		"insert_after": "moadian_default_pattern",
	},
	{
		"fieldname": "moadian_memory_id",
		"label": "Tax Memory ID (شناسه یکتای حافظه مالیاتی)",
		"fieldtype": "Data",
		"depends_on": "moadian_enabled",
		"insert_after": "moadian_company_column",
		"description": "6 characters, from the Moadian portal.",
	},
	{
		"fieldname": "moadian_private_key",
		"label": "Signing Private Key",
		"fieldtype": "Password",
		"depends_on": "moadian_enabled",
		"insert_after": "moadian_memory_id",
		"description": "The private key (PEM) of the certificate below. It stays encrypted.",
	},
	{
		"fieldname": "moadian_certificate",
		"label": "Signing Certificate",
		"fieldtype": "Long Text",
		"depends_on": "moadian_enabled",
		"insert_after": "moadian_private_key",
		"description": "The certificate (PEM) whose public key you registered in the Moadian portal.",
	},
	{
		"fieldname": "moadian_base_url",
		"label": "API Address",
		"fieldtype": "Data",
		"depends_on": "moadian_enabled",
		"insert_after": "moadian_certificate",
		"description": "Leave empty for the live tax authority. Put a test environment address here to try.",
	},
	{
		"fieldname": "moadian_test_connection",
		"label": "Test Connection",
		"fieldtype": "Button",
		"depends_on": "moadian_enabled",
		"insert_after": "moadian_base_url",
	},
]

CUSTOM_FIELDS.update(
	{
		"Sales Invoice": SALES_INVOICE_MOADIAN_FIELDS + custom_fields(HEADER_EXTRAS, "moadian_errors"),
		"Sales Invoice Item": custom_fields(ITEM_EXTRAS, "description"),
		"Item": ITEM_MOADIAN_FIELDS,
		"UOM": UOM_MOADIAN_FIELDS,
		"Company": COMPANY_MOADIAN_FIELDS,
	}
)

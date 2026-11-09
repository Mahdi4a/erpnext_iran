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
		"options": "\n1 - Individual\n2 - Company\n3 - Civil partnership\n4 - Foreign national",
		"insert_after": "moadian_col",
		"description": "Individual and foreign buyers need a national number or economic code and a postal code. Companies need an economic code.",
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
		"fieldname": "moadian_late_after_hours",
		"label": "Late Sending Window (hours)",
		"fieldtype": "Int",
		"depends_on": "moadian_enabled",
		"insert_after": "moadian_default_pattern",
		"description": "The deadline the tax authority announced between the date of an invoice and sending it. Older invoices go with their registration time. 0 means no late sending.",
	},
	{
		"fieldname": "moadian_test_connection",
		"label": "Test Connection",
		"fieldtype": "Button",
		"depends_on": "moadian_enabled",
		"insert_after": "moadian_base_url",
	},
]

ITEM_SCALE_FIELDS = [
	{
		"fieldname": "scale_plu",
		"label": "Scale PLU (کد ترازو)",
		"fieldtype": "Data",
		"insert_after": "barcodes",
		"length": 8,
		"no_copy": 1,
		"description": "For goods weighed at the till. The barcode of the item is made from it, and a label from the scale is read as this item with the weight on it.",
	},
]

POS_PROFILE_FIELDS = [
	{
		"fieldname": "skip_submit_confirmation",
		"label": "Complete a Sale Without Asking",
		"fieldtype": "Check",
		"default": "1",
		"insert_after": "auto_add_item_to_cart",
		"description": "Hides the Permanently Submit question when the cashier completes a sale, so a customer takes one key press less.",
	},
]

SALES_CHANNELS = "\nStore\nWebsite\nInstagram\nTelegram\nWhatsApp\nPhone"

CHANNEL_FIELDS = [
	{"fieldname": "sales_channel", "label": "Sales Channel", "fieldtype": "Select", "options": SALES_CHANNELS, "insert_after": "order_type", "in_standard_filter": 1, "allow_on_submit": 1},
]
SALES_ORDER_CHANNEL_FIELDS = CHANNEL_FIELDS + [
	{"fieldname": "quick_mobile", "label": "Customer Mobile", "fieldtype": "Data", "insert_after": "sales_channel", "description": "Type the mobile number: the customer is found, or made, on the spot."},
	{"fieldname": "delivery_address_text", "label": "Delivery Address", "fieldtype": "Small Text", "insert_after": "customer_name"},
	{"fieldname": "customer_note", "label": "Customer Note", "fieldtype": "Small Text", "insert_after": "delivery_address_text"},
	{"fieldname": "woo_order_id", "label": "WooCommerce Order", "fieldtype": "Data", "read_only": 1, "no_copy": 1, "insert_after": "po_no", "search_index": 1},
]
ITEM_APPAREL_FIELDS = [
	{"fieldname": "season", "label": "Season", "fieldtype": "Select", "options": "\nبهار\nتابستان\nپاییز\nزمستان\nهمه فصل", "insert_after": "item_group", "in_standard_filter": 1, "description": "Used by the clothing pack: sell-through by season and the end-of-season discount."},
]

ITEM_PHARMACY_FIELDS = [
	{"fieldname": "pharmacy_section", "label": "Pharmacy", "fieldtype": "Section Break", "insert_after": "season", "collapsible": 1},
	{"fieldname": "generic_name", "label": "Generic Name", "fieldtype": "Data", "insert_after": "pharmacy_section", "search_index": 1, "description": "The active ingredient. Drugs with the same generic name can stand in for each other."},
	{"fieldname": "drug_strength", "label": "Strength", "fieldtype": "Data", "insert_after": "generic_name", "description": "For example 500 mg"},
	{"fieldname": "dosage_form", "label": "Dosage Form", "fieldtype": "Data", "insert_after": "drug_strength", "description": "Tablet, syrup, ampoule, ..."},
	{"fieldname": "irc_code", "label": "IRC Code", "fieldtype": "Data", "insert_after": "dosage_form"},
	{"fieldname": "pharmacy_column", "fieldtype": "Column Break", "insert_after": "irc_code"},
	{"fieldname": "requires_prescription", "label": "Prescription Only", "fieldtype": "Check", "insert_after": "pharmacy_column", "in_standard_filter": 1, "description": "Cannot be sold without the prescription number and the prescriber."},
	{"fieldname": "is_controlled_drug", "label": "Controlled Drug", "fieldtype": "Check", "insert_after": "requires_prescription", "description": "Also needs the patient's name and national ID, and is listed in the Prescription Register."},
	{"fieldname": "approved_price", "label": "Approved Retail Price", "fieldtype": "Currency", "insert_after": "is_controlled_drug", "description": "The price set by the authority. A sale above it is refused. Empty: no cap."},
]

SALES_INVOICE_PRESCRIPTION_FIELDS = [
	{"fieldname": "prescription_section", "label": "Prescription", "fieldtype": "Section Break", "insert_after": "customer_name", "collapsible": 1, "collapsible_depends_on": "eval:doc.prescription_no"},
	{"fieldname": "prescription_no", "label": "Prescription Number", "fieldtype": "Data", "insert_after": "prescription_section", "no_copy": 1},
	{"fieldname": "prescriber_name", "label": "Prescriber", "fieldtype": "Data", "insert_after": "prescription_no", "no_copy": 1},
	{"fieldname": "prescriber_license", "label": "Medical Council Number", "fieldtype": "Data", "insert_after": "prescriber_name", "no_copy": 1},
	{"fieldname": "prescription_column", "fieldtype": "Column Break", "insert_after": "prescriber_license"},
	{"fieldname": "patient_name", "label": "Patient", "fieldtype": "Data", "insert_after": "prescription_column", "no_copy": 1},
	{"fieldname": "patient_national_id", "label": "Patient National ID", "fieldtype": "Data", "insert_after": "patient_name", "no_copy": 1},
]

ITEM_ONLINE_FIELDS = [
	{"fieldname": "sell_online", "label": "Sell Online", "fieldtype": "Check", "insert_after": "item_group", "description": "Sent to the WooCommerce store and listed in the Instagram catalog."},
	{"fieldname": "woo_product_id", "label": "WooCommerce Product ID", "fieldtype": "Data", "read_only": 1, "no_copy": 1, "insert_after": "sell_online"},
]


EMPLOYEE_PAYROLL_FIELDS = [
	{"fieldname": "iran_payroll_section", "label": "Iran Payroll", "fieldtype": "Section Break", "insert_after": "salary_mode", "collapsible": 1},
	{"fieldname": "iran_national_id", "label": "National ID", "fieldtype": "Data", "insert_after": "iran_payroll_section"},
	{"fieldname": "iran_insurance_number", "label": "Insurance Number", "fieldtype": "Data", "insert_after": "iran_national_id"},
	{"fieldname": "iran_insurance_applies", "label": "Insurance Applies", "fieldtype": "Check", "default": "1", "insert_after": "iran_insurance_number"},
	{"fieldname": "iran_payroll_column", "fieldtype": "Column Break", "insert_after": "iran_insurance_applies"},
	{"fieldname": "iran_children", "label": "Number of Children", "fieldtype": "Int", "default": "0", "insert_after": "iran_payroll_column"},
	{"fieldname": "iran_housing", "label": "Housing Allowance (monthly)", "fieldtype": "Currency", "insert_after": "iran_children"},
	{"fieldname": "iran_food", "label": "Food Allowance (monthly)", "fieldtype": "Currency", "insert_after": "iran_housing"},
]


def _pricing_rule_time_fields():
	from erpnext_iran.pricing_time import DAYS

	fields = [
		{
			"fieldname": "iran_time_section",
			"label": "Days and Hours",
			"fieldtype": "Section Break",
			"insert_after": "valid_upto",
			"description": "Leave empty for every day and every hour. For example Thursday 10:00 to 12:00.",
		}
	]
	previous = "iran_time_section"
	for fieldname, _weekday, label in DAYS:
		fields.append({"fieldname": fieldname, "label": label, "fieldtype": "Check", "insert_after": previous})
		previous = fieldname
	fields += [
		{"fieldname": "iran_time_break", "fieldtype": "Column Break", "insert_after": previous},
		{"fieldname": "iran_from_time", "label": "From Time", "fieldtype": "Time", "insert_after": "iran_time_break"},
		{"fieldname": "iran_to_time", "label": "To Time", "fieldtype": "Time", "insert_after": "iran_from_time"},
	]
	return fields


POS_DISCOUNT_FIELDS = [
	{
		"fieldname": "cashier_discount_limit",
		"label": "Cashier Discount Limit (%)",
		"fieldtype": "Percent",
		"default": "100",
		"insert_after": "skip_submit_confirmation",
		"description": "The most a cashier may take off the listed prices of a sale. Above it a manager must approve with their password. 100 means no limit. Pricing Rule promotions do not count.",
	},
]

SALES_INVOICE_DISCOUNT_FIELDS = [
	{"fieldname": "discount_approval_token", "label": "Discount Approval Token", "fieldtype": "Data", "hidden": 1, "no_copy": 1, "print_hide": 1, "read_only": 1, "insert_after": "additional_discount_percentage"},
	{"fieldname": "discount_approved_by", "label": "Discount Approved By", "fieldtype": "Link", "options": "User", "read_only": 1, "no_copy": 1, "insert_after": "discount_amount"},
]

SALES_INVOICE_OFFLINE_FIELDS = [
	{
		"fieldname": "offline_sale_id",
		"label": "Offline Sale ID",
		"fieldtype": "Data",
		"unique": 1,
		"read_only": 1,
		"no_copy": 1,
		"print_hide": 1,
		"insert_after": "pos_profile",
		"description": "Made by the till when the sale was rung up without a connection; keeps a sale that is sent twice from becoming two invoices.",
	},
]

CUSTOM_FIELDS.update(
	{
		"Pricing Rule": _pricing_rule_time_fields(),
		"Employee": EMPLOYEE_PAYROLL_FIELDS,
		"Sales Invoice": SALES_INVOICE_MOADIAN_FIELDS + custom_fields(HEADER_EXTRAS, "moadian_errors") + SALES_INVOICE_DISCOUNT_FIELDS + SALES_INVOICE_OFFLINE_FIELDS + CHANNEL_FIELDS + SALES_INVOICE_PRESCRIPTION_FIELDS,
		"Sales Order": SALES_ORDER_CHANNEL_FIELDS,
		"Sales Invoice Item": custom_fields(ITEM_EXTRAS, "description"),
		"Item": ITEM_MOADIAN_FIELDS + ITEM_SCALE_FIELDS + ITEM_ONLINE_FIELDS + ITEM_APPAREL_FIELDS + ITEM_PHARMACY_FIELDS,
		"POS Profile": POS_PROFILE_FIELDS + POS_DISCOUNT_FIELDS,
		"UOM": UOM_MOADIAN_FIELDS,
		"Company": COMPANY_MOADIAN_FIELDS,
	}
)

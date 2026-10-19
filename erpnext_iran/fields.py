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

CUSTOM_FIELDS = {"Customer": PARTY_FIELDS, "Supplier": PARTY_FIELDS}

# Moadian (سامانه مؤدیان) fields. Every label says "unverified": the names and codes follow the
# public Moadian invoice description as remembered, not an official document the project holds.
MOADIAN_UNVERIFIED = "Unverified against the official Moadian documentation."

SALES_INVOICE_MOADIAN_FIELDS = [
	{
		"fieldname": "moadian_section",
		"label": "Moadian (سامانه مؤدیان)",
		"fieldtype": "Section Break",
		"insert_after": "remarks",
		"collapsible": 1,
		"description": MOADIAN_UNVERIFIED,
	},
	{
		"fieldname": "moadian_invoice_type",
		"label": "Invoice Type (inty)",
		"fieldtype": "Select",
		"options": "\n1\n2\n3",
		"default": "1",
		"insert_after": "moadian_section",
		"description": "1: type one, 2: type two, 3: type three. " + MOADIAN_UNVERIFIED,
	},
	{
		"fieldname": "moadian_pattern",
		"label": "Invoice Pattern (inp)",
		"fieldtype": "Select",
		"options": "\n1\n2\n3\n4\n5\n6\n7\n8\n9",
		"default": "1",
		"insert_after": "moadian_invoice_type",
		"description": "1: sale. " + MOADIAN_UNVERIFIED,
	},
	{
		"fieldname": "moadian_subject",
		"label": "Invoice Subject (ins)",
		"fieldtype": "Select",
		"options": "\n1\n2\n3\n4",
		"default": "1",
		"insert_after": "moadian_pattern",
		"description": "1: original, 2: correction, 3: cancellation, 4: sales return. " + MOADIAN_UNVERIFIED,
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
		"options": "\n1\n2\n3\n4\n5",
		"default": "2",
		"insert_after": "moadian_col",
		"description": "1: individual, 2: company, 3: civil partnership, 4: foreign national, 5: final consumer. "
		+ MOADIAN_UNVERIFIED,
	},
	{
		"fieldname": "moadian_settlement_method",
		"label": "Settlement Method (setm)",
		"fieldtype": "Select",
		"options": "\n1\n2\n3",
		"default": "1",
		"insert_after": "moadian_buyer_type",
		"description": "1: cash, 2: credit, 3: cash and credit. " + MOADIAN_UNVERIFIED,
	},
	{
		"fieldname": "moadian_tax_id",
		"label": "Tax ID (taxid)",
		"fieldtype": "Data",
		"read_only": 1,
		"no_copy": 1,
		"insert_after": "moadian_settlement_method",
		"description": "Filled by the integration, which does not exist yet.",
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
		"no_copy": 1,
		"insert_after": "moadian_reference_number",
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
		"fieldname": "moadian_memory_id",
		"label": "Tax Memory ID (شناسه یکتای حافظه مالیاتی)",
		"fieldtype": "Data",
		"insert_after": "tax_id",
		"description": "6 characters. " + MOADIAN_UNVERIFIED,
	},
]

CUSTOM_FIELDS.update(
	{
		"Sales Invoice": SALES_INVOICE_MOADIAN_FIELDS,
		"Item": ITEM_MOADIAN_FIELDS,
		"UOM": UOM_MOADIAN_FIELDS,
		"Company": COMPANY_MOADIAN_FIELDS,
	}
)

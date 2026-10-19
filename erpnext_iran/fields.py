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

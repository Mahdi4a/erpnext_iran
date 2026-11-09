"""Inputs the Moadian patterns ask for beyond a plain sale (RC_IITP.IS_V7.9, table 2).

Each is a custom field named `moadian_<code>`: on the Sales Invoice when it belongs to the header,
on the Sales Invoice Item when it belongs to the body. Only the fields the pattern of the invoice
lists are sent (see data/moadian_patterns.json), so a field that stays empty costs nothing.
"""

from __future__ import annotations

# (code, label, field type)
HEADER_EXTRAS = [
	("ft", "Flight Type", "Select", "\n1 - Domestic flight\n2 - Foreign flight"),
	("crn", "Contract Number", "Data"),
	("billid", "Subscription or Bill ID", "Data"),
	("cno", "Fleet Number", "Data"),
	("lno", "Waybill Number", "Data"),
	("lrno", "Reference Waybill Number", "Data"),
	("lt", "Waybill or Cargo Type", "Data"),
	("did", "Road Driver ID", "Data"),
	("tid", "Sender ID", "Data"),
	("rid", "Receiver ID", "Data"),
	("ocu", "Origin Country", "Data"),
	("oci", "Origin City", "Data"),
	("dco", "Destination Country", "Data"),
	("dci", "Destination City", "Data"),
	("asn", "Bourse Sale Notice Number", "Data"),
	("asd", "Bourse Sale Notice Date", "Data"),
	("in", "Insurance Policy ID", "Data"),
	("an", "Insurance Annex ID", "Data"),
	("scln", "Customs License Number", "Data"),
	("scc", "Customs Declaration Place Code", "Data"),
	("cdcn", "Customs Declaration Cottage Number", "Data"),
	("cdcd", "Customs Declaration Cottage Date", "Data"),
	("bpn", "Buyer Passport Number", "Data"),
	("tinc", "Economic Agency Number", "Data"),
	("sbc", "Seller Branch Code", "Data"),
	("bpc", "Buyer Postal Code", "Data"),
	("bbc", "Buyer Branch Code", "Data"),
	("nti1", "Note 1", "Data"),
	("nti2", "Note 2", "Data"),
]

ITEM_EXTRAS = [
	("nw", "Net Weight", "Float"),
	("cfee", "Unit Price in Currency", "Float"),
	("cut", "Currency Type", "Data"),
	("exr", "Currency Exchange Rate", "Float"),
	("ssrv", "Item Value in Rial", "Float"),
	("sscv", "Item Value in Currency", "Float"),
	("consfee", "Manufacturing Fee (Gold)", "Float"),
	("spro", "Seller Profit (Gold)", "Float"),
	("bros", "Brokerage (Gold)", "Float"),
	("cui", "Carat (Gold)", "Float"),
	("sgid", "Carried Goods ID", "Data"),
	("sgt", "Carried Goods Description", "Data"),
	("cpr", "Currency Purchase Rate", "Float"),
	("sovat", "VAT Source in Currency Sale", "Int"),
	("vba", "VAT Base Amount", "Float"),
]

HEADER_CODES = [code for code, *_ in HEADER_EXTRAS]
ITEM_CODES = [code for code, *_ in ITEM_EXTRAS]


def custom_fields(extras, after: str) -> list[dict]:
	"""Custom field definitions for one doctype, in a section placed after `after`."""
	fields = [
		{"fieldname": f"moadian_{after}_section", "label": "Moadian Pattern Fields", "fieldtype": "Section Break", "insert_after": after, "collapsible": 1}
	]
	for code, label, fieldtype, *options in extras:
		fields.append(
			{
				"fieldname": f"moadian_{code}",
				"label": f"{label} ({code})",
				"fieldtype": fieldtype,
				"insert_after": fields[-1]["fieldname"],
				"no_copy": 1,
				**({"options": options[0]} if options else {}),
			}
		)
	return fields

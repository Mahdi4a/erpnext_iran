from __future__ import annotations

import frappe

# Sheba bank code (the three digits after IR and the check digits) and the name of the bank.
# Taken from the public iran-bank-detector data (npm), which agrees with the codes the banks
# print on a Sheba. Banks merged into Sepah in 2018-19 (Ansar, Ghavamin, Hekmat Iranian, Kosar,
# Mehr Eghtesad) are left out. 051 is listed there as Tose'e Taavon; 022, which some lists give
# to the same bank, is not added.
BANKS = {
	"010": "بانک مرکزی جمهوری اسلامی ایران",
	"011": "بانک صنعت و معدن",
	"012": "بانک ملت",
	"013": "بانک رفاه کارگران",
	"014": "بانک مسکن",
	"015": "بانک سپه",
	"016": "بانک کشاورزی",
	"017": "بانک ملی ایران",
	"018": "بانک تجارت",
	"019": "بانک صادرات ایران",
	"020": "بانک توسعه صادرات ایران",
	"021": "پست بانک ایران",
	"051": "بانک توسعه تعاون",
	"053": "بانک کارآفرین",
	"054": "بانک پارسیان",
	"055": "بانک اقتصاد نوین",
	"056": "بانک سامان",
	"057": "بانک پاسارگاد",
	"058": "بانک سرمایه",
	"059": "بانک سینا",
	"060": "بانک قرض‌الحسنه مهر ایران",
	"061": "بانک شهر",
	"062": "بانک آینده",
	"064": "بانک گردشگری",
	"066": "بانک دی",
	"069": "بانک ایران زمین",
	"070": "بانک قرض‌الحسنه رسالت",
	"075": "موسسه اعتباری ملل",
	"078": "بانک خاورمیانه",
	"080": "موسسه اعتباری نور",
	"095": "بانک ایران و ونزوئلا",
}


def sheba_bank_code(value) -> str | None:
	"""'IR36012...' -> '012'. None for anything that is not an Iranian Sheba."""
	from erpnext_iran.validations import normalize_sheba

	text = normalize_sheba(value)
	if len(text) == 26 and text.startswith("IR") and text[2:].isdigit():
		return text[4:7]
	return None


def bank_for_sheba(value) -> str | None:
	"""The Bank whose Sheba code is in the number, if there is one."""
	code = sheba_bank_code(value)
	if code:
		return frappe.db.get_value("Bank", {"sheba_code": code}, "name")
	return None


def ensure_banks():
	"""Adds the banks that are missing and gives a bank of the same name its Sheba code when it has none.
	A bank somebody renamed or gave another code is left alone."""
	for code, name in BANKS.items():
		if frappe.db.exists("Bank", name):
			if not frappe.db.get_value("Bank", name, "sheba_code"):
				frappe.db.set_value("Bank", name, "sheba_code", code)
		elif not frappe.db.exists("Bank", {"sheba_code": code}):
			bank = frappe.new_doc("Bank")
			bank.bank_name = name
			bank.sheba_code = code
			bank.flags.ignore_permissions = True
			bank.insert()

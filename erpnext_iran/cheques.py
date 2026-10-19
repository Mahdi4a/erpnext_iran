"""Status flow and accounting of Iran Cheque (چک دریافتنی و پرداختنی).

Every status change posts one Journal Entry, so the books always show where a cheque is:

Received (the customer's cheque is an asset until it is collected)
	submit    Dr Cheques in hand            Cr Receivable (customer)
	deposit   Dr Cheques in collection      Cr Cheques in hand
	clear     Dr Bank                       Cr Cheques in collection
	bounce    Dr Receivable (customer)      Cr Cheques in collection
	endorse   Dr Payable (supplier)         Cr Cheques in hand

Issued (our cheque is a liability until the supplier collects it)
	submit    Dr Payable (supplier)         Cr Cheques payable
	clear     Dr Cheques payable            Cr Bank
	bounce    Dr Cheques payable            Cr Payable (supplier)
"""

from __future__ import annotations

import frappe
from frappe import _

# (type, status) -> {action: new status}
TRANSITIONS = {
	("Received", "In Hand"): {"deposit": "Deposited", "endorse": "Endorsed"},
	("Received", "Deposited"): {"clear": "Cleared", "bounce": "Bounced"},
	("Issued", "Issued"): {"clear": "Cleared", "bounce": "Bounced"},
}

INITIAL_STATUS = {"Received": "In Hand", "Issued": "Issued"}

# Account numbers of the Iran chart of accounts, used when the settings give no account
DEFAULT_ACCOUNT_NUMBERS = {
	"cheques_in_hand": "110402",
	"cheques_in_collection": "110401",
	"cheques_payable": "210201",
}


def next_status(cheque_type: str, status: str, action: str) -> str:
	allowed = TRANSITIONS.get((cheque_type, status), {})
	if action not in allowed:
		frappe.throw(
			_("A {0} cheque that is {1} cannot be {2}").format(_(cheque_type), _(status), _(action)),
			title=_("Not Allowed"),
		)
	return allowed[action]


def available_actions(cheque_type: str, status: str) -> list[str]:
	return list(TRANSITIONS.get((cheque_type, status), {}))


def posting_lines(cheque_type: str, step: str, accounts: dict) -> list[dict]:
	"""The debit and credit side of one step, without amounts.

	`step` is "submit" or an action. `accounts` holds cheques_in_hand, cheques_in_collection,
	cheques_payable, bank and `party` / `endorsed_to` as {"account", "party_type", "party"}.
	"""
	party, endorsed_to = accounts.get("party"), accounts.get("endorsed_to")
	hand, collection = accounts.get("cheques_in_hand"), accounts.get("cheques_in_collection")
	payable, bank = accounts.get("cheques_payable"), accounts.get("bank")

	if cheque_type == "Received":
		steps = {
			"submit": [("debit", hand), ("credit", party)],
			"deposit": [("debit", collection), ("credit", hand)],
			"clear": [("debit", bank), ("credit", collection)],
			"bounce": [("debit", party), ("credit", collection)],
			"endorse": [("debit", endorsed_to), ("credit", hand)],
		}
	else:
		steps = {
			"submit": [("debit", party), ("credit", payable)],
			"clear": [("debit", payable), ("credit", bank)],
			"bounce": [("debit", payable), ("credit", party)],
		}

	lines = []
	for side, target in steps[step]:
		if not target:
			frappe.throw(_("An account is missing for the step {0}").format(_(step)))
		line = {"side": side}
		line.update(target if isinstance(target, dict) else {"account": target})
		lines.append(line)
	return lines


def get_cheque_accounts(company: str) -> dict:
	"""Cheque accounts of the company: the settings table first, then the Iran chart's account numbers."""
	settings_row = {}
	settings = frappe.get_cached_doc("ERPNext Iran Settings")
	for row in settings.get("cheque_accounts") or []:
		if row.company == company:
			settings_row = row.as_dict()
			break

	accounts = {}
	for key, number in DEFAULT_ACCOUNT_NUMBERS.items():
		account = settings_row.get(key) or frappe.db.get_value(
			"Account", {"company": company, "account_number": number, "is_group": 0}, "name"
		)
		if not account:
			frappe.throw(
				_("No account for {0} in {1}. Set it in ERPNext Iran Settings, Cheque Accounts.").format(
					_(key.replace("_", " ").title()), company
				),
				title=_("Cheque Accounts Missing"),
			)
		accounts[key] = account
	return accounts


def party_row(company: str, party_type: str, party: str) -> dict:
	from erpnext.accounts.party import get_party_account

	return {
		"account": get_party_account(party_type, party, company),
		"party_type": party_type,
		"party": party,
	}


def post(cheque, step: str, posting_date=None, bank_account: str | None = None, endorsed_to=None) -> str:
	"""Create and submit the Journal Entry of a step; returns its name."""
	accounts = get_cheque_accounts(cheque.company)
	accounts["party"] = party_row(cheque.company, cheque.party_type, cheque.party)
	if endorsed_to:
		accounts["endorsed_to"] = party_row(cheque.company, "Supplier", endorsed_to)
	if bank_account:
		accounts["bank"] = frappe.db.get_value("Bank Account", bank_account, "account")

	journal_entry = frappe.new_doc("Journal Entry")
	journal_entry.update(
		{
			"voucher_type": "Journal Entry",
			"company": cheque.company,
			"posting_date": posting_date or frappe.utils.today(),
			"cheque_no": cheque.cheque_no,
			"cheque_date": cheque.due_date,
			"user_remark": _("Cheque {0}: {1}").format(cheque.cheque_no, _(step)),
		}
	)
	for line in posting_lines(cheque.cheque_type, step, accounts):
		row = {
			"account": line["account"],
			f"{line['side']}_in_account_currency": cheque.amount,
		}
		if line.get("party"):
			row.update(party_type=line["party_type"], party=line["party"])
		journal_entry.append("accounts", row)

	journal_entry.insert(ignore_permissions=True)
	journal_entry.submit()
	return journal_entry.name

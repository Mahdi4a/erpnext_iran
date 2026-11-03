"""Cities of each province for the Address form.

The list is the cities of the official country divisions file up to the end of 1404, as published
in the repository sajaddp/list-of-cities-in-Iran (GPL-3.0), reduced to the name of each city of each
province. A city is free text in the Address: the list only suggests."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

import frappe

DATA = Path(__file__).parent / "data" / "iran_cities.json"


@cache
def all_cities() -> dict[str, list[str]]:
	return json.loads(DATA.read_text(encoding="utf-8"))


@frappe.whitelist()
def get_cities(province: str | None = None) -> list[str]:
	"""The cities of a province, in alphabetical order. Empty for a name that is not a province."""
	return all_cities().get(province or "", [])

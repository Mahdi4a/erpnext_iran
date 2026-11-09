"""The Moadian tax ID (شماره منحصر به فرد مالیاتی): 22 characters.

memory ID (6) + days since 1970 as 5 hex digits + serial as 10 hex digits + 1 control digit.
The control digit is the Verhoeff check digit of a decimal text: the memory ID with each letter
replaced by its character code, the days padded to 6 digits, the serial padded to 12 digits.
Source: TaxIdProviderImpl and VerhoeffAlgorithm of the official tax-collect-data-sdk-java 2.0.33.
"""

from __future__ import annotations

SECONDS_PER_DAY = 86_400

_MULTIPLICATION = [
	[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5], [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
	[3, 4, 0, 1, 2, 8, 9, 5, 6, 7], [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
	[6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3], [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
	[9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]  # fmt: skip
_PERMUTATION = [
	[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4], [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
	[8, 9, 1, 6, 0, 4, 3, 5, 2, 7], [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
	[2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]  # fmt: skip
_INVERSE = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]


def verhoeff_check_digit(digits: str) -> str:
	total = 0
	for position, digit in enumerate(reversed(digits)):
		total = _MULTIPLICATION[total][_PERMUTATION[(position + 1) % 8][int(digit)]]
	return str(_INVERSE[total])


def memory_id_digits(memory_id: str) -> str:
	return "".join(char if char.isdigit() else str(ord(char)) for char in memory_id)


def control_digit(memory_id: str, days: int, serial: int) -> str:
	return verhoeff_check_digit(f"{memory_id_digits(memory_id)}{days:06d}{serial:012d}")


def tax_id(memory_id: str, invoice_millis: int, serial: int) -> str:
	days = invoice_millis // 1000 // SECONDS_PER_DAY
	body = f"{memory_id}{days:05X}{serial:010X}"
	return (body + control_digit(memory_id, days, serial)).upper()

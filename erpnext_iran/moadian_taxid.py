"""The Moadian tax ID (شماره منحصر به فرد مالیاتی): 22 characters, from RC_TICS.IS_v1.5 samples.

memory ID (6) + days since 1970 as 5 hex digits + serial as 10 hex digits + 1 control digit.
The control digit algorithm is in the separate document "قالب شناسه یکتای حافظه مالیاتی و شماره
منحصر به فرد مالیاتی", which the project does not hold yet. Until `control_digit` is written from it,
no tax ID is made, so nothing wrong reaches the tax authority.
"""

from __future__ import annotations

MILLIS_PER_DAY = 86_400_000


def control_digit(body: str) -> str:
	"""Not written on purpose: the algorithm cannot be guessed from the two samples of the spec."""
	raise NotImplementedError(
		"The Moadian tax ID control digit is not implemented. Write it from the official document "
		"'قالب شناسه یکتای حافظه مالیاتی و شماره منحصر به فرد مالیاتی' (see TAX_ID_SAMPLES)."
	)


# From the spec, to test `control_digit` with once it exists: (memory ID, invoice time in
# milliseconds, serial) -> tax ID. The first is from RC_IITP.IS_V7.9 (inno 49321217).
TAX_ID_SAMPLES = [("A11216", 1683997837988, 49321217, "A1121604C220002F095011")]


def tax_id(memory_id: str, invoice_millis: int, serial: int) -> str:
	body = f"{memory_id}{invoice_millis // MILLIS_PER_DAY:05X}{serial:010X}"
	return body + control_digit(body)

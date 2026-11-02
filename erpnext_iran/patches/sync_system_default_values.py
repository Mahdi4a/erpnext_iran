from erpnext_iran.defaults import apply_system_defaults


def execute():
	"""Sites set up before this read the stock number format and decimals on the desk, and English
	as the language, although System Settings said otherwise."""
	apply_system_defaults()

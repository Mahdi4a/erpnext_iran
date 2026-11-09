app_name = "erpnext_iran"
app_title = "ERPNext Iran"
app_publisher = "Mahdi"
app_description = "Iran localization for ERPNext"
app_email = "guts2day@gmail.com"
app_license = "gpl-3.0"

required_apps = ["iran_base", "erpnext"]

after_install = "erpnext_iran.install.after_install"
after_migrate = "erpnext_iran.install.after_migrate"

app_include_js = [
	"/assets/erpnext_iran/js/erpnext_iran.js",
	"/assets/erpnext_iran/js/pos_scale.js",
	"/assets/erpnext_iran/js/pos_quick_pay.js",
]

extend_bootinfo = "erpnext_iran.defaults.extend_bootinfo"

jinja = {
	"filters": [
		"erpnext_iran.defaults.persian_digits",
		"erpnext_iran.defaults.iran_digits",
		"erpnext_iran.jalali.jalali_date",
	]
}

doc_events = {
	"*": {"validate": "erpnext_iran.in_words.set_in_words"},
	"Company": {
		"before_validate": [
			"erpnext_iran.defaults.set_company_currency",
			"erpnext_iran.chart_of_accounts.before_company_save",
		],
		"on_update": "erpnext_iran.setup.on_company_update",
	},
	"Sales Invoice": {
		"before_validate": "erpnext_iran.moadian.set_defaults_from_company",
		"on_submit": "erpnext_iran.moadian_send.auto_send_on_submit",
		"on_cancel": "erpnext_iran.moadian_send.cancel_after_erp_cancel",
	},
	"Item": {"validate": "erpnext_iran.scale.validate_item"},
	"Customer": {"validate": "erpnext_iran.validations.validate_party"},
	"Supplier": {"validate": "erpnext_iran.validations.validate_party"},
	"Bank Account": {"validate": "erpnext_iran.validations.validate_bank_account"},
	"Address": {"validate": "erpnext_iran.validations.validate_address"},
}

override_whitelisted_methods = {
	"erpnext.accounts.doctype.account.chart_of_accounts.chart_of_accounts.get_charts_for_country": "erpnext_iran.chart_of_accounts.get_charts_for_country",
}

# Jalali parts for naming series, e.g. ACC-SINV-.JY.-.#####
naming_series_variables_list = ["JY", "JYY", "JM", "JD"]
naming_series_variables = {
	variable: "erpnext_iran.naming.parse_variable" for variable in ("JY", "JYY", "JM", "JD")
}
scheduler_events = {
	"daily": ["erpnext_iran.jalali.ensure_current_and_next_fiscal_years"],
	"hourly": ["erpnext_iran.moadian_send.check_sent_invoices"],
}

doctype_list_js = {"Fiscal Year": "public/js/fiscal_year_list.js"}
doctype_js = {
	"Address": "public/js/address.js",
	"Sales Invoice": "public/js/moadian_sales_invoice.js",
	"Company": "public/js/moadian_company.js",
}

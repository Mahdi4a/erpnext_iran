app_name = "erpnext_iran"
app_title = "ERPNext Iran"
app_publisher = "Mahdi"
app_description = "Iran localization for ERPNext"
app_email = "guts2day@gmail.com"
app_license = "gpl-3.0"

required_apps = ["iran_base", "erpnext"]

after_install = "erpnext_iran.install.after_install"

doc_events = {
	"Company": {
		"before_validate": "erpnext_iran.chart_of_accounts.before_company_save",
		"on_update": "erpnext_iran.setup.on_company_update",
	},
	"Customer": {"validate": "erpnext_iran.validations.validate_party"},
	"Supplier": {"validate": "erpnext_iran.validations.validate_party"},
	"Address": {"validate": "erpnext_iran.validations.validate_address"},
}

override_whitelisted_methods = {
	"erpnext.accounts.doctype.account.chart_of_accounts.chart_of_accounts.get_charts_for_country": "erpnext_iran.chart_of_accounts.get_charts_for_country",
}

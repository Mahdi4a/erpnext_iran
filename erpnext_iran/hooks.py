app_name = "erpnext_iran"
app_title = "ERPNext Iran"
app_publisher = "Mahdi"
app_description = "Iran localization for ERPNext"
app_email = "guts2day@gmail.com"
app_license = "gpl-3.0"

required_apps = ["iran_base", "erpnext"]

after_install = "erpnext_iran.install.after_install"
after_migrate = "erpnext_iran.install.after_migrate"
before_request = ["erpnext_iran.pricing_time.install", "erpnext_iran.iran_payroll.install", "erpnext_iran.offline.install"]
before_job = ["erpnext_iran.pricing_time.install", "erpnext_iran.iran_payroll.install", "erpnext_iran.offline.install"]

app_include_js = [
	"/assets/erpnext_iran/js/erpnext_iran.js",
	"/assets/erpnext_iran/js/pos_scale.js",
	"/assets/erpnext_iran/js/pos_quick_pay.js",
	"/assets/erpnext_iran/js/pos_loyalty.js",
	"/assets/erpnext_iran/js/pos_discount.js",
	"/assets/erpnext_iran/js/pos_offline_core.js",
	"/assets/erpnext_iran/js/pos_offline.js",
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
		"validate": ["erpnext_iran.loyalty.validate_redeem_limit", "erpnext_iran.channels.default_channel"],
		"before_submit": "erpnext_iran.discount.check_discount",
		"on_submit": ["erpnext_iran.moadian_send.auto_send_on_submit", "erpnext_iran.woocommerce.push_after_sale", "erpnext_iran.discount.consume_token"],
		"on_cancel": ["erpnext_iran.moadian_send.cancel_after_erp_cancel", "erpnext_iran.woocommerce.push_after_sale"],
	},
	"Item": {"validate": "erpnext_iran.scale.validate_item"},
	"Pricing Rule": {"validate": "erpnext_iran.pricing_time.validate_pricing_rule"},
	"Customer": {
		"validate": ["erpnext_iran.validations.validate_party", "erpnext_iran.branches.keep_walk_in_out_of_loyalty"]
	},
	"Supplier": {"validate": "erpnext_iran.validations.validate_party"},
	"Bank Account": {"validate": "erpnext_iran.validations.validate_bank_account"},
	"Address": {"validate": "erpnext_iran.validations.validate_address"},
}

override_whitelisted_methods = {
	"erpnext.accounts.doctype.sales_invoice.sales_invoice.get_loyalty_programs": "erpnext_iran.branches.get_loyalty_programs",
	"erpnext.accounts.doctype.account.chart_of_accounts.chart_of_accounts.get_charts_for_country": "erpnext_iran.chart_of_accounts.get_charts_for_country",
}

# Jalali parts for naming series, e.g. ACC-SINV-.JY.-.#####
naming_series_variables_list = ["JY", "JYY", "JM", "JD"]
naming_series_variables = {
	variable: "erpnext_iran.naming.parse_variable" for variable in ("JY", "JYY", "JM", "JD")
}
scheduler_events = {
	"daily": ["erpnext_iran.jalali.ensure_current_and_next_fiscal_years"],
	"hourly": ["erpnext_iran.moadian_send.check_sent_invoices", "erpnext_iran.woocommerce.scheduled_push"],
}

doctype_list_js = {"Fiscal Year": "public/js/fiscal_year_list.js"}
doctype_js = {
	"Address": "public/js/address.js",
	"Sales Invoice": "public/js/moadian_sales_invoice.js",
	"Sales Order": "public/js/sales_order_quick.js",
	"Online Channel Settings": "public/js/online_channel_settings.js",
	"Company": "public/js/moadian_company.js",
}

# erpnext_iran

Iran localization for ERPNext, on top of `iran_base`. It adds custom fields and validation hooks; it
does not change ERPNext.

- Customer and Supplier: National ID (کد ملی), Legal ID (شناسه ملی), Economic Code (کد اقتصادی), checked on save
- Address: postal code checked when the country is Iran
- "Iran VAT" sales and purchase tax templates for every company (rate from `iran_vat_rate`, default 10; check the current legal rate)

Not done yet: Iranian chart of accounts, the Moadian tax-authority integration, Iranian payment gateways.

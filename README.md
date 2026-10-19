# erpnext_iran

Iran localization for ERPNext, on top of `iran_base`. It adds custom fields and validation hooks; it
does not change ERPNext.

- Customer and Supplier: National ID (کد ملی), Legal ID (شناسه ملی), Economic Code (کد اقتصادی), checked on save
- Address: postal code checked when the country is Iran
- "Iran VAT" sales and purchase tax templates for every company (rate from `iran_vat_rate`, default 10; check the current legal rate)
- Chart of accounts "Iran - Chart of Accounts" (کدینگ حسابداری), offered on the Company form when the country is Iran. The coding (1 current assets, 2 non-current assets, 3 current liabilities, 4 non-current liabilities, 5 equity, 6 income, 7 costs) is a common convention, not an official standard: review it with your accountant
- IRR and IRT currencies with whole numbers, and Iran defaults for the site (number format `#,###`, no currency decimals, Saturday as first day of the week, Asia/Tehran) applied on install only where the stock value is still in place; an Iranian company without a currency gets IRR
- "Use Persian Digits" in ERPNext Iran Settings: Persian digits in lists, reports and read-only values (inputs stay 0-9); `{{ value | persian_digits }}` for print formats

Not done yet: the Moadian tax-authority integration, Iranian payment gateways.

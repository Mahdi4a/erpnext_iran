# erpnext_iran

Iran localization for ERPNext, on top of `iran_base`. It adds custom fields and validation hooks; it
does not change ERPNext.

- Customer and Supplier: National ID (کد ملی), Legal ID (شناسه ملی), Economic Code (کد اقتصادی), checked on save
- Address: postal code checked when the country is Iran
- "Iran VAT" sales and purchase tax templates for every company (rate from `iran_vat_rate`, default 10; check the current legal rate)
- Chart of accounts "Iran - Chart of Accounts" (کدینگ حسابداری), offered on the Company form when the country is Iran. The coding (1 current assets, 2 non-current assets, 3 current liabilities, 4 non-current liabilities, 5 equity, 6 income, 7 costs) is a common convention, not an official standard: review it with your accountant
- IRR and IRT currencies with whole numbers, and Iran defaults for the site (number format `#,###`, no currency decimals, Saturday as first day of the week, Asia/Tehran) applied on install only where the stock value is still in place; an Iranian company without a currency gets IRR
- "Use Persian Digits" in ERPNext Iran Settings: Persian digits in lists, reports and read-only values (inputs stay 0-9); `{{ value | persian_digits }}` for print formats
- Jalali (Shamsi) fiscal years named after the Jalali year (1404, 1405...), starting 1 Farvardin: "Create Jalali Fiscal Year" button on the Fiscal Year list, the current and next year are also created daily. ERPNext only accepts a year of exactly one Gregorian year, so a Jalali year of another length gets "Is Short Year" ticked; if a year overlaps an existing one, give it a company
- "Show Jalali Dates" in ERPNext Iran Settings: Date and Datetime values in lists and reports are shown as Jalali (stored and entered as Gregorian); `{{ doc.posting_date | jalali_date }}` for print formats
- Iran Cheque (چک دریافتنی / پرداختنی, Erpnext Iran module, `/desk/iran-cheque`): submittable, status buttons Deposit / Endorse / Mark Cleared / Mark Bounced, each posting a Journal Entry (flow in `erpnext_iran/cheques.py`). Accounts come from ERPNext Iran Settings > Cheque Accounts, else from account numbers 110402, 110401 and 210201 of the Iran chart. Amounts are in the company currency. Sayad ID is only checked for 16 digits
- Bank Account: an Iranian Sheba (IR + 24 digits, with or without IR and spaces) is checked with the ISO 13616 mod 97 test and stored as `IR...`

Not done yet: the Moadian tax-authority integration, Iranian payment gateways.

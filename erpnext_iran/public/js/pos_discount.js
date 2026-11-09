// A cashier who gives more discount than the POS Profile allows needs a manager at the till: the manager types
// their user and password once and the sale goes on. The server checks again when the sale is submitted.
(function () {
	function percent(doc) {
		let listed = 0;
		let given = 0;
		(doc.items || []).forEach((row) => {
			const line = flt(row.price_list_rate) * flt(row.qty);
			listed += line;
			if (line && !row.pricing_rules) given += Math.max(0, line - flt(row.rate) * flt(row.qty));
		});
		given += Math.max(0, flt(doc.discount_amount));
		return listed ? (given / listed) * 100 : 0;
	}

	const MANAGER_ROLES = ['System Manager', 'Sales Manager', 'Accounts Manager'];
	const isManager = () => frappe.session.user === 'Administrator' || MANAGER_ROLES.some((role) => frappe.user_roles.includes(role));

	function askManager() {
		return new Promise((resolve) => {
			const dialog = frappe.prompt(
				[
					{ fieldname: 'manager', label: __('Manager User'), fieldtype: 'Data', options: 'Email', reqd: 1 },
					{ fieldname: 'password', label: __('Password'), fieldtype: 'Password', reqd: 1 },
				],
				async (values) => {
					try {
						const result = await frappe.xcall('erpnext_iran.discount.approve_discount', values);
						resolve(result);
					} catch (error) {
						resolve(null);
					}
				},
				__('Manager Approval Needed'),
				__('Approve')
			);
			dialog.onhide = () => setTimeout(() => resolve(null), 0);
		});
	}

	function patch() {
		const Controller = window.erpnext && erpnext.PointOfSale && erpnext.PointOfSale.Controller;
		if (!Controller) return false;
		if (Controller.prototype._iran_discount) return true;
		Controller.prototype._iran_discount = true;

		const checkout = Controller.prototype.save_and_checkout;
		Controller.prototype.save_and_checkout = async function () {
			const doc = this.frm.doc;
			const limit = flt(this.settings.cashier_discount_limit);
			const over = limit > 0 && limit < 100 && percent(doc) > limit + 0.0001;
			if (over && !isManager() && !doc.discount_approval_token) {
				frappe.show_alert({
					message: __('Discount {0}% is above the cashier limit of {1}%', [format_number(percent(doc), null, 1), limit]),
					indicator: 'orange',
				});
				const approval = await askManager();
				if (!approval) return;
				await frappe.model.set_value(doc.doctype, doc.name, 'discount_approval_token', approval.token);
				frappe.show_alert({ message: __('Approved by {0}', [approval.user]), indicator: 'green' });
			}
			return checkout.apply(this, arguments);
		};
		return true;
	}

	const timer = setInterval(() => patch() && clearInterval(timer), 1000);
})();

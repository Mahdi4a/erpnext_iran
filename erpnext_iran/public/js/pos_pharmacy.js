// A prescription drug in the basket: before payment the till asks for the prescription number and the prescriber, and
// for a controlled drug also the patient and a valid national ID. The server checks again when the sale is submitted.
(function () {
	function validNationalId(value) {
		const code = String(value || '').replace(/[۰-۹]/g, (d) => '۰۱۲۳۴۵۶۷۸۹'.indexOf(d)).trim();
		if (!/^\d{10}$/.test(code) || /^(\d)\1{9}$/.test(code)) return false;
		let total = 0;
		for (let i = 0; i < 9; i++) total += Number(code[i]) * (10 - i);
		const rest = total % 11;
		const control = Number(code[9]);
		return rest < 2 ? control === rest : control === 11 - rest;
	}

	function ask(doc, controlled) {
		return new Promise((resolve) => {
			let submitted = false;
			const dialog = frappe.prompt(
				[
					{ fieldname: 'prescription_no', label: __('Prescription Number'), fieldtype: 'Data', reqd: 1, default: doc.prescription_no },
					{ fieldname: 'prescriber_name', label: __('Prescriber'), fieldtype: 'Data', reqd: 1, default: doc.prescriber_name },
					{ fieldname: 'prescriber_license', label: __('Medical Council Number'), fieldtype: 'Data', default: doc.prescriber_license },
					{ fieldname: 'patient_name', label: __('Patient'), fieldtype: 'Data', reqd: controlled ? 1 : 0, default: doc.patient_name },
					{ fieldname: 'patient_national_id', label: __('Patient National ID'), fieldtype: 'Data', reqd: controlled ? 1 : 0, default: doc.patient_national_id },
				],
				(values) => {
					if (controlled && !validNationalId(values.patient_national_id)) {
						frappe.msgprint(__('The national ID is not valid.'));
						return resolve(null);
					}
					submitted = true;
					resolve(values);
				},
				controlled ? __('Controlled Drug') : __('Prescription'),
				__('Continue')
			);
			dialog.onhide = () => setTimeout(() => !submitted && resolve(null), 0);
		});
	}

	function patch() {
		const Controller = window.erpnext && erpnext.PointOfSale && erpnext.PointOfSale.Controller;
		if (!Controller) return false;
		if (Controller.prototype._iran_pharmacy) return true;
		Controller.prototype._iran_pharmacy = true;

		const checkout = Controller.prototype.save_and_checkout;
		Controller.prototype.save_and_checkout = async function () {
			const doc = this.frm.doc;
			const codes = [...new Set((doc.items || []).map((row) => row.item_code))];
			if (codes.length) {
				const need = await frappe.xcall('erpnext_iran.pharmacy.rx_requirements', { item_codes: codes });
				const controlled = need.controlled.length > 0;
				const missing = need.prescription.length > 0 && (!doc.prescription_no || !doc.prescriber_name || (controlled && (!doc.patient_name || !validNationalId(doc.patient_national_id))));
				if (missing) {
					const values = await ask(doc, controlled);
					if (!values) return;
					for (const [field, value] of Object.entries(values)) await frappe.model.set_value(doc.doctype, doc.name, field, value || '');
				}
			}
			return checkout.apply(this, arguments);
		};
		return true;
	}

	const timer = setInterval(() => patch() && clearInterval(timer), 1000);
})();

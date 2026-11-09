import unittest
from unittest.mock import MagicMock, patch

import frappe

from erpnext_iran import branches


def branch(cashiers, before=None):
	doc = MagicMock()
	doc.pos_profile = "P"
	doc.get.side_effect = lambda key, default=None: [frappe._dict(user=u) for u in cashiers] if key == "cashiers" else default
	old = MagicMock()
	old.get.side_effect = lambda key, default=None: [frappe._dict(user=u) for u in (before or [])]
	doc.get_doc_before_save.return_value = old if before is not None else None
	return doc


def profile(users):
	doc = MagicMock()
	doc.name = "P"
	doc.applicable_for_users = [frappe._dict(user=u) for u in users]
	doc.append.side_effect = lambda field, row: doc.applicable_for_users.append(frappe._dict(row))
	doc.remove.side_effect = lambda row: doc.applicable_for_users.remove(row)
	return doc


class TestSyncCashiers(unittest.TestCase):
	def sync(self, doc, existing, other_default=False):
		with patch.object(branches.frappe.db, "exists", side_effect=lambda *a, **k: other_default if isinstance(a[0], str) and a[0] == "POS Profile User" else True), patch.object(
			branches.frappe, "get_doc", return_value=existing
		):
			branches.sync_cashiers(doc)
		return existing

	def test_listed_users_become_users_of_the_profile(self):
		p = self.sync(branch(["a@x", "b@x"]), profile([]))
		self.assertEqual([r.user for r in p.applicable_for_users], ["a@x", "b@x"])
		self.assertTrue(all(r.default == 1 for r in p.applicable_for_users))
		p.save.assert_called_once()

	def test_a_user_who_already_has_another_default_gets_no_second_default(self):
		p = self.sync(branch(["a@x"]), profile([]), other_default=True)
		self.assertEqual(p.applicable_for_users[0].default, 0)

	def test_a_removed_cashier_leaves_the_profile_but_a_hand_added_user_stays(self):
		p = self.sync(branch(["a@x"], before=["a@x", "gone@x"]), profile(["a@x", "gone@x", "manual@x"]))
		self.assertEqual([r.user for r in p.applicable_for_users], ["a@x", "manual@x"])

	def test_nothing_changed_nothing_saved(self):
		p = self.sync(branch(["a@x"], before=["a@x"]), profile(["a@x"]))
		p.save.assert_not_called()

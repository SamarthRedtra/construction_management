# Copyright (c) 2026, Construction Management and Contributors
# See license.txt

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from construction_management.api.security_instrument import build_reclaim_payment_entry_values
from construction_management.overrides.payment_entry import sync_security_instrument_status


# On IntegrationTestCase, the doctype test records and all
# link-field test record dependencies are recursively loaded
# Use these module variables to add/remove to/from that list
EXTRA_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]
IGNORE_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]



class IntegrationTestSecurityInstrument(IntegrationTestCase):
	def test_build_reclaim_payment_entry_values_inverts_pay_to_receive(self):
		instrument = frappe._dict({
			"name": "SEC-0001",
			"instrument_type": "Security Deposit",
			"amount": 2500,
		})
		issue_payment_entry = frappe._dict({
			"payment_type": "Pay",
			"paid_from": "Bank - TEST",
			"party_type": "Supplier",
			"party": "Supp-1",
			"company": "Test Company",
			"project": "PROJ-1",
			"mode_of_payment": "Bank",
			"reference_no": "REF-1",
			"reference_date": "2026-03-14",
		})

		values = build_reclaim_payment_entry_values(instrument, issue_payment_entry)

		self.assertEqual(values["payment_type"], "Receive")
		self.assertEqual(values["paid_to"], "Bank - TEST")
		self.assertEqual(values["custom_security_entry_role"], "Reclaim")
		self.assertEqual(values["custom_is_security_deposit"], 1)
		self.assertEqual(values["custom_is_security_cheque"], 0)
		self.assertEqual(values.get("custom_is_authorization_fees", 0), 0)
		self.assertEqual(values["custom_security_redeemed"], 0)

	def test_build_reclaim_payment_entry_values_inverts_receive_to_pay(self):
		instrument = frappe._dict({
			"name": "SEC-0002",
			"instrument_type": "Security Cheque",
			"amount": 1800,
		})
		issue_payment_entry = frappe._dict({
			"payment_type": "Receive",
			"paid_to": "Bank - TEST",
			"party_type": "Customer",
			"party": "Cust-1",
			"company": "Test Company",
			"project": "PROJ-2",
			"mode_of_payment": "Cheque",
			"reference_no": "CHQ-1",
			"reference_date": "2026-03-14",
		})

		values = build_reclaim_payment_entry_values(instrument, issue_payment_entry)

		self.assertEqual(values["payment_type"], "Pay")
		self.assertEqual(values["paid_from"], "Bank - TEST")
		self.assertEqual(values["custom_is_security_cheque"], 1)
		self.assertEqual(values["custom_is_security_deposit"], 0)
		self.assertEqual(values.get("custom_is_authorization_fees", 0), 0)
		self.assertEqual(values["custom_security_redeemed"], 0)

	def test_build_reclaim_payment_entry_values_authorization_fees(self):
		instrument = frappe._dict({
			"name": "SEC-0003",
			"instrument_type": "Authorization Fees",
			"amount": 500,
		})
		issue_payment_entry = frappe._dict({
			"payment_type": "Receive",
			"paid_to": "Bank - TEST",
			"party_type": "Customer",
			"party": "Cust-1",
			"company": "Test Company",
			"project": "PROJ-3",
			"mode_of_payment": "Bank",
			"reference_no": "AUTH-1",
			"reference_date": "2026-03-20",
		})

		values = build_reclaim_payment_entry_values(instrument, issue_payment_entry)

		self.assertEqual(values["payment_type"], "Pay")
		self.assertEqual(values["paid_from"], "Bank - TEST")
		self.assertEqual(values.get("custom_is_authorization_fees", 0), 1)
		self.assertEqual(values["custom_is_security_cheque"], 0)
		self.assertEqual(values["custom_is_security_deposit"], 0)
		self.assertEqual(values["custom_security_redeemed"], 0)

	def test_sync_security_instrument_status_marks_issue_entries_as_issued(self):
		instrument = MagicMock()
		doc = frappe._dict({
			"custom_security_instrument": "SEC-0001",
		})

		with patch(
			"construction_management.overrides.payment_entry.frappe.db.exists",
			return_value=True,
		), patch(
			"construction_management.overrides.payment_entry.frappe.get_doc",
			return_value=instrument,
		):
			sync_security_instrument_status(doc, "Issued")

		instrument.mark_issued.assert_called_once()
		instrument.mark_reclaimed.assert_not_called()

	def test_sync_security_instrument_status_reclaim_cancel_reverts_to_issued(self):
		instrument = MagicMock()
		instrument.payment_entry = "PAY-ISSUE-1"
		issue_entry = frappe._dict({"docstatus": 1})
		doc = frappe._dict({
			"custom_security_instrument": "SEC-0001",
			"custom_security_entry_role": "Reclaim",
		})

		with patch(
			"construction_management.overrides.payment_entry.frappe.db.exists",
			return_value=True,
		), patch(
			"construction_management.overrides.payment_entry.frappe.get_doc",
			side_effect=[instrument, issue_entry],
		):
			sync_security_instrument_status(doc, "Cancelled")

		instrument.revert_to_issued.assert_called_once()

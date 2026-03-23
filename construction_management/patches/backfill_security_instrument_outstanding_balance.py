# Copyright (c) 2026, Construction Management
# License: MIT

import frappe

from construction_management.construction_management.doctype.security_instrument.security_instrument import (
	persist_security_instrument_outstanding_balance,
)


def execute():
	for name in frappe.get_all("Security Instrument", pluck="name"):
		persist_security_instrument_outstanding_balance(name)

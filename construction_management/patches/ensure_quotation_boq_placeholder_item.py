# Copyright (c) 2026, Construction Management
# License: MIT

import frappe

from construction_management.overrides.quotation import _get_or_create_placeholder_item


def execute():
	_get_or_create_placeholder_item(None)
	frappe.db.commit()

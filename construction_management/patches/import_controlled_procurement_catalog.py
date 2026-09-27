# Copyright (c) 2026, Construction Management
# License: MIT

"""Seed the approved controlled procurement catalog on each site once."""

import frappe

from construction_management.api.controlled_procurement import import_packaged_catalog
from construction_management.setup.install import create_controlled_procurement_fields


def execute():
	create_controlled_procurement_fields()
	frappe.clear_cache(doctype="Item")
	result = import_packaged_catalog()
	frappe.logger("controlled_procurement").info({"event": "catalog_import", **result})

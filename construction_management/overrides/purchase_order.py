# Copyright (c) 2026, Construction Management
# License: MIT

import frappe
from frappe import _
from construction_management.api.drum_uom_utils import apply_drum_uom_conversion_for_items


def validate(doc, method):
    """
    Set default site to 'Transit' if blank to resolve mandatory dimension errors.
    """
    apply_drum_uom_conversion_for_items(doc.get("items"))
    # Auto-fill blank custom site fields to resolve mandatory dimension errors
    for row in doc.get("items", []):
        if not row.get("site") and frappe.get_meta(row.doctype).has_field("site"):
            row.site = "Transit"
        if not row.get("rejected_site") and frappe.get_meta(row.doctype).has_field("rejected_site"):
            row.rejected_site = "Transit"

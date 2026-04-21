# Copyright (c) 2026, Construction Management
# License: MIT

import frappe
from frappe import _

def validate(doc, method):
    """
    Set default site to 'Transit' if blank to resolve mandatory dimension errors.
    """
    # Auto-fill blank custom site fields to resolve mandatory dimension errors
    for row in doc.get("items", []):
        if not row.get("site") and frappe.get_meta(row.doctype).has_field("site"):
            row.site = "Transit"
        if not row.get("rejected_site") and frappe.get_meta(row.doctype).has_field("rejected_site"):
            row.rejected_site = "Transit"

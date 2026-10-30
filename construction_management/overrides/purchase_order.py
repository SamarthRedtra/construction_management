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


DEFAULT_SERIES = {"", "PUR-ORD-.YYYY.-"}


def set_company_naming_series(doc, method=None):
    """Name new POs in the company's LPO series unless another series was chosen explicitly."""
    from construction_management.api.controlled_procurement import _is_mrg_company
    from construction_management.api.project_numbering import is_skada_company

    if doc.get("amended_from") or (doc.get("naming_series") or "") not in DEFAULT_SERIES:
        return
    if is_skada_company(doc.company):
        doc.naming_series = "SKD-LPO-"
    elif _is_mrg_company(doc.company):
        doc.naming_series = "MRG-LPO-"

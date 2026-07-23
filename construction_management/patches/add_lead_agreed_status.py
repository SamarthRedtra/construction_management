# Copyright (c) 2026, Construction Management
# License: MIT

"""Ensure Lead.Status includes Agreed for Quotation agreement sync."""

from construction_management.overrides.quotation import _ensure_lead_agreed_status_option


def execute():
	_ensure_lead_agreed_status_option()

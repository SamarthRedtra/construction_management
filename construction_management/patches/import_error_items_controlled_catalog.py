# Copyright (c) 2026, Construction Management
# License: MIT

"""Import Error Items spreadsheet into the controlled procurement catalogue."""


def execute():
	from construction_management.api.error_items_catalog_import import submit

	submit()

# Copyright (c) 2026, Construction Management
# License: MIT

from construction_management.api.bulk_material_issue import reverse_bulk_material_issue


def on_cancel(doc, method=None):
	reverse_bulk_material_issue(doc)

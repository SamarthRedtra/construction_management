"""Install the Purchase Order group hold after DocType synchronization."""

from construction_management.setup.install import create_lpo_fields


def execute():
	create_lpo_fields()

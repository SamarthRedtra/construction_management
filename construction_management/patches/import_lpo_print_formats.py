# Copyright (c) 2026, Construction Management
# License: MIT

import os

import frappe
from frappe.modules.import_file import import_file_by_path

LPO_MRG_SKADA = "LPO MRG Skada"
LPO_PF = "LPO PF"
MODULE = "Construction Management"


def execute():
	_ensure_print_format_for("DocType")
	_import_format(LPO_MRG_SKADA)
	_sync_lpo_pf_html()
	frappe.db.commit()


def _ensure_print_format_for(value: str) -> None:
	if not frappe.get_meta("Print Format").has_field("print_format_for"):
		return
	frappe.db.sql(
		"""
		UPDATE `tabPrint Format`
		SET print_format_for = %(value)s
		WHERE name IN %(names)s
			AND (print_format_for IS NULL OR print_format_for = '')
		""",
		{"value": value, "names": (LPO_MRG_SKADA, LPO_PF)},
	)


def _import_format(print_format_name: str) -> None:
	module_path = frappe.get_module_path(MODULE, "Print Format", print_format_name)
	json_path = os.path.join(module_path, f"{frappe.scrub(print_format_name)}.json")
	if not os.path.exists(json_path):
		return
	import_file_by_path(json_path, force=True)
	html_path = os.path.join(module_path, f"{frappe.scrub(print_format_name)}.html")
	if os.path.isfile(html_path):
		with open(html_path, encoding="utf-8") as handle:
			frappe.db.set_value("Print Format", print_format_name, "html", handle.read(), update_modified=False)


def _sync_lpo_pf_html() -> None:
	module_path = frappe.get_module_path(MODULE, "Print Format", LPO_PF)
	html_path = os.path.join(module_path, "lpo_pf.html")
	if not os.path.isfile(html_path):
		return
	with open(html_path, encoding="utf-8") as handle:
		html = handle.read()
	if frappe.db.exists("Print Format", LPO_PF):
		frappe.db.set_value(
			"Print Format",
			LPO_PF,
			{"html": html, "print_format_type": "Jinja", "doc_type": "Purchase Order"},
			update_modified=True,
		)
	else:
		import_file_by_path(os.path.join(module_path, "lpo_pf.json"), force=True)
		frappe.db.set_value("Print Format", LPO_PF, "html", html, update_modified=False)
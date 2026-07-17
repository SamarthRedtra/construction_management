# Copyright (c) 2026, Construction Management
# License: MIT

"""Seed Project Tab Access from Redtra Access.xlsx matrix (name → User matching)."""

from __future__ import annotations

import frappe

from construction_management.construction_management.doctype.project_tab_access.project_tab_access import (
	COMMISSION_SPECIFIC_ROLE,
)

# Columns from Redtra Access.xlsx (Costing/Progress intentionally omitted — always hidden).
TAB_COLUMNS = [
	"Details",
	"Connections",
	"Construction",
	"Approved Materials",
	"Accounting",
	"Project SOA",
	"Commission",
]

# Sheet rows: Name → {tab: Y|N|S}. Blank Costing/Progress treated as N globally.
ACCESS_MATRIX = [
	{
		"name": "Faraaz",
		"access": {
			"Details": "Y",
			"Connections": "Y",
			"Construction": "Y",
			"Approved Materials": "Y",
			"Accounting": "Y",
			"Project SOA": "Y",
			"Commission": "Y",
		},
	},
	{
		"name": "Salman",
		"access": {
			"Details": "Y",
			"Connections": "Y",
			"Construction": "Y",
			"Approved Materials": "Y",
			"Accounting": "Y",
			"Project SOA": "Y",
			"Commission": "Y",
		},
	},
	{
		"name": "Taqreeb",
		"access": {
			"Details": "Y",
			"Connections": "N",
			"Construction": "Y",
			"Approved Materials": "Y",
			"Accounting": "N",
			"Project SOA": "Y",
			"Commission": "S",
		},
	},
	{
		"name": "Suhana",
		"access": {
			"Details": "Y",
			"Connections": "Y",
			"Construction": "Y",
			"Approved Materials": "Y",
			"Accounting": "Y",
			"Project SOA": "Y",
			"Commission": "Y",
		},
	},
	{
		"name": "Gul",
		"access": {
			"Details": "Y",
			"Connections": "Y",
			"Construction": "Y",
			"Approved Materials": "N",
			"Accounting": "Y",
			"Project SOA": "Y",
			"Commission": "Y",
		},
	},
	{
		"name": "Khaliq",
		"access": {
			"Details": "Y",
			"Connections": "Y",
			"Construction": "Y",
			"Approved Materials": "N",
			"Accounting": "Y",
			"Project SOA": "Y",
			"Commission": "Y",
		},
	},
	{
		"name": "Saqib",
		"access": {
			"Details": "S",
			"Connections": "N",
			"Construction": "S",
			"Approved Materials": "S",
			"Accounting": "N",
			"Project SOA": "S",
			"Commission": "S",
		},
	},
	{
		"name": "Atif",
		"access": {
			"Details": "Y",
			"Connections": "N",
			"Construction": "N",
			"Approved Materials": "Y",
			"Accounting": "N",
			"Project SOA": "N",
			"Commission": "N",
		},
	},
	{
		"name": "Irsath",
		"access": {
			"Details": "Y",
			"Connections": "N",
			"Construction": "N",
			"Approved Materials": "Y",
			"Accounting": "N",
			"Project SOA": "N",
			"Commission": "N",
		},
	},
	{
		"name": "Asma",
		"access": {
			"Details": "Y",
			"Connections": "N",
			"Construction": "N",
			"Approved Materials": "Y",
			"Accounting": "N",
			"Project SOA": "N",
			"Commission": "N",
		},
	},
	{
		"name": "Waqar",
		"access": {
			"Details": "Y",
			"Connections": "N",
			"Construction": "Y",
			"Approved Materials": "Y",
			"Accounting": "N",
			"Project SOA": "Y",
			"Commission": "S",
		},
	},
	{
		"name": "Shavez",
		"access": {
			"Details": "Y",
			"Connections": "Y",
			"Construction": "Y",
			"Approved Materials": "Y",
			"Accounting": "N",
			"Project SOA": "Y",
			"Commission": "N",
		},
	},
	{
		"name": "Tanveer",
		"access": {
			"Details": "Y",
			"Connections": "Y",
			"Construction": "Y",
			"Approved Materials": "Y",
			"Accounting": "N",
			"Project SOA": "Y",
			"Commission": "N",
		},
	},
	{
		"name": "Faiz",
		"access": {
			"Details": "Y",
			"Connections": "N",
			"Construction": "Y",
			"Approved Materials": "Y",
			"Accounting": "N",
			"Project SOA": "Y",
			"Commission": "N",
		},
	},
	{
		"name": "Suveesh",
		"access": {
			"Details": "Y",
			"Connections": "N",
			"Construction": "Y",
			"Approved Materials": "Y",
			"Accounting": "N",
			"Project SOA": "Y",
			"Commission": "N",
		},
	},
	{
		"name": "Junaid",
		"access": {
			"Details": "Y",
			"Connections": "Y",
			"Construction": "N",
			"Approved Materials": "Y",
			"Accounting": "N",
			"Project SOA": "Y",
			"Commission": "N",
		},
	},
	{
		"name": "Shayan",
		"access": {
			"Details": "Y",
			"Connections": "Y",
			"Construction": "N",
			"Approved Materials": "Y",
			"Accounting": "N",
			"Project SOA": "Y",
			"Commission": "N",
		},
	},
	{
		"name": "Engineers",
		"is_role_group": True,
		"roles": ["Site Engineer", "project engineer"],
		"access": {
			"Details": "S",
			"Connections": "N",
			"Construction": "N",
			"Approved Materials": "Y",
			"Accounting": "N",
			"Project SOA": "N",
			"Commission": "N",
		},
	},
	{
		"name": "Ahbab",
		"access": {
			"Details": "Y",
			"Connections": "N",
			"Construction": "Y",
			"Approved Materials": "Y",
			"Accounting": "N",
			"Project SOA": "Y",
			"Commission": "S",
		},
	},
]

# Explicit overrides for ambiguous / multi-company matches (sheet name → user emails).
EXPLICIT_USER_MAP = {
	"Faraaz": ["faraaz@mrggroup.ae"],
	"Salman": ["salman@mrggroup.ae"],
	"Taqreeb": ["taqreeb@mrggroup.ae"],
	"Suhana": ["accounts@mrggroup.ae", "accounts1@skada.ae"],
	"Gul": ["accounts@skada.ae", "accounts1@mrggroup.ae"],
	"Khaliq": ["khaliqacc.mrggroup@gmail.com", "khaliqacc.skada@gmail.com"],
	"Saqib": ["saqib@mrggroup.ae"],
	"Atif": ["admin@mrggroup.ae"],
	"Irsath": ["dc@mrggroup.ae", "dc@skada.ae"],
	"Asma": ["support@mrggroup.ae"],
	"Waqar": ["waqar@mrggroup.ae"],
	"Shavez": ["shavez.mrggroup@gmail.com"],
	"Faiz": ["faiz@mrggroup.ae"],
	"Suveesh": ["suveesh.mrg@gmail.com"],
	"Junaid": ["procurement@mrg.ae", "procurement@skada.ae", "purchase@mrggroup.ae"],
	"Shayan": ["shayan.mrggroup@gmail.com", "shayan.skada@gmail.com"],
	"Ahbab": ["billingcontrol@mrggroup.ae"],
}


def execute():
	_ensure_access_mode_columns()
	settings = frappe.get_single("Project Tab Access")
	settings.enabled = 1
	settings.set("rules", [])

	matched = 0
	skipped = []

	for row in ACCESS_MATRIX:
		sheet_name = row["name"]
		access = row["access"]

		if row.get("is_role_group"):
			for role in row.get("roles") or []:
				if not frappe.db.exists("Role", role):
					frappe.logger("construction_management").warning(
						f"Redtra tab access: role {role!r} not found for {sheet_name}"
					)
					continue
				_append_rules_for_subject(settings, access, role=role)
				matched += 1
			continue

		users = _resolve_users(sheet_name)
		if not users:
			skipped.append(sheet_name)
			frappe.logger("construction_management").warning(
				f"Redtra tab access: no User match for {sheet_name!r}"
			)
			continue

		for user in users:
			_append_rules_for_subject(settings, access, user=user)
			matched += 1

	settings.save(ignore_permissions=True)
	frappe.db.commit()

	if skipped:
		frappe.msgprint(
			f"Project Tab Access seeded. Matched subjects: {matched}. Skipped names: {', '.join(skipped)}",
			alert=True,
		)
	else:
		frappe.msgprint(f"Project Tab Access seeded for {matched} subjects.", alert=True)


def _ensure_access_mode_columns():
	"""Add access_mode / required_role columns if migrate has not run yet."""
	table = "tabProject Tab Access Rule"
	if not frappe.db.table_exists("Project Tab Access Rule"):
		return

	columns = {row[0] for row in frappe.db.sql(f"SHOW COLUMNS FROM `{table}`")}
	if "access_mode" not in columns:
		frappe.db.sql(
			f"ALTER TABLE `{table}` ADD COLUMN `access_mode` varchar(140) DEFAULT 'Y'"
		)
	if "required_role" not in columns:
		frappe.db.sql(
			f"ALTER TABLE `{table}` ADD COLUMN `required_role` varchar(140) DEFAULT NULL"
		)


def _resolve_users(sheet_name: str) -> list[str]:
	explicit = EXPLICIT_USER_MAP.get(sheet_name) or []
	users = [u for u in explicit if frappe.db.exists("User", u)]
	if users:
		return users

	# Fuzzy fallback by full_name first token
	needle = sheet_name.strip().upper()
	rows = frappe.db.sql(
		"""
		SELECT name, full_name
		FROM `tabUser`
		WHERE enabled = 1
			AND name NOT IN ('Guest', 'Administrator')
			AND (
				UPPER(full_name) LIKE %(like)s
				OR UPPER(name) LIKE %(like)s
			)
		""",
		{"like": f"%{needle}%"},
		as_dict=True,
	)
	return [r.name for r in rows]


def _append_rules_for_subject(settings, access: dict, user: str | None = None, role: str | None = None):
	y_tabs = []
	s_tabs = []

	for tab in TAB_COLUMNS:
		flag = (access.get(tab) or "N").strip().upper()
		if flag == "Y":
			y_tabs.append(tab)
		elif flag == "S":
			# Non-Commission S treated as allow (Y). Commission S stays specific.
			if tab in ("Commission", "Project Commission"):
				s_tabs.append("Commission")
			else:
				y_tabs.append(tab)

	if y_tabs:
		settings.append(
			"rules",
			{
				"tabs": ", ".join(y_tabs),
				"user": user or "",
				"role": role or "",
				"access_mode": "Y",
				"required_role": "",
			},
		)

	if s_tabs:
		settings.append(
			"rules",
			{
				"tabs": ", ".join(s_tabs),
				"user": user or "",
				"role": role or "",
				"access_mode": "S",
				"required_role": COMMISSION_SPECIFIC_ROLE,
			},
		)

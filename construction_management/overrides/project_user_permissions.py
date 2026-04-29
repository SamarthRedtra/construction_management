# Copyright (c) 2024, Construction Management
# License: MIT

"""
Monkey-patch to exclude Project Engineer and Sales Engineer from user permission filtering.

When user has User Permission restricted to Company (e.g. MRG only), the Project list view
was incorrectly filtering out projects where the Project Engineer links to an Employee from
another company.

Two places need patching:
1. Engine.get_doctype_link_fields - exclude these fields from Project's user permission WHERE
2. LinkTableField.apply_join - when fetching custom_project_engineer.employee_name, the JOIN
   to Employee applies permission conditions on the joined table, filtering out projects
   whose Project Engineer is from another company. We must skip that for these fields.
"""

import frappe

# Fields to exclude from user permission filtering on Project (Employee links)
PROJECT_ENGINEER_FIELDS = {"custom_project_engineer", "custom_sales_engineer"}


def _patched_get_doctype_link_fields(self, doctype=None):
	"""Exclude Project Engineer fields from user permission check for Project."""
	doctype = doctype or self.permission_doctype
	meta = frappe.get_meta(doctype)
	doctype_link_fields = [{"options": doctype, "fieldname": "name"}]
	link_fields = meta.get_link_fields()

	if doctype == "Project":
		def _fieldname(df):
			return getattr(df, "fieldname", None) or (df.get("fieldname") if hasattr(df, "get") else None)
		link_fields = [df for df in link_fields if _fieldname(df) not in PROJECT_ENGINEER_FIELDS]

	doctype_link_fields.extend(link_fields)
	return doctype_link_fields


def _patched_link_table_apply_select(self, query, engine=None):
	"""Alias table fields correctly for related Link queries."""
	table = frappe.qb.DocType(self.doctype)
	if self.parent_doctype == "Project" and self.link_fieldname in PROJECT_ENGINEER_FIELDS:
		table = table.as_(f"tab{self.doctype}_{self.link_fieldname}")
	query = self.apply_join(query, engine=engine)
	return query.select(getattr(table, self.fieldname).as_(self.alias or None))


def _patched_link_table_apply_join(self, query, engine=None):
	"""Skip permission conditions on Employee join for Project Engineer fields and apply aliases."""
	table = frappe.qb.DocType(self.doctype)
	if self.parent_doctype == "Project" and self.link_fieldname in PROJECT_ENGINEER_FIELDS:
		table = table.as_(f"tab{self.doctype}_{self.link_fieldname}")
		
	main_table = frappe.qb.DocType(self.parent_doctype)
	if not query.is_joined(table):
		query = query.left_join(table).on(table.name == getattr(main_table, self.link_fieldname))
		# Skip Employee permission filter for Project Engineer/Sales Engineer - they may be from another company
		skip_join_perms = (
			self.parent_doctype == "Project"
			and self.link_fieldname in PROJECT_ENGINEER_FIELDS
		)
		if engine and engine.apply_permissions and not skip_join_perms:
			if condition := engine.get_permission_conditions(self.doctype, table):
				query = query.where(condition)

	return query


def patch_project_user_permissions():
	"""Apply monkey-patches for Project list view user permissions."""
	from frappe.database.query import Engine, LinkTableField

	if not hasattr(Engine, "_project_perm_patched"):
		print("patching project user permissions")
		Engine.get_doctype_link_fields = _patched_get_doctype_link_fields
		LinkTableField.apply_join = _patched_link_table_apply_join
		LinkTableField.apply_select = _patched_link_table_apply_select
		Engine._project_perm_patched = True


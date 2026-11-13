import frappe
from frappe.query_builder.functions import Count


def execute():
	"""Remove duplicate Raven Workspace Member rows (same workspace + user); keep the oldest."""
	if not frappe.db.exists("DocType", "Raven Workspace Member"):
		return

	workspace_member = frappe.qb.DocType("Raven Workspace Member")

	duplicates = (
		frappe.qb.from_(workspace_member)
		.select(
			workspace_member.workspace,
			workspace_member.user,
			Count(workspace_member.name).as_("count"),
		)
		.groupby(workspace_member.workspace, workspace_member.user)
		.having(Count(workspace_member.name) > 1)
	).run(as_dict=True)

	if not duplicates:
		return

	deleted = frappe.db.sql(
		"""
		DELETE rwm FROM `tabRaven Workspace Member` rwm
		INNER JOIN (
			SELECT workspace, user, MIN(creation) AS min_creation
			FROM `tabRaven Workspace Member`
			GROUP BY workspace, user
			HAVING COUNT(*) > 1
		) dup
		ON rwm.workspace = dup.workspace
		   AND rwm.user = dup.user
		   AND rwm.creation > dup.min_creation
		"""
	)

	# frappe.db.sql DELETE returns rowcount on MariaDB via cursor; log pairs cleaned
	frappe.logger().info(
		"dedupe_raven_workspace_members: %s duplicate (workspace, user) groups",
		len(duplicates),
	)

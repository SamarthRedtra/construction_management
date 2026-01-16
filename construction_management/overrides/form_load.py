import frappe
from frappe.desk.form import load as core_load
from frappe.desk.form.load import get_meta_bundle as core_get_meta_bundle


def _prefer_custom_over_standard_fields(meta):
	"""
	When a custom field reuses an existing fieldname, prefer the custom field.
	Limited to Purchase Invoice to resolve bill_no/supplier_invoice_no clash.
	"""
	if meta.name != "Purchase Invoice":
		return

	fields = list(meta.get("fields") or [])
	if not fields:
		return

	by_name = {}
	for df in reversed(fields):
		fname = df.fieldname
		if not fname:
			continue

		# For bill_no keep only the Project Bill link; drop any other bill_no definition
		# or legacy fields that carried the oldfieldname bill_no.
		if fname == "bill_no" or df.get("oldfieldname") == "bill_no":
			is_project_link = df.fieldtype == "Link" and df.options == "BOQ Bill"
			if not is_project_link:
				continue

		if fname in by_name:
			continue

		by_name[fname] = df

	# If we somehow removed bill_no, re-add it from Custom Field definition.
	# If we somehow removed bill_no, re-add it from Custom Field definition.
	if "bill_no" not in by_name:
		cf = frappe.get_value(
			"Custom Field",
			{"dt": "Purchase Invoice", "fieldname": "bill_no"},
			["fieldname", "label", "fieldtype", "options", "insert_after", "idx"],
			as_dict=True,
		)
		if cf and cf.fieldtype == "Link" and cf.options == "BOQ Bill":
			by_name["bill_no"] = frappe._dict(
				is_custom_field=1,
				**cf,
			)

	# Move bill_no just after project for visibility (avoid hiding under Supplier Invoice section).
	project_idx = by_name.get("project", frappe._dict(idx=0)).idx or 0
	bill = by_name.get("bill_no")
	if bill:
		bill.insert_after = "project"
		# place just after project in ordering
		bill.idx = project_idx + 0.1
		by_name["bill_no"] = bill

	meta.fields = sorted(by_name.values(), key=lambda d: d.idx or 0)


def _get_meta_bundle_with_custom_preference(doctype):
	bundle = core_get_meta_bundle(doctype)
	for meta in bundle:
		_prefer_custom_over_standard_fields(meta)
	return bundle


@frappe.whitelist()
def getdoctype(doctype, with_parent: bool = False):
	"""Load doctype metadata, preferring custom fields when names clash."""
	docs = []
	parent_dt = None

	if with_parent and (parent_dt := frappe.model.meta.get_parent_dt(doctype)):
		docs = _get_meta_bundle_with_custom_preference(parent_dt)
		frappe.response["parent_dt"] = parent_dt

	if not docs:
		docs = _get_meta_bundle_with_custom_preference(doctype)

	frappe.response.setdefault("docs", []).extend(docs)
	frappe.response["user_settings"] = core_load.get_user_settings(parent_dt or doctype)

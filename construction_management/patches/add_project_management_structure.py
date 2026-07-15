# Copyright (c) 2026, Construction Management
# License: MIT

import json

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field


DETAILS_FIELD_ORDER = [
	"naming_series",
	"custom_project_info_section",
	"custom_project_no",
	"custom_contract_name",
	"project_name",
	"custom_project_short_name",
	"custom_project_info_col_break_1",
	"custom_location",
	"custom_emirates",
	"expected_start_date",
	"expected_end_date",
	"custom_project_info_col_break_2",
	"status",
	"project_type",
	"is_active",
	"column_break_5",
	"priority",
	"department",
	"custom_payment_terms_summary_section",
	"advance_deduction",
	"enable_progressive_boq",
	"retention_percentage",
	"custom_payment_terms_summary_col",
	"custom_project_allocation_section",
	"custom_project_team",
	"custom_project_team_html",
	"custom_project_engineer",
	"custom_sales_engineer",
	"project_template",
	"connections_tab",
	"construction_tab",
	"construction_details_section",
	"company",
	"project_type_construction",
	"consultant",
	"column_break_construction",
	"site_location",
	"contractor",
	"budget_control_section",
	"budget_enforcement_level",
	"budget_mode",
	"budget_threshold_percent",
	"custom_payment_terms",
	"custom_payment_terms_data",
	"custom_payment_terms_html",
	"custom_approved_materials",
	"custom_approved_materials_data",
	"custom_approved_materials_html",
	"construction_dashboard_section",
	"construction_dashboard",
	"financial_section_break",
	"total_revenue",
	"total_estimated_cost",
	"total_actual_cost",
	"total_estimated_gp",
	"project_gp_percentage",
	"financial_column_break",
	"total_retention_retained",
	"total_retention_released",
	"total_retention_balance",
	"total_advance_given",
	"total_advance_utilized",
	"total_advance_available",
	"project_net_receivable",
	"section_break_18",
	"actual_start_date",
	"actual_time",
	"column_break_20",
	"actual_end_date",
	"custom_more_information",
	"customer_details",
	"customer",
	"column_break_14",
	"sales_order",
	"custom_section_break_gylqi",
	"custom_column_break_wnbrl",
	"custom_default_billing_mode",
	"percent_complete",
	"percent_complete_method",
	"users_section",
	"users",
	"copied_from",
	"section_break0",
	"notes",
	"costing_tab",
	"project_details",
	"estimated_costing",
	"total_costing_amount",
	"total_expense_claim",
	"total_purchase_cost",
	"column_break_28",
	"total_sales_amount",
	"total_billable_amount",
	"total_billed_amount",
	"total_consumed_material_cost",
	"cost_center",
	"margin",
	"gross_margin",
	"column_break_37",
	"per_gross_margin",
	"monitor_progress_tab",
	"collect_progress",
	"holiday_list",
	"frequency",
	"from_time",
	"to_time",
	"first_email",
	"second_email",
	"daily_time_to_send",
	"day_to_send",
	"weekly_time_to_send",
	"column_break_45",
	"subject",
	"message",
	"more_info_tab",
	"project_soa_tab",
	"project_soa_section",
	"project_soa_html",
	"project_commission_tab",
	"project_commission_section",
	"project_commission_html",
	"custom_dashboard",
]


def execute():
	_ensure_project_team_member_doctype()
	_create_custom_fields()
	_update_field_order()
	_update_field_labels()
	_hide_legacy_allocation_fields()
	_migrate_legacy_team_members()
	frappe.clear_cache(doctype="Project")


def _ensure_project_team_member_doctype():
	if frappe.db.exists("DocType", "Project Team Member"):
		return
	frappe.reload_doc("construction_management", "doctype", "project_team_member")


def _create_custom_fields():
	fields = [
		{
			"fieldname": "custom_project_info_section",
			"label": "Project Information",
			"fieldtype": "Section Break",
			"insert_after": "naming_series",
			"collapsible": 0,
		},
		{
			"fieldname": "custom_contract_name",
			"label": "Contract Name",
			"fieldtype": "Data",
			"insert_after": "custom_project_no",
		},
		{
			"fieldname": "custom_project_info_col_break_1",
			"fieldtype": "Column Break",
			"insert_after": "custom_project_short_name",
		},
		{
			"fieldname": "custom_project_info_col_break_2",
			"fieldtype": "Column Break",
			"insert_after": "expected_end_date",
		},
		{
			"fieldname": "custom_payment_terms_summary_section",
			"label": "Payment Terms",
			"fieldtype": "Section Break",
			"insert_after": "department",
			"collapsible": 1,
		},
		{
			"fieldname": "custom_payment_terms_summary_col",
			"fieldtype": "Column Break",
			"insert_after": "retention_percentage",
		},
		{
			"fieldname": "custom_project_allocation_section",
			"label": "Project Management Structure",
			"fieldtype": "Section Break",
			"insert_after": "custom_payment_terms_summary_col",
			"collapsible": 1,
		},
		{
			"fieldname": "custom_project_team",
			"label": "Project Team",
			"fieldtype": "Table",
			"insert_after": "custom_project_allocation_section",
			"options": "Project Team Member",
			"hidden": 1,
		},
		{
			"fieldname": "custom_project_team_html",
			"label": "Team Allocation",
			"fieldtype": "HTML",
			"insert_after": "custom_project_team",
		},
	]

	for field in fields:
		if not frappe.db.exists("Custom Field", {"dt": "Project", "fieldname": field["fieldname"]}):
			create_custom_field("Project", field)


def _update_field_order():
	prop_name = "Project-main-field_order"
	if frappe.db.exists("Property Setter", prop_name):
		frappe.db.set_value("Property Setter", prop_name, "value", json.dumps(DETAILS_FIELD_ORDER))
	else:
		frappe.get_doc(
			{
				"doctype": "Property Setter",
				"doc_type": "Project",
				"doctype_or_field": "DocType",
				"property": "field_order",
				"property_type": "Data",
				"value": json.dumps(DETAILS_FIELD_ORDER),
			}
		).insert(ignore_permissions=True)


def _update_field_labels():
	labels = {
		"custom_project_no": "Project Number",
		"custom_location": "Location",
		"custom_emirates": "Emirate",
		"expected_start_date": "Start Date",
		"expected_end_date": "End Date",
		"advance_deduction": "Advance Payment %",
		"enable_progressive_boq": "Progressive Payment",
		"retention_percentage": "Retention %",
	}
	for fieldname, label in labels.items():
		_set_field_label(fieldname, label)


def _set_field_label(fieldname, label):
	custom_name = frappe.db.get_value("Custom Field", {"dt": "Project", "fieldname": fieldname})
	if custom_name:
		frappe.db.set_value("Custom Field", custom_name, "label", label)
		return

	prop_name = f"Project-{fieldname}-label"
	if frappe.db.exists("Property Setter", prop_name):
		frappe.db.set_value("Property Setter", prop_name, "value", label)
	else:
		frappe.get_doc(
			{
				"doctype": "Property Setter",
				"doc_type": "Project",
				"doctype_or_field": "DocField",
				"field_name": fieldname,
				"property": "label",
				"value": label,
			}
		).insert(ignore_permissions=True)


def _hide_legacy_allocation_fields():
	for fieldname in ("custom_project_engineer", "custom_sales_engineer"):
		custom_name = frappe.db.get_value("Custom Field", {"dt": "Project", "fieldname": fieldname})
		if custom_name:
			frappe.db.set_value("Custom Field", custom_name, "hidden", 1)


def _migrate_legacy_team_members():
	projects = frappe.get_all(
		"Project",
		filters={},
		fields=["name", "custom_project_engineer", "custom_sales_engineer"],
	)
	for project in projects:
		doc = frappe.get_doc("Project", project.name)
		existing_employees = {row.employee for row in doc.get("custom_project_team") or [] if row.employee}
		changed = False

		if project.custom_project_engineer and project.custom_project_engineer not in existing_employees:
			doc.append(
				"custom_project_team",
				{"role": "Engineer", "employee": project.custom_project_engineer},
			)
			changed = True

		if project.custom_sales_engineer and project.custom_sales_engineer not in existing_employees:
			doc.append(
				"custom_project_team",
				{"role": "Sales Manager", "employee": project.custom_sales_engineer},
			)
			changed = True

		if changed:
			doc.flags.ignore_validate = True
			doc.save(ignore_permissions=True)

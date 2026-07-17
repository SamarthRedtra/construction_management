# Copyright (c) 2026, Construction Management
# License: MIT

"""Rename More Information → Accounting, add KPI HTML, hide Costing/Progress + Construction clutter."""

import json

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field


# Construction keeps only BOQ dashboard; these stay on the tab but are hidden.
CONSTRUCTION_HIDDEN_FIELDS = [
	"construction_details_section",
	"company",
	"project_type_construction",
	"consultant",
	"column_break_construction",
	"site_location",
	"budget_control_section",
	"budget_enforcement_level",
	"budget_mode",
	"budget_threshold_percent",
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
]

ALWAYS_HIDDEN_TABS = [
	"costing_tab",
	"monitor_progress_tab",
]

PROJECT_FIELD_ORDER = [
	"naming_series",
	"custom_project_info_section",
	"custom_project_no",
	"custom_contract_name",
	"project_name",
	"custom_project_short_name",
	"custom_project_info_col_break_1",
	"customer",
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
	"construction_dashboard_section",
	"construction_dashboard",
	"construction_details_section",
	"company",
	"project_type_construction",
	"consultant",
	"column_break_construction",
	"site_location",
	"budget_control_section",
	"budget_enforcement_level",
	"budget_mode",
	"budget_threshold_percent",
	"custom_payment_terms",
	"custom_payment_terms_data",
	"custom_payment_terms_html",
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
	"custom_approved_materials_tab",
	"custom_approved_materials",
	"custom_approved_materials_data",
	"custom_approved_materials_html",
	"custom_more_information",
	"accounting_kpi_html",
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
	_ensure_accounting_kpi_field()
	_rename_more_information_to_accounting()
	_update_field_order()
	_hide_construction_clutter()
	_hide_costing_and_progress_tabs()
	frappe.clear_cache(doctype="Project")


def _ensure_accounting_kpi_field():
	cf_name = frappe.db.get_value(
		"Custom Field", {"dt": "Project", "fieldname": "accounting_kpi_html"}, "name"
	)
	if cf_name:
		frappe.db.set_value(
			"Custom Field",
			cf_name,
			{
				"label": "Accounting KPIs",
				"insert_after": "custom_more_information",
				"hidden": 0,
			},
			update_modified=False,
		)
		return

	create_custom_field(
		"Project",
		{
			"fieldname": "accounting_kpi_html",
			"label": "Accounting KPIs",
			"fieldtype": "HTML",
			"insert_after": "custom_more_information",
		},
	)


def _rename_more_information_to_accounting():
	_set_label("custom_more_information", "Accounting")


def _update_field_order():
	prop_name = "Project-main-field_order"
	value = json.dumps(PROJECT_FIELD_ORDER)
	if frappe.db.exists("Property Setter", prop_name):
		frappe.db.set_value("Property Setter", prop_name, "value", value, update_modified=False)
	else:
		frappe.get_doc(
			{
				"doctype": "Property Setter",
				"doc_type": "Project",
				"doctype_or_field": "DocType",
				"property": "field_order",
				"property_type": "Data",
				"value": value,
			}
		).insert(ignore_permissions=True)


def _hide_construction_clutter():
	for fieldname in CONSTRUCTION_HIDDEN_FIELDS:
		_set_hidden(fieldname, 1)

	# Keep payment terms UI visible on Construction (data field stays hidden).
	_set_hidden("custom_payment_terms", 0)
	_set_hidden("custom_payment_terms_html", 0)
	_set_hidden("custom_payment_terms_data", 1)


def _hide_costing_and_progress_tabs():
	for fieldname in ALWAYS_HIDDEN_TABS:
		_set_hidden(fieldname, 1)


def _set_label(fieldname, label):
	cf_name = frappe.db.get_value("Custom Field", {"dt": "Project", "fieldname": fieldname}, "name")
	if cf_name:
		frappe.db.set_value("Custom Field", cf_name, "label", label, update_modified=False)
		return

	prop_name = f"Project-{fieldname}-label"
	if frappe.db.exists("Property Setter", prop_name):
		frappe.db.set_value("Property Setter", prop_name, "value", label, update_modified=False)
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


def _set_hidden(fieldname, hidden):
	cf_name = frappe.db.get_value("Custom Field", {"dt": "Project", "fieldname": fieldname}, "name")
	if cf_name:
		frappe.db.set_value("Custom Field", cf_name, "hidden", hidden, update_modified=False)
		return

	prop_name = f"Project-{fieldname}-hidden"
	if frappe.db.exists("Property Setter", prop_name):
		frappe.db.set_value("Property Setter", prop_name, "value", str(hidden), update_modified=False)
	else:
		frappe.get_doc(
			{
				"doctype": "Property Setter",
				"doc_type": "Project",
				"doctype_or_field": "DocField",
				"field_name": fieldname,
				"property": "hidden",
				"property_type": "Check",
				"value": str(hidden),
			}
		).insert(ignore_permissions=True)

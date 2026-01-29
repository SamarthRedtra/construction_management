app_name = "construction_management"
app_title = "Construction Management"
app_publisher = "Construction Management"
app_description = "Construction management platform with BOQ, Bids, MAR, NCR, IR, Tasks, DPR, IPC"
app_email = "admin@example.com"
app_license = "mit"
# App configuration
# Reload triggered by Antigravity at 2026-01-24 02:27
# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "construction_management",
# 		"logo": "/assets/construction_management/logo.png",
# 		"title": "Construction Management",
# 		"route": "/construction",
# 		"has_permission": "construction_management.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/construction_management/css/construction_management.css"
app_include_js = "/assets/construction_management/js/accounting_dimension_filters.js"

# include js, css files in header of web template
# web_include_css = "/assets/construction_management/css/construction_management.css"
# web_include_js = "/assets/construction_management/js/construction_management.js"

# include custom scss in every website theme (without signing in)
# website_theme_scss = "construction_management/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {
	"BOQ": "public/js/boq.js",
	"Bid": "public/js/bid.js",
	"Interim Payment Certificate": "public/js/ipc.js",
	"Project": ["public/js/boq_management_table.js", "public/js/boq_fullscreen_manager.js", "public/js/sticky_columns_manager.js", "public/js/profit_loss_indicator.js", "public/js/bill_financial_summary_widget.js", "public/js/project.js"],
	"Daily Progress Record": "public/js/daily_progress_record.js",
	"Purchase Receipt": "public/js/purchase_receipt.js",
	"Sales Invoice": ["public/js/accounting_dimension_filters.js", "public/js/sales_invoice.js"],
	"Purchase Invoice": ["public/js/accounting_dimension_filters.js", "public/js/purchase_invoice.js"],
	"Purchase Order": ["public/js/accounting_dimension_filters.js", "public/js/purchase_order.js"],
	"Sales Order": ["public/js/accounting_dimension_filters.js", "public/js/sales_order.js"],
	"Stock Entry": ["public/js/accounting_dimension_filters.js", "public/js/stock_entry.js"],
	"Journal Entry": ["public/js/accounting_dimension_filters.js", "public/js/journal_entry.js"]
}

# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Iconsapp
# ------------------
# include app icons in desk
# app_include_icons = "construction_management/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "construction_management.utils.jinja_methods",
# 	"filters": "construction_management.utils.jinja_filters"
# }

# Installation
# ------------

before_install = "construction_management.setup.install.before_install"
after_install = "construction_management.setup.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "construction_management.uninstall.before_uninstall"
# after_uninstall = "construction_management.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/dependencies for a connected app,
# add required app names to integration_connected_app in hooks.py
# integration_connected_app = ["frappe_mailjet"]

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "construction_management.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Sales Invoice": {
		"validate": "construction_management.overrides.sales_invoice.validate",
		"before_insert": "construction_management.overrides.sales_invoice.before_insert",
		"on_submit": "construction_management.overrides.sales_invoice.on_submit",
		"on_cancel": "construction_management.overrides.sales_invoice.on_cancel",
		"on_update_after_submit": "construction_management.overrides.sales_invoice.on_update"
	},
	"Purchase Invoice": {
		"on_submit": "construction_management.overrides.purchase_invoice.on_submit",
		"on_cancel": "construction_management.overrides.purchase_invoice.on_cancel"
	},
	"Purchase Receipt": {
		"validate": "construction_management.overrides.purchase_receipt.validate",
		"before_submit": "construction_management.overrides.purchase_receipt.before_submit"
	},
	"Project": {
		"on_update": "construction_management.overrides.project.clear_project_cache",
		"after_insert": "construction_management.construction_management.doctype.boq_settings.boq_settings.auto_create_project_warehouse"
	},
	"Daily Progress Record": {
		"validate": "construction_management.construction_management.doctype.boq_settings.boq_settings.validate_warehouse_for_dpr"
	},
	"Sales Order": {
		"validate": "construction_management.overrides.sales_order.validate",
		"on_submit": "construction_management.overrides.sales_order.on_submit",
		"on_cancel": "construction_management.overrides.sales_order.on_cancel",
		"on_update_after_submit": "construction_management.overrides.sales_order.on_update_after_submit"
	},
	"GL Entry": {
		"on_update": "construction_management.api.gl_hook.update_cost_from_gl"
	},
	"Payment Entry": {
		"on_submit": "construction_management.overrides.payment_entry.on_submit"
	}
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	"daily": [
		"construction_management.tasks.send_task_reminders",
		"construction_management.tasks.check_overdue_tasks",
		"construction_management.api.employee_rate_cache.daily_refresh_employee_rates"
	],
	"weekly": [
		"construction_management.tasks.send_weekly_report"
	]
}

# Testing
# -------

# before_tests = "construction_management.install.before_tests"

# Overriding Methods
# ------------------------------
#
override_whitelisted_methods = {
	"frappe.desk.form.load.getdoctype": "construction_management.overrides.form_load.getdoctype",
}
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "construction_management.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["construction_management.utils.before_request"]
# after_request = ["construction_management.utils.after_request"]

# Job Events
# ----------
# before_job = ["construction_management.utils.before_job"]
# after_job = ["construction_management.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"construction_management.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Fixtures - Export roles and custom fields
fixtures = [
	{
		"dt": "Role",
		"filters": [["name", "in", [
			"Construction Manager",
			"Quantity Surveyor",
			"Site Engineer",
			"Consultant",
			"Contractor",
			"Client"
		]]]
	},
	{
		"dt": "Custom Field",
		"filters": [["name", "in", [
			"Project-enable_progressive_boq",
			"Project-retention_percentage",
			"Project-construction_dashboard_section",
			"Project-construction_dashboard",
			"Stock Entry Detail-boq_item",
			"Stock Entry Detail-bill_no",
			"Project-budget_control_section",
			"Project-budget_enforcement_level",
			"Project-budget_mode",
			"Project-budget_threshold_percent"
		]]]
	}
]

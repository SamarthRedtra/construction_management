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
app_include_js = [
	"/assets/construction_management/js/accounting_dimension_filters.js",
	"/assets/construction_management/js/combined_sales_invoice_from_so.js",
	"/assets/construction_management/js/bulk_material_issue.js",
]

# include js, css files in header of web template
# web_include_css = "/assets/construction_management/css/construction_management.css"
# web_include_js = "/assets/construction_management/js/construction_management.js"

# include custom scss in every website theme (without signing in)
# website_theme_scss = "construction_management/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
page_js = {
	"project-soa": "public/js/project_soa_dashboard.js",
	"project-commission": "public/js/project_commission_dashboard.js",
	"project-collection": "public/js/project_collection_dashboard.js",
	"print": "public/js/print_boq_progress_excel.js",
}

# include js in doctype views
doctype_js = {
	"BOQ": "public/js/boq.js",
	"Bid": "public/js/bid.js",
	"Interim Payment Certificate": "public/js/ipc.js",
	"Project": ["public/js/project_tab_access.js", "public/js/boq_management_table.js", "public/js/boq_fullscreen_manager.js", "public/js/sticky_columns_manager.js", "public/js/profit_loss_indicator.js", "public/js/bill_financial_summary_widget.js", "public/js/project_soa_dashboard.js", "public/js/project_commission_dashboard.js", "public/js/project_approved_materials.js", "public/js/project_team_allocation.js", "public/js/project.js"],
	"Daily Progress Record": "public/js/daily_progress_record.js",
	"Daily Roster": "public/js/daily_roster.js",
	"Purchase Receipt": "public/js/purchase_receipt.js",
	"Sales Invoice": ["public/js/accounting_dimension_filters.js", "public/js/deduction_summary.js", "public/js/sales_invoice.js"],
	"Purchase Invoice": ["public/js/accounting_dimension_filters.js", "public/js/purchase_invoice.js"],
	"Purchase Order": ["public/js/accounting_dimension_filters.js", "public/js/purchase_order.js"],
	"Sales Order": ["public/js/accounting_dimension_filters.js", "public/js/deduction_summary.js", "public/js/sales_order.js"],
	"Stock Entry": ["public/js/accounting_dimension_filters.js", "public/js/stock_entry.js"],
	"Journal Entry": ["public/js/accounting_dimension_filters.js", "public/js/journal_entry.js"],
	"Material Request": ["public/js/accounting_dimension_filters.js", "public/js/material_request.js"],
	"Quotation": [
		"public/js/quotation.js",
		"public/js/quotation_boq_easy_entry.js",
	],
	"Payment Entry": "public/js/payment_entry.js",
	"Project Tab Access": "public/js/project_tab_access.js",
}

# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
doctype_list_js = {
	"Sales Order": "public/js/sales_order_list.js",
	"Purchase Receipt": "public/js/purchase_receipt_list.js",
	"Stock Entry": "public/js/stock_entry_list.js",
}
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

jinja = {
	"methods": [
		"construction_management.so_boq_progress_print_context.get_so_boq_progress_print_context",
	],
}

# Installation
# ------------

before_install = "construction_management.setup.install.before_install"
after_install = "construction_management.setup.install.after_install"
after_migrate = "construction_management.setup.install.after_migrate"

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

permission_query_conditions = {
	"Project": "construction_management.permissions.project.get_project_permission_query_conditions",
}

has_permission = {
	"Project": "construction_management.permissions.project.has_project_permission",
}

# DocType Class
# ---------------
# Override standard doctype classes

override_doctype_class = {
	"Sales Invoice": "construction_management.overrides.sales_invoice.SalesInvoiceOverride",
	"Purchase Invoice": "construction_management.overrides.purchase_invoice.PurchaseInvoiceOverride",
	"Purchase Receipt": "construction_management.overrides.purchase_receipt_class.PurchaseReceiptOverride",
	"Process Statement Of Accounts": "construction_management.overrides.process_statement_of_accounts.ProcessStatementOfAccountsOverride",
	"GL Entry": "construction_management.overrides.gl_entry.GLEntryOverride",
	"Quotation": "construction_management.overrides.quotation.QuotationOverride",
}

# Monkey Patches
# --------------
# - Financial Statements SQL Fix: construction_management.overrides.financial_statements_fix
#   (Imported in __init__.py to apply on app load)

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Sales Invoice": {
		# Handled in class override
	},
	"Purchase Invoice": {
		"before_validate": "construction_management.overrides.purchase_invoice.before_validate",
		"validate": "construction_management.overrides.purchase_invoice.validate",
		"before_cancel": "construction_management.overrides.purchase_invoice.before_cancel",
		"on_submit": "construction_management.overrides.purchase_invoice.on_submit",
		"on_cancel": "construction_management.overrides.purchase_invoice.on_cancel"
	},
	"Purchase Order": {
		"validate": "construction_management.overrides.purchase_order.validate"
	},
	"Purchase Receipt": {
		"before_validate": "construction_management.overrides.purchase_receipt.before_validate",
		"validate": "construction_management.overrides.purchase_receipt.validate",
		"before_submit": "construction_management.overrides.purchase_receipt.before_submit",
		"on_submit": "redtra_customisation.override.provisional_purchase_order.on_purchase_receipt_submit",
	},
	"Project": {
		"before_insert": "construction_management.api.project_numbering.assign_project_number_if_missing",
		"validate": "construction_management.api.project_numbering.assign_project_number_if_missing",
		"on_update": [
			"construction_management.overrides.project.clear_project_cache",
			"construction_management.raven_integrations.project_channel.on_update",
		],
		"after_insert": [
			"construction_management.construction_management.doctype.boq_settings.boq_settings.auto_create_project_warehouse",
			"construction_management.raven_integrations.project_channel.after_insert",
		],
		"on_trash": "construction_management.raven_integrations.project_channel.on_trash",
	},
	"Daily Progress Record": {
		"validate": "construction_management.construction_management.doctype.boq_settings.boq_settings.validate_warehouse_for_dpr"
	},
	"Daily Roster": {
		"validate": "construction_management.overrides.daily_roster.set_project_short_name",
	},
	"Sales Order": {
		"validate": "construction_management.overrides.sales_order.validate",
		"on_submit": "construction_management.overrides.sales_order.on_submit",
		"on_cancel": "construction_management.overrides.sales_order.on_cancel",
		"on_update_after_submit": "construction_management.overrides.sales_order.on_update_after_submit",
		"on_trash": "construction_management.overrides.sales_order.on_trash"
	},
	"GL Entry": {
		"on_update": "construction_management.api.gl_hook.update_cost_from_gl"
	},
	"Payment Entry": {
		"before_validate": "construction_management.overrides.payment_entry.before_validate",
		"validate": "construction_management.overrides.payment_entry.validate",
		"on_submit": "construction_management.overrides.payment_entry.on_submit",
		"on_cancel": "construction_management.overrides.payment_entry.on_cancel",
	},
	"Journal Entry": {
		"on_submit": "construction_management.api.boq_opening_balance.sync_opening_journal_entry",
		"on_cancel": "construction_management.api.boq_opening_balance.cancel_opening_journal_entry",
	},
	"BOQ Item": {
		"after_delete": "construction_management.construction_management.doctype.boq_item.boq_item.update_parent_totals"
	},
	"Task": {
		"on_update": "construction_management.overrides.task.on_update"
	},
	"Item Price": {
		"after_insert": "construction_management.tasks.delete_special_item_price_on_insert"
	},
	"Stock Entry": {
		"before_validate": "construction_management.api.drum_uom_utils.apply_stock_entry_uom_conversion",
		"on_cancel": "construction_management.overrides.stock_entry.on_cancel",
	},
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	"cron": {
		"* * * * *": [
			"construction_management.tasks.delete_special_item_prices"
		]
	},
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
	"erpnext.accounts.doctype.process_statement_of_accounts.process_statement_of_accounts.download_statements": "construction_management.overrides.process_statement_of_accounts.download_statements",
	"erpnext.accounts.doctype.process_statement_of_accounts.process_statement_of_accounts.send_emails": "construction_management.overrides.process_statement_of_accounts.send_emails",
	"erpnext.accounts.party.get_party_account": "construction_management.overrides.party.get_party_account",
}

# Custom SOA HTML template for Advanced General Ledger
process_soa_html = {
	"Advanced General Ledger": "construction_management/construction_management/report/advanced_general_ledger/advanced_general_ledger_soa.html"
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
before_request = [
	"construction_management.overrides.party.install_party_account_perm_patch",
]
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
	},
	{
		"dt": "Property Setter",
		"filters": [["doc_type", "=", "Process Statement Of Accounts"]]
	},
	{
		"dt": "Print Format",
		"filters": [["name", "in", [
			"BOQ Quotation",
			"Daily Roster",
			"Payment Certificate Payable",
			"Project Completion Report",
			"Sales Order BOQ Progress",
		]]]
	},
]

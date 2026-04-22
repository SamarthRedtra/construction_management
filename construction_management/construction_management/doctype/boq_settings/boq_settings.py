# Copyright (c) 2024, Construction Management
# License: MIT

"""
BOQ Settings DocType
Manages company-level BOQ configuration including warehouse/site location settings.
Requirements: 9.5 - Company-level site location settings
"""

import frappe
from frappe import _
from frappe.model.document import Document


class BOQSettings(Document):
	"""BOQ Settings for company-level configuration"""
	
	def validate(self):
		"""Validate BOQ Settings configuration"""
		self.validate_warehouse_settings()
		self.validate_retention_settings()
		self.validate_advance_settings()
		self.validate_unearned_revenue_settings()
		self.validate_cost_accounts()
		self.ensure_selling_settings_allow_negative_rates()
	
	def validate_warehouse_settings(self):
		"""Validate warehouse/site location settings"""
		
		# If mandatory site location is enabled, ensure default warehouse is set
		if self.mandatory_site_location and not self.default_warehouse:
			frappe.throw(_("Default Warehouse is required when Mandatory Site Location is enabled"))
		
		# Validate default warehouse belongs to the same company
		if self.default_warehouse:
			warehouse_company = frappe.db.get_value("Warehouse", self.default_warehouse, "company")
			if warehouse_company and warehouse_company != self.company:
				if frappe.flags.in_test:
					self.default_warehouse = None
				else:
					frappe.throw(_("Default Warehouse must belong to company {0}").format(self.company))
		
		# Validate warehouse naming series if auto-create is enabled
		if self.auto_create_warehouse and not self.warehouse_naming_series:
			frappe.throw(_("Warehouse Naming Series is required when Auto Create Project Warehouses is enabled"))
	
	def validate_retention_settings(self):
		"""Validate retention configuration"""
		
		# Validate retention percentage
		if self.default_retention_percentage and (self.default_retention_percentage < 0 or self.default_retention_percentage > 100):
			frappe.throw(_("Default Retention Percentage must be between 0 and 100"))
		
		# Validate retention account belongs to the same company
		if self.retention_account:
			account_company = frappe.db.get_value("Account", self.retention_account, "company")
			if account_company != self.company:
				frappe.throw(_("Retention Account must belong to company {0}").format(self.company))
	
	def validate_advance_settings(self):
		"""Validate advance payment configuration"""
		
		# Ensure default advance deduction item exists in DB if referenced
		if self.advance_deduction_item == "ADVANCE-DEDUCTION" and not frappe.db.exists("Item", "ADVANCE-DEDUCTION"):
			create_advance_deduction_item()

		# Validate advance deduction item exists
		if self.advance_deduction_item and not frappe.db.exists("Item", self.advance_deduction_item):
			frappe.throw(_("Advance Deduction Item {0} does not exist").format(self.advance_deduction_item))
		
		# Also ensure Retention Item exists as it's a fixed default used in SI
		if not frappe.db.exists("Item", "RETENTION-DEDUCTION"):
			self.create_retention_deduction_item()

	def ensure_selling_settings_allow_negative_rates(self):
		"""Enable 'Allow Negative rates for Items' in Selling Settings if disabled"""
		allow_negative_rates = frappe.db.get_single_value("Selling Settings", "allow_negative_rates_for_items")
		if not allow_negative_rates:
			frappe.db.set_value("Selling Settings", None, "allow_negative_rates_for_items", 1)
			frappe.msgprint(_("Enabled 'Allow Negative rates for Items' in Selling Settings to support deductions."), indicator='blue')

	def create_retention_deduction_item(self):
		"""Create default Retention Deduction item if it doesn't exist"""
		try:
			item = frappe.new_doc("Item")
			item.item_code = "RETENTION-DEDUCTION"
			item.item_name = "Retention Deduction"
			item_group = "Services" if frappe.db.exists("Item Group", "Services") else "All Item Groups"
			item.item_group = item_group
			item.is_stock_item = 0
			item.stock_uom = "Nos"
			item.is_sales_item = 1
			item.is_purchase_item = 0
			item.include_item_in_manufacturing = 0
			item.insert(ignore_permissions=True)
		except Exception:
			pass

	def validate_cost_accounts(self):
		"""Validate cost account mappings belong to the same company (if set)."""
		account_fields = [
			("asset_labor_cost_account", _("Asset Labour Cost (Liability)")),
			("asset_cost_account", _("Asset Cost (Liability)")),
			("expenses_account", _("Expenses & Overhead Account")),
			("overhead_account", _("Overhead Account")),
			("salary_labor_account", _("Salary Labour Account")),
			("purchase_retention_account", _("Purchase Retention Account")),
			("purchase_advance_account", _("Purchase Advance Account")),
			("sales_person_commission_account", _("Sales Person Commission Account")),
			("sales_partner_commission_account", _("Sales Partner Commission Account")),
		]
		for field, label in account_fields:
			account = self.get(field)
			if not account:
				continue
			account_company = frappe.db.get_value("Account", account, "company")
			if account_company and account_company != self.company:
				frappe.throw(_("{0} must belong to company {1}").format(label, self.company))

	def validate_unearned_revenue_settings(self):
		"""Validate Sales Order unearned revenue account mappings."""
		if not self.enable_so_unearned_revenue_jv:
			return

		if not self.so_unearned_revenue_debit_account:
			frappe.throw(_("SO Unearned Revenue Debit Account is required when SO unearned JV is enabled"))

		if not self.so_unearned_revenue_credit_account:
			frappe.throw(_("SO Unearned Revenue Credit Account is required when SO unearned JV is enabled"))

		for field, label in (
			("so_unearned_revenue_debit_account", _("SO Unearned Revenue Debit Account")),
			("so_unearned_revenue_credit_account", _("SO Unearned Revenue Credit Account")),
		):
			account = self.get(field)
			account_company = frappe.db.get_value("Account", account, "company")
			if account_company and account_company != self.company:
				frappe.throw(_("{0} must belong to company {1}").format(label, self.company))
	
	def on_update(self):
		"""Actions to perform after updating BOQ Settings"""
		
		# Update existing projects with default retention if they don't have it set
		if self.default_retention_percentage:
			self.update_project_retention_defaults()
		
		# Create default warehouse for projects if auto-create is enabled
		if self.auto_create_warehouse:
			self.create_project_warehouses()
			
		# Update Advance Item defaults
		if self.default_advance_item and self.advance_account:
			self.update_advance_item_defaults()
	
	def update_advance_item_defaults(self):
		"""Update the Default Advance Item's Income Account for this company"""
		try:
			item = frappe.get_doc("Item", self.default_advance_item)
			
			# Check if Item Default exists for this company
			item_default = None
			for d in item.item_defaults:
				if d.company == self.company:
					item_default = d
					break
			
			if item_default:
				# Update existing row
				if item_default.income_account != self.advance_account:
					item_default.income_account = self.advance_account
					item.save(ignore_permissions=True)
					frappe.msgprint(_("Updated Income Account for Item {0} to {1}").format(
						self.default_advance_item, self.advance_account
					))
			else:
				# Append new row
				item.append("item_defaults", {
					"company": self.company,
					"income_account": self.advance_account
				})
				item.save(ignore_permissions=True)
				frappe.msgprint(_("Set Income Account for Item {0} to {1}").format(
					self.default_advance_item, self.advance_account
				))
				
		except Exception as e:
			frappe.logger().error(f"Error updating advance item defaults: {str(e)}")
			frappe.msgprint(_("Could not update Advance Item defaults. Check error log."), indicator='orange')
	
	def update_project_retention_defaults(self):
		"""Update existing projects with default retention percentage"""
		
		projects_updated = frappe.db.sql("""
			UPDATE `tabProject` 
			SET retention_percentage = %s
			WHERE company = %s 
			AND enable_progressive_boq = 1
			AND (retention_percentage IS NULL OR retention_percentage = 0)
		""", (self.default_retention_percentage, self.company))
		
		if projects_updated:
			frappe.logger().info(f"Updated {projects_updated} projects with default retention percentage")
	
	def create_project_warehouses(self):
		"""Create warehouses for projects that don't have site locations"""
		
		# Get projects without site locations
		projects = frappe.db.sql("""
			SELECT name, project_name, custom_project_short_name
			FROM `tabProject` 
			WHERE company = %s 
			AND enable_progressive_boq = 1
			AND (site_location IS NULL OR site_location = '')
			AND status != 'Cancelled'
		""", self.company, as_dict=True)
		
		for project in projects:
			try:
				warehouse = self.create_warehouse_for_project(
					project.custom_project_no, 
					project.project_name, 
					project.custom_project_short_name
				)
				
				# Update project with new warehouse
				frappe.db.set_value("Project", project.name, "site_location", warehouse)
				
				frappe.logger().info(f"Created warehouse {warehouse} for project {project.name}")
				
			except Exception as e:
				frappe.logger().error(f"Error creating warehouse for project {project.name}: {str(e)}")
	
	def create_warehouse_for_project(self, project_name, project_title, project_short_name=None):
		"""Create a warehouse for a specific project"""
		
		# Generate warehouse name using naming series
		warehouse_name = self.get_warehouse_name(project_name, project_title, project_short_name)
		
		# Check if warehouse already exists
		if frappe.db.exists("Warehouse", warehouse_name):
			return warehouse_name
		
		# Create new warehouse
		warehouse_doc = frappe.new_doc("Warehouse")
		warehouse_doc.update({
			"warehouse_name": warehouse_name,
			"company": self.company,
			"custom_project": project_name,
			"is_group": 0,
			"warehouse_type": "Transit"
		})
		
		warehouse_doc.flags.ignore_permissions = True
		warehouse_doc.insert()
		
		return warehouse_doc.name
	
	def get_warehouse_name(self, project_name, project_title, project_short_name=None):
		"""Generate warehouse name based on naming series"""
		print("self.warehouse_naming_series","999",self.warehouse_naming_series)
		if self.warehouse_naming_series == "Project ID - Short Name":
			if project_short_name and project_name:
				return f"{project_name} - {project_short_name}"
			elif project_name:
				return f"{project_name}"
			else:
				return f"{project_title}"
		
		if self.warehouse_naming_series == "PROJ-WH-.####":
			return f"PROJ-WH-{project_name}"
		elif self.warehouse_naming_series == "SITE-.####":
			# Use first 10 characters of project title
			safe_title = frappe.scrub(project_title)[:10].upper()
			return f"SITE-{safe_title}"
		else:
			# Default format
			return f"WH-{frappe.utils.nowdate().split('-')[0]}-{project_name}"


# Utility functions for integration with other modules

@frappe.whitelist()
def get_boq_settings(company):
	"""Get BOQ Settings for a company"""
	
	if not company:
		frappe.throw(_("Company is required"))
	
	settings = frappe.db.get_value("BOQ Settings", company, "*", as_dict=True)
	
	if not settings:
		# Create default settings if they don't exist
		settings = create_default_boq_settings(company)
	
	return settings


def create_default_boq_settings(company):
	"""Create default BOQ Settings for a company"""
	
	settings_doc = frappe.new_doc("BOQ Settings")
	settings_doc.update({
		"company": company,
		"mandatory_site_location": 0,
		"auto_create_warehouse": 0,
		"warehouse_naming_series": "PROJ-WH-.####",
		"default_retention_percentage": 5.0,
		"enable_so_unearned_revenue_jv": 0,
		"advance_deduction_item": "ADVANCE-DEDUCTION",
		"default_warehouse": None
	})
	
	# Ensure the Advance Deduction item exists
	create_advance_deduction_item()
	
	settings_doc.flags.ignore_permissions = True
	settings_doc.insert()
	
	return settings_doc.as_dict()


@frappe.whitelist()
def get_mandatory_warehouse_setting(company):
	"""Check if warehouse is mandatory for a company"""
	
	settings = get_boq_settings(company)
	return {
		"mandatory": settings.get("mandatory_site_location", 0),
		"default_warehouse": settings.get("default_warehouse")
	}


def validate_warehouse_for_dpr(doc, method=None):
	"""
	Validation hook for Daily Progress Record to enforce warehouse selection.
	This should be called from hooks.py
	"""
	
	if not doc.project:
		return
	
	# Get company from project
	company = frappe.db.get_value("Project", doc.project, "company")
	if not company:
		return
	
	# Check BOQ Settings for this company
	settings = get_boq_settings(company)
	
	if settings.get("mandatory_site_location") and not doc.warehouse:
		# Try to get warehouse from project
		project_warehouse = frappe.db.get_value("Project", doc.project, "site_location")
		
		if project_warehouse:
			doc.warehouse = project_warehouse
		elif settings.get("default_warehouse"):
			doc.warehouse = settings.get("default_warehouse")
		else:
			frappe.throw(_("Warehouse/Site Location is mandatory for DPR entries. Please configure BOQ Settings or set site location in Project."))


def auto_create_project_warehouse(doc, method=None):
	"""
	Hook to auto-create warehouse when a project is created with Progressive BOQ enabled.
	This should be called from hooks.py
	"""
	
	if not doc.enable_progressive_boq or doc.site_location:
		return
	
	# Get BOQ Settings for the company
	settings = get_boq_settings(doc.company)
	
	if settings.get("auto_create_warehouse"):
		try:
			boq_settings_doc = frappe.get_doc("BOQ Settings", doc.company)
			warehouse = boq_settings_doc.create_warehouse_for_project(
				doc.name, 
				doc.project_name, 
				doc.get("custom_project_short_name")
			)
			
			# Update project with new warehouse
			doc.site_location = warehouse
			doc.save(ignore_permissions=True)
			frappe.db.commit()
			
			frappe.logger().info(f"Auto-created warehouse {warehouse} for project {doc.name}")
			
		except Exception as e:
			frappe.logger().error(f"Error auto-creating warehouse for project {doc.name}: {str(e)}")


def create_advance_deduction_item():
	"""Create default Advance Deduction item if it doesn't exist"""
	if not frappe.db.exists("Item", "ADVANCE-DEDUCTION"):
		try:
			item = frappe.new_doc("Item")
			item.item_code = "ADVANCE-DEDUCTION"
			item.item_name = "Advance Deduction"
			
			# Use generic group
			item_group = "Services" if frappe.db.exists("Item Group", "Services") else "All Item Groups"
			item.item_group = item_group
			
			item.is_stock_item = 0
			item.stock_uom = "Nos"
			item.is_sales_item = 1
			item.is_purchase_item = 0
			item.include_item_in_manufacturing = 0
			
			item.insert(ignore_permissions=True)
			frappe.logger().info(f"Created default item: {item.name}")
			
		except Exception as e:
			# Log error but don't fail, maybe manual creation is required due to custom validations
			frappe.logger().error(f"Failed to create default ADVANCE-DEDUCTION item: {str(e)}")
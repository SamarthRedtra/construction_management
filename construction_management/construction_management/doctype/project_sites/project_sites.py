# Copyright (c) 2026, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.model.document import Document


class ProjectSites(Document):
	"""Project Sites DocType for tracking construction sites"""
	
	def validate(self):
		"""Validate the Project Sites document"""
		self.validate_hierarchy()
		self.validate_unique_site_name()
	
	def validate_hierarchy(self):
		"""Validate that bill_no belongs to project and boq_item belongs to bill_no"""
		# Validate bill_no belongs to project
		if self.bill_no:
			bill_project = frappe.db.get_value("BOQ Bill", self.bill_no, "project")
			if bill_project != self.project:
				frappe.throw(
					_("Bill No {0} does not belong to Project {1}").format(
						frappe.bold(self.bill_no),
						frappe.bold(self.project)
					),
					title=_("Invalid Bill No")
				)
		
		# Validate boq_item belongs to bill_no
		if self.boq_item:
			if not self.bill_no:
				frappe.throw(
					_("Bill No is required when BOQ Item is selected"),
					title=_("Missing Bill No")
				)
			
			item_bill = frappe.db.get_value("BOQ Item", self.boq_item, "parent_bill")
			if item_bill != self.bill_no:
				frappe.throw(
					_("BOQ Item {0} does not belong to Bill No {1}").format(
						frappe.bold(self.boq_item),
						frappe.bold(self.bill_no)
					),
					title=_("Invalid BOQ Item")
				)
	
	def validate_unique_site_name(self):
		"""Ensure site name is unique within a project"""
		existing = frappe.db.exists(
			"Project Sites",
			{
				"project": self.project,
				"site_name": self.site_name,
				"name": ["!=", self.name]
			}
		)
		if existing:
			frappe.throw(
				_("Site Name {0} already exists for Project {1}").format(
					frappe.bold(self.site_name),
					frappe.bold(self.project)
				),
				title=_("Duplicate Site Name")
			)


@frappe.whitelist()
def create_bulk_sites(project, site_names):
	"""
	Create multiple Project Sites at once
	
	Args:
		project: Project name
		site_names: List of site names (can be string with newlines or list)
	
	Returns:
		dict with success count and created sites
	"""
	if isinstance(site_names, str):
		# Split by newline and clean up
		site_names = [name.strip() for name in site_names.split('\n') if name.strip()]
	
	created_sites = []
	errors = []
	
	for site_name in site_names:
		try:
			# Check if site already exists
			existing = frappe.db.exists("Project Sites", {
				"project": project,
				"site_name": site_name
			})
			
			if existing:
				errors.append({
					"site_name": site_name,
					"error": f"Site already exists: {existing}"
				})
				continue
			
			# Create new site
			site = frappe.get_doc({
				"doctype": "Project Sites",
				"project": project,
				"site_name": site_name
			})
			site.insert(ignore_permissions=True)
			created_sites.append(site.name)
			
		except Exception as e:
			errors.append({
				"site_name": site_name,
				"error": str(e)
			})
	
	frappe.db.commit()
	
	return {
		"success": len(created_sites),
		"created": created_sites,
		"errors": errors,
		"total": len(site_names)
	}


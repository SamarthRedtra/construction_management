# Copyright (c) 2024, Construction Management
# License: MIT

"""
Patch to add document links to the Project doctype for Connections section.
This allows related construction management documents to show up in Project's connections.
"""

import frappe


def execute():
	"""Add DocType Links to Project for construction management doctypes"""
	
	print("Adding document links to Project doctype...")
	
	# Define the links to add
	# Each link will show related documents in the Project's Connections section
	links_to_add = [
		{
			"link_doctype": "Project BOQ",
			"link_fieldname": "project",
			"group": "BOQ Management"
		},
		{
			"link_doctype": "BOQ Bill",
			"link_fieldname": "project",
			"group": "BOQ Management"
		},
		{
			"link_doctype": "BOQ Item",
			"link_fieldname": "project",
			"group": "BOQ Management"
		},
		{
			"link_doctype": "Daily Progress Record",
			"link_fieldname": "project",
			"group": "BOQ Management"
		},
		{
			"link_doctype": "BOQ Progress Ledger",
			"link_fieldname": "project",
			"group": "BOQ Management"
		},
		{
			"link_doctype": "BOQ Advance Payment",
			"link_fieldname": "project",
			"group": "BOQ Management"
		},
		{
			"link_doctype": "Project Asset Billing",
			"link_fieldname": "project",
			"group": "BOQ Management"
		},
		{
			"link_doctype": "Resource Planner",
			"link_fieldname": "project",
			"group": "BOQ Management"
		},
		{
			"link_doctype": "Payment Certificate",
			"link_fieldname": "project",
			"group": "Billing"
		},
		{
			"link_doctype": "Proforma Invoice",
			"link_fieldname": "project",
			"group": "Billing"
		},
		{
			"link_doctype": "Warehouse",
			"link_fieldname": "custom_project",
			"group": "Site Location"
		},
		{
			"link_doctype": "Project Sites",
			"link_fieldname": "project",
			"group": "Site Location"
		}
	]
	
	added_count = 0
	
	for link in links_to_add:
		# Check if link_doctype exists
		if not frappe.db.exists("DocType", link["link_doctype"]):
			print(f"Skipping {link['link_doctype']} - DocType does not exist")
			continue
		
		# Check if link already exists
		existing = frappe.db.exists("DocType Link", {
			"parent": "Project",
			"link_doctype": link["link_doctype"],
			"link_fieldname": link["link_fieldname"]
		})
		
		if existing:
			print(f"Link {link['link_doctype']} already exists")
			continue
		
		# Add the link
		try:
			doc = frappe.get_doc("DocType", "Project")
			doc.append("links", {
				"link_doctype": link["link_doctype"],
				"link_fieldname": link["link_fieldname"],
				"group": link.get("group", "")
			})
			doc.flags.ignore_permissions = True
			doc.save()
			added_count += 1
			print(f"Added link: {link['link_doctype']}")
		except Exception as e:
			frappe.log_error(f"Error adding link {link['link_doctype']}: {str(e)}")
			print(f"Error adding link {link['link_doctype']}: {str(e)}")
	
	if added_count > 0:
		frappe.db.commit()
		# Clear cache to reflect changes
		frappe.clear_cache(doctype="Project")
	
	print(f"Added {added_count} document links to Project")

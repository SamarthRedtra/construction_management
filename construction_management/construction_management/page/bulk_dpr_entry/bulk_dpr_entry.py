import json

import frappe
from frappe import _
from frappe.utils import flt

from construction_management.api.dpr_utils import (
	_create_dpr_internal,
	get_employees_with_rates,
	get_item_valuation_rate,
)
from construction_management.construction_management.page.bulk_dpr_entry.bulk_dpr_fetch import (
	empty_day_payload,
	empty_master_payload,
	get_boq_items_with_balance,
	get_day_totals,
	get_existing_dprs,
	get_materials,
	get_overhead_accounts,
	get_project_assets_with_rates as load_project_assets,
	get_project_sites,
	get_project_summary,
	project_company_mismatch,
)


@frappe.whitelist()
def get_master_data(project: str = None, company: str = None, date: str = None) -> dict:
	if not project or project_company_mismatch(project, company):
		return empty_master_payload(company)

	project_row = get_project_summary(project)
	project_company = (project_row.company if project_row else None) or company
	help_video_url = ""
	if project_company:
		help_video_url = frappe.db.get_value(
			"BOQ Settings", project_company, "bulk_dpr_help_video_url"
		) or ""

	return {
		"project": project_row,
		"boq_items": get_boq_items_with_balance(project),
		"sites": get_project_sites(project),
		"employees": get_employees_with_rates(),
		"materials": get_materials(project),
		"assets": load_project_assets(project, date),
		"overhead_accounts": get_overhead_accounts(project_company),
		"help_video_url": help_video_url,
	}


@frappe.whitelist()
def get_day_rows(
	project: str,
	date: str = None,
	start: int = 0,
	page_length: int = 20,
	company: str = None,
) -> dict:
	if not date:
		date = frappe.utils.today()
	start = int(start or 0)
	page_length = int(page_length or 20)
	if not project or project_company_mismatch(project, company):
		return empty_day_payload()

	existing = get_existing_dprs(project, date, start, page_length, company)
	return {
		"existing_dprs": existing["dprs"],
		"total_dprs": existing["total"],
		"day_totals": get_day_totals(project, date),
	}


@frappe.whitelist()
def get_initial_data(
	project: str, date: str = None, start: int = 0, page_length: int = 20, company: str = None
) -> dict:
	masters = get_master_data(project, company, date)
	rows = get_day_rows(project, date, start, page_length, company)
	return {**masters, **rows}


@frappe.whitelist()
def get_project_assets_with_rates(project: str, date: str = None) -> list:
	return load_project_assets(project, date)

@frappe.whitelist()
def get_workers_from_daily_roster(project: str, date: str) -> list:
	"""
	Fetch all workers from Daily Roster where project and date match.
	Returns list of {employee, employee_name, rate_per_day} for use in DPR labour section.
	"""
	if not project or not date:
		return []

	rosters = frappe.get_all(
		"Daily Roster",
		filters={"project": project, "date": date, "docstatus": ["<", 2]},
		fields=["name"]
	)

	employee_ids = set()
	for r in rosters:
		doc = frappe.get_doc("Daily Roster", r.name)
		for row in getattr(doc, "workers", []):
			if row.employee:
				employee_ids.add(row.employee)

	if not employee_ids:
		return []

	# Enrich with rate_per_day from get_employees_with_rates
	rates_map = {e["name"]: e.get("rate_per_day", 0) for e in get_employees_with_rates() if e["name"] in employee_ids}

	result = []
	for emp_id in employee_ids:
		emp_name = frappe.db.get_value("Employee", emp_id, "employee_name")
		result.append({
			"employee": emp_id,
			"employee_name": emp_name or emp_id,
			"rate_per_day": rates_map.get(emp_id, 0)
		})
	return result


@frappe.whitelist()
def cancel_bulk_dpr(names: list | str):
	if isinstance(names, str):
		names = json.loads(names)
	
	cancelled = []
	for name in names:
		doc = frappe.get_doc("Daily Progress Record", name)
		if doc.docstatus == 1:
			doc.cancel()
			cancelled.append(name)
	
	return cancelled


@frappe.whitelist()
def delete_bulk_dpr(names: list | str):
	"""Delete draft DPR records from bulk entry."""
	if isinstance(names, str):
		names = json.loads(names)

	deleted = []
	errors = []
	for name in names:
		try:
			doc = frappe.get_doc("Daily Progress Record", name)
			if doc.docstatus != 0:
				errors.append(f"{name}: {_('Only draft DPRs can be deleted')}")
				continue
			frappe.delete_doc("Daily Progress Record", name, force=1)
			deleted.append(name)
		except Exception as e:
			errors.append(f"{name}: {str(e)}")

	return {"deleted": deleted, "errors": errors}


@frappe.whitelist()
def create_quick_project_site(project: str, site_name: str) -> dict:
	"""Create a Project Site from Bulk DPR entry."""
	site_name = (site_name or "").strip()
	if not project:
		frappe.throw(_("Project is required"))
	if not site_name:
		frappe.throw(_("Site name is required"))

	existing = frappe.db.exists("Project Sites", {"project": project, "site_name": site_name})
	if existing:
		return {"name": existing, "site_name": site_name, "created": False}

	site = frappe.get_doc({
		"doctype": "Project Sites",
		"project": project,
		"site_name": site_name,
	})
	site.insert(ignore_permissions=True)
	frappe.db.commit()

	return {"name": site.name, "site_name": site.site_name, "created": True}

@frappe.whitelist()
def save_bulk_dpr(project: str, date: str, rows: list | str, submit: bool = False):
	if isinstance(rows, str):
		rows = json.loads(rows)
	
	if isinstance(submit, str):
		submit = json.loads(submit)
        
	project_doc = frappe.get_doc("Project", project)
	default_warehouse = project_doc.site_location
    
	if not default_warehouse:
		default_warehouse = frappe.db.get_value("Warehouse", {"warehouse_name": project})

	saved_names = []
	errors = []
    
	for row in rows:
		if not row.get("name") and not row.get("boq_item"):
			continue
            
		# Use the standardized internal function for creation/submission
		# This ensures consistency with the single DPR entry page
		
		# If updating existing
		if row.get("name"):
			doc = frappe.get_doc("Daily Progress Record", row.get("name"))
			# If it's already submitted, we might need a different handling or skip
			if doc.docstatus > 0:
				continue
		
		# Prepare data for _create_dpr_internal
		# It expects list of dicts for child tables
		
		# Collect all material and overhead remarks to append to main remarks
		# based on user request "put it on new line"
		material_details = []
		for mat in row.get("materials", []):
			if mat.get("description"):
				material_details.append(f"Material {mat.get('item_code')}: {mat.get('description')}")
		
		overhead_details = []
		for ovh in row.get("overheads", []):
			if ovh.get("description"):
				overhead_details.append(f"Overhead {ovh.get('account')}: {ovh.get('description')}")
		
		main_remarks = row.get("remarks") or ""
		if material_details:
			main_remarks += ("\n" if main_remarks else "") + "\n".join(material_details)
		if overhead_details:
			main_remarks += ("\n" if main_remarks else "") + "\n".join(overhead_details)

		dpr_data = {
			"project": project,
			"date": date,
			"boq_item": row.get("boq_item"),
			"project_sites": row.get("site"),
			"warehouse": default_warehouse,
			"remarks": main_remarks,
			"area_covered": row.get("area_covered"),
			"employees": row.get("employees", []),
			"absent_employees": row.get("absent_employees", []),
			"materials": row.get("materials", []),
			"overheads": row.get("overheads", []),
			"submit": submit
		}
		
		# _create_dpr_internal handles both new and existing? Let's check its code.
		# Ah, _create_dpr_internal always calls frappe.new_doc. 
		# So if updating, I should handle it.
		
		if row.get("name"):
			# Update logic (manual update since utils might not support update)
			doc = frappe.get_doc("Daily Progress Record", row.get("name"))
			doc.project = dpr_data["project"]
			doc.date = dpr_data["date"]
			if dpr_data.get("boq_item"):
				doc.boq_item = dpr_data["boq_item"]
				doc.bill_no = frappe.db.get_value("BOQ Item", dpr_data["boq_item"], "parent_bill")
			doc.project_sites = dpr_data["project_sites"]
			doc.warehouse = dpr_data["warehouse"]
			doc.remarks = dpr_data["remarks"]
			doc.area_covered = flt(dpr_data["area_covered"])
			
			doc.employees = []
			for emp in dpr_data["employees"]:
				hours = flt(emp.get("hours", 8))
				rate = flt(emp.get("rate_per_day", 0))
				amount = flt(emp.get("amount", 0)) or (rate * (hours / 8))
				doc.append("employees", {
					"employee": emp.get("employee"),
					"hours": hours,
					"rate_per_day": rate,
					"amount": amount
				})
			
			doc.materials = []
			for mat in dpr_data["materials"]:
				item_code = mat.get("item_code") or mat.get("name")
				rate = flt(mat.get("rate", 0))
				if not rate and item_code:
					rate = flt(get_item_valuation_rate(item_code, dpr_data["warehouse"]).get("valuation_rate", 0))
				qty = flt(mat.get("qty", 0))
				amount = flt(mat.get("amount", 0)) or (rate * qty)
				doc.append("materials", {
					"item_code": item_code,
					"warehouse": dpr_data["warehouse"],
					"qty": qty,
					"rate": rate,
					"amount": amount
				})
			
			doc.overheads = []
			for ovh in dpr_data["overheads"]:
				amount = flt(ovh.get("amount", 0)) or flt(ovh.get("qty", 0))
				doc.append("overheads", {
					"account": ovh.get("account"),
					"description": ovh.get("description", ""),
					"amount": amount
				})

			doc.absent_employees = []
			for ae in dpr_data.get("absent_employees", []):
				emp_id = ae.get("employee") or ae.get("name")
				if emp_id:
					doc.append("absent_employees", {"employee": emp_id})

			doc.save()
			if submit:
				try:
					doc.submit()
				except Exception as e:
					errors.append(f"{doc.name}: {str(e)}")
			saved_names.append(doc.name)
		else:
			# New DPR
			normalized_materials = []
			for mat in dpr_data["materials"]:
				item_code = mat.get("item_code") or mat.get("name")
				rate = flt(mat.get("rate", 0))
				if not rate and item_code:
					rate = flt(get_item_valuation_rate(item_code, dpr_data["warehouse"]).get("valuation_rate", 0))
				qty = flt(mat.get("qty", 0))
				amount = flt(mat.get("amount", 0)) or (rate * qty)
				normalized_materials.append({
					**mat,
					"item_code": item_code,
					"rate": rate,
					"qty": qty,
					"amount": amount
				})
			result = _create_dpr_internal(
				project=project,
				date=date,
				boq_item=dpr_data["boq_item"],
				project_sites=dpr_data["project_sites"],
				warehouse=dpr_data["warehouse"],
				remarks=dpr_data["remarks"],
				area_covered=dpr_data["area_covered"],
				employees=dpr_data["employees"],
				absent_employees=dpr_data.get("absent_employees", []),
				materials=normalized_materials,
				overheads=dpr_data["overheads"],
				submit=submit
			)
			if result.get("name"):
				saved_names.append(result["name"])
			if result.get("error"):
				errors.append(f"{result.get('name')}: {result.get('error')}")

	return {"saved_names": saved_names, "errors": errors}

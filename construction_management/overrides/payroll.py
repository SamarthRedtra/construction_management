import frappe
from frappe.utils import date_diff, getdate, flt


def get_employees_with_mid_period_salary_structure(start_date, end_date, employees=None):
    """
    Get employees whose Salary Structure Assignment was created within the payroll period.
    
    Args:
        start_date: Payroll period start date (e.g., 2025-12-01)
        end_date: Payroll period end date (e.g., 2025-12-31)
        employees: Optional list of employee IDs to filter
    
    Returns:
        Dict with employee ID as key and their SSA from_date as value
    """
    filters = {
        "docstatus": 1,
        "from_date": [">", start_date],
        "from_date": ["<=", end_date]
    }
    
    if employees:
        filters["employee"] = ["in", employees]
    
    # Get salary structure assignments where from_date is within the period
    # but after the start_date (mid-period joiners)
    assignments = frappe.db.sql("""
        SELECT 
            ssa.employee,
            ssa.from_date,
            e.employee_name
        FROM `tabSalary Structure Assignment` ssa
        INNER JOIN `tabEmployee` e ON e.name = ssa.employee
        WHERE ssa.docstatus = 1
            AND ssa.from_date > %s
            AND ssa.from_date <= %s
            {employee_filter}
        ORDER BY ssa.from_date DESC
    """.format(
        employee_filter="AND ssa.employee IN %(employees)s" if employees else ""
    ), {
        "start_date": start_date,
        "end_date": end_date,
        "employees": employees or []
    }, as_dict=True)
    
    # Return dict with latest assignment per employee
    result = {}
    for assignment in assignments:
        if assignment.employee not in result:
            result[assignment.employee] = {
                "from_date": assignment.from_date,
                "employee_name": assignment.employee_name
            }
    
    return result


def calculate_prorata_payment_days(ssa_from_date, period_start_date, period_end_date):
    """
    Calculate pro-rata payment days for mid-period salary structure.
    
    Args:
        ssa_from_date: Salary Structure Assignment from_date
        period_start_date: Payroll period start
        period_end_date: Payroll period end
    
    Returns:
        Number of payment days from SSA from_date to period end
    """
    ssa_from_date = getdate(ssa_from_date)
    period_start_date = getdate(period_start_date)
    period_end_date = getdate(period_end_date)
    
    # If SSA from_date is after period start, use SSA from_date
    effective_start = max(ssa_from_date, period_start_date)
    
    # Calculate days (inclusive of both start and end)
    payment_days = date_diff(period_end_date, effective_start) + 1
    
    return max(0, payment_days)


def validate_salary_slip_for_mid_period_ssa(doc, method=None):
    """
    Hook for Salary Slip validate - adjusts payment days for mid-period SSA.
    """
    if not doc.employee or not doc.start_date or not doc.end_date:
        return
    
    # Check if employee has a mid-period salary structure assignment
    mid_period_employees = get_employees_with_mid_period_salary_structure(
        doc.start_date, 
        doc.end_date,
        [doc.employee]
    )
    
    if doc.employee in mid_period_employees:
        ssa_data = mid_period_employees[doc.employee]
        ssa_from_date = ssa_data["from_date"]
        
        # Calculate total period days
        total_period_days = date_diff(doc.end_date, doc.start_date) + 1
        
        # Calculate pro-rata payment days
        prorata_days = calculate_prorata_payment_days(
            ssa_from_date, 
            doc.start_date, 
            doc.end_date
        )
        
        # Store original payment days for reference
        original_payment_days = doc.payment_days
        
        # Only adjust if SSA from_date is after period start
        if getdate(ssa_from_date) > getdate(doc.start_date):
            # Adjust payment days (cap at calculated pro-rata days)
            doc.payment_days = min(doc.payment_days, prorata_days)
            
            # Add a comment for audit trail
            frappe.msgprint(
                f"Salary for {doc.employee_name} adjusted for mid-period joining. "
                f"SSA effective from {frappe.format(ssa_from_date, 'Date')}. "
                f"Payment days: {prorata_days} (out of {total_period_days} period days)",
                title="Pro-rata Salary Adjustment",
                indicator="blue"
            )


def before_salary_slip_submit(doc, method=None):
    """
    Final validation before submit to ensure pro-rata is correctly applied.
    """
    validate_salary_slip_for_mid_period_ssa(doc, method)


@frappe.whitelist()
def get_mid_period_employees_report(start_date, end_date, company=None):
    """
    API to get list of employees with mid-period salary structure assignments.
    Useful for review before payroll processing.
    
    Args:
        start_date: Period start date
        end_date: Period end date
        company: Optional company filter
    
    Returns:
        List of employees with their pro-rata details
    """
    query = """
        SELECT 
            ssa.employee,
            e.employee_name,
            e.designation,
            e.department,
            ssa.from_date as ssa_from_date,
            ssa.salary_structure,
            DATEDIFF(%s, ssa.from_date) + 1 as payment_days,
            DATEDIFF(%s, %s) + 1 as total_period_days
        FROM `tabSalary Structure Assignment` ssa
        INNER JOIN `tabEmployee` e ON e.name = ssa.employee
        WHERE ssa.docstatus = 1
            AND ssa.from_date > %s
            AND ssa.from_date <= %s
            AND e.status = 'Active'
            {company_filter}
        ORDER BY ssa.from_date
    """.format(
        company_filter="AND e.company = %(company)s" if company else ""
    )
    
    params = [end_date, end_date, start_date, start_date, end_date]
    if company:
        params.append(company)
    
    employees = frappe.db.sql(query, params, as_dict=True)
    
    # Calculate pro-rata percentage
    for emp in employees:
        emp["prorata_percentage"] = flt(
            (emp["payment_days"] / emp["total_period_days"]) * 100, 2
        )
    
    return employees


@frappe.whitelist()
def get_employees_without_salary_structure(start_date, employees=None):
    """
    Find employees without a valid salary structure assignment before the given date.
    Helps identify the 'None' employee issue in Payroll Entry.
    
    Args:
        start_date: The date to check SSA validity against
        employees: Optional list of employee IDs
    
    Returns:
        List of employees without valid SSA
    """
    if employees and isinstance(employees, str):
        import json
        employees = json.loads(employees)
    
    employee_filter = ""
    if employees:
        employee_filter = f"AND e.name IN {tuple(employees) if len(employees) > 1 else f\"('{employees[0]}')\"}".replace(",)", ")")
    
    query = f"""
        SELECT 
            e.name as employee,
            e.employee_name,
            e.designation,
            e.department,
            e.status
        FROM `tabEmployee` e
        WHERE e.status = 'Active'
            {employee_filter}
            AND NOT EXISTS (
                SELECT 1 
                FROM `tabSalary Structure Assignment` ssa 
                WHERE ssa.employee = e.name 
                    AND ssa.from_date <= %s
                    AND ssa.docstatus = 1
            )
        ORDER BY e.name
    """
    
    return frappe.db.sql(query, [start_date], as_dict=True)

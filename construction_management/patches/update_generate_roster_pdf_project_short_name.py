import frappe


def execute():
	if not frappe.db.exists("Server Script", "generate_roster_pdf"):
		return

	doc = frappe.get_doc("Server Script", "generate_roster_pdf")
	doc.script = SCRIPT
	doc.save(ignore_permissions=True)
	frappe.db.commit()


SCRIPT = """
from_date = frappe.form_dict.get("from_date")
to_date = frappe.form_dict.get("to_date")

if not from_date or not to_date:
    frappe.throw("From Date and To Date are required")

rosters = frappe.get_all(
    "Daily Roster",
    filters={"date": ["between", [from_date, to_date]], "docstatus": 1},
    fields=[
        "name",
        "date",
        "project",
        "custom_project_short_name",
        "time_in",
        "time_out",
        "custom_engineer_name",
        "company",
        "custom_contractor",
        "custom_external_workers",
        "custom_foreman",
        "custom_total_workers",
        "remarks"
    ],
    order_by="date asc"
)

if not rosters:
    frappe.throw("No records found")

rows = ""
total_internal_count = 0

for i, r in enumerate(rosters):

    workers = frappe.get_all(
        "Roster Employee Child",
        filters={"parent": r.name},
        fields=["employee"]
    )

    internal_names = []

    for w in workers:
        emp_name = frappe.db.get_value(
            "Employee", w.employee, "employee_name"
        ) or w.employee

        internal_names.append(emp_name)
        total_internal_count += 1

    project_display = r.project or ""
    short_name = r.custom_project_short_name
    if not short_name and r.project:
        short_name = frappe.db.get_value("Project", r.project, "custom_project_short_name")
    if project_display and short_name:
        project_display = f"{project_display} - {short_name}"

    rows += f\"\"\"
    <tr>
        <td style="text-align:center;">{i + 1}</td>
        <td>{r.custom_contractor or ""}</td>
        <td>{project_display}</td>
        <td>{r.custom_engineer_name or ""}</td>
        <td>{r.custom_foreman or ""}</td>
        <td style="text-align:center;">{r.time_in or ""}</td>
        <td style="text-align:center;">{r.time_out or ""}</td>
        <td style="color:#1a5fb4;font-weight:bold;">{" - ".join(internal_names)}</td>
        <td class="external-col" style="color:#d9534f;font-weight:bold;">
            {r.custom_external_workers or ""}
        </td>
        <td style="text-align:center;">{r.custom_total_workers or ""}</td>
        <td>{r.remarks or ""}</td>
    </tr>
    \"\"\"

company = rosters[0].company

html = f\"\"\"
<!DOCTYPE html>
<html>
<head>

<script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>

<style>

@page {{
    size: A4 landscape;
    margin: 8mm;
}}

body {{
    font-family: Helvetica, Arial, sans-serif;
    font-size: 8.2pt;
    margin: 20px;
}}

.no-print-bar {{
    text-align: right;
    margin-bottom: 15px;
}}

.btn {{
    padding: 8px 14px;
    margin-left: 5px;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    font-weight: bold;
    color: #fff;
}}

.btn-print {{ background: #28a745; }}
.btn-image {{ background: #007bff; }}

table {{
    width: 100%;
    border-collapse: collapse;
    table-layout: fixed;
}}

th, td {{
    border: 1px solid #000;
    padding: 5px;
}}

th {{
    background: #444;
    color: #fff;
    font-size: 7.5pt;
}}

.external-col {{
    width: 90px;
    word-wrap: break-word;
    white-space: normal;
}}

@media print {{
    .no-print-bar {{ display: none; }}
}}

</style>
</head>

<body>

<div class="no-print-bar">
    <button class="btn btn-print" onclick="window.print()">Print / Save PDF</button>
    <button class="btn btn-image" onclick="saveAsImage()">Save as Image</button>
</div>

<div id="report-area">

<table style="border:none;margin-bottom:15px;">
<tr>

<td width="30%">
    <img src="/files/mrg-logo.jpeg" style="width:130px;">
</td>

<td width="40%" style="text-align:center;">
    <h2 style="margin:0;text-decoration:underline;">{company}</h2>
    <h3 style="margin:5px 0;">DAILY WORK PROGRAM SHEET</h3>
    <b>Period: {from_date} to {to_date}</b>
</td>

<td width="30%" style="text-align:right;">
    <img src="/files/skada-logo.jpeg" style="width:100px;">
</td>

</tr>
</table>


<table>

<thead>
<tr>
    <th style="width:25px;">SR</th>
    <th style="width:130px;">Contractor</th>
    <th style="width:120px;">Project</th>
    <th style="width:120px;">Engineer</th>
    <th style="width:120px;">Foreman</th>
    <th style="width:60px;">In</th>
    <th style="width:60px;">Out</th>
    <th>Labour (Internal)</th>
    <th class="external-col">Labour (External)</th>
    <th style="width:80px;">Total Workers</th>
    <th style="width:100px;">Remarks</th>
</tr>
</thead>

<tbody>
{rows}
</tbody>

</table>

<div style="margin-top:10px;font-weight:bold;">
Total Internal Employees Assigned: {total_internal_count}
</div>

</div>

<script>

function saveAsImage() {{
    const element = document.getElementById("report-area");

    html2canvas(element, {{ scale: 2 }}).then(canvas => {{
        const link = document.createElement("a");
        link.download = "Daily_Work_Program.png";
        link.href = canvas.toDataURL("image/png");
        link.click();
    }});
}}

</script>

</body>
</html>
\"\"\"

frappe.response["type"] = "json"
frappe.response["message"] = {"html": html}
"""

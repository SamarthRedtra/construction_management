// Controlled Procurement now runs as a standalone app at /procurement.
frappe.pages["controlled-procurement"].on_page_load = () => {
	window.location.href = "/procurement"
}

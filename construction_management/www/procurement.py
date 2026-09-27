import json
from pathlib import Path
from urllib.parse import quote

import frappe
from frappe import _
from frappe.sessions import get_csrf_token

from construction_management.api.controlled_procurement import PURCHASE_ROLES, STOCK_ROLES

no_cache = 1

APP_ROUTE = "procurement"
ASSET_BASE = "/assets/construction_management/controlled_procurement/"


def has_app_permission() -> bool:
	if frappe.session.user == "Guest":
		return False
	return bool(set(frappe.get_roles()).intersection(PURCHASE_ROLES | STOCK_ROLES))


def get_context(context):
	if frappe.session.user == "Guest":
		path = frappe.local.request.path if getattr(frappe.local, "request", None) else f"/{APP_ROUTE}"
		frappe.local.flags.redirect_location = f"/login?redirect-to={quote(path)}"
		raise frappe.Redirect
	if not has_app_permission():
		frappe.throw(_("You do not have permission to access Controlled Procurement"), frappe.PermissionError)

	context.no_cache = 1
	context.title = _("Controlled Procurement")
	context.frontend_assets = get_frontend_assets()
	context.boot = {
		"csrf_token": frappe.session.data.get("csrf_token") or get_csrf_token(),
		"session_user": frappe.session.user,
		"site_name": frappe.local.site,
		"app_route": f"/{APP_ROUTE}",
	}
	return context


def get_frontend_assets():
	manifest_path = Path(
		frappe.get_app_path("construction_management", "public", "controlled_procurement", ".vite", "manifest.json")
	)
	if not manifest_path.exists():
		return None
	entry = json.loads(manifest_path.read_text()).get("index.html")
	if not entry:
		return None
	return frappe._dict(
		entry=f"{ASSET_BASE}{entry['file']}",
		styles=[f"{ASSET_BASE}{css}" for css in entry.get("css", [])],
	)

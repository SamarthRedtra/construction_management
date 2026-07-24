# Copyright (c) 2026, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime
from erpnext.selling.doctype.quotation.quotation import Quotation

PLACEHOLDER_ITEM_CODE = "QUOTATION-BOQ"

APPROVAL_QUOTATION_STATUSES = {
	"Pending Sales Manager Approval",
	"Pending Director Approval",
	"Rejected by Sales Manager",
	"Rejected by Director",
}


class QuotationOverride(Quotation):
	def insert(self, *args, **kwargs):
		self._prepare_boq_before_link_validation()
		return super().insert(*args, **kwargs)

	def save(self, *args, **kwargs):
		self._prepare_boq_before_link_validation()
		return super().save(*args, **kwargs)

	def validate(self):
		self._reset_amendment_approval_state()
		self._set_default_sales_person()
		self._apply_vat_preference()
		self._update_boq_line_amounts()
		self._sync_boq_html_from_lines()
		self._ensure_boq_placeholder_item()
		super().validate()

	def on_submit(self):
		super().on_submit()
		self._start_approval()
		# Approval workflow starts immediately; refresh Lead after custom status is applied.
		_sync_linked_lead_status(self)

	def on_cancel(self):
		"""A cancelled quotation must not keep approval alerts open."""
		super().on_cancel()
		_close_open_quotation_assignments(self)
		_sync_linked_lead_status(self)

	def update_lead(self):
		"""Keep Lead status in sync with custom Agreed / Not Agreed quotation flow."""
		_sync_linked_lead_status(self)

	def copy_attachments_from_amended_from(self):
		"""Copy usable attachments without letting a missing legacy file block amendment."""
		from frappe.desk.form.load import get_attachments

		for attachment in get_attachments(self.doctype, self.amended_from):
			source_file = frappe.get_doc("File", attachment.name)
			if not source_file.exists_on_disk():
				self.add_comment(
					"Info",
					_("Attachment {0} was not copied because its source file is missing.").format(
						frappe.bold(attachment.file_name)
					),
				)
				continue

			frappe.get_doc(
				{
					"doctype": "File",
					"file_url": attachment.file_url,
					"file_name": attachment.file_name,
					"attached_to_name": self.name,
					"attached_to_doctype": self.doctype,
					"attached_to_field": attachment.attached_to_field,
					"folder": attachment.folder or "Home/Attachments",
					"is_private": attachment.is_private,
				}
			).save()

	def set_status(self, update=False, status=None, update_modified=True):
		"""Keep the normal Quotation Status visible while approval is in progress."""
		super().set_status(update=update, status=status, update_modified=update_modified)
		approval_status = _visible_quotation_status(
			self.get("custom_approval_status"), self.get("custom_agreement_status")
		)
		if self.docstatus == 1 and approval_status:
			self.status = approval_status
			if update:
				self.db_set("status", approval_status, update_modified=update_modified)

	def _prepare_boq_before_link_validation(self):
		"""Create placeholder Item before Frappe _validate_links (runs before validate)."""
		if not self.get("custom_boq_lines"):
			return

		_get_or_create_placeholder_item(self.company)
		self._update_boq_line_amounts()
		self._ensure_boq_placeholder_item()

	def get_boq_quotation_print_context(self):
		"""Build dict for BOQ Quotation Jinja print format."""
		from construction_management.quotation_boq_print_context import build_boq_quotation_print_context

		return build_boq_quotation_print_context(self)

	def _update_boq_line_amounts(self):
		for row in self.get("custom_boq_lines") or []:
			if row.get("line_type") != "Sub":
				row.amount = 0
				continue

			display_mode = row.get("display_mode") or "Normal"
			if display_mode != "Normal":
				row.amount = 0
			elif not _is_manual_amount_line(row):
				row.amount = flt(row.qty) * flt(row.rate)

	def _sync_boq_html_from_lines(self):
		lines = self.get("custom_boq_lines") or []
		if not lines:
			return

		from construction_management.api.quotation_boq import lines_to_boq_html

		self.custom_boq_html = lines_to_boq_html(
			lines,
			include_totals=True,
			company=self.company,
			include_vat=_include_vat(self),
		)

	def _boq_total(self) -> float:
		return sum(
			flt(row.amount)
			for row in self.get("custom_boq_lines") or []
			if row.get("line_type") == "Sub"
			and (row.get("display_mode") or "Normal") == "Normal"
		)

	def _set_default_sales_person(self):
		if not frappe.get_meta("Quotation").has_field("custom_sales_person") or self.get("custom_sales_person"):
			return
		employee = frappe.db.get_value("Employee", {"user_id": self.owner, "status": "Active"}, "name")
		if employee:
			self.custom_sales_person = frappe.db.get_value(
				"Sales Person", {"employee": employee, "enabled": 1}, "name"
			)

	def _reset_amendment_approval_state(self):
		"""Clear inherited approval decisions only when first creating an amendment.

		Frappe copies custom fields from the cancelled quotation into its amendment.
		Approval decisions and the old cost sheet must not be copied into the new draft.

		IMPORTANT: run only on first create (`is_new()`). Running on every validate was
		wiping a user-selected Sales Manager Approver on each Save/Submit.
		"""
		if not self.get("amended_from") or self.docstatus != 0:
			return
		if not self.is_new():
			return

		for fieldname in (
			"custom_approval_status",
			"custom_agreement_status",
			"custom_cost_sheet",
			"custom_sales_manager_approver",
			"custom_director_approver",
			"custom_sales_manager_approved_by",
			"custom_sales_manager_approval_date",
			"custom_director_approved_by",
			"custom_director_approval_date",
		):
			self.set(fieldname, None)

	def _apply_vat_preference(self):
		"""A VAT-excluded quotation must not retain tax rows from a template."""
		if not _include_vat(self):
			self.taxes = []
			self.taxes_and_charges = None

	def _start_approval(self):
		managers, directors = _get_quotation_approvers(self.company)
		if not managers or not directors:
			frappe.throw(
				_("Configure at least one Quotation Sales Manager and one Quotation Director on Company {0} before submitting.").format(
					frappe.bold(self.company)
				)
			)
		# One Sales Manager per quotation (not the full Company list) + all Directors.
		assigned_manager = _resolve_assigned_sales_manager(self, managers)
		self.db_set("custom_sales_manager_approver", assigned_manager, update_modified=False)
		self.db_set("custom_director_approver", directors[0], update_modified=False)
		self.db_set("custom_approval_status", "Pending Sales Manager Approval", update_modified=False)
		self.db_set("custom_agreement_status", "Pending", update_modified=False)
		self.db_set("status", "Pending Sales Manager Approval", update_modified=False)
		_assign_quotation_users(
			self,
			[assigned_manager],
			_("Quotation requires sales-manager approval and cost sheet."),
		)
		# Directors are alerted immediately, so they can step in when no manager responds.
		_assign_quotation_users(
			self,
			directors,
			_("Director alert: Sales-manager approval is pending. You may act on behalf of the manager."),
			cancel_open=False,
		)

	def _ensure_boq_placeholder_item(self):
		"""Keep one valid Quotation Item so ERPNext mandatory Item Name / UOM pass."""
		lines = self.get("custom_boq_lines") or []
		if not lines:
			# Drop blank item rows that cause "Item Name / UOM required"
			self.items = [
				row
				for row in (self.get("items") or [])
				if row.get("item_code") or row.get("item_name")
			]
			return

		item_code = _get_or_create_placeholder_item(self.company)
		item_meta = frappe.db.get_value(
			"Item",
			item_code,
			["item_name", "stock_uom", "description"],
			as_dict=True,
		) or {}
		uom = item_meta.get("stock_uom") or "Nos"
		item_name = item_meta.get("item_name") or "Quotation BOQ"
		description = item_meta.get("description") or "Quotation Bill of Quantities"
		boq_total = self._boq_total()

		# Remove blank / non-placeholder rows so user never manages Items
		self.items = [
			row
			for row in (self.get("items") or [])
			if row.get("item_code") == item_code
		]

		if self.items:
			row = self.items[0]
			row.item_code = item_code
			row.item_name = item_name
			row.description = description
			row.uom = uom
			row.qty = 1
			row.rate = boq_total
			row.amount = boq_total
		else:
			self.append(
				"items",
				{
					"item_code": item_code,
					"item_name": item_name,
					"description": description,
					"uom": uom,
					"qty": 1,
					"rate": boq_total,
					"amount": boq_total,
				},
			)

		self.with_items = 1


def _is_manual_amount_line(row) -> bool:
	"""Selected Fixed Amount lines retain their entered amount; all others use Qty × Rate."""
	return bool(cint(row.get("is_fixed_rate")))


def _include_vat(doc) -> bool:
	"""Documents created before the field was introduced keep the historical VAT behaviour."""
	value = doc.get("custom_include_vat")
	return value is None or bool(cint(value))


def _visible_quotation_status(approval_status: str | None, agreement_status: str | None) -> str | None:
	if approval_status in APPROVAL_QUOTATION_STATUSES:
		return approval_status
	if approval_status == "Approved":
		return agreement_status if agreement_status in {"Agreed", "Not Agreed"} else "Pending Agreement"
	return None


def _ensure_lead_agreed_status_option():
	"""Allow Lead.Status = Agreed (used when Quotation is marked Agreed)."""
	meta = frappe.get_meta("Lead")
	field = meta.get_field("status")
	if not field:
		return
	options = [o for o in (field.options or "").split("\n") if o is not None]
	if "Agreed" in options:
		return
	if "Quotation" in options:
		idx = options.index("Quotation") + 1
		options.insert(idx, "Agreed")
	else:
		options.append("Agreed")
	new_options = "\n".join(options)
	existing = frappe.db.exists(
		"Property Setter",
		{"doc_type": "Lead", "field_name": "status", "property": "options"},
	)
	if existing:
		frappe.db.set_value("Property Setter", existing, "value", new_options)
	else:
		frappe.make_property_setter(
			{
				"doctype": "Lead",
				"fieldname": "status",
				"property": "options",
				"value": new_options,
				"property_type": "Text",
			},
			validate_fields_for_doctype=False,
		)
	frappe.clear_cache(doctype="Lead")


def _sync_linked_lead_status(doc):
	"""Push Quotation lifecycle onto the linked Lead (Agreed / Not Agreed / Quotation / Lost)."""
	if getattr(doc, "quotation_to", None) != "Lead" or not doc.get("party_name"):
		return
	if not frappe.db.exists("Lead", doc.party_name):
		return

	_ensure_lead_agreed_status_option()

	# Prefer highest progress across all submitted quotations for this Lead
	rows = frappe.get_all(
		"Quotation",
		filters={
			"quotation_to": "Lead",
			"party_name": doc.party_name,
			"docstatus": 1,
		},
		fields=["name", "status", "custom_agreement_status", "custom_approval_status"],
	)

	lead_status = None
	statuses = {r.get("status") for r in rows}
	agreements = {r.get("custom_agreement_status") for r in rows}

	if any(s in {"Ordered", "Partially Ordered"} for s in statuses):
		# Customer may not exist yet; keep Agreed until Customer converts the Lead
		lead_status = "Agreed"
	elif "Agreed" in statuses or "Agreed" in agreements:
		lead_status = "Agreed"
	elif any(
		s
		and s
		not in {
			"Lost",
			"Not Agreed",
			"Cancelled",
			"Rejected by Sales Manager",
			"Rejected by Director",
		}
		for s in statuses
	):
		lead_status = "Quotation"
	elif "Not Agreed" in statuses or "Not Agreed" in agreements or "Lost" in statuses:
		lead_status = "Lost Quotation"
	elif rows:
		lead_status = "Quotation"

	lead = frappe.get_doc("Lead", doc.party_name)
	# Never downgrade Converted
	if lead.status == "Converted" or lead.has_customer():
		lead.set_status(update=True)
		return

	if not lead_status:
		lead.set_status(update=True)
		return

	if lead.status != lead_status:
		lead.db_set("status", lead_status, update_modified=True)
		lead.add_comment(
			"Info",
			_("Status updated to {0} from Quotation {1}.").format(
				frappe.bold(lead_status), frappe.bold(doc.name)
			),
		)


def _get_quotation_approvers(company: str) -> tuple[list[str], list[str]]:
	if not company:
		return [], []
	company_doc = frappe.get_doc("Company", company)
	managers = _approver_users(company_doc.get("custom_quotation_sales_managers"))
	directors = _approver_users(company_doc.get("custom_quotation_directors"))
	return (
		managers or _approver_users(company_doc.get("custom_quotation_sales_manager")),
		directors or _approver_users(company_doc.get("custom_quotation_director")),
	)


def _approver_users(rows_or_user) -> list[str]:
	"""Accept both the old single Link value and the new Table MultiSelect rows."""
	if isinstance(rows_or_user, str):
		return [rows_or_user] if rows_or_user else []
	users = []
	for row in rows_or_user or []:
		user = row.get("user") if hasattr(row, "get") else None
		if user and user not in users:
			users.append(user)
	return users


def _sales_person_user(sales_person: str | None) -> str | None:
	if not sales_person:
		return None
	employee = frappe.db.get_value("Sales Person", sales_person, "employee")
	if not employee:
		return None
	return frappe.db.get_value("Employee", employee, "user_id")


def _resolve_assigned_sales_manager(doc, managers: list[str]) -> str:
	"""Resolve the single Sales Manager for this quotation.

	Company may list several Quotation Sales Managers; only one is assigned
	per quotation (ToDo / Sales Manager Approver).
	"""
	selected = (doc.get("custom_sales_manager_approver") or "").strip()
	if selected in managers:
		return selected

	from_sales_person = _sales_person_user(doc.get("custom_sales_person"))
	if from_sales_person in managers:
		return from_sales_person

	if len(managers) == 1:
		return managers[0]

	frappe.throw(
		_(
			"Select the Sales Manager Approver before submitting this quotation. "
			"Available managers: {0}"
		).format(", ".join(managers))
	)


@frappe.whitelist()
def get_quotation_approver_options(company: str) -> dict:
	"""Company-configured manager / director user lists for Quotation form filters."""
	managers, directors = _get_quotation_approvers(company)
	return {"managers": managers, "directors": directors}


@frappe.whitelist()
def get_sales_person_manager_user(sales_person: str | None = None, company: str | None = None) -> str | None:
	"""Return the Sales Person's user if they are a Quotation Sales Manager for the company."""
	user = _sales_person_user(sales_person)
	if not user:
		return None
	managers, _ = _get_quotation_approvers(company)
	return user if user in managers else None


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def sales_manager_approver_query(
	doctype: str,
	txt: str,
	searchfield: str,
	start: int,
	page_len: int,
	filters: dict | None = None,
):
	"""Link search for Sales Manager Approver — scoped to Company managers, ignores User perms.

	Standard User link search uses get_list and fails for users without User read permission.
	"""
	filters = filters or {}
	if isinstance(filters, str):
		import json

		try:
			filters = json.loads(filters)
		except Exception:
			filters = {}
	company = filters.get("company")
	managers, _ = _get_quotation_approvers(company)
	if not managers:
		return []

	txt = (txt or "").strip()
	like = f"%{txt}%"
	rows = frappe.db.sql(
		"""
		SELECT name, IFNULL(full_name, name) AS full_name
		FROM `tabUser`
		WHERE enabled = 1
			AND name IN %(managers)s
			AND (
				%(txt)s = ''
				OR name LIKE %(like)s
				OR IFNULL(full_name, '') LIKE %(like)s
				OR IFNULL(first_name, '') LIKE %(like)s
				OR IFNULL(last_name, '') LIKE %(like)s
			)
		ORDER BY full_name ASC, name ASC
		LIMIT %(start)s, %(page_len)s
		""",
		{
			"managers": tuple(managers),
			"txt": txt,
			"like": like,
			"start": int(start or 0),
			"page_len": int(page_len or 20),
		},
	)
	return rows



def _assign_quotation_users(doc, users: list[str], description: str, *, cancel_open: bool = True):
	"""Create visible quotation-level alerts for every designated user."""
	if cancel_open:
		_close_open_quotation_assignments(doc)
	for user in dict.fromkeys(users):
		if not user or user == "Guest":
			continue
		if frappe.db.exists(
			"ToDo",
			{
				"allocated_to": user,
				"reference_type": "Quotation",
				"reference_name": doc.name,
				"status": "Open",
			},
		):
			continue
		frappe.get_doc(
			{
				"doctype": "ToDo",
				"allocated_to": user,
				"reference_type": "Quotation",
				"reference_name": doc.name,
				"description": description,
				"status": "Open",
				"priority": "Medium",
			}
		).insert(ignore_permissions=True)


def _close_open_quotation_assignments(doc):
	frappe.db.set_value(
		"ToDo",
		{"reference_type": "Quotation", "reference_name": doc.name, "status": "Open"},
		"status",
		"Cancelled",
		update_modified=False,
	)


def _get_submitted_quotation(quotation: str):
	doc = frappe.get_doc("Quotation", quotation)
	if doc.docstatus != 1:
		frappe.throw(_("Only a submitted quotation can be approved."))
	return doc


@frappe.whitelist()
def create_quotation_amendment(quotation: str) -> dict:
	"""Create a clean draft amendment for a cancelled quotation.

	The Desk's local-copy flow can retain the cancelled form state when a
	Quotation has the BOQ client scripts loaded.  Creating the amendment on the
	server gives the user an actual writable draft and retains Frappe's standard
	amended-from validation.
	"""
	original = frappe.get_doc("Quotation", quotation)
	original.check_permission("amend")
	if original.docstatus != 2:
		frappe.throw(_("Cancel the quotation before creating an amendment."))

	# A cancelled amendment is itself the document that must be amended next.
	# Follow that chain so a repeated amendment receives the correct suffix.
	last_amendment = original
	while next_amendment := frappe.db.get_value(
		"Quotation", {"amended_from": last_amendment.name}, "name", order_by="creation desc"
	):
		last_amendment = frappe.get_doc("Quotation", next_amendment)

	if last_amendment.name != original.name and last_amendment.docstatus != 2:
		# An interrupted request may already have created a usable draft. Reopen it
		# rather than presenting the user with an unrecoverable duplicate error.
		return {"name": last_amendment.name, "existing": True}

	# Python's copy_doc normally removes fields marked no_copy. For an amendment,
	# that would incorrectly drop Company and fall back to the system default.
	amendment = frappe.copy_doc(last_amendment, ignore_no_copy=True)
	amendment.amended_from = last_amendment.name
	amendment.docstatus = 0
	amendment.status = "Draft"
	amendment.company = original.company
	amendment.insert()
	return {"name": amendment.name}


def _require_approver(doc, approval_type: str):
	if _is_administrator():
		return
	managers, directors = _get_quotation_approvers(doc.company)
	if approval_type == "manager":
		assigned = doc.get("custom_sales_manager_approver")
		approvers = [assigned] if assigned else managers
	else:
		approvers = directors
	if frappe.session.user not in approvers:
		frappe.throw(_("Only the configured approver can perform this action."), frappe.PermissionError)


def _is_administrator() -> bool:
	"""Administrator can manage approvals for every Company."""
	return frappe.session.user == "Administrator"


def _set_approval_state(doc, state: str, *, comment: str = ""):
	doc.db_set("custom_approval_status", state, update_modified=False)
	visible_status = _visible_quotation_status(state, doc.get("custom_agreement_status"))
	if visible_status:
		doc.db_set("status", visible_status, update_modified=False)
	_close_open_quotation_assignments(doc)
	if comment:
		doc.add_comment("Comment", comment)
	_sync_linked_lead_status(doc)


@frappe.whitelist()
def sales_manager_approve_quotation(quotation: str):
	doc = _get_submitted_quotation(quotation)
	_require_approver(doc, "manager")
	if doc.get("custom_approval_status") != "Pending Sales Manager Approval":
		frappe.throw(_("This quotation is not awaiting sales-manager approval."))
	if not doc.get("custom_cost_sheet"):
		frappe.throw(_("Upload the cost sheet before approving this quotation."))

	doc.db_set("custom_sales_manager_approved_by", frappe.session.user, update_modified=False)
	doc.db_set("custom_sales_manager_approval_date", now_datetime(), update_modified=False)
	_set_approval_state(doc, "Pending Director Approval", comment=_("Approved by Sales Manager."))
	managers, directors = _get_quotation_approvers(doc.company)
	_assign_quotation_users(doc, directors, _("Quotation requires director approval."))
	return {"status": "Pending Director Approval"}


@frappe.whitelist()
def sales_manager_reject_quotation(quotation: str, reason: str | None = None):
	doc = _get_submitted_quotation(quotation)
	_require_approver(doc, "manager")
	if doc.get("custom_approval_status") != "Pending Sales Manager Approval":
		frappe.throw(_("This quotation is not awaiting sales-manager approval."))
	_set_approval_state(doc, "Rejected by Sales Manager", comment=_("Rejected by Sales Manager. {0}").format(reason or ""))
	return {"status": "Rejected by Sales Manager"}


@frappe.whitelist()
def director_approve_sales_manager_on_behalf(quotation: str):
	"""A director can unblock the first level when no assigned manager responds."""
	doc = _get_submitted_quotation(quotation)
	_require_approver(doc, "director")
	if doc.get("custom_approval_status") != "Pending Sales Manager Approval":
		frappe.throw(_("This quotation is not awaiting sales-manager approval."))
	if not doc.get("custom_cost_sheet"):
		frappe.throw(_("Upload the cost sheet before approving on behalf of the Sales Manager."))

	doc.db_set("custom_sales_manager_approved_by", frappe.session.user, update_modified=False)
	doc.db_set("custom_sales_manager_approval_date", now_datetime(), update_modified=False)
	_set_approval_state(
		doc,
		"Pending Director Approval",
		comment=_("Director approved on behalf of the Sales Manager."),
	)
	managers, directors = _get_quotation_approvers(doc.company)
	_assign_quotation_users(doc, directors, _("Quotation requires director approval."))
	return {"status": "Pending Director Approval"}


@frappe.whitelist()
def director_reject_sales_manager_on_behalf(quotation: str, reason: str | None = None):
	doc = _get_submitted_quotation(quotation)
	_require_approver(doc, "director")
	if doc.get("custom_approval_status") != "Pending Sales Manager Approval":
		frappe.throw(_("This quotation is not awaiting sales-manager approval."))
	_set_approval_state(
		doc,
		"Rejected by Sales Manager",
		comment=_("Director rejected on behalf of the Sales Manager. {0}").format(reason or ""),
	)
	return {"status": "Rejected by Sales Manager"}


@frappe.whitelist()
def director_approve_quotation(quotation: str):
	doc = _get_submitted_quotation(quotation)
	_require_approver(doc, "director")
	if doc.get("custom_approval_status") != "Pending Director Approval":
		frappe.throw(_("This quotation is not awaiting director approval."))

	doc.db_set("custom_director_approved_by", frappe.session.user, update_modified=False)
	doc.db_set("custom_director_approval_date", now_datetime(), update_modified=False)
	doc.db_set("custom_agreement_status", "Pending", update_modified=False)
	_set_approval_state(doc, "Approved", comment=_("Approved by Director."))
	return {"status": "Approved"}


@frappe.whitelist()
def director_reject_quotation(quotation: str, reason: str | None = None):
	doc = _get_submitted_quotation(quotation)
	_require_approver(doc, "director")
	if doc.get("custom_approval_status") != "Pending Director Approval":
		frappe.throw(_("This quotation is not awaiting director approval."))
	_set_approval_state(doc, "Rejected by Director", comment=_("Rejected by Director. {0}").format(reason or ""))
	return {"status": "Rejected by Director"}


@frappe.whitelist()
def set_quotation_agreement(quotation: str, agreed: int | str, reason: str | None = None):
	doc = _get_submitted_quotation(quotation)
	if doc.get("custom_approval_status") != "Approved":
		frappe.throw(_("Director approval is required before recording agreement."))
	managers, directors = _get_quotation_approvers(doc.company)
	allowed_users = {"Administrator", doc.owner, *managers, *directors}
	if frappe.session.user not in allowed_users:
		frappe.throw(_("You are not permitted to record this agreement."), frappe.PermissionError)

	agreement = "Agreed" if cint(agreed) else "Not Agreed"
	doc.db_set("custom_agreement_status", agreement, update_modified=False)
	doc.db_set("status", agreement, update_modified=False)
	doc.db_set("custom_agreement_recorded_by", frappe.session.user, update_modified=False)
	doc.db_set("custom_agreement_date", now_datetime(), update_modified=False)
	doc.add_comment("Comment", _("Agreement marked as {0}. {1}").format(agreement, reason or ""))
	_sync_linked_lead_status(doc)
	return {"status": agreement}


@frappe.whitelist()
def get_quotation_approval_access(quotation: str) -> dict:
	"""Form-level access flags for the assigned manager and all directors."""
	doc = frappe.get_doc("Quotation", quotation)
	doc.check_permission("read")
	managers, directors = _get_quotation_approvers(doc.company)
	user = frappe.session.user
	is_administrator = _is_administrator()
	assigned_manager = doc.get("custom_sales_manager_approver")
	is_assigned_manager = bool(assigned_manager and user == assigned_manager)
	# Draft / legacy rows without an assigned manager: any configured manager.
	is_manager = is_administrator or is_assigned_manager or (not assigned_manager and user in managers)
	return {
		"is_manager": is_manager,
		"is_director": is_administrator or user in directors,
		"is_administrator": is_administrator,
		"assigned_manager": assigned_manager,
		"manager_count": len(managers),
		"director_count": len(directors),
	}


def _get_or_create_placeholder_item(company: str | None) -> str:
	"""Resolve Company.custom_quotation_boq_item or ensure QUOTATION-BOQ exists."""
	item_code = None
	if company and frappe.db.has_column("Company", "custom_quotation_boq_item"):
		item_code = frappe.db.get_value("Company", company, "custom_quotation_boq_item")

	if item_code and frappe.db.exists("Item", item_code):
		return item_code

	if frappe.db.exists("Item", PLACEHOLDER_ITEM_CODE):
		return PLACEHOLDER_ITEM_CODE

	item_group = frappe.db.get_value("Item Group", {"is_group": 0}, "name") or "All Item Groups"
	stock_uom = frappe.db.get_value("UOM", "Nos") or frappe.db.get_value("UOM", {}, "name")

	doc = frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": PLACEHOLDER_ITEM_CODE,
			"item_name": "Quotation BOQ",
			"item_group": item_group,
			"stock_uom": stock_uom or "Nos",
			"is_stock_item": 0,
			"is_sales_item": 1,
			"is_purchase_item": 0,
			"description": "Service item used for Quotation BOQ totals",
		}
	)
	doc.insert(ignore_permissions=True)
	return PLACEHOLDER_ITEM_CODE


@frappe.whitelist()
def ensure_quotation_boq_placeholder_item(company=None):
	"""Ensure QUOTATION-BOQ Item exists (callable from Quotation form before save)."""
	return _get_or_create_placeholder_item(company)

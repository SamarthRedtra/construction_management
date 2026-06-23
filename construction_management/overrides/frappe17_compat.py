"""
Compatibility patches for mixed-version stacks.

Context:
- ERPNext 16.15 calls `Document.round_floats_in(..., do_not_round_fields=...)`
- Frappe 17 dev in this bench exposes `round_floats_in(self, doc, fieldnames=None)`
  (without `do_not_round_fields` kwarg), causing TypeError at runtime.
"""

import inspect

import frappe
from frappe.model.document import Document


def patch_round_floats_in_do_not_round_fields():
	"""Make Document.round_floats_in accept ERPNext's do_not_round_fields kwarg."""
	original = Document.round_floats_in
	params = inspect.signature(original).parameters

	# Already compatible (or patched before) -> no-op.
	if "do_not_round_fields" in params:
		return

	def _patched_round_floats_in(self, doc, fieldnames=None, do_not_round_fields=None, **kwargs):
		# If explicit fieldnames are not provided, emulate ERPNext behavior by
		# excluding do_not_round_fields from auto-selected numeric fields.
		if not fieldnames and do_not_round_fields:
			skip_fields = set(do_not_round_fields or [])
			fieldnames = (
				df.fieldname
				for df in doc.meta.get("fields", {"fieldtype": ["in", ["Currency", "Float", "Percent"]]})
				if df.fieldname not in skip_fields
			)

		# Ignore extra kwargs for forward compatibility.
		return original(self, doc, fieldnames=fieldnames)

	Document.round_floats_in = _patched_round_floats_in
	frappe.logger().info("Applied compatibility patch for Document.round_floats_in do_not_round_fields")


patch_round_floats_in_do_not_round_fields()


def patch_payment_ledger_entry_submit_compatibility():
	"""Keep ERPNext payment ledger posting compatible with stricter Frappe link validation.

	This bench has ERPNext code that creates Payment Ledger Entry rows with `submit()`.
	During cancellation, those reverse ledger rows intentionally point back to the
	cancelled voucher. Newer Frappe validates cancelled links more strictly, so we
	skip link validation only for these system-created ledger rows.
	"""
	from erpnext.accounts import utils as accounts_utils

	if getattr(accounts_utils.create_payment_ledger_entry, "_cm_patched", False):
		return

	original = accounts_utils.create_payment_ledger_entry

	def _patched_create_payment_ledger_entry(
		gl_entries,
		cancel=0,
		adv_adj=0,
		update_outstanding="Yes",
		from_repost=0,
		partial_cancel=False,
	):
		if not gl_entries:
			return

		ple_map = accounts_utils.get_payment_ledger_entries(gl_entries, cancel=cancel)

		for entry in ple_map:
			ple = frappe.get_doc(entry)

			if cancel:
				accounts_utils.delink_original_entry(ple, partial_cancel=partial_cancel)
				if accounts_utils.is_immutable_ledger_enabled():
					ple.delinked = 0
					ple.posting_date = frappe.form_dict.get("posting_date") or accounts_utils.getdate()

			ple.flags.ignore_permissions = 1
			ple.flags.ignore_links = True
			ple.flags.skip_docstatus_validation = True
			ple.flags.adv_adj = adv_adj
			ple.flags.from_repost = from_repost
			ple.flags.update_outstanding = update_outstanding
			ple.submit()

	_patched_create_payment_ledger_entry._cm_patched = True
	accounts_utils.create_payment_ledger_entry = _patched_create_payment_ledger_entry

	# general_ledger imports the function directly, so patch that reference too.
	try:
		from erpnext.accounts import general_ledger

		general_ledger.create_payment_ledger_entry = _patched_create_payment_ledger_entry
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Payment Ledger Entry compatibility patch failed")

	frappe.logger().info("Applied compatibility patch for Payment Ledger Entry submit links")


patch_payment_ledger_entry_submit_compatibility()


def patch_gl_entry_submit_compatibility():
	"""Keep ERPNext GL posting compatible when GL Entry is non-submittable in site metadata."""
	from erpnext.accounts import general_ledger

	if getattr(general_ledger.make_entry, "_cm_patched", False):
		return

	def _patched_make_entry(args, adv_adj, update_outstanding, from_repost=False):
		gle = frappe.new_doc("GL Entry")
		gle.update(args)
		gle.flags.ignore_permissions = 1
		gle.flags.ignore_links = True
		gle.flags.skip_docstatus_validation = True
		gle.flags.from_repost = from_repost
		gle.flags.adv_adj = adv_adj
		gle.flags.update_outstanding = update_outstanding or "Yes"
		gle.flags.notify_update = False
		gle.submit()

		if (
			not from_repost
			and gle.voucher_type != "Period Closing Voucher"
			and (gle.is_cancelled == 0 or gle.voucher_type == "Journal Entry")
		):
			general_ledger.validate_expense_against_budget(args)

	_patched_make_entry._cm_patched = True
	general_ledger.make_entry = _patched_make_entry
	frappe.logger().info("Applied compatibility patch for GL Entry submit")


patch_gl_entry_submit_compatibility()


def patch_stock_ledger_entry_submit_compatibility():
	"""Keep ERPNext stock posting compatible when Stock Ledger Entry is non-submittable."""
	from erpnext.stock import stock_ledger

	if getattr(stock_ledger.make_entry, "_cm_patched", False):
		return

	def _patched_make_entry(args, allow_negative_stock=False, via_landed_cost_voucher=False):
		args["doctype"] = "Stock Ledger Entry"
		sle = frappe.get_doc(args)
		sle.flags.ignore_permissions = 1
		sle.flags.skip_docstatus_validation = True
		sle.allow_negative_stock = allow_negative_stock
		sle.via_landed_cost_voucher = via_landed_cost_voucher
		sle.submit()

		if args.get("creation_time") and args.get("voucher_type") == "Stock Reconciliation":
			sle.db_set("creation", args.get("creation_time"))

		return sle

	_patched_make_entry._cm_patched = True
	stock_ledger.make_entry = _patched_make_entry
	frappe.logger().info("Applied compatibility patch for Stock Ledger Entry submit")


patch_stock_ledger_entry_submit_compatibility()

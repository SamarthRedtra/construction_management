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

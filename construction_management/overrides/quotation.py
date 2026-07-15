# Copyright (c) 2026, Construction Management
# License: MIT

import frappe
from frappe.utils import flt
from erpnext.selling.doctype.quotation.quotation import Quotation

PLACEHOLDER_ITEM_CODE = "QUOTATION-BOQ"


class QuotationOverride(Quotation):
	def insert(self, *args, **kwargs):
		self._prepare_boq_before_link_validation()
		return super().insert(*args, **kwargs)

	def save(self, *args, **kwargs):
		self._prepare_boq_before_link_validation()
		return super().save(*args, **kwargs)

	def validate(self):
		self._update_boq_line_amounts()
		self._sync_boq_html_from_lines()
		self._ensure_boq_placeholder_item()
		super().validate()

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
			if display_mode == "Normal":
				row.amount = flt(row.qty) * flt(row.rate)
			else:
				row.amount = 0

	def _sync_boq_html_from_lines(self):
		lines = self.get("custom_boq_lines") or []
		if not lines:
			return

		from construction_management.api.quotation_boq import lines_to_boq_html

		self.custom_boq_html = lines_to_boq_html(lines, include_totals=True, company=self.company)

	def _boq_total(self) -> float:
		return sum(
			flt(row.amount)
			for row in self.get("custom_boq_lines") or []
			if row.get("line_type") == "Sub" and (row.get("display_mode") or "Normal") == "Normal"
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

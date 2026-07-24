# Copyright (c) 2026, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class ProjectEstimate(Document):
	def validate(self):
		self._validate_links()
		self.recalculate_totals()

	def on_submit(self):
		self.recalculate_totals()
		self.post_to_boq_item()

	def _validate_links(self):
		if not self.boq_bill or not self.project:
			return
		bill_project = frappe.db.get_value("BOQ Bill", self.boq_bill, "project")
		if bill_project and bill_project != self.project:
			frappe.throw(_("BOQ Bill {0} does not belong to Project {1}").format(self.boq_bill, self.project))

		if self.boq_item:
			item = frappe.db.get_value(
				"BOQ Item",
				self.boq_item,
				["parent_bill", "project"],
				as_dict=True,
			)
			if item:
				if item.parent_bill != self.boq_bill:
					frappe.throw(_("BOQ Item {0} does not belong to BOQ Bill {1}").format(self.boq_item, self.boq_bill))
				if item.project and item.project != self.project:
					frappe.throw(_("BOQ Item {0} does not belong to Project {1}").format(self.boq_item, self.project))

	def recalculate_totals(self):
		from construction_management.api.project_estimate import calculate_activity_row

		total_material = 0.0
		total_labour = 0.0
		primary_area = 0.0

		for row in self.activities or []:
			calculate_activity_row(row)
			total_material += flt(row.material_cost)
			total_labour += flt(row.labour_cost)
			if not primary_area and flt(row.est_area):
				primary_area = flt(row.est_area)

		self.total_material_cost = total_material
		self.total_labour_cost = total_labour
		self.total_estimated_cost = total_material + total_labour

		if not primary_area and self.boq_item:
			primary_area = flt(frappe.db.get_value("BOQ Item", self.boq_item, "total_qty"))

		self.cost_per_m2 = (
			flt(self.total_estimated_cost) / primary_area if primary_area else 0.0
		)

	def post_to_boq_item(self):
		"""Post material + labour estimates onto the linked BOQ Item."""
		from construction_management.api.cost_validation import update_estimated_costs

		if not self.boq_item:
			frappe.throw(_("BOQ Item is required to post estimate"))

		boq = frappe.get_doc("BOQ Item", self.boq_item)
		qty = flt(boq.total_qty)
		if qty <= 0:
			frappe.throw(_("BOQ Item {0} has zero quantity; cannot post per-unit estimate").format(self.boq_item))

		material_per_unit = flt(self.total_material_cost) / qty
		labour_per_unit = flt(self.total_labour_cost) / qty

		old_values = {
			"estimated_material_cost_per_unit": flt(boq.estimated_material_cost_per_unit),
			"estimated_labour_cost_per_unit": flt(boq.estimated_labour_cost_per_unit),
			"estimated_subcontract_cost_per_unit": flt(boq.estimated_subcontract_cost_per_unit),
			"estimated_asset_cost_per_unit": flt(boq.estimated_asset_cost_per_unit),
			"estimated_other_cost_per_unit": flt(boq.estimated_other_cost_per_unit),
			"estimated_material_cost": flt(boq.estimated_material_cost),
			"estimated_labour_cost": flt(boq.estimated_labour_cost),
			"estimated_subcontract_cost": flt(boq.estimated_subcontract_cost),
			"estimated_asset_cost": flt(boq.estimated_asset_cost),
			"estimated_other_cost": flt(boq.estimated_other_cost),
			"total_estimated_cost": flt(boq.total_estimated_cost),
		}

		# Only overwrite material + labour per-unit; leave other components as-is.
		# BOQ Item.validate → calculate_estimated_costs recomputes totals on save.
		new_values = dict(old_values)
		new_values["estimated_material_cost_per_unit"] = material_per_unit
		new_values["estimated_labour_cost_per_unit"] = labour_per_unit
		new_values["estimated_material_cost"] = material_per_unit * qty
		new_values["estimated_labour_cost"] = labour_per_unit * qty
		new_values["total_estimated_cost"] = (
			flt(new_values["estimated_material_cost"])
			+ flt(new_values["estimated_labour_cost"])
			+ flt(old_values["estimated_subcontract_cost"])
			+ flt(old_values["estimated_asset_cost"])
			+ flt(old_values["estimated_other_cost"])
		)

		result = update_estimated_costs(self.boq_item, new_values, old_values)
		if not result.get("success"):
			frappe.throw(_("Failed to post estimate to BOQ Item: {0}").format(result.get("message")))

# Copyright (c) 2024, Construction Management
# License: MIT

import frappe
from frappe import _
from frappe.utils import flt, cint
from typing import Dict, List, Optional, Tuple


class EstimatedGPCalculator:
	"""
	Estimated Gross Profit Calculator
	Calculates estimated gross profit independently from actual GP using BOQ rates and estimated costs
	"""
	
	def __init__(self):
		self.cost_components = ['material', 'labour', 'asset', 'subcontract', 'other']
	
	def calculate_estimated_gp(self, boq_item: str) -> Dict:
		"""
		Calculate estimated gross profit for a BOQ item
		
		Args:
			boq_item: BOQ Item name
			
		Returns:
			dict: Estimated GP calculations
		"""
		try:
			# Get BOQ Item details
			item_doc = frappe.get_doc("BOQ Item", boq_item)
			
			# Calculate estimated revenue (BOQ rate * total quantity)
			estimated_revenue = flt(item_doc.total_qty) * flt(item_doc.rate)
			
			# Get estimated costs
			estimated_costs = self.get_estimated_costs(boq_item)
			total_estimated_cost = estimated_costs.get('total', 0)
			
			# Calculate estimated GP
			estimated_gp = estimated_revenue - total_estimated_cost
			estimated_gp_percent = (estimated_gp / estimated_revenue * 100) if estimated_revenue > 0 else 0
			
			return {
				'estimated_revenue': estimated_revenue,
				'estimated_costs': estimated_costs,
				'estimated_gp': estimated_gp,
				'estimated_gp_percent': estimated_gp_percent,
				'boq_rate': item_doc.rate,
				'total_qty': item_doc.total_qty
			}
			
		except Exception as e:
			frappe.log_error(f"Error calculating estimated GP for {boq_item}: {str(e)}")
			return self._get_empty_gp_result()
	
	def get_estimated_costs(self, boq_item: str) -> Dict:
		"""
		Get estimated costs for a BOQ item
		
		Args:
			boq_item: BOQ Item name
			
		Returns:
			dict: Estimated costs breakdown
		"""
		try:
			# Check if estimated costs are stored in BOQ Item
			item_doc = frappe.get_doc("BOQ Item", boq_item)
			
			# Try to get from custom fields first
			estimated_costs = {}
			total_cost = 0
			
			for component in self.cost_components:
				field_name = f"estimated_{component}_cost"
				cost_value = flt(getattr(item_doc, field_name, 0))
				estimated_costs[component] = cost_value
				total_cost += cost_value
			
			# If no estimated costs in BOQ Item, calculate from rate breakdown
			if total_cost == 0:
				estimated_costs = self._calculate_costs_from_rate_breakdown(boq_item)
				total_cost = sum(estimated_costs.values())
			
			estimated_costs['total'] = total_cost
			return estimated_costs
			
		except Exception as e:
			frappe.log_error(f"Error getting estimated costs for {boq_item}: {str(e)}")
			return {component: 0 for component in self.cost_components + ['total']}
	
	def _calculate_costs_from_rate_breakdown(self, boq_item: str) -> Dict:
		"""
		Calculate estimated costs from rate breakdown if available
		
		Args:
			boq_item: BOQ Item name
			
		Returns:
			dict: Estimated costs breakdown
		"""
		try:
			# Get rate breakdown from BOQ Item or related documents
			item_doc = frappe.get_doc("BOQ Item", boq_item)
			
			# Default percentage breakdown if no specific breakdown available
			# These percentages can be configured per project or item type
			default_breakdown = {
				'material': 0.45,  # 45% material
				'labour': 0.30,    # 30% labour
				'asset': 0.10,     # 10% equipment/asset
				'subcontract': 0.10, # 10% subcontract
				'other': 0.05      # 5% other costs
			}
			
			# Get project-specific breakdown if available
			breakdown = self._get_project_cost_breakdown(item_doc.get('project')) or default_breakdown
			
			# Calculate costs based on BOQ rate
			total_rate = flt(item_doc.rate)
			estimated_costs = {}
			
			for component in self.cost_components:
				percentage = breakdown.get(component, 0)
				estimated_costs[component] = total_rate * percentage
			
			return estimated_costs
			
		except Exception as e:
			frappe.log_error(f"Error calculating costs from rate breakdown for {boq_item}: {str(e)}")
			return {component: 0 for component in self.cost_components}
	
	def _get_project_cost_breakdown(self, project: str) -> Optional[Dict]:
		"""
		Get project-specific cost breakdown percentages
		
		Args:
			project: Project name
			
		Returns:
			dict or None: Cost breakdown percentages
		"""
		if not project:
			return None
		
		try:
			# Check if project has custom cost breakdown settings
			project_doc = frappe.get_doc("Project", project)
			
			# Look for cost breakdown in project settings
			breakdown = {}
			for component in self.cost_components:
				field_name = f"default_{component}_percentage"
				percentage = flt(getattr(project_doc, field_name, 0)) / 100
				if percentage > 0:
					breakdown[component] = percentage
			
			return breakdown if breakdown else None
			
		except Exception:
			return None
	
	def update_estimated_costs(self, boq_item: str, costs: Dict) -> bool:
		"""
		Update estimated costs for a BOQ item
		
		Args:
			boq_item: BOQ Item name
			costs: Dictionary of cost components
			
		Returns:
			bool: Success status
		"""
		try:
			item_doc = frappe.get_doc("BOQ Item", boq_item)
			
			# Update estimated cost fields
			for component in self.cost_components:
				if component in costs:
					field_name = f"estimated_{component}_cost"
					setattr(item_doc, field_name, flt(costs[component]))
			
			# Calculate and store total estimated cost
			total_estimated_cost = sum(flt(costs.get(comp, 0)) for comp in self.cost_components)
			item_doc.estimated_total_cost = total_estimated_cost
			
			# Calculate and store estimated GP
			estimated_revenue = flt(item_doc.total_qty) * flt(item_doc.rate)
			estimated_gp = estimated_revenue - total_estimated_cost
			estimated_gp_percent = (estimated_gp / estimated_revenue * 100) if estimated_revenue > 0 else 0
			
			item_doc.estimated_gp = estimated_gp
			item_doc.estimated_gp_percent = estimated_gp_percent
			
			item_doc.save()
			return True
			
		except Exception as e:
			frappe.log_error(f"Error updating estimated costs for {boq_item}: {str(e)}")
			return False
	
	def calculate_actual_gp(self, boq_item: str) -> Dict:
		"""
		Calculate actual gross profit for comparison
		
		Args:
			boq_item: BOQ Item name
			
		Returns:
			dict: Actual GP calculations
		"""
		try:
			# Get actual revenue from invoices
			actual_revenue = self._get_actual_revenue(boq_item)
			
			# Get actual costs from transactions
			actual_costs = self._get_actual_costs(boq_item)
			total_actual_cost = actual_costs.get('total', 0)
			
			# Calculate actual GP
			actual_gp = actual_revenue - total_actual_cost
			actual_gp_percent = (actual_gp / actual_revenue * 100) if actual_revenue > 0 else 0
			
			return {
				'actual_revenue': actual_revenue,
				'actual_costs': actual_costs,
				'actual_gp': actual_gp,
				'actual_gp_percent': actual_gp_percent
			}
			
		except Exception as e:
			frappe.log_error(f"Error calculating actual GP for {boq_item}: {str(e)}")
			return self._get_empty_gp_result()
	
	def _get_actual_revenue(self, boq_item: str) -> float:
		"""
		Get actual revenue from sales invoices
		
		Args:
			boq_item: BOQ Item name
			
		Returns:
			float: Actual revenue
		"""
		try:
			revenue = frappe.db.sql("""
				SELECT COALESCE(SUM(sii.amount), 0) as total_revenue
				FROM `tabSales Invoice Item` sii
				JOIN `tabSales Invoice` si ON si.name = sii.parent
				WHERE sii.boq_item = %s
				AND si.docstatus = 1
			""", boq_item, as_dict=True)
			
			return flt(revenue[0].total_revenue) if revenue else 0
			
		except Exception:
			return 0
	
	def _get_actual_costs(self, boq_item: str) -> Dict:
		"""
		Get actual costs from various transactions
		
		Args:
			boq_item: BOQ Item name
			
		Returns:
			dict: Actual costs breakdown
		"""
		try:
			# Get costs from different sources
			material_cost = self._get_material_costs(boq_item)
			labour_cost = self._get_labour_costs(boq_item)
			asset_cost = self._get_asset_costs(boq_item)
			subcontract_cost = self._get_subcontract_costs(boq_item)
			other_cost = self._get_other_costs(boq_item)
			
			actual_costs = {
				'material': material_cost,
				'labour': labour_cost,
				'asset': asset_cost,
				'subcontract': subcontract_cost,
				'other': other_cost,
				'total': material_cost + labour_cost + asset_cost + subcontract_cost + other_cost
			}
			
			return actual_costs
			
		except Exception as e:
			frappe.log_error(f"Error getting actual costs for {boq_item}: {str(e)}")
			return {component: 0 for component in self.cost_components + ['total']}
	
	def _get_material_costs(self, boq_item: str) -> float:
		"""Get actual material costs from stock entries and purchase receipts"""
		try:
			# Get from stock entries
			stock_cost = frappe.db.sql("""
				SELECT COALESCE(SUM(sed.amount), 0) as total_cost
				FROM `tabStock Entry Detail` sed
				JOIN `tabStock Entry` se ON se.name = sed.parent
				WHERE sed.boq_item = %s
				AND se.docstatus = 1
				AND se.stock_entry_type IN ('Material Issue', 'Material Transfer')
			""", boq_item, as_dict=True)
			
			return flt(stock_cost[0].total_cost) if stock_cost else 0
			
		except Exception:
			return 0
	
	def _get_labour_costs(self, boq_item: str) -> float:
		"""Get actual labour costs from DPR and payroll"""
		try:
			# Get from DPR labour entries
			labour_cost = frappe.db.sql("""
				SELECT COALESCE(SUM(dl.total_cost), 0) as total_cost
				FROM `tabDPR Labour` dl
				JOIN `tabDaily Progress Record` dpr ON dpr.name = dl.parent
				WHERE dl.boq_item = %s
				AND dpr.docstatus = 1
			""", boq_item, as_dict=True)
			
			return flt(labour_cost[0].total_cost) if labour_cost else 0
			
		except Exception:
			return 0
	
	def _get_asset_costs(self, boq_item: str) -> float:
		"""Get actual asset/equipment costs"""
		try:
			# Get from asset billing or equipment usage
			asset_cost = frappe.db.sql("""
				SELECT COALESCE(SUM(pab.billing_amount), 0) as total_cost
				FROM `tabProject Asset Billing` pab
				WHERE pab.boq_item = %s
				AND pab.docstatus = 1
			""", boq_item, as_dict=True)
			
			return flt(asset_cost[0].total_cost) if asset_cost else 0
			
		except Exception:
			return 0
	
	def _get_subcontract_costs(self, boq_item: str) -> float:
		"""Get actual subcontract costs from Subcontractor purchase invoices"""
		try:
			from construction_management.api.purchase_receipt_utils import get_purchase_cost_category_sql

			party_expr = get_purchase_cost_category_sql("pi", "pii")
			subcontract_cost = frappe.db.sql(
				f"""
				SELECT COALESCE(SUM(pii.amount), 0) as total_cost
				FROM `tabPurchase Invoice Item` pii
				JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
				WHERE pii.boq_item = %s
				AND pi.docstatus = 1
				AND {party_expr} = 'Subcontractor'
				""",
				boq_item,
				as_dict=True,
			)

			return flt(subcontract_cost[0].total_cost) if subcontract_cost else 0

		except Exception:
			return 0
	
	def _get_other_costs(self, boq_item: str) -> float:
		"""Get other miscellaneous costs"""
		try:
			# Get from expense claims or other cost entries
			other_cost = frappe.db.sql("""
				SELECT COALESCE(SUM(ecd.amount), 0) as total_cost
				FROM `tabExpense Claim Detail` ecd
				JOIN `tabExpense Claim` ec ON ec.name = ecd.parent
				WHERE ecd.boq_item = %s
				AND ec.docstatus = 1
			""", boq_item, as_dict=True)
			
			return flt(other_cost[0].total_cost) if other_cost else 0
			
		except Exception:
			return 0
	
	def get_gp_comparison(self, boq_item: str) -> Dict:
		"""
		Get comprehensive GP comparison between estimated and actual
		
		Args:
			boq_item: BOQ Item name
			
		Returns:
			dict: GP comparison data
		"""
		try:
			estimated_gp = self.calculate_estimated_gp(boq_item)
			actual_gp = self.calculate_actual_gp(boq_item)
			
			# Calculate variances
			revenue_variance = actual_gp['actual_revenue'] - estimated_gp['estimated_revenue']
			cost_variance = actual_gp['actual_costs']['total'] - estimated_gp['estimated_costs']['total']
			gp_variance = actual_gp['actual_gp'] - estimated_gp['estimated_gp']
			gp_percent_variance = actual_gp['actual_gp_percent'] - estimated_gp['estimated_gp_percent']
			
			return {
				'estimated': estimated_gp,
				'actual': actual_gp,
				'variances': {
					'revenue_variance': revenue_variance,
					'cost_variance': cost_variance,
					'gp_variance': gp_variance,
					'gp_percent_variance': gp_percent_variance
				},
				'performance': {
					'revenue_performance': 'over' if revenue_variance > 0 else 'under' if revenue_variance < 0 else 'on_target',
					'cost_performance': 'over' if cost_variance > 0 else 'under' if cost_variance < 0 else 'on_target',
					'gp_performance': 'better' if gp_variance > 0 else 'worse' if gp_variance < 0 else 'on_target'
				}
			}
			
		except Exception as e:
			frappe.log_error(f"Error getting GP comparison for {boq_item}: {str(e)}")
			return {}
	
	def _get_empty_gp_result(self) -> Dict:
		"""Return empty GP result structure"""
		return {
			'estimated_revenue': 0,
			'estimated_costs': {component: 0 for component in self.cost_components + ['total']},
			'estimated_gp': 0,
			'estimated_gp_percent': 0,
			'actual_revenue': 0,
			'actual_costs': {component: 0 for component in self.cost_components + ['total']},
			'actual_gp': 0,
			'actual_gp_percent': 0
		}


# Whitelisted API functions
@frappe.whitelist()
def calculate_estimated_gp(boq_item: str) -> Dict:
	"""
	API function to calculate estimated GP for a BOQ item
	
	Args:
		boq_item: BOQ Item name
		
	Returns:
		dict: Estimated GP calculations
	"""
	calculator = EstimatedGPCalculator()
	return calculator.calculate_estimated_gp(boq_item)


@frappe.whitelist()
def update_estimated_costs(boq_item: str, costs: str) -> Dict:
	"""
	API function to update estimated costs for a BOQ item
	
	Args:
		boq_item: BOQ Item name
		costs: JSON string of cost components
		
	Returns:
		dict: Success status and updated GP
	"""
	import json
	
	try:
		costs_dict = json.loads(costs) if isinstance(costs, str) else costs
		calculator = EstimatedGPCalculator()
		
		success = calculator.update_estimated_costs(boq_item, costs_dict)
		
		if success:
			updated_gp = calculator.calculate_estimated_gp(boq_item)
			return {
				'status': 'success',
				'message': 'Estimated costs updated successfully',
				'estimated_gp': updated_gp
			}
		else:
			return {
				'status': 'error',
				'message': 'Failed to update estimated costs'
			}
			
	except Exception as e:
		frappe.log_error(f"Error updating estimated costs: {str(e)}")
		return {
			'status': 'error',
			'message': f'Error updating estimated costs: {str(e)}'
		}


@frappe.whitelist()
def get_gp_comparison(boq_item: str) -> Dict:
	"""
	API function to get GP comparison between estimated and actual
	
	Args:
		boq_item: BOQ Item name
		
	Returns:
		dict: GP comparison data
	"""
	calculator = EstimatedGPCalculator()
	return calculator.get_gp_comparison(boq_item)


@frappe.whitelist()
def get_project_gp_summary(project: str) -> Dict:
	"""
	Get GP summary for all BOQ items in a project
	
	Args:
		project: Project name
		
	Returns:
		dict: Project GP summary
	"""
	try:
		calculator = EstimatedGPCalculator()
		
		# Get all BOQ items for the project
		boq_items = frappe.db.sql("""
			SELECT bi.name, bi.description, bi.total_qty, bi.rate
			FROM `tabBOQ Item` bi
			JOIN `tabBOQ Bill` bb ON bb.name = bi.parent_bill
			WHERE bb.project = %s
			ORDER BY bb.bill_no, bi.idx
		""", project, as_dict=True)
		
		project_summary = {
			'total_estimated_revenue': 0,
			'total_estimated_cost': 0,
			'total_estimated_gp': 0,
			'total_actual_revenue': 0,
			'total_actual_cost': 0,
			'total_actual_gp': 0,
			'item_count': len(boq_items),
			'items': []
		}
		
		for item in boq_items:
			gp_data = calculator.get_gp_comparison(item.name)
			
			if gp_data:
				estimated = gp_data.get('estimated', {})
				actual = gp_data.get('actual', {})
				
				project_summary['total_estimated_revenue'] += estimated.get('estimated_revenue', 0)
				project_summary['total_estimated_cost'] += estimated.get('estimated_costs', {}).get('total', 0)
				project_summary['total_estimated_gp'] += estimated.get('estimated_gp', 0)
				
				project_summary['total_actual_revenue'] += actual.get('actual_revenue', 0)
				project_summary['total_actual_cost'] += actual.get('actual_costs', {}).get('total', 0)
				project_summary['total_actual_gp'] += actual.get('actual_gp', 0)
				
				project_summary['items'].append({
					'boq_item': item.name,
					'description': item.description,
					'gp_data': gp_data
				})
		
		# Calculate percentages
		if project_summary['total_estimated_revenue'] > 0:
			project_summary['estimated_gp_percent'] = (
				project_summary['total_estimated_gp'] / project_summary['total_estimated_revenue'] * 100
			)
		
		if project_summary['total_actual_revenue'] > 0:
			project_summary['actual_gp_percent'] = (
				project_summary['total_actual_gp'] / project_summary['total_actual_revenue'] * 100
			)
		
		return project_summary
		
	except Exception as e:
		frappe.log_error(f"Error getting project GP summary for {project}: {str(e)}")
		return {}
__version__ = "0.0.1"
import construction_management.overrides.financial_statements_fix
import construction_management.overrides.project_user_permissions
import construction_management.overrides.frappe17_compat

# Patch Project list view to exclude Project Engineer from user permission filtering
construction_management.overrides.project_user_permissions.patch_project_user_permissions()

# Monkey-patch insert_item_price to skip deduction/advance items
# This prevents both the Item Price creation AND the "Item Price added" popup
from construction_management.tasks import SPECIAL_ITEM_PRICE_CLEANUP_CODES
import erpnext.stock.get_item_details as _item_details

_original_insert_item_price = _item_details.insert_item_price

def _patched_insert_item_price(ctx):
	if getattr(ctx, "item_code", None) in SPECIAL_ITEM_PRICE_CLEANUP_CODES:
		return
	return _original_insert_item_price(ctx)

_item_details.insert_item_price = _patched_insert_item_price

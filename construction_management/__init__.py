__version__ = "0.0.1"
import construction_management.overrides.financial_statements_fix
import construction_management.overrides.project_user_permissions
import construction_management.overrides.frappe17_compat

# Patch Project list view to exclude Project Engineer from user permission filtering
construction_management.overrides.project_user_permissions.patch_project_user_permissions()

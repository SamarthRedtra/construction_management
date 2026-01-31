import frappe
from construction_management.construction_management.page.bulk_dpr_entry.bulk_dpr_entry import get_overhead_accounts

# Fetch overhead accounts
accounts = get_overhead_accounts()
print(f"Fetched {len(accounts)} accounts.")
for acc in accounts[:5]:
    print(f"- {acc.name} ({acc.account_name})")

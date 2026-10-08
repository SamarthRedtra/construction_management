"""Purchase Order dashboard additions for controlled procurement."""

from frappe import _


def get_dashboard_data(data: dict) -> dict:
	"""Add PO-linked post-dated cheques to the standard payment connections."""
	dashboard = dict(data)
	dashboard["non_standard_fieldnames"] = dict(dashboard.get("non_standard_fieldnames") or {})
	dashboard["non_standard_fieldnames"]["Post Dated Cheques"] = "custom_purchase_order"
	dashboard["transactions"] = [
		{**group, "items": list(group.get("items") or [])}
		for group in dashboard.get("transactions") or []
	]

	for group in dashboard["transactions"]:
		if "Payment Entry" not in group["items"]:
			continue
		if "Post Dated Cheques" not in group["items"]:
			group["items"].append("Post Dated Cheques")
		break
	else:
		dashboard["transactions"].append({"label": _("Payment"), "items": ["Post Dated Cheques"]})

	return dashboard

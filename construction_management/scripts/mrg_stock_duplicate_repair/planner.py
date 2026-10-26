"""Conservative, deterministic eligibility rules for retiring duplicate stock."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict

from .data import COMPANY, CUTOFF, SOURCES, Evidence, normalize


def build_plan() -> dict:
	"""Hold uncertain mappings and later legacy movements for separate review."""
	evidence = Evidence()
	eligible, exceptions = [], []
	for source in evidence.source_rows:
		if source["source_qty"] <= 0 or (source["new_code"], source["warehouse"]) not in evidence.snapshot_pairs:
			continue
		rows, reason = classify(source, evidence)
		if reason:
			exceptions.append(dict(source, reason=reason))
		else:
			eligible.extend(rows)
	eligible, overlaps = remove_overlapping_legacy_rows(eligible)
	exceptions.extend(overlaps)
	for pair in sorted(evidence.snapshot_pairs):
		if pair not in {(row["new_code"], row["warehouse"]) for row in evidence.source_rows}:
			exceptions.append({"new_code": pair[0], "warehouse": pair[1], "reason": "no_source_snapshot_row"})
	payload = {"version": 1, "company": COMPANY, "cutoff": CUTOFF, "sources": SOURCES,
		"eligible": sorted(eligible, key=lambda row: (row["warehouse"], row["old_code"])),
		"exceptions": exceptions, "pending_revaluations": evidence.pending}
	payload["plan_hash"] = plan_hash(payload)
	payload["summary"] = {"eligible_rows": len(eligible), "new_items": len({row["new_code"] for row in eligible}),
		"legacy_items": len({row["old_code"] for row in eligible}),
		"warehouses": len({row["warehouse"] for row in eligible}),
		"expected_difference_account_debit": round(sum(row["old_value"] for row in eligible), 6),
		"exceptions_by_reason": dict(Counter(row["reason"] for row in exceptions)),
		"pending_revaluations": len(evidence.pending)}
	return payload


def classify(source: dict, evidence: Evidence) -> tuple[list[dict], str]:
	new_code, warehouse = source["new_code"], source["warehouse"]
	new = evidence.items[new_code]
	# Mutation requires an explicit workbook mapping; name similarity is insufficient.
	codes = sorted(evidence.mapping.get(new_code, []))
	if not codes:
		return [], "missing_explicit_mapping"
	positive = [code for code in codes if (code, warehouse) in evidence.balances
		and evidence.balances[code, warehouse].qty_after_transaction > 0]
	if not positive:
		return [], "no_positive_legacy_balance"
	if any(code not in evidence.items for code in positive):
		return [], "missing_legacy_master"
	old_items = [evidence.items[code] for code in positive]
	if any(not row.is_stock_item or row.has_serial_no or row.has_batch_no
		or row.disabled or row.is_customer_provided_item for row in [new, *old_items]):
		return [], "unsupported_item_properties"
	if len({normalize(item.stock_uom) for item in old_items}) != 1:
		return [], "multiple_legacy_stock_units"
	if any(package_conflict(old.item_name, new.item_name) for old in old_items):
		return [], "conflicting_package_sizes"
	if len(source["source_uoms"]) != 1:
		return [], "multiple_source_units"
	unit = source["source_uoms"][0]
	factors = [source_factor(unit, old, new, evidence.uoms[old.name]) for old in old_items]
	if any(factor is None for factor in factors) or len(set(factors)) != 1:
		return [], "source_unit_conversion_unverified"
	quantity = sum(float(evidence.balances[code, warehouse].qty_after_transaction) for code in positive)
	if not quantities_match(quantity, source["source_qty"] * factors[0]):
		return [], "legacy_quantity_differs_from_source"
	if any((code, warehouse) in evidence.future for code in positive):
		return [], "legacy_transactions_after_cutoff"
	if any(evidence.reserved.get((code, warehouse), 0) > 0 for code in positive):
		return [], "legacy_stock_reserved"
	new_balance = evidence.balances.get((new_code, warehouse))
	if not new_balance or new_balance.voucher_type != "Stock Reconciliation":
		return [], "new_stock_not_from_reconciliation_at_cutoff"
	if str(new_balance.posting_datetime)[:10] != CUTOFF[:10]:
		return [], "new_snapshot_not_at_cutoff"
	rows = []
	for old in old_items:
		balance = evidence.balances[old.name, warehouse]
		if float(balance.stock_value) <= 0 or float(balance.valuation_rate) <= 0:
			return [], "nonpositive_legacy_value"
		rows.append(dict(source, old_code=old.name, old_uom=old.stock_uom, new_uom=new.stock_uom,
			old_qty=float(balance.qty_after_transaction), old_rate=float(balance.valuation_rate),
			old_value=float(balance.stock_value), legacy_sle=balance.name,
			new_qty=float(new_balance.qty_after_transaction), new_value=float(new_balance.stock_value),
			new_sle=new_balance.name, new_snapshot_voucher=new_balance.voucher_no,
			mapping_rows=evidence.mapping_rows[new_code, old.name], source_factor=factors[0]))
	return rows, ""


def source_factor(unit, old, new, uoms):
	"""Read stored conversions; generic package labels require unchanged package dimensions."""
	if normalize(unit) == normalize(old.stock_uom):
		return 1.0
	if normalize(unit) in uoms:
		return uoms[normalize(unit)]
	package_units = {"nos", "roll", "rolls", "bag", "bags", "pail", "drum", "set", "sets"}
	if normalize(unit) == normalize(new.stock_uom) and normalize(old.stock_uom) in package_units:
		if normalize(unit) in package_units and not package_conflict(old.item_name, new.item_name):
			return 1.0
	return None


def package_conflict(old_name, new_name):
	pattern = r"(\d+(?:\.\d+)?)\s*(kg|ltr|litre|ml)\b"
	def sizes(name):
		return {(float(number), "ltr" if unit == "litre" else unit)
			for number, unit in re.findall(pattern, name.lower())}
	old_sizes, new_sizes = sizes(old_name), sizes(new_name)
	return bool(old_sizes and new_sizes and old_sizes != new_sizes)


def quantities_match(actual, expected):
	return abs(actual - expected) <= max(0.00001, abs(expected) * 0.000000001)


def remove_overlapping_legacy_rows(rows):
	owners = defaultdict(set)
	for row in rows:
		owners[row["old_code"], row["warehouse"]].add(row["new_code"])
	conflicts = {key for key, codes in owners.items() if len(codes) > 1}
	return ([row for row in rows if (row["old_code"], row["warehouse"]) not in conflicts],
		[dict(row, reason="legacy_balance_mapped_to_multiple_new_items") for row in rows
			if (row["old_code"], row["warehouse"]) in conflicts])


def plan_hash(plan):
	identity = {key: plan[key] for key in ["version", "company", "cutoff", "sources", "eligible", "exceptions"]}
	return hashlib.sha256(json.dumps(identity, sort_keys=True, default=str).encode()).hexdigest()

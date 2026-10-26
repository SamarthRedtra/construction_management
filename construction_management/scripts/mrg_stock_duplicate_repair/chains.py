"""Find and rebuild stale stock balance chains using native valuation jobs."""

from __future__ import annotations

import hashlib

import frappe

from .data import COMPANY


CHAIN_PREFIX = "MRG-CHAIN-20260930-"


def rebuild_remaining(dry_run):
	"""Recompute only item/warehouse chains whose movements disagree with closing values."""
	gaps = find_gaps()
	if len(gaps) > 50:
		raise ValueError("More than 50 additional stock chains need inspection before rebuilding")
	names = []
	for row in gaps:
		name = CHAIN_PREFIX + hashlib.sha256((row.item_code + "\0" + row.warehouse).encode()).hexdigest()[:12]
		names.append(name)
		if dry_run:
			continue
		if frappe.db.exists("Repost Item Valuation", name):
			document = frappe.get_doc("Repost Item Valuation", name)
			if document.company != COMPANY or document.item_code != row.item_code or document.warehouse != row.warehouse:
				raise ValueError(f"Additional chain job scope mismatch: {name}")
			if document.status != "Queued":
				raise ValueError(f"Inspect remaining chain gap and existing job {name}: {document.status}")
		else:
			document = frappe.new_doc("Repost Item Valuation")
			document.company = COMPANY
			document.based_on = "Item and Warehouse"
			document.item_code = row.item_code
			document.warehouse = row.warehouse
			document.posting_date = "1900-01-01"
			document.posting_time = "00:00:00"
			document.allow_negative_stock = frappe.db.get_single_value("Stock Settings", "allow_negative_stock")
			document.insert(set_name=name)
			document.submit()
		print(f"Rebuilding stale chain {name}: {row.item_code} / {row.warehouse}", flush=True)
		document.repost_now()
		document.reload()
		frappe.db.commit()
		if document.status not in ("Completed", "Skipped"):
			raise ValueError(f"Additional chain revaluation failed: {name} / {document.status}")
	# Include completed jobs on reruns, so their linked GL tasks remain resumable.
	if not dry_run:
		existing = frappe.get_all("Repost Item Valuation", filters={"company": COMPANY,
			"name": ["like", CHAIN_PREFIX + "%"]}, fields=["name", "status"], order_by="name")
		if any(row.status not in ("Completed", "Skipped") for row in existing):
			raise ValueError("An additional chain revaluation is incomplete; inspect its status")
		names = [row.name for row in existing]
	return gaps, names


def find_gaps():
	by_pair = {}
	for date in ["2026-09-30", "2026-10-31"]:
		rows = frappe.db.sql("""
			WITH deltas AS (
				SELECT item_code,warehouse,SUM(stock_value_difference) moved
				FROM `tabStock Ledger Entry`
				WHERE company=%s AND is_cancelled=0 AND posting_date<=%s
				GROUP BY item_code,warehouse
			), ranked AS (
				SELECT item_code,warehouse,stock_value,ROW_NUMBER() OVER (
					PARTITION BY item_code,warehouse ORDER BY posting_datetime DESC,creation DESC,name DESC) rn
				FROM `tabStock Ledger Entry`
				WHERE company=%s AND is_cancelled=0 AND posting_date<=%s
			)
			SELECT d.item_code,d.warehouse,d.moved,r.stock_value,d.moved-r.stock_value AS gap
			FROM deltas d JOIN ranked r ON r.item_code=d.item_code AND r.warehouse=d.warehouse AND r.rn=1
			WHERE ABS(d.moved-r.stock_value)>0.011
		""", (COMPANY, date, COMPANY, date), as_dict=True)
		for row in rows:
			pair = row.item_code, row.warehouse
			if pair not in by_pair or abs(row.gap) > abs(by_pair[pair].gap):
				by_pair[pair] = row
	return [by_pair[key] for key in sorted(by_pair)]

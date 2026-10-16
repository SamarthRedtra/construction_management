# Copyright (c) 2026, Construction Management
# License: MIT

"""Disable zero-stock duplicate controlled-catalog Items from the repeated list.

Keeps any Item with live Bin stock enabled. When a description group has no
stock, keeps one survivor (prefer non `-2` code, else first listed) enabled.
"""

from __future__ import annotations

from collections import defaultdict

import frappe
from frappe.utils import flt


ITEM_CODES = (
	'CP-BONDCRETE_RAK_FIX_012_(_50KG_/_BAG_)',
	'CP-BONDCRETE_RAK_FIX_012_(_50KG_/_BAG_)-2',
	"CP-COMMERCIAL_PLYWOOD_4MM_(_8'_X_4'_X__4_MM_)",
	"CP-COMMERCIAL_PLYWOOD_4MM_(_8'_X_4'_X__4_MM_)-2",
	"CP-COMMERCIAL_PLYWOOD_6MM_(_8'_X_4'_X__6_MM_)",
	"CP-COMMERCIAL_PLYWOOD_6MM_(_8'_X_4'_X__6_MM_)-2",
	'CP-CORROPLAST_AB__(_40KG_/_BAG_)',
	'CP-CORROPLAST_AB__(_40KG_/_BAG_)-2',
	'CP-CORROPLAST_KEY_COAT_N_(_40KG_/_BAG_)',
	'CP-CORROPLAST_KEY_COAT_N_(_40KG_/_BAG_)-2',
	'CP-DEFORMED_STEEL__BARS_16_MM',
	'CP-DEFORMED_STEEL__BARS_16_MM-2',
	'CP-DEFORMED_STEEL_BARS_20_MM',
	'CP-DEFORMED_STEEL_BARS_20_MM-2',
	'CP-DEFORMED_STEEL_BARS_32_MM',
	'CP-DEFORMED_STEEL_BARS_32_MM-2',
	'CP-DEFORMED_STEEL_BARS_8___MM',
	'CP-DEFORMED_STEEL_BARS_8___MM-2',
	'CP-DULAS_P_180_4MM_SBS_MEMBRANE___(1M*10M_ROLL)',
	'CP-DULAS_P_180_5MM__SBS_MEMBRANE_(1M*10M_ROLL)',
	'CP-G.I_ANGLE_BEAD_(_50MM_X_50MM_X_13MM_)',
	'CP-G.I_ANGLE_BEAD_(_50MM_X_50MM_X_13MM_)-2',
	'CP-G.I_BLOCK_MESH___(200MM_X_50M/_ROLL)',
	'CP-G.I_BLOCK_MESH___(200MM_X_50M/_ROLL)-2',
	'CP-G.I_BLOCK_MESH__(100MM_X_50M/_ROLL)',
	'CP-G.I_BLOCK_MESH__(100MM_X_50M/_ROLL)-2',
	'CP-G.I_BLOCK_MESH__(250MM_X_50M/_ROLL)',
	'CP-G.I_BLOCK_MESH__(250MM_X_50M/_ROLL)-2',
	'CP-JK_PLAST_COAT_RS11_(_50KG_/_BAG_)',
	'CP-JK_PLAST_COAT_RS11_(_50KG_/_BAG_)-2',
	'CP-JK_PLAST_PP22_(_50KG_/_BAG_)',
	'CP-JK_PLAST_PP22_(_50KG_/_BAG_)-2',
	"CP-MARINE_PLYWOOD__(_8'_X_4'_X_18MM_)",
	"CP-MARINE_PLYWOOD__(_8'_X_4'_X_18MM_)-2",
	"CP-MARINE_PLYWOOD_(_8'_X_4'_X_12MM_)",
	"CP-MARINE_PLYWOOD_(_8'_X_4'_X_12MM_)-2",
	'CP-MATERX_LAVACHEM_FLOWABLE_(_25KG/BAG)',
	'CP-MATERX_LAVACHEM_FLOWABLE_(_25KG/BAG)-2',
	'CP-MIX_GROUT_NS_(_25KG/BAG)',
	'CP-MIX_GROUT_NS_(_25KG/BAG)-2',
	'CP-MIXBUILD_MC_GREY(_25KG/BAG)',
	'CP-MIXBUILD_MC_GREY(_25KG/BAG)-2',
	'CP-MS_60_6MM_PROTECTION_BOARD_(1M*2M_)',
	'CP-MS60_PROTECTION_BOARD_6MM__(1M*2M_)',
	'CP-MULTI_DIRECTIONAL_REINJECTIBLE_HOSE_AN_INTEGRATED_INJECTION_SYSTEM_100LM/BOX',
	'CP-MULTI_DIRECTIONAL_REINJECTIBLE_HOSE_AN_INTEGRATED_INJECTION_SYSTEM_100LM/BOX-2',
	'CP-NEOBOND_SBR_250_(_20LTR_/_PAIL_)',
	'CP-NEOBOND_SBR_250_(_20LTR_/_PAIL_)-2',
	'CP-NEOGROUT_NS_(20KG/BAG)',
	'CP-NEOGROUT_NS_(20KG/BAG)-2',
	'CP-NEOSULPHIDE_SEALANT_GG_PART_A+PART_B__(_2.5LTR/PACK_)',
	'CP-NEOSULPHIDE_SEALANT_GG_PART_A+PART_B__(_2.5LTR/PACK_)-2',
	'CP-NEOSULPHIDE_SEALANT_PART_A+PART_B__(_2.5LTR/PACK_)',
	'CP-OPC_CEMENT_(_50KG_/_BAG_)',
	'CP-OPC_CEMENT_(_50KG_/_BAG_)-2',
	'CP-PVC_WATERSTOPPER__DOUBLE_FACE_(15M/ROLL)',
	'CP-PVC_WATERSTOPPER__DOUBLE_FACE_(15M/ROLL)-2',
	'CP-PVC_WATWER_STOP__IC250_(15M/ROLL)',
	'CP-PVC_WATWER_STOP__IC250_(15M/ROLL)-2',
	'CP-RENDEROC_FC_(20KG/BAG_)',
	'CP-RENDEROC_FC_(20KG/BAG_)-2',
	'CP-RENDEROC_HS__(20KG/BAG_)',
	'CP-RENDEROC_HS__(20KG/BAG_)-2',
	'CP-S.S_ANGLE_BEAD__(_50MM_X_50MM_X_13MM_)',
	'CP-S.S_ANGLE_BEAD__(_50MM_X_50MM_X_13MM_)-2',
	'CP-SIKA_WATERSTOP_G__1C25_(_15M/ROLL)',
	'CP-SIKA_WATERSTOP_G__1C25_(_15M/ROLL)-2',
	'CP-SIKA_WATERSTOP_G__EC25_(_15M/ROLL)',
	'CP-SIKA_WATERSTOP_G__EC25_(_15M/ROLL)-2',
	'CP-SIKALATIC_311__AE_(_20_LTR_PAIL_)',
	'CP-SIKALATIC_311__AE_(_20_LTR_PAIL_)-2',
	'CP-SS_PLASTER_STOPPER__(13MM_X_13_MTR_)',
	'CP-SS_PLASTER_STOPPER__(13MM_X_13_MTR_)-2',
	'CP-SUPERCAST_INJECTOSEAL_(_100M/ROLL)',
	'CP-SUPERCAST_INJECTOSEAL_(_100M/ROLL)-2',
	'CP-WATAFOIL_250MM_(_12M/ROLL)',
	'CP-WATAFOIL_250MM_(_12M/ROLL)-2',
	'CP-WEBERAD_225_MB_(_20LTR_/_PAIL_)',
	'CP-WEBERAD_225_MB_(_20LTR_/_PAIL_)-2',
	'CP-WEBERCOL_PRO_GREY__(25KG/_BAG_)',
	'CP-WEBERCOL_PRO_GREY__(25KG/_BAG_)-2',
	'CP-WEBERJOINT_112_BONE_WHITE_(5_KG_/_BAG_)',
	'CP-WEBERJOINT_112_BONE_WHITE_(5_KG_/_BAG_)-2',
	'CP-WEBERJOINT_120_IVORY__(5_KG_/_BAG_)',
	'CP-WEBERJOINT_120_IVORY__(5_KG_/_BAG_)-2',
	'CP-WHITE_WOOD_(1"_X_4"_X_13\')',
	'CP-WHITE_WOOD_(1"_X_4"_X_13\')-2',
	'CP-WHITE_WOOD_(3"_X_3"_X_13\')',
	'CP-WHITE_WOOD_(3"_X_3"_X_13\')-2',
	'CP-WING_NUT_HD',
	'CP-WING_NUT_HD-2',
)

# Workbook descriptions; MS60 alt shares the MS_60 group key.
DESCRIPTION_BY_CODE = {
	'CP-BONDCRETE_RAK_FIX_012_(_50KG_/_BAG_)': 'BONDCRETE RAK FIX 012 ( 50KG / BAG )',
	'CP-BONDCRETE_RAK_FIX_012_(_50KG_/_BAG_)-2': 'BONDCRETE RAK FIX 012 ( 50KG / BAG )',
	"CP-COMMERCIAL_PLYWOOD_4MM_(_8'_X_4'_X__4_MM_)": "COMMERCIAL PLYWOOD 4MM ( 8' X 4' X  4 MM )",
	"CP-COMMERCIAL_PLYWOOD_4MM_(_8'_X_4'_X__4_MM_)-2": "COMMERCIAL PLYWOOD 4MM ( 8' X 4' X  4 MM )",
	"CP-COMMERCIAL_PLYWOOD_6MM_(_8'_X_4'_X__6_MM_)": "COMMERCIAL PLYWOOD 6MM ( 8' X 4' X  6 MM )",
	"CP-COMMERCIAL_PLYWOOD_6MM_(_8'_X_4'_X__6_MM_)-2": "COMMERCIAL PLYWOOD 6MM ( 8' X 4' X  6 MM )",
	'CP-CORROPLAST_AB__(_40KG_/_BAG_)': 'CORROPLAST AB  ( 40KG / BAG )',
	'CP-CORROPLAST_AB__(_40KG_/_BAG_)-2': 'CORROPLAST AB  ( 40KG / BAG )',
	'CP-CORROPLAST_KEY_COAT_N_(_40KG_/_BAG_)': 'CORROPLAST KEY COAT N ( 40KG / BAG )',
	'CP-CORROPLAST_KEY_COAT_N_(_40KG_/_BAG_)-2': 'CORROPLAST KEY COAT N ( 40KG / BAG )',
	'CP-DEFORMED_STEEL__BARS_16_MM': 'DEFORMED STEEL  BARS 16 MM',
	'CP-DEFORMED_STEEL__BARS_16_MM-2': 'DEFORMED STEEL  BARS 16 MM',
	'CP-DEFORMED_STEEL_BARS_20_MM': 'DEFORMED STEEL BARS 20 MM',
	'CP-DEFORMED_STEEL_BARS_20_MM-2': 'DEFORMED STEEL BARS 20 MM',
	'CP-DEFORMED_STEEL_BARS_32_MM': 'DEFORMED STEEL BARS 32 MM',
	'CP-DEFORMED_STEEL_BARS_32_MM-2': 'DEFORMED STEEL BARS 32 MM',
	'CP-DEFORMED_STEEL_BARS_8___MM': 'DEFORMED STEEL BARS 8   MM',
	'CP-DEFORMED_STEEL_BARS_8___MM-2': 'DEFORMED STEEL BARS 8   MM',
	'CP-DULAS_P_180_4MM_SBS_MEMBRANE___(1M*10M_ROLL)': 'Dulas P 180 4MM SBS MEMBRANE   (1M*10M ROLL)',
	'CP-DULAS_P_180_5MM__SBS_MEMBRANE_(1M*10M_ROLL)': 'Dulas P 180 5MM  SBS MEMBRANE (1M*10M ROLL)',
	'CP-G.I_ANGLE_BEAD_(_50MM_X_50MM_X_13MM_)': 'G.I ANGLE BEAD ( 50MM X 50MM X 13MM )',
	'CP-G.I_ANGLE_BEAD_(_50MM_X_50MM_X_13MM_)-2': 'G.I ANGLE BEAD ( 50MM X 50MM X 13MM )',
	'CP-G.I_BLOCK_MESH___(200MM_X_50M/_ROLL)': 'G.I BLOCK MESH   (200MM X 50M/ ROLL)',
	'CP-G.I_BLOCK_MESH___(200MM_X_50M/_ROLL)-2': 'G.I BLOCK MESH   (200MM X 50M/ ROLL)',
	'CP-G.I_BLOCK_MESH__(100MM_X_50M/_ROLL)': 'G.I BLOCK MESH  (100MM X 50M/ ROLL)',
	'CP-G.I_BLOCK_MESH__(100MM_X_50M/_ROLL)-2': 'G.I BLOCK MESH  (100MM X 50M/ ROLL)',
	'CP-G.I_BLOCK_MESH__(250MM_X_50M/_ROLL)': 'G.I BLOCK MESH  (250MM X 50M/ ROLL)',
	'CP-G.I_BLOCK_MESH__(250MM_X_50M/_ROLL)-2': 'G.I BLOCK MESH  (250MM X 50M/ ROLL)',
	'CP-JK_PLAST_COAT_RS11_(_50KG_/_BAG_)': 'JK PLAST COAT-RS11 ( 50KG / BAG )',
	'CP-JK_PLAST_COAT_RS11_(_50KG_/_BAG_)-2': 'JK PLAST COAT-RS11 ( 50KG / BAG )',
	'CP-JK_PLAST_PP22_(_50KG_/_BAG_)': 'JK PLAST PP22 ( 50KG / BAG )',
	'CP-JK_PLAST_PP22_(_50KG_/_BAG_)-2': 'JK PLAST PP22 ( 50KG / BAG )',
	"CP-MARINE_PLYWOOD__(_8'_X_4'_X_18MM_)": "MARINE PLYWOOD  ( 8' X 4' X 18MM )",
	"CP-MARINE_PLYWOOD__(_8'_X_4'_X_18MM_)-2": "MARINE PLYWOOD  ( 8' X 4' X 18MM )",
	"CP-MARINE_PLYWOOD_(_8'_X_4'_X_12MM_)": "MARINE PLYWOOD ( 8' X 4' X 12MM )",
	"CP-MARINE_PLYWOOD_(_8'_X_4'_X_12MM_)-2": "MARINE PLYWOOD ( 8' X 4' X 12MM )",
	'CP-MATERX_LAVACHEM_FLOWABLE_(_25KG/BAG)': 'MATERX LAVACHEM FLOWABLE ( 25KG/BAG)',
	'CP-MATERX_LAVACHEM_FLOWABLE_(_25KG/BAG)-2': 'MATERX LAVACHEM FLOWABLE ( 25KG/BAG)',
	'CP-MIX_GROUT_NS_(_25KG/BAG)': 'MIX GROUT NS ( 25KG/BAG)',
	'CP-MIX_GROUT_NS_(_25KG/BAG)-2': 'MIX GROUT NS ( 25KG/BAG)',
	'CP-MIXBUILD_MC_GREY(_25KG/BAG)': 'MIXBUILD MC GREY( 25KG/BAG)',
	'CP-MIXBUILD_MC_GREY(_25KG/BAG)-2': 'MIXBUILD MC GREY( 25KG/BAG)',
	'CP-MS_60_6MM_PROTECTION_BOARD_(1M*2M_)': 'MS 60 6MM PROTECTION BOARD (1M*2M )',
	'CP-MS60_PROTECTION_BOARD_6MM__(1M*2M_)': 'MS 60 6MM PROTECTION BOARD (1M*2M )',
	'CP-MULTI_DIRECTIONAL_REINJECTIBLE_HOSE_AN_INTEGRATED_INJECTION_SYSTEM_100LM/BOX': 'MULTI-DIRECTIONAL REINJECTIBLE HOSE-AN INTEGRATED INJECTION SYSTEM 100LM/box',
	'CP-MULTI_DIRECTIONAL_REINJECTIBLE_HOSE_AN_INTEGRATED_INJECTION_SYSTEM_100LM/BOX-2': 'MULTI-DIRECTIONAL REINJECTIBLE HOSE-AN INTEGRATED INJECTION SYSTEM 100LM/box',
	'CP-NEOBOND_SBR_250_(_20LTR_/_PAIL_)': 'NEOBOND SBR 250 ( 20LTR / PAIL )',
	'CP-NEOBOND_SBR_250_(_20LTR_/_PAIL_)-2': 'NEOBOND SBR 250 ( 20LTR / PAIL )',
	'CP-NEOGROUT_NS_(20KG/BAG)': 'NEOGROUT NS (20KG/BAG)',
	'CP-NEOGROUT_NS_(20KG/BAG)-2': 'NEOGROUT NS (20KG/BAG)',
	'CP-NEOSULPHIDE_SEALANT_GG_PART_A+PART_B__(_2.5LTR/PACK_)': 'NEOSULPHIDE SEALANT GG PART A+PART B  ( 2.5LTR/PACK )',
	'CP-NEOSULPHIDE_SEALANT_GG_PART_A+PART_B__(_2.5LTR/PACK_)-2': 'NEOSULPHIDE SEALANT GG PART A+PART B  ( 2.5LTR/PACK )',
	'CP-NEOSULPHIDE_SEALANT_PART_A+PART_B__(_2.5LTR/PACK_)': 'NEOSULPHIDE SEALANT PART A+PART B  ( 2.5LTR/PACK )',
	'CP-OPC_CEMENT_(_50KG_/_BAG_)': 'OPC CEMENT ( 50KG / BAG )',
	'CP-OPC_CEMENT_(_50KG_/_BAG_)-2': 'OPC CEMENT ( 50KG / BAG )',
	'CP-PVC_WATERSTOPPER__DOUBLE_FACE_(15M/ROLL)': 'PVC WATERSTOPPER -DOUBLE FACE (15M/ROLL)',
	'CP-PVC_WATERSTOPPER__DOUBLE_FACE_(15M/ROLL)-2': 'PVC WATERSTOPPER -DOUBLE FACE (15M/ROLL)',
	'CP-PVC_WATWER_STOP__IC250_(15M/ROLL)': 'PVC WATWER STOP -IC250 (15M/ROLL)',
	'CP-PVC_WATWER_STOP__IC250_(15M/ROLL)-2': 'PVC WATWER STOP -IC250 (15M/ROLL)',
	'CP-RENDEROC_FC_(20KG/BAG_)': 'RENDEROC FC (20KG/BAG )',
	'CP-RENDEROC_FC_(20KG/BAG_)-2': 'RENDEROC FC (20KG/BAG )',
	'CP-RENDEROC_HS__(20KG/BAG_)': 'RENDEROC HS  (20KG/BAG )',
	'CP-RENDEROC_HS__(20KG/BAG_)-2': 'RENDEROC HS  (20KG/BAG )',
	'CP-S.S_ANGLE_BEAD__(_50MM_X_50MM_X_13MM_)': 'S.S ANGLE BEAD  ( 50MM X 50MM X 13MM )',
	'CP-S.S_ANGLE_BEAD__(_50MM_X_50MM_X_13MM_)-2': 'S.S ANGLE BEAD  ( 50MM X 50MM X 13MM )',
	'CP-SIKA_WATERSTOP_G__1C25_(_15M/ROLL)': 'SIKA WATERSTOP G -1C25 ( 15M/ROLL)',
	'CP-SIKA_WATERSTOP_G__1C25_(_15M/ROLL)-2': 'SIKA WATERSTOP G -1C25 ( 15M/ROLL)',
	'CP-SIKA_WATERSTOP_G__EC25_(_15M/ROLL)': 'SIKA WATERSTOP G -EC25 ( 15M/ROLL)',
	'CP-SIKA_WATERSTOP_G__EC25_(_15M/ROLL)-2': 'SIKA WATERSTOP G -EC25 ( 15M/ROLL)',
	'CP-SIKALATIC_311__AE_(_20_LTR_PAIL_)': 'SIKALATIC 311- AE ( 20 LTR PAIL )',
	'CP-SIKALATIC_311__AE_(_20_LTR_PAIL_)-2': 'SIKALATIC 311- AE ( 20 LTR PAIL )',
	'CP-SS_PLASTER_STOPPER__(13MM_X_13_MTR_)': 'SS PLASTER STOPPER  (13MM X 13 MTR )',
	'CP-SS_PLASTER_STOPPER__(13MM_X_13_MTR_)-2': 'SS PLASTER STOPPER  (13MM X 13 MTR )',
	'CP-SUPERCAST_INJECTOSEAL_(_100M/ROLL)': 'SUPERCAST INJECTOSEAL ( 100M/ROLL)',
	'CP-SUPERCAST_INJECTOSEAL_(_100M/ROLL)-2': 'SUPERCAST INJECTOSEAL ( 100M/ROLL)',
	'CP-WATAFOIL_250MM_(_12M/ROLL)': 'WATAFOIL 250MM ( 12M/ROLL)',
	'CP-WATAFOIL_250MM_(_12M/ROLL)-2': 'WATAFOIL 250MM ( 12M/ROLL)',
	'CP-WEBERAD_225_MB_(_20LTR_/_PAIL_)': 'WEBERAD 225 MB ( 20LTR / PAIL )',
	'CP-WEBERAD_225_MB_(_20LTR_/_PAIL_)-2': 'WEBERAD 225 MB ( 20LTR / PAIL )',
	'CP-WEBERCOL_PRO_GREY__(25KG/_BAG_)': 'WEBERCOL PRO GREY  (25KG/ BAG )',
	'CP-WEBERCOL_PRO_GREY__(25KG/_BAG_)-2': 'WEBERCOL PRO GREY  (25KG/ BAG )',
	'CP-WEBERJOINT_112_BONE_WHITE_(5_KG_/_BAG_)': 'WEBERJOINT 112 BONE WHITE (5 KG / BAG )',
	'CP-WEBERJOINT_112_BONE_WHITE_(5_KG_/_BAG_)-2': 'WEBERJOINT 112 BONE WHITE (5 KG / BAG )',
	'CP-WEBERJOINT_120_IVORY__(5_KG_/_BAG_)': 'WEBERJOINT 120 IVORY  (5 KG / BAG )',
	'CP-WEBERJOINT_120_IVORY__(5_KG_/_BAG_)-2': 'WEBERJOINT 120 IVORY  (5 KG / BAG )',
	'CP-WHITE_WOOD_(1"_X_4"_X_13\')': 'WHITE WOOD (1" X 4" X 13\')',
	'CP-WHITE_WOOD_(1"_X_4"_X_13\')-2': 'WHITE WOOD (1" X 4" X 13\')',
	'CP-WHITE_WOOD_(3"_X_3"_X_13\')': 'WHITE WOOD (3" X 3" X 13\')',
	'CP-WHITE_WOOD_(3"_X_3"_X_13\')-2': 'WHITE WOOD (3" X 3" X 13\')',
	'CP-WING_NUT_HD': 'WING NUT HD',
	'CP-WING_NUT_HD-2': 'WING NUT HD',
}


def execute() -> None:
	result = run()
	frappe.logger("construction_management").info(
		{"event": "disable_repeated_controlled_catalog_items", **result}
	)


def run() -> dict:
	"""Disable zero-stock duplicates; return counters for logging/tests."""
	items = _load_items()
	missing = [code for code in ITEM_CODES if code not in items]
	qty_by_item = _bin_qty_by_item(list(items))
	groups = _group_by_description(items)

	disabled: list[str] = []
	kept_with_stock: list[str] = []
	kept_as_survivor: list[str] = []
	skipped: list[str] = []

	for _group_key, members in groups.items():
		outcomes = _apply_group(members, qty_by_item)
		disabled.extend(outcomes["disabled"])
		kept_with_stock.extend(outcomes["kept_with_stock"])
		kept_as_survivor.extend(outcomes["kept_as_survivor"])
		skipped.extend(outcomes["skipped"])

	return {
		"missing": len(missing),
		"disabled": len(disabled),
		"kept_with_stock": len(kept_with_stock),
		"kept_as_survivor": len(kept_as_survivor),
		"skipped": len(skipped),
		"disabled_codes": disabled,
		"kept_with_stock_codes": kept_with_stock,
		"kept_as_survivor_codes": kept_as_survivor,
	}


def _apply_group(members: list[dict], qty_by_item: dict[str, float]) -> dict:
	stocked = [m for m in members if flt(qty_by_item.get(m["name"], 0)) > 0]
	zero = [m for m in members if flt(qty_by_item.get(m["name"], 0)) <= 0]

	disabled: list[str] = []
	kept_with_stock = [m["name"] for m in stocked]
	kept_as_survivor: list[str] = []
	skipped: list[str] = []

	if stocked:
		to_disable = zero
	else:
		survivor = _pick_survivor(zero)
		to_disable = [m for m in zero if m["name"] != survivor]
		if survivor:
			_ensure_enabled(survivor, members)
			kept_as_survivor.append(survivor)

	for member in to_disable:
		if member.get("disabled"):
			skipped.append(member["name"])
			continue
		frappe.db.set_value("Item", member["name"], "disabled", 1, update_modified=False)
		disabled.append(member["name"])

	return {
		"disabled": disabled,
		"kept_with_stock": kept_with_stock,
		"kept_as_survivor": kept_as_survivor,
		"skipped": skipped,
	}


def _ensure_enabled(item_code: str, members: list[dict]) -> None:
	"""Keep the zero-stock survivor orderable when the whole group had no stock."""
	row = next((m for m in members if m["name"] == item_code), None)
	if row and row.get("disabled"):
		frappe.db.set_value("Item", item_code, "disabled", 0, update_modified=False)


def _pick_survivor(members: list[dict]) -> str | None:
	if not members:
		return None
	non_suffix = [m for m in members if not m["name"].endswith("-2")]
	pool = non_suffix or members
	order = {code: idx for idx, code in enumerate(ITEM_CODES)}
	pool.sort(key=lambda m: order.get(m["name"], 10**9))
	return pool[0]["name"]


def _group_by_description(items: dict[str, dict]) -> dict[str, list[dict]]:
	groups: dict[str, list[dict]] = defaultdict(list)
	for code, row in items.items():
		key = DESCRIPTION_BY_CODE.get(code) or row.get("item_name") or code
		groups[key].append(row)
	return groups


def _load_items() -> dict[str, dict]:
	rows = frappe.get_all(
		"Item",
		filters={"name": ["in", list(ITEM_CODES)]},
		fields=["name", "disabled", "item_name"],
		limit_page_length=0,
	)
	return {row.name: row for row in rows}


def _bin_qty_by_item(item_codes: list[str]) -> dict[str, float]:
	if not item_codes:
		return {}
	rows = frappe.db.sql(
		"""
		SELECT item_code, COALESCE(SUM(actual_qty), 0) AS qty
		FROM `tabBin`
		WHERE item_code IN %(codes)s
		GROUP BY item_code
		""",
		{"codes": item_codes},
		as_dict=True,
	)
	return {row.item_code: flt(row.qty) for row in rows}

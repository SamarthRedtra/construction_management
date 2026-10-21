# Bitumat / Sheridan GRN item-mapping pilot — results (skada.local)

Date: 2026-10-21  
Source: `GRN Testing - Bitumat, Sheridan.xlsx`  
Engine: `apply_item_trail_list_migration` (`merge` via `frappe.model.rename_doc.rename_doc`)

## Verdict: GO for same-UOM Bitumat-style merges

Open LPO lines can be remapped to new CP catalog codes **without cancelling POs or recreating historical GRNs**. Remaining qty can be received against the new CP item.

## What was applied (7 merges)

| Old Item Code | New Item Code |
|---|---|
| CONCRETE PRIMER D41 ( 200 LTR PER DRUM ) | CP-CONCRETE_PRIMER_D41_(200LTR_/DRUM) |
| SUPERSEAL  ( 200 LTR PER DRUM ) | CP-SUPERSEAL_WB_(200_LTR_/DRUM) |
| POLYFLEX MS 270 APP MEMBRTANE  ( 1M X  10M PER ROLL ) | CP-POLYFLEX_MS_270_APP_MEMBRTANE____(1M*10M_ROLL) |
| POLYFLEX GN MINERAL 180 ( 1M X 10M PER ROLL ) | CP-POLYFLEX_GN_MINERAL_180___(1M*10M_ROLL) |
| EXTRUDED INSULATION BOARD 60MM  DENSITY 32-35 KG | CP-E_FOAM__60MM_(_1.25_X_0.60M_)_DENSITY_32_35_KG |
| EXTRUDED INSULATION BOARD  70MM ( 1.25 X 0.60M ) | CP-ROOFMATE__70MM_(_1.25_X_0.60M_)_DENSITY_32_35_KG |
| PREMIERFLEX 200 AD 270 ( 1M X  10M PER ROLL ) | CP-PREMIERFLEX_200_AD_270_(1M*10M_ROLL) |

CSV: [`apply_item_trail_list_migration.csv`](apply_item_trail_list_migration.csv)

## Smoke GRN

- PO: `MRG-LPO-00546-1` (all 7 lines now CP codes; prior received qty kept — e.g. Polyflex 391 / 115)
- New GRN: `MAT-PRE-2026-00024` — received **1** of `CP-SUPERSEAL_WB_(200_LTR_/DRUM)`
- SLE: `+1` on warehouse `1186-Arady Developments DIFC - MRG`
- PO `received_qty` for Superseal → `1.0`
- Historical GRN `MRG-GRN-01115` lines now show the CP Polyflex codes (history retained)

## UOM exceptions — NO-GO for merge (Sheridan set)

Do **not** merge these until Stock UOM is aligned (old ≠ new):

| Old Item Code | Old UOM | New Item Code | New UOM |
|---|---|---|---|
| NEOSEAL FLEX 550 - WHITE  (PART A 15KG+ PART B 5KG) | KIT | CP-NEOSEAL_FLEX_550___WHITE__(_PART_A_15KG+_PART_B_5KG) | Nos |
| NEOSULPHIDE SEALANT-GUN GRADE 2.5LTR(PART 4 4KG+PART B 0.250KG) | KIT | CP-NEOSULPHIDE_SEALANT_GG_PART_A+PART_B__(_2.5LTR/PACK_) | Nos |
| NEOFLEX PU 25 LM (POLYURETHENE SEALANT) 600 ML-GREY | TUBE | CP-NEOFLEX_PU_25_LM_GREY_(600_ML_SAUSAGE) | Nos |
| NEOSEAL FLEX 588 -GREY (PART A 25KG+PART B 10KG) | KIT | CP-NEOSEAL_FLEX_588__GREY_(PART_A_25KG+PART_B_10KG) | Nos |
| NEOBOND SBR 250  ( 20 LTR TIN ) | PAIL | CP-NEOBOND_SBR_250_(_20LTR_/_PAIL_) | Nos |
| NEOGROUT NS 20 KG | BAG | CP-NEOGROUT_NS_(20KG/BAG) | Nos |

Same-code noop (already catalog): `FILLER BOARD 10MM THICK WITH 7CM CUTTING PCS`

## Code fixes made during pilot

1. `rename_doc` now calls `frappe.model.rename_doc.rename_doc` (wrapper dropped `ignore_permissions`).
2. `_cell()` preserves internal spaces in Item Codes (double-space legacy codes were incorrectly “already migrated”).
3. Site: recreated missing custom DocType **Company Restriction** (Link target on Item/Customer/Supplier) so rename could complete.

## Full rollout checklist

1. Expand Trail CSV with `action=merge` only where both Items exist and Stock UOM matches.
2. Keep a separate UOM-exception list (no merge).
3. Run `preflight_uom` then `bench execute …apply_item_trail_list_migration.run` with loaded rows (do not rely on empty first migrate).
4. Smoke GRN on one open LPO per company before mass apply.
5. Legacy open LPOs still have `controlled_procurement=0` — Desk GRN works; Vue `/procurement` GRN for those POs is a separate follow-up.

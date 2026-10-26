# Item Linking – Redtra (LPO Reference) status

Date: 2026-10-22  
Site: `skada.local`  
Source: `Item Linking - Redtra ( Submitted to Samarth ).xlsx` → sheet **Final - To Submit**  
Engine: `apply_item_trail_list_migration` (`merge` / `name_only` via `frappe.model.rename_doc.rename_doc`)

## Sheet size

| Metric | Count |
|---|---:|
| Sheet data rows | 425 |
| Unique old→new pairs | 421 |
| Distinct LPOs referenced | ~499 |

## This run (GO batch)

CSV: [`apply_item_trail_list_migration.csv`](apply_item_trail_list_migration.csv)

| Result | Count |
|---|---:|
| Applied (merge) | 85 |
| Applied (`name_only`) | 1 |
| Failed (after retry) | 0 |

Notes:

1. First pass: 75 applied, 11 failed on missing Python module for child DocType **Company Restriction**.
2. Stub added under [`erpnext/stock/doctype/company_restriction/`](../../../erpnext/erpnext/stock/doctype/company_restriction/) (DB DocType already existed as Stock child table).
3. Retry of 11 rows: all applied.

`bench migrate` was **not** used (patch already in Patch Log). Applied via `bench console` → `apply_row` / commit.

## Done vs pending (post-run, 421 unique pairs)

| Bucket | Count | % |
|---|---:|---:|
| **Done — same code** | 141 | 33% |
| **Done — migrated** (old gone, new exists) | 91 | 22% |
| **Pending — Stock UOM mismatch** | 163 | 39% |
| **Pending — other Item props** (`is_stock_item` / serial / batch) | 25 | 6% |
| **Pending — new Item missing** | 1 | &lt;1% |
| **Total done** | **232** | **55%** |
| **Total pending** | **189** | **45%** |

### Pending examples (not merged — by design)

**UOM mismatch** (old Stock UOM ≠ new): e.g. `RENDROC HS…` Nos→BAGS, Sheridan KIT/TUBE/PAIL/BAG→Nos, hire Day, etc.

**Property mismatch** (same UOM but `is_stock_item` differs): e.g. `PAPER A3` (0 vs 1), several stationery/tools.

**Target missing:** `SOPRADERE HT 20 LTR` → `CP-SOPRADERE_HT_(200LTR_/DRUM)` (new Item not in master) — LPO `MRG-LPO-00146`.

## Spot checks

| PO | Result |
|---|---|
| `MRG-LPO-00546-1` | All 7 Bitumat lines now CP codes; qty / received_qty retained (e.g. Polyflex received 391 / 115) |
| `MRG-LPO-00395` | Still legacy codes (`RENDROC HS…`, `RENDEROC FC…`) — **expected** (Nos→BAGS UOM block) |

## Next for remaining 189

1. Align Stock UOM (or accept `name_only` / `rename_code` without merge) for the 163 UOM rows.
2. Decide stock vs non-stock for the 25 `is_stock_item` conflicts, then re-merge.
3. Create missing `CP-SOPRADERE_HT_(200LTR_/DRUM)` (or correct target code) and merge/rename.
4. Re-run GO CSV build + `run` after those fixes; do not force-merge across UOM.

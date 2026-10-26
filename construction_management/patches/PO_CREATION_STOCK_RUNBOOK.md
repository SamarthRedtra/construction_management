# Stock runbook after LPO sheet PO creation

## Already on migrate (`patches.txt`)

1. `stage_mrg_stock_snapshot`
2. `apply_mrg_corrected_stock_2026_10_12` (allows negative stock during SR submit)
3. `repost_mrg_corrected_stock_to_2026_09_30`
4. `apply_item_trail_list_migration` (old → new item on existing POs)
5. `create_pos_from_po_creation_sheet` (this sheet → draft POs dated 2025-09-04)

## Duplicate repair (manual — do not auto-patch)

If `tabBin.actual_qty < 0` remains for MRG after the above:

```sh
# Preview (writes plan_hash)
bench --site <site> execute construction_management.scripts.mrg_stock_duplicate_repair.run \
  --kwargs '{"output_dir":"/absolute/path/to/preview"}'

# Apply reviewed hash
bench --site <site> execute construction_management.scripts.mrg_stock_duplicate_repair.run \
  --kwargs '{"dry_run":0,"expected_site":"<site>","plan_hash":"<HASH>","output_dir":"/absolute/path/to/applied"}'

# Finish queued Repost Item Valuation jobs
bench --site <site> execute construction_management.scripts.mrg_stock_duplicate_repair.revaluation.finish \
  --kwargs '{"dry_run":0,"expected_site":"<site>","plan_hash":"<HASH>","output_dir":"/absolute/path/to/final"}'
```

Production requires a **fresh** preview hash for that site (`allow_production:1`). Do not reuse a local trial hash.

Local trial reference: `artifacts/mrg_stock_investigation_2026-10-22/`
(`plan_hash` in `local_trial_applied/final_after_revaluation/result.json`).

## skada.local check (2026-10-24)

- Corrected-stock + item-trail patches: already in Patch Log.
- Sheet draft POs: `transaction_date=2025-09-04`, warehouse `Stores - MRG`, project `100`.
- Remaining: 5 negative bins; 2 Repost Item Valuation jobs Queued — finish via `revaluation.finish` after a fresh duplicate-repair preview if legacy negatives must be cleared. Duplicate repair is **not** in `patches.txt`.

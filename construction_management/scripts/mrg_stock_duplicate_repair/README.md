# MRG stock duplicate correction

This is a manually invoked repair, not an automatic deployment patch. It retires verified legacy balances already introduced under the controlled CP catalog, using submitted Stock Reconciliations dated 30 September 2026 at 00:00:01. It preserves the new item quantities and valuation rates. It does not merge items, rewrite purchase documents, edit GL/SLE tables directly, or zero expense accounts with journals.

The packaged item-linking workbook and original stock snapshot are checksum verified. A correction requires an explicit mapping, agreement between the source quantity and historical legacy balance, and a new-code reconciliation at the cutover. Different package capacities, reservations, serial/batch items, uncertain quantities and later legacy activity are held for review. Generic package labels such as Roll versus Nos are treated as one package only when the explicitly mapped package capacities do not conflict and the complete source quantity matches the historical legacy quantity. Review those mappings with the CA.

## Local trial

A database backup was taken before the trial. The backup path is recorded in the CA handover document under the workspace's `artifacts/mrg_stock_investigation_2026-10-22` directory.

The local trial required syncing Inventory Dimension because the installed ERPNext code referenced `mandatory_depends_on_backend`, which was missing from the database. The sole existing inventory dimension had no old mandatory expression to migrate. This repair does not perform schema changes automatically. On another site, resolve code/schema compatibility and preserve any configured mandatory expressions before applying.

Preview:

```sh
bench --site skada.local execute construction_management.scripts.mrg_stock_duplicate_repair.run \
  --kwargs '{"output_dir":"/absolute/path/to/preview"}'
```

Apply the exact reviewed preview:

```sh
bench --site skada.local execute construction_management.scripts.mrg_stock_duplicate_repair.run \
  --kwargs '{"dry_run":0,"expected_site":"skada.local","plan_hash":"HASH_FROM_PREVIEW","output_dir":"/absolute/path/to/applied"}'
```

Apply requires the exact site name and preview hash. Stale plans are rejected. The correction documents are submitted and validated within one database transaction; the bench command commits only after success. Every correction must remove the expected stock value and post an equal debit to **Stock Received But Not Billed - MRG** (liability; not Stock Adjustment), clear the selected legacy balance, preserve new-item balances, leave September/October P&L unchanged for Stock Adjustment / COGS / Stock Expenses, and move inventory by the expected amount. Failure rolls the batch back. Deterministic voucher names and a checksummed File manifest make a repeated run return `already_applied` rather than add another correction.

### Why SRBNB (not Stock Adjustment)

The 30-Sep duplicate retirement is a balance-sheet inventory correction for stock already represented under the CP catalog. Debiting **Stock Received But Not Billed - MRG** reduces that liability while Stock In Hand is credited. **Stock Adjustment - MRG** is reserved for consumption / issue paths so P&L books when materials are actually used, not at this correction.

### Remap all 30-Sep MAT-RECO vouchers (Stock Adjustment → SRBNB)

Default rebook target is every **submitted** `MAT-RECO-%` on `2026-09-30` whose `expense_account` is still Stock Adjustment - MRG (posting date kept). Already-remapped vouchers (e.g. `MAT-RECO-2026-00170-1`) are not selected. Production `MRG-DUP-*` should be created fresh on SRBNB by the repair runner; pass `include_mrg_dup:1` only to remount existing DUPs still on Stock Adjustment.

```sh
# Dry run — all remaining 30-Sep MAT-RECO on Stock Adjustment
bench --site skada.local execute \
  construction_management.scripts.mrg_stock_duplicate_repair.rebook_expense_to_srbnb.execute \
  --kwargs '{"dry_run":1}'

# Apply — requires exact site; non-local also needs allow_production:1
bench --site skada.local execute \
  construction_management.scripts.mrg_stock_duplicate_repair.rebook_expense_to_srbnb.execute \
  --kwargs '{"dry_run":0,"expected_site":"skada.local"}'
```

Idempotent and resumable: each voucher is committed after amend. Re-run skips vouchers already on SRBNB.

## Finish item-merge revaluations

Pre-existing item merges queued valuation jobs before this correction. Until those jobs and their linked accounting rebuilds finish, ledger closing values can disagree with accounting. This phase uses ERPNext's native resumable reposting, which commits job checkpoints separately from the atomic correction batch.

Preview the captured jobs:

```sh
bench --site skada.local execute construction_management.scripts.mrg_stock_duplicate_repair.revaluation.finish \
  --kwargs '{"plan_hash":"HASH_FROM_PREVIEW","output_dir":"/absolute/path/to/revaluation-preview"}'
```

Complete them locally:

```sh
bench --site skada.local execute construction_management.scripts.mrg_stock_duplicate_repair.revaluation.finish \
  --kwargs '{"dry_run":0,"expected_site":"skada.local","plan_hash":"HASH_FROM_PREVIEW","output_dir":"/absolute/path/to/final-review"}'
```

The captured jobs and their explicitly linked accounting jobs are processed first. The function then compares movement totals against closing stock for every MRG item/warehouse at September and October month-end. Any remaining stale chain is rebuilt using a deterministically named native revaluation job and its linked accounting jobs. More than 50 such additional chains stops for inspection. No ledger tables are edited directly.

A restart skips completed jobs. Failed or already running jobs stop the operation for inspection. The function does not automatically restart failed jobs. `max_jobs` can limit the initial stock jobs; `job_names` can select a subset of captured names. Linked GL jobs may be created by ERPNext during the stock phase and are included in the final review. Inspect `remaining_captured_jobs`, `remaining_accounting_jobs`, `remaining_chain_gaps` and `inventory_reconciled` before accepting the result.

## CA review and production

`CA_review.xlsx` contains the plan identity, before/after monthly P&L, eligible rows, exceptions, correction-voucher checks, stock/GL reconciliation and revaluation statuses. The original plan and results are also exported as JSON/CSV and attached privately to the first correction voucher.

The `no_positive_legacy_balance` category does not authorize a correction. It includes old codes already merged into CP codes; those require valuation completion and review of the surviving snapshot, rather than another removal of legacy stock. A positive P&L does not independently prove the physical stock is correct. Quantity/date/package conflicts require an agreed mapping or physical count and are not auto-resolved.

Production has not been run. After CA approval, deploy this package together with `construction_management/data/mrg_item_linking_2026_10_22.xlsx` and the already packaged original snapshot. Take a fresh production backup and run a production-specific preview. Compare its eligibility, exceptions and accounting effects to the approved trial. Use that preview's hash and exact site name; do not copy a local hash without checking it matches. Applying to a non-local site additionally requires the explicit `allow_production:1` argument for both phases. No entry is added to `patches.txt`.

For recovery, use the pre-trial backup only on an isolated review copy or use an audited cancellation of this batch followed by valuation completion. Restoring a backup onto a site with subsequent work would discard that later work. No automatic destructive restore is provided.

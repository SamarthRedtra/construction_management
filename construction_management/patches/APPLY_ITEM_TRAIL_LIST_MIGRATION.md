# Item Trail List mapping (employees)

Fill `apply_item_trail_list_migration.csv` — one row per item that must change.

Columns:

| Column | Required | Meaning |
|---|---|---|
| `old_item_code` | yes | Exact Item Code in the system today |
| `new_item_code` | for `rename_code` / `merge` | Trail List code (blank for `name_only`) |
| `new_item_name` | for `name_only` | New description from Trail List |
| `action` | yes | `name_only` \| `rename_code` \| `merge` |
| `current_uom` | no | Stock UOM in the system today |
| `trail_uom` | no | UOM on the Trail List |
| `uom_flag` | no | `yes` when Trail UOM differs from system Stock UOM |

## Rule when UOM differs

**Do not use `merge`.** Use `name_only` or `rename_code`, keep the system Stock UOM, set `uom_flag=yes`, and fill `current_uom` / `trail_uom`.

The migration never changes Stock UOM. PO/GRN history stays valid.

| Situation | Action |
|---|---|
| Same code, only name changes | `name_only` |
| Code becomes a new Trail code (new code must not exist) | `rename_code` |
| Two existing codes are the same item **and** Stock UOM matches | `merge` |
| Duplicates but UOM differs (Nos vs LM, etc.) | Do **not** merge — rename/name the primary; flag UOM |

Example (UOM differs — keep Nos in the system):

```text
CP-PIPE_20MM,CP-PIPE_20MM_LM,PIPE 20MM,rename_code,Nos,LM,yes
```

## Preflight before migrate

```bash
bench --site <site> execute construction_management.patches.apply_item_trail_list_migration.preflight_uom
```

Lists every row with `uom_flag=yes` or where `trail_uom` differs from the Item’s Stock UOM / `current_uom`.

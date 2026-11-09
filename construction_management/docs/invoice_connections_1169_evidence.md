# Project 1169 — Invoice Connections evidence (Connections panel)

Checked on site `skada.local` against Suhana’s note that a July invoice was connected with an April invoice. Focus: **Connections** (option A).

Shared link: Sales Order `PINV/1169/2026-OCT/1-1`.

## Summary

| Document | Role | Connections finding |
|----------|------|---------------------|
| `PINV/1169/2026-OCT/1-1` | Oct proforma (amended) | **No Sales Invoice** in Connections. `custom_tax_invoice` empty. |
| `SAL-ORD-2026-00370` | July proforma (31 Jul 2026) | Sales Invoice `ACC-SINV-2026-00258` (26 Aug 2026) — expected late tax invoice. |
| `ACC-SINV-2026-00258` | Tax invoice for July SO | Header/line `sales_order` = `SAL-ORD-2026-00370`. No April SO/SI. |
| `ACC-SINV-2026-00161` | May advance SI (19 May 2026) | Separate advance; not linked to the July SO in Connections. |

There is **no April Sales Invoice** on project 1169. Closest early document is the **May advance**.

## Connections dump (key links)

### `PINV/1169/2026-OCT/1-1` (Sales Order)

- Journal Entry: `ACC-JV-2026-07314` (2026-10-21)
- BOQ Progress Ledger: `BOQL-2026-01456` (2026-10-21)
- Project SOA Follow Up: `PSOAFU-2026-00230`, `PSOAFU-2026-00315`
- Sales Invoice: **none**

### `SAL-ORD-2026-00370` (Sales Order)

- Sales Invoice: `ACC-SINV-2026-00258` (2026-08-26)
- Journal Entry: `ACC-JV-2026-03736` (2026-07-31)
- BOQ Progress Ledger: `BOQL-2026-01088` (2026-07-31)

### `ACC-SINV-2026-00258` (Sales Invoice)

- Payment Entry: `ACC-PAY-2026-00603` (2026-10-26)
- Linked Sales Order (header + lines): `SAL-ORD-2026-00370`

## Draft reply to Suhana

> Hi Suhana — we checked the link you shared (`PINV/1169/2026-OCT/1-1`) on Connections.
>
> That document is an **October** proforma Sales Order. Its Connections do **not** show any Sales Invoice (and there is no April invoice on project 1169).
>
> The July billing for this project is separate and looks correct:
> - Proforma: `SAL-ORD-2026-00370` (31 Jul)
> - Tax invoice: `ACC-SINV-2026-00258` (26 Aug), linked to that July proforma in Connections
>
> The only earlier invoice on 1169 is advance `ACC-SINV-2026-00161` (19 May), which is not connected to the July SO.
>
> If you meant a different pair (July tax invoice showing an April proforma on another project), please send the exact July and April document names from Connections and we will check those next. We also have a dry-run audit for SO↔SI links with a 2+ month gap if useful.

## Follow-up audit

Cross-month SO↔SI Connections pairs (readonly):

```bash
bench --site skada.local execute construction_management.api.audit_so_si_month_mismatch.run
bench --site skada.local execute construction_management.api.audit_so_si_month_mismatch.run --kwargs "{'project': '1169'}"
```

Also runs once on migrate via patch `construction_management.patches.audit_so_si_month_mismatch` (prints the report; does not change links).

Do not auto-unlink; accounts classify each row as late billing vs wrong link.

### Run on skada.local (this ticket)

- Project **1169**, `min_month_gap=2`: **0 pairs** — nothing to correct for the shared link.
- Site-wide: **52 pairs** with gap ≥ 2 months (many are late tax conversion or combined TINVs). Example of the July↔April Connections pattern on another project: `SAL-ORD-2026-00277` (2026-04-29, project 1148) ↔ `ACC-SINV-2026-00232` (2026-07-15).

### Fix status

No confirmed wrong links for project 1169. Data changes deferred until Suhana (or accounts) flags a specific pair from the audit as incorrect.

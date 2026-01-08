# BOQ & Cost Control Enhancements Walkthrough

## 1. Multi-Level Budget Control
Implementation of Requirement 3.
- **Project Settings**: Added fields to `Project` DocType configuration:
  - `Enforcement Level`: None, Project Level, BOQ Item Level, Both.
  - `Budget Mode`: Soft Limit (Warning) or Hard Limit (Block).
  - `Tolerance`: Percentage allowance.
- **Validation Logic**: 
  - New `api/budget_control.py` service.
  - Validates "Actual Cost (GL) + New DPR Cost" against Estimates.
  - Triggered during `Daily Progress Record` submission.

## 2. Real-Time Costing via GL Entries
Implementation of Requirement 2.
- **Hook**: Added `GL Entry` `on_update` hook in `hooks.py`.
- **Logic**:
  - Costs are no longer updated solely by DPR submission (Operational).
  - Instead, the system listens for GL Entries (financial transactions).
  - Updates `Project` and `BOQ Item` actual costs based on "Expense" and "WIP" account postings.
  - Ensures strict financial accuracy ("Financial Costing").
- **DPR Integration**:
  - DPR now generates REAL Journal Entries for Labor (`employees` tables) and Assets (`assets` table) to ensure these costs hit the GL.
  - Disabled legacy cost update logic in DPR to avoid double-counting.

## 3. Unit Level Breakdown
Implementation of Requirement 3 (Estimation).
- **BOQ Item**: Added `item_breakdown` child table.
- **Calculation**: Pre-calculation logic updates `total_unit_rate` and component estimates based on breakdown rows (Material, Labour, Asset, etc.).

## 4. Setup Instructions
To activate these changes:
1. **Migrate Database**: Run `bench migrate` to apply new Custom Fields on `Project` and `BOQ Item`.
2. **Restart Server**: Run `bench restart` to load the new `GL Entry` hook.
3. **Verify Accounts**: Ensure Company has default Expense/Payable accounts or custom usage fields for Labor/Asset journaling.

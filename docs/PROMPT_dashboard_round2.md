# Dashboard prompt, review round 2 (generator changes of 2026-11-17)

Paste everything below the line into a Claude Code session opened in the **dashboard repo** (not in the generator repo).

---

## Task

The NorFinGen generator and its production database were changed on 2026-11-17 (already deployed, data regenerated). Adapt
the Streamlit dashboard to it. Work in the order A → B → C → D and stop after each step so I can review. Do not run git
commands, only propose them (commit messages fully in English, no `Co-Authored-By` trailer). Never print the database URL
or any token. Read-only access to the data is enough; do not modify the generator or the database. Keep the existing style,
the EN/PL/NO switch and dark mode working: every new text must exist in all three languages.

## What changed in the data (facts, deployed and verified)

1. **New view `v_invoice_status`, one row per sales invoice (order)**, the single source of truth for the state of an invoice.
   Columns: `order_id`, `invoice_status` (`PAID` | `OPEN` | `OVERDUE` | `WRITTEN_OFF`), `is_overdue`, `payment_due_date`,
   `paid_date`, `paid_late`, `write_off_voucher_id`, `write_off_pending` (boolean), `write_off_planned_date`.
   - `WRITTEN_OFF` appears only once the write-off voucher exists (accounts 7830 / 2700 / 1500).
   - `write_off_pending` = the generator already decided the invoice is bad debt, but the voucher is not booked yet; the
     invoice is shown as `OVERDUE` until `write_off_planned_date` (today: order 1761, planned 2026-12-23).
   - The raw column `orders.status` is the generator's internal intent (it says WRITTEN_OFF from the day the order is
     created). **It must not be used as the invoice status anywhere in the dashboard.** Join `v_invoice_status` on `order_id`.
   - Counts on 2026-11-17: PAID 1864, OPEN 57, OVERDUE 8, WRITTEN_OFF 8.
2. **COGS is owed to six suppliers, not two** (accounts 4291 and 4292, three suppliers each): Microsoft Norge AS, Crayon Group
   AS, SoftwareOne AS (4291); Ingram Micro AS, Atea AS, Proact IT Norge AS (4292). The largest, Ingram Micro, carries about
   33 % of the COGS. Monthly net COGS per account and every other cost are unchanged. Each supplier has its own accrual
   voucher and payable, so there are 3 COGS vouchers per account per month (552 rows in `cogs_payables` now).
3. **COGS payments are now regular**: the due date is the last working day of the month after the accrual, so there is
   exactly one payment per supplier per month (6 per month, about 2.9 mln NOK gross in total). The earlier "jumping" cash
   outflows (0 one month, double the next) are gone.
4. **Voucher numbers changed.** `voucher_number` equals `vouchers.id`; because COGS vouchers are split, the ids of every
   voucher from the first COGS accrual (2019) onwards were renumbered. Voucher count is 7 263 (was 6 526). Anything that
   stores or links voucher numbers (bookmarks, saved filters, drill-down links) must be re-checked.
5. Unchanged and still valid: `v_pl_monthly.is_partial` (use `WHERE NOT is_partial` for yearly / YTD / trailing figures), the
   owner loan (account 2290, repaid in 2025-12), interest on 8150 deliberately outside the operating result, write-offs on
   7830.

## Step A: invoice status from `v_invoice_status` (most important)

1. List every query and page that reads an invoice status: Receivables (donut, ageing, top lists, write-offs per month),
   Today ("Invoice & payment status" table), Clients (client profile), anywhere `orders.status` or a status derived from
   it is used. Show me the list first.
2. Replace them with a join to `v_invoice_status`. For the Receivables page keep the current look and numbers: outstanding
   = OPEN + OVERDUE (gross, incl. VAT), written off = sum over WRITTEN_OFF, paid late = count of `paid_late`.
3. Add a small, translated note where it helps: invoices with `write_off_pending` stay "Overdue" and will be written off on
   `write_off_planned_date`. A tooltip or a footnote under the Overdue figure is enough; show the planned date.
4. Verify: Paid 1864, Open 57, Overdue 8, Written off 8 (sum 1937); written-off net equals the 7830 total in the ledger
   (the two figures on the page must reconcile to the cent: net 7830 from the GL and net of the WRITTEN_OFF invoices).

## Step B: suppliers and COGS

1. The suppliers view should take suppliers from the COGS data (it already does if it reads `cogs_payables` / `suppliers`);
   check that it shows all six COGS suppliers plus the original eight invoice suppliers (13 suppliers in total) and that
   nothing is hard-coded to two suppliers.
2. If there is a supplier concentration view or a top-suppliers chart, make sure the largest share is about 33 % (Ingram
   Micro) and sums to 100 %. If there is none, add one small chart "COGS by supplier" (share of net COGS, all years) on
   Operations → Suppliers. Do not invent supplier attributes: names come from `suppliers.name`.
3. The Liquidity tab's COGS payables table now has three rows per account and month; make sure it still reads well (group
   or filter by supplier if it became too long, keep sorting by accrual date).

## Step C: cash flow and voucher numbers

1. Operations → Cash flow: after the generator change the outgoing line is steady. Check the chart still marks the month in
   progress (2026-11) with the same grey band and footnote as the other charts; fix it if the previous fix missed it.
2. Search for anything that uses `voucher_number` as a stable identifier (deep links, URL parameters, cached lookups) and
   either clear the cache / links or tell me where it persists.

## Step D (optional, only after A–C are reviewed)

- On Receivables, add a "Pending write-off" mini table (`write_off_pending` invoices with customer, amount, due date and
  `write_off_planned_date`).

## Definition of done

For each step: a short description of the change, a screenshot of every changed page (EN and one other language), and the
proposed English commit message. Reference values (2026-11-17, must not change because of these fixes): bank balance min
893 255.52 NOK on 2019-10-01, VAT to pay 761 833.30 NOK (2026-T5, due 2026-12-10), unpaid COGS payables 2 916 645.87 NOK,
vouchers 7 263, orders 1 937, written-off net (7830) 1 396 006.90 NOK.

# Dashboard fixes 1–4 (Streamlit, norfingen-analytics)

Paste everything below the line into a Claude Code session opened in the **dashboard repo** (not in the generator repo).

---

## Task

Fix four issues found in the live dashboard https://norfingen-analytics.streamlit.app/ on 2026-11-16. Work one fix at a
time and stop after each so I can review. Do not run git commands, only propose them (commit messages fully in English,
no `Co-Authored-By` trailer). Never print the database URL or any token. Read-only access to the data is enough; do not
modify the generator or the database. Keep the existing style, language switch (EN/PL/NO) and dark mode working: every
new text must be added to all three languages.

Facts about the data you need:
- `v_pl_monthly` has `month` (YYYY-MM) and `is_partial` (TRUE for the month that is not over yet). Payroll and COGS are
  booked at month end, so a month in progress shows revenue without its costs.
- Aggregates over time (YTD, last N months, any date range) must only use full months (`NOT is_partial`).
- The owner loan (account 2290) was fully repaid in the last instalment of 2025-12; outstanding is 0 from 2026-01 on.

## Fix 1 — Time Analysis: the date range cuts a month in half (most important)

Problem: the default range is 2025-11-16 → 2026-11-16. Revenue of Nov 2025 is counted only from the 16th (≈0.5M), but the
costs booked at month end (payroll, COGS) land inside the range in full (≈-3M). Result: 12-month profit shows
-1 640 631 kr, while the real trailing-12-month result (last 12 full months, 2025-11 … 2026-10) has a positive margin
of ≈3.06%.

What to do:
1. For the profit, cost and margin measures, snap the range to whole months: start = first day of the start month, end =
   last day of the last FULL month (exclude `is_partial`). Show a visible note under the KPI: "Range aligned to full
   months: YYYY-MM … YYYY-MM" (translated).
2. Keep the date picker as is, but the revenue-only views may still use the exact dates if the user explicitly picked a
   custom range; in that case, if the range does not start on the 1st or does not end on a month end, show a warning
   that profit/margin for partial months are not meaningful.
3. Add a test or at least a manual check: the default "last 12 months" KPI must match `GET /pl/trailing-12m` from
   https://norfingen-analytics.streamlit.app's backend API (`https://norfingen-api.fly.dev/pl/trailing-12m`, fields
   `revenue`, `operating_result`, `margin_pct`) within rounding. Note: the dashboard's profit includes more than
   `operating_result` if it already subtracts financial items, so first state which definition each one uses and make
   the labels unambiguous.

## Fix 2 — Overview: empty "Coverage" panel

Problem: on the Overview tab, next to "History", the "Coverage" panel renders as an empty white box.

What to do:
1. Find the code for that panel and reproduce the problem locally (run the app, open Overview, "All years").
2. Determine whether it is a missing data query, an exception swallowed by a `try/except`, or a chart with no traces.
3. Fix it. If the panel has no meaningful content any more, remove it and let "History" use the full width instead. Say
   which you chose and why.

## Fix 3 — Operations → Cash flow: month in progress is not marked

Problem: the "Cash flow" sub-tab (Operations) draws the current, unfinished month (2026-11) as a normal point. Incoming
drops to ≈2.5M and Outgoing drops to ≈0, which looks like a collapse. The other charts already show a grey band
"month in progress".

What to do:
1. Reuse the same "month in progress" band/label component that the Time Analysis and VAT charts use (do not write a new
   one).
2. Add the same footnote used elsewhere ("month in progress, not final").
3. Optional: draw the line of that last month dashed instead of solid, if the chart library allows it simply.

## Fix 4 — Liquidity: KPI "Owner loan outstanding 0 kr" says nothing

Problem: the KPI card on the Liquidity tab shows "OWNER LOAN OUTSTANDING 0 kr". After the loan was repaid (2025-12) this is
uninformative.

What to do:
1. When the current outstanding principal is 0, show the status "Repaid" (translated: EN "Repaid", PL "Spłacona",
   NO "Nedbetalt") with the sub-line "last instalment YYYY-MM" taken from the data (the last month with a principal
   repayment, not hard-coded).
2. When it is greater than 0 (for example if the model changes), keep showing the amount as before.

## Definition of done

- For each fix: a short description of the change, a screenshot of the changed page in EN and one in another language,
  and the proposed English commit message.
- Reference values to check (as of 2026-11-16): bank balance 7 984 433 kr, lowest balance 893 256 kr on 2019-10-01,
  VAT to pay 761 833 kr (2026-T5, due 2026-12-10), unpaid COGS payables 2 916 646 kr, receivables outstanding
  7 385 783 kr. None of these may change because of these fixes.

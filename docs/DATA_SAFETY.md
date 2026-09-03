# NorFinGen — Data Safety

Ten dokument opisuje decyzje dotyczące realizmu vs bezpieczeństwa nazw firm użytych w generatorze — dwie różne, celowo ODWROTNE logiki dla klientów i dostawców, wynikające z jednej, nadrzędnej zasady poniżej.

## Core rule: direction of the simulated relationship determines what can be real

- **The simulated company itself (sender)** — always fictional, never a real registered entity
- **Suppliers (money flows FROM the simulated company TO them)** — MAY be real, named, registered companies (e.g. Microsoft Norge AS, Telenor Norge AS). Being one vendor among many customers is a neutral, public fact and does not misattribute financial results to that company.
- **Customers/clients (money flows FROM them TO the simulated company)** — MUST always be fictional. A named, real, identifiable company must never be shown "generating" specific fictional revenue, margin, or payment history — that constitutes attributing invented financial results to a real legal entity.
- **Location and industry metadata (city, postal code, NACE code) for customers** — MAY reflect real, plausible Norwegian geography/industry data, since this describes a place or sector, not a named entity's finances.

This rule applies to every future extension of the project (new industries, new templates, external API access) without needing to be re-decided each time.

## Customer authenticity

Klienci (`roster.CUSTOMERS`, K01-K52) to w pełni fikcyjne firmy — kolizja z nazwą realnej norweskiej firmy byłaby niepożądana (fikcyjny klient nie powinien przypadkowo "być" realną firmą). Zob. też: nazwa własnej symulowanej firmy NorFinGen sama w sobie **nie ma nadanej nazwy** nigdzie w projekcie (ani `roster.py`, ani `docs/DATA_DICTIONARY.md`, ani `raport-site`) — więc nie ma tu żadnej kolizji do sprawdzenia, świadomie i celowo (2026-09, przy okazji audytu dostawców poniżej).

## Supplier authenticity

Suppliers in this simulation are checked against the public Brønnøysundregistrene registry (`data.brreg.no`). Where a supplier name matches a real, large, well-known Norwegian company (e.g. Microsoft Norge AS, Telenor Norge AS), this is intentional — the simulation assumes the fictional company purchases services from real, publicly known vendors, which is standard practice in financial simulations. Smaller/local suppliers may be entirely fictional. See `scripts/audit_supplier_names.py`.

**Note the logic here is the OPPOSITE of customers**: for customers, a collision with a real company is a risk to avoid; for suppliers, a collision with a real, well-known company is the desired, more-realistic outcome.

### Audit result (2026-09, `scripts/audit_supplier_names.py` against data.brreg.no)

| # | Supplier | Result | Action |
|---|---|---|---|
| L01 | Microsoft Norge AS | Exact match, org.nr 957485030 | None — confirmed real |
| L02 | Telenor Norge AS | Exact match, org.nr 976967631 | None — confirmed real |
| L03 | Reitan Convenience AS | Exact match, org.nr 983415652 | None — confirmed real |
| L04 | Statsbygg | Exact match, org.nr 971278374 | None — confirmed real |
| L05 | Sandvik IT Solutions AS | Only a small, unrelated real entity found ("SANDVIK IT", Fister) — not the global Sandvik AB brand | Kept fictional (user decision) — matching would not add brand-recognition realism |
| L06 | ~~Advokatfirma Thommessen~~ → **Advokatfirmaet Thommessen AS** | Typo found (missing "et") — real, well-known Norwegian law firm, org.nr 957423248 | **Renamed** to exact legal form |
| L07 | Avis Norge AS | Inconclusive — Brreg's `navn` search matches thousands of entities containing the common Norwegian word "avis" (newspaper), making exact confirmation unreliable via this method | Kept as-is (user decision) — Avis is a recognizable global brand regardless of exact local legal-entity confirmation |
| L08 | ~~Nordic Insurance Partners AS~~ → **Gjensidige Forsikring ASA** | Fully fictional, no match found | **Replaced** with a real, recognizable Norwegian insurer, org.nr 995568217 (user decision) |

Confirmed real-entity org numbers are stored informationally in `roster.SupplierSeed.real_org_number` (Python) and `suppliers.organization_number` (Supabase, existing Tripletex-schema column — no new column needed). **Purely informational — does not affect any pricing, COGS, or financial logic** (Zadanie 1c requirement, verified: no changes to `amount_min`/`amount_max`/`gl_account`/`capitalization_*` for any supplier).

### Known limitation

`scripts/audit_name_collisions.py` (klienci) referenced in the originating prompt as "from a previous session" does not exist in this repository — no trace in git history or `SESSION_HANDOFF.md`. Not created here (out of scope for this session — this session covers suppliers only, per the prompt's own Zadanie 1/2 split). If a client-side collision audit is wanted, it would need its own session/prompt.

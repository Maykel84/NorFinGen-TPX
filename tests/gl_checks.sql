-- =====================================================================
-- NorFinGen: testy akceptacyjne księgowania (PostgreSQL / DuckDB)
-- Tabele = eksporty: gl (Postingi_GL), sales (Faktury_sprzedazy),
--   purch (Faktury_zakupu), cogs (Zobowiazania_COGS, faza 4), pay (Payroll_per_pracownik)
-- Każdy test zwraca 0 wierszy = PASS (chyba że opis mówi inaczej).
-- Założenie: kwoty Wn dodatnie, Ma ujemne (jak w obecnym eksporcie).
-- =====================================================================

-- T1: cała księga bilansuje się do zera (PASS = 0 wierszy)
SELECT 'T1' AS test, ROUND(SUM(amount), 2) AS diff
FROM gl
HAVING ABS(SUM(amount)) > 0.01;

-- T2: każdy dokument bilansuje się do zera (wymaga voucher_number z fazy 6)
SELECT 'T2' AS test, voucher_number, ROUND(SUM(amount), 2) AS diff
FROM gl
GROUP BY voucher_number
HAVING ABS(SUM(amount)) > 0.01;

-- T3: saldo należności 1500 >= 0 i równe sumie nieopłaconych faktur brutto
--     (porównaj ręcznie z listą faktur z flagą zaległości)
SELECT 'T3' AS test, ROUND(SUM(amount), 2) AS saldo_1500
FROM gl
WHERE account_number = 1500
HAVING SUM(amount) < -0.01;

-- T4: przychód w GL (konta 3xxx) = przychód z faktur, per miesiąc
WITH g AS (
    SELECT EXTRACT(YEAR FROM date) * 100 + EXTRACT(MONTH FROM date) AS ym, -SUM(amount) AS rev_gl
    FROM gl WHERE account_number BETWEEN 3000 AND 3999 GROUP BY 1
), s AS (
    SELECT EXTRACT(YEAR FROM invoice_date) * 100 + EXTRACT(MONTH FROM invoice_date) AS ym,
           SUM(amount_excluding_vat_currency) AS rev_inv
    FROM sales GROUP BY 1
)
SELECT 'T4' AS test, COALESCE(g.ym, s.ym) AS ym, g.rev_gl, s.rev_inv
FROM g FULL JOIN s ON g.ym = s.ym
WHERE ABS(COALESCE(g.rev_gl, 0) - COALESCE(s.rev_inv, 0)) > 1;

-- T5: VAT należny (Ma 2700) = 25% przychodu 3xxx
SELECT 'T5' AS test,
       ROUND(-SUM(CASE WHEN account_number = 2700 AND amount < 0 THEN amount END), 2) AS vat_out,
       ROUND(-SUM(CASE WHEN account_number BETWEEN 3000 AND 3999 THEN amount END) * 0.25, 2) AS expected
FROM gl
HAVING SUM(CASE WHEN account_number BETWEEN 3000 AND 3999 THEN amount END) IS NULL  -- brak przychodu w GL = FAIL
    OR ABS(-SUM(CASE WHEN account_number = 2700 AND amount < 0 THEN amount END)
          + SUM(CASE WHEN account_number BETWEEN 3000 AND 3999 THEN amount END) * 0.25)
       > 0.01 * (SELECT COUNT(*) FROM gl WHERE account_number = 2700 AND amount < 0);
-- (Faza 3: tolerancja zmieniona z 1 NOK na 1 grosz PER FAKTURA. VAT każdej faktury to 25% jej netto z dokładnością do grosza,
--  bo linie są zaokrąglane po jednej: na 1853 faktur do 2026-09-30 1167 jest dokładnych, 531 ma +0,01, 155 ma -0,01, razem 3,16 NOK.
--  Żadne księgowanie wierne fakturom nie zmieści się w 1 NOK na 213 mln przychodu; oryginał z progiem 1 NOK
--  kończyłby się FAIL na poprawnych danych.)

-- T6: VAT naliczony (Wn 2710) = suma VAT z faktur zakupu
SELECT 'T6' AS test,
       (SELECT ROUND(SUM(amount), 2) FROM gl WHERE account_number = 2710 AND amount > 0) AS vat_in_gl,
       (SELECT ROUND(SUM(vat_amount_currency), 2) FROM purch) AS vat_in_invoices
WHERE ABS(COALESCE((SELECT SUM(amount) FROM gl WHERE account_number = 2710 AND amount > 0), 0)
        - COALESCE((SELECT SUM(vat_amount_currency) FROM purch), 0)) > 1;
-- (COALESCE added in phase 0.5a: without it an empty side makes the WHERE NULL and the test passes vacuously.)

-- T7: żadnych postingów płacowych na kontach VAT
SELECT 'T7' AS test, account_number, COUNT(*) AS n
FROM gl
WHERE voucher_type = 'SALARY' AND account_number IN (2700, 2710, 2740)
GROUP BY account_number;

-- T8: saldo dostawców 2400 = minus suma nieopłaconych zobowiązań wobec dostawców (brutto):
--     nieopłacone faktury zakupu (purch) + nieopłacone zobowiązania COGS (cogs, wariant B z SPEC; status UNPAID = flaga).
--     Zobowiązania COGS (konta 4291/4292) nie mają faktury zakupu, więc bez arkusza cogs saldo 2400 nie dałoby się uzgodnić.
SELECT 'T8' AS test, ROUND(SUM(amount), 2) AS saldo_2400,
       -(SELECT ROUND(COALESCE(SUM(amount_currency), 0), 2) FROM purch WHERE status = 'UNPAID')
       -(SELECT ROUND(COALESCE(SUM(amount_currency), 0), 2) FROM cogs WHERE status = 'UNPAID') AS expected
FROM gl
WHERE account_number = 2400
HAVING ABS(SUM(amount)
         + COALESCE((SELECT SUM(amount_currency) FROM purch WHERE status = 'UNPAID'), 0)
         + COALESCE((SELECT SUM(amount_currency) FROM cogs WHERE status = 'UNPAID'), 0)) > 1;
-- (COALESCE dodane w fazie 0.5a: gdy żadna faktura nie jest UNPAID, podzapytanie jest NULL, HAVING staje się NULL i oryginalny
--  test przechodził pozornie nawet przy 88 mln NOK niezapłaconego COGS na 2400. Faza 4: dodany arkusz cogs.)

-- T9: REGRESJA ŚWIADOMEGO ZAŁOŻENIA — w każdym czerwcu od 2020 r. feriepenger są
--     wypłacane z rezerwy 2940 (Wn). Pensja (5000) w czerwcu może wystąpić tylko u osób
--     bez pełnej rezerwy (nowi pracownicy, np. 2019–2023) — to poprawne, nie zmieniać.
--     PASS = 0 wierszy (każdy rok ma wypłatę z 2940).
WITH lata AS (SELECT DISTINCT EXTRACT(YEAR FROM date) AS rok FROM gl WHERE EXTRACT(YEAR FROM date) >= 2020 AND EXTRACT(MONTH FROM date) >= 7
              UNION SELECT DISTINCT EXTRACT(YEAR FROM date) FROM gl WHERE EXTRACT(MONTH FROM date) = 6 AND EXTRACT(YEAR FROM date) >= 2020),
     wyplaty AS (SELECT EXTRACT(YEAR FROM date) AS rok, SUM(amount) AS wn_2940
                 FROM gl WHERE account_number = 2940 AND EXTRACT(MONTH FROM date) = 6 AND amount > 0 GROUP BY 1)
SELECT 'T9' AS test, l.rok
FROM lata l LEFT JOIN wyplaty w ON l.rok = w.rok
WHERE COALESCE(w.wn_2940, 0) <= 0;

-- T10: bieżący miesiąc — koszty istnieją dla dni, które minęły
--      (opcja A) LUB miesiąc ma status 'open' (opcja B). Wersja dla opcji A:
SELECT 'T10' AS test, MAX(date) AS ostatni_koszt
FROM gl
WHERE (account_number BETWEEN 4000 AND 4999 OR account_number BETWEEN 6000 AND 7999)
HAVING COALESCE(MAX(date), DATE '1900-01-01') < (SELECT MAX(date) FROM gl) - INTERVAL '7 days';

-- T11: typy i puste kolumny
SELECT 'T11' AS test, 'purch.postal_code w 100% pusta' AS problem
WHERE (SELECT COUNT(postal_code) FROM purch) = 0
UNION ALL
SELECT 'T11', 'gl.employee_id w 100% pusta (SALARY)'
WHERE (SELECT COUNT(employee_id) FROM gl WHERE voucher_type = 'SALARY') = 0;

-- REGRESJA (faza 0.5a; reguła z decyzji (c) w SPEC, zastępuje pierwotne 211 624 547 na 2026-10-30,
-- które nie uwzględniało faktur weekendowych gubionych przez przebieg dzienny).
-- PASS = 0 wierszy.
--
-- REG_A: historia do 2026-09-30 jest NIEZMIENIONA. Przychód bez MVA = 209 030 662 NOK.
SELECT 'REG_A' AS test, ROUND(SUM(amount_excluding_vat_currency), 0) AS przychod
FROM sales
WHERE invoice_date <= DATE '2026-09-30'
HAVING ABS(SUM(amount_excluding_vat_currency) - 209030662) > 1;

-- REG_C: brutto płac (typy 100 Fast lønn + 260 Feriepenger) do 2026-09-30 = 81 422 455 NOK.
SELECT 'REG_C' AS test, ROUND(SUM(gross_amount), 0) AS brutto_plac
FROM pay
WHERE date <= DATE '2026-09-30'
HAVING ABS(SUM(gross_amount) - 81422455) > 1;

-- REG_B: przychód do 2026-10-30 = 213 117 314,34 NOK. Składa się z:
--   211 624 546,65  przychód w produkcji przed poprawkami (ten sam co 211 624 547 po zaokrągleniu)
--   +  1 359 615,08 13 faktur subskrypcyjnych z weekendowym invoice_day (3,4,10,11,17,18,24.10), gubionych przez przebieg dzienny
--   +    133 152,61 4 zamówienia extra consulting z niedzieli 25.10 (K02, K07, K16, K32), których ścieżka dzienna nie tworzyła wcale
--   = 213 117 314,34 (łącznie 17 zamówień, +1 492 767,69). K12 bez faktury (bankructwo).
SELECT 'REG_B' AS test, ROUND(SUM(amount_excluding_vat_currency), 2) AS przychod
FROM sales
WHERE invoice_date <= DATE '2026-10-30'
HAVING ABS(SUM(amount_excluding_vat_currency) - 213117314.34) > 1;

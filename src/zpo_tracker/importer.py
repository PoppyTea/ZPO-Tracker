"""
Logika importu danych kurier/ZPO do SQLite.
Zasady wynikające z analizy realnego pliku (2026-08-07-snapshot-ZPO):
  - PNI ZPO jest wiarygodnym kluczem punktu; różnica w adresie przy tym
    samym PNI generuje ostrzeżenie, nie blokadę (adres kanoniczny = pierwszy zapisany)
  - klienci bez PNI są deduplikowani po parze (nadawca, adres)
  - wiersze bez daty są pomijane (puste/szablonowe wiersze w arkuszu źródłowym)
  - duplikat (data, kurier, punkt) jest pomijany z ostrzeżeniem, nie crashuje importu
"""
from datetime import date


def parse_quantity(value):
    """Zamienia wartość komórki na int albo None. Obsługuje spację jako pusty wpis."""
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if value == "":
            return None
        return int(value)
    return int(value)


def get_or_create_kurier(conn, imie_nazwisko):
    row = conn.execute(
        "SELECT id FROM kurierzy WHERE imie_nazwisko = ?", (imie_nazwisko,)
    ).fetchone()
    if row:
        return row[0]
    cur = conn.execute(
        "INSERT INTO kurierzy (imie_nazwisko) VALUES (?)", (imie_nazwisko,)
    )
    return cur.lastrowid


def get_or_create_rejon(conn, kod):
    if not kod:
        return None
    row = conn.execute("SELECT id FROM rejony WHERE kod = ?", (kod,)).fetchone()
    if row:
        return row[0]
    cur = conn.execute("INSERT INTO rejony (kod) VALUES (?)", (kod,))
    return cur.lastrowid


def get_or_create_wykonawca(conn, nazwa):
    if not nazwa:
        return None
    row = conn.execute("SELECT id FROM wykonawcy WHERE nazwa = ?", (nazwa,)).fetchone()
    if row:
        return row[0]
    cur = conn.execute("INSERT INTO wykonawcy (nazwa) VALUES (?)", (nazwa,))
    return cur.lastrowid


def get_or_create_punkt(conn, nadawca, adres, pni_zpo):
    """
    Zwraca (punkt_id, lista_ostrzezen).
    Dla punktow z PNI: PNI jest kluczem, adres kanoniczny to ten zapisany
    przy pierwszym utworzeniu punktu - kolejne rozne adresy tylko ostrzegaja.
    Dla zwyklych klientow (PNI=None): deduplikacja po (nadawca, adres).
    """
    warnings = []
    if pni_zpo:
        row = conn.execute(
            "SELECT id, adres FROM punkty WHERE pni_zpo = ?", (pni_zpo,)
        ).fetchone()
        if row:
            punkt_id, stored_adres = row
            if stored_adres != adres:
                warnings.append(
                    f"PNI ZPO {pni_zpo} był już zarejestrowany pod adresem "
                    f"'{stored_adres}', teraz podano '{adres}' - zignorowano nowy adres."
                )
            return punkt_id, warnings
        cur = conn.execute(
            "INSERT INTO punkty (nadawca, adres, pni_zpo) VALUES (?, ?, ?)",
            (nadawca, adres, pni_zpo),
        )
        return cur.lastrowid, warnings
    else:
        row = conn.execute(
            "SELECT id FROM punkty WHERE nadawca = ? AND adres = ? AND pni_zpo IS NULL",
            (nadawca, adres),
        ).fetchone()
        if row:
            return row[0], warnings
        cur = conn.execute(
            "INSERT INTO punkty (nadawca, adres, pni_zpo) VALUES (?, ?, NULL)",
            (nadawca, adres),
        )
        return cur.lastrowid, warnings


def import_row(conn, row):
    """
    Importuje pojedynczy wiersz (dict z kluczami = nazwy kolumn z xlsx).
    Zwraca dict: {"skipped": bool, "reason": str | None, "warnings": list[str]}
    """
    data_val = row.get("data")
    if not data_val:
        return {"skipped": True, "reason": "brak daty", "warnings": []}

    kurier_nazwa = row.get("Kurier")
    if not kurier_nazwa:
        return {"skipped": True, "reason": "brak kuriera (pusty wiersz)", "warnings": []}

    if hasattr(data_val, "date"):
        data_val = data_val.date()
    elif isinstance(data_val, str):
        data_val = date.fromisoformat(data_val)

    nadawca = row.get(" Pełna Nazwa Nadawcy")
    adres = row.get("Adres odbioru dla wszystkich nadawców")
    rejon_kod = row.get("Rejon")
    wykonawca_nazwa = row.get("Wykonawca")
    pni = row.get("PNI ZPO")
    if pni is not None:
        pni = str(pni).strip() or None

    kurier_id = get_or_create_kurier(conn, kurier_nazwa)
    rejon_id = get_or_create_rejon(conn, rejon_kod)
    wykonawca_id = get_or_create_wykonawca(conn, wykonawca_nazwa)
    punkt_id, warnings = get_or_create_punkt(conn, nadawca, adres, pni)

    ilosc_total = parse_quantity(row.get(" Wpisujemy łączną liczbę odebranych Pocztexów"))
    ilosc_zpo = parse_quantity(
        row.get(" Wpisujemy   w tym liczbę z Zewnetrznych Punktów Odbiorów ")
    )

    try:
        conn.execute(
            """INSERT INTO transakcje
               (data, kurier_id, punkt_id, rejon_id, wykonawca_id, ilosc_total, ilosc_zpo)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (data_val.isoformat(), kurier_id, punkt_id, rejon_id, wykonawca_id,
             ilosc_total, ilosc_zpo),
        )
    except conn.IntegrityError:
        return {
            "skipped": True,
            "reason": "duplikat (ta sama data+kurier+punkt już istnieje)",
            "warnings": warnings,
        }

    return {"skipped": False, "reason": None, "warnings": warnings}

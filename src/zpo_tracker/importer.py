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

from zpo_tracker.normalizacja import normalizuj_rejon


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
    """
    Nigdy nie zwraca None - pusty/śmieciowy kod normalizuje się do
    kanonicznego wpisu REJON_NIEZNANY ("???"), więc podgląd i eksport
    zawsze mają CO pokazać zamiast pustej komórki (normalizacja.py).
    """
    kod = normalizuj_rejon(kod)
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


def get_or_create_firma_zpo(conn, nazwa):
    if not nazwa:
        return None
    row = conn.execute("SELECT id FROM firmy_zpo WHERE nazwa = ?", (nazwa,)).fetchone()
    if row:
        return row[0]
    cur = conn.execute("INSERT INTO firmy_zpo (nazwa) VALUES (?)", (nazwa,))
    return cur.lastrowid


def get_or_create_punkt(conn, nadawca, adres, pni_zpo):
    """
    Zwraca (punkt_id, lista_ostrzezen).
    Dla punktow z PNI: PNI jest kluczem, adres kanoniczny to ten zapisany
    przy pierwszym utworzeniu punktu - kolejne rozne adresy tylko ostrzegaja.
    Nadawca punktu z PNI to nazwa sieci (Żabka/Duży Ben/Groszek/...) i trafia
    dodatkowo do słownika firmy_zpo.
    Dla zwyklych klientow (PNI=None): deduplikacja po (nadawca, adres).
    """
    warnings = []
    if pni_zpo:
        # get_or_create_firma_zpo MUSI być za tym SELECT-em: wołane wcześniej
        # zakładało wpis w firmy_zpo także wtedy, gdy punkt już istniał pod
        # inną pisownią sieci - a wtedy jego id było wyrzucane i zostawał
        # osierocony wpis w słowniku, którego nie referencuje żaden punkt.
        row = conn.execute(
            "SELECT id, adres, nadawca FROM punkty WHERE pni_zpo = ?", (pni_zpo,)
        ).fetchone()
        if row:
            punkt_id, stored_adres, stored_nadawca = row
            if stored_adres != adres:
                warnings.append(
                    f"PNI ZPO {pni_zpo} był już zarejestrowany pod adresem "
                    f"'{stored_adres}', teraz podano '{adres}' - zignorowano nowy adres."
                )
            if stored_nadawca != nadawca:
                # ta sama klasa problemu co rozjazd adresu wyżej: PNI jest
                # kluczem, więc nazwa sieci ze źródła jest ignorowana - ale
                # człowiek musi się o tym dowiedzieć
                warnings.append(
                    f"PNI ZPO {pni_zpo} był już zarejestrowany dla nadawcy "
                    f"'{stored_nadawca}', teraz podano '{nadawca}' - zignorowano nowego nadawcę."
                )
            return punkt_id, warnings
        firma_zpo_id = get_or_create_firma_zpo(conn, nadawca)
        cur = conn.execute(
            "INSERT INTO punkty (nadawca, adres, pni_zpo, firma_zpo_id) VALUES (?, ?, ?, ?)",
            (nadawca, adres, pni_zpo, firma_zpo_id),
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


def znajdz_lub_utworz_punkt_niezaufany(conn, nadawca, adres):
    """
    Punkt dla wiersza z NIEZAUFANEGO pliku (0.1-alpha.3.2): kluczem jest
    wyłącznie (nadawca, adres), bo PNI z takiego źródła jest odrzucane
    w całości (patrz import_orchestrator.zaimportuj).

    OSOBNA funkcja, nie flaga w `get_or_create_punkt`: tamta obsługuje
    ścieżkę zaufaną ORAZ scalanie baz (scalanie.py, gdzie źródłem jest
    nasza własna baza), a jej semantyka nie może dryfować razem z regułami
    zaufania importu.

    Trzy gałęzie, w tej kolejności:

    1. dokładne (nadawca, adres) po DOWOLNYM punkcie - także takim, który
       MA już PNI. To rozwiązuje pułapkę predykatu `AND pni_zpo IS NULL`
       z `get_or_create_punkt`: bez tego wiersz o adresie znanym nam już
       jako punkt ZPO tworzyłby drugi punkt tej samej fizycznej lokalizacji.
    2. dokładnie JEDEN punkt pod tym adresem, choć nadawca się nie zgadza -
       podpinamy się do niego, ale człowiek musi się dowiedzieć (najczęściej
       to inna pisownia tej samej firmy).
    3. wiele punktów pod adresem i żaden nie pasuje nadawcą - NOWY punkt bez
       PNI + ostrzeżenie. Świadomie NIE wybieramy żadnego z istniejących:
       reguła projektu mówi, że adres z wieloma nadawcami nigdy nie
       rozstrzyga się sam (dedukcja.py), a duplikat punktu jest naprawialny
       (Słowniki/scalanie), ciche podpięcie pod zły punkt - nie.
    """
    ostrzezenia = []
    dokladny = conn.execute(
        "SELECT id FROM punkty WHERE nadawca = ? AND adres = ?", (nadawca, adres)
    ).fetchone()
    if dokladny:
        return dokladny[0], ostrzezenia

    pod_adresem = conn.execute(
        "SELECT id, nadawca FROM punkty WHERE adres = ?", (adres,)
    ).fetchall()
    if len(pod_adresem) == 1:
        ostrzezenia.append(
            f"Adres '{adres}' jest już zapisany dla nadawcy "
            f"'{pod_adresem[0][1]}', a plik podaje '{nadawca}' - podpięto do "
            f"istniejącego punktu, sprawdź, czy to ta sama firma."
        )
        return pod_adresem[0][0], ostrzezenia
    if len(pod_adresem) > 1:
        ostrzezenia.append(
            f"Pod adresem '{adres}' istnieje już {len(pod_adresem)} punktów, "
            f"żaden dla nadawcy '{nadawca}' - utworzono nowy punkt zamiast "
            f"zgadywać, do którego podpiąć."
        )

    cur = conn.execute(
        "INSERT INTO punkty (nadawca, adres, pni_zpo) VALUES (?, ?, NULL)",
        (nadawca, adres),
    )
    return cur.lastrowid, ostrzezenia


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

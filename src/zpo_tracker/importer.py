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

from zpo_tracker import adresy as adresy_modul
from zpo_tracker import dedukcja_miejscowosci
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


def get_or_create_nadawca(conn, nazwa, liczy_zpo=False):
    """
    Nadawca - sieciówka i zwykły klient w JEDNEJ tabeli (schema.sql v4).

    `liczy_zpo` jest wyłącznie PODNOSZONE, nigdy opuszczane. Flaga mówi, czy
    dla tego nadawcy wypełnia się kolumnę "w tym ZPO", a jeden wiersz bez PNI
    nie jest dowodem, że nadawca przestał być punktem ZPO - PNI bardzo często
    po prostu jeszcze nie znamy. Zgaszenie flagi wygasza pole w formularzu,
    czego użytkownik nie ma jak zauważyć; flaga zapalona omyłkowo jest
    widoczna i naprawialna w Słownikach.
    """
    row = conn.execute(
        "SELECT id, liczy_zpo FROM nadawcy WHERE nazwa = ?", (nazwa,)
    ).fetchone()
    if row:
        if liczy_zpo and not row[1]:
            conn.execute("UPDATE nadawcy SET liczy_zpo = 1 WHERE id = ?", (row[0],))
        return row[0]
    cur = conn.execute(
        "INSERT INTO nadawcy (nazwa, liczy_zpo) VALUES (?, ?)",
        (nazwa, 1 if liczy_zpo else 0),
    )
    return cur.lastrowid


def get_or_create_miejscowosc(conn, nazwa, gmina=None):
    """
    Miejscowość w postaci, w jakiej ją zapisano ("Warszawa (Śródmieście)").

    Wołane WYŁĄCZNIE ze ścieżki, która ma miejscowość ROZSTRZYGNIĘTĄ - patrz
    ostrzeżenie w `get_or_create_adres`. Nie ma tu żadnego zgadywania i nie
    wolno go tu dołożyć.
    """
    row = conn.execute("SELECT id FROM miejscowosci WHERE nazwa = ?", (nazwa,)).fetchone()
    if row:
        return row[0]
    cur = conn.execute(
        "INSERT INTO miejscowosci (nazwa, gmina) VALUES (?, ?)", (nazwa, gmina))
    return cur.lastrowid


def get_or_create_ulica(conn, nazwa, miejscowosc_id, typ=None):
    """
    UNIQUE jest na (nazwa, miejscowosc_id) BEZ typu, bo ta sama ulica bywa
    zapisana raz z prefiksem, raz bez ("Aleja Kwiatowa" / "Kwiatowa") -
    gdyby typ wchodził do klucza, oba zapisy byłyby dwiema różnymi ulicami.

    Typ uzupełniamy tylko w LUKĘ: pierwszy napotkany zapis bez prefiksu nie
    może na zawsze przesądzić, że ta ulica prefiksu nie ma, ale kolejne
    warianty też nie mogą nadpisywać już ustalonego.
    """
    row = conn.execute(
        "SELECT id, typ FROM ulice WHERE nazwa = ? AND miejscowosc_id = ?",
        (nazwa, miejscowosc_id),
    ).fetchone()
    if row:
        if typ and row[1] is None:
            conn.execute("UPDATE ulice SET typ = ? WHERE id = ?", (typ, row[0]))
        return row[0]
    cur = conn.execute(
        "INSERT INTO ulice (nazwa, typ, miejscowosc_id) VALUES (?, ?, ?)",
        (nazwa, typ, miejscowosc_id),
    )
    return cur.lastrowid


def get_or_create_adres(conn, surowy, *, szukaj=None, rejon=None,
                        miejscowosci_dnia=()):
    """
    Adres jako wiersz `adresy`, get-or-create po `surowy` (UNIQUE) - to surowy
    tekst jest tożsamością adresu, struktura jest tylko jego interpretacją
    i wolno ją policzyć jeszcze raz.

    KRYTYCZNE: wpis w `miejscowosci`/`ulice` powstaje WYŁĄCZNIE dla adresu,
    który parser rozłożył (`adresy.rozbij` -> `pewnosc != PEWNOSC_BRAK`).
    Zła interpretacja adresu zakłada w słowniku byt, do którego podepną się
    potem kolejne adresy - i śmieć przestaje być usterką jednego wiersza,
    a staje się usterką słownika, sprzątaną scalaniem wpisów zamiast edycją
    pola. Adres nierozstrzygnięty zapisuje się z samym `surowy`; nic nie
    przepada, bo parser przepuści go ponownie, kiedy dorośnie do przypadku.

    Bez miejscowości nie ma też ulicy (`ulice.miejscowosc_id` NOT NULL).
    Miejscowość może pochodzić z dwóch źródeł: wprost z tekstu adresu albo
    z kaskady `dedukcja_miejscowosci`, i to KASKADA decyduje, czy jest
    dość pewna - jej reguły są ułożone malejąco po zmierzonej trafności
    właśnie po to. Gdy odmówi, adres dostaje numer budynku i lokalu (te
    nie zakładają niczego w żadnym słowniku), a `ulica_id` zostaje puste.

    `szukaj` to wstrzykiwany rejonarz (patrz `dedukcja_miejscowosci`).
    POMINIĘTY ALBO wskazujący na pustą migawkę daje zachowanie bit w bit
    takie jak przed wpięciem kaskady - stacja bez zaimportowanego
    rejonarza ma działać dokładnie tak jak przedtem, i jest to przypięte
    testem w obie strony. Ta sama zasada co przy wpinaniu rejonarza
    w `dedukcja.dedukuj_wiersz`.

    Brak adresu (None) staje się JEDNYM wierszem o pustym `surowy`, nie
    wierszem na każde wystąpienie: `punkty.adres_id` jest NOT NULL, więc
    taki wiersz i tak musi powstać, a skoro `surowy` jest UNIQUE, to
    wszystkie bezadresowe punkty zbierają się w jednym koszyku do poprawy.
    To celowe - osobny wiersz na każdy taki przypadek dawałby listę
    identycznych pustych adresów, z której nic nie wynika.
    """
    surowy = "" if surowy is None else str(surowy)
    row = conn.execute("SELECT id FROM adresy WHERE surowy = ?", (surowy,)).fetchone()
    if row:
        return row[0]

    rozbicie = adresy_modul.rozbij(surowy)
    if rozbicie.pewnosc == adresy_modul.PEWNOSC_BRAK:
        cur = conn.execute("INSERT INTO adresy (surowy) VALUES (?)", (surowy,))
        return cur.lastrowid

    # Kaskada dostaje rozbicie ZAWSZE, gdy jest czym pytać: dla adresu
    # z miejscowością zwraca ją natychmiast (i nie pyta rejonarza, żeby
    # migawka nie miała jak nadpisać tego, co podał kurier), a dla adresu
    # bez miejscowości próbuje ją domyślić. Bez tego drugiego przypadku
    # rozbicie adresu nie robi tego, po co powstało: 79% realnych adresów
    # nie niesie miasta, a `ulice.miejscowosc_id` jest NOT NULL - więc
    # cztery piąte adresów zostałoby bez struktury.
    wynik = dedukcja_miejscowosci.dedukuj(
        rozbicie, szukaj or _BEZ_REJONARZA,
        rejon=rejon, miejscowosci_dnia=miejscowosci_dnia)

    ulica_id = zrodlo_miejscowosci = None
    if wynik.rozstrzygniete:
        miejscowosc_id = get_or_create_miejscowosc(conn, wynik.miejscowosc)
        ulica_id = get_or_create_ulica(
            conn, rozbicie.ulica, miejscowosc_id, rozbicie.typ_ulicy)
        zrodlo_miejscowosci = wynik.zrodlo

    cur = conn.execute(
        """INSERT INTO adresy (surowy, ulica_id, nr_budynku, nr_lokalu, stan,
                               zrodlo_miejscowosci)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (surowy, ulica_id, rozbicie.nr_budynku, rozbicie.nr_lokalu,
         adresy_modul.STAN_SPARSOWANY, zrodlo_miejscowosci),
    )
    return cur.lastrowid


def get_or_create_punkt(conn, nadawca, adres, pni_zpo):
    """
    Zwraca (punkt_id, lista_ostrzezen).

    Dla punktów z PNI: PNI jest kluczem, adres kanoniczny to ten zapisany przy
    pierwszym utworzeniu punktu - kolejne różne adresy tylko ostrzegają.
    Nadawca takiego punktu dostaje `nadawcy.liczy_zpo = 1`: to jego kolumnę
    "w tym ZPO" się wypełnia (patrz `get_or_create_nadawca`).

    Dla zwykłych klientów (PNI=None): deduplikacja po (nadawca, adres), czyli
    dokładnie po `UNIQUE(nadawca_id, adres_id)` ze schematu.
    """
    ostrzezenia = []
    if pni_zpo:
        row = conn.execute(
            """SELECT p.id, a.surowy, n.nazwa FROM punkty p
               JOIN nadawcy n ON n.id = p.nadawca_id
               JOIN adresy a ON a.id = p.adres_id
               WHERE p.pni_zpo = ?""",
            (pni_zpo,),
        ).fetchone()
        if row:
            punkt_id, zapisany_adres, zapisany_nadawca = row[0], row[1], row[2]
            if zapisany_adres != adres:
                ostrzezenia.append(
                    f"PNI ZPO {pni_zpo} był już zarejestrowany pod adresem "
                    f"'{zapisany_adres}', teraz podano '{adres}' - zignorowano nowy adres."
                )
            if zapisany_nadawca != nadawca:
                # ta sama klasa problemu co rozjazd adresu wyżej: PNI jest
                # kluczem, więc nazwa sieci ze źródła jest ignorowana - ale
                # człowiek musi się o tym dowiedzieć
                ostrzezenia.append(
                    f"PNI ZPO {pni_zpo} był już zarejestrowany dla nadawcy "
                    f"'{zapisany_nadawca}', teraz podano '{nadawca}' - zignorowano nowego nadawcę."
                )
            return punkt_id, ostrzezenia

        nadawca_id = get_or_create_nadawca(conn, nadawca, liczy_zpo=True)
        adres_id = get_or_create_adres(conn, adres)
        # Ten sam nadawca pod tym samym adresem może już istnieć BEZ PNI:
        # PNI zdobywa się później (z paragonu), a UNIQUE(nadawca_id, adres_id)
        # mówi wprost, że to jeden i ten sam punkt. Dopisujemy więc PNI do
        # istniejącego wiersza zamiast zakładać drugi - to jest domknięcie
        # listy "liczy_zpo = 1 AND pni_zpo IS NULL" ze schematu, nie
        # przypadek brzegowy.
        istniejacy = conn.execute(
            "SELECT id, pni_zpo FROM punkty WHERE nadawca_id = ? AND adres_id = ?",
            (nadawca_id, adres_id),
        ).fetchone()
        if istniejacy:
            if istniejacy[1] is None:
                conn.execute(
                    "UPDATE punkty SET pni_zpo = ? WHERE id = ?", (pni_zpo, istniejacy[0]))
            else:
                # dwa różne PNI dla tej samej pary nadawca+adres: schemat
                # dopuszcza tam jeden punkt, więc nowego nie da się założyć,
                # a podmiana zapisanego PNI byłaby cichym nadpisaniem klucza
                ostrzezenia.append(
                    f"Punkt '{nadawca}' / '{adres}' ma już PNI ZPO {istniejacy[1]}, "
                    f"teraz podano {pni_zpo} - zignorowano nowe PNI."
                )
            return istniejacy[0], ostrzezenia

        cur = conn.execute(
            "INSERT INTO punkty (nadawca_id, adres_id, pni_zpo) VALUES (?, ?, ?)",
            (nadawca_id, adres_id, pni_zpo),
        )
        return cur.lastrowid, ostrzezenia

    nadawca_id = get_or_create_nadawca(conn, nadawca)
    adres_id = get_or_create_adres(conn, adres)
    # Bez predykatu `AND pni_zpo IS NULL`, który miała wersja v3: pod tą samą
    # parą (nadawca, adres) v4 dopuszcza JEDEN punkt, więc wiersz bez PNI
    # trafia w istniejący punkt ZPO zamiast zakładać jego bliźniaka - ta sama
    # pułapka, którą osobno obchodziło `znajdz_lub_utworz_punkt_niezaufany`.
    row = conn.execute(
        "SELECT id FROM punkty WHERE nadawca_id = ? AND adres_id = ?",
        (nadawca_id, adres_id),
    ).fetchone()
    if row:
        return row[0], ostrzezenia
    cur = conn.execute(
        "INSERT INTO punkty (nadawca_id, adres_id, pni_zpo) VALUES (?, ?, NULL)",
        (nadawca_id, adres_id),
    )
    return cur.lastrowid, ostrzezenia


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
        """SELECT p.id FROM punkty p
           JOIN nadawcy n ON n.id = p.nadawca_id
           JOIN adresy a ON a.id = p.adres_id
           WHERE n.nazwa = ? AND a.surowy = ?""",
        (nadawca, adres),
    ).fetchone()
    if dokladny:
        return dokladny[0], ostrzezenia

    pod_adresem = conn.execute(
        """SELECT p.id, n.nazwa FROM punkty p
           JOIN nadawcy n ON n.id = p.nadawca_id
           JOIN adresy a ON a.id = p.adres_id
           WHERE a.surowy = ?""",
        (adres,),
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

    # Nadawca z niezaufanego pliku NIE dostaje `liczy_zpo` - PNI z takiego
    # źródła jest odrzucane w całości, więc zapalenie flagi tutaj otwierałoby
    # pole "w tym ZPO" na podstawie danych, którym z założenia nie ufamy.
    cur = conn.execute(
        "INSERT INTO punkty (nadawca_id, adres_id, pni_zpo) VALUES (?, ?, NULL)",
        (get_or_create_nadawca(conn, nadawca), get_or_create_adres(conn, adres)),
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


def _BEZ_REJONARZA(_klucz):
    """Rejonarz, który nic nie wie. Pozwala wołać kaskadę bezwarunkowo -
    dla adresu z miejscowością i tak zwraca ona odpowiedź bez pytania
    migawki, a dla pozostałych „brak migawki" i „migawka nic nie wie"
    mają dawać ten sam wynik."""
    return ()

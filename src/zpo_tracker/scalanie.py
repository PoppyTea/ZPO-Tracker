"""
Ręczne scalanie dwóch baz: docelowa (żywa, ta w której pracuje użytkownik)
WCHŁANIA źródłową (wskazany plik `.db`) - JEDNOKIERUNKOWO, źródło zostaje
NIETKNIĘTE (bezpieczne do ponownego przejrzenia/scalenia gdzie indziej).

Źródło musi mieć BIEŻĄCĄ wersję schematu: jest otwierane tylko do odczytu,
więc nie ma jak go po drodze zmigrować. Rozjazd wersji odrzuca
`_sprawdz_wersje_zrodla` czytelnym komunikatem, ZANIM cokolwiek zostanie
zmienione. Brakujące KOLUMNY w `transakcje` są mimo to obsłużone przez
`w.get(...)` i stają się NULL - to zabezpieczenie na bazy w stanie
pośrednim, nie furtka dla starego układu tabel.

Dwa etapy, rozdzielone celowo (ten sam wzorzec co import_orchestrator.py):
1. `zaplanuj_scalenie` - WYŁĄCZNIE odczyt obu baz, buduje pełny plan, nic
   nie zmienia - użytkownik widzi co się stanie ZANIM cokolwiek się stanie.
2. `wykonaj_scalenie` - stosuje plan (+ rozstrzygnięcia z ekranu korekty)
   do bazy docelowej, atomowo.

Reguła z roadmap.md, NIGDY nie łamana: konflikt wartości (ta sama trójka
data+kurier+punkt, różne ilości) NIE jest rozstrzygany automatycznie -
świadczy o błędzie we wprowadzaniu albo w papierze, wymaga człowieka.

Dopasowanie słowników po kluczu NATURALNYM, nie po `id` - te same
osoby/miejsca mają różne surogatowe ID na różnych stacjach:
- kurierzy/wykonawcy/rejony/nadawcy: nazwa, z tym samym trójpoziomowym
  podejściem co import_orchestrator.py (bezpieczne białe znaki -> automat,
  literówka -> propozycja, WYŁĄCZNIE diakrytyki -> ostrzeżenie, nigdy
  automat). Wykrywanie literówek tylko dla kurierów - świadomie wąskie,
  jak w imporcie (docs/domain-model.md: to konkretny, nazwany problem).
- punkty: PNI ZPO albo (nadawca, adres) - identycznie jak przy imporcie
  (`importer.get_or_create_punkt`), reużyte wprost przy wykonaniu. Adresy
  i nadawcy jadą jako TEKST, nie jako id: w v4 są osobnymi tabelami, ale
  ich surogatowe id są tak samo lokalne dla stacji jak każde inne.
- users: `id` to już deterministyczny UUIDv5 (patrz uzytkownicy.py) - żadne
  dopasowanie nie jest potrzebne, tylko wykrycie rzadkiego przypadku tej
  samej osoby z różnym numerem kadrowym na obu stacjach (miękkie
  ostrzeżenie, informacyjne, nie blokuje scalenia).
"""
import sqlite3
from pathlib import Path

from zpo_tracker import repo
from zpo_tracker.importer import get_or_create_punkt, get_or_create_rejon
from zpo_tracker.normalizacja import (
    czy_literowka, klucz_bialych_znakow, klucz_rozmyty, normalizuj_rejon,
)

_SLOWNIKI_PROSTE = {
    "kurierzy": ("imie_nazwisko", True),
    "wykonawcy": ("nazwa", False),
    "rejony": ("kod", False),
    "nadawcy": ("nazwa", False),
}

# Punkt źródłowy w postaci porównywalnej między bazami: nadawca i adres jako
# tekst, bo tylko on jest wspólny dla obu stacji (id nie jest).
_SQL_PUNKTY_ZRODLOWE = """
    SELECT p.id, n.nazwa AS nadawca, a.surowy AS adres, p.pni_zpo
    FROM punkty p
    JOIN nadawcy n ON n.id = p.nadawca_id
    JOIN adresy a ON a.id = p.adres_id
"""

_POLA_ILOSCI = ["ilosc_total", "ilosc_zpo", "ilosc_vinted",
                "ilosc_automaty", "ilosc_kurier48", "ilosc_niezrealizowane"]


def _ilosci_identyczne(a, b):
    return all(a[p] == b[p] for p in _POLA_ILOSCI)


class NiezgodnaWersjaZrodla(Exception):
    """
    Plik źródłowy ma inną wersję struktury niż ten program. Komunikat idzie
    wprost do użytkownika (`gui/zakladka_scalanie.py` pokazuje `str(e)`
    w okienku), więc jest po polsku i bez żargonu.
    """


def _sprawdz_wersje_zrodla(conn_zrodlowa):
    """
    Odpowiednik `repo.sprawdz_zgodnosc_wersji`, ale w OBIE strony i dla
    pliku, którego nie da się naprawić: źródło jest otwierane tylko do
    odczytu, więc `migruj` nie ma tu zastosowania.

    Bez tego sprawdzenia użytkownik wskazujący starszy plik dostawał surowy
    `no such table: nadawcy` - komunikat, z którym nie zrobi nic w programie
    pisanym dla ludzi, którzy nie mają jak go zinterpretować.
    """
    wersja = conn_zrodlowa.execute("PRAGMA user_version").fetchone()[0]
    if wersja == repo.WERSJA_SCHEMATU:
        return
    kierunek = "starszej" if wersja < repo.WERSJA_SCHEMATU else "nowszej"
    raise NiezgodnaWersjaZrodla(
        f"Wybrany plik pochodzi ze {kierunek} wersji programu (wersja danych "
        f"{wersja}, ten program obsługuje {repo.WERSJA_SCHEMATU}). "
        f"Scalanie zostało przerwane - nic nie zostało zmienione. "
        f"Otwórz ten plik w programie w tej samej wersji, żeby go podnieść."
    )


def _otworz_zrodlo_tylko_do_odczytu(sciezka):
    """
    Twarda gwarancja na poziomie silnika SQLite (URI `mode=ro`), nie tylko
    konwencja "nie wołaj INSERT" - źródło MUSI zostać nietknięte niezależnie
    od błędów gdziekolwiek dalej w scalaniu. `Path.as_uri()` poprawnie
    koduje spacje/znaki specjalne w ścieżce (typowe przy plikach wybranych
    przez użytkownika z okna dialogowego na Windows).
    """
    uri = Path(sciezka).resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _dopasuj_prosty_slownik(conn_docelowa, conn_zrodlowa, tabela, kolumna,
                             wykryj_literowki=False):
    """
    Zwraca {"mapowanie": {id_zrodlowe: id_docelowe}, "nowe": [...],
    "propozycje": [...], "ostrzezenia": [...]} - patrz docstring modułu.

    `rejony`: wartości przepuszczane przez `normalizuj_rejon` PRZED
    dopasowaniem, nie tylko przy wstawianiu - inaczej śmieciowy kod
    zapisany wprost w źródle (np. stara baza sprzed tej reguły) nie
    trafiłby w kanoniczny wiersz celu, tylko stałby się osobnym "nowym"
    wpisem o tej samej (nieznormalizowanej) treści.
    """
    normalizuj = normalizuj_rejon if tabela == "rejony" else (lambda v: v)
    docelowe = {r["id"]: normalizuj(r[kolumna])
                for r in conn_docelowa.execute(f"SELECT id, {kolumna} FROM {tabela}")}
    zrodlowe = {r["id"]: normalizuj(r[kolumna])
                for r in conn_zrodlowa.execute(f"SELECT id, {kolumna} FROM {tabela}")}

    po_kluczu = {klucz_bialych_znakow(v): id_doc for id_doc, v in docelowe.items()}
    po_kluczu_rozmytym = {klucz_rozmyty(v): (id_doc, v) for id_doc, v in docelowe.items()}

    mapowanie, nowe, propozycje, ostrzezenia = {}, [], [], []

    for id_zrodlowe, nazwa in zrodlowe.items():
        klucz = klucz_bialych_znakow(nazwa)
        if klucz in po_kluczu:
            mapowanie[id_zrodlowe] = po_kluczu[klucz]
            continue

        kr = klucz_rozmyty(nazwa)
        if kr in po_kluczu_rozmytym:
            id_docelowe, docelowa_nazwa = po_kluczu_rozmytym[kr]
            ostrzezenia.append({
                "id_zrodlowe": id_zrodlowe, "id_docelowe": id_docelowe,
                "zrodlowa": nazwa, "docelowa": docelowa_nazwa,
            })
            continue

        if wykryj_literowki:
            trafienie = next(
                (id_doc for id_doc, doc_nazwa in docelowe.items()
                 if czy_literowka(nazwa, doc_nazwa)),
                None,
            )
            if trafienie is not None:
                propozycje.append({
                    "id_zrodlowe": id_zrodlowe, "id_docelowe": trafienie,
                    "z": nazwa, "na": docelowe[trafienie],
                })
                continue

        nowe.append({"id_zrodlowe": id_zrodlowe, "nazwa": nazwa})

    return {"mapowanie": mapowanie, "nowe": nowe, "propozycje": propozycje,
            "ostrzezenia": ostrzezenia}


def _przenies_flage_liczy_zpo(conn_docelowa, conn_zrodlowa, mapa_nadawcow):
    """
    `liczy_zpo` to flaga, nie nazwa, więc generyczny INSERT prostego słownika
    (sama kolumna `nazwa`) jej nie przenosi. Scalamy ją przez OR: zapaloną
    zapalamy w celu, zgaszonej NIE gasimy.

    Powód asymetrii jest ten sam co w `importer.get_or_create_nadawca`:
    zgaszenie flagi wygasza pole "w tym ZPO" u nadawcy, dla którego druga
    stacja to pole normalnie wypełniała - i nikt tego nie zauważy, bo pole
    po prostu przestaje przyjmować wpis. Flaga zapalona nadmiarowo jest
    widoczna i naprawialna w Słownikach.
    """
    for r in conn_zrodlowa.execute("SELECT id, liczy_zpo FROM nadawcy"):
        if r["liczy_zpo"]:
            conn_docelowa.execute(
                "UPDATE nadawcy SET liczy_zpo = 1 WHERE id = ?", (mapa_nadawcow[r["id"]],))


def _dopasuj_uzytkownikow(conn_docelowa, conn_zrodlowa):
    """
    `users.id` to już deterministyczny UUIDv5 - dopasowanie to prosty
    lookup po id, nie po nazwie. Zwraca {"nowi": [...], "ostrzezenia": [...]}.
    """
    docelowi = {
        r["id"]: dict(r) for r in
        conn_docelowa.execute("SELECT id, login, alias, nr_kadrowy FROM users")
    }
    zrodlowi = conn_zrodlowa.execute(
        "SELECT id, login, alias, nr_kadrowy FROM users").fetchall()

    nowi, ostrzezenia = [], []
    for w in zrodlowi:
        w = dict(w)
        istniejacy = docelowi.get(w["id"])
        if istniejacy is None:
            nowi.append(w)
            continue
        if (w["nr_kadrowy"] and istniejacy["nr_kadrowy"]
                and w["nr_kadrowy"] != istniejacy["nr_kadrowy"]):
            ostrzezenia.append({
                "login": w["login"],
                "nr_kadrowy_docelowy": istniejacy["nr_kadrowy"],
                "nr_kadrowy_zrodlowy": w["nr_kadrowy"],
            })

    return {"nowi": nowi, "ostrzezenia": ostrzezenia}


def _znajdz_punkt_docelowy(conn_docelowa, nadawca, adres, pni_zpo):
    """
    Odpowiednik `importer.get_or_create_punkt`, ale WYŁĄCZNIE odczyt - do
    użytku w `zaplanuj_scalenie` (etap planu nic nie może zmienić). Ten sam
    klucz dopasowania: PNI ZPO gdy jest, inaczej (nadawca, adres) - patrz
    docs/domain-model.md, PNI jest wiarygodnym unikalnym identyfikatorem.
    """
    if pni_zpo:
        row = conn_docelowa.execute(
            "SELECT id FROM punkty WHERE pni_zpo = ?", (pni_zpo,)).fetchone()
    else:
        # bez predykatu `AND pni_zpo IS NULL`, tak samo jak w
        # `get_or_create_punkt` po przejściu na v4: para (nadawca, adres)
        # opisuje tam JEDEN punkt, więc wiersz bez PNI dopasuje się do
        # istniejącego punktu ZPO zamiast wyglądać na nowy
        row = conn_docelowa.execute(
            """SELECT p.id FROM punkty p
               JOIN nadawcy n ON n.id = p.nadawca_id
               JOIN adresy a ON a.id = p.adres_id
               WHERE n.nazwa = ? AND a.surowy = ?""",
            (nadawca, adres),
        ).fetchone()
    return row["id"] if row else None


def _zaplanuj_punkty(conn_docelowa, conn_zrodlowa):
    """
    Punkty NIE mają fazy propozycji/ostrzeżeń jak proste słowniki -
    dopasowanie po PNI/adresie jest już rozstrzygalne bez człowieka
    (ten sam klucz co przy imporcie).
    """
    mapowanie, nowe = {}, []
    for r in conn_zrodlowa.execute(_SQL_PUNKTY_ZRODLOWE):
        id_docelowe = _znajdz_punkt_docelowy(conn_docelowa, r["nadawca"], r["adres"], r["pni_zpo"])
        if id_docelowe is not None:
            mapowanie[r["id"]] = id_docelowe
        else:
            nowe.append(dict(r))
    return {"mapowanie": mapowanie, "nowe": nowe}


def _zaplanuj_transakcje(conn_docelowa, conn_zrodlowa, slowniki, punkty):
    """
    Klasyfikuje każdą transakcję źródła: nowa / duplikat / konflikt.
    Transakcja, której kurier/punkt jeszcze nie ma potwierdzonego
    dopasowania w celu (nowy wpis albo nierozstrzygnięte ostrzeżenie),
    jest ZAWSZE "nowa" - nie może już istnieć w celu pod id, które
    jeszcze nie istnieje. Propozycje literówek liczą się jako tymczasowo
    zaakceptowane (domyślne zachowanie, jak przy imporcie) - inaczej plan
    pokazywałby fałszywe konflikty dla par, które i tak zostaną scalone.
    """
    mapa_kurierzy = dict(slowniki["kurierzy"]["mapowanie"])
    for p in slowniki["kurierzy"]["propozycje"]:
        mapa_kurierzy[p["id_zrodlowe"]] = p["id_docelowe"]
    mapa_punkty = punkty["mapowanie"]

    nowe, duplikaty, konflikty = [], [], []

    for w in conn_zrodlowa.execute("SELECT * FROM transakcje"):
        w = dict(w)
        kurier_docelowy = mapa_kurierzy.get(w["kurier_id"])
        punkt_docelowy = mapa_punkty.get(w["punkt_id"])

        if kurier_docelowy is None or punkt_docelowy is None:
            nowe.append(w)
            continue

        istniejaca = conn_docelowa.execute(
            "SELECT * FROM transakcje WHERE data = ? AND kurier_id = ? AND punkt_id = ?",
            (w["data"], kurier_docelowy, punkt_docelowy),
        ).fetchone()

        if istniejaca is None:
            nowe.append(w)
        elif _ilosci_identyczne(w, dict(istniejaca)):
            duplikaty.append(w)
        else:
            kurier = conn_docelowa.execute(
                "SELECT imie_nazwisko FROM kurierzy WHERE id = ?",
                (kurier_docelowy,)).fetchone()[0]
            punkt = conn_docelowa.execute(
                """SELECT n.nazwa AS nadawca, a.surowy AS adres FROM punkty p
                   JOIN nadawcy n ON n.id = p.nadawca_id
                   JOIN adresy a ON a.id = p.adres_id
                   WHERE p.id = ?""",
                (punkt_docelowy,)).fetchone()
            konflikty.append({
                "id_transakcji_zrodlowej": w["id"],
                "kurier": kurier,
                "punkt": f"{punkt['nadawca']} / {punkt['adres']}",
                "data": w["data"],
                "zrodlowa": w,
                "docelowa": dict(istniejaca),
            })

    return {"nowe": nowe, "duplikaty": duplikaty, "konflikty": konflikty}


def zaplanuj_scalenie(conn_docelowa, sciezka_zrodlowa):
    """
    Otwiera źródło WYŁĄCZNIE do odczytu i buduje pełny plan scalenia - nic
    nie zmienia w żadnej z baz. Do pokazania użytkownikowi PRZED
    `wykonaj_scalenie`.
    """
    conn_zrodlowa = _otworz_zrodlo_tylko_do_odczytu(sciezka_zrodlowa)
    try:
        _sprawdz_wersje_zrodla(conn_zrodlowa)
        slowniki = {
            tabela: _dopasuj_prosty_slownik(
                conn_docelowa, conn_zrodlowa, tabela, kolumna, wykryj_literowki)
            for tabela, (kolumna, wykryj_literowki) in _SLOWNIKI_PROSTE.items()
        }
        punkty = _zaplanuj_punkty(conn_docelowa, conn_zrodlowa)
        uzytkownicy_plan = _dopasuj_uzytkownikow(conn_docelowa, conn_zrodlowa)
        transakcje = _zaplanuj_transakcje(conn_docelowa, conn_zrodlowa, slowniki, punkty)
    finally:
        conn_zrodlowa.close()

    return {
        "slowniki": slowniki, "punkty": punkty,
        "uzytkownicy": uzytkownicy_plan, "transakcje": transakcje,
    }


def wykonaj_scalenie(conn_docelowa, sciezka_zrodlowa, *,
                      odrzucone_propozycje_kurierow=None,
                      zaakceptowane_ostrzezenia=None,
                      rozstrzygniecia_konfliktow=None):
    """
    Stosuje scalenie do `conn_docelowa`, atomowo (`repo.transakcja` -
    awaria w połowie nie zostawia bazy w stanie pośrednim). Źródło zostaje
    otwarte tylko do odczytu i nietknięte - scalenie jest jednokierunkowe.

    - `odrzucone_propozycje_kurierow`: id_zrodlowe propozycji literówek
      (patrz `_dopasuj_prosty_slownik`), które MIMO sugestii mają zostać
      osobnymi wpisami zamiast scalone - domyślnie wszystkie propozycje są
      akceptowane, jak przy imporcie.
    - `zaakceptowane_ostrzezenia`: {tabela: set(id_zrodlowe)} - ostrzeżenia
      o różnicy WYŁĄCZNIE w diakrytykach, jawnie zaakceptowane do scalenia
      z dopasowanym wpisem docelowym - domyślnie ŻADNE nie są scalane
      automatycznie (ta sama zasada co przy imporcie: to decyzja człowieka).
    - `rozstrzygniecia_konfliktow`: {id_transakcji_zrodlowej: "zrodlowa"} -
      konflikt wartości (roadmap.md: NIGDY nie rozstrzygany automatycznie)
      domyślnie zostaje z wartością DOCELOWĄ (nigdy nie nadpisuje po cichu),
      chyba że jawnie wybrano wartość źródłową.
    """
    odrzucone_propozycje_kurierow = odrzucone_propozycje_kurierow or set()
    zaakceptowane_ostrzezenia = zaakceptowane_ostrzezenia or {}
    rozstrzygniecia_konfliktow = rozstrzygniecia_konfliktow or {}

    conn_zrodlowa = _otworz_zrodlo_tylko_do_odczytu(sciezka_zrodlowa)
    try:
        _sprawdz_wersje_zrodla(conn_zrodlowa)
        with repo.transakcja(conn_docelowa):
            wynik = _wykonaj_scalenie_bez_transakcji(
                conn_docelowa, conn_zrodlowa,
                odrzucone_propozycje_kurierow, zaakceptowane_ostrzezenia,
                rozstrzygniecia_konfliktow,
            )
    finally:
        conn_zrodlowa.close()
    return wynik


def _wykonaj_scalenie_bez_transakcji(conn_docelowa, conn_zrodlowa,
                                      odrzucone_propozycje_kurierow,
                                      zaakceptowane_ostrzezenia,
                                      rozstrzygniecia_konfliktow):
    # 1. słowniki proste: mapowanie pewne + zaakceptowane propozycje/
    #    ostrzeżenia, wszystko inne (nowe wpisy, odrzucone propozycje,
    #    nieprzyjęte ostrzeżenia) dostaje świeży wpis w celu
    mapy = {}
    for tabela, (kolumna, wykryj_literowki) in _SLOWNIKI_PROSTE.items():
        dopasowanie = _dopasuj_prosty_slownik(
            conn_docelowa, conn_zrodlowa, tabela, kolumna, wykryj_literowki)
        mapa = dict(dopasowanie["mapowanie"])

        for p in dopasowanie["propozycje"]:
            if p["id_zrodlowe"] not in odrzucone_propozycje_kurierow:
                mapa[p["id_zrodlowe"]] = p["id_docelowe"]

        zaakceptowane_tej_tabeli = zaakceptowane_ostrzezenia.get(tabela, set())
        for o in dopasowanie["ostrzezenia"]:
            if o["id_zrodlowe"] in zaakceptowane_tej_tabeli:
                mapa[o["id_zrodlowe"]] = o["id_docelowe"]

        nierozstrzygniete = (
            dopasowanie["nowe"]
            + [{"id_zrodlowe": p["id_zrodlowe"], "nazwa": p["z"]}
               for p in dopasowanie["propozycje"] if p["id_zrodlowe"] not in mapa]
            + [{"id_zrodlowe": o["id_zrodlowe"], "nazwa": o["zrodlowa"]}
               for o in dopasowanie["ostrzezenia"] if o["id_zrodlowe"] not in mapa]
        )
        for wpis in nierozstrzygniete:
            if tabela == "rejony":
                # get-or-create, NIE ślepy INSERT: dwa różne id źródłowe
                # mogą normalizować się do tej samej wartości (np. "-" i
                # "n/a" -> "???") - ślepy INSERT drugiego z nich rzuciłby
                # IntegrityError na UNIQUE i wycofał całe scalenie
                mapa[wpis["id_zrodlowe"]] = get_or_create_rejon(conn_docelowa, wpis["nazwa"])
            else:
                cur = conn_docelowa.execute(
                    f"INSERT INTO {tabela} ({kolumna}) VALUES (?)", (wpis["nazwa"],))
                mapa[wpis["id_zrodlowe"]] = cur.lastrowid

        mapy[tabela] = mapa

    _przenies_flage_liczy_zpo(conn_docelowa, conn_zrodlowa, mapy["nadawcy"])

    # 2. użytkownicy - id już globalnie spójny (UUIDv5), dopisz tylko
    #    brakujących; ostrzeżenia o rozjeździe nr_kadrowy są informacyjne,
    #    nie blokują (niska stawka w porównaniu do konfliktu ilości)
    for u in _dopasuj_uzytkownikow(conn_docelowa, conn_zrodlowa)["nowi"]:
        conn_docelowa.execute(
            "INSERT INTO users (id, login, alias, nr_kadrowy, utworzono)"
            " VALUES (?, ?, ?, ?, ?)",
            (u["id"], u["login"], u["alias"], u["nr_kadrowy"], u.get("utworzono")),
        )

    # 3. punkty - reużywa get_or_create_punkt WPROST (ten sam klucz co przy
    #    imporcie, idempotentne, bezpieczne do wywołania na mutującym conn)
    mapa_punkty = {}
    for p in conn_zrodlowa.execute(_SQL_PUNKTY_ZRODLOWE):
        id_docelowe, _ostrzezenia = get_or_create_punkt(
            conn_docelowa, p["nadawca"], p["adres"], p["pni_zpo"])
        mapa_punkty[p["id"]] = id_docelowe

    # 4. transakcje - insert czystych nowości, pominięcie prawdziwych
    #    duplikatów, konflikt NIGDY po cichu (domyślnie zostaje wartość
    #    docelowa, chyba że jawnie rozstrzygnięto na korzyść źródła)
    dodano = pominieto = rozstrzygnieto = 0
    for w in conn_zrodlowa.execute("SELECT * FROM transakcje"):
        w = dict(w)
        kurier_id = mapy["kurierzy"][w["kurier_id"]]
        punkt_id = mapa_punkty[w["punkt_id"]]
        # NULL ze źródła (stara, niereperowana baza) NIE może wrócić jako
        # NULL do celu - trafia w ten sam kanoniczny wiersz co każdy inny
        # śmieciowy rejon, get_or_create_rejon(None) -> REJON_NIEZNANY
        rejon_id = (mapy["rejony"][w["rejon_id"]] if w["rejon_id"] is not None
                    else get_or_create_rejon(conn_docelowa, None))
        wykonawca_id = (mapy["wykonawcy"].get(w["wykonawca_id"])
                         if w["wykonawca_id"] is not None else None)

        istniejaca = conn_docelowa.execute(
            "SELECT * FROM transakcje WHERE data = ? AND kurier_id = ? AND punkt_id = ?",
            (w["data"], kurier_id, punkt_id),
        ).fetchone()

        if istniejaca is None:
            # sesja_uuid/zrodlo (0.1-alpha.3.2): PRZENIESIONE ze źródła, nie
            # nadpisane - pochodzenie wiersza to miejsce, gdzie POWSTAŁ, nie
            # gdzie zostało scalone. `.get()` zamiast `w["..."]`: źródło może
            # być bazą sprzed tego wydania (kolumny wtedy nie istnieją w
            # ogóle w `dict(row)`), a nie tylko mieć w nich NULL.
            conn_docelowa.execute(
                """INSERT INTO transakcje
                   (data, kurier_id, punkt_id, rejon_id, wykonawca_id,
                    ilosc_total, ilosc_zpo, ilosc_vinted, ilosc_automaty,
                    ilosc_kurier48, ilosc_niezrealizowane, komentarz,
                    uuid, autor_id, utworzono, zmodyfikowano,
                    sesja_uuid, zrodlo)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (w["data"], kurier_id, punkt_id, rejon_id, wykonawca_id,
                 w["ilosc_total"], w["ilosc_zpo"], w["ilosc_vinted"],
                 w["ilosc_automaty"], w["ilosc_kurier48"], w["ilosc_niezrealizowane"],
                 w["komentarz"], w["uuid"], w["autor_id"], w["utworzono"],
                 w["zmodyfikowano"], w.get("sesja_uuid"), w.get("zrodlo")),
            )
            dodano += 1
            continue

        istniejaca = dict(istniejaca)
        if _ilosci_identyczne(w, istniejaca):
            pominieto += 1
            continue

        if rozstrzygniecia_konfliktow.get(w["id"]) == "zrodlowa":
            conn_docelowa.execute(
                """UPDATE transakcje SET
                   ilosc_total=?, ilosc_zpo=?, ilosc_vinted=?, ilosc_automaty=?,
                   ilosc_kurier48=?, ilosc_niezrealizowane=?, zmodyfikowano=?
                   WHERE id=?""",
                (w["ilosc_total"], w["ilosc_zpo"], w["ilosc_vinted"],
                 w["ilosc_automaty"], w["ilosc_kurier48"], w["ilosc_niezrealizowane"],
                 w["zmodyfikowano"], istniejaca["id"]),
            )
            rozstrzygnieto += 1
        # brak rozstrzygnięcia (albo jawnie "docelowa") -> nic się nie
        # zmienia, wartość docelowa zostaje - nigdy po cichu nie nadpisujemy

    return {"dodano_transakcji": dodano, "pominieto_duplikatow": pominieto,
            "rozstrzygnieto_konfliktow": rozstrzygnieto}

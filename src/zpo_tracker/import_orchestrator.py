"""
Orkiestracja importu .xlsx: walidacja wierszy, wykrycie prawdopodobnych
literówek w nazwiskach kurierów W RAMACH PARTII importu, i zapis do bazy
z rozdzieleniem wyniku na "przeszło cicho" vs "wymaga uwagi" - ekran
korekty w GUI pokazuje wyłącznie drugie (patrz plan MVP, krok 7).

Decyzja o scaleniu literówki jest podejmowana PRZED zapisem (nie jako
odwracanie po fakcie) - "opcjonalne przywrócenie" z wymagań użytkownika
oznacza tutaj: automatyczne dopasowanie jest domyślnie zaznaczone do
scalenia w ekranie korekty, ale można je odznaczyć przed zatwierdzeniem
importu, zamiast scalać na pewno i cofać później.
"""
import sqlite3
import uuid
from datetime import datetime

from pydantic import ValidationError

from zpo_tracker.importer import (
    get_or_create_kurier,
    get_or_create_punkt,
    get_or_create_rejon,
    get_or_create_wykonawca,
    znajdz_lub_utworz_punkt_niezaufany,
)
from zpo_tracker.models import WierszImportu
from zpo_tracker.normalizacja import czy_literowka, grupuj_bezpiecznie, znajdz_podobne

MAPA_NAGLOWKOW = {
    "data": "data",
    " Pełna Nazwa Nadawcy": "nadawca",
    "Adres odbioru dla wszystkich nadawców": "adres",
    "Kurier": "kurier",
    "Rejon": "rejon",
    " Wpisujemy łączną liczbę odebranych Pocztexów": "ilosc_total",
    " Wpisujemy   w tym liczbę z Zewnetrznych Punktów Odbiorów ": "ilosc_zpo",
    "PNI ZPO": "pni_zpo",
    "Wpisujemy w tym liczbę odebranych z ZPO  w ramach             e Commerce -Vinted": "ilosc_vinted",
    "w tym Liczba z Automatów ": "ilosc_automaty",
    "w tym Kurier 48": "ilosc_kurier48",
    "Paczki nierozliczone - niezrealizowane odbiory": "ilosc_niezrealizowane",
    "Wykonawca": "wykonawca",
}


def _przemapuj(surowy):
    return {MAPA_NAGLOWKOW[k]: v for k, v in surowy.items() if k in MAPA_NAGLOWKOW}


def _pierwszy_blad(wyjatek: ValidationError) -> str:
    blad = wyjatek.errors()[0]
    pole = ".".join(str(p) for p in blad["loc"])
    return f"{pole}: {blad['msg']}"


# Metadana transportowa doklejana do surowego wiersza przy czytaniu pliku,
# żeby dało się wskazać, KTÓRY wiersz źródłowego Excela wymaga poprawki.
# Nie jest kolumną danych: `_przemapuj` filtruje po MAPA_NAGLOWKOW, więc
# nigdy nie dociera do WierszImportu.
KLUCZ_NUMERU_WIERSZA = "__wiersz__"


def zbierz_odrzucone(odrzucone, wymagajace_uwagi=()):
    """
    Sprowadza dwa różne kształty odrzuceń do jednej listy dla raportu.

    Odrzucenia przychodzą z dwóch etapów i wyglądają inaczej: walidacja
    oddaje SUROWY dict (i zna numer wiersza), a konflikty duplikatu/PNI
    wychodzą dopiero przy zapisie i niosą już zwalidowany `WierszImportu`
    (numeru nie znają). Raport ma pokazać jedno i drugie, bo dla
    wprowadzającego to ta sama sprawa: "co nie weszło i dlaczego".
    """
    pozycje = []
    for zrodlo in (odrzucone, wymagajace_uwagi):
        for pozycja in zrodlo:
            wiersz = pozycja["wiersz"]
            dane = dict(wiersz) if isinstance(wiersz, dict) else dict(wiersz)
            numer = dane.pop(KLUCZ_NUMERU_WIERSZA, None)
            pozycje.append({
                "numer_wiersza": numer,
                "powod": pozycja["powod"],
                "dane": dane,
            })
    return pozycje


def zwaliduj_wiersze(wiersze_surowe):
    """
    wiersze_surowe: lista dictów nagłówek->wartość (z xlsx, przez openpyxl).
    Zwraca (zwalidowane: list[WierszImportu], odrzucone: list[dict]).
    Wiersze bez daty lub kuriera są pomijane BEZ zgłaszania - to puste
    wiersze-szablony w źródle (docs/domain-model.md), nie błąd do przeglądu.
    """
    zwalidowane, odrzucone = [], []
    for surowy in wiersze_surowe:
        if not surowy.get("data") or not surowy.get("Kurier"):
            continue
        try:
            zwalidowane.append(WierszImportu(**_przemapuj(surowy)))
        except ValidationError as e:
            odrzucone.append({"wiersz": surowy, "powod": _pierwszy_blad(e)})
    return zwalidowane, odrzucone


def znajdz_propozycje_scalenia_kurierow(zwalidowane):
    """
    Wykrywa prawdopodobne literówki w nazwiskach kurierów w RAMACH TEJ
    PARTII (nie w całej bazie). Zwraca listę {"z": ..., "na": ...} -
    kanoniczna forma to ta z liczniejszej grupy wariantów białych znaków.
    """
    grupy = grupuj_bezpiecznie(w.kurier for w in zwalidowane)
    propozycje = []
    uzyte = set()
    for i, g1 in enumerate(grupy):
        if g1.kanoniczna in uzyte:
            continue
        for g2 in grupy[i + 1:]:
            if g2.kanoniczna in uzyte:
                continue
            if czy_literowka(g1.kanoniczna, g2.kanoniczna):
                wieksza, mniejsza = (g1, g2) if g1.liczba >= g2.liczba else (g2, g1)
                propozycje.append({"z": mniejsza.kanoniczna, "na": wieksza.kanoniczna})
                uzyte.add(mniejsza.kanoniczna)
    return propozycje


def znajdz_ostrzezenia_podobienstwa_kurierow(zwalidowane):
    """
    Różnica WYŁĄCZNIE w diakrytykach/wielkości liter (np. "Wołczuk Rafal"
    / "Wołczuk Rafał", docs/domain-model.md) - NIGDY automatyczne scalanie,
    tylko sygnał do ekranu korekty. Osobna kategoria od propozycji
    literówek (znajdz_propozycje_scalenia_kurierow), która świadomie tych
    par nie dotyka.
    """
    grupy = grupuj_bezpiecznie(w.kurier for w in zwalidowane)
    return znajdz_podobne(grupy)


def zaimportuj(conn, zwalidowane, mapowanie_scalen=None, *, zaufany=False,
                autor_id=None, sesja_uuid=None, teraz=None):
    """
    Zapisuje zwalidowane wiersze do bazy, stosując mapowanie_scalen
    (surowy kurier -> kanoniczny, tylko zaakceptowane w ekranie korekty)
    przed zapisem. Zwraca {"zaimportowano": int, "wymagajace_uwagi": [...]}.
    wymagajace_uwagi: {"wiersz": WierszImportu, "powod": str} dla
    duplikatów i konfliktów PNI/adres - jedyne, co ekran korekty pokazuje
    z tego etapu.

    `zaufany` (0.1-alpha.3.2) - domyślnie **False**, bo brak jawnego
    zaufania musi znaczyć brak zaufania. Plik niezaufany NIE wnosi:

    - **PNI** - to klucz tożsamości punktu (`punkty.pni_zpo UNIQUE`), więc
      śmieciowa wartość po cichu podpina transakcję pod cudzy punkt, zamienia
      kolejne wiersze w "duplikaty" (utrata danych) i trwale otwiera pole
      "w tym ZPO" przez `repo.czy_nadawca_ma_pni`;
    - **rejon** - dane z papierowych blankietów są zakłamane, a rejonarz
      (0.1-alpha.3.3/3.4) będzie źródłem prawdy; wiersze lądują na
      kanonicznym "???" i staną się kandydatami do uzupełnienia.

    Reszta (kurier, wykonawca, nadawca, adres, ilości) wchodzi normalnie -
    to dane czytelne dla człowieka i poprawialne w aplikacji (widok poprawek,
    Słowniki). Odcinamy WYŁĄCZNIE to, czego nie da się ani zweryfikować, ani
    sensownie poprawić ręcznie.

    Import pisze też `uuid`/`autor_id`/`utworzono`/`zmodyfikowano`/
    `sesja_uuid`/`zrodlo` - dotąd wiersze z importu były "drugiej kategorii"
    względem formularza (bez tożsamości niezależnej od klucza naturalnego,
    bez atrybucji).
    """
    mapowanie_scalen = mapowanie_scalen or {}
    teraz = teraz or datetime.now().isoformat(timespec="seconds")
    zrodlo = "import_zaufany" if zaufany else "import"
    zaimportowano = 0
    wymagajace_uwagi = []

    for w in zwalidowane:
        kurier_nazwa = mapowanie_scalen.get(w.kurier, w.kurier)
        kurier_id = get_or_create_kurier(conn, kurier_nazwa)
        # niezaufany: rejon -> kanoniczne "???" (get_or_create_rejon(None)),
        # PNI -> całkowicie pominięte (osobna ścieżka podpinania punktu)
        rejon_id = get_or_create_rejon(conn, w.rejon if zaufany else None)
        wykonawca_id = get_or_create_wykonawca(conn, w.wykonawca)
        if zaufany:
            punkt_id, ostrzezenia = get_or_create_punkt(conn, w.nadawca, w.adres, w.pni_zpo)
        else:
            punkt_id, ostrzezenia = znajdz_lub_utworz_punkt_niezaufany(
                conn, w.nadawca, w.adres)
        if ostrzezenia:
            wymagajace_uwagi.append({"wiersz": w, "powod": "; ".join(ostrzezenia)})

        try:
            conn.execute(
                """INSERT INTO transakcje
                   (data, kurier_id, punkt_id, rejon_id, wykonawca_id,
                    ilosc_total, ilosc_zpo, ilosc_vinted, ilosc_automaty,
                    ilosc_kurier48, ilosc_niezrealizowane,
                    uuid, autor_id, utworzono, zmodyfikowano,
                    sesja_uuid, zrodlo)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    w.data.isoformat(), kurier_id, punkt_id, rejon_id, wykonawca_id,
                    w.ilosc_total, w.ilosc_zpo, w.ilosc_vinted, w.ilosc_automaty,
                    w.ilosc_kurier48, w.ilosc_niezrealizowane,
                    str(uuid.uuid4()), autor_id, teraz, teraz,
                    sesja_uuid, zrodlo,
                ),
            )
            zaimportowano += 1
        except sqlite3.IntegrityError:
            wymagajace_uwagi.append({
                "wiersz": w, "powod": "duplikat (ta sama data+kurier+punkt już istnieje)",
            })

    return {"zaimportowano": zaimportowano, "wymagajace_uwagi": wymagajace_uwagi}

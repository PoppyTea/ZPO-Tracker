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

from pydantic import ValidationError

from zpo_tracker.importer import (
    get_or_create_kurier,
    get_or_create_punkt,
    get_or_create_rejon,
    get_or_create_wykonawca,
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


def zaimportuj(conn, zwalidowane, mapowanie_scalen=None):
    """
    Zapisuje zwalidowane wiersze do bazy, stosując mapowanie_scalen
    (surowy kurier -> kanoniczny, tylko zaakceptowane w ekranie korekty)
    przed zapisem. Zwraca {"zaimportowano": int, "wymagajace_uwagi": [...]}.
    wymagajace_uwagi: {"wiersz": WierszImportu, "powod": str} dla
    duplikatów i konfliktów PNI/adres - jedyne, co ekran korekty pokazuje
    z tego etapu.
    """
    mapowanie_scalen = mapowanie_scalen or {}
    zaimportowano = 0
    wymagajace_uwagi = []

    for w in zwalidowane:
        kurier_nazwa = mapowanie_scalen.get(w.kurier, w.kurier)
        kurier_id = get_or_create_kurier(conn, kurier_nazwa)
        rejon_id = get_or_create_rejon(conn, w.rejon)
        wykonawca_id = get_or_create_wykonawca(conn, w.wykonawca)
        punkt_id, ostrzezenia = get_or_create_punkt(conn, w.nadawca, w.adres, w.pni_zpo)
        if ostrzezenia:
            wymagajace_uwagi.append({"wiersz": w, "powod": "; ".join(ostrzezenia)})

        try:
            conn.execute(
                """INSERT INTO transakcje
                   (data, kurier_id, punkt_id, rejon_id, wykonawca_id,
                    ilosc_total, ilosc_zpo, ilosc_vinted, ilosc_automaty,
                    ilosc_kurier48, ilosc_niezrealizowane)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    w.data.isoformat(), kurier_id, punkt_id, rejon_id, wykonawca_id,
                    w.ilosc_total, w.ilosc_zpo, w.ilosc_vinted, w.ilosc_automaty,
                    w.ilosc_kurier48, w.ilosc_niezrealizowane,
                ),
            )
            zaimportowano += 1
        except sqlite3.IntegrityError:
            wymagajace_uwagi.append({
                "wiersz": w, "powod": "duplikat (ta sama data+kurier+punkt już istnieje)",
            })

    return {"zaimportowano": zaimportowano, "wymagajace_uwagi": wymagajace_uwagi}

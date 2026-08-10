"""
Export transakcji do pliku .xlsx o układzie identycznym ze snapshotem
źródłowym: te same nagłówki i kolejność kolumn, jeden arkusz na miesiąc,
nazwany po polsku (docs/domain-model.md: "każdy nowy miesiąc to nowy
arkusz"). Typy komórek kanonicznie czyste (int/date) - świadomie NIE
odtwarzają niespójności ręcznego wpisywania w źródle (część ilości i PNI
tam jest zapisana jako tekst), bo czyszczenie tego jest celem narzędzia.
"""
import calendar
from datetime import date

import openpyxl

# Dokładne stringi ze snapshotu źródłowego (białe znaki są częścią danych).
NAGLOWKI = [
    "data",
    " Pełna Nazwa Nadawcy",
    "Adres odbioru dla wszystkich nadawców",
    "Kurier",
    "Rejon",
    " Wpisujemy łączną liczbę odebranych Pocztexów",
    " Wpisujemy   w tym liczbę z Zewnetrznych Punktów Odbiorów ",
    "PNI ZPO",
    "Wpisujemy w tym liczbę odebranych z ZPO  w ramach             e Commerce -Vinted",
    "w tym Liczba z Automatów ",
    "w tym Kurier 48",
    "Paczki nierozliczone - niezrealizowane odbiory",
    "Wykonawca",
]

NAZWY_MIESIECY_PL = [
    "Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec",
    "Lipiec", "Sierpień", "Wrzesień", "Październik", "Listopad", "Grudzień",
]


def nazwa_arkusza(rok, miesiac):
    return NAZWY_MIESIECY_PL[miesiac - 1]


def _jako_int_lub_none(v):
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return v


def pobierz_transakcje_miesiaca(conn, rok, miesiac):
    """Transakcje z danego miesiąca (włącznie z rzadkimi ilościami)."""
    pierwszy = date(rok, miesiac, 1)
    ostatni = date(rok, miesiac, calendar.monthrange(rok, miesiac)[1])
    wiersze = conn.execute(
        """SELECT t.data, p.nadawca, p.adres, k.imie_nazwisko AS kurier,
                  r.kod AS rejon, t.ilosc_total, t.ilosc_zpo, p.pni_zpo,
                  t.ilosc_vinted, t.ilosc_automaty, t.ilosc_kurier48,
                  t.ilosc_niezrealizowane, w.nazwa AS wykonawca
           FROM transakcje t
           JOIN kurierzy k ON k.id = t.kurier_id
           JOIN punkty p ON p.id = t.punkt_id
           LEFT JOIN rejony r ON r.id = t.rejon_id
           LEFT JOIN wykonawcy w ON w.id = t.wykonawca_id
           WHERE t.data BETWEEN ? AND ?
           ORDER BY t.data, t.id""",
        (pierwszy.isoformat(), ostatni.isoformat()),
    ).fetchall()
    return [dict(w) for w in wiersze]


def eksportuj_miesiac(conn, rok, miesiac, sciezka):
    """
    Zapisuje transakcje z danego miesiąca do pliku .xlsx - jeden arkusz
    nazwany miesiącem, kolumny A-M identyczne ze snapshotem źródłowym.
    Zwraca liczbę wyeksportowanych wierszy.
    """
    wiersze = pobierz_transakcje_miesiaca(conn, rok, miesiac)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = nazwa_arkusza(rok, miesiac)
    ws.append(NAGLOWKI)

    for w in wiersze:
        data_val = w["data"]
        if isinstance(data_val, str):
            data_val = date.fromisoformat(data_val)
        ws.append([
            data_val,
            w["nadawca"],
            w["adres"],
            w["kurier"],
            w["rejon"],
            w["ilosc_total"],
            w["ilosc_zpo"],
            _jako_int_lub_none(w["pni_zpo"]),
            w["ilosc_vinted"],
            w["ilosc_automaty"],
            w["ilosc_kurier48"],
            w["ilosc_niezrealizowane"],
            w["wykonawca"],
        ])

    for komorka in ws["A"][1:]:
        komorka.number_format = "yyyy-mm-dd"

    wb.save(sciezka)
    return len(wiersze)

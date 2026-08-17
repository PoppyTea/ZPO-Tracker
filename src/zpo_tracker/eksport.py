"""
Export transakcji do pliku .xlsx o układzie identycznym ze snapshotem
źródłowym: te same nagłówki i kolejność kolumn, jeden arkusz na miesiąc,
nazwany po polsku (docs/domain-model.md: "każdy nowy miesiąc to nowy
arkusz"). Typy komórek kanonicznie czyste (int/date) - świadomie NIE
odtwarzają niespójności ręcznego wpisywania w źródle (część ilości tam jest
zapisana jako tekst), bo czyszczenie tego jest celem narzędzia.

**PNI jest wyjątkiem od tej reguły i zostaje TEKSTEM** (0.1-alpha.3.2): to
klucz tożsamości punktu (`punkty.pni_zpo UNIQUE`), a nie wielkość liczbowa.
Rzutowanie na int zamieniało "007" w 7, reimport czytał "7" i ten sam
fizyczny punkt dostawał dwa różne klucze - samo-zadana korupcja, bez udziału
jakiegokolwiek obcego pliku.

Znacznik pochodzenia + odcisk palca (0.1-alpha.3.2): plik dostaje dwie
właściwości niestandardowe dokumentu - stały znacznik "to nasz eksport"
i SHA-256 kanonicznej postaci danych. Import po nich rozpoznaje, czy
plikowi wolno ufać (patrz `zweryfikuj_plik` i import_orchestrator.py).
Sam znacznik nie wystarcza: pliki .xlsx są trywialnie edytowalne w Excelu,
więc dopiero zgodny odcisk dowodzi, że zawartość jest ta, którą zapisaliśmy.
"""
import calendar
import hashlib
from datetime import date, datetime

import openpyxl
from openpyxl.packaging.custom import StringProperty

NAZWA_ZNACZNIKA = "zpo_tracker_eksport"
NAZWA_ODCISKU = "zpo_tracker_odcisk"
WERSJA_ZNACZNIKA = "1"

# wyniki `zweryfikuj_plik`
PLIK_ZAUFANY = "zaufany"            # nasz eksport, odcisk się zgadza
PLIK_OBCY = "obcy"                  # brak znacznika - obcy/ręcznie robiony plik
PLIK_ZMODYFIKOWANY = "zmodyfikowany"  # nasz znacznik, ale zawartość już nie ta

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


def _jako_tekst_lub_none(v):
    """PNI zawsze jako tekst - patrz docstring modułu."""
    if v is None or v == "":
        return None
    return str(v).strip() or None


def _kanoniczna_komorka(v):
    """
    Jedna komórka -> stabilny tekst do policzenia odcisku. Musi dać ten sam
    wynik po stronie ZAPISU (wartości prosto z bazy) i ODCZYTU (to, co
    openpyxl przeczyta z pliku) - stąd sprowadzenie daty/czasu do ISO daty
    (openpyxl czyta daty jako `datetime`, my zapisujemy `date`) i liczb
    całkowitych do jednej postaci (int zapisany w xlsx wraca jako int, ale
    część z nich potrafi wrócić jako float, np. 3 -> 3.0).
    """
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def odcisk_wierszy(wiersze):
    """
    SHA-256 kanonicznej postaci danych arkusza. `wiersze`: iterowalne krotek
    wartości komórek (dokładnie to, co zwraca `ws.iter_rows(values_only=True)`),
    razem z wierszem nagłówków - zmiana nagłówka też musi unieważnić odcisk.
    Separatory (`\\x1f` między komórkami, `\\x1e` między wierszami) nie mogą
    wystąpić w danych, więc "a|b" i "a", "b" dają różne odciski.
    """
    tresc = "\x1e".join(
        "\x1f".join(_kanoniczna_komorka(k) for k in wiersz) for wiersz in wiersze
    )
    return hashlib.sha256(tresc.encode("utf-8")).hexdigest()


def zweryfikuj_plik(sciezka):
    """
    PLIK_ZAUFANY / PLIK_OBCY / PLIK_ZMODYFIKOWANY - patrz stałe wyżej i
    docstring modułu. Nieczytelny plik to PLIK_OBCY, nie wyjątek: decyzja
    o zaufaniu nigdy nie może wysadzić importu, a "nie umiem tego
    zweryfikować" znaczy dokładnie tyle co "nie ufam".
    """
    try:
        wb = openpyxl.load_workbook(sciezka, data_only=True)
    except Exception:
        return PLIK_OBCY

    wlasciwosci = {p.name: p.value for p in wb.custom_doc_props.props}
    if NAZWA_ZNACZNIKA not in wlasciwosci:
        return PLIK_OBCY

    ws = wb[wb.sheetnames[0]]
    if wlasciwosci.get(NAZWA_ODCISKU) != odcisk_wierszy(ws.iter_rows(values_only=True)):
        return PLIK_ZMODYFIKOWANY
    return PLIK_ZAUFANY


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
            _jako_tekst_lub_none(w["pni_zpo"]),
            w["ilosc_vinted"],
            w["ilosc_automaty"],
            w["ilosc_kurier48"],
            w["ilosc_niezrealizowane"],
            w["wykonawca"],
        ])

    for komorka in ws["A"][1:]:
        komorka.number_format = "yyyy-mm-dd"

    # znacznik + odcisk liczone z GOTOWEGO arkusza, nie z `wiersze` z bazy:
    # import policzy hash dokładnie z tych samych komórek, więc obie strony
    # muszą wyjść od tej samej reprezentacji (patrz docstring modułu)
    wb.custom_doc_props.append(
        StringProperty(name=NAZWA_ZNACZNIKA, value=WERSJA_ZNACZNIKA))
    wb.custom_doc_props.append(
        StringProperty(name=NAZWA_ODCISKU,
                        value=odcisk_wierszy(ws.iter_rows(values_only=True))))

    wb.save(sciezka)
    return len(wiersze)

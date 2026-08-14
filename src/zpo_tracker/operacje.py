"""
Fasada łącząca migawki (kopie.py) z dziennikiem operacji (dziennik.py):
każda mutująca operacja dostaje migawkę SPRZED wykonania i wpis w dzienniku,
więc cofnięcie do dowolnego punktu w historii jest zawsze możliwe - cel
`0.1-alpha.3`: żaden pojedynczy błąd (użytkownika, aplikacji, dysku) nie
kosztuje więcej niż jedną operację pracy.

GUI woła WYŁĄCZNIE `wykonaj`/`cofnij`, nigdy `repo.*` bezpośrednio dla
operacji mutujących - inaczej mutacja ominęłaby migawkę i dziennik.
"""
from datetime import datetime
from pathlib import Path

from zpo_tracker import dziennik, kopie, repo


def wykonaj(conn, katalog_danych, rodzaj, etykieta, funkcja,
            args=(), kwargs=None, licz_wiersze=None, licz_pominiete=None):
    """
    Migawka PRZED wywołaniem `funkcja(conn, *args, **kwargs)`, potem wpis
    w dzienniku. Migawka poprzedza wykonanie, nie następuje po nim -
    inaczej cofnięcie przywracałoby stan już zepsuty przez tę samą operację.

    `licz_pominiete` (0.1-alpha.3.2): jak `licz_wiersze`, ale dla liczby
    wierszy POMINIĘTYCH (np. `licz_pominiete_wiersze` dla wyniku
    `repo.zapisz_blankiet`) - bez tego wpis "wszystkie wiersze pominięte
    jako duplikaty" wygląda w dzienniku identycznie jak pełny sukces.

    Wyjątek z `funkcja` jest logowany (wynik="blad") i podniesiony dalej -
    migawka sprzed operacji zostaje, żeby dziennik pozostał kompletnym
    śladem tego, co się stało, nawet gdy operacja się nie powiodła.
    """
    kwargs = kwargs or {}
    seq = dziennik.nastepny_seq(katalog_danych)
    plik_migawki = kopie.zrob_migawke(conn, katalog_danych, seq)
    teraz = datetime.now().isoformat(timespec="seconds")

    try:
        wynik = funkcja(conn, *args, **kwargs)
    except Exception:
        dziennik.zapisz_operacje(
            katalog_danych, seq=seq, rodzaj=rodzaj, etykieta=etykieta,
            wersja_schematu=repo.wersja_schematu(conn),
            plik_migawki=str(plik_migawki), wynik="blad", czas=teraz,
        )
        raise

    dziennik.zapisz_operacje(
        katalog_danych, seq=seq, rodzaj=rodzaj, etykieta=etykieta,
        liczba_wierszy=licz_wiersze(wynik) if licz_wiersze else None,
        liczba_pominietych=licz_pominiete(wynik) if licz_pominiete else None,
        wersja_schematu=repo.wersja_schematu(conn),
        plik_migawki=str(plik_migawki), wynik="ok", czas=teraz,
    )
    return wynik


def cofnij(katalog_danych, sciezka_bazy, seq_docelowy):
    """
    Przywraca bazę do stanu SPRZED operacji `seq_docelowy` - czyli migawki
    zapisanej dla niej przez `wykonaj` (migawka jest robiona PRZED
    wykonaniem). Cofa też wszystko, co wydarzyło się PO tej operacji - to
    przywrócenie do punktu w czasie, nie selektywne cofnięcie jednej zmiany.

    Samo cofnięcie jest też logowane jako nowa operacja (z własną migawką
    sprzed cofnięcia), więc "cofnięcie cofnięcia" jest możliwe tym samym
    mechanizmem.

    WYMAGA zamkniętego połączenia z bazą - podmiana pliku pod otwartym
    uchwytem jest niebezpieczna. Zamknięcie/otwarcie `conn` należy do
    wywołującego (GUI, zakładka Historia).
    """
    wpisy = {w["seq"]: w for w in dziennik.wczytaj_operacje(katalog_danych)}
    wpis = wpisy.get(seq_docelowy)
    if wpis is None:
        raise ValueError(f"Nieznana operacja: {seq_docelowy}")
    plik_migawki = wpis.get("plik_migawki")
    if not plik_migawki:
        raise ValueError(f"Operacja {seq_docelowy} nie ma migawki")
    if not Path(plik_migawki).exists():
        # migawka mogła zostać przycięta (kopie.przytnij_migawki) - sprawdzone
        # PRZED zrobieniem migawki bezpieczeństwa, żeby jej nie marnować
        raise ValueError(
            f"Migawka operacji {seq_docelowy} już nie istnieje (przycięta) - "
            f"cofnięcie do tego punktu nie jest już możliwe")

    seq = dziennik.nastepny_seq(katalog_danych)
    migawka_przed_cofnieciem = kopie.zrob_migawke_pliku(
        sciezka_bazy, katalog_danych, seq)

    kopie.przywroc_migawke(sciezka_bazy, plik_migawki)

    dziennik.zapisz_operacje(
        katalog_danych, seq=seq, rodzaj="cofniecie",
        etykieta=f"cofnięto do operacji #{seq_docelowy}",
        plik_migawki=str(migawka_przed_cofnieciem), wynik="ok",
        czas=datetime.now().isoformat(timespec="seconds"),
    )


def znajdz_najblizsze_migawki(katalog_danych, seq_docelowy):
    """
    Gdy migawka operacji `seq_docelowy` zniknęła (przycięta przez
    `kopie.przytnij_migawki`), szuka najbliższych INNYCH operacji - jednej
    starszej, jednej nowszej - których migawka WCIĄŻ istnieje na dysku.
    To alternatywy do zaoferowania użytkownikowi zamiast ślepego błędu
    (patrz zakładka Historia). Zwraca (poprzednia, nastepna); każde z nich
    to wpis z dziennika albo `None`, gdy takiej operacji nie ma.
    """
    wpisy = sorted(dziennik.wczytaj_operacje(katalog_danych), key=lambda w: w["seq"])

    def ma_zywa_migawke(w):
        plik = w.get("plik_migawki")
        return bool(plik) and Path(plik).exists()

    poprzednia = None
    nastepna = None
    for w in wpisy:
        if w["seq"] < seq_docelowy and ma_zywa_migawke(w):
            poprzednia = w
        elif w["seq"] > seq_docelowy and ma_zywa_migawke(w) and nastepna is None:
            nastepna = w
    return poprzednia, nastepna


def licz_zapisane_wiersze(wyniki_zapisz_blankiet):
    """Helper dla `licz_wiersze` przy `repo.zapisz_blankiet` - pomija duplikaty."""
    return sum(1 for w in wyniki_zapisz_blankiet if not w["pominieto"])


def licz_pominiete_wiersze(wyniki_zapisz_blankiet):
    """Helper dla `licz_pominiete` przy `repo.zapisz_blankiet` (0.1-alpha.3.2)."""
    return sum(1 for w in wyniki_zapisz_blankiet if w["pominieto"])

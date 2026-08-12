"""
dedukcja.py: silnik dedukcji pól formularza wprowadzania z bazy. Czysta
logika, bez display. TDD.

Zasada jednolita (Papaver, 2026-08-12): jednoznaczne -> wypełniamy;
niejednoznaczne -> NIE wypełniamy, aktywujemy pole, warianty jako
kandydatów. Rejon z adresu, wykonawca z kuriera. PNI WYŁĄCZNIE z
rozstrzygniętego punktu, nigdy niezależnie od nadawcy (patrz test poniżej
z adresem o dwóch nadawcach - to konkretny błąd złapany przy planowaniu:
9,4% wierszy realnej próbki jest pod adresami z >1 nadawcą).

Ilość/"w tym ZPO" NIGDY nie są źródłem ani bramą dedukcji innych pól -
osobna poprawka Papavera, testowana explicite niżej.
"""
from datetime import date

import pytest

from zpo_tracker import dedukcja, repo
from zpo_tracker.dedukcja import StanPola, sprawdz_niezmienniki
from zpo_tracker.models import Blankiet, WierszBlankietu


@pytest.fixture
def conn():
    conn = repo.polacz(":memory:")
    repo.utworz_schemat(conn)
    yield conn
    conn.close()


def _blok(rejon="WA87", **nadpisz):
    wiersze = nadpisz.pop("wiersze", None)
    if wiersze is None:
        wiersze = [WierszBlankietu(
            nadawca="Żabka", adres="Odkryta 24", rejon=rejon,
            pni_zpo="228648", ilosc_total=3, ilosc_zpo=3)]
    dane = dict(kurier="Kowalski Jan", data=date(2026, 8, 10), wykonawca="Koli", wiersze=wiersze)
    dane.update(nadpisz)
    return Blankiet(**dane)


# --- dedukuj_wiersz: adres pusty ---

def test_adres_pusty_wszystko_szare_nieaktywne(conn):
    wynik = dedukcja.dedukuj_wiersz(conn, kurier="Kowalski Jan", adres="")
    assert wynik.punkt_id is None
    for klucz in ("nadawca", "pni_zpo", "rejon"):
        assert wynik.pola[klucz].stan == "szary"
        assert wynik.pola[klucz].aktywne is False


# --- dedukuj_wiersz: adres -> dokładnie 1 punkt ---

def test_jeden_punkt_deukuje_nadawce_pni_i_rejon(conn):
    repo.zapisz_blankiet(conn, _blok())
    wynik = dedukcja.dedukuj_wiersz(conn, kurier="Kowalski Jan", adres="Odkryta 24")
    assert wynik.punkt_id is not None
    assert wynik.pola["nadawca"] == StanPola(wartosc="Żabka", stan="zielony", aktywne=False)
    assert wynik.pola["pni_zpo"].wartosc == "228648"
    assert wynik.pola["pni_zpo"].stan == "zielony"
    assert wynik.pola["rejon"] == StanPola(wartosc="WA87", stan="zielony", aktywne=False)


def test_jeden_punkt_bez_pni_zwyklego_nadawcy_jest_zielony(conn):
    repo.zapisz_blankiet(conn, _blok(wiersze=[
        WierszBlankietu(nadawca="ZUS", adres="Senatorska 6/8", ilosc_total=1)]))
    wynik = dedukcja.dedukuj_wiersz(conn, kurier="Kowalski Jan", adres="Senatorska 6/8")
    assert wynik.pola["pni_zpo"].stan == "zielony"
    assert wynik.pola["pni_zpo"].wartosc is None


def test_jeden_punkt_bez_pni_ale_nadawca_to_znana_siec_zpo_daje_pomaranczowy(conn):
    # ten sam nadawca MA PNI w innej lokalizacji - ten konkretny punkt
    # najwyraźniej go nie ma zarejestrowanego, warto sprawdzić
    repo.zapisz_blankiet(conn, _blok())  # Żabka, Odkryta 24, PNI=228648
    repo.zapisz_blankiet(conn, _blok(wiersze=[
        WierszBlankietu(nadawca="Żabka", adres="Inna 5", ilosc_total=1)]))  # bez PNI
    wynik = dedukcja.dedukuj_wiersz(conn, kurier="Kowalski Jan", adres="Inna 5")
    assert wynik.pola["pni_zpo"].stan == "pomaranczowy"
    assert wynik.pola["pni_zpo"].aktywne is True


# --- dedukuj_wiersz: adres -> wiele punktów (niejednoznaczność) ---

def test_wiele_nadawcow_pod_adresem_nie_wypelnia_i_aktywuje(conn):
    repo.zapisz_blankiet(conn, _blok())  # Żabka, Odkryta 24
    repo.zapisz_blankiet(conn, _blok(wiersze=[
        WierszBlankietu(nadawca="Gemartis", adres="Odkryta 24", ilosc_total=1)]))
    wynik = dedukcja.dedukuj_wiersz(conn, kurier="Kowalski Jan", adres="Odkryta 24")
    assert wynik.punkt_id is None
    assert wynik.pola["nadawca"].stan == "pomaranczowy"
    assert wynik.pola["nadawca"].wartosc is None  # NIE wypełniamy przy niejednoznaczności
    assert set(wynik.pola["nadawca"].kandydaci) == {"Żabka", "Gemartis"}
    assert wynik.pola["nadawca"].aktywne is True
    assert wynik.pola["nadawca"].w_nawigacji is True


def test_pni_nie_dedukowane_niezaleznie_gdy_nadawca_niejednoznaczny(conn):
    # SEDNO POPRAWKI Z PRZEGLĄDU: mimo że jeden z dwóch punktów pod tym
    # adresem MA jednoznaczne PNI, nie wolno go użyć - to właśnie
    # powodowało ciche podpięcie transakcji pod zły punkt
    repo.zapisz_blankiet(conn, _blok())  # Żabka, PNI=228648 - jednoznaczne PNI
    repo.zapisz_blankiet(conn, _blok(wiersze=[
        WierszBlankietu(nadawca="Gemartis", adres="Odkryta 24", ilosc_total=1)]))
    wynik = dedukcja.dedukuj_wiersz(conn, kurier="Kowalski Jan", adres="Odkryta 24")
    assert wynik.pola["pni_zpo"].wartosc is None
    assert wynik.pola["pni_zpo"].stan != "zielony"


def test_nadawca_podany_recznie_zawęża_niejednoznaczny_adres(conn):
    repo.zapisz_blankiet(conn, _blok())  # Żabka, Odkryta 24
    repo.zapisz_blankiet(conn, _blok(wiersze=[
        WierszBlankietu(nadawca="Gemartis", adres="Odkryta 24", ilosc_total=1)]))
    wynik = dedukcja.dedukuj_wiersz(
        conn, kurier="Kowalski Jan", adres="Odkryta 24", nadawca="Gemartis")
    assert wynik.punkt_id is not None
    assert len(wynik.kandydaci_punktow) == 1
    # rozstrzygnięte -> PNI też może być teraz jednoznacznie wyprowadzone
    # (Gemartis nie ma PNI w tym scenariuszu)
    assert wynik.pola["pni_zpo"].stan == "zielony"
    assert wynik.pola["pni_zpo"].wartosc is None


# --- dedukuj_wiersz: adres -> zero punktów (nowy punkt) ---

def test_nowy_adres_nadawca_czerwony_i_w_nawigacji(conn):
    wynik = dedukcja.dedukuj_wiersz(conn, kurier="Kowalski Jan", adres="Nowa Ulica 1")
    assert wynik.punkt_id is None
    assert wynik.kandydaci_punktow == ()
    assert wynik.pola["nadawca"].stan == "czerwony"
    assert wynik.pola["nadawca"].aktywne is True
    assert wynik.pola["nadawca"].w_nawigacji is True


# --- dedukuj_wiersz: rejon - historia punktu ---

def test_rejon_wiele_w_historii_nie_wypelnia(conn):
    repo.zapisz_blankiet(conn, _blok(rejon="WA87", data=date(2026, 8, 1)))
    repo.zapisz_blankiet(conn, _blok(rejon="WA88", data=date(2026, 8, 2)))
    wynik = dedukcja.dedukuj_wiersz(conn, kurier="Kowalski Jan", adres="Odkryta 24")
    assert wynik.pola["rejon"].stan == "pomaranczowy"
    assert wynik.pola["rejon"].wartosc is None
    assert set(wynik.pola["rejon"].kandydaci) == {"WA87", "WA88"}


def test_rejon_punkt_bez_historii_transakcji(conn):
    # punkt istnieje (przez get_or_create_punkt), ale nigdy nie było
    # transakcji - nic do zdedukowania, ale pole aktywne, żeby dało się uzupełnić
    from zpo_tracker.importer import get_or_create_punkt
    get_or_create_punkt(conn, "Żabka", "Świeży Adres 1", "999999")
    wynik = dedukcja.dedukuj_wiersz(conn, kurier="Kowalski Jan", adres="Świeży Adres 1")
    assert wynik.punkt_id is not None
    assert wynik.pola["rejon"].stan == "pomaranczowy"
    assert wynik.pola["rejon"].aktywne is True


# --- dedukuj_wiersz: adres dopasowany rozmyto (repo.znajdz_punkty_po_adresie) ---

def test_adres_wpisany_niedokladnie_wciaz_deukuje(conn):
    repo.zapisz_blankiet(conn, _blok())
    wynik = dedukcja.dedukuj_wiersz(conn, kurier="Kowalski Jan", adres="odkryta  24")
    assert wynik.punkt_id is not None
    assert wynik.pola["nadawca"].wartosc == "Żabka"


# --- dedukuj_wiersz: ilosc_zpo - NIGDY bramowane przez ilość, tylko przez PNI nadawcy ---

def test_ilosc_zpo_aktywne_gdy_nadawca_ma_pni_gdziekolwiek(conn):
    repo.zapisz_blankiet(conn, _blok())  # Żabka ma PNI
    wynik = dedukcja.dedukuj_wiersz(
        conn, kurier="Kowalski Jan", adres="Odkryta 24", ilosc_total=5)
    assert wynik.pola["ilosc_zpo"].aktywne is True
    assert wynik.pola["ilosc_zpo"].wartosc == 5  # autouzupełnione z Ilości


def test_ilosc_zpo_nieaktywne_dla_zwyklego_nadawcy(conn):
    repo.zapisz_blankiet(conn, _blok(wiersze=[
        WierszBlankietu(nadawca="ZUS", adres="Senatorska 6/8", ilosc_total=1)]))
    wynik = dedukcja.dedukuj_wiersz(
        conn, kurier="Kowalski Jan", adres="Senatorska 6/8", ilosc_total=5)
    assert wynik.pola["ilosc_zpo"].aktywne is False
    assert wynik.pola["ilosc_zpo"].wartosc is None


def test_ilosc_pusta_nie_blokuje_dedukcji_pozostalych_pol(conn):
    # POPRAWKA PAPAVERA 2026-08-12: dedukcja rusza z kuriera/adresu,
    # NIGDY nie czeka na wypełnienie Ilości
    repo.zapisz_blankiet(conn, _blok())
    wynik = dedukcja.dedukuj_wiersz(
        conn, kurier="Kowalski Jan", adres="Odkryta 24", ilosc_total=None)
    assert wynik.pola["nadawca"].stan == "zielony"
    assert wynik.pola["rejon"].stan == "zielony"
    # ilosc_zpo samo w sobie AKTYWNE mimo braku ilosc_total - tylko autofill
    # wartości (nie sama aktywność) zależy od Ilości
    assert wynik.pola["ilosc_zpo"].aktywne is True
    assert wynik.pola["ilosc_zpo"].wartosc is None


def test_ilosc_zpo_juz_wpisana_recznie_nie_jest_nadpisywana(conn):
    repo.zapisz_blankiet(conn, _blok())
    wynik = dedukcja.dedukuj_wiersz(
        conn, kurier="Kowalski Jan", adres="Odkryta 24", ilosc_total=5, ilosc_zpo=2)
    assert wynik.pola["ilosc_zpo"].wartosc == 2


# --- dedukuj_naglowek: wykonawca z historii kuriera ---

def test_naglowek_jeden_wykonawca_w_historii(conn):
    repo.zapisz_blankiet(conn, _blok(wykonawca="Koli"))
    pola = dedukcja.dedukuj_naglowek(conn, kurier="Kowalski Jan", data=date(2026, 8, 11))
    assert pola["wykonawca"] == StanPola(wartosc="Koli", stan="zielony", aktywne=False)


def test_naglowek_wielu_wykonawcow_posortowani_po_swiezosci(conn):
    repo.zapisz_blankiet(conn, _blok(wykonawca="Koli", data=date(2026, 8, 1)))
    repo.zapisz_blankiet(conn, _blok(wykonawca="Koli", data=date(2026, 8, 2)))
    repo.zapisz_blankiet(conn, _blok(wykonawca="Translist", data=date(2026, 8, 5)))
    pola = dedukcja.dedukuj_naglowek(conn, kurier="Kowalski Jan", data=date(2026, 8, 11))
    assert pola["wykonawca"].stan == "pomaranczowy"
    assert pola["wykonawca"].wartosc is None
    assert pola["wykonawca"].kandydaci[0] == "Translist"  # najświeższy pierwszy


def test_naglowek_nowy_kurier_pomaranczowy(conn):
    pola = dedukcja.dedukuj_naglowek(conn, kurier="Nowy Kurier", data=date(2026, 8, 11))
    assert pola["wykonawca"].stan == "pomaranczowy"
    assert pola["wykonawca"].aktywne is True


def test_naglowek_pusty_kurier_szary(conn):
    pola = dedukcja.dedukuj_naglowek(conn, kurier="", data=date(2026, 8, 11))
    assert pola["wykonawca"].stan == "szary"
    assert pola["wykonawca"].aktywne is False


# --- sprawdz_niezmienniki ---

def test_niezmiennik_pomaranczowy_musi_byc_aktywne():
    with pytest.raises(AssertionError):
        sprawdz_niezmienniki({"x": StanPola(stan="pomaranczowy", aktywne=False)}, tryb="auto")


def test_niezmiennik_czerwony_musi_byc_aktywne():
    with pytest.raises(AssertionError):
        sprawdz_niezmienniki({"x": StanPola(stan="czerwony", aktywne=False)}, tryb="auto")


def test_niezmiennik_aktywne_nieszare_musi_byc_w_nawigacji():
    with pytest.raises(AssertionError):
        sprawdz_niezmienniki(
            {"x": StanPola(stan="pomaranczowy", aktywne=True, w_nawigacji=False)}, tryb="auto")


def test_niezmienniki_poprawny_stan_przechodzi():
    sprawdz_niezmienniki({
        "a": StanPola(stan="zielony", aktywne=False),
        "b": StanPola(stan="pomaranczowy", aktywne=True, w_nawigacji=True),
        "c": StanPola(stan="czerwony", aktywne=True, w_nawigacji=True),
        "d": StanPola(stan="szary", aktywne=False),
    }, tryb="auto")  # nie rzuca


# --- kolejnosc_pol ---

def test_kolejnosc_auto_zawiera_pola_glowne(conn):
    naglowek = dedukcja.dedukuj_naglowek(conn, kurier="Kowalski Jan", data=date(2026, 8, 11))
    wiersz = dedukcja.dedukuj_wiersz(conn, kurier="Kowalski Jan", adres="Odkryta 24")
    kolejnosc = dedukcja.kolejnosc_pol("auto", naglowek, [wiersz])
    assert ("naglowek", "kurier") in kolejnosc
    assert ("naglowek", "data") in kolejnosc
    assert ("wiersz", 0, "adres") in kolejnosc
    assert ("wiersz", 0, "ilosc_total") in kolejnosc


def test_kolejnosc_auto_wlacza_niejednoznaczne_pole_drugorzedne(conn):
    repo.zapisz_blankiet(conn, _blok())
    repo.zapisz_blankiet(conn, _blok(wiersze=[
        WierszBlankietu(nadawca="Gemartis", adres="Odkryta 24", ilosc_total=1)]))
    naglowek = dedukcja.dedukuj_naglowek(conn, kurier="Kowalski Jan", data=date(2026, 8, 11))
    wiersz = dedukcja.dedukuj_wiersz(conn, kurier="Kowalski Jan", adres="Odkryta 24")
    kolejnosc = dedukcja.kolejnosc_pol("auto", naglowek, [wiersz])
    # pole "nadawca" jest niejednoznaczne (pomarańcz, w_nawigacji) - MUSI
    # być osiągalne Tabem, inaczej nie da się go wypełnić z klawiatury
    assert ("wiersz", 0, "nadawca") in kolejnosc


def test_kolejnosc_auto_pomija_dedukowane_jednoznacznie(conn):
    repo.zapisz_blankiet(conn, _blok())
    naglowek = dedukcja.dedukuj_naglowek(conn, kurier="Kowalski Jan", data=date(2026, 8, 11))
    wiersz = dedukcja.dedukuj_wiersz(conn, kurier="Kowalski Jan", adres="Odkryta 24")
    kolejnosc = dedukcja.kolejnosc_pol("auto", naglowek, [wiersz])
    assert ("wiersz", 0, "nadawca") not in kolejnosc
    assert ("wiersz", 0, "rejon") not in kolejnosc


def test_kolejnosc_nieznany_tryb_rzuca(conn):
    naglowek = dedukcja.dedukuj_naglowek(conn, kurier="Kowalski Jan", data=date(2026, 8, 11))
    with pytest.raises(NotImplementedError):
        dedukcja.kolejnosc_pol("polauto", naglowek, [])


# --- przesun_w_kolejnosci: Tab/Enter (+1) i Shift-Tab/ISO_Left_Tab (-1) ---

def test_przesun_do_przodu_zwraca_nastepny_klucz():
    kolejnosc = [("naglowek", "kurier"), ("naglowek", "data"), ("wiersz", 0, "adres")]
    assert dedukcja.przesun_w_kolejnosci(kolejnosc, ("naglowek", "kurier"), 1) == ("naglowek", "data")


def test_przesun_do_tylu_zwraca_poprzedni_klucz():
    kolejnosc = [("naglowek", "kurier"), ("naglowek", "data"), ("wiersz", 0, "adres")]
    assert dedukcja.przesun_w_kolejnosci(kolejnosc, ("wiersz", 0, "adres"), -1) == ("naglowek", "data")


def test_przesun_do_przodu_zawija_na_koncu():
    kolejnosc = [("naglowek", "kurier"), ("naglowek", "data")]
    assert dedukcja.przesun_w_kolejnosci(kolejnosc, ("naglowek", "data"), 1) == ("naglowek", "kurier")


def test_przesun_do_tylu_zawija_na_poczatku():
    kolejnosc = [("naglowek", "kurier"), ("naglowek", "data")]
    assert dedukcja.przesun_w_kolejnosci(kolejnosc, ("naglowek", "kurier"), -1) == ("naglowek", "data")


def test_przesun_gdy_biezace_pole_nie_jest_w_kolejnosci_zaczyna_od_poczatku():
    # np. fokus wszedł do formularza z zewnątrz (kliknięcie myszą w pole
    # nieaktywne, które nie jest w kolejnosci) - Tab musi mimo to gdzieś
    # wylądować, nie wybuchnąć ValueError
    kolejnosc = [("naglowek", "kurier"), ("naglowek", "data")]
    assert dedukcja.przesun_w_kolejnosci(kolejnosc, ("wiersz", 0, "pni_zpo"), 1) == ("naglowek", "kurier")
    assert dedukcja.przesun_w_kolejnosci(kolejnosc, ("wiersz", 0, "pni_zpo"), -1) == ("naglowek", "data")


def test_przesun_pusta_kolejnosc_zwraca_none():
    assert dedukcja.przesun_w_kolejnosci([], ("naglowek", "kurier"), 1) is None

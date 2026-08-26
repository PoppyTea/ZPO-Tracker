"""
Testy dla normalizacji tekstu i dedupu literówek. TDD.
Wzorzec kluczy (klucz_bialych_znakow/klucz_rozmyty) przeniesiony
z demo/przeglad-kurierow-prototyp.html (wsKey/fuzzyKey).
"""
import pytest

from zpo_tracker import normalizacja
from zpo_tracker.normalizacja import (
    REJON_NIEZNANY,
    klucz_bialych_znakow,
    klucz_rozmyty,
    normalizuj_rejon,
    odleglosc_edycyjna,
    czy_literowka,
    grupuj_bezpiecznie,
    znajdz_podobne,
)


# --- klucz_bialych_znakow: bezpieczna normalizacja (trim + collapse) ---

def test_klucz_bialych_znakow_trimuje_i_collapsuje():
    assert klucz_bialych_znakow("  Michalak   Maciej ") == "Michalak Maciej"


def test_klucz_bialych_znakow_tabulatory_i_nowe_linie():
    assert klucz_bialych_znakow("Jan\tKowalski\n") == "Jan Kowalski"


def test_klucz_bialych_znakow_identyczny_string_bez_zmian():
    assert klucz_bialych_znakow("Jan Kowalski") == "Jan Kowalski"


# --- klucz_rozmyty: lowercase + bez polskich znaków + białe znaki ---

def test_klucz_rozmyty_usuwa_diakrytyki_i_wielkosc_liter():
    assert klucz_rozmyty("Wołczuk Rafał") == klucz_rozmyty("wolczuk rafal")


def test_klucz_rozmyty_odroznia_realnie_rozne_nazwiska():
    assert klucz_rozmyty("Kowalski Jan") != klucz_rozmyty("Nowak Jan")


# --- odleglosc_edycyjna: dystans z transpozycją sąsiednich znaków jako 1 ---

def test_odleglosc_edycyjna_identyczne_stringi():
    assert odleglosc_edycyjna("Kowalski", "Kowalski") == 0


def test_odleglosc_edycyjna_jedna_litera_inna():
    assert odleglosc_edycyjna("Kowalski", "Kowalsku") == 1


def test_odleglosc_edycyjna_transpozycja_sasiednich_znakow():
    # najczęstszy typ literówki z klawiatury - zamienione dwie sąsiednie litery
    assert odleglosc_edycyjna("Kowalski", "Kowalksi") == 1


def test_odleglosc_edycyjna_rozne_dlugosci():
    assert odleglosc_edycyjna("Kowalski", "Kowalscy") == 2


# --- czy_literowka: automatyczny dedup, ale tylko realne literówki ---

def test_czy_literowka_true_dla_bliskiego_dystansu():
    assert czy_literowka("Kowalski Jan", "Kowalksi Jan") is True


def test_czy_literowka_false_dla_roznych_nazwisk():
    assert czy_literowka("Kowalski Jan", "Nowak Jan") is False


def test_czy_literowka_false_gdy_to_juz_ta_sama_fuzzy_forma():
    # różnica tylko w diakrytykach/wielkości liter to nie "literówka" do
    # automatycznego scalenia - to sprawa dla znajdz_podobne (decyzja czlowieka)
    assert czy_literowka("Wołczuk Rafał", "Wolczuk Rafal") is False


# --- grupuj_bezpiecznie: automatyczne scalanie WYŁĄCZNIE po białych znakach ---

def test_grupuj_bezpiecznie_scala_warianty_bialych_znakow():
    grupy = grupuj_bezpiecznie(["Michalak Maciej", "Michalak Maciej ", "Zdun Piotr"])
    assert len(grupy) == 2
    michalak = next(g for g in grupy if g.kanoniczna == "Michalak Maciej")
    assert michalak.liczba == 2


def test_grupuj_bezpiecznie_nie_scala_roznic_diakrytykow():
    # to jest sedno: różnica w "ł"/"l" NIE jest bezpiecznym scaleniem
    grupy = grupuj_bezpiecznie(["Wołczuk Rafał", "Wołczuk Rafal"])
    assert len(grupy) == 2


# --- znajdz_podobne: miękkie ostrzeżenie, nigdy automatyczne scalanie ---

def test_znajdz_podobne_wykrywa_roznice_diakrytykow():
    grupy = grupuj_bezpiecznie(["Wołczuk Rafał", "Wołczuk Rafal"])
    ostrzezenia = znajdz_podobne(grupy)
    assert len(ostrzezenia) == 1


def test_znajdz_podobne_nie_zglasza_realnie_roznych_nazwisk():
    grupy = grupuj_bezpiecznie(["Kowalski Jan", "Nowak Jan"])
    assert znajdz_podobne(grupy) == []


# --- normalizuj_rejon: kanoniczny "rejon nieznany" (??? ) ---

def test_normalizuj_rejon_prawidlowy_kod_zostaje_bez_zmian():
    assert normalizuj_rejon("WA87") == "WA87"


def test_normalizuj_rejon_puste_i_none_daja_nieznany():
    assert normalizuj_rejon(None) == REJON_NIEZNANY
    assert normalizuj_rejon("") == REJON_NIEZNANY
    assert normalizuj_rejon("   ") == REJON_NIEZNANY


def test_normalizuj_rejon_znak_zapytania_daje_nieznany():
    assert normalizuj_rejon("?") == REJON_NIEZNANY
    assert normalizuj_rejon("WA?7") == REJON_NIEZNANY


def test_normalizuj_rejon_spacja_w_srodku_daje_nieznany():
    # spacja w kodzie rejonu to zawsze artefakt wpisywania, nie prawdziwy kod
    assert normalizuj_rejon("WA 87") == REJON_NIEZNANY


def test_normalizuj_rejon_smieciowe_wartosci_daja_nieznany():
    for smiec in ("-", "n/a", "N/A", "null", "NULL"):
        assert normalizuj_rejon(smiec) == REJON_NIEZNANY


def test_normalizuj_rejon_jest_idempotentny():
    assert normalizuj_rejon(REJON_NIEZNANY) == REJON_NIEZNANY


# --- rejon z eksportu BaŚKi (0.1-alpha.3.3) ----------------------------
#
# Reguła potwierdzona naocznie w przeglądarce 2026-08-23: interesują nas
# rejony węzła WW o typie kierowania 1, a do numeru doklejamy literał
# "WA". UWAGA: "WA" NIE jest kodem węzła źródłowego - w BaŚce istnieje
# osobny węzeł o kodzie WA (WER Warszawa W101, ul. Łączyny) i to zupełnie
# inny byt. Wnioskowanie "prefiks = kod węzła" jest błędne, mimo że
# dokumentacja i przykłady w API pozornie je potwierdzają.

def test_goly_numer_dostaje_prefiks_wa():
    assert normalizacja.normalizuj_rejon_baska("119") == "WA119"


def test_numer_z_litera_na_koncu_tez_dostaje_prefiks():
    assert normalizacja.normalizuj_rejon_baska("21A") == "WA21A"


def test_biale_znaki_wokol_numeru_nie_przeszkadzaja():
    assert normalizacja.normalizuj_rejon_baska("  119  ") == "WA119"


def test_jest_idempotentna_dla_kodu_juz_z_prefiksem():
    """Backfill i ponowny import muszą móc przejechać po tych samych
    danych bez robienia z WA119 -> WAWA119."""
    assert normalizacja.normalizuj_rejon_baska("WA119") == "WA119"


def test_kod_z_innym_prefiksem_zostaje_nietkniety():
    """W bazie żyją kody typu Z3/L11/ND1 z wcześniejszej epoki danych.
    Doklejenie WA dałoby WAZ3 - gorzej niż zostawienie jak jest."""
    assert normalizacja.normalizuj_rejon_baska("ND1") == "ND1"
    assert normalizacja.normalizuj_rejon_baska("l11") == "L11"


@pytest.mark.parametrize("wartownik", ["*UP", "ZPO", "UP", "AP", "FUP"])
def test_wartownicy_baski_sa_rejonem_nieznanym(wartownik):
    """Wszystkie pięć stoi w drzewie ścieżek jako rodzeństwo rejonów
    numerycznych, ale żaden nie jest kodem rejonu. Instrukcja mówi wprost
    o *UP: 'należy zmienić pozycje oznaczone *UP poprzez uzupełnienie
    właściwego rejonu doręczeń'."""
    assert normalizacja.normalizuj_rejon_baska(wartownik) == normalizacja.REJON_NIEZNANY


@pytest.mark.parametrize("wartownik", ["zpo", "  fup  ", "*up"])
def test_wartownicy_lapia_sie_niezaleznie_od_wielkosci_liter(wartownik):
    assert normalizacja.normalizuj_rejon_baska(wartownik) == normalizacja.REJON_NIEZNANY


@pytest.mark.parametrize("puste", [None, "", "   "])
def test_brak_wartosci_to_rejon_nieznany(puste):
    assert normalizacja.normalizuj_rejon_baska(puste) == normalizacja.REJON_NIEZNANY


@pytest.mark.parametrize("sciezka", ["PO-1----", "KA-2----", "WA-1----119"])
def test_sciezka_czesciowa_nie_jest_rejonem(sciezka):
    """BaŚKa sama oznacza je komunikatem 'Znaleziona ścieżka nie jest
    ścieżką pełną!'. Do kolumny rejonu nie mają prawa wejść."""
    assert normalizacja.normalizuj_rejon_baska(sciezka) == normalizacja.REJON_NIEZNANY


@pytest.mark.parametrize("smiec", ["-", "n/a", "NULL", "119 120", "12?"])
def test_smieci_lapia_sie_tak_samo_jak_w_starej_regule(smiec):
    assert normalizacja.normalizuj_rejon_baska(smiec) == normalizacja.REJON_NIEZNANY


def test_prefiks_jest_stala_nie_literalem_w_kodzie():
    assert normalizacja.PREFIKS_REJONU_WARSZAWA == "WA"


# --- kody czysto literowe: znalezisko z realnego eksportu WER Ciemne ---
#
# Plik "WW - WER Ciemne" ma 219 arkuszy, po jednym na rejon. Nasza reguła
# odrzucała z nich SIEDEM, bo wzorzec wymagał cyfry: MIG, POU, PP, RDH,
# WER, WRC, WRT. RDH niesie realne adresy, więc było to ciche gubienie
# danych. Pozostałe sześć jest dziś puste, ale to kwestia szczęścia,
# nie poprawności - w liście rejonów BaŚKi stoją na równi z resztą.

@pytest.mark.parametrize("kod", ["MIG", "POU", "PP", "RDH", "WER", "WRC", "WRT"])
def test_kod_czysto_literowy_jest_prawidlowym_rejonem(kod):
    assert normalizacja.normalizuj_rejon_baska(kod) == kod


def test_kod_czysto_literowy_dostaje_wielkie_litery():
    assert normalizacja.normalizuj_rejon_baska("rdh") == "RDH"


@pytest.mark.parametrize("wartownik", ["UP", "AP", "FUP", "ZPO"])
def test_wartownicy_nadal_wygrywaja_z_regula_literowa(wartownik):
    """Krytyczne rozróżnienie: `PP` i `WER` to rejony, a `UP`, `AP`, `FUP`
    i `ZPO` to wartownicy - mimo że wszystkie są czysto literowe. Nie da
    się ich odróżnić kształtem, więc lista wartowników musi być jawna
    i sprawdzana PRZED regułą kształtu."""
    assert normalizacja.normalizuj_rejon_baska(wartownik) == normalizacja.REJON_NIEZNANY


@pytest.mark.parametrize("smiec", ["ABCDE", "A", "Warszawa"])
def test_zbyt_dlugie_i_zbyt_krotkie_nadal_odrzucane(smiec):
    """Poluzowanie nie może zamienić się w przyjmowanie czegokolwiek -
    realne kody mają od dwóch do czterech liter."""
    assert normalizacja.normalizuj_rejon_baska(smiec) == normalizacja.REJON_NIEZNANY

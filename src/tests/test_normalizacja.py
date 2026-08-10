"""
Testy dla normalizacji tekstu i dedupu literówek. TDD.
Wzorzec kluczy (klucz_bialych_znakow/klucz_rozmyty) przeniesiony
z demo/przeglad-kurierow-prototyp.html (wsKey/fuzzyKey).
"""
from zpo_tracker.normalizacja import (
    klucz_bialych_znakow,
    klucz_rozmyty,
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

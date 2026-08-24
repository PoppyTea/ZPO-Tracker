"""
profil_kolumn: dopasowanie kolumn arkusza po NAGŁÓWKU, nie po pozycji.

Dziś import Excela dopasowuje nagłówki przez dokładne porównanie stringów
(import_orchestrator.MAPA_NAGLOWKOW), więc " Pełna Nazwa Nadawcy" ze
spacją na początku jest czymś innym niż "Pełna Nazwa Nadawcy", a brakująca
kolumna ujawnia się dopiero jako ValidationError pydantic gdzieś dalej.
Ten moduł ma robić to samo odporniej i mówić wprost, czego zabrakło.

Drugi powód istnienia: profil może pomijać kolumny, więc selektywny import
wybranych pozycji (przydatny przy danych historycznych) wychodzi za darmo.
"""
import pytest

from zpo_tracker import profil_kolumn


PROFIL_TESTOWY = profil_kolumn.Profil(
    pola={
        "miejscowosc": ["Miejscowość"],
        "ulica": ["Ulica"],
        "nr": ["Nr", "Nr domu"],
        "pna": ["PNA"],
        "rejon": ["Rejon"],
    },
    wymagane={"miejscowosc", "ulica", "nr", "rejon"},
)


# --- dopasowanie nagłówków ---------------------------------------------

def test_dokladny_naglowek_trafia_w_pole():
    d = profil_kolumn.dopasuj_kolumny(
        ["Miejscowość", "Ulica", "Nr", "Rejon"], PROFIL_TESTOWY)
    assert d.mapowanie["Miejscowość"] == "miejscowosc"
    assert d.mapowanie["Rejon"] == "rejon"
    assert d.braki == []


def test_wielkosc_liter_i_diakrytyki_nie_przeszkadzaja():
    """Eksport z BaŚKi ma sześć lat i nikt nie obiecywał, że nagłówki są
    stabilne co do znaku."""
    d = profil_kolumn.dopasuj_kolumny(
        ["MIEJSCOWOSC", "ulica", "NR", "rejon"], PROFIL_TESTOWY)
    assert d.mapowanie["MIEJSCOWOSC"] == "miejscowosc"
    assert d.mapowanie["ulica"] == "ulica"
    assert d.braki == []


def test_biale_znaki_wokol_naglowka_nie_przeszkadzaja():
    """Dokładnie ten przypadek psuje dziś istniejące mapowanie:
    ' Pełna Nazwa Nadawcy' vs 'Pełna Nazwa Nadawcy'."""
    d = profil_kolumn.dopasuj_kolumny(
        ["  Miejscowość ", "Ulica", "Nr", "Rejon"], PROFIL_TESTOWY)
    assert d.mapowanie["  Miejscowość "] == "miejscowosc"


def test_pole_moze_miec_kilka_akceptowanych_naglowkow():
    """Siatka 'Ścieżka > adres' ma kolumnę 'Nr', a 'Odbiór w punkcie'
    ma 'Nr domu' - to ta sama rzecz."""
    d = profil_kolumn.dopasuj_kolumny(
        ["Miejscowość", "Ulica", "Nr domu", "Rejon"], PROFIL_TESTOWY)
    assert d.mapowanie["Nr domu"] == "nr"
    assert d.braki == []


def test_literowka_w_naglowku_jest_wybaczana():
    d = profil_kolumn.dopasuj_kolumny(
        ["Miejscowosc", "Ulcia", "Nr", "Rejon"], PROFIL_TESTOWY)
    assert d.mapowanie["Ulcia"] == "ulica"


def test_zupelnie_obcy_naglowek_nie_jest_zgadywany():
    """Wybaczanie literówek nie może zamienić się w dopasowywanie
    czegokolwiek do czegokolwiek."""
    d = profil_kolumn.dopasuj_kolumny(
        ["Miejscowość", "Ulica", "Nr", "Rejon", "Wykonawca"], PROFIL_TESTOWY)
    assert "Wykonawca" in d.nierozpoznane
    assert "Wykonawca" not in d.mapowanie


# --- braki i nadmiary ---------------------------------------------------

def test_brak_wymaganej_kolumny_jest_zglaszany_wprost():
    """Dziś brakująca kolumna ujawnia się dopiero jako ValidationError
    pydantic przy pierwszym wierszu - czyli daleko od przyczyny."""
    d = profil_kolumn.dopasuj_kolumny(["Miejscowość", "Ulica"], PROFIL_TESTOWY)
    assert set(d.braki) == {"nr", "rejon"}
    assert not d.kompletne


def test_komplet_wymaganych_daje_kompletne():
    d = profil_kolumn.dopasuj_kolumny(
        ["Miejscowość", "Ulica", "Nr", "Rejon"], PROFIL_TESTOWY)
    assert d.kompletne


def test_brak_kolumny_nieobowiazkowej_nie_przeszkadza():
    """PNA jest w profilu, ale nie jest wymagana - jej brak to nie awaria."""
    d = profil_kolumn.dopasuj_kolumny(
        ["Miejscowość", "Ulica", "Nr", "Rejon"], PROFIL_TESTOWY)
    assert "pna" not in d.braki
    assert d.kompletne


def test_puste_naglowki_sa_pomijane():
    """openpyxl na pustych komórkach nagłówka zwraca None."""
    d = profil_kolumn.dopasuj_kolumny(
        ["Miejscowość", None, "Ulica", "", "Nr", "Rejon"], PROFIL_TESTOWY)
    assert d.kompletne
    assert None not in d.mapowanie


def test_powtorzony_naglowek_nie_nadpisuje_pierwszego():
    """Arkusze bywają sklejane z kilku - druga kolumna o tej samej nazwie
    ma zostać zgłoszona, nie po cichu podmienić pierwszą."""
    d = profil_kolumn.dopasuj_kolumny(
        ["Rejon", "Miejscowość", "Ulica", "Nr", "Rejon "], PROFIL_TESTOWY)
    assert d.mapowanie["Rejon"] == "rejon"
    assert "Rejon " in d.nierozpoznane


# --- wyciąganie wiersza -------------------------------------------------

def test_wyodrebnia_wiersz_wedlug_dopasowania():
    d = profil_kolumn.dopasuj_kolumny(
        ["Miejscowość", "Ulica", "Nr", "Rejon", "Wykonawca"], PROFIL_TESTOWY)
    surowy = {"Miejscowość": "Warszawa", "Ulica": "Marsa", "Nr": "56",
              "Rejon": "119", "Wykonawca": "nieistotne"}
    assert profil_kolumn.wyodrebnij(surowy, d) == {
        "miejscowosc": "Warszawa", "ulica": "Marsa", "nr": "56", "rejon": "119",
    }


def test_wyodrebnianie_pomija_kolumny_spoza_profilu():
    """To jest mechanizm selektywnego importu: czego nie ma w profilu,
    tego nie wciągamy."""
    d = profil_kolumn.dopasuj_kolumny(["Miejscowość", "Ulica", "Nr", "Rejon"],
                                      PROFIL_TESTOWY)
    surowy = {"Miejscowość": "Warszawa", "Ulica": "Marsa", "Nr": "56",
              "Rejon": "119", "Tryb": "A", "PRP": "E2"}
    assert set(profil_kolumn.wyodrebnij(surowy, d)) == {
        "miejscowosc", "ulica", "nr", "rejon"}


# --- heurystyki treści --------------------------------------------------

@pytest.mark.parametrize("wartosci,oczekiwane", [
    (["02-822", "14-500", "37-455"], True),
    (["Warszawa", "Braniewo"], False),
    ([], False),
])
def test_heurystyka_rozpoznaje_kod_pocztowy(wartosci, oczekiwane):
    assert profil_kolumn.pasuje_do_wzorca("pna", wartosci) is oczekiwane


@pytest.mark.parametrize("wartosci,oczekiwane", [
    (["231270", "936272"], True),
    (["WA119", "??? "], False),
])
def test_heurystyka_rozpoznaje_pni(wartosci, oczekiwane):
    assert profil_kolumn.pasuje_do_wzorca("pni", wartosci) is oczekiwane


def test_heurystyka_dla_pola_bez_wzorca_nie_orzeka():
    """Brak wzorca ma znaczyć 'nie wiem', a nie 'nie pasuje' - inaczej
    siatka bezpieczeństwa zamieniłaby się w źródło fałszywych alarmów."""
    assert profil_kolumn.pasuje_do_wzorca("ulica", ["Marsa"]) is None


def test_ostrzezenia_o_tresci_wskazuja_kolumne():
    """Nagłówek mówi PNA, a w środku miasta - najpewniej przesunięte
    kolumny albo zły arkusz."""
    d = profil_kolumn.dopasuj_kolumny(
        ["Miejscowość", "Ulica", "Nr", "Rejon", "PNA"], PROFIL_TESTOWY)
    probki = {"pna": ["Warszawa", "Radom"], "nr": ["56", "12"]}
    ostrzezenia = profil_kolumn.sprawdz_tresc(d, probki)
    assert [o.pole for o in ostrzezenia] == ["pna"]

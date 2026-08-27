"""
Import rejonarza z eksportu, w którym REJON JEST NAZWĄ ARKUSZA.

Realny eksport „WW - WER Ciemne" ma 219 arkuszy, po jednym na rejon, a
w środku wyłącznie `Miejscowość | Ulica | Nr | PNA`. Kolumny `Rejon` tam
NIE MA — jest nazwą zakładki. Dotychczasowy import czytał `sheetnames[0]`
i wymagał tej kolumny, więc z tego pliku nie wciągnąłby ani jednego
wiersza.

Obsługiwane są oba kształty naraz, bo oba przychodzą z BaŚKi: eksport
jednoarkuszowy z kolumną `Rejon` i eksport per-arkusz bez niej.
"""
import pytest
import xlwt

from zpo_tracker import normalizacja, rejonarz


@pytest.fixture
def conn():
    c = rejonarz.polacz(":memory:")
    yield c
    c.close()


@pytest.fixture
def zbuduj_xls(tmp_path):
    """Buduje .xls z podanych arkuszy. `xlwt`, bo `xlrd` wyłącznie czyta -
    bez zapisu testowalibyśmy podłożony artefakt, nie kształt formatu."""
    licznik = {"n": 0}

    def zbuduj(arkusze_dane):
        licznik["n"] += 1
        wb = xlwt.Workbook()
        for tytul, wiersze in arkusze_dane.items():
            ws = wb.add_sheet(tytul)
            for i, wiersz in enumerate(wiersze):
                for j, wartosc in enumerate(wiersz):
                    ws.write(i, j, wartosc)
        sciezka = tmp_path / f"eksport{licznik['n']}.xls"
        wb.save(str(sciezka))
        return sciezka
    return zbuduj


NAGLOWKI_BEZ_REJONU = ["Miejscowość", "Ulica", "Nr", "PNA"]


def _rejony_w_migawce(conn):
    return sorted(r[0] for r in conn.execute(
        "SELECT DISTINCT rejon FROM adresy_rejony"))


# --- rejon z nazwy arkusza ---------------------------------------------

def test_rejon_brany_z_nazwy_arkusza(conn, zbuduj_xls):
    sciezka = zbuduj_xls({
        "87": [NAGLOWKI_BEZ_REJONU, ["Warszawa", "Kwiatowa", "8", "00-001"]],
        "L11": [NAGLOWKI_BEZ_REJONU, ["Legionowo", "Polna", "3", "05-120"]],
    })
    wynik = rejonarz.zaimportuj(conn, sciezka)

    assert wynik.zapisane == 2
    # "87" dostaje prefiks WA (reguła BaŚKi), "L11" zostaje bez zmian
    assert _rejony_w_migawce(conn) == ["L11", "WA87"]


def test_wszystkie_arkusze_sa_czytane(conn, zbuduj_xls):
    """Dotąd czytany był wyłącznie pierwszy - czyli 1/219 realnego pliku."""
    sciezka = zbuduj_xls({
        str(i): [NAGLOWKI_BEZ_REJONU, ["Warszawa", "Kwiatowa", str(i), "00-001"]]
        for i in range(1, 11)
    })
    assert rejonarz.zaimportuj(conn, sciezka).zapisane == 10


def test_kod_czysto_literowy_w_nazwie_arkusza(conn, zbuduj_xls):
    """`RDH` niesie realne adresy w eksporcie WER Ciemne. Wzorzec, który
    wymagał cyfry, odrzucał go razem z sześcioma innymi."""
    sciezka = zbuduj_xls({
        "RDH": [NAGLOWKI_BEZ_REJONU, ["Radzymin", "Logistyczna", "10", "05-902"]],
    })
    rejonarz.zaimportuj(conn, sciezka)
    assert _rejony_w_migawce(conn) == ["RDH"]


# --- oba kształty eksportu naraz ---------------------------------------

def test_kolumna_rejon_ma_pierwszenstwo_przed_nazwa_arkusza(conn, zbuduj_xls):
    """Gdy arkusz NIESIE rejon w kolumnie, nazwa zakładki jest tylko
    etykietą i nie ma prawa go nadpisać - inaczej eksport jednoarkuszowy
    o przypadkowej nazwie („Arkusz1") psułby poprawne dane."""
    sciezka = zbuduj_xls({
        "Arkusz1": [["Miejscowość", "Ulica", "Nr", "PNA", "Rejon"],
                    ["Warszawa", "Kwiatowa", "8", "00-001", "WA93"]],
    })
    rejonarz.zaimportuj(conn, sciezka)
    assert _rejony_w_migawce(conn) == ["WA93"]


def test_arkusze_obu_rodzajow_w_jednym_pliku(conn, zbuduj_xls):
    sciezka = zbuduj_xls({
        "Arkusz1": [["Miejscowość", "Ulica", "Nr", "Rejon"],
                    ["Warszawa", "Kwiatowa", "8", "WA93"]],
        "L11": [["Miejscowość", "Ulica", "Nr"],
                ["Legionowo", "Polna", "3"]],
    })
    rejonarz.zaimportuj(conn, sciezka)
    assert _rejony_w_migawce(conn) == ["L11", "WA93"]


# --- arkusze, których nie da się użyć ----------------------------------

def test_arkusz_bez_rejonu_i_o_zlej_nazwie_jest_pomijany_JAWNIE(conn, zbuduj_xls):
    """Pominięcie musi być policzone, nie ciche. Eksport bywa sklejany
    z kilku i arkusz „Podsumowanie" na końcu jest realny - ale gdyby
    znikał bez śladu, tak samo zniknąłby arkusz z literówką w nazwie
    rejonu, czyli realna strata danych."""
    sciezka = zbuduj_xls({
        "L11": [NAGLOWKI_BEZ_REJONU, ["Legionowo", "Polna", "3", "05-120"]],
        "Podsumowanie": [NAGLOWKI_BEZ_REJONU, ["Warszawa", "Kwiatowa", "8", "00-001"]],
    })
    wynik = rejonarz.zaimportuj(conn, sciezka)

    assert wynik.zapisane == 1
    assert wynik.arkusze_pominiete == ["Podsumowanie"]
    assert _rejony_w_migawce(conn) == ["L11"]


def test_gdy_zaden_arkusz_sie_nie_nadaje_import_odmawia(conn, zbuduj_xls):
    """Zwrócenie „zapisano 0" wyglądałoby jak pusty plik. Odmowa z nazwami
    arkuszy mówi, CO poszło nie tak."""
    sciezka = zbuduj_xls({
        "Podsumowanie": [NAGLOWKI_BEZ_REJONU, ["Warszawa", "Kwiatowa", "8", "00-001"]],
    })
    with pytest.raises(rejonarz.NiezgodnyArkusz) as e:
        rejonarz.zaimportuj(conn, sciezka)
    assert "Podsumowanie" in str(e.value)


def test_arkusz_bez_wymaganych_kolumn_tez_jest_pomijany(conn, zbuduj_xls):
    sciezka = zbuduj_xls({
        "L11": [NAGLOWKI_BEZ_REJONU, ["Legionowo", "Polna", "3", "05-120"]],
        "WA87": [["Notatki"], ["cokolwiek"]],
    })
    wynik = rejonarz.zaimportuj(conn, sciezka)
    assert wynik.zapisane == 1
    assert wynik.arkusze_pominiete == ["WA87"]


def test_pusty_arkusz_nie_wywraca_importu(conn, zbuduj_xls):
    sciezka = zbuduj_xls({
        "L11": [NAGLOWKI_BEZ_REJONU, ["Legionowo", "Polna", "3", "05-120"]],
        "WA87": [],
    })
    wynik = rejonarz.zaimportuj(conn, sciezka)
    assert wynik.zapisane == 1
    assert "WA87" in wynik.arkusze_pominiete


# --- podmiana migawki zostaje podmianą ---------------------------------

def test_powtorny_import_podmienia_calosc_a_nie_dopisuje(conn, zbuduj_xls):
    """Migawka to stan, nie dziennik przyrostowy: adresy wycofane z BaŚKi
    muszą zniknąć, bo zostawione wyglądałyby na potwierdzone."""
    pierwszy = zbuduj_xls({
        "L11": [NAGLOWKI_BEZ_REJONU, ["Legionowo", "Polna", "3", "05-120"]]})
    drugi = zbuduj_xls({
        "WA87": [NAGLOWKI_BEZ_REJONU, ["Warszawa", "Kwiatowa", "8", "00-001"]]})

    rejonarz.zaimportuj(conn, pierwszy)
    rejonarz.zaimportuj(conn, drugi)

    assert _rejony_w_migawce(conn) == ["WA87"]
    assert rejonarz.policz(conn) == 1


def test_wartownik_w_nazwie_arkusza_nie_trafia_do_migawki(conn, zbuduj_xls):
    """`*UP`, `ZPO`, `UP` to wartowniki, nie rejony. Zapisane jako `???`
    kazałyby dedukcji mówić „wiem, że nie wiem" tam, gdzie prawdą jest
    „nie mam wpisu"."""
    sciezka = zbuduj_xls({
        "L11": [NAGLOWKI_BEZ_REJONU, ["Legionowo", "Polna", "3", "05-120"]],
        "ZPO": [NAGLOWKI_BEZ_REJONU, ["Warszawa", "Kwiatowa", "8", "00-001"]],
    })
    rejonarz.zaimportuj(conn, sciezka)
    assert normalizacja.REJON_NIEZNANY not in _rejony_w_migawce(conn)
    assert _rejony_w_migawce(conn) == ["L11"]


def test_eksport_per_arkusz_jest_oznaczony_jako_taki(conn, zbuduj_xls):
    """
    Eksport per-arkusz Z DEFINICJI nie niesie kolumny węzła, więc
    komunikat „arkusz bez kolumn Węzeł/TK - wzięto wszystko" byłby przy
    nim myląco alarmujący: brzmi jak usterka, a jest normalnym kształtem
    tego pliku.

    Ostrzeżenie ma jednak zostać, bo realne ryzyko istnieje - ktoś może
    wczytać eksport CUDZEGO węzła i nie zauważyć. Rozróżnienie pozwala
    powiedzieć mu wprost, co ma sprawdzić, zamiast straszyć go brakiem
    kolumn, na które i tak nic nie poradzi.
    """
    sciezka = zbuduj_xls({
        "L11": [NAGLOWKI_BEZ_REJONU, ["Legionowo", "Polna", "3", "05-120"]]})
    wynik = rejonarz.zaimportuj(conn, sciezka)
    assert wynik.rejon_z_nazw_arkuszy is True


def test_eksport_z_kolumna_rejonu_nie_jest_per_arkusz(conn, zbuduj_xls):
    sciezka = zbuduj_xls({
        "Arkusz1": [["Miejscowość", "Ulica", "Nr", "Rejon"],
                    ["Warszawa", "Kwiatowa", "8", "WA93"]]})
    wynik = rejonarz.zaimportuj(conn, sciezka)
    assert wynik.rejon_z_nazw_arkuszy is False

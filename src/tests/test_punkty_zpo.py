"""
Rejestr punktów ZPO z BaŚKi: PNI -> kanoniczny adres + rejon.

To jest ogniwo, którego rejonarz adresowy nie ma. **PNI jest jedyną
rzeczą na paragonie, którą da się odczytać i przepisać jednoznacznie**,
a ten eksport wiąże je z adresem i rejonem — czyli pozwala ustalić rejon
BEZ parsowania adresu w ogóle.

Dwie rzeczy, które ten plik pilnuje najmocniej:

**Filtr idzie po WĘŹLE, ale przyjmuje DWA: `WA` i `WW`.** To nie to samo
co filtr rejonarza adresowego, który bierze wyłącznie `WW` — i różnica
jest celowa. Tam pytanie brzmi „jakie rejony doręczeń ma NASZ węzeł",
tutaj „do których punktów jeździmy po przesyłki", a jeździmy do obu
warszawskich węzłów.

Zmierzone na realnym eksporcie: `WER in (WA, WW)` daje **2354 punkty**
z 22 393. Sam `WW` dałby 223, czyli 9% z tego. Filtr po jednostce `RS/RD`
dałby z kolei 3138 — o 784 za dużo, bo wciąga punkty obsługiwane przez
Ciechanów, Płock, Kielce, Siedlce i Ostrołękę.

**PNI zostaje TEKSTEM.** `"007"` i `"7"` to dwa różne punkty; rzutowanie
na liczbę to ta sama samo-zadana korupcja, którą naprawialiśmy
w eksporcie miesiąca.
"""
import pytest
import xlwt

from zpo_tracker import rejonarz


@pytest.fixture
def conn():
    c = rejonarz.polacz(":memory:")
    yield c
    c.close()


@pytest.fixture
def zbuduj_xls(tmp_path):
    licznik = {"n": 0}

    def zbuduj(naglowki, wiersze, tytul="Odbiór w punkcie"):
        licznik["n"] += 1
        wb = xlwt.Workbook()
        ws = wb.add_sheet(tytul)
        for j, n in enumerate(naglowki):
            ws.write(0, j, n)
        for i, w in enumerate(wiersze, start=1):
            for j, v in enumerate(w):
                ws.write(i, j, v)
        sciezka = tmp_path / f"punkty{licznik['n']}.xls"
        wb.save(str(sciezka))
        return sciezka
    return zbuduj


NAGLOWKI_A = ["RS/RD", "Placówka/ZPO", "PNI", "Miejscowość", "PNA",
              "Ulica", "Nr domu", "Węzeł", "TK", "Rejon"]
NAGLOWKI_NOWE = ["RS/RD", "Placówka / ZPO", "PNI / Id ZPO", "Miejscowość",
                 "PNA (skr.)", "Ulica", "Nr domu", "Węzeł", "TK", "Rejon"]


def _wiersz(jednostka="RD Warszawa", nazwa="Sklep ABC", pni="542261",
            miejscowosc="Marki", pna="05-270", ulica="Duża", nr="32",
            wezel="WW", tk="1", rejon="M4"):
    return [jednostka, nazwa, pni, miejscowosc, pna, ulica, nr, wezel, tk, rejon]


# --- rozpoznanie rodzaju pliku -----------------------------------------

def test_plik_z_kolumna_pni_to_rejestr_punktow(zbuduj_xls):
    """Jeden przycisk „Importuj" - rodzaj rozpoznajemy po ZAWARTOŚCI.
    Osobny przycisk na każdy eksport byłby przerzuceniem na użytkownika
    decyzji, którą program potrafi podjąć sam."""
    sciezka = zbuduj_xls(NAGLOWKI_A, [_wiersz()])
    assert rejonarz.rozpoznaj_rodzaj(sciezka) == rejonarz.RODZAJ_PUNKTY_ZPO


def test_plik_bez_pni_to_rejonarz_adresowy(zbuduj_xls):
    sciezka = zbuduj_xls(["Miejscowość", "Ulica", "Nr", "PNA"],
                         [["Warszawa", "Kwiatowa", "8", "00-001"]], tytul="WA87")
    assert rejonarz.rozpoznaj_rodzaj(sciezka) == rejonarz.RODZAJ_REJONARZ


# --- filtr po węźle: OBA warszawskie ----------------------------------

def test_biore_oba_warszawskie_wezly(conn, zbuduj_xls):
    """SEDNO. Sam `WW` zostawiłby 223 punkty z 2354 - dziewięć procent."""
    sciezka = zbuduj_xls(NAGLOWKI_A, [
        _wiersz(pni="1", wezel="WW"),
        _wiersz(pni="2", wezel="WA"),
    ])
    wynik = rejonarz.zaimportuj_punkty(conn, sciezka)

    assert wynik.zapisane == 2
    assert sorted(r[0] for r in conn.execute("SELECT pni FROM punkty_zpo")) == ["1", "2"]


def test_punkty_obcych_wezlow_odpadaja(conn, zbuduj_xls):
    """Ciechanów, Płock, Kielce, Siedlce, Ostrołęka - punkty formalnie
    przypisane naszym jednostkom, ale leżące poza obszarem, po którym
    jeżdżą nasi kurierzy. Filtr po samej jednostce wciągnąłby ich 784."""
    sciezka = zbuduj_xls(NAGLOWKI_A, [
        _wiersz(pni="1", wezel="WW"),
        _wiersz(pni="2", wezel="CI"),
        _wiersz(pni="3", wezel="KI"),
    ])
    wynik = rejonarz.zaimportuj_punkty(conn, sciezka)

    assert wynik.zapisane == 1
    assert wynik.pominiete == 2


def test_tk_2_jest_zapisywane_a_nie_wycinane(conn, zbuduj_xls):
    """TK zapisujemy i zostawiamy filtrowanie na odczyt. Wycięcie przy
    imporcie jest nieodwracalne do następnego wczytania, a punkt z TK=2
    to nadal punkt, do którego kurier jedzie."""
    sciezka = zbuduj_xls(NAGLOWKI_A, [
        _wiersz(pni="1", tk="1"), _wiersz(pni="2", tk="2")])
    rejonarz.zaimportuj_punkty(conn, sciezka)
    assert dict(conn.execute("SELECT pni, tk FROM punkty_zpo").fetchall()) == \
        {"1": "1", "2": "2"}


# --- warianty nagłówków i rozbicie PNI ---------------------------------

def test_nowszy_eksport_z_polaczonym_pni_i_id(conn, zbuduj_xls):
    """`PNI / Id ZPO` to JEDNA kolumna z dwiema wartościami
    (`542261 / TN6000468`). Id ZPO przyda się w rozmowie z BaŚKą, więc
    wyrzucanie go byłoby stratą bez powodu."""
    sciezka = zbuduj_xls(NAGLOWKI_NOWE, [_wiersz(pni="542261 / TN6000468")])
    rejonarz.zaimportuj_punkty(conn, sciezka)

    w = conn.execute("SELECT pni, id_zpo FROM punkty_zpo").fetchone()
    assert (w[0], w[1]) == ("542261", "TN6000468")


def test_starszy_eksport_bez_id_zpo(conn, zbuduj_xls):
    sciezka = zbuduj_xls(NAGLOWKI_A, [_wiersz(pni="613838")])
    rejonarz.zaimportuj_punkty(conn, sciezka)
    w = conn.execute("SELECT pni, id_zpo FROM punkty_zpo").fetchone()
    assert (w[0], w[1]) == ("613838", None)


def test_pna_w_obu_wariantach_nazwy(conn, zbuduj_xls):
    for naglowki in (NAGLOWKI_A, NAGLOWKI_NOWE):
        c = rejonarz.polacz(":memory:")
        rejonarz.zaimportuj_punkty(c, zbuduj_xls(naglowki, [_wiersz()]))
        assert c.execute("SELECT pna FROM punkty_zpo").fetchone()[0] == "05-270"
        c.close()


# --- PNI jako klucz ----------------------------------------------------

def test_pni_zostaje_tekstem(conn, zbuduj_xls):
    """`"007"` i `"7"` to dwa różne punkty. Rzutowanie na liczbę to ta
    sama samo-zadana korupcja, którą naprawialiśmy w eksporcie."""
    sciezka = zbuduj_xls(NAGLOWKI_A, [_wiersz(pni="007"), _wiersz(pni="7")])
    rejonarz.zaimportuj_punkty(conn, sciezka)
    assert sorted(r[0] for r in conn.execute("SELECT pni FROM punkty_zpo")) == ["007", "7"]


def test_wiersz_bez_pni_jest_pomijany(conn, zbuduj_xls):
    """PNI jest kluczem tego rejestru - bez niego wiersz nie ma
    tożsamości i nie da się go później odnaleźć."""
    sciezka = zbuduj_xls(NAGLOWKI_A, [_wiersz(pni=""), _wiersz(pni="1")])
    wynik = rejonarz.zaimportuj_punkty(conn, sciezka)
    assert (wynik.zapisane, wynik.bez_pni) == (1, 1)


def test_znajdz_po_pni(conn, zbuduj_xls):
    rejonarz.zaimportuj_punkty(conn, zbuduj_xls(NAGLOWKI_A, [_wiersz(pni="542261")]))
    punkt = rejonarz.znajdz_po_pni(conn, "542261")
    assert punkt["rejon"] == "M4"
    assert punkt["miejscowosc"] == "Marki"
    assert rejonarz.znajdz_po_pni(conn, "999999") is None


def test_znajdz_po_pni_nie_porownuje_liczbowo(conn, zbuduj_xls):
    rejonarz.zaimportuj_punkty(conn, zbuduj_xls(NAGLOWKI_A, [_wiersz(pni="007")]))
    assert rejonarz.znajdz_po_pni(conn, "007") is not None
    assert rejonarz.znajdz_po_pni(conn, "7") is None


# --- migawka to migawka ------------------------------------------------

def test_powtorny_import_podmienia_rejestr(conn, zbuduj_xls):
    rejonarz.zaimportuj_punkty(conn, zbuduj_xls(NAGLOWKI_A, [_wiersz(pni="1")]))
    rejonarz.zaimportuj_punkty(conn, zbuduj_xls(NAGLOWKI_A, [_wiersz(pni="2")]))
    assert [r[0] for r in conn.execute("SELECT pni FROM punkty_zpo")] == ["2"]


def test_rejestr_punktow_nie_rusza_rejonarza_adresowego(conn, zbuduj_xls):
    """Dwie osobne tabele właśnie po to: import jednego pliku nie może
    wymazać drugiego. Wspólna tabela oznaczałaby, że wczytanie punktów
    kasuje rejonarz adresowy - i odwrotnie."""
    conn.execute(
        "INSERT INTO adresy_rejony (klucz, klucz_ulica_nr, miejscowosc, nr, rejon)"
        " VALUES ('a', 'b', 'Warszawa', '1', 'WA87')")
    rejonarz.zaimportuj_punkty(conn, zbuduj_xls(NAGLOWKI_A, [_wiersz()]))
    assert rejonarz.policz(conn) == 1


def test_brak_kolumny_wezla_nie_blokuje_ale_jest_zaznaczony(conn, zbuduj_xls):
    """Eksport bez kolumny węzła da się wczytać, ale użytkownik musi
    wiedzieć, że wszedł CAŁY plik, a nie nasze punkty - inaczej wziąłby
    ogólnopolską listę za swoją."""
    naglowki = [n for n in NAGLOWKI_A if n != "Węzeł"]
    sciezka = zbuduj_xls(naglowki, [[v for n, v in zip(NAGLOWKI_A, _wiersz())
                                     if n != "Węzeł"]])
    wynik = rejonarz.zaimportuj_punkty(conn, sciezka)
    assert wynik.zapisane == 1
    assert wynik.bez_filtrowania is True

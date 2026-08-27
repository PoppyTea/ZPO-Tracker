"""
Podpięcie kaskady dedukcji miejscowości pod zakładanie adresu.

Bez tego schemat v4 nie robi tego, po co powstał. `ulice.miejscowosc_id`
jest NOT NULL, więc adres bez miejscowości nie dostaje ulicy - a w
realnych danych **528 z 664 unikalnych adresów (79%) nie ma miasta**,
bo kurierzy go nie piszą (Warszawa jest domyślna). Sama zmiana schematu
zostawiłaby więc cztery piąte adresów bez struktury, czyli dokładnie tam,
gdzie były przed rozbiciem.

Kaskada jest tu wstrzykiwana, nie importowana na sztywno, i to jest
kontrakt: stacja bez `rejonarz.db` ma zachowywać się DOKŁADNIE tak jak
przed tą zmianą. Przypięte testem w obie strony - to samo rozstrzygnięcie
co przy wpinaniu rejonarza w `dedukcja.py`.
"""
import pytest

from zpo_tracker import dedukcja_miejscowosci, repo
from zpo_tracker.importer import get_or_create_adres


@pytest.fixture
def conn():
    c = repo.polacz(":memory:")
    repo.utworz_schemat(c)
    yield c
    c.close()


def _adres(conn, surowy):
    return conn.execute(
        """SELECT a.surowy, a.ulica_id, a.zrodlo_miejscowosci, a.nr_budynku,
                  u.nazwa AS ulica, m.nazwa AS miejscowosc
           FROM adresy a
           LEFT JOIN ulice u ON u.id = a.ulica_id
           LEFT JOIN miejscowosci m ON m.id = u.miejscowosc_id
           WHERE a.surowy = ?""",
        (surowy,),
    ).fetchone()


def _rejonarz(wiersze):
    """Wstrzykiwany rejonarz: klucz -> lista (miejscowosc, rejon)."""
    def szukaj(klucz):
        return wiersze.get(klucz, [])
    return szukaj


# --- stacja bez migawki: zachowanie MUSI zostać nietknięte -------------

def test_bez_kaskady_adres_bez_miasta_nie_dostaje_ulicy(conn):
    """Kontrakt zgodności wstecznej. Gdyby to przestało działać, program
    na stacji bez zaimportowanego rejonarza zacząłby się zachowywać
    inaczej - a nie ma jak tego zauważyć poza produkcją."""
    get_or_create_adres(conn, "Kwiatowa 8")
    w = _adres(conn, "Kwiatowa 8")
    assert w["ulica_id"] is None
    assert w["nr_budynku"] == "8"          # numer nie zakłada nic w słowniku


def test_pusta_migawka_znaczy_to_samo_co_brak_migawki(conn):
    """Pusty rejonarz i brak rejonarza to dla dedukcji ta sama sytuacja -
    inaczej „zaimportowałem, ale plik był pusty" dawałoby ciche zmiany
    zachowania."""
    get_or_create_adres(conn, "Kwiatowa 8", szukaj=_rejonarz({}))
    assert _adres(conn, "Kwiatowa 8")["ulica_id"] is None


# --- z migawką: adres bez miasta dostaje strukturę ---------------------

def test_jednoznaczna_miejscowosc_domyka_adres(conn):
    szukaj = _rejonarz({"kwiatowa|8": [("Ząbki", "WA1")]})
    get_or_create_adres(conn, "Kwiatowa 8", szukaj=szukaj)

    w = _adres(conn, "Kwiatowa 8")
    assert (w["miejscowosc"], w["ulica"]) == ("Ząbki", "Kwiatowa")
    assert w["zrodlo_miejscowosci"] == dedukcja_miejscowosci.ZRODLO_JEDNOZNACZNY


def test_zrodlo_niesie_regule_ktora_zadzialala(conn):
    """Kolumna `zrodlo_miejscowosci` istnieje po to, żeby człowiek
    odróżnił „wiemy na pewno" od „założyliśmy Warszawę". Zapisanie
    samej miejscowości bez nazwy reguły czyni ją bezużyteczną."""
    szukaj = _rejonarz({"kwiatowa|8": [
        ("Warszawa (Wola) - Warszawa", "WA1"),
        ("Marki - Marki", "M1"),
    ]})
    get_or_create_adres(conn, "Kwiatowa 8", szukaj=szukaj)
    assert _adres(conn, "Kwiatowa 8")["zrodlo_miejscowosci"] == \
        dedukcja_miejscowosci.ZRODLO_WARSZAWA


def test_nierozstrzygniete_zostaje_bez_ulicy(conn):
    """Dwie miejscowości spoza Warszawy i bez innych przesłanek - kaskada
    ma ODMÓWIĆ, a nie wybrać pierwszą z brzegu. To jest ochrona słownika:
    zgadnięta miejscowość zakłada byt, pod który podepną się kolejne
    adresy."""
    szukaj = _rejonarz({"kwiatowa|8": [
        ("Marki - Marki", "M1"),
        ("Ząbki - Ząbki", "Z1"),
    ]})
    get_or_create_adres(conn, "Kwiatowa 8", szukaj=szukaj)

    w = _adres(conn, "Kwiatowa 8")
    assert w["ulica_id"] is None
    assert w["surowy"] == "Kwiatowa 8"     # nic nie przepadło


def test_rejon_domyka_to_czego_sam_adres_nie_domyka(conn):
    """Rejon warszawski zawęża do jednej gminy w 120/121 przypadków -
    stąd wolno mu rozstrzygnąć automatycznie."""
    szukaj = _rejonarz({"kwiatowa|8": [
        ("Warszawa (Wola) - Warszawa", "WA1"),
        ("Warszawa (Ochota) - Warszawa", "WA2"),
    ]})
    get_or_create_adres(conn, "Kwiatowa 8", szukaj=szukaj, rejon="WA2")

    w = _adres(conn, "Kwiatowa 8")
    assert w["miejscowosc"] == "Warszawa (Ochota) - Warszawa"
    assert w["zrodlo_miejscowosci"] == dedukcja_miejscowosci.ZRODLO_REJON


# --- miasto podane wprost wygrywa z migawką ----------------------------

def test_miasto_z_adresu_nie_pyta_rejonarza(conn):
    """Człowiek, który miejscowość napisał, jest lepszym źródłem niż
    migawka. Pytanie rejonarza byłoby nie tylko zbędne - dawałoby mu
    szansę nadpisać to, co podał kurier."""
    wolania = []

    def szukaj(klucz):
        wolania.append(klucz)
        return [("Marki - Marki", "M1")]

    get_or_create_adres(conn, "Kwiatowa 8, Ząbki", szukaj=szukaj)

    assert wolania == []
    w = _adres(conn, "Kwiatowa 8, Ząbki")
    assert w["miejscowosc"] == "Ząbki"
    assert w["zrodlo_miejscowosci"] == dedukcja_miejscowosci.ZRODLO_Z_ADRESU


# --- adres nie do sparsowania ------------------------------------------

def test_adres_bez_numeru_nie_pyta_rejonarza_i_zostaje_surowy(conn):
    """Bez numeru budynku nie ma klucza, więc nie ma o co pytać."""
    wolania = []

    def szukaj(klucz):
        wolania.append(klucz)
        return []

    get_or_create_adres(conn, "Metro Ratusz", szukaj=szukaj)

    assert wolania == []
    w = _adres(conn, "Metro Ratusz")
    assert (w["ulica_id"], w["nr_budynku"]) == (None, None)
    assert w["surowy"] == "Metro Ratusz"


# --- powtórne zakładanie -----------------------------------------------

def test_ten_sam_surowy_nie_zaklada_drugiego_wiersza(conn):
    szukaj = _rejonarz({"kwiatowa|8": [("Ząbki", "WA1")]})
    pierwszy = get_or_create_adres(conn, "Kwiatowa 8", szukaj=szukaj)
    drugi = get_or_create_adres(conn, "Kwiatowa 8", szukaj=szukaj)
    assert pierwszy == drugi
    assert conn.execute("SELECT COUNT(*) FROM adresy").fetchone()[0] == 1

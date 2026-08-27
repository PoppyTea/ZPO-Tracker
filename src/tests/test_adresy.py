"""
Rozbicie wolnego tekstu adresu na części składowe.

Ten moduł zastępuje `rejonarz.rozbij_adres`, które radziło sobie wyłącznie
ze znacznikami `m.`/`lok.`/`mieszk.` oddzielonymi spacją i wymagało, żeby
lokal był liczbą. Pomiar na realnym snapshocie pokazał, że to za mało:
z 219 adresów, których nie dało się wyrejonizować, **161 miało PNI** -
czyli punkty ZPO, które siedzą w lokalach usługowych i zapisywane są
w kilkunastu wariantach naraz.

WZORCE w tych testach pochodzą z realnych danych, ale NAZWY ULIC są
zmyślone - repozytorium jest publiczne, a `data/CLAUDE.md` zabrania
wnoszenia do niego realnych adresów. Pod testem jest kształt zapisu,
nie konkretny punkt, więc podmiana nazwy niczego nie osłabia.

Naczelna zasada modułu: `rozbij` NIGDY nie rzuca. Nieudane rozbicie to
stan wyniku (`pewnosc='brak'`), nie wyjątek - bo wiersz, którego nie
umiemy rozłożyć, ma trafić do pliku do poprawy, a nie wywalić import.
"""
import pytest

from zpo_tracker import adresy


# --- przypadki podstawowe ----------------------------------------------

def test_ulica_i_numer_bez_miasta():
    """Najczęstszy kształt w naszych danych - miasto pomijane, bo
    Warszawa jest dla kurierów domyślna."""
    r = adresy.rozbij("Kwiatowa 8")
    assert (r.ulica, r.nr_budynku, r.nr_lokalu) == ("Kwiatowa", "8", None)
    assert r.miejscowosc is None
    assert r.pewnosc == "bez_miasta"


def test_miasto_po_przecinku():
    r = adresy.rozbij("Kwiatowa 8, Ząbki")
    assert (r.miejscowosc, r.ulica, r.nr_budynku) == ("Ząbki", "Kwiatowa", "8")
    assert r.pewnosc == "pelna"


def test_numer_z_litera():
    assert adresy.rozbij("Kwiatowa 98C").nr_budynku == "98C"


def test_surowy_jest_zawsze_zachowany():
    """Surowy string jest źródłem prawdy - struktura jest tylko jego
    interpretacją i musi dać się odtworzyć od nowa lepszym parserem."""
    assert adresy.rozbij("  Kwiatowa 8  ").surowy == "  Kwiatowa 8  "


# --- lokale usługowe: rodzina, która wywracała stary parser -------------

@pytest.mark.parametrize("zapis, lokal", [
    ("Kwiatowa 60 lok. U2", "U2"),
    ("Kwiatowa 60 lok.U2", "U2"),          # bez spacji po kropce
    ("Kwiatowa 60 lok U2", "U2"),          # bez kropki
    ("Kwiatowa 60 lok, U4", "U4"),         # przecinek zamiast kropki
    ("Kwiatowa 60 lok.U05", "U05"),        # zero wiodące
    ("Kwiatowa 60 lok. LU2", "LU2"),       # dwuliterowy prefiks
    ("Kwiatowa 60 m. 3", "3"),             # stary wariant nadal działa
    ("Kwiatowa 60 mieszk. 3", "3"),
])
def test_znacznik_lokalu_w_wariantach_zapisu(zapis, lokal):
    r = adresy.rozbij(zapis)
    assert (r.ulica, r.nr_budynku, r.nr_lokalu) == ("Kwiatowa", "60", lokal)


@pytest.mark.parametrize("zapis, lokal", [
    ("Kwiatowa 200 lok. U5/U6/U7/U8", "U5/U6/U7/U8"),
    ("Kwiatowa 16 lok. LU2/LU3", "LU2/LU3"),
    ("Kwiatowa 98 lok. 1i2", "1i2"),
    ("Kwiatowa 120 lok. 1.2.3", "1.2.3"),
    ("Kwiatowa 4 lok.U13,U14", "U13,U14"),
])
def test_lokal_zbiorczy_zostaje_w_calosci(zapis, lokal):
    """Jeden punkt zajmujący kilka lokali to jeden punkt. Rozbijanie go
    na osobne adresy zrobiłoby duplikaty tam, gdzie ich nie ma."""
    assert adresy.rozbij(zapis).nr_lokalu == lokal


def test_przecinek_wewnatrz_lokalu_nie_jest_separatorem_miasta():
    """PUŁAPKA: `lok.U13,U14` ma przecinek, który NIE oddziela miasta.
    Rozróżnienie idzie po cyfrach - nazwy miejscowości ich nie zawierają."""
    r = adresy.rozbij("Kwiatowa 4 lok.U13,U14")
    assert r.miejscowosc is None
    assert r.nr_lokalu == "U13,U14"


def test_lokal_i_miasto_naraz():
    r = adresy.rozbij("Kwiatowa 33H lok. U1 , Ząbki")
    assert (r.miejscowosc, r.nr_budynku, r.nr_lokalu) == ("Ząbki", "33H", "U1")


# --- ukośnik: budynek czy lokal ----------------------------------------

def test_ukosnik_przed_litera_to_lokal():
    """`13/U1` - `U1` nie może być numerem budynku, więc to lokal."""
    r = adresy.rozbij("Kwiatowa 13/U1")
    assert (r.nr_budynku, r.nr_lokalu) == ("13", "U1")


def test_goly_ukosnik_miedzy_cyframi_zostaje_w_budynku():
    """`6/8` bywa podwójnym numerem JEDNEGO budynku równie często, co
    budynkiem z mieszkaniem. Rozstrzygnięcie zostaje po stronie
    wyszukiwania, które próbuje obu odczytów - parser nie zgaduje."""
    r = adresy.rozbij("Kwiatowa 6/8")
    assert (r.nr_budynku, r.nr_lokalu) == ("6/8", None)


def test_ukosnik_z_lokalem_i_miastem():
    r = adresy.rozbij("Kwiatowa 11/U12, Ząbki")
    assert (r.miejscowosc, r.nr_budynku, r.nr_lokalu) == ("Ząbki", "11", "U12")


# --- warianty nazwy ulicy ----------------------------------------------

@pytest.mark.parametrize("zapis", [
    "Aleja Kwiatowa 65",
    "Aleje Kwiatowa 65",
    "Al. Kwiatowa 65",
    "al.Kwiatowa 65",
])
def test_prefiks_alei_jest_odcinany_od_nazwy(zapis):
    """`Solidarności 117` i `Aleja Solidarności 83/89` to ta sama ulica
    zapisana dwoma sposobami - w danych występują OBA warianty naraz.
    Prefiks idzie do osobnego pola, żeby klucz wyszukiwania był wspólny."""
    r = adresy.rozbij(zapis)
    assert r.ulica == "Kwiatowa"
    assert r.typ_ulicy == "Aleja"


def test_brak_prefiksu_daje_pusty_typ():
    assert adresy.rozbij("Kwiatowa 65").typ_ulicy is None


def test_kropka_w_nazwie_ulicy_nie_myli_parsera():
    r = adresy.rozbij("Św. Anny 12")
    assert (r.ulica, r.nr_budynku) == ("Św. Anny", "12")


# --- przypadki, które MAJĄ zostać nierozstrzygnięte ---------------------

@pytest.mark.parametrize("zapis", [
    "Kwiatowa",              # sama ulica, bez numeru
    "Al. Kwiatowe",          # jw. z prefiksem
    "Metro Ratusz",          # w ogóle nie adres
    "",
    "   ",
])
def test_bez_numeru_budynku_pewnosc_brak(zapis):
    """Bez numeru budynku nie ma czego szukać w rejonarzu, a zgadywanie
    rejonu dla samej ulicy jest dokładnie tym, co rejonarz ma eliminować.
    Taki wiersz ma trafić do człowieka, nie do bazy."""
    r = adresy.rozbij(zapis)
    assert r.pewnosc == "brak"
    assert r.nr_budynku is None


def test_none_nie_wywraca_parsera():
    assert adresy.rozbij(None).pewnosc == "brak"


def test_nierozstrzygniety_adres_tez_zachowuje_surowy():
    """Bez tego wiersz nie do sparsowania nie miałby jak trafić do pliku
    do poprawy - a to jest cała jego dalsza droga."""
    assert adresy.rozbij("Metro Ratusz").surowy == "Metro Ratusz"


# --- klucze do dopasowania ---------------------------------------------

def test_klucz_pomija_diakrytyki_wielkosc_i_prefiks():
    """Trzy zapisy tej samej ulicy muszą dać ten sam klucz - inaczej
    dopasowanie do rejonarza rozjeżdża się na zapisie, nie na adresie."""
    klucze = {
        adresy.rozbij(z).klucz_ulica_nr
        for z in ["Aleja Żółta 8", "al. Zolta 8", "ŻÓŁTA 8"]
    }
    assert len(klucze) == 1


def test_klucz_pelny_zawiera_miejscowosc():
    a = adresy.rozbij("Kwiatowa 8, Ząbki")
    b = adresy.rozbij("Kwiatowa 8, Marki")
    assert a.klucz != b.klucz
    assert a.klucz_ulica_nr == b.klucz_ulica_nr


def test_numer_budynku_nie_jest_normalizowany_rozmyto():
    """`56` i `56A` to dwa różne budynki, często w różnych rejonach."""
    assert adresy.rozbij("Kwiatowa 56").klucz_ulica_nr != \
           adresy.rozbij("Kwiatowa 56A").klucz_ulica_nr


# --- sama nazwa rodzajowa to nie jest nazwa ulicy -----------------------
#
# Domknięcie tej samej dziury, przez którą przechodziło `"Piaseczno, al. 5"`.
# Tam prefiks zjadał człon w całości i zostawał pusty string; tutaj zostaje
# NIEPUSTY, ale bezwartościowy: `"al"` bez kropki nie łapie się we wzorcu
# prefiksu, więc przeżywa jako nazwa ulicy.
#
# Dlaczego to nie jest drobiazg: taki adres ma `pewnosc='pelna'`, czyli
# parser jest go PEWNY - a to jedyny warunek wpuszczający wpis do słownika
# ulic. Powstawałaby tam ulica o nazwie „al", zbierająca pod sobą wszystkie
# adresy tego kształtu z danej miejscowości.

@pytest.mark.parametrize("zapis", [
    "Ząbki, al 7",
    "Ząbki, al. 7",
    "Ząbki, aleja 7",
    "Ząbki, ul 7",
    "Ząbki, ulica 7",
    "Ząbki, pl 7",
    "Ząbki, plac 7",
])
def test_sam_wyraz_rodzajowy_nie_jest_ulica(zapis):
    r = adresy.rozbij(zapis)
    assert r.pewnosc == "brak"
    assert r.ulica is None


def test_wyraz_rodzajowy_z_nazwa_zostaje_ulica():
    """Kontrola, żeby poprzedni test nie okazał się prawdziwy przez
    wycięcie za dużo - `"Aleja Kwiatowa"` ma nadal działać."""
    r = adresy.rozbij("Ząbki, aleja Kwiatowa 7")
    assert (r.ulica, r.typ_ulicy, r.pewnosc) == ("Kwiatowa", "Aleja", "pelna")

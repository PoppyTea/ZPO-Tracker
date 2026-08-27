"""
Testy kaskady dedukcji miejscowości (`zpo_tracker.dedukcja_miejscowosci`).

NAZWY ULIC I MIEJSCOWOŚCI SĄ ZMYŚLONE - repozytorium jest publiczne,
a `data/CLAUDE.md` zabrania wnoszenia do niego realnych adresów. Pod
testem jest KSZTAŁT reguły, nie konkretny punkt, więc podmiana nazwy
niczego nie osłabia. Jedyny wyjątek to słowo "Warszawa" w roli GMINY:
to nie dana z naszego zbioru, tylko stała samej reguły (kurierzy pomijają
miejscowość dokładnie dlatego, że Warszawa jest dla nich domyślna).
Dzielnice w nawiasach są już zmyślone.

Liczby w komentarzach (55,3% / +9,3% / 120 na 121 / 32 na 59 / 86%) to
pomiary z eksportu "WW - WER Ciemne". Są tutaj po to, żeby granica
reguły `rejon_wskazuje_gmine` nie wyglądała na arbitralną - to ona
decyduje, czy program wpisuje sam, czy pyta człowieka.
"""
import dataclasses

import pytest

from zpo_tracker import adresy
from zpo_tracker import dedukcja_miejscowosci as dm
from zpo_tracker import normalizacja

# Dwie zmyślone dzielnice tej samej gminy - na nich stoi cała rodzina
# przypadków "jedna gmina, kilka miejscowości".
WARSZAWA_A = "Warszawa (Nowy Bór) - Warszawa"
WARSZAWA_B = "Warszawa (Stary Bór) - Warszawa"
# Dwie zmyślone miejscowości jednej gminy spoza Warszawy.
LUGOWICE_A = "Nowa Górka - Ługowice"
LUGOWICE_B = "Podlesie - Ługowice"
# Miejscowość będąca własną gminą (zapis BaŚKi powtarza wtedy nazwę).
KWIATOW = "Kwiatów - Kwiatów"

ADRES = "Kwiatowa 8"
ROZBICIE = adresy.rozbij(ADRES)


def szukajka(*wiersze, dziennik=None):
    """
    Fabryka wstrzykiwanej zależności - cała "baza" tych testów.

    Sedno projektu modułu: kaskada dostaje callable `szukaj(klucz)`,
    więc testy nie potrzebują SQLite ani pliku `rejonarz.db`. Wiersze
    podajemy jako krotki `(miejscowosc, rejon)`, bo to najkrótszy zapis
    czytelny w treści testu.
    """
    mapa = {ROZBICIE.klucz_ulica_nr: list(wiersze)}

    def szukaj(klucz):
        if dziennik is not None:
            dziennik.append(klucz)
        return mapa.get(klucz, [])

    return szukaj


# --- zwijanie miejscowości do gminy ------------------------------------
# Na tym stoją reguły 2 i 3: bez zwinięcia dzielnice Warszawy są
# osobnymi miejscowościami i "dokładnie jedna z gminą Warszawa" nigdy
# nie byłoby prawdą.

def test_gmina_zwija_dzielnice_do_gminy():
    assert dm.gmina(WARSZAWA_A) == "Warszawa"
    assert dm.gmina(WARSZAWA_B) == "Warszawa"


def test_gmina_wsi_to_nazwa_gminy_a_nie_wsi():
    assert dm.gmina(LUGOWICE_A) == "Ługowice"
    assert dm.gmina(LUGOWICE_B) == "Ługowice"


def test_gmina_bez_separatora_to_sama_nazwa():
    """Brak " - " znaczy "nie wiem, w jakiej gminie" - zgadywanie tutaj
    byłoby wymyślaniem danych, więc miejscowość jest własną tożsamością."""
    assert dm.gmina("Kwiatów") == "Kwiatów"


def test_mysnik_bez_spacji_nie_jest_separatorem_gminy():
    """PUŁAPKA, przez którą separatorem jest " - ", a nie "-": nazwy
    dwuczłonowe z łącznikiem są normalnymi nazwami miejscowości."""
    assert dm.gmina("Wólka-Zdrój") == "Wólka-Zdrój"


def test_gmina_bierze_ostatni_czlon_przy_kilku_separatorach():
    assert dm.gmina("Nowa Górka - Kolonia - Ługowice") == "Ługowice"


@pytest.mark.parametrize("wejscie", [None, "", "   "])
def test_gmina_dla_pustego_wejscia_jest_pusta(wejscie):
    assert dm.gmina(wejscie) == ""


# --- granica "rejon warszawski czy nie" --------------------------------

@pytest.mark.parametrize("rejon", ["WA87", "WA26A", "wa87", " WA100 "])
def test_rejon_warszawski_rozpoznany(rejon):
    assert dm.czy_rejon_warszawski(rejon) is True


@pytest.mark.parametrize("rejon", [
    "ND4", "ND5", "L9", "R1", "W3", "XP2", "MM1", "XG1", "XL2", "Z3",
])
def test_rejon_spoza_warszawy_nie_jest_warszawski(rejon):
    assert dm.czy_rejon_warszawski(rejon) is False


@pytest.mark.parametrize("rejon", [None, "", "???", "WER", "WA"])
def test_brak_rejonu_i_kody_bez_numeru_nie_sa_warszawskie(rejon):
    """"???" to kanoniczny "nie wiem" (`normalizacja.REJON_NIEZNANY`),
    a "WER"/"WA" bez numeru nie mają kształtu rejonu warszawskiego -
    żadne z nich nie może uruchomić automatu."""
    assert dm.czy_rejon_warszawski(rejon) is False


# --- reguła 1: jednoznaczny_w_rejonarzu (zmierzone 55,3%) --------------

def test_jeden_kandydat_rozstrzyga():
    wynik = dm.dedukuj(ROZBICIE, szukajka((LUGOWICE_A, "ND4")))
    assert wynik.miejscowosc == LUGOWICE_A
    assert wynik.zrodlo == dm.ZRODLO_JEDNOZNACZNY
    assert wynik.kandydaci == (LUGOWICE_A,)


def test_ta_sama_miejscowosc_w_dwoch_rejonach_wciaz_jest_jednoznaczna():
    """Dedukujemy MIEJSCOWOŚĆ, nie rejon - sprzeczność rejonów pod jednym
    adresem jest problemem rejonarza (`rejonarz.znajdz_rejon` sam odmawia
    rozstrzygnięcia) i nie może blokować dedukcji miejscowości."""
    wynik = dm.dedukuj(
        ROZBICIE, szukajka((LUGOWICE_A, "ND4"), (LUGOWICE_A, "ND5")))
    assert (wynik.miejscowosc, wynik.zrodlo) == (
        LUGOWICE_A, dm.ZRODLO_JEDNOZNACZNY)


def test_powtorzony_identyczny_wiersz_nie_tworzy_dwoch_kandydatow():
    wynik = dm.dedukuj(
        ROZBICIE, szukajka((KWIATOW, "L9"), (KWIATOW, "L9")))
    assert wynik.kandydaci == (KWIATOW,)


# --- reguła 2: zalozona_warszawa (domyka +9,3%, obalona w 0,2%) --------

def test_jedyny_kandydat_z_gminy_warszawa_wygrywa():
    wynik = dm.dedukuj(
        ROZBICIE, szukajka((KWIATOW, "L9"), (WARSZAWA_A, "WA87"),
                           (LUGOWICE_A, "ND4")))
    assert wynik.miejscowosc == WARSZAWA_A
    assert wynik.zrodlo == dm.ZRODLO_WARSZAWA
    # Pełna lista zostaje w wyniku: człowiek przeglądający zapis ma
    # widzieć, że wybór był z trzech, a nie że innych nie było.
    assert wynik.kandydaci == tuple(sorted([KWIATOW, WARSZAWA_A, LUGOWICE_A]))


def test_dwie_dzielnice_warszawy_nie_rozstrzygaja_zalozeniem():
    """Reguła 2 rozstrzyga MIEJSCOWOŚĆ, a "gmina Warszawa" to za mało,
    kiedy pasują do niej dwie dzielnice - zapisujemy nazwę miejscowości,
    nie gminy, więc wybór jednej z nich byłby losowaniem."""
    wynik = dm.dedukuj(
        ROZBICIE, szukajka((WARSZAWA_A, "WA87"), (WARSZAWA_B, "WA88"),
                           (LUGOWICE_A, "ND4")))
    assert wynik.miejscowosc is None
    assert wynik.zrodlo == dm.ZRODLO_DO_WYBORU


def test_brak_kandydata_warszawskiego_przechodzi_dalej():
    wynik = dm.dedukuj(
        ROZBICIE, szukajka((KWIATOW, "L9"), (LUGOWICE_A, "ND4")))
    assert wynik.zrodlo == dm.ZRODLO_DO_WYBORU


# --- reguła 3, strona WA: wolno wpisać automatycznie (120 na 121) ------

def test_rejon_warszawski_rozstrzyga_miedzy_dzielnicami():
    """Przypadek, dla którego ta reguła w ogóle istnieje: reguła 2
    odpadła (dwie dzielnice tej samej gminy), a rejon wskazuje jedną."""
    wynik = dm.dedukuj(
        ROZBICIE,
        szukajka((WARSZAWA_A, "WA87"), (WARSZAWA_B, "WA88")),
        rejon="WA87")
    assert wynik.miejscowosc == WARSZAWA_A
    assert wynik.zrodlo == dm.ZRODLO_REJON
    assert wynik.zawezone_rejonem == (WARSZAWA_A,)


def test_rejon_warszawski_pasujacy_do_dwoch_nie_rozstrzyga():
    wynik = dm.dedukuj(
        ROZBICIE,
        szukajka((WARSZAWA_A, "WA87"), (WARSZAWA_B, "WA87"),
                 (LUGOWICE_A, "ND4")),
        rejon="WA87")
    assert wynik.miejscowosc is None
    assert wynik.zrodlo == dm.ZRODLO_DO_WYBORU
    # Zawężenie i tak jest warte pokazania - człowiek wybiera z dwóch
    # zamiast z trzech.
    assert wynik.zawezone_rejonem == tuple(sorted([WARSZAWA_A, WARSZAWA_B]))


def test_rejon_niepasujacy_do_zadnego_kandydata_nie_zawezajac_niczego():
    """Rejon, którego nie ma pod tym adresem, nie niesie informacji
    o miejscowości - wycięcie wszystkich kandydatów zostawiłoby człowieka
    z pustą listą, czyli gorzej niż przed regułą."""
    wynik = dm.dedukuj(
        ROZBICIE,
        szukajka((WARSZAWA_A, "WA87"), (LUGOWICE_A, "ND4"),
                 (LUGOWICE_B, "ND5")),
        rejon="WA99")
    assert wynik.zawezone_rejonem == ()
    assert len(wynik.kandydaci) == 3


def test_goly_numer_rejonu_degraduje_sie_do_pytania_nie_do_bledu():
    """Migawka trzyma rejony kanonicznie (`normalizuj_rejon_baska` robi
    z `87` -> `WA87`), ale nasze ścieżki zapisu używają `normalizuj_rejon`,
    który `WA` NIE dokleja - stare wiersze mogą więc nieść goły `87`.
    Kaskada takiego kodu nie rozpozna i to jest ZAMIERZONE: traci się
    pomoc, nie zyskuje błędu. Doklejenie `WA` na wejściu odzyskałoby te
    przypadki, ale zarazem pozwoliłoby gołemu numerowi ze starych danych
    rozstrzygać automatycznie - czyli ruszyłoby granicę 120/121. To
    decyzja dla kroku integracji, nie dla tego modułu."""
    wynik = dm.dedukuj(
        ROZBICIE,
        szukajka((WARSZAWA_A, "WA87"), (WARSZAWA_B, "WA88")),
        rejon="87")
    assert wynik.miejscowosc is None
    assert wynik.zrodlo == dm.ZRODLO_DO_WYBORU
    assert wynik.zawezone_rejonem == ()


def test_prefiks_warszawski_pochodzi_ze_wspolnej_stalej():
    """Kształt rejonu warszawskiego jest tu ostrzejszy niż goły prefiks
    (`WER` ma się NIE łapać), ale sam prefiks ma jedno źródło - inaczej
    zmiana stałej w `normalizacja` rozjechałaby się z tą kaskadą po
    cichu."""
    assert dm.czy_rejon_warszawski(
        normalizacja.PREFIKS_REJONU_WARSZAWA + "87") is True


@pytest.mark.parametrize("rejon", [None, "", "???", "   "])
def test_brak_rejonu_nie_uruchamia_reguly_trzeciej(rejon):
    wynik = dm.dedukuj(
        ROZBICIE,
        szukajka((WARSZAWA_A, "WA87"), (WARSZAWA_B, "WA88")),
        rejon=rejon)
    assert wynik.zrodlo == dm.ZRODLO_DO_WYBORU
    assert wynik.zawezone_rejonem == ()


# --- reguła 3, strona spoza WA: NIGDY automatycznie (32 na 59) ---------

def test_rejon_spoza_warszawy_nie_wpisuje_nawet_przy_jednym_trafieniu():
    """NAJWAŻNIEJSZY TEST GRANICY. `ND4` obejmuje 36 miejscowości, `ND5`
    35, `L9` 25 - zgodność rejonu NIE dowodzi więc gminy, choćby pod tym
    jednym adresem pasował tylko jeden kandydat. Wolno zawęzić listę
    człowiekowi, nie wolno wpisać za niego."""
    wynik = dm.dedukuj(
        ROZBICIE,
        szukajka((LUGOWICE_A, "ND4"), (KWIATOW, "L9")),
        rejon="ND4")
    assert wynik.miejscowosc is None
    assert wynik.zrodlo == dm.ZRODLO_DO_WYBORU
    assert wynik.zawezone_rejonem == (LUGOWICE_A,)
    assert wynik.kandydaci == tuple(sorted([LUGOWICE_A, KWIATOW]))


@pytest.mark.parametrize("rejon", ["ND4", "ND5", "L9", "R1", "W3",
                                   "XP2", "MM1", "XG1", "XL2"])
def test_zaden_prefiks_spoza_wa_nie_rozstrzyga_automatycznie(rejon):
    wynik = dm.dedukuj(
        ROZBICIE,
        szukajka((LUGOWICE_A, rejon), (KWIATOW, "ZZ9")),
        rejon=rejon)
    assert wynik.miejscowosc is None
    assert wynik.zawezone_rejonem == (LUGOWICE_A,)


@pytest.mark.parametrize("rejon, oczekiwane_zrodlo, oczekiwana_miejscowosc", [
    ("WA87", "rejon_wskazuje_gmine", WARSZAWA_A),
    ("ND4", "do_wyboru", None),
])
def test_o_wyniku_decyduje_wylacznie_prefiks_rejonu(
        rejon, oczekiwane_zrodlo, oczekiwana_miejscowosc):
    """Ten sam zestaw kandydatów, to samo zawężenie do jednego wiersza -
    różni je WYŁĄCZNIE prefiks rejonu. Dane są tu celowo sztuczne
    (dzielnica z rejonem `ND4`), żeby granica została odizolowana od
    wszystkiego innego."""
    wynik = dm.dedukuj(
        ROZBICIE,
        szukajka((WARSZAWA_A, "WA87"), (WARSZAWA_B, "ND4")),
        rejon=rejon)
    assert wynik.zrodlo == oczekiwane_zrodlo
    assert wynik.miejscowosc == oczekiwana_miejscowosc


# --- reguła 4: dzien_kuriera (86% par (kurier, dzień) w jednej gminie) -

def test_jedna_gmina_w_dniu_kuriera_rozstrzyga():
    wynik = dm.dedukuj(
        ROZBICIE,
        szukajka((LUGOWICE_A, "ND4"), (KWIATOW, "L9")),
        miejscowosci_dnia=[LUGOWICE_B])
    assert wynik.miejscowosc == LUGOWICE_A
    assert wynik.zrodlo == dm.ZRODLO_DZIEN_KURIERA


def test_dwie_gminy_w_dniu_kuriera_nie_rozstrzygaja():
    """9% par (kurier, dzień) rozjeżdża się na dwie gminy - wtedy dzień
    nie jest przesłanką, tylko szumem."""
    wynik = dm.dedukuj(
        ROZBICIE,
        szukajka((LUGOWICE_A, "ND4"), (KWIATOW, "L9")),
        miejscowosci_dnia=[LUGOWICE_B, KWIATOW])
    assert wynik.miejscowosc is None
    assert wynik.zrodlo == dm.ZRODLO_DO_WYBORU


def test_gmina_dnia_spoza_kandydatow_nie_rozstrzyga():
    wynik = dm.dedukuj(
        ROZBICIE,
        szukajka((LUGOWICE_A, "ND4"), (KWIATOW, "L9")),
        miejscowosci_dnia=[WARSZAWA_A])
    assert wynik.zrodlo == dm.ZRODLO_DO_WYBORU


def test_gmina_dnia_pasujaca_do_dwoch_kandydatow_nie_rozstrzyga():
    wynik = dm.dedukuj(
        ROZBICIE,
        szukajka((LUGOWICE_A, "ND4"), (LUGOWICE_B, "ND5"), (KWIATOW, "L9")),
        miejscowosci_dnia=[LUGOWICE_A])
    assert wynik.miejscowosc is None


def test_zawezenie_spoza_wa_nie_moze_odblokowac_dnia_kuriera():
    """Druga strona tej samej granicy, łatwa do przeoczenia: gdyby
    reguła 4 liczyła się na liście ZAWĘŻONEJ rejonem `ND4`, gmina dnia
    trafiłaby w dokładnie jednego kandydata i program wpisałby wynik -
    czyli rejon spoza WA rozstrzygnąłby automatycznie tylnymi drzwiami.
    Dlatego reguła 4 patrzy na PEŁNĄ listę kandydatów."""
    wynik = dm.dedukuj(
        ROZBICIE,
        szukajka((LUGOWICE_A, "ND4"), (LUGOWICE_B, "ND5"), (KWIATOW, "L9")),
        rejon="ND4",
        miejscowosci_dnia=[LUGOWICE_B])
    assert wynik.miejscowosc is None
    assert wynik.zrodlo == dm.ZRODLO_DO_WYBORU
    assert wynik.zawezone_rejonem == (LUGOWICE_A,)


def test_zawezenie_warszawskie_ma_pierwszenstwo_przed_dniem_kuriera():
    """Kolejność kaskady jest kolejnością pewności: rejon warszawski
    (120/121) bije dzień kuriera (86%), więc przy sprzecznych przesłankach
    wygrywa rejon."""
    wynik = dm.dedukuj(
        ROZBICIE,
        szukajka((WARSZAWA_A, "WA87"), (WARSZAWA_B, "WA88")),
        rejon="WA88",
        miejscowosci_dnia=[WARSZAWA_A])
    assert wynik.miejscowosc == WARSZAWA_B
    assert wynik.zrodlo == dm.ZRODLO_REJON


# --- kolejność kaskady: co bije co -------------------------------------
# Kaskada jest posortowana malejąco po ZMIERZONEJ pewności, więc kolejność
# bloków `if` w `dedukuj` jest zachowaniem, nie szczegółem zapisu. Testy
# niżej celowo podają dane, przy których obie sąsiadujące reguły mogłyby
# strzelić naraz - bez nich przestawienie bloków przechodzi niezauważone.
# Sąsiedztwa już przypięte gdzie indziej: 1 nie może kolidować (wymaga
# jednego kandydata), 3 vs 4 w `test_zawezenie_warszawskie_ma_...`,
# `z_adresu` vs reszta w `test_miejscowosc_podana_w_adresie_...`.

def test_zalozenie_warszawskie_bije_wskazanie_rejonu():
    """Reguła 2 (obalona w 0,2%, czyli trafna w 99,8%) stoi WYŻEJ niż
    reguła 3 (120 na 121, czyli 99,17%). Dane są celowo sprzeczne -
    rejon `WA88` prowadzi pod tym adresem do kandydata spoza Warszawy -
    żeby było widać, która reguła wygrywa, a nie tylko że wynik jest
    ten sam."""
    wynik = dm.dedukuj(
        ROZBICIE,
        szukajka((WARSZAWA_A, "WA87"), (KWIATOW, "WA88")),
        rejon="WA88")
    assert wynik.miejscowosc == WARSZAWA_A
    assert wynik.zrodlo == dm.ZRODLO_WARSZAWA


def test_zalozenie_warszawskie_bije_dzien_kuriera():
    """Reguła 2 (99,8%) stoi wyżej niż reguła 4 (86% par (kurier, dzień)
    w jednej gminie). Dzień kuriera wskazuje tu gminę Ługowice, a mimo to
    wygrywa założenie warszawskie."""
    wynik = dm.dedukuj(
        ROZBICIE,
        szukajka((WARSZAWA_A, "WA87"), (LUGOWICE_A, "ND4")),
        miejscowosci_dnia=[LUGOWICE_B])
    assert wynik.miejscowosc == WARSZAWA_A
    assert wynik.zrodlo == dm.ZRODLO_WARSZAWA


# --- reguły 5 i 6 oraz miejscowość podana wprost -----------------------

def test_kilku_kandydatow_bez_przeslanek_idzie_do_czlowieka():
    wynik = dm.dedukuj(
        ROZBICIE, szukajka((LUGOWICE_A, "ND4"), (KWIATOW, "L9")))
    assert wynik.miejscowosc is None
    assert wynik.zrodlo == dm.ZRODLO_DO_WYBORU
    assert wynik.kandydaci == tuple(sorted([LUGOWICE_A, KWIATOW]))
    assert wynik.rozstrzygniete is False


def test_brak_wpisow_w_rejonarzu_to_brak_a_nie_do_wyboru():
    """"Nie mam wpisu" i "mam kilka" to dwie różne odpowiedzi - zlanie
    ich zostawiłoby człowiekowi pustą listę do wyboru."""
    wynik = dm.dedukuj(ROZBICIE, szukajka())
    assert wynik == dm.Wynik()
    assert wynik.zrodlo == dm.ZRODLO_BRAK


def test_adres_bez_numeru_nie_odpytuje_rejonarza():
    dziennik = []
    wynik = dm.dedukuj(adresy.rozbij("Metro Ratusz"),
                       szukajka((KWIATOW, "L9"), dziennik=dziennik))
    assert wynik.zrodlo == dm.ZRODLO_BRAK
    assert dziennik == []


def test_miejscowosc_podana_w_adresie_nie_jest_dedukowana():
    """Kurier, który miejscowość napisał, jest lepszym źródłem niż
    kaskada - i musi być w wyniku ODRÓŻNIALNY od zgadywania, bo to
    zupełnie inny poziom zaufania."""
    dziennik = []
    wynik = dm.dedukuj(adresy.rozbij("Kwiatowa 8, Ługowice"),
                       szukajka((KWIATOW, "L9"), dziennik=dziennik))
    assert wynik.miejscowosc == "Ługowice"
    assert wynik.zrodlo == dm.ZRODLO_Z_ADRESU
    assert wynik.rozstrzygniete is True
    # Zapytanie do rejonarza się nie odbywa - to nie optymalizacja, tylko
    # gwarancja, że migawka nie ma jak nadpisać tego, co napisał człowiek.
    assert dziennik == []


# --- kontrakt modułu ---------------------------------------------------

@pytest.mark.parametrize("wejscie", [None, "Kwiatowa 8", 42, object()])
def test_zle_wejscie_daje_brak_zamiast_wyjatku(wejscie):
    """Ta sama zasada co w `adresy.rozbij`: wiersz, którego nie umiemy
    obsłużyć, ma trafić do poprawy, a nie wywalić całego importu."""
    assert dm.dedukuj(wejscie, szukajka((KWIATOW, "L9"))).zrodlo == dm.ZRODLO_BRAK


@pytest.mark.parametrize("wiersz", [
    None, (), ("",), (None, "L9"), ("   ", "L9"), 7, "Kwiatów",
])
def test_smieciowy_wiersz_z_rejonarza_jest_pomijany_bez_wyjatku(wiersz):
    wynik = dm.dedukuj(ROZBICIE, szukajka(wiersz, (KWIATOW, "L9")))
    assert wynik.miejscowosc == KWIATOW
    assert wynik.zrodlo == dm.ZRODLO_JEDNOZNACZNY


def test_wiersz_slownikowy_z_bazy_jest_rozumiany():
    """Produkcyjny kształt wiersza to `sqlite3.Row`/dict z zapytania
    `SELECT miejscowosc, rejon FROM adresy_rejony ...` - kaskada musi go
    przyjąć bez przepakowywania po stronie wywołującego."""
    wynik = dm.dedukuj(
        ROZBICIE, szukajka({"miejscowosc": KWIATOW, "rejon": "L9"}))
    assert wynik.miejscowosc == KWIATOW


def test_wiersz_bez_kolumny_rejonu_nie_wywraca_kaskady():
    wynik = dm.dedukuj(ROZBICIE, szukajka({"miejscowosc": KWIATOW}))
    assert wynik.miejscowosc == KWIATOW


def test_gotowy_kandydat_przechodzi_bez_zmian():
    wynik = dm.dedukuj(
        ROZBICIE, szukajka(dm.Kandydat(miejscowosc=KWIATOW, rejon="L9")))
    assert wynik.miejscowosc == KWIATOW


def test_zrodlo_moze_zwrocic_generator():
    """Rejonarz czyta duże zbiory generatorem (patrz `rejonarz.py`) -
    kaskada nie może zakładać, że dostaje listę do wielokrotnego
    przejścia."""
    def szukaj(_klucz):
        return (w for w in [(LUGOWICE_A, "ND4"), (KWIATOW, "L9")])

    assert dm.dedukuj(ROZBICIE, szukaj).zrodlo == dm.ZRODLO_DO_WYBORU


def test_smieciowe_miejscowosci_dnia_nie_wywracaja_kaskady():
    wynik = dm.dedukuj(
        ROZBICIE,
        szukajka((LUGOWICE_A, "ND4"), (KWIATOW, "L9")),
        miejscowosci_dnia=[None, "", "   ", LUGOWICE_B])
    assert wynik.miejscowosc == LUGOWICE_A


def test_wynik_jest_niemutowalny():
    """Wynik dedukcji trafia do `adresy.zrodlo_miejscowosci` i bywa
    przekazywany dalej - podmiana pola w locie rozjechałaby zapisane
    źródło z zapisaną wartością."""
    wynik = dm.dedukuj(ROZBICIE, szukajka((KWIATOW, "L9")))
    with pytest.raises(dataclasses.FrozenInstanceError):
        wynik.miejscowosc = LUGOWICE_A


@pytest.mark.parametrize("kwargi", [
    {},
    {"rejon": "WA87"},
    {"miejscowosci_dnia": [LUGOWICE_B]},
    {"rejon": "ND4", "miejscowosci_dnia": [LUGOWICE_B]},
])
def test_wpisana_miejscowosc_zawsze_jest_wsrod_kandydatow(kwargi):
    """Inwariant całej kaskady: nigdy nie wpisujemy wartości spoza listy,
    którą pokazalibyśmy człowiekowi. Bez tego "wybierz z listy" i "wpisano
    automatycznie" mogłyby wskazywać na różne miejscowości."""
    wynik = dm.dedukuj(
        ROZBICIE,
        szukajka((WARSZAWA_A, "WA87"), (LUGOWICE_A, "ND4")),
        **kwargi)
    if wynik.rozstrzygniete:
        assert wynik.miejscowosc in wynik.kandydaci


def test_nazwy_zrodel_sa_stabilne():
    """Te napisy lądują w `adresy.zrodlo_miejscowosci` w bazie - zmiana
    którejkolwiek unieważnia dane już zapisane, więc jest przypięta."""
    assert (dm.ZRODLO_JEDNOZNACZNY, dm.ZRODLO_WARSZAWA, dm.ZRODLO_REJON,
            dm.ZRODLO_DZIEN_KURIERA, dm.ZRODLO_DO_WYBORU, dm.ZRODLO_BRAK,
            dm.ZRODLO_Z_ADRESU) == (
        "jednoznaczny_w_rejonarzu", "zalozona_warszawa",
        "rejon_wskazuje_gmine", "dzien_kuriera", "do_wyboru", "brak",
        "z_adresu")

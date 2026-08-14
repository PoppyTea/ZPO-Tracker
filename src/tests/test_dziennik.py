"""
Diagnostyka: log tekstowy (kanał wsparcia) + JSONL dziennik operacji
(indeks dla migawek i cofania). TDD.

Kontekst, którego te testy pilnują - w buildzie PyInstallera z
`console=False` (`zpo_tracker.spec`) `sys.stderr is None`, więc:
  1. konfiguracja logowania NIE MOŻE dokładać handlera na stderr,
  2. `sys.excepthook` NIE łapie wyjątków z callbacków Tk - potrzebne jest
     osobne podpięcie `report_callback_exception`.
Bez obu tych rzeczy każda awaria w produkcji jest dziś niewidzialna.
"""
import json
import logging

import pytest

from zpo_tracker import dziennik


@pytest.fixture
def katalog(tmp_path):
    """Świeży katalog na logi + sprzątanie globalnego stanu logging."""
    yield tmp_path
    dziennik.odepnij()


# --- skonfiguruj ---

def test_konfiguracja_nie_dodaje_handlera_na_stderr(katalog):
    # sys.stderr is None w buildzie okienkowym - StreamHandler na None
    # zamieniłby samo logowanie w źródło awarii
    log = dziennik.skonfiguruj(katalog)
    strumieniowe = [
        h for h in log.handlers
        if isinstance(h, logging.StreamHandler)
        and not isinstance(h, logging.FileHandler)
    ]
    assert strumieniowe == []


def test_konfiguracja_wylacza_raiseExceptions(katalog):
    dziennik.skonfiguruj(katalog)
    assert logging.raiseExceptions is False


def test_konfiguracja_jest_idempotentna(katalog):
    # dwa wywołania (np. main() + Aplikacja.__init__) nie mogą dublować
    # handlerów - dwa uchwyty na ten sam plik psują rotację na Windows
    log = dziennik.skonfiguruj(katalog)
    ile = len(log.handlers)
    log = dziennik.skonfiguruj(katalog)
    assert len(log.handlers) == ile


def test_konfiguracja_na_inny_katalog_odpina_poprzedni(katalog, tmp_path):
    # logger to singleton na poziomie procesu: bez odpięcia poprzedniego
    # handlera wpis trafia do OBU lokalizacji naraz - czyli log wycieka
    # tam, gdzie już nie powinien
    dziennik.skonfiguruj(katalog)
    nowy = tmp_path / "inny"
    log = dziennik.skonfiguruj(nowy)
    log.error("wpis kontrolny")

    assert (nowy / dziennik.NAZWA_LOGU).exists()
    assert not (katalog / dziennik.NAZWA_LOGU).exists()


# --- zainstaluj_haki ---

class _FalszywyTk:
    """Namiastka okna Tk - `report_callback_exception` to zwykły atrybut."""


def test_wyjatek_z_callbacku_tk_trafia_do_pliku(katalog):
    dziennik.skonfiguruj(katalog)
    app = _FalszywyTk()
    dziennik.zainstaluj_haki(app)

    try:
        raise ValueError("awaria w callbacku")
    except ValueError:
        import sys
        app.report_callback_exception(*sys.exc_info())

    tresc = (katalog / dziennik.NAZWA_LOGU).read_text(encoding="utf-8")
    assert "awaria w callbacku" in tresc
    assert "ValueError" in tresc


def test_hak_tk_nie_podnosi_wyjatku_dalej(katalog):
    # awaria w jednym callbacku nie może ubić całej aplikacji
    dziennik.skonfiguruj(katalog)
    app = _FalszywyTk()
    dziennik.zainstaluj_haki(app)
    import sys
    try:
        raise ValueError("x")
    except ValueError:
        app.report_callback_exception(*sys.exc_info())  # nie rzuca


def test_excepthook_zapisuje_traceback(katalog):
    import sys
    dziennik.skonfiguruj(katalog)
    poprzedni = sys.excepthook
    try:
        dziennik.zainstaluj_haki()
        try:
            raise RuntimeError("awaria poza Tk")
        except RuntimeError:
            sys.excepthook(*sys.exc_info())
        tresc = (katalog / dziennik.NAZWA_LOGU).read_text(encoding="utf-8")
        assert "awaria poza Tk" in tresc
    finally:
        sys.excepthook = poprzedni


# --- dziennik operacji (JSONL) ---

def test_wpis_operacji_zapisuje_sie_jako_jsonl(katalog):
    dziennik.skonfiguruj(katalog)
    dziennik.zapisz_operacje(
        katalog, seq=1, rodzaj="import", etykieta="sierpien.xlsx",
        liczba_wierszy=1239, wersja_schematu=1,
    )
    linie = (katalog / dziennik.NAZWA_DZIENNIKA).read_text(
        encoding="utf-8").strip().splitlines()
    assert len(linie) == 1
    wpis = json.loads(linie[0])
    assert wpis["rodzaj"] == "import"
    assert wpis["liczba_wierszy"] == 1239
    assert wpis["seq"] == 1


def test_wpis_operacji_ma_tylko_zadeklarowane_pola(katalog):
    # dziennik JSONL jest kandydatem do wysłania na zewnątrz (wsparcie,
    # w przyszłości katalog wymiany), więc jego kształt musi być zamknięty
    # - żadnych nazwisk kurierów ani adresów, tylko liczniki i identyfikatory
    dziennik.skonfiguruj(katalog)
    dziennik.zapisz_operacje(
        katalog, seq=1, rodzaj="zapis_blankietu", etykieta="blok 2026-08",
        liczba_wierszy=12, wersja_schematu=1,
    )
    wpis = json.loads((katalog / dziennik.NAZWA_DZIENNIKA).read_text(
        encoding="utf-8").strip())
    assert set(wpis) == set(dziennik.POLA_WPISU)


def test_wpis_operacji_przyjmuje_liczbe_pominietych(katalog):
    # 0.1-alpha.3.2: wpis wszystkich-duplikatów przestaje wyglądać jak
    # sukces - patrz zakladka_wprowadzanie.py
    dziennik.skonfiguruj(katalog)
    wpis = dziennik.zapisz_operacje(
        katalog, seq=1, rodzaj="zapis_blankietu", etykieta="blok 2026-08",
        liczba_wierszy=3, liczba_pominietych=2, wersja_schematu=1,
    )
    assert wpis["liczba_pominietych"] == 2


def test_wpis_operacji_bez_liczby_pominietych_jest_none(katalog):
    dziennik.skonfiguruj(katalog)
    wpis = dziennik.zapisz_operacje(
        katalog, seq=1, rodzaj="import", etykieta="x", wersja_schematu=1)
    assert wpis["liczba_pominietych"] is None


def test_odczyt_zwraca_wpisy_w_kolejnosci_seq(katalog):
    dziennik.skonfiguruj(katalog)
    for s in (3, 1, 2):
        dziennik.zapisz_operacje(
            katalog, seq=s, rodzaj="import", etykieta=f"op{s}",
            liczba_wierszy=1, wersja_schematu=1,
        )
    assert [w["seq"] for w in dziennik.wczytaj_operacje(katalog)] == [1, 2, 3]


def test_odczyt_pomija_uszkodzona_ostatnia_linie(katalog):
    # zapis przerwany awarią zasilania zostawia urwaną linię - reszta
    # dziennika musi pozostać czytelna
    dziennik.skonfiguruj(katalog)
    dziennik.zapisz_operacje(
        katalog, seq=1, rodzaj="import", etykieta="ok",
        liczba_wierszy=5, wersja_schematu=1,
    )
    with open(katalog / dziennik.NAZWA_DZIENNIKA, "a", encoding="utf-8") as f:
        f.write('{"seq": 2, "rodzaj": "impo')

    wpisy = dziennik.wczytaj_operacje(katalog)
    assert [w["seq"] for w in wpisy] == [1]


def test_odczyt_pustego_dziennika_daje_pusta_liste(katalog):
    assert dziennik.wczytaj_operacje(katalog) == []


def test_kolejny_seq_rosnie_od_ostatniego_wpisu(katalog):
    # kolejność operacji nie może zależeć od zegara: w Polsce godzina
    # 02:00-03:00 powtarza się raz w roku, a zegary firmowych maszyn bywają
    # rozjechane
    dziennik.skonfiguruj(katalog)
    assert dziennik.nastepny_seq(katalog) == 1
    dziennik.zapisz_operacje(
        katalog, seq=1, rodzaj="import", etykieta="a",
        liczba_wierszy=1, wersja_schematu=1,
    )
    assert dziennik.nastepny_seq(katalog) == 2

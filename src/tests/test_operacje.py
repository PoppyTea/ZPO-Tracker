"""
Fasada łącząca migawki (kopie.py) z dziennikiem (dziennik.py): każda
mutująca operacja dostaje migawkę SPRZED wykonania + wpis w dzienniku,
więc cofnięcie do dowolnego punktu w historii jest zawsze możliwe - cel
`0.1-alpha.3` "żaden pojedynczy błąd nie kosztuje więcej niż jedną
operację". TDD.
"""
import sqlite3

import pytest

from zpo_tracker import dziennik, kopie, operacje, repo


@pytest.fixture
def conn():
    conn = repo.polacz(":memory:")
    repo.utworz_schemat(conn)
    yield conn
    conn.close()


def _wstaw_kuriera(conn, nazwa):
    cur = conn.execute("INSERT INTO kurierzy (imie_nazwisko) VALUES (?)", (nazwa,))
    return cur.lastrowid


# --- wykonaj ---

def test_wykonaj_wykonuje_funkcje_i_zwraca_jej_wynik(conn, tmp_path):
    wynik = operacje.wykonaj(
        conn, tmp_path, rodzaj="test", etykieta="e",
        funkcja=_wstaw_kuriera, args=("Kowalski Jan",),
    )
    assert wynik is not None
    assert conn.execute(
        "SELECT imie_nazwisko FROM kurierzy WHERE id = ?", (wynik,)
    ).fetchone()[0] == "Kowalski Jan"


def test_wykonaj_robi_migawke_sprzed_wykonania_funkcji(conn, tmp_path):
    operacje.wykonaj(
        conn, tmp_path, rodzaj="test", etykieta="e",
        funkcja=_wstaw_kuriera, args=("Kowalski Jan",),
    )
    migawki = kopie.lista_migawek(tmp_path)
    assert len(migawki) == 1
    kopia = sqlite3.connect(str(migawki[0]))
    # migawka SPRZED - kurier wstawiony PRZEZ tę operację nie może w niej być
    assert kopia.execute("SELECT COUNT(*) FROM kurierzy").fetchone()[0] == 0
    kopia.close()


def test_wykonaj_zapisuje_wpis_w_dzienniku(conn, tmp_path):
    operacje.wykonaj(
        conn, tmp_path, rodzaj="zapis_blankietu", etykieta="blok 2026-08",
        funkcja=_wstaw_kuriera, args=("Kowalski Jan",),
    )
    wpisy = dziennik.wczytaj_operacje(tmp_path)
    assert len(wpisy) == 1
    assert wpisy[0]["rodzaj"] == "zapis_blankietu"
    assert wpisy[0]["etykieta"] == "blok 2026-08"
    assert wpisy[0]["wynik"] == "ok"
    assert wpisy[0]["plik_migawki"] is not None


def test_wykonaj_zapisuje_czas_wpisu(conn, tmp_path):
    # bez tego kopie.przytnij_migawki nie ma po czym liczyć wieku migawki
    operacje.wykonaj(
        conn, tmp_path, rodzaj="test", etykieta="e",
        funkcja=_wstaw_kuriera, args=("Kowalski Jan",),
    )
    wpisy = dziennik.wczytaj_operacje(tmp_path)
    assert wpisy[0]["czas"] is not None


def test_wykonaj_uzywa_licz_wiersze_do_liczby_wierszy_w_dzienniku(conn, tmp_path):
    operacje.wykonaj(
        conn, tmp_path, rodzaj="test", etykieta="e",
        funkcja=lambda conn: [1, 2, 3], licz_wiersze=len,
    )
    wpisy = dziennik.wczytaj_operacje(tmp_path)
    assert wpisy[0]["liczba_wierszy"] == 3


def test_wykonaj_bez_licz_wiersze_zostawia_liczbe_wierszy_none(conn, tmp_path):
    operacje.wykonaj(
        conn, tmp_path, rodzaj="test", etykieta="e",
        funkcja=_wstaw_kuriera, args=("Kowalski Jan",),
    )
    wpisy = dziennik.wczytaj_operacje(tmp_path)
    assert wpisy[0]["liczba_wierszy"] is None


def test_wykonaj_uzywa_licz_pominiete_do_liczby_pominietych_w_dzienniku(conn, tmp_path):
    operacje.wykonaj(
        conn, tmp_path, rodzaj="test", etykieta="e",
        funkcja=lambda conn: [1, 2, 3], licz_pominiete=len,
    )
    wpisy = dziennik.wczytaj_operacje(tmp_path)
    assert wpisy[0]["liczba_pominietych"] == 3


def test_wykonaj_bez_licz_pominiete_zostawia_none(conn, tmp_path):
    operacje.wykonaj(
        conn, tmp_path, rodzaj="test", etykieta="e",
        funkcja=_wstaw_kuriera, args=("Kowalski Jan",),
    )
    wpisy = dziennik.wczytaj_operacje(tmp_path)
    assert wpisy[0]["liczba_pominietych"] is None


def test_wykonaj_przy_wyjatku_podnosi_go_dalej(conn, tmp_path):
    def _wybuchnij(conn):
        raise ValueError("awaria testowa")

    with pytest.raises(ValueError, match="awaria testowa"):
        operacje.wykonaj(conn, tmp_path, rodzaj="test", etykieta="e", funkcja=_wybuchnij)


def test_wykonaj_przy_wyjatku_i_tak_zapisuje_wpis_z_wynikiem_blad(conn, tmp_path):
    def _wybuchnij(conn):
        raise ValueError("awaria testowa")

    with pytest.raises(ValueError):
        operacje.wykonaj(conn, tmp_path, rodzaj="test", etykieta="e", funkcja=_wybuchnij)

    wpisy = dziennik.wczytaj_operacje(tmp_path)
    assert len(wpisy) == 1
    assert wpisy[0]["wynik"] == "blad"
    # migawka SPRZED wciąż istnieje - operacja nie zdążyła nic zepsuć,
    # ale ślad w historii musi zostać, żeby dziennik pozostał kompletny
    assert wpisy[0]["plik_migawki"] is not None


def test_wykonaj_kolejne_operacje_dostaja_rosnace_seq(conn, tmp_path):
    operacje.wykonaj(conn, tmp_path, rodzaj="test", etykieta="a", funkcja=_wstaw_kuriera, args=("A",))
    operacje.wykonaj(conn, tmp_path, rodzaj="test", etykieta="b", funkcja=_wstaw_kuriera, args=("B",))
    wpisy = dziennik.wczytaj_operacje(tmp_path)
    assert [w["seq"] for w in wpisy] == [1, 2]


# --- cofnij ---

@pytest.fixture
def sciezka_bazy(tmp_path):
    sciezka = tmp_path / "baza.db"
    conn = sqlite3.connect(str(sciezka))
    conn.close()
    return sciezka


def _polacz_i_zaszczep_schemat(sciezka_bazy):
    conn = repo.polacz(str(sciezka_bazy))
    repo.utworz_schemat(conn)
    return conn


def test_cofnij_przywraca_stan_sprzed_wskazanej_operacji(tmp_path, sciezka_bazy):
    conn = _polacz_i_zaszczep_schemat(sciezka_bazy)
    operacje.wykonaj(conn, tmp_path, rodzaj="test", etykieta="a",
                      funkcja=_wstaw_kuriera, args=("Kowalski Jan",))
    seq_do_cofniecia = dziennik.wczytaj_operacje(tmp_path)[-1]["seq"]
    operacje.wykonaj(conn, tmp_path, rodzaj="test", etykieta="b",
                      funkcja=_wstaw_kuriera, args=("Nowak Piotr",))
    conn.close()

    operacje.cofnij(tmp_path, sciezka_bazy, seq_do_cofniecia)

    po_cofnieciu = repo.polacz(str(sciezka_bazy))
    nazwiska = [r[0] for r in po_cofnieciu.execute(
        "SELECT imie_nazwisko FROM kurierzy").fetchall()]
    assert nazwiska == []  # stan SPRZED operacji "a" - jeszcze bez Kowalskiego
    po_cofnieciu.close()


def test_cofnij_zapisuje_sie_jako_nowa_operacja_z_wlasna_migawka(tmp_path, sciezka_bazy):
    # dzięki temu "cofnięcie cofnięcia" jest możliwe tym samym mechanizmem
    conn = _polacz_i_zaszczep_schemat(sciezka_bazy)
    operacje.wykonaj(conn, tmp_path, rodzaj="test", etykieta="a",
                      funkcja=_wstaw_kuriera, args=("Kowalski Jan",))
    seq_do_cofniecia = dziennik.wczytaj_operacje(tmp_path)[-1]["seq"]
    conn.close()

    operacje.cofnij(tmp_path, sciezka_bazy, seq_do_cofniecia)

    wpisy = dziennik.wczytaj_operacje(tmp_path)
    assert wpisy[-1]["rodzaj"] == "cofniecie"
    assert wpisy[-1]["plik_migawki"] is not None
    assert wpisy[-1]["czas"] is not None
    assert len(kopie.lista_migawek(tmp_path)) == 2  # migawka "a" + migawka cofnięcia


def test_cofnij_nieznana_operacja_rzuca_wyjatek(tmp_path, sciezka_bazy):
    with pytest.raises(ValueError, match="[Nn]ieznan"):
        operacje.cofnij(tmp_path, sciezka_bazy, 999)


def test_cofnij_operacja_bez_migawki_rzuca_wyjatek(tmp_path, sciezka_bazy):
    dziennik.zapisz_operacje(
        tmp_path, seq=1, rodzaj="import", etykieta="e", plik_migawki=None,
    )
    with pytest.raises(ValueError, match="migawk"):
        operacje.cofnij(tmp_path, sciezka_bazy, 1)


def test_cofnij_operacja_z_przycieta_migawka_rzuca_czytelny_wyjatek(tmp_path, sciezka_bazy):
    # plik istniał kiedyś (patrz kopie.przytnij_migawki), ale zniknął z dysku
    dziennik.zapisz_operacje(
        tmp_path, seq=1, rodzaj="import", etykieta="e",
        plik_migawki=str(tmp_path / "migawki" / "000001.db"),
    )
    with pytest.raises(ValueError, match="przycięta"):
        operacje.cofnij(tmp_path, sciezka_bazy, 1)


# --- znajdz_najblizsze_migawki ---

def _wpis_z_migawka(tmp_path, seq, ma_plik):
    plik = kopie.katalog_migawek(tmp_path) / f"{seq:06d}.db"
    if ma_plik:
        plik.write_bytes(b"x")
    dziennik.zapisz_operacje(
        tmp_path, seq=seq, rodzaj="test", etykieta=f"op{seq}",
        plik_migawki=str(plik), czas=f"2026-08-{seq:02d}T00:00:00",
    )


def test_znajdz_najblizsze_migawki_pomija_wpisy_bez_pliku(tmp_path):
    _wpis_z_migawka(tmp_path, 1, ma_plik=True)
    _wpis_z_migawka(tmp_path, 2, ma_plik=False)
    _wpis_z_migawka(tmp_path, 3, ma_plik=False)  # cel - jego migawka zniknęła
    _wpis_z_migawka(tmp_path, 4, ma_plik=False)
    _wpis_z_migawka(tmp_path, 5, ma_plik=True)

    poprzednia, nastepna = operacje.znajdz_najblizsze_migawki(tmp_path, 3)

    assert poprzednia["seq"] == 1
    assert nastepna["seq"] == 5


def test_znajdz_najblizsze_migawki_bezposredni_sasiedzi_gdy_maja_plik(tmp_path):
    _wpis_z_migawka(tmp_path, 1, ma_plik=True)
    _wpis_z_migawka(tmp_path, 2, ma_plik=False)  # cel
    _wpis_z_migawka(tmp_path, 3, ma_plik=True)

    poprzednia, nastepna = operacje.znajdz_najblizsze_migawki(tmp_path, 2)

    assert poprzednia["seq"] == 1
    assert nastepna["seq"] == 3


def test_znajdz_najblizsze_migawki_brak_poprzedniej(tmp_path):
    _wpis_z_migawka(tmp_path, 1, ma_plik=False)  # cel, najstarsza operacja w ogóle
    _wpis_z_migawka(tmp_path, 2, ma_plik=True)

    poprzednia, nastepna = operacje.znajdz_najblizsze_migawki(tmp_path, 1)

    assert poprzednia is None
    assert nastepna["seq"] == 2


def test_znajdz_najblizsze_migawki_brak_nastepnej(tmp_path):
    _wpis_z_migawka(tmp_path, 1, ma_plik=True)
    _wpis_z_migawka(tmp_path, 2, ma_plik=False)  # cel, najnowsza operacja w ogóle

    poprzednia, nastepna = operacje.znajdz_najblizsze_migawki(tmp_path, 2)

    assert poprzednia["seq"] == 1
    assert nastepna is None


def test_znajdz_najblizsze_migawki_obie_brak_nie_wybucha(tmp_path):
    _wpis_z_migawka(tmp_path, 1, ma_plik=False)  # jedyna operacja w ogóle

    poprzednia, nastepna = operacje.znajdz_najblizsze_migawki(tmp_path, 1)

    assert poprzednia is None
    assert nastepna is None


# --- liczniki wierszy (helpery dla wywołań GUI) ---

def test_licz_zapisane_wiersze_pomija_pominiete():
    wyniki = [
        {"id": 1, "pominieto": False},
        {"id": None, "pominieto": True},
        {"id": 3, "pominieto": False},
    ]
    assert operacje.licz_zapisane_wiersze(wyniki) == 2


def test_licz_pominiete_wiersze_liczy_wylacznie_pominiete():
    wyniki = [
        {"id": 1, "pominieto": False},
        {"id": None, "pominieto": True},
        {"id": None, "pominieto": True},
    ]
    assert operacje.licz_pominiete_wiersze(wyniki) == 2

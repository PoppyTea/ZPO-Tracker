"""
Atrybucja zmian do autora. SQLite w pamięci, bez mocków. TDD.

Sedno projektu: `users.id` to **UUIDv5 wyliczone z `domena\\login`**, a nie
losowy UUID nadawany przy pierwszym zetknięciu z nowym loginem. Losowy
rozjechałby się między stacjami - każda nadałaby temu samemu człowiekowi
inny identyfikator, a po ich zsynchronizowaniu ta sama osoba istniałaby
wielokrotnie. UUIDv5 liczy się identycznie wszędzie, bez koordynacji
i bez wyścigu przy pierwszym uruchomieniu.

Nr kadrowy jest atrybutem biznesowym OBOK UUID, nigdy zamiast: wpisuje go
człowiek, a 5 znaków bez sumy kontrolnej znaczy, że literówka jest
niewykrywalna i rozniosłaby się po synchronizacji.
"""
from datetime import date

import pytest

from zpo_tracker import repo, uzytkownicy
from zpo_tracker.models import Blankiet, WierszBlankietu


@pytest.fixture
def conn():
    conn = repo.polacz(":memory:")
    repo.utworz_schemat(conn)
    yield conn
    conn.close()


# --- tożsamość ---

def test_uuid_uzytkownika_jest_taki_sam_dla_tego_samego_loginu():
    # to jest CAŁY sens UUIDv5 - dwie stacje liczą identycznie, bez
    # uzgadniania czegokolwiek między sobą
    a = uzytkownicy.uuid_uzytkownika("POCZTA-POLSKA\\jkowalski")
    b = uzytkownicy.uuid_uzytkownika("POCZTA-POLSKA\\jkowalski")
    assert a == b


def test_uuid_uzytkownika_ignoruje_wielkosc_liter_loginu():
    # Windows nie rozróżnia wielkości liter w nazwach kont, więc
    # "JKowalski" i "jkowalski" to ta sama osoba
    a = uzytkownicy.uuid_uzytkownika("POCZTA-POLSKA\\JKowalski")
    b = uzytkownicy.uuid_uzytkownika("poczta-polska\\jkowalski")
    assert a == b


def test_rozne_loginy_daja_rozne_uuid():
    a = uzytkownicy.uuid_uzytkownika("POCZTA-POLSKA\\jkowalski")
    b = uzytkownicy.uuid_uzytkownika("POCZTA-POLSKA\\anowak")
    assert a != b


def test_biezacy_login_sklada_domene_i_konto_na_windows():
    login = uzytkownicy.biezacy_login(
        srodowisko={"USERDOMAIN": "POCZTA-POLSKA", "USERNAME": "jkowalski"})
    assert login == "POCZTA-POLSKA\\jkowalski"


def test_biezacy_login_bez_domeny_uzywa_samego_konta():
    login = uzytkownicy.biezacy_login(srodowisko={"USERNAME": "jkowalski"})
    assert login == "jkowalski"


# --- nr kadrowy ---

@pytest.mark.parametrize("nr", ["abc12", "ABCDE", "12345", "a1B2c"])
def test_nr_kadrowy_przyjmuje_poprawny_format(nr):
    assert uzytkownicy.poprawny_nr_kadrowy(nr) is True


@pytest.mark.parametrize("nr", ["abc1", "abc123", "abc-1", "abc 1", "ąbcde", "", None])
def test_nr_kadrowy_odrzuca_zly_format(nr):
    assert uzytkownicy.poprawny_nr_kadrowy(nr) is False


def test_nr_kadrowy_rozroznia_wielkosc_liter(conn):
    # wymóg wprost od użytkownika: case sensitive. W SQLite pilnuje tego
    # GLOB (LIKE jest niewrażliwy na wielkość liter i ten test by przeszedł
    # niezależnie od poprawności implementacji)
    uzytkownicy.zapewnij_uzytkownika(
        conn, login="dom\\a", alias="A", nr_kadrowy="ab12X")
    uzytkownicy.zapewnij_uzytkownika(
        conn, login="dom\\b", alias="B", nr_kadrowy="ab12x")
    numery = [r[0] for r in conn.execute(
        "SELECT nr_kadrowy FROM users ORDER BY nr_kadrowy")]
    assert len(numery) == 2


def test_baza_odrzuca_nr_kadrowy_o_zlej_dlugosci(conn):
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO users(id, login, alias, nr_kadrowy, utworzono)"
            " VALUES ('x','dom\\c','C','abc',  '2026-08-11')")


# --- zapewnij_uzytkownika ---

def test_zapewnij_uzytkownika_tworzy_wpis(conn):
    uid = uzytkownicy.zapewnij_uzytkownika(
        conn, login="POCZTA-POLSKA\\jkowalski", alias="Jan Kowalski",
        nr_kadrowy="ab12X")
    wiersz = conn.execute(
        "SELECT id, login, alias, nr_kadrowy FROM users").fetchone()
    assert wiersz["id"] == uid == uzytkownicy.uuid_uzytkownika(
        "POCZTA-POLSKA\\jkowalski")
    assert wiersz["alias"] == "Jan Kowalski"


def test_zapewnij_uzytkownika_jest_idempotentne(conn):
    for _ in range(3):
        uzytkownicy.zapewnij_uzytkownika(conn, login="dom\\a", alias="A")
    assert conn.execute("SELECT count(*) FROM users").fetchone()[0] == 1


def test_alias_nie_zmienia_tozsamosci(conn):
    uid1 = uzytkownicy.zapewnij_uzytkownika(conn, login="dom\\a", alias="Jan Kowalksi")
    uid2 = uzytkownicy.zapewnij_uzytkownika(conn, login="dom\\a", alias="Jan Kowalski")
    assert uid1 == uid2
    assert conn.execute("SELECT count(*) FROM users").fetchone()[0] == 1
    assert conn.execute("SELECT alias FROM users").fetchone()[0] == "Jan Kowalski"


def test_brak_aliasu_jest_wykrywalny(conn):
    # popup przy pierwszym uruchomieniu ma się pokazać dokładnie wtedy
    uzytkownicy.zapewnij_uzytkownika(conn, login="dom\\a")
    assert uzytkownicy.wymaga_uzupelnienia(conn, login="dom\\a") is True
    uzytkownicy.zapewnij_uzytkownika(
        conn, login="dom\\a", alias="Jan Kowalski", nr_kadrowy="ab12X")
    assert uzytkownicy.wymaga_uzupelnienia(conn, login="dom\\a") is False


def test_brak_nr_kadrowego_nie_jest_wykrywalny(conn):
    # 0.1-alpha.3.2: nr kadrowy przestaje być wymagany - pracownicy jeszcze
    # go nie mają w momencie wdrożenia; alias sam wystarcza
    uzytkownicy.zapewnij_uzytkownika(conn, login="dom\\a", alias="Jan Kowalski")
    assert uzytkownicy.wymaga_uzupelnienia(conn, login="dom\\a") is False


# --- kontrola krzyżowa UUID <-> nr kadrowy ---

def test_ten_sam_uuid_inny_nr_kadrowy_daje_ostrzezenie(conn):
    # to samo konto Windows, a inny numer => ktoś się pomylił przy wpisywaniu
    uzytkownicy.zapewnij_uzytkownika(
        conn, login="dom\\a", alias="A", nr_kadrowy="ab12X")
    ostrzezenia = uzytkownicy.ostrzezenia_tozsamosci(
        conn, login="dom\\a", nr_kadrowy="zz99Y")
    assert len(ostrzezenia) == 1
    assert "literówk" in ostrzezenia[0].lower()


def test_ten_sam_nr_kadrowy_inne_konto_daje_ostrzezenie(conn):
    # ten sam człowiek na dwóch kontach Windows
    uzytkownicy.zapewnij_uzytkownika(
        conn, login="dom\\a", alias="A", nr_kadrowy="ab12X")
    ostrzezenia = uzytkownicy.ostrzezenia_tozsamosci(
        conn, login="dom\\b", nr_kadrowy="ab12X")
    assert len(ostrzezenia) == 1
    assert "konta" in ostrzezenia[0].lower()


def test_zgodna_para_nie_daje_ostrzezen(conn):
    uzytkownicy.zapewnij_uzytkownika(
        conn, login="dom\\a", alias="A", nr_kadrowy="ab12X")
    assert uzytkownicy.ostrzezenia_tozsamosci(
        conn, login="dom\\a", nr_kadrowy="ab12X") == []


def test_ostrzezenia_sa_miekkie_nie_blokuja_zapisu(conn):
    # zgodnie z docs/ux-ui.md: miękkie ostrzeżenia, nie twarde blokady
    uzytkownicy.zapewnij_uzytkownika(
        conn, login="dom\\a", alias="A", nr_kadrowy="ab12X")
    uzytkownicy.zapewnij_uzytkownika(
        conn, login="dom\\b", alias="B", nr_kadrowy="zz99Y")
    assert conn.execute("SELECT count(*) FROM users").fetchone()[0] == 2


# --- stemplowanie transakcji ---

def _blok(**nadpisz):
    wiersze = nadpisz.pop("wiersze", None)
    if wiersze is None:
        wiersze = [WierszBlankietu(nadawca="Żabka", adres="Odkryta 24", rejon="WA87", ilosc_total=3)]
    dane = dict(kurier="Kowalski Jan", data=date(2026, 8, 10), wiersze=wiersze)
    dane.update(nadpisz)
    return Blankiet(**dane)


def test_zapisz_blok_stempluje_autora_i_czas(conn):
    uid = uzytkownicy.zapewnij_uzytkownika(conn, login="dom\\a", alias="A")
    repo.zapisz_blankiet(conn, _blok(), autor_id=uid, teraz="2026-08-11T10:00:00")
    wiersz = conn.execute(
        "SELECT autor_id, utworzono, zmodyfikowano FROM transakcje").fetchone()
    assert wiersz["autor_id"] == uid
    assert wiersz["utworzono"] == "2026-08-11T10:00:00"
    assert wiersz["zmodyfikowano"] == "2026-08-11T10:00:00"


def test_zapisz_blok_nadaje_uuid_kazdemu_wierszowi(conn):
    # tożsamość wiersza niezależna od klucza naturalnego: poprawka daty
    # albo kuriera zmienia klucz, a przy synchronizacji między stacjami wyglądałoby
    # to jak nowy wiersz i powstałby duplikat
    repo.zapisz_blankiet(conn, _blok(wiersze=[
        WierszBlankietu(nadawca="Żabka", adres=f"Ulica {i}", ilosc_total=1)
        for i in range(3)
    ]))
    uuidy = [r[0] for r in conn.execute("SELECT uuid FROM transakcje")]
    assert len(uuidy) == 3
    assert all(uuidy) and len(set(uuidy)) == 3


def test_zapisz_blok_dziala_bez_podanego_autora(conn):
    # atrybucja nie może być warunkiem zapisania danych
    wyniki = repo.zapisz_blankiet(conn, _blok())
    assert wyniki[0]["id"] is not None


# --- 0.1-alpha.3.2: współdzielone konta Windows - login rozszerzony ---

def test_login_rozszerzony_laczy_login_bazowy_i_alias():
    assert (uzytkownicy.login_rozszerzony("DOM\\a", "Jan Kowalski")
            == "DOM\\a#Jan Kowalski")


def test_login_rozszerzony_daje_deterministyczny_uuid_miedzy_stacjami():
    # ta sama maszyneria co uuid_uzytkownika zwykłego loginu - kluczowe dla
    # synchronizacji: dwie stacje muszą policzyć TEN SAM id dla tej samej osoby
    login = uzytkownicy.login_rozszerzony("DOM\\a", "Jan Kowalski")
    assert (uzytkownicy.uuid_uzytkownika(login)
            == uzytkownicy.uuid_uzytkownika(login))
    assert uzytkownicy.uuid_uzytkownika(login) != uzytkownicy.uuid_uzytkownika("DOM\\a")


def test_znajdz_konta_dla_loginu_zwraca_baze_i_rozszerzone(conn):
    uzytkownicy.zapewnij_uzytkownika(conn, login="DOM\\a", alias="Konto bazowe")
    uzytkownicy.zapewnij_uzytkownika(
        conn, login=uzytkownicy.login_rozszerzony("DOM\\a", "Jan Kowalski"),
        alias="Jan Kowalski")
    uzytkownicy.zapewnij_uzytkownika(
        conn, login=uzytkownicy.login_rozszerzony("DOM\\a", "Anna Nowak"),
        alias="Anna Nowak")

    konta = uzytkownicy.znajdz_konta_dla_loginu(conn, "DOM\\a")

    aliasy = {k["alias"] for k in konta}
    assert aliasy == {"Konto bazowe", "Jan Kowalski", "Anna Nowak"}


def test_znajdz_konta_dla_loginu_nie_zwraca_obcych_kont(conn):
    uzytkownicy.zapewnij_uzytkownika(conn, login="DOM\\a", alias="A")
    uzytkownicy.zapewnij_uzytkownika(conn, login="DOM\\b", alias="B")
    uzytkownicy.zapewnij_uzytkownika(
        conn, login=uzytkownicy.login_rozszerzony("DOM\\b", "C"), alias="C")

    konta = uzytkownicy.znajdz_konta_dla_loginu(conn, "DOM\\a")

    assert {k["alias"] for k in konta} == {"A"}

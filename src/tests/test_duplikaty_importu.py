"""
Znalezione duplikaty jako OSOBNY artefakt importu.

Zgłoszenie Papavera: wiersz odrzucony jako duplikat trafiał do pliku
„do-poprawy", a tam nie ma czego poprawiać — plik-reszta jest do
POPRAWIENIA I PONOWNEGO WCZYTANIA, więc duplikat w nim albo wraca jako
ten sam duplikat, albo zostaje skasowany ręcznie. Jedno i drugie to
strata czasu.

Ale pomiar na realnym sierpniu pokazał, że „duplikat" znaczy tu dwie
bardzo różne rzeczy. Z 30 powtórzonych kluczy (data + kurier + punkt):

* **11 jest identycznych** — kopiuj-wklej, faktycznie nic do decydowania
* **19 RÓŻNI SIĘ** ilością, „w tym ZPO", PNI, wykonawcą albo rejonem

Do tego tylko 8 z 30 sąsiaduje ze sobą; mediana odległości to 4 wiersze,
a maksimum **3431**. Przy arkuszu sklejonym z pracy sześciu osób znaczy
to, że ten sam odbiór wpisały DWIE RÓŻNE OSOBY w dwóch miejscach pliku.

Dlatego ten plik nie jest wykazem „co wyrzuciliśmy", tylko materiałem
do ROZSTRZYGNIĘCIA: pokazuje obie wersje obok siebie i mówi, czym się
różnią. Nazwa „znalezione duplikaty", nie „usunięte" — nie kasujemy
niczego, co należy do użytkownika, tylko zgłaszamy, że w źródle są dwa
zapisy tego samego zdarzenia.
"""
import openpyxl
import pytest

from zpo_tracker import eksport


NAGLOWKI = ["data", "Kurier", "Ilość"]


def _pozycja(numer, dane, istniejace, roznice):
    return {"numer_wiersza": numer, "dane": dane,
            "istniejace": istniejace, "roznice": roznice}


def _wczytaj(sciezka):
    ws = openpyxl.load_workbook(sciezka).active
    return [list(r) for r in ws.iter_rows(values_only=True)]


def test_plik_powstaje_z_obiema_wersjami(tmp_path):
    """Sedno: żeby człowiek mógł rozstrzygnąć, musi WIDZIEĆ obie liczby.
    Wykaz mówiący „odrzucono wiersz 41 jako duplikat" nie pozwala
    stwierdzić, która wersja jest prawdziwa."""
    sciezka = tmp_path / "duplikaty.xlsx"
    eksport.zapisz_duplikaty(sciezka, NAGLOWKI, [
        _pozycja(41, {"data": "2026-08-03", "Kurier": "Kowalski", "Ilość": 4},
                 {"Ilość": 2}, ["Ilość"]),
    ])
    wiersze = _wczytaj(sciezka)
    plaski = " ".join(str(k) for w in wiersze for k in w)
    assert "4" in plaski and "2" in plaski
    assert "Ilość" in plaski


def test_kolumna_mowi_CZYM_sie_roznia(tmp_path):
    """Bez tego człowiek porównuje kilkanaście kolumn wzrokiem, żeby
    znaleźć jedną różniącą się liczbę - przy trzydziestu przypadkach to
    gwarancja przeoczenia."""
    sciezka = tmp_path / "d.xlsx"
    eksport.zapisz_duplikaty(sciezka, NAGLOWKI, [
        _pozycja(41, {"data": "2026-08-03", "Kurier": "Kowalski", "Ilość": 4},
                 {"Ilość": 2}, ["Ilość"]),
    ])
    assert any("Ilość" in str(k) for w in _wczytaj(sciezka) for k in w)


def test_identyczne_powtorzenie_jest_oznaczone_jako_bez_roznic(tmp_path):
    """11 z 30 realnych przypadków to czyste kopie. Muszą dać się
    odróżnić na pierwszy rzut oka od tych, które wymagają decyzji -
    inaczej człowiek przegląda trzydzieści wierszy zamiast dziewiętnastu."""
    sciezka = tmp_path / "d.xlsx"
    eksport.zapisz_duplikaty(sciezka, NAGLOWKI, [
        _pozycja(41, {"data": "2026-08-03", "Kurier": "Kowalski", "Ilość": 4},
                 {"Ilość": 4}, []),
    ])
    plaski = " ".join(str(k) for w in _wczytaj(sciezka) for k in w)
    assert eksport.OPIS_BEZ_ROZNIC in plaski


def test_pusta_lista_NIE_tworzy_pliku(tmp_path):
    """Inaczej niż wykaz odrzuconych, który powstaje zawsze. Tam pusty
    plik znaczy „sprawdziłem, nic nie odrzucono"; tutaj plik oznacza
    „masz coś do zrobienia", więc pusty byłby fałszywym alarmem."""
    sciezka = tmp_path / "d.xlsx"
    assert eksport.zapisz_duplikaty(sciezka, NAGLOWKI, []) == 0
    assert not sciezka.exists()


def test_numer_wiersza_prowadzi_do_zrodla(tmp_path):
    """Bez numeru wiersza użytkownik nie ma jak znaleźć tego miejsca
    w swoim Excelu - a przy pliku na 5286 wierszy to jedyna droga."""
    sciezka = tmp_path / "d.xlsx"
    eksport.zapisz_duplikaty(sciezka, NAGLOWKI, [
        _pozycja(3431, {"data": "x", "Kurier": "y", "Ilość": 1}, {"Ilość": 2}, ["Ilość"]),
    ])
    assert any("3431" in str(k) for w in _wczytaj(sciezka) for k in w)


# --- orkiestrator: duplikat to NIE jest "wymagające uwagi" ---------------

def _wiersz(adres="Kwiatowa 8", ilosc=5, zpo=None, data="2026-08-03",
            kurier="Kowalski Jan"):
    from zpo_tracker.import_orchestrator import MAPA_NAGLOWKOW
    odw = {p: n for n, p in MAPA_NAGLOWKOW.items()}
    pola = {"data": data, "nadawca": "Sklep", "adres": adres, "kurier": kurier,
            "rejon": None, "ilosc_total": ilosc, "ilosc_zpo": zpo, "pni_zpo": None}
    return {odw[k]: v for k, v in pola.items() if k in odw}


@pytest.fixture
def baza():
    from zpo_tracker import repo
    c = repo.polacz(":memory:")
    repo.utworz_schemat(c)
    yield c
    c.close()


def test_duplikat_nie_trafia_do_wymagajacych_uwagi(baza):
    """Sedno zgłoszenia. Plik „do-poprawy" jest DO PRACY - poprawia się
    go i wczytuje ponownie. Duplikat w nim albo wraca jako ten sam
    duplikat, albo trzeba go ręcznie skasować."""
    from zpo_tracker.import_orchestrator import zaimportuj, zwaliduj_wiersze

    zw, _ = zwaliduj_wiersze([_wiersz(ilosc=5), _wiersz(ilosc=5)])
    wynik = zaimportuj(baza, zw)

    assert wynik["zaimportowano"] == 1
    assert wynik["wymagajace_uwagi"] == []
    assert len(wynik["duplikaty"]) == 1


def test_duplikat_niesie_stan_z_bazy_do_porownania(baza):
    """Bez tego człowiek widzi tylko „odrzucono wiersz 3" i nie ma jak
    stwierdzić, która wersja jest prawdziwa."""
    from zpo_tracker.import_orchestrator import zaimportuj, zwaliduj_wiersze

    zw, _ = zwaliduj_wiersze([_wiersz(ilosc=2), _wiersz(ilosc=4)])
    dup = zaimportuj(baza, zw)["duplikaty"][0]

    assert dup["istniejace"]["ilosc_total"] == 2
    assert dup["wiersz"].ilosc_total == 4
    assert "ilosc_total" in dup["roznice"]


def test_identyczne_powtorzenie_ma_pusta_liste_roznic(baza):
    from zpo_tracker.import_orchestrator import zaimportuj, zwaliduj_wiersze

    zw, _ = zwaliduj_wiersze([_wiersz(ilosc=5), _wiersz(ilosc=5)])
    assert zaimportuj(baza, zw)["duplikaty"][0]["roznice"] == []


def test_roznica_w_polu_zpo_tez_jest_wykrywana(baza):
    """13 z 30 realnych przypadków różni się właśnie tym polem, nie
    ilością całkowitą."""
    from zpo_tracker.import_orchestrator import zaimportuj, zwaliduj_wiersze

    zw, _ = zwaliduj_wiersze([_wiersz(ilosc=5, zpo=1), _wiersz(ilosc=5, zpo=3)])
    assert zaimportuj(baza, zw)["duplikaty"][0]["roznice"] == ["ilosc_zpo"]


# --- przełącznik i zapamiętywanie ustawienia ----------------------------

def test_zapisywanie_duplikatow_jest_domyslnie_wlaczone(tmp_path):
    """Domyślnie WŁĄCZONE, bo cisza jest tu gorsza od nadmiaru: plik
    powstaje tylko wtedy, gdy duplikaty faktycznie są, więc nie zaśmieca
    katalogu, a jego brak przy wyłączonej opcji oznacza po prostu
    niewiedzę o utraconych wierszach."""
    from zpo_tracker import ustawienia
    assert ustawienia.czy_zapisywac_duplikaty(ustawienia.wczytaj(tmp_path)) is True


def test_stan_przelacznika_przezywa_restart(tmp_path):
    """Papaver: „stan zapisywany do konfiguracji". Bez tego odznaczenie
    trzeba powtarzać przy każdym imporcie."""
    from zpo_tracker import ustawienia
    ustawienia.zapisz(tmp_path, {ustawienia.KLUCZ_ZAPISU_DUPLIKATOW: False})
    assert ustawienia.czy_zapisywac_duplikaty(ustawienia.wczytaj(tmp_path)) is False


def test_uszkodzony_wpis_wraca_do_domyslnej(tmp_path):
    from zpo_tracker import ustawienia
    for smiec in ["nie", 0, None, []]:
        assert ustawienia.czy_zapisywac_duplikaty(
            {ustawienia.KLUCZ_ZAPISU_DUPLIKATOW: smiec}) is True

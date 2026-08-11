"""
Migawki bazy: pełna kopia pliku .db, robiona PRZED każdą mutującą operacją
(patrz `operacje.py`), żeby cofnięcie do dowolnego punktu w historii było
zawsze możliwe - schemat-agnostyczne, żadnej wiedzy o `transakcje`/`users`.

Dwie ścieżki kopiowania, bo różnią się gwarancjami:
- `zrob_migawke` - z otwartego połączenia, przez SQLite Backup API. To NIE
  jest kopia pliku: działa poprawnie niezależnie od otwartych transakcji
  i trybu dziennika SQLite, i owszem, działa też ze źródła `:memory:`.
- `zrob_migawke_pliku` - zwykłe kopiowanie pliku, do użycia wyłącznie gdy
  nie ma żywego połączenia (np. `operacje.cofnij`, gdzie wywołujący musiał
  najpierw zamknąć `conn`, żeby bezpiecznie podmienić plik).
"""
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

NAZWA_KATALOGU = "migawki"

# Granice wieku (dni) rotacji migawek: pełna rozdzielczość do 1 dnia, dalej
# malejąca gęstość aż do 1/rok BEZ KOŃCA (nie twardy limit - patrz
# `przytnij_migawki`). To rzeczywisty upływ czasu (datetime), NIE `seq` -
# w odróżnieniu od numeracji operacji w dziennik.py ("nigdy po zegarze"),
# tu chodzi o wiek migawki, nie kolejność zdarzeń.
GRANICE_RETENCJI_DNI = [1, 3, 7, 14, 30, 90, 182, 365]


def katalog_migawek(katalog_danych):
    katalog = Path(katalog_danych) / NAZWA_KATALOGU
    katalog.mkdir(parents=True, exist_ok=True)
    return katalog


def _nazwa_pliku(seq):
    return f"{seq:06d}.db"


def zrob_migawke(conn, katalog_danych, seq):
    """Migawka aktualnego stanu z otwartego połączenia `conn`."""
    docelowa = katalog_migawek(katalog_danych) / _nazwa_pliku(seq)
    kopia = sqlite3.connect(str(docelowa))
    try:
        conn.backup(kopia)
    finally:
        kopia.close()
    return docelowa


def zrob_migawke_pliku(sciezka_bazy, katalog_danych, seq):
    """Migawka przez kopiowanie pliku - tylko gdy `conn` jest zamknięte."""
    docelowa = katalog_migawek(katalog_danych) / _nazwa_pliku(seq)
    shutil.copy2(sciezka_bazy, docelowa)
    return docelowa


def lista_migawek(katalog_danych):
    """Ścieżki do migawek, posortowane rosnąco po numerze seq w nazwie."""
    return sorted(katalog_migawek(katalog_danych).glob("*.db"))


def przywroc_migawke(sciezka_bazy, plik_migawki):
    """
    Podmienia plik bazy na wskazaną migawkę. Wymaga zamkniętego połączenia
    z bazą docelową - podmiana pliku pod otwartym uchwytem jest niebezpieczna
    (na Windows w ogóle niedozwolona). Zamknięcie/otwarcie `conn` należy do
    wywołującego (`operacje.cofnij`).
    """
    plik_migawki = Path(plik_migawki)
    if not plik_migawki.exists():
        raise FileNotFoundError(f"Migawka nie istnieje: {plik_migawki}")
    shutil.copy2(plik_migawki, sciezka_bazy)


def przytnij_migawki(katalog_danych, wpisy_dziennika, teraz=None):
    """
    Usuwa nadmiarowe migawki wg rotacji: pełna rozdzielczość do 1 dnia,
    dalej 1 na kubełek malejącej gęstości (dzień/3dni/tydzień/2tyg/
    miesiąc/3mc/pół roku/rok), po roku 1/rok bez końca - inaczej katalog
    `migawki/` rośnie bez ograniczeń (pełna kopia bazy PRZED każdą
    operacją, patrz operacje.py).

    W każdym kubełku zostaje TYLKO NAJNOWSZA migawka (najmniejszy wiek) -
    najbliższa "teraz" przy danej rozdzielczości. Bezstanowe i idempotentne:
    każde wywołanie liczy kubełki od nowa na podstawie `teraz`, więc migawka
    naturalnie "awansuje" do rzadszej rozdzielczości w miarę starzenia się,
    bez potrzeby pamiętania czegokolwiek między uruchomieniami.

    `wpisy_dziennika`: lista wpisów z `dziennik.wczytaj_operacje` (jawnie
    przekazywana, nie czytana z dysku tutaj - łatwa testowalność bez
    fikstur plikowych dziennika). Usuwa WYŁĄCZNIE pliki migawek - wpisy
    w dzienniku JSONL zostają (append-only, patrz dziennik.py); próba
    cofnięcia do przyciętej operacji kończy się czytelnym błędem
    w `operacje.cofnij`.
    """
    teraz = teraz or datetime.now()

    zachowaj_nazwy = set()
    kubelki = {}
    for wpis in wpisy_dziennika:
        czas, plik = wpis.get("czas"), wpis.get("plik_migawki")
        if not czas or not plik:
            continue
        czas = datetime.fromisoformat(czas)
        wiek_dni = (teraz - czas).total_seconds() / 86400
        nazwa = Path(plik).name

        if wiek_dni < GRANICE_RETENCJI_DNI[0]:
            zachowaj_nazwy.add(nazwa)
            continue

        rozdzielczosc = GRANICE_RETENCJI_DNI[0]
        for granica in GRANICE_RETENCJI_DNI:
            if wiek_dni >= granica:
                rozdzielczosc = granica
        klucz_kubelka = (rozdzielczosc, int(wiek_dni // rozdzielczosc))
        obecny = kubelki.get(klucz_kubelka)
        if obecny is None or czas > obecny[0]:
            kubelki[klucz_kubelka] = (czas, nazwa)

    zachowaj_nazwy |= {nazwa for _, nazwa in kubelki.values()}

    for plik in lista_migawek(katalog_danych):
        if plik.name not in zachowaj_nazwy:
            plik.unlink(missing_ok=True)

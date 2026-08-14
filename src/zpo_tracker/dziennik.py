"""
Diagnostyka: log tekstowy + JSONL dziennik operacji.

Dwa osobne strumienie, bo służą do czego innego:

- **log tekstowy** (`zpo.log`) - kanał wsparcia. Czytelny dla człowieka,
  zawiera tracebacki. Może zawierać dane z komunikatów wyjątków (np.
  pydantic wypisuje wartość, która nie przeszła walidacji), więc zostaje
  na maszynie użytkownika i nie jest nigdzie wysyłany automatycznie.
- **dziennik JSONL** (`operacje.jsonl`) - indeks operacji: co się stało,
  kiedy, ile wierszy, która migawka. Kształt wpisu jest **zamknięty**
  (`POLA_WPISU`) właśnie dlatego, że ten plik jest kandydatem do
  wyniesienia na zewnątrz - żadnych nazwisk kurierów ani adresów.

Dlaczego oba żyją POZA bazą: mają przetrwać uszkodzenie bazy i jej
podmianę przy cofaniu operacji. Tabela audytowa w środku bazy nie umie
zapisać własnego przywrócenia.

Pułapki buildu okienkowego (`console=False` w `zpo_tracker.spec`), których
pilnują testy:
- `sys.stderr is None`, więc `logging.basicConfig()` (domyślnie zakładający
  `StreamHandler` na stderr) zamienia logowanie w źródło awarii,
- `sys.excepthook` NIE łapie wyjątków z callbacków Tk - do tego służy
  `Tk.report_callback_exception`, podpinane osobno.
"""
import json
import logging
import logging.handlers
import sys
import traceback
from pathlib import Path

NAZWA_LOGU = "zpo.log"
NAZWA_DZIENNIKA = "operacje.jsonl"
NAZWA_AWARII = "awaria.log"

# Zamknięty zestaw pól wpisu - patrz docstring modułu. `liczba_pominietych`
# (0.1-alpha.3.2): licznik, nie narusza kontraktu no-PII - bez niego zapis
# wszystkich-duplikatów formularza (zakladka_wprowadzanie.py) wyglądał w
# dzienniku identycznie jak pełny sukces ("N wierszy, wynik=ok").
POLA_WPISU = ("seq", "czas", "rodzaj", "etykieta", "liczba_wierszy",
              "liczba_pominietych", "wersja_schematu", "plik_migawki", "wynik")

_NAZWA_LOGGERA = "zpo_tracker"
_MAX_BAJTOW = 1_000_000
_ILE_KOPII = 3


def skonfiguruj(katalog, poziom=logging.INFO):
    """
    Konfiguruje logger projektu na jawnych handlerach. Idempotentne -
    powtórne wywołanie nie dubluje handlerów (dwa uchwyty na ten sam plik
    psują rotację na Windows).
    """
    katalog = Path(katalog)
    katalog.mkdir(parents=True, exist_ok=True)

    # awaria samego logowania nie może wypłynąć jako wyjątek do UI
    logging.raiseExceptions = False

    log = logging.getLogger(_NAZWA_LOGGERA)
    log.setLevel(poziom)
    # bez propagacji do roota - root może mieć StreamHandler na sys.stderr
    # (który w buildzie okienkowym jest None)
    log.propagate = False

    sciezka = katalog / NAZWA_LOGU
    if any(getattr(h, "_zpo_sciezka", None) == str(sciezka)
           for h in log.handlers):
        return log  # już skonfigurowane na ten katalog

    # logger jest singletonem na proces, więc handlery trzeba ZASTĄPIĆ,
    # nie dokładać - inaczej po zmianie katalogu wpisy lecą do obu naraz
    # (i log wycieka tam, gdzie już nie powinien)
    odepnij()

    handler = logging.handlers.RotatingFileHandler(
        sciezka, maxBytes=_MAX_BAJTOW, backupCount=_ILE_KOPII,
        encoding="utf-8",
        # delay=True: nie otwieraj pliku, dopóki nie ma co zapisać -
        # mniejsze okno na kolizję z antywirusem przy starcie
        delay=True,
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-8s %(message)s"))
    handler._zpo_sciezka = str(sciezka)
    log.addHandler(handler)

    return log


def odepnij():
    """Zdejmuje handlery - potrzebne w testach, żeby nie trzymać plików."""
    log = logging.getLogger(_NAZWA_LOGGERA)
    for h in list(log.handlers):
        log.removeHandler(h)
        h.close()


def zainstaluj_haki(app=None, katalog=None):
    """
    Podpina przechwytywanie awarii. `app` to okno Tk (opcjonalne) -
    `sys.excepthook` sam nie wystarcza, bo Tk łapie wyjątki z callbacków
    i kieruje je do `report_callback_exception`, nie do excepthooka.
    """
    log = logging.getLogger(_NAZWA_LOGGERA)

    def _zapisz(typ, wartosc, tb, zrodlo):
        log.error("Nieobsłużony wyjątek (%s):\n%s", zrodlo,
                  "".join(traceback.format_exception(typ, wartosc, tb)))

    def _excepthook(typ, wartosc, tb):
        _zapisz(typ, wartosc, tb, "excepthook")

    sys.excepthook = _excepthook

    if app is not None:
        def _tk(typ, wartosc, tb):
            # świadomie NIE podnosimy dalej - awaria jednego callbacku nie
            # może ubić całej aplikacji
            _zapisz(typ, wartosc, tb, "callback Tk")
        app.report_callback_exception = _tk

    if katalog is not None:
        _wlacz_faulthandler(Path(katalog) / NAZWA_AWARII)

    return log


def _wlacz_faulthandler(sciezka):
    """
    Twarde awarie (SIGSEGV/SIGABRT) nie przechodzą przez Pythonowe haki -
    na tej maszynie wystąpiła już awaria klasy SIGABRT w tkinterze
    (docs/environment.md), a na Windows taka awaria jest bez tego zupełnie
    niewidoczna.
    """
    import faulthandler
    try:
        sciezka.parent.mkdir(parents=True, exist_ok=True)
        faulthandler.enable(file=open(sciezka, "a", encoding="utf-8"))
    except (OSError, ValueError):
        pass  # brak faulthandlera nie może blokować startu aplikacji


# --- dziennik operacji (JSONL) ---

def zapisz_operacje(katalog, *, seq, rodzaj, etykieta, liczba_wierszy=None,
                    liczba_pominietych=None, wersja_schematu=None,
                    plik_migawki=None, wynik="ok", czas=None):
    """
    Dopisuje jeden wpis do dziennika. Parametry są **nazwane i jawne**, nie
    `**kwargs` - dzięki temu strukturalnie nie da się wpisać tu nazwiska
    ani adresu (patrz docstring modułu).
    """
    katalog = Path(katalog)
    katalog.mkdir(parents=True, exist_ok=True)
    wpis = {
        "seq": seq,
        "czas": czas,
        "rodzaj": rodzaj,
        "etykieta": etykieta,
        "liczba_wierszy": liczba_wierszy,
        "liczba_pominietych": liczba_pominietych,
        "wersja_schematu": wersja_schematu,
        "plik_migawki": plik_migawki,
        "wynik": wynik,
    }
    with open(katalog / NAZWA_DZIENNIKA, "a", encoding="utf-8") as f:
        f.write(json.dumps(wpis, ensure_ascii=False) + "\n")
    return wpis


def wczytaj_operacje(katalog):
    """
    Wpisy posortowane po `seq`. Linie nieparsowalne są pomijane - zapis
    przerwany awarią zostawia urwaną linię, co nie może uczynić całego
    dziennika bezużytecznym.
    """
    sciezka = Path(katalog) / NAZWA_DZIENNIKA
    if not sciezka.exists():
        return []
    wpisy = []
    for linia in sciezka.read_text(encoding="utf-8").splitlines():
        linia = linia.strip()
        if not linia:
            continue
        try:
            wpisy.append(json.loads(linia))
        except json.JSONDecodeError:
            continue
    return sorted(wpisy, key=lambda w: w.get("seq") or 0)


def nastepny_seq(katalog):
    """
    Kolejny numer operacji. Numeracja jawna, NIE po zegarze - w Polsce
    godzina 02:00-03:00 powtarza się raz w roku, a zegary firmowych maszyn
    bywają rozjechane.
    """
    wpisy = wczytaj_operacje(katalog)
    return max((w.get("seq") or 0) for w in wpisy) + 1 if wpisy else 1

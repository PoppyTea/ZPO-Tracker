"""
Ustawienia per-stacja: plik `settings.json` w katalogu danych (0.1-alpha.3.2).

Celowo POZA bazą, nie tabela: ustawienia typu "odsłoń przełącznik
zaawansowany" (np. wymuszenie zaufania importu) muszą być lokalne dla
KONKRETNEJ stacji i NIE podlegać scalaniu/synchronizacji między stacjami
(patrz scalanie.py, docs/roadmap.md) - scalenie dwóch baz nie ma prawa
przenieść czyichś ustawień na inną maszynę.
"""
import json
import os
from pathlib import Path

NAZWA_PLIKU = "settings.json"


def _sciezka(katalog_danych):
    return Path(katalog_danych) / NAZWA_PLIKU


def wczytaj(katalog_danych):
    """
    Zwraca dict ustawień. Brak pliku, uszkodzony JSON albo zawartość, która
    nie jest obiektem - zawsze puste {}, NIGDY wyjątek: ustawienia nie mogą
    zablokować startu aplikacji.
    """
    try:
        with open(_sciezka(katalog_danych), encoding="utf-8") as f:
            dane = json.load(f)
    # ValueError pokrywa też UnicodeDecodeError (dziedziczy z ValueError, nie
    # z OSError) - plik w innym kodowaniu nie może zablokować startu
    except (OSError, ValueError):
        return {}
    return dane if isinstance(dane, dict) else {}


def zapisz(katalog_danych, dane):
    """
    Zapisuje CAŁY dict atomowo: plik tymczasowy w tym samym katalogu +
    `os.replace` - awaria w trakcie zapisu nie może zostawić settings.json
    w stanie połowicznym/uszkodzonym. Woła się z pełnym dictem
    (read-modify-write po stronie wołającego, patrz `wczytaj`), więc klucze
    nieznane tej wersji aplikacji przeżywają zapis bez zmian.
    """
    katalog_danych = Path(katalog_danych)
    katalog_danych.mkdir(parents=True, exist_ok=True)
    docelowa = _sciezka(katalog_danych)
    tymczasowa = docelowa.with_name(docelowa.name + ".tmp")
    with open(tymczasowa, "w", encoding="utf-8") as f:
        json.dump(dane, f, ensure_ascii=False, indent=2)
    os.replace(tymczasowa, docelowa)


# Tryb testowy. Domyślnie WŁĄCZONY, bo program jest dziś wydawany
# wyłącznie do testów i nikt nie trzyma w nim danych roboczych (patrz
# akapit "not deployed yet" w root CLAUDE.md). Dopóki to prawda, tryb
# testowy jest stanem NORMALNYM, a nie wyjątkiem do włączania.
#
# Domyślność ma zniknąć razem z tamtym akapitem - stąd jawna stała,
# a nie `True` zaszyte w kilku miejscach, których potem nie sposób
# odnaleźć.
TRYB_TESTOWY_DOMYSLNIE = True

KLUCZ_TRYBU_TESTOWEGO = "tryb_testowy"


def czy_tryb_testowy(dane_ustawien=None) -> bool:
    """
    Czy program działa w trybie testowym.

    Dziś wyłącza jedno: pytanie o dane użytkownika przy starcie, bo
    proces logowania jest wstrzymany i okna nie da się sensownie
    wypełnić.

    NIGDY nie rzuca - jak `wczytaj`. Wartość spoza `true`/`false`
    (literówka w ręcznie edytowanym pliku) wraca do domyślnej, zamiast
    blokować uruchomienie programu osobie bez konsoli i bez uprawnień
    administratora.
    """
    wartosc = (dane_ustawien or {}).get(KLUCZ_TRYBU_TESTOWEGO)
    if isinstance(wartosc, bool):
        return wartosc
    return TRYB_TESTOWY_DOMYSLNIE

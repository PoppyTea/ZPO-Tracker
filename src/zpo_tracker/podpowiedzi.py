"""
Silnik podpowiedzi: uszeregowane trafienia dla prefiksu z listy kandydatów.
Źródło danych jest wstrzykiwane (docs/ux-ui.md: architektura ma od razu
uwzględniać wymienne źródło, np. dane referencyjne zewnętrzne później) -
ten moduł dostaje gotową listę stringów, nie sięga do bazy sam.

Szeregowanie: dopasowanie od początku prefiksu przed dopasowaniem w
środku, dalej częstość użycia, dalej "ostatnio używane" jako
rozstrzygacz remisu. Porównanie na klucz_rozmyty (bez diakrytyków/
wielkości liter), żeby "zabka" trafiało w "Żabka".
"""
from zpo_tracker.normalizacja import klucz_rozmyty


def podpowiedz(prefiks, kandydaci, uzycia=None, ostatnio_uzywane=None, limit=8):
    if not prefiks:
        return []

    klucz_prefiksu = klucz_rozmyty(prefiks)
    uzycia = uzycia or {}
    ostatnio_uzywane = ostatnio_uzywane or []

    wyniki = []
    for kandydat in kandydaci:
        klucz_kandydata = klucz_rozmyty(kandydat)
        if klucz_kandydata.startswith(klucz_prefiksu):
            priorytet = 0
        elif klucz_prefiksu in klucz_kandydata:
            priorytet = 1
        else:
            continue

        pozycja_ostatnio = (
            ostatnio_uzywane.index(kandydat)
            if kandydat in ostatnio_uzywane
            else len(ostatnio_uzywane)
        )
        wyniki.append((priorytet, -uzycia.get(kandydat, 0), pozycja_ostatnio, kandydat))

    wyniki.sort()
    return [w[-1] for w in wyniki[:limit]]


def najlepsza_podpowiedz(prefiks, kandydaci, uzycia=None, ostatnio_uzywane=None):
    """Pierwszy wynik podpowiedz() - to, co widget pokazuje jako ghost text."""
    wyniki = podpowiedz(prefiks, kandydaci, uzycia, ostatnio_uzywane, limit=1)
    return wyniki[0] if wyniki else None

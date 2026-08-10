"""
Wyróżnianie różnic między dwoma podobnymi stringami - do ekranu korekty
importu (GH #2), sekcja ostrzeżeń o podobieństwie (diakrytyki/wielkość
liter). Czysta logika: zwraca segmenty do pokolorowania w tk.Text, nie
rysuje niczego samo, więc testowalne bez display.
"""
import difflib

SYMBOL_SPACJI = "·"


def segmenty_roznicy(a, b):
    """
    Zwraca (segmenty_a, segmenty_b), każdy jako lista (tekst, czy_rozni_sie).
    Białe znaki w RÓŻNIĄCYM SIĘ segmencie są zamieniane na SYMBOL_SPACJI,
    żeby różnica w samych spacjach była w ogóle widoczna (inaczej dwie
    spacje wyglądają identycznie na ekranie).
    """
    matcher = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    segmenty_a, segmenty_b = [], []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        fragment_a, fragment_b = a[i1:i2], b[j1:j2]
        rozni_sie = tag != "equal"
        if rozni_sie:
            fragment_a = fragment_a.replace(" ", SYMBOL_SPACJI)
            fragment_b = fragment_b.replace(" ", SYMBOL_SPACJI)
        if fragment_a:
            segmenty_a.append((fragment_a, rozni_sie))
        if fragment_b:
            segmenty_b.append((fragment_b, rozni_sie))
    return segmenty_a, segmenty_b

"""
Wyróżnianie różnic między podobnymi stringami (GH #2: formatowanie
konfliktów). Czysta logika, zero GUI - zwraca segmenty do pokolorowania,
nie rysuje niczego. TDD.
"""
from zpo_tracker.gui.roznice import segmenty_roznicy, SYMBOL_SPACJI


def test_identyczne_stringi_zaden_segment_nie_rozni_sie():
    seg_a, seg_b = segmenty_roznicy("Kowalski Jan", "Kowalski Jan")
    assert all(not rozni for _, rozni in seg_a)
    assert all(not rozni for _, rozni in seg_b)


def test_pojedyncza_litera_rozni_sie_wyodrebniona():
    # "Wołczuk Rafał" / "Wołczuk Rafal" - realny przypadek z domain-model.md
    seg_a, seg_b = segmenty_roznicy("Wołczuk Rafał", "Wołczuk Rafal")
    rozniace_a = [t for t, rozni in seg_a if rozni]
    rozniace_b = [t for t, rozni in seg_b if rozni]
    assert rozniace_a == ["ł"]
    assert rozniace_b == ["l"]
    # reszta wspólna i NIE oznaczona jako różnica
    wspolne_a = [t for t, rozni in seg_a if not rozni]
    assert "".join(wspolne_a) == "Wołczuk Rafa"


def test_roznica_w_bialych_znakach_dostaje_widoczny_symbol():
    seg_a, seg_b = segmenty_roznicy("Michalak Maciej", "Michalak Maciej ")
    rozniace_b = [t for t, rozni in seg_b if rozni]
    assert rozniace_b == [SYMBOL_SPACJI]


def test_segmenty_skladaja_sie_z_powrotem_do_oryginalu_bez_bialych_znakow():
    # sklejenie segmentów (poza podmiana spacji na symbol) odtwarza string
    a, b = "Kowalksi Jan", "Kowalski Jan"
    seg_a, seg_b = segmenty_roznicy(a, b)
    assert "".join(t for t, _ in seg_a) == a
    assert "".join(t for t, _ in seg_b) == b

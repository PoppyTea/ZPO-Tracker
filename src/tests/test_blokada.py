"""
Blokada jednej instancji na katalog danych - blokada pliku na poziomie
systemu operacyjnego (fcntl/msvcrt), nie sam PID w pliku: PID martwego
procesu bywa ponownie przydzielony innemu, żywemu procesowi, więc obecność
pliku z PID-em sama w sobie niczego nie gwarantuje. TDD.
"""
import pytest

from zpo_tracker import blokada


def test_zdobycie_wolnej_blokady_zwraca_true(tmp_path):
    b = blokada.Blokada(tmp_path)
    try:
        assert b.zdobadz() is True
    finally:
        b.zwolnij()


def test_druga_blokada_na_ten_sam_katalog_nie_udaje_sie(tmp_path):
    pierwsza = blokada.Blokada(tmp_path)
    druga = blokada.Blokada(tmp_path)
    try:
        assert pierwsza.zdobadz() is True
        assert druga.zdobadz() is False
    finally:
        pierwsza.zwolnij()
        druga.zwolnij()


def test_po_zwolnieniu_mozna_zdobyc_ponownie(tmp_path):
    pierwsza = blokada.Blokada(tmp_path)
    pierwsza.zdobadz()
    pierwsza.zwolnij()

    druga = blokada.Blokada(tmp_path)
    try:
        assert druga.zdobadz() is True
    finally:
        druga.zwolnij()


def test_dwa_rozne_katalogi_nie_koliduja(tmp_path):
    a = blokada.Blokada(tmp_path / "a")
    b = blokada.Blokada(tmp_path / "b")
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    try:
        assert a.zdobadz() is True
        assert b.zdobadz() is True
    finally:
        a.zwolnij()
        b.zwolnij()


def test_zwolnienie_bez_zdobycia_nie_wybucha(tmp_path):
    b = blokada.Blokada(tmp_path)
    b.zwolnij()  # nie wywołane zdobadz() - nie może rzucić


def test_dziala_jako_context_manager(tmp_path):
    with blokada.Blokada(tmp_path) as zdobyta:
        assert zdobyta is True
    # po wyjściu z bloku blokada zwolniona - inna instancja może ją zdobyć
    druga = blokada.Blokada(tmp_path)
    try:
        assert druga.zdobadz() is True
    finally:
        druga.zwolnij()


def test_context_manager_gdy_zajeta_daje_false(tmp_path):
    trzymajaca = blokada.Blokada(tmp_path)
    trzymajaca.zdobadz()
    try:
        with blokada.Blokada(tmp_path) as zdobyta:
            assert zdobyta is False
    finally:
        trzymajaca.zwolnij()

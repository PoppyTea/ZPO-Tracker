# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller - pojedynczy, niepodpisany .exe (docs/environment.md).

WAŻNE: PyInstaller nie kompiluje skrośnie - budowa .exe musi się odbyć
NA Windowsie, nie na tej maszynie deweloperskiej (Debian). Uruchamianie
tego spec pliku na Linuksie produkuje binarkę ELF, użyteczną tylko jako
"proxy build" sprawdzający, że wszystkie zależności (w tym natywnie
kompilowany pydantic-core) w ogóle się pakują - nie jako finalny artefakt.

Budowa (z katalogu repo root, w środowisku z zainstalowanym `uv sync
--extra build`):
    uv run pyinstaller zpo_tracker.spec
Wynik: dist/zpo-tracker(.exe)
"""

a = Analysis(
    ['src/zpo_tracker/gui/app.py'],
    pathex=['src'],
    datas=[('schema.sql', '.')],
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='zpo-tracker',
    console=False,
)

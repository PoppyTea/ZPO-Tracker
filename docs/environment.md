# Środowisko: produkcyjne vs deweloperskie

Referencja dla `CLAUDE.md`.

## Środowisko produkcyjne (docelowe, IRL) — twarde ograniczenia

- Windows 11 Pro, konta bez uprawnień administratora
- Internet efektywnie zablokowany, poza whitelistowanym ruchem Microsoft 365
  (stąd OneDrive/SharePoint działają, ale nic poza tym)
- **Wyjątek: `github.com` jest częściowo dostępny** — warto to wykorzystać.
  Czy obejmuje to pobieranie artefaktów z Releases, jest niesprawdzone
  i bramkuje strategię aktualizacji (→ AID-107)
- VBA zablokowane (teoretycznie odblokowywalne przez IT, ale proces
  uzyskiwania pozwoleń w firmie jest na tyle kulawy, że wolimy tego unikać)
- Power Apps: zablokowany dostęp do wymaganych adresów proxy
- Lokalnie zainstalowany pakiet biurowy to OpenOffice/Calc, NIE Excel — mimo
  że docelowy plik to `.xlsx` na firmowym OneDrive w Excelu 365
- Niepodpisane pliki `.exe` **działają bez problemu** (potwierdzone; nawet
  wewnętrzne oprogramowanie finansowe Poczty odpalane jest przez niepodpisany
  launcher)
- Odbiorcy: patrz `ux-ui.md`, sekcja "idioto-odporność" — to więcej niż
  zwykła "nietechniczność"

## Środowisko deweloperskie (Papavera)

- Debian 13 (Trixie), ZSH + oh-my-zsh
- Python: **pip + venv jest teraz domyślną, udokumentowaną ścieżką**
  (`requirements.txt`/`requirements-dev.txt`/`requirements-build.txt`,
  wersje odzwierciedlają `uv.lock`) - dopasowane do tego, co realnie jest
  dostępne na Windowsie w pracy. `uv`/`uvx`/`pipx` wciąż dostępne i
  działają na tej maszynie, ale jako alternatywa, nie ścieżka główna.
- IDE: Zed (programowanie), Sublime Text (dokumenty)
- Notatki: Obsidian
- Agenci AI: Claude Code, Gemini CLI
- Drugie miejsce pracy: Windows w biurze, bez uprawnień administratora,
  bez `git` zainstalowanego domyślnie — patrz "Portable Git" niżej.

## Znany problem: `uv`-owy Python ma zepsuty tkinter na tej maszynie

Odkryte 2026-08-10 po długiej sesji debugowania fałszywego tropu (podejrzenie
padło najpierw na wygaszanie ekranu/DPMS monitora — **niesłusznie**,
wykluczone eksperymentalnie: `xdpyinfo`/`xset` działają normalnie nawet z
monitorem w stanie DPMS "Off", a błąd występuje identycznie na całkiem
świeżym, headless `Xvfb`, gdzie fizycznego monitora/DPMS w ogóle nie ma).

**Objaw:** tworzenie JAKIEGOKOLWIEK widgetu Tk (nawet gołego `tk.Entry`)
przez Pythona zarządzanego przez `uv` (`.venv/bin/python3`,
python-build-standalone) kończy się fatalnym `SIGABRT`:
`[xcb] Unknown sequence number... Assertion '!xcb_xlib_unknown_seq_number' failed`.

**Zdiagnozowane przez `strace`:** proces `uv`-owego Pythona pada, ZANIM w
ogóle otworzy `libtcl8.6.so`/`libtk8.6.so` — czyli awaria dzieje się na
etapie wcześniejszym niż ładowanie Tcl/Tk, mimo że oba interpretery
(`uv`-owy i systemowy) docelowo linkują się z TYMI SAMYMI systemowymi
`libX11.so.6`/`libxcb.so.1` (zweryfikowane przez `strace`). Systemowy
Python (`python3 -m venv`, Debian, aktualnie 3.13) tworzy identyczne
widgety bez żadnego problemu, tymi samymi bibliotekami systemowymi.

**Wniosek:** to nie kod projektu, nie monitor, nie sesja X11 jako taka -
to coś specyficznego dla konkretnej binarki Pythona z dystrybucji
python-build-standalone, której używa `uv` na tej maszynie, w interakcji
z inicjalizacją X11/XCB. **Obejście: używać systemowego Pythona (przez
`venv`+`pip`, patrz wyżej) do wszystkiego, co dotyka `tkinter`/GUI na tej
maszynie** — co i tak jest teraz domyślną ścieżką z innego powodu (dopasowanie
do Windowsa w pracy). `src/tests/test_gui_smoke.py` wykrywa to automatycznie
(sondowanie w osobnym podprocesie) i pomija się czysto zamiast ubijać cały
`pytest`, gdy trafi na tę konkretną binarkę Pythona.

**Naprawione 2026-08-11:** `.venv/` był wcześniej przez pomyłkę zbudowany
przez `uv` (`pyvenv.cfg` wskazywał na
`~/.local/share/uv/python/cpython-3.11.13-...`), a NIE przez systemowego
Pythona, mimo że ten drugi jest udokumentowaną ścieżką domyślną. Skutek:
pod tamtym `.venv/` testy GUI pomijały się. Przebudowany systemowym
Pythonem (`/usr/bin/python3 -m venv .venv`) — pełny zestaw (175 testów)
przechodzi teraz bez pominięć pod zwykłym `.venv/`. Osobny `.venv-sys/`
nie jest już potrzebny i został usunięty; polecenia z `CLAUDE.md`
(`python -m venv .venv && pip install ...`) wystarczają same w sobie,
pod warunkiem że `python3` w `PATH` wskazuje na systemowego Pythona, nie
na `uv`/`pyenv`/inny menedżer — warto to sprawdzić (`which python3`)
przy zakładaniu środowiska od zera na tej maszynie.

Nie zbadane do końca: dlaczego akurat binarka `uv`-owego Pythona
(python-build-standalone, `cpython-3.11.13-linux-x86_64-gnu`) tak się
zachowuje. Do sprawdzenia kiedyś, gdyby się powtórzyło na innej maszynie:
czy to znana usterka konkretnej wersji python-build-standalone, czy coś
specyficznego dla tego systemu (np. rozjazd wersji `libxcb`/`libtk8.6`
między momentem zbudowania tej dystrybucji Pythona a obecnym stanem
pakietów systemowych).

## Portable Git (Windows w biurze, bez admina)

Oficjalny "Git for Windows" ma wariant bez instalatora:
`https://github.com/git-for-windows/git/releases/latest` → szukać pliku
`PortableGit-<wersja>-64-bit.7z.exe` (pełny, z Git Bash) albo
`MinGit-<wersja>-64-bit.zip` (minimalny, sam `git.exe`, bez powłoki) —
oba to samorozpakowujące się archiwa, zero instalacji, zero uprawnień
administratora, rozpakuj i dodaj do PATH użytkownika (albo odpalaj
bezpośrednio ze ścieżki).

## Budowa .exe (PyInstaller)

`zpo_tracker.spec` (root repo) jest gotowym plikiem konfiguracyjnym.
**Musi być odpalony NA Windowsie** - PyInstaller nie kompiluje skrośnie,
więc budowa z Debiana produkuje binarkę ELF, nie `.exe`. Na Windowsie:

```
uv sync --extra build
uv run pyinstaller zpo_tracker.spec
```

Wynik: `dist/zpo-tracker.exe`. Budowa z Linuksa ma sens tylko jako
"proxy build" sprawdzający, że natywnie kompilowany `pydantic-core` w
ogóle się pakuje (zweryfikowane - pakuje się bez błędów importu).

## Konsekwencje różnicy dev/prod

- Kod pisany i testowany na Debianie, ale musi działać jako pojedynczy,
  niepodpisany `.exe` (PyInstaller) na Windows 11 bez adminam — testować
  faktyczne uruchomienie na Windowsie przed uznaniem czegoś za gotowe, nie
  polegać wyłącznie na testach z maszyny deweloperskiej
- Żadna zależność wymagająca instalacji/uprawnień administratora w runtime
  nie wchodzi w grę — wszystko musi być spakowane do jednego `.exe` albo
  działać z bibliotek standardowych
- `uv`/`pip` służą tylko do developmentu — produkcyjny `.exe` nie zakłada
  żadnego menedżera pakietów po stronie użytkownika końcowego

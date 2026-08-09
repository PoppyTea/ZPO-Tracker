# Środowisko: produkcyjne vs deweloperskie

Referencja dla `CLAUDE.md`.

## Środowisko produkcyjne (docelowe, IRL) — twarde ograniczenia

- Windows 11 Pro, konta bez uprawnień administratora
- Internet efektywnie zablokowany, poza whitelistowanym ruchem Microsoft 365
  (stąd OneDrive/SharePoint działają, ale nic poza tym)
- **Wyjątek: `github.com` jest częściowo dostępny** — warto to wykorzystać
  (patrz `backlog.md`, sekcja infrastruktura)
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
- Python: uv / uvx / pipx / pip
- IDE: Zed (programowanie), Sublime Text (dokumenty)
- Notatki: Obsidian
- Agenci AI: Claude Code, Gemini CLI

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

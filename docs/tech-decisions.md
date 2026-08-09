# Decyzje techniczne i dlaczego

Referencja dla `CLAUDE.md`.

## Stack

**Python + SQLite + openpyxl + tkinter + PyInstaller.**

`openpyxl` czyta/pisze `.xlsx` bezpośrednio na poziomie formatu pliku, więc
w ogóle nie obchodzi go czy na maszynie jest Excel, Calc, czy nic — kluczowe
w środowisku, gdzie lokalnie jest tylko OpenOffice/Calc.

**Ważne:** źródłem prawdy do parsowania jest zawsze `.xlsx` przez `openpyxl`,
NIE eksport do `.csv` — CSV wprowadza zanieczyszczenie typów (część liczb w
kolumnach ilościowych eksportuje się jako string zamiast liczby).

## Odrzucone alternatywy i powody

- **VBA** — zablokowane w środowisku docelowym, niechęć do proszenia IT
  o odblokowanie (proces uzyskiwania pozwoleń w firmie jest kulawy)
- **VBA UserForm wbudowany w plik** — ten sam problem blokady co wyżej
- **Power Apps / Power Automate (online)** — zablokowany dostęp do
  wymaganych adresów proxy w środowisku docelowym
- **Power Automate Desktop** — dostępny i działa lokalnie, ale automatyzuje
  Excela przez COM, a lokalnie nie ma Excela (tylko OpenOffice) — więc nie
  zadziała niezawodnie

Pełny opis środowiska, w którym te ograniczenia obowiązują: `environment.md`.

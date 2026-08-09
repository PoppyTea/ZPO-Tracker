# Backlog

Referencja dla `CLAUDE.md`. Pogrupowane tematycznie, nie priorytetyzowane
chronologicznie w obrębie grupy.

## Schemat / dane

- [ ] Wdrożenie normalizacji v2 (patrz `normalization-v2.md` i
      `schema_v2_draft.sql`) — wymaga rozstrzygnięcia dwóch otwartych ryzyk
      opisanych tam
- [ ] `kurierzy.identyfikator_zewnetrzny` — zewnętrzny identyfikator (nie
      wewnętrzny `id`), potrzebny przy łączeniu z innymi systemami; już
      dodane do `schema_v2_draft.sql`
- [ ] Normalizacja `nadawcy` (ZUS, PKO, Kruk...) do osobnej tabeli — celowo
      odłożone, patrz `normalization-v2.md`
- [ ] Dołączenie zewnętrznych danych referencyjnych do silnika podpowiedzi
      (patrz `reference-data-sources.md`) — NIE priorytet przed MVP

## UI / UX

- [ ] Silnik podpowiedzi na bazie już wprowadzonych danych — priorytet
      przed MVP (patrz `ux-ui.md`)
- [ ] Formularz wprowadzania danych (tkinter), kurier-first, grupowanie po
      rejonach, zamykanie/dodawanie rejonu jako operacja grupowa
- [ ] Doprecyzowanie mechaniki podpowiedzi (dropdown/filtrowanie/kolejność)
- [ ] Ustalenie dokładnej hierarchii przynależności encji (kurier/rejon/
      wykonawca/punkt) — zaczęte wizualnie w interaktywnym artefakcie,
      przełożone na propozycję w `normalization-v2.md`, do potwierdzenia
- [ ] Eksport do `.xlsx` (nowy arkusz per miesiąc, zgodny z formatem
      docelowym)

## Infrastruktura

- [ ] **Założenie repozytorium na GitHubie** — `github.com` jest jednym
      z niewielu adresów częściowo dostępnych w sieci firmowej mimo
      generalnie zablokowanego internetu (patrz `environment.md`); warto
      to wykorzystać zamiast szukać alternatyw
- [ ] Packaging PyInstaller → pojedynczy, niepodpisany `.exe` (potwierdzone
      że działa w środowisku docelowym)

## Zrobione (dla porządku, nie duplikować)

- [x] `schema.sql` — SQLite v1: kurierzy, rejony, wykonawcy, punkty,
      transakcje
- [x] `src/zpo_tracker/importer.py` + `src/tests/test_importer.py` — TDD,
      przetestowane na realnych danych (1239/4573 wierszy poprawnie
      zaimportowanych, walidacja PNI/adres zadziałała 51 razy, 20 wykrytych
      literalnych duplikatów)
- [x] Prototyp narzędzia do przeglądu kurierów (imię/nazwisko), patrz
      `ux-ui.md`

# Backlog

Referencja dla `CLAUDE.md`. Pogrupowane tematycznie, nie priorytetyzowane
chronologicznie w obrębie grupy.

## Schemat / dane

- [ ] Pełne wdrożenie normalizacji v2 (adresy, kurier→imię/nazwisko) —
      `firmy_zpo` już wdrożone w v1 (patrz Zrobione), reszta wciąż wymaga
      rozstrzygnięcia ryzyka podziału adresów, patrz `normalization-v2.md`
- [ ] `kurierzy.identyfikator_zewnetrzny` — zewnętrzny identyfikator (nie
      wewnętrzny `id`), potrzebny przy łączeniu z innymi systemami; już
      dodane do `schema_v2_draft.sql`, nie do `schema.sql`
- [ ] Normalizacja `nadawcy` (ZUS, PKO, Kruk...) do osobnej tabeli — celowo
      odłożone, patrz `normalization-v2.md`
- [ ] Dołączenie zewnętrznych danych referencyjnych do silnika podpowiedzi
      (patrz `reference-data-sources.md`) — NIE priorytet przed MVP;
      `podpowiedzi.py` ma już wymienne źródło kandydatów, gotowe na to

## UI / UX

- [ ] **Ghost text w polu wpisywania** — `widget_autocomplete.py` ma dziś
      tylko dropdown+klawiaturę, bez nakładki z podpowiedzią przed
      kursorem; nie zaimplementowane z powodu awarii środowiska
      graficznego w trakcie budowy MVP (patrz `../src/AGENTS.md`)
- [ ] **Wpięcie `widget_autocomplete.py` do formularza wprowadzania** —
      widget istnieje, ale nie jest podłączony do żadnego pola i nie
      został odpalony ani razu; zweryfikować pierwsze, gdy display wróci
- [ ] Doprecyzowanie dokładnej hierarchii przynależności encji (kurier/
      rejon/wykonawca/punkt) na wypadek pełnej normalizacji v2

## Infrastruktura

- [ ] **Realna budowa `.exe` na Windowsie** — `zpo_tracker.spec` gotowy,
      proxy-build na Linuksie potwierdził pakowanie `pydantic_core`, ale
      PyInstaller nie kompiluje skrośnie — finalny artefakt wymaga
      uruchomienia na docelowej maszynie, patrz `environment.md`

## Zrobione (dla porządku, nie duplikować)

- [x] `schema.sql` v1 — kurierzy, rejony, wykonawcy, **firmy_zpo**, punkty
      (+ `firma_zpo_id`), transakcje (+ `komentarz` per blok rejonu)
- [x] `src/zpo_tracker/importer.py`, `models.py` (pydantic v2),
      `normalizacja.py`, `repo.py`, `import_orchestrator.py`, `eksport.py`,
      `podpowiedzi.py` — TDD, 89/89 testów, round-trip import→export
      zweryfikowany na realnych danych (1239/4573 wierszy poprawnie
      zaimportowanych, 71 wymagających uwagi: 51 konfliktów PNI/adres +
      20 literalnych duplikatów)
- [x] Aplikacja desktopowa (tkinter): przeglądanie, formularz wprowadzania
      blankietowy (bloki rejonów, komentarz), import z ekranem korekty,
      export z wyborem miesiąca, zakładka słowników — zweryfikowane
      wizualnie do zakładki przeglądania (krok 5), dalej tylko wzorcem
      kodu i testami logiki z powodu awarii środowiska graficznego
- [x] Prototyp narzędzia do przeglądu kurierów (imię/nazwisko), patrz
      `ux-ui.md`
- [x] Publiczne repozytorium GitHub (`github.com/PoppyTea/ZPO-Tracker`)

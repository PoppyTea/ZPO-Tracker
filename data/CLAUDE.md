# data

## Purpose

Lokalny schowek na realne eksporty `.xlsx`/`.csv` do ręcznej pracy i
testowania importu — nie część kodu, nie część historii repo.

## Ownership

Jak w całym projekcie — patrz root `CLAUDE.md`.

## Local Contracts

- Cały katalog jest w `.gitignore` poza `README.md` (wzorzec `data/*` +
  `!data/README.md`, celowo rekurencyjny — łapie też podkatalogi typu
  `real-data-samples/`). Zobacz `README.md` w tym katalogu dla notatki dla
  człowieka.
- Dane tu wklejane to realne dane firmowe (nazwiska kurierów, adresy,
  ilości przesyłek) — repozytorium docelowo trafia na **publiczny**
  GitHub, więc nic z tego katalogu (poza `README.md`) nigdy nie może
  zostać dodane do gita.

## Work Guidance

- Nie rozluźniać wzorca `.gitignore` dla tego katalogu bez bardzo
  świadomej decyzji — konsekwencją byłby wyciek realnych danych osobowych
  i biznesowych do publicznego repo.
- Nie cytować realnej zawartości (nazwisk, adresów, PNI) w commitach,
  dokumentacji czy komentarzach kodu gdziekolwiek w repo — ustalenia z
  analizy danych trzymamy w `../docs/domain-model.md` w formie
  zanonimizowanej/opisowej, nie jako surowe cytaty.

## Verification

Brak.

## Child DOX Index

Brak.

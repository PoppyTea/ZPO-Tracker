# data

Lokalny schowek na realne eksporty `.xlsx`/`.xls`/`.csv` do ręcznej pracy
i testowania importu. Nie jest częścią kodu ani historii repo.

## Local Contracts

1. Wszystko tutaj poza `README.md`, `CLAUDE.md` i `AGENTS.md` to realne
   dane firmowe (nazwiska kurierów, adresy, ilości) i **nigdy nie trafia do
   gita**. Repo jest publiczne.
2. Wzorzec `.gitignore` `data/*` z wyjątkami tylko dla tych trzech plików
   jest celowo rekurencyjny. Nie rozluźniać go bez świadomej decyzji Papavera.
3. Surowe eksporty z BaŚKi mają drugą, niezależną osłonę: wzorce po nazwie
   pliku w `.gitignore` (`**/Odbiór w punkcie*`, `**/Nieprzypisane.*`,
   `**/AliasyPNA.*`, `**/*exporty*.zip`) łapią je w **każdym** katalogu,
   bo pliki z przeglądarki lądują tam, gdzie wskaże okno zapisu. Nowy
   rodzaj eksportu dostaje taki wzorzec od razu.
4. Ustalenia z analizy danych trafiają do `../docs/domain-model.md`
   w formie opisowej, bez cytowania realnych nazwisk, adresów czy PNI.

## Verification

`git ls-files data/` zwraca wyłącznie `README.md`, `CLAUDE.md`
i `AGENTS.md`.

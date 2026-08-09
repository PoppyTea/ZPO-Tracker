-- DRAFT v2 — DO PRZEGLĄDU, NIE WDROŻONE.
-- Wynik sesji "co zawiera się w czym" (patrz CLAUDE.md, sekcja
-- "Normalizacja v2"). NIE zastępuje schema.sql automatycznie —
-- to punkt wyjścia do świadomej decyzji, najlepiej przez TDD w Claude Code.
--
-- Dwie rzeczy czekają na decyzję PRZED wdrożeniem (opisane szerzej w CLAUDE.md):
--   1. kod_pocztowy nie istnieje w danych źródłowych — nie ma z czego go
--      zaimportować automatycznie, zostanie puste do ręcznego uzupełnienia
--   2. rozbicie Kurier -> imię/nazwisko jest ryzykowne parsingowo (niespójne
--      białe znaki, brak gwarancji kolejności) — stąd pelne_nazwisko_raw
--      jako pole zapasowe

PRAGMA foreign_keys = ON;

CREATE TABLE wykonawcy (
    id      INTEGER PRIMARY KEY,
    nazwa   TEXT NOT NULL UNIQUE            -- Koli, Poczta Polska, Translist, Rekus
                                             -- (podwykonawca obsługi kurierskiej)
);

CREATE TABLE kurierzy (
    id                      INTEGER PRIMARY KEY,
    imie                    TEXT NOT NULL,
    nazwisko                TEXT NOT NULL,
    pelne_nazwisko_raw      TEXT,               -- fallback: oryginalny string z importu
    identyfikator_zewnetrzny TEXT UNIQUE,        -- backlog: potrzebny przy łączeniu z innymi systemami (np. nr pracownika)
    wykonawca_id            INTEGER REFERENCES wykonawcy(id),
    UNIQUE(imie, nazwisko, wykonawca_id)
);

CREATE TABLE miejscowosci (
    id      INTEGER PRIMARY KEY,
    nazwa   TEXT NOT NULL UNIQUE
);

CREATE TABLE ulice (
    id              INTEGER PRIMARY KEY,
    nazwa           TEXT NOT NULL,
    miejscowosc_id  INTEGER NOT NULL REFERENCES miejscowosci(id),
    UNIQUE(nazwa, miejscowosc_id)           -- ta sama nazwa w innej miejscowości = inny rekord
);

CREATE TABLE adresy (
    id              INTEGER PRIMARY KEY,
    ulica_id        INTEGER NOT NULL REFERENCES ulice(id),
    nr_budynku      TEXT NOT NULL,
    nr_lokalu       TEXT,
    kod_pocztowy    TEXT,                   -- brak w danych źródłowych, patrz notatka wyżej
    UNIQUE(ulica_id, nr_budynku, nr_lokalu)
);

CREATE TABLE firmy_zpo (
    id      INTEGER PRIMARY KEY,
    nazwa   TEXT NOT NULL UNIQUE            -- Żabka, Duży Ben, Groszek, Delikatesy Centrum, ABC...
);

-- nadawcy (zwykli klienci: ZUS, PKO, Kruk...) CELOWO nie są tu jeszcze
-- znormalizowani do osobnej tabeli - wzorzec ich powiązania z ZPO/punktami
-- nie jest jeszcze jasny (podejrzenie, że mogą się z czasem okazać z tym
-- powiązane), więc trzymamy luzem jako pole tekstowe, patrz CLAUDE.md

-- Punkt = adres, pod który kurier jedzie odebrać przesyłki.
CREATE TABLE punkty (
    id              INTEGER PRIMARY KEY,
    adres_id        INTEGER NOT NULL REFERENCES adresy(id),
    pni_zpo         TEXT UNIQUE,             -- NULL dla zwykłych klientów
    firma_zpo_id    INTEGER REFERENCES firmy_zpo(id),   -- wypełnione tylko gdy pni_zpo != NULL
    nadawca_surowy  TEXT                     -- luźne pole, jeszcze nie znormalizowane (patrz wyżej)
);

CREATE TABLE rejony (
    id              INTEGER PRIMARY KEY,
    prefix          TEXT NOT NULL,           -- WA, ND, M, Z, L, R...
    numer           TEXT NOT NULL,           -- może zawierać literę sufiksu, np. "23A"
    miejscowosc_id  INTEGER REFERENCES miejscowosci(id),  -- "największe miasto" wg prefiksu
    wykonawca_id    INTEGER REFERENCES wykonawcy(id),
    UNIQUE(prefix, numer)
);

CREATE TABLE transakcje (
    id                      INTEGER PRIMARY KEY,
    data                    DATE NOT NULL,
    kurier_id               INTEGER NOT NULL REFERENCES kurierzy(id),
    punkt_id                INTEGER NOT NULL REFERENCES punkty(id),
    rejon_id                INTEGER REFERENCES rejony(id),
    ilosc_total             INTEGER NOT NULL,
    ilosc_zpo               INTEGER,
    ilosc_vinted            INTEGER,
    ilosc_automaty          INTEGER,
    ilosc_kurier48          INTEGER,
    ilosc_niezrealizowane   INTEGER,
    UNIQUE(data, kurier_id, punkt_id)
);

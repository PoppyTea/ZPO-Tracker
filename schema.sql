-- Schemat MVP: modernizacja wprowadzania danych kurier/ZPO
-- Oparty na analizie realnych danych (2026-08-07-snapshot-ZPO, 4573 wierszy / 5 dni)
--
-- Kluczowe założenia wynikające z analizy:
--   * PNI ZPO jest wiarygodnym unikalnym identyfikatorem fizycznego punktu
--     (potwierdzone: pozorna "kolizja" Kordeckiego 26 Legionowo/Chotomów
--     to tylko niekonsekwentny zapis tego samego adresu, nie duplikat ID)
--   * "Punkt" nie musi być zewnętrznym punktem odbioru (ZPO) — zwykli
--     nadawcy (ZUS, PKO, Kruk...) też mają swój adres, po prostu bez PNI
--   * Transakcja = log, nie stan: ta sama para kurier+punkt powtarza się
--     wielokrotnie w miesiącu, różniąc się datą i ilością

PRAGMA foreign_keys = ON;

CREATE TABLE kurierzy (
    id              INTEGER PRIMARY KEY,
    imie_nazwisko   TEXT NOT NULL UNIQUE
);

CREATE TABLE rejony (
    id              INTEGER PRIMARY KEY,
    kod             TEXT NOT NULL UNIQUE          -- np. WA87, ND1, Z2
);

-- Kanoniczny "rejon nieznany" - musi być zgodny z
-- normalizacja.REJON_NIEZNANY. Zaseedowany tutaj, żeby świeża baza miała
-- ten sam wiersz, który dla bazy migrowanej dokłada repo.napraw_dane.
INSERT INTO rejony (kod) VALUES ('???');

CREATE TABLE wykonawcy (
    id              INTEGER PRIMARY KEY,
    nazwa           TEXT NOT NULL UNIQUE          -- Koli, Poczta Polska, Translist, Rekus
);

-- Firma ZPO = sieć hostująca zewnętrzny punkt odbioru (Żabka, Duży Ben,
-- Groszek, Delikatesy Centrum, ABC...). Osobna rola od wykonawcy (ten
-- obsługuje trasę kurierską) - łatwo je pomylić, patrz normalization-v2.md.
CREATE TABLE firmy_zpo (
    id              INTEGER PRIMARY KEY,
    nazwa           TEXT NOT NULL UNIQUE
);

-- Punkt = adres, pod który kurier jedzie odebrać przesyłki.
-- Może to być zwykły nadawca (pni_zpo = NULL) albo zewnętrzny punkt
-- odbioru typu Żabka/Groszek/Duży Ben/ABC (pni_zpo + firma_zpo_id wypełnione).
CREATE TABLE punkty (
    id              INTEGER PRIMARY KEY,
    nadawca         TEXT NOT NULL,                -- np. "Żabka", "ZUS", "PKO"
    adres           TEXT NOT NULL,                -- adres kanoniczny, zapisany raz
    pni_zpo         TEXT UNIQUE,                  -- NULL dla zwykłych nadawców
    firma_zpo_id    INTEGER REFERENCES firmy_zpo(id)  -- wypełnione tylko gdy pni_zpo != NULL
);

CREATE INDEX idx_punkty_nadawca ON punkty(nadawca);

-- Log transakcyjny — to jest jedyna tabela, do której realnie
-- dopisuje się nowe wiersze każdego dnia roboczego.
CREATE TABLE transakcje (
    id                      INTEGER PRIMARY KEY,
    data                    DATE NOT NULL,
    kurier_id               INTEGER NOT NULL REFERENCES kurierzy(id),
    punkt_id                INTEGER NOT NULL REFERENCES punkty(id),
    rejon_id                INTEGER REFERENCES rejony(id),
    wykonawca_id            INTEGER REFERENCES wykonawcy(id),

    ilosc_total             INTEGER NOT NULL,      -- pole aktywne w MVP
    ilosc_zpo               INTEGER,                -- pole aktywne w MVP (tylko gdy punkt ma pni_zpo)

    -- obecne w realnych danych, ale rzadkie/puste w próbce — kolumny
    -- gotowe na przyszłość, na razie NIE eksponowane w formularzu MVP
    ilosc_vinted            INTEGER,
    ilosc_automaty          INTEGER,
    ilosc_kurier48          INTEGER,
    ilosc_niezrealizowane   INTEGER,

    -- komentarz do bloku rejonu na blankiecie (np. gdy rejon nieznany
    -- w momencie wpisywania) - patrz ux-ui.md, ta sama wartość dla
    -- wszystkich wierszy jednego bloku REJON w formularzu
    komentarz               TEXT,

    -- Tożsamość wiersza NIEZALEŻNA od klucza naturalnego. Poprawka daty
    -- albo kuriera zmienia (data,kurier,punkt), więc przy synchronizacji
    -- między stacjami wyglądałaby jak nowy wiersz i powstałby duplikat.
    uuid                    TEXT UNIQUE,

    -- Atrybucja: kto i kiedy. Znaczniki czasu służą do audytu i pokazania
    -- użytkownikowi - NIGDY do automatycznego rozstrzygania konfliktów
    -- (zegary firmowych maszyn bywają rozjechane, a konflikt ilości i tak
    -- zawsze rozstrzyga człowiek - patrz docs/roadmap.md).
    autor_id                TEXT REFERENCES users(id),
    utworzono               TEXT,
    zmodyfikowano           TEXT,

    -- twarda ochrona przed literalnym duplikatem tego samego wiersza
    UNIQUE(data, kurier_id, punkt_id)
);

-- Pracownicy działu wprowadzający dane (NIE kurierzy - to inna tabela
-- i inny format numeru kadrowego, patrz docs/roadmap.md).
--
-- `id` to UUIDv5 wyliczone z "domena\login", a NIE losowy UUID nadawany
-- przy pierwszym zetknięciu z nowym loginem: losowy rozjechałby się między
-- stacjami (każda nadałaby tej samej osobie inny), a po synchronizacji
-- między stacjami ta sama osoba istniałaby wielokrotnie.
CREATE TABLE users (
    id          TEXT PRIMARY KEY,        -- UUIDv5(domena\login)
    login       TEXT NOT NULL UNIQUE,    -- "DOMENA\login" z systemu
    alias       TEXT,                    -- imię i nazwisko, zmienialne
    nr_kadrowy  TEXT UNIQUE,             -- 5 znaków [a-zA-Z0-9], case sensitive
    utworzono   TEXT,
    -- GLOB, nie LIKE: LIKE jest niewrażliwy na wielkość liter, a numer
    -- kadrowy jest case sensitive (wymóg z organizacji)
    CHECK (nr_kadrowy IS NULL OR (
        length(nr_kadrowy) = 5
        AND nr_kadrowy GLOB '[A-Za-z0-9][A-Za-z0-9][A-Za-z0-9][A-Za-z0-9][A-Za-z0-9]'
    ))
);

CREATE INDEX idx_transakcje_data ON transakcje(data);
CREATE INDEX idx_transakcje_punkt ON transakcje(punkt_id);

-- 0.1-alpha.3.1: pod dedukcję pól formularza (dedukcja.py) - bez nich
-- historia_wykonawcow_kuriera/znajdz_punkty_po_adresie robią pełny SCAN
-- (EXPLAIN QUERY PLAN, zmierzone), co na wątku głównym Tk rośnie liniowo
-- z historią transakcji.
CREATE INDEX idx_transakcje_kurier ON transakcje(kurier_id);
CREATE INDEX idx_punkty_adres ON punkty(adres);

-- Wersja schematu. Podnosić przy KAŻDEJ zmianie struktury.
-- Bez tego przywrócenie starszej migawki po aktualizacji aplikacji otwiera
-- bazę o nieaktualnej strukturze i wywala się na "no such column" - już po
-- nadpisaniu dobrych danych. Musi być zgodna z repo.WERSJA_SCHEMATU
-- (pilnowane testem test_utworzenie_schematu_ustawia_user_version).
PRAGMA user_version = 2;

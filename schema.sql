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

    -- twarda ochrona przed literalnym duplikatem tego samego wiersza
    UNIQUE(data, kurier_id, punkt_id)
);

CREATE INDEX idx_transakcje_data ON transakcje(data);
CREATE INDEX idx_transakcje_punkt ON transakcje(punkt_id);

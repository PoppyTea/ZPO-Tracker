-- Schemat v4: adres strukturalny, nadawcy w jednej tabeli.
--
-- Oparty na analizie realnych danych (2026-08-07-snapshot-ZPO, 1259 wierszy)
-- oraz na kompletnym eksporcie rejonarza z BaŚKi (WW - WER Ciemne,
-- 277 568 adresów, 219 rejonów).
--
-- Kluczowe założenia wynikające z analizy:
--   * PNI ZPO jest wiarygodnym unikalnym identyfikatorem fizycznego punktu
--   * "Punkt" nie musi być zewnętrznym punktem odbioru (ZPO) — zwykli
--     nadawcy też mają swój adres, po prostu bez PNI
--   * Transakcja = log, nie stan: ta sama para kurier+punkt powtarza się
--     wielokrotnie w miesiącu, różniąc się datą i ilością
--
-- CO ZMIENIŁO SIĘ WOBEC v3 I DLACZEGO:
--
--   * `punkty.adres TEXT` rozbite na `miejscowosci`/`ulice`/`adresy`.
--     Powód jest zmierzony, nie estetyczny: 32,9% adresów nie dawało się
--     dopasować do rejonarza, a 15,04% zapytań było strukturalnie
--     nierozstrzygalnych, bo adres nie niósł miejscowości.
--   * `firmy_zpo` USUNIĘTE, zastąpione przez `nadawcy` z flagą.
--     Poprzedni układ trzymał nazwę w dwóch miejscach naraz
--     (`punkty.nadawca` i `firmy_zpo.nazwa`), przez co naprawa danych
--     musiała zakładać "firmę" dla każdego punktu z PNI — i samodzielny
--     sklep stawał się jednoelementową siecią. Jedna tabela to usuwa
--     u źródła, zamiast obudowywać.
--   * `rejony.kod` CELOWO zostaje jednym polem. Wcześniejszy draft v2
--     zapowiadał podział regexem ^([A-Z]+)(\d+[A-Z]?)$ — ten wzorzec
--     odrzuca RDH, PP, WER, MIG, POU, WRC i WRT, potwierdzone jako
--     prawdziwe rejony w eksporcie BaŚKi. Podział nie kupuje nic
--     mierzalnego, a kosztuje regex, który już raz zgubił dane.

PRAGMA foreign_keys = ON;

CREATE TABLE kurierzy (
    id              INTEGER PRIMARY KEY,
    imie_nazwisko   TEXT NOT NULL UNIQUE
);

CREATE TABLE rejony (
    id              INTEGER PRIMARY KEY,
    kod             TEXT NOT NULL UNIQUE          -- np. WA87, ND1, Z2, RDH
);

-- Kanoniczny "rejon nieznany" - musi być zgodny z
-- normalizacja.REJON_NIEZNANY. Zaseedowany tutaj, żeby świeża baza miała
-- ten sam wiersz, który dla bazy migrowanej dokłada repo.napraw_dane.
INSERT INTO rejony (kod) VALUES ('???');

CREATE TABLE wykonawcy (
    id              INTEGER PRIMARY KEY,
    nazwa           TEXT NOT NULL UNIQUE          -- Koli, Poczta Polska, Translist, Rekus
);

-- --- adres strukturalny -------------------------------------------------

-- Miejscowość w postaci, w jakiej podaje ją BaŚKa: "Warszawa (Śródmieście)"
-- z gminą "Warszawa" obok. Zwinięcie dzielnic do gminy jest tym, na czym
-- stoi reguła "załóż Warszawę" w kaskadzie dedukcji miejscowości.
CREATE TABLE miejscowosci (
    id      INTEGER PRIMARY KEY,
    nazwa   TEXT NOT NULL UNIQUE,
    gmina   TEXT
);

CREATE TABLE ulice (
    id              INTEGER PRIMARY KEY,
    nazwa           TEXT NOT NULL,
    typ             TEXT,                   -- Ulica/Aleja/Plac; ta sama ulica
                                            -- bywa zapisana z prefiksem i bez
    miejscowosc_id  INTEGER NOT NULL REFERENCES miejscowosci(id),
    UNIQUE(nazwa, miejscowosc_id)           -- ta sama nazwa w innej
                                            -- miejscowości to inna ulica
);

-- Adres. WSZYSTKIE pola strukturalne są NULLowalne, i to jest decyzja,
-- nie niedopatrzenie: brak wartości znaczy "jeszcze nie wiemy", nie
-- "błąd". Wiersz, którego nie umiemy rozłożyć, ma dać się zapisać i
-- trafić do poprawy — blokada zapisu zamieniłaby zaległość w utratę.
--
-- `surowy` jest źródłem prawdy i NIGDY nie jest nadpisywany. Struktura to
-- tylko jego interpretacja. Parser adresu to lista reguł, nie algorytm,
-- więc będzie się poprawiał; z zachowanym oryginałem da się przepuścić
-- całą bazę jeszcze raz, bez niego każda poprawka parsera wymagałaby
-- ponownego importu z Excela.
CREATE TABLE adresy (
    id            INTEGER PRIMARY KEY,
    surowy        TEXT NOT NULL UNIQUE,
    ulica_id      INTEGER REFERENCES ulice(id),
    nr_budynku    TEXT,
    nr_lokalu     TEXT,
    pna           TEXT,

    -- surowy | sparsowany | potwierdzony | do_decyzji
    stan          TEXT NOT NULL DEFAULT 'surowy',

    -- KTÓRA reguła kaskady dała miejscowość. Bez tego człowiek
    -- przeglądający wynik nie odróżni "wiemy na pewno" od "zgadliśmy
    -- z dnia kuriera", a to jest różnica, przy której trzeba się
    -- zatrzymać.
    zrodlo_miejscowosci TEXT,

    -- Trzy rejony w trzech miejscach, CELOWO nie mieszane:
    -- co wpisano w źródle -> transakcje.rejon_id (fakt historyczny),
    -- co mówi BaŚKa       -> rejon_baska (odświeżane przy imporcie),
    -- co rozstrzygnął człowiek -> rejon_potwierdzony (wiążące).
    -- Kolejka poprawek to wtedy zwykły WHERE po rozbieżności.
    rejon_baska         TEXT,
    rejon_potwierdzony  TEXT
);

CREATE INDEX idx_adresy_ulica ON adresy(ulica_id);

-- --- nadawcy i punkty ---------------------------------------------------

-- Wszyscy nadawcy w jednej tabeli: i sieciówki (Żabka, Groszek, ABC),
-- i zwykli klienci (ZUS, PKO), i punkty samodzielne.
CREATE TABLE nadawcy (
    id       INTEGER PRIMARY KEY,
    nazwa    TEXT NOT NULL UNIQUE,

    -- Czy dla tego nadawcy wypełnia się kolumnę "w tym ZPO".
    -- Nazwane tym, co robi, a nie tym, czym jest ("czy sieciówka"),
    -- bo tylko to z tego rozróżnienia realnie wynika.
    --
    -- Wcześniej program wnioskował to z obecności PNI, co było błędne
    -- dokładnie w przypadku, który zdarza się najczęściej: punkt JEST
    -- ZPO, ale PNI jeszcze nie znamy — i pole było wygaszone. Jawna
    -- flaga to naprawia i przy okazji daje gotową listę "trzeba zdobyć
    -- PNI z paragonu":
    --     WHERE n.liczy_zpo = 1 AND p.pni_zpo IS NULL
    liczy_zpo  INTEGER NOT NULL DEFAULT 0
);

-- Punkt = konkretny nadawca pod konkretnym adresem.
CREATE TABLE punkty (
    id          INTEGER PRIMARY KEY,
    nadawca_id  INTEGER NOT NULL REFERENCES nadawcy(id),
    adres_id    INTEGER NOT NULL REFERENCES adresy(id),
    pni_zpo     TEXT UNIQUE,            -- NULL, gdy jeszcze nieznane
    UNIQUE(nadawca_id, adres_id)
);

CREATE INDEX idx_punkty_nadawca ON punkty(nadawca_id);
CREATE INDEX idx_punkty_adres ON punkty(adres_id);

-- --- log transakcyjny ---------------------------------------------------

-- Jedyna tabela, do której realnie dopisuje się wiersze każdego dnia.
CREATE TABLE transakcje (
    id                      INTEGER PRIMARY KEY,
    data                    DATE NOT NULL,
    kurier_id               INTEGER NOT NULL REFERENCES kurierzy(id),
    punkt_id                INTEGER NOT NULL REFERENCES punkty(id),

    -- Rejon TAK, JAK GO WPISANO w źródle. Fakt historyczny - nie
    -- poprawiamy go po cichu tym, co mówi BaŚKa; porównanie obu żyje
    -- w adresy.rejon_baska i to człowiek rozstrzyga rozbieżność.
    rejon_id                INTEGER REFERENCES rejony(id),
    wykonawca_id            INTEGER REFERENCES wykonawcy(id),

    ilosc_total             INTEGER NOT NULL,
    ilosc_zpo               INTEGER,

    -- obecne w realnych danych, ale rzadkie/puste w próbce — kolumny
    -- gotowe na przyszłość, na razie NIE eksponowane w formularzu
    ilosc_vinted            INTEGER,
    ilosc_automaty          INTEGER,
    ilosc_kurier48          INTEGER,
    ilosc_niezrealizowane   INTEGER,

    komentarz               TEXT,

    -- Tożsamość wiersza NIEZALEŻNA od klucza naturalnego. Poprawka daty
    -- albo kuriera zmienia (data,kurier,punkt), więc przy synchronizacji
    -- między stacjami wyglądałaby jak nowy wiersz i powstałby duplikat.
    uuid                    TEXT UNIQUE,

    -- Atrybucja: kto i kiedy. Znaczniki czasu służą do audytu i pokazania
    -- użytkownikowi - NIGDY do automatycznego rozstrzygania konfliktów
    -- (zegary firmowych maszyn bywają rozjechane, a konflikt ilości i tak
    -- zawsze rozstrzyga człowiek).
    autor_id                TEXT REFERENCES users(id),
    utworzono               TEXT,
    zmodyfikowano           TEXT,

    -- `sesja_uuid` = losowy UUID nadany RAZ przy starcie aplikacji (klucz
    -- grupujący "co wpisałem teraz"). `zrodlo` = skąd wiersz powstał
    -- ('formularz'/'import'/'import_zaufany').
    sesja_uuid               TEXT,
    zrodlo                   TEXT,

    UNIQUE(data, kurier_id, punkt_id)
);

-- Pracownicy działu wprowadzający dane (NIE kurierzy - to inna tabela
-- i inny format numeru kadrowego).
--
-- `id` to UUIDv5 wyliczone z "domena\login", a NIE losowy UUID nadawany
-- przy pierwszym zetknięciu z nowym loginem: losowy rozjechałby się między
-- stacjami, a po synchronizacji ta sama osoba istniałaby wielokrotnie.
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
CREATE INDEX idx_transakcje_kurier ON transakcje(kurier_id);
CREATE INDEX idx_transakcje_sesja ON transakcje(sesja_uuid);

-- Wersja schematu. Podnosić przy KAŻDEJ zmianie struktury.
-- Bez tego przywrócenie starszej migawki po aktualizacji aplikacji otwiera
-- bazę o nieaktualnej strukturze i wywala się na "no such column" - już po
-- nadpisaniu dobrych danych. Musi być zgodna z repo.WERSJA_SCHEMATU
-- (pilnowane testem test_utworzenie_schematu_ustawia_user_version).
PRAGMA user_version = 4;

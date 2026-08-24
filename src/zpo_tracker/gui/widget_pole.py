"""
Kolorowy pasek wskaźnika stanu pola (dedukcja.StanPola) + obwódka
sygnalizująca uwagę/kolejność nawigacji Tab (0.1-alpha.3.1). Sam nie
waliduje ani nie decyduje - tylko odzwierciedla stan przekazany z
dedukcja.py, żeby logika szeregowania/aktywności została w warstwie
logiki (patrz src/CLAUDE.md: "jeśli widget zaczyna decydować... to kod
należy do modułu logiki").

tk.Frame, nie ttk.Frame: highlightthickness/highlightbackground na
obwódkę jest opcją tk-ową, a ttk (pod motywem, np. `vista` na Windows)
nie honoruje jej tak samo przewidywalnie.
"""
import tkinter as tk

from zpo_tracker.gui import styl

# Re-eksport, NIE kopia - jedno źródło prawdy siedzi w styl.py, patrz
# tamtejszy docstring. Nazwa `KOLORY` zostaje dla zgodności z istniejącym
# kodem (zakladka_wprowadzanie importuje ją stąd).
KOLORY = styl.KOLORY_STANOW
KOLORY_POLPRZYGASZONE = styl.KOLORY_STANOW_POLPRZYGASZONE
KOLORY_PRZYGASZONE = styl.KOLORY_STANOW_PRZYGASZONE

# Grubość jest STAŁA. Wcześniej przełączała się między 0, 1 i 2 px, a to
# zmienia żądany rozmiar widgetu o 2*grubość na stronę - przez co
# zawartość komórek siatki skakała przy każdej dedukcji. Sygnał niesie
# teraz wyłącznie kolor (rampa niżej).
GRUBOSC_OBWODKI = 1

SZEROKOSC_STRZALKI = 16
ZNAK_STRZALKI = "▾"


class PoleZeWskaznikiem(tk.Frame):
    """
    Owija istniejący widget pola (Entry/EntryZPodpowiedzia) paskiem stanu
    po lewej + obwódką. Dziecko z metodą `ustaw_stan_pola(state,
    takefocus)` (EntryZPodpowiedzia) jest sterowane przez nią; zwykły
    Entry/ttk.Entry dostaje surowe `configure(state=..., takefocus=...)`.
    """

    def __init__(self, parent, fabryka_widgetu_pola, **kwargs):
        """
        `fabryka_widgetu_pola`: wywoływalne przyjmujące JEDEN argument
        (rodzica) i zwracające widget pola, np. `lambda p: ttk.Entry(p,
        textvariable=var)` albo sama klasa (`tk.Entry`). NIE gotowy
        widget - Tk pakuje/griduje widget do jego RZECZYWISTEGO rodzica
        ustalonego przy tworzeniu, więc widget zbudowany z innym
        rodzicem niż ten wrapper wylądowałby wizualnie jako rodzeństwo w
        oknie nadrzędnym, nie wewnątrz paska ze wskaźnikiem (sprawdzone
        eksperymentalnie).
        """
        super().__init__(parent, highlightthickness=0, **kwargs)
        self._stan = "szary"
        self._aktywne = False
        self._nastepne = False
        self._fokus = False
        self._zablokowane = False
        self._ile_wariantow = 0
        self._strzalka = None

        self.pasek = tk.Frame(self, width=4, background=KOLORY["szary"])
        self.pasek.pack(side="left", fill="y")
        self.pasek.pack_propagate(False)
        self.widget_pola = fabryka_widgetu_pola(self)
        self.widget_pola.pack(side="left", fill="both", expand=True)

        # add="+" - nie kasujemy bindingów, które widget pola mógł już
        # mieć (EntryZPodpowiedzia wiesza własne na FocusIn).
        ogniskowalny = self._widget_ogniskowalny()
        ogniskowalny.bind("<FocusIn>", lambda e: self.ustaw_fokus(True), add="+")
        ogniskowalny.bind("<FocusOut>", lambda e: self.ustaw_fokus(False), add="+")
        self._odswiez_obwodke()

    def ustaw_stan(self, stan):
        """stan: jeden z dedukcja.STANY."""
        self._stan = stan
        self.pasek.configure(background=KOLORY[stan])
        self._odswiez_obwodke()

    def ustaw_aktywnosc(self, aktywne):
        """
        aktywne=True: pole edytowalne i osiągalne Tabem.
        aktywne=False: readonly (zaznaczalne, ale nieedytowalne) +
        takefocus=0 - dopiero ta kombinacja pomija pole w nawigacji Tab
        (zweryfikowane empirycznie: samo readonly nie wystarcza).

        UWAGA: "aktywne" to NIE to samo co "ma kursor". Od 2026-08-24
        wyglądem obwódki rządzi fokus (patrz `ustaw_fokus`), a nie ta
        flaga - pole edytowalne, ale nietknięte, ma być spokojne.
        """
        self._aktywne = aktywne
        stan_tk = "normal" if aktywne else "readonly"
        takefocus = 1 if aktywne else 0
        if hasattr(self.widget_pola, "ustaw_stan_pola"):
            self.widget_pola.ustaw_stan_pola(stan_tk, takefocus)
        else:
            self.widget_pola.configure(state=stan_tk, takefocus=takefocus)
        self._odswiez_obwodke()

    def ustaw_fokus(self, czy):
        """Pole jest właśnie wypełniane (ma kursor) - pełny kolor stanu.

        Wywoływane samo, z bindingów `<FocusIn>`/`<FocusOut>`; publiczne,
        żeby dało się je przetestować bez symulowania zdarzeń Tk.
        """
        self._fokus = czy
        self._odswiez_obwodke()

    def ustaw_nastepne(self, czy):
        """Pole, na które doprowadzi kolejny Tab. Środkowy stopień rampy -
        widoczne, ale nie krzyczy jak pole z kursorem."""
        self._nastepne = czy
        self._odswiez_obwodke()

    def ustaw_liste(self, ile_wariantow):
        """
        Pokazuje (albo chowa) afordancję rozwijanej listy - wariant A2,
        czyli szary box z trójkątem po prawej.

        Widget sam nie wie, ile jest kandydatów: `dedukcja.StanPola`
        rozpakowuje warstwa wyżej, a pytanie dziecka przy każdym renderze
        oznaczałoby zapytanie do bazy. Stąd jawny argument.

        Do 2026-08-24 pole z listą i pole bez były wizualnie
        nierozróżnialne, a lista wyskakiwała dopiero po wpisaniu znaku.
        """
        self._ile_wariantow = ile_wariantow or 0
        if self._ile_wariantow > 0 and self._strzalka is None:
            self._strzalka = tk.Frame(
                self, width=SZEROKOSC_STRZALKI, background=styl.PALETA["linia_mocna"])
            # `before` jest konieczne: widget pola jest spakowany z
            # expand=True, więc bez tego zabrałby całą szerokość, a box
            # spakowany później nie miałby się gdzie zmieścić.
            self._strzalka.pack(side="right", fill="y", before=self.widget_pola)
            self._strzalka.pack_propagate(False)
            tk.Label(
                self._strzalka, text=ZNAK_STRZALKI,
                background=styl.PALETA["linia_mocna"],
                foreground=styl.PALETA["tekst"],
                font=("TkDefaultFont", 7),
            ).pack(expand=True)
        elif self._ile_wariantow == 0 and self._strzalka is not None:
            self._strzalka.destroy()
            self._strzalka = None

    def zablokuj(self, czy):
        """Miejsce na wygląd zablokowanego pola (0.1-alpha.5, kliknięcie
        wskaźnika) - nikt jeszcze tego nie ustawia."""
        self._zablokowane = czy

    def _widget_ogniskowalny(self):
        """EntryZPodpowiedzia trzyma prawdziwy Entry w `.entry`; zwykły
        ttk.Entry jest sam sobie polem."""
        return getattr(self.widget_pola, "entry", self.widget_pola)

    def _kolor_obwodki(self):
        """Trzystopniowa rampa na barwie stanu, zamiast trzech grubości:
        pełny (kursor tutaj) -> półprzygaszony (tu doprowadzi Tab) ->
        przygaszony (spokojne). Decyzja Papavera 2026-08-24: W2 dla pola
        wypełnianego, W3 dla reszty."""
        if self._fokus:
            return KOLORY[self._stan]
        if self._nastepne:
            return KOLORY_POLPRZYGASZONE[self._stan]
        return KOLORY_PRZYGASZONE[self._stan]

    def _odswiez_obwodke(self):
        kolor = self._kolor_obwodki()
        self.configure(
            highlightthickness=GRUBOSC_OBWODKI,
            highlightbackground=kolor,
            highlightcolor=kolor,
        )

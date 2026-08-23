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

# Przestrojone pod CIEMNE tło (2026-08-24) - poprzedni zestaw
# (#888888/#1e7a3a/#b35c00/#c0392b) był dobrany pod jasne i na ciemnym
# schodził poniżej progu czytelności: sam zielony miał tam ok. 1.6:1.
# Wartości niżej mają na `styl.PALETA["tlo"]` od 5.5:1 do 7.0:1, co
# pilnuje test_kolory_stanow_widoczne_na_tle. Zielony i czerwony trafiają
# dodatkowo na etykietę statusu jako TEKST, więc dla nich obowiązuje
# ostrzejszy próg 4.5:1, nie 3:1 jak dla paska wskaźnika.
#
# To JEDYNE źródło tych czterech barw w projekcie - `styl.KOLORY_STANOW`
# jest tym samym obiektem, nie kopią (przypięte testem tożsamości).
KOLORY = {
    "szary": "#8b95a5",
    "zielony": "#4caf6a",
    "pomaranczowy": "#e0913c",
    "czerwony": "#e4695c",
}

GRUBOSC_AKTYWNE = 2
GRUBOSC_NASTEPNE = 1


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
        self._zablokowane = False

        self.pasek = tk.Frame(self, width=4, background=KOLORY["szary"])
        self.pasek.pack(side="left", fill="y")
        self.pasek.pack_propagate(False)
        self.widget_pola = fabryka_widgetu_pola(self)
        self.widget_pola.pack(side="left", fill="both", expand=True)

    def ustaw_stan(self, stan):
        """stan: jeden z dedukcja.STANY."""
        self._stan = stan
        self.pasek.configure(background=KOLORY[stan])
        self._odswiez_obwodke()

    def ustaw_aktywnosc(self, aktywne):
        """
        aktywne=True: pole edytowalne, osiągalne Tabem, dostaje trwałą
        obwódkę w kolorze bieżącego stanu (aktywne pole zawsze wymaga
        uwagi - patrz dedukcja.sprawdz_niezmienniki).
        aktywne=False: readonly (zaznaczalne, ale nieedytowalne) +
        takefocus=0 - dopiero ta kombinacja pomija pole w nawigacji Tab
        (zweryfikowane empirycznie: samo readonly nie wystarcza).
        """
        self._aktywne = aktywne
        stan_tk = "normal" if aktywne else "readonly"
        takefocus = 1 if aktywne else 0
        if hasattr(self.widget_pola, "ustaw_stan_pola"):
            self.widget_pola.ustaw_stan_pola(stan_tk, takefocus)
        else:
            self.widget_pola.configure(state=stan_tk, takefocus=takefocus)
        self._odswiez_obwodke()

    def ustaw_nastepne(self, czy):
        """Podświetla pole jako NASTĘPNE w kolejności nawigacji - ten sam
        motyw (kolor) co pole aktywne, cieńsza obwódka. `aktywne` ma
        pierwszeństwo: pole jednocześnie aktywne i następne pokazuje
        grubszą obwódkę, nie cichą nadpisankę."""
        self._nastepne = czy
        self._odswiez_obwodke()

    def zablokuj(self, czy):
        """Miejsce na wygląd zablokowanego pola (0.1-alpha.3.2, kliknięcie
        wskaźnika) - nikt jeszcze tego nie ustawia."""
        self._zablokowane = czy

    def _odswiez_obwodke(self):
        if self._aktywne:
            grubosc = GRUBOSC_AKTYWNE
        elif self._nastepne:
            grubosc = GRUBOSC_NASTEPNE
        else:
            grubosc = 0
        self.configure(
            highlightthickness=grubosc,
            highlightbackground=KOLORY[self._stan],
            highlightcolor=KOLORY[self._stan],
        )

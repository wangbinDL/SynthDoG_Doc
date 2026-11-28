"""Language registry: the Top-10 non-Chinese, non-English languages by total speakers.

Ranking source: Wikipedia "List of languages by total number of speakers" (Ethnologue);
see docs/languages.md for the table and the ranking rationale.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Lang:
    code: str                 # ISO 639-1
    name: str                 # English name
    native: str               # endonym
    script: str               # latin | cyrillic | devanagari | bengali | arabic
    rtl: bool
    wiki_config: str          # wikimedia/wikipedia config
    fineweb_config: str       # HuggingFaceFW/fineweb-2 config
    country_tlds: tuple       # TLDs of the main countries using the language
    news_domains: tuple       # national news sites (domain suffixes) used to pick "news" text
    native_digits: str = ""   # native digit glyphs 0-9 if the script has them
    native_digit_prob: float = 0.0  # probability a document uses native digits
    hyphenate: bool = False   # pre-hyphenate with pyphen (soft hyphens) for justified columns
    pyphen_lang: str = ""
    quotes: tuple = ("“", "”")
    countries: tuple = field(default=())


LANGS = {
    "hi": Lang("hi", "Hindi", "हिन्दी", "devanagari", False, "20231101.hi", "hin_Deva",
               (".in",),
               ("bhaskar.com", "jagran.com", "amarujala.com", "livehindustan.com", "navbharattimes.indiatimes.com",
                "ndtv.in", "aajtak.in", "abplive.com", "patrika.com", "jansatta.com", "prabhasakshi.com",
                "zeenews.india.com", "hindi.news18.com", "news18.com", "tv9hindi.com", "naidunia.com",
                "haribhoomi.com", "prabhatkhabar.com", "punjabkesari.in", "webdunia.com", "lokmat.com",
                "hindi.oneindia.com", "khabar.ndtv.com", "deshbandhu.co.in", "bbc.com", "dw.com"),
               native_digits="०१२३४५६७८९", native_digit_prob=0.15,
               quotes=("“", "”"), countries=("India",)),
    "es": Lang("es", "Spanish", "Español", "latin", False, "20231101.es", "spa_Latn",
               (".es", ".mx", ".ar", ".co", ".cl", ".pe", ".ve", ".ec", ".uy", ".bo", ".py", ".cr", ".gt", ".cu"),
               ("elpais.com", "elmundo.es", "abc.es", "lavanguardia.com", "clarin.com", "lanacion.com.ar",
                "eluniversal.com.mx", "milenio.com", "eltiempo.com", "infobae.com", "20minutos.es", "larazon.es",
                "elespanol.com", "elconfidencial.com", "publico.es", "eldiario.es", "excelsior.com.mx",
                "jornada.com.mx", "elcomercio.pe", "emol.com", "latercera.com", "elespectador.com",
                "pagina12.com.ar", "efe.com", "europapress.es", "rtve.es", "heraldo.es", "lavozdegalicia.es"),
               hyphenate=True, pyphen_lang="es", quotes=("«", "»"),
               countries=("Mexico", "Spain", "Colombia", "Argentina")),
    "ar": Lang("ar", "Arabic", "العربية", "arabic", True, "20231101.ar", "arb_Arab",
               (".eg", ".sa", ".ae", ".ma", ".dz", ".iq", ".sy", ".jo", ".lb", ".kw", ".qa", ".om", ".tn", ".ly", ".sd", ".ye", ".bh", ".ps"),
               ("youm7.com", "ahram.org.eg", "almasryalyoum.com", "alarabiya.net", "aljazeera.net", "aawsat.com",
                "alkhaleej.ae", "albayan.ae", "alriyadh.com", "okaz.com.sa", "masrawy.com", "elwatannews.com",
                "shorouknews.com", "annahar.com", "hespress.com", "alittihad.ae", "alwatan.com.sa", "akhbarelyom.com",
                "alrai.com", "addustour.com", "aleqt.com", "sabq.org", "skynewsarabia.com", "bbc.com", "dw.com",
                "almanar.com.lb", "alquds.co.uk", "elbalad.news", "vetogate.com", "alghad.com"),
               native_digits="٠١٢٣٤٥٦٧٨٩", native_digit_prob=0.55,
               quotes=("«", "»"), countries=("Egypt", "Saudi Arabia", "UAE", "Morocco")),
    "fr": Lang("fr", "French", "Français", "latin", False, "20231101.fr", "fra_Latn",
               (".fr", ".be", ".ch", ".ca", ".sn", ".ci", ".ma", ".tn", ".dz", ".cm", ".lu"),
               ("lemonde.fr", "lefigaro.fr", "liberation.fr", "leparisien.fr", "ouest-france.fr", "20minutes.fr",
                "francetvinfo.fr", "lesechos.fr", "la-croix.com", "rfi.fr", "france24.com", "ledevoir.com",
                "lesoir.be", "lapresse.ca", "letemps.ch", "lepoint.fr", "lexpress.fr", "nouvelobs.com",
                "humanite.fr", "ladepeche.fr", "sudouest.fr", "lavoixdunord.fr", "midilibre.fr", "lalibre.be",
                "rtbf.be", "radio-canada.ca", "jeuneafrique.com", "europe1.fr", "bfmtv.com"),
               hyphenate=True, pyphen_lang="fr", quotes=("« ", " »"),
               countries=("France", "Canada", "Belgium", "Switzerland")),
    "bn": Lang("bn", "Bengali", "বাংলা", "bengali", False, "20231101.bn", "ben_Beng",
               (".bd", ".in"),
               ("prothomalo.com", "anandabazar.com", "bd-pratidin.com", "jugantor.com", "kalerkantho.com",
                "bdnews24.com", "banglanews24.com", "samakal.com", "ittefaq.com.bd", "dailyinqilab.com",
                "sangbadpratidin.in", "eisamay.com", "jagonews24.com", "dhakatimes24.com", "risingbd.com",
                "bangla.bdnews24.com", "dailynayadiganta.com", "manobkantha.com.bd", "somoynews.tv",
                "channel24bd.tv", "ekattor.tv", "bbc.com", "dw.com", "bartamanpatrika.com", "sangbad.net.bd"),
               native_digits="০১২৩৪৫৬৭৮৯", native_digit_prob=0.8,
               quotes=("‘", "’"), countries=("Bangladesh", "India")),
    "pt": Lang("pt", "Portuguese", "Português", "latin", False, "20231101.pt", "por_Latn",
               (".br", ".pt", ".ao", ".mz"),
               ("folha.uol.com.br", "g1.globo.com", "oglobo.globo.com", "estadao.com.br", "publico.pt", "dn.pt",
                "expresso.pt", "jn.pt", "uol.com.br", "terra.com.br", "correiodopovo.com.br", "gazetadopovo.com.br",
                "correiobraziliense.com.br", "em.com.br", "zh.clicrbs.com.br", "veja.abril.com.br", "cartacapital.com.br",
                "observador.pt", "sapo.pt", "rtp.pt", "cmjornal.pt", "agenciabrasil.ebc.com.br", "metropoles.com",
                "istoe.com.br", "valor.globo.com", "exame.com", "otempo.com.br"),
               hyphenate=True, pyphen_lang="pt_BR", quotes=("“", "”"),
               countries=("Brazil", "Portugal", "Angola", "Mozambique")),
    "ru": Lang("ru", "Russian", "Русский", "cyrillic", False, "20231101.ru", "rus_Cyrl",
               (".ru", ".by", ".kz", ".su", ".рф"),
               ("ria.ru", "tass.ru", "lenta.ru", "rbc.ru", "kommersant.ru", "iz.ru", "rg.ru", "gazeta.ru", "mk.ru",
                "kp.ru", "vedomosti.ru", "interfax.ru", "aif.ru", "fontanka.ru", "novayagazeta.ru", "vesti.ru",
                "1tv.ru", "ntv.ru", "regnum.ru", "vz.ru", "argumenti.ru", "pnp.ru", "sb.by", "tengrinews.kz",
                "nur.kz", "e1.ru", "ngs.ru", "ura.news", "newsru.com"),
               hyphenate=True, pyphen_lang="ru", quotes=("«", "»"),
               countries=("Russia", "Belarus", "Kazakhstan")),
    "id": Lang("id", "Indonesian", "Bahasa Indonesia", "latin", False, "20231101.id", "ind_Latn",
               (".id",),
               ("kompas.com", "detik.com", "tempo.co", "liputan6.com", "antaranews.com", "republika.co.id",
                "cnnindonesia.com", "tribunnews.com", "okezone.com", "sindonews.com", "merdeka.com", "suara.com",
                "jpnn.com", "kumparan.com", "kompas.id", "mediaindonesia.com", "beritasatu.com", "viva.co.id",
                "idntimes.com", "inews.id", "jawapos.com", "pikiran-rakyat.com", "bisnis.com", "kontan.co.id",
                "cnbcindonesia.com", "solopos.com", "harianjogja.com"),
               hyphenate=True, pyphen_lang="id_ID", quotes=("“", "”"),
               countries=("Indonesia",)),
    "ur": Lang("ur", "Urdu", "اردو", "arabic", True, "20231101.ur", "urd_Arab",
               (".pk",),
               ("jang.com.pk", "express.pk", "urdu.geo.tv", "dawnnews.tv", "nawaiwaqt.com.pk", "dunya.com.pk",
                "urdu.dunyanews.tv", "urdupoint.com", "humsub.com.pk", "92newshd.tv", "aaj.tv", "bbc.com",
                "dw.com", "independenturdu.com", "urdu.arynews.tv", "dailypakistan.com.pk", "roznama92news.com",
                "mashriqtv.pk", "nai-baat.pk", "dailyausaf.com", "jasarat.com", "urdu.samaa.tv", "khabrain.com",
                "naibaat.pk", "voaurdu.com"),
               native_digits="۰۱۲۳۴۵۶۷۸۹", native_digit_prob=0.35,
               quotes=("“", "”"), countries=("Pakistan", "India")),
    "de": Lang("de", "German", "Deutsch", "latin", False, "20231101.de", "deu_Latn",
               (".de", ".at", ".ch"),
               ("spiegel.de", "zeit.de", "faz.net", "sueddeutsche.de", "welt.de", "tagesschau.de", "focus.de",
                "stern.de", "taz.de", "handelsblatt.com", "n-tv.de", "derstandard.at", "nzz.ch", "merkur.de",
                "rp-online.de", "fr.de", "tagesspiegel.de", "morgenpost.de", "ksta.de", "abendblatt.de",
                "diepresse.com", "kurier.at", "tz.de", "bild.de", "deutschlandfunk.de", "mdr.de", "br.de", "ndr.de",
                "swr.de", "wdr.de", "zdf.de", "heise.de", "stuttgarter-zeitung.de", "badische-zeitung.de"),
               hyphenate=True, pyphen_lang="de_DE", quotes=("„", "“"),
               countries=("Germany", "Austria", "Switzerland")),
}

# Ranking order used everywhere (Ethnologue total speakers, excluding Chinese & English).
LANG_ORDER = ["hi", "es", "ar", "fr", "bn", "pt", "id", "ur", "ru", "de"]


def get(code: str) -> Lang:
    return LANGS[code]

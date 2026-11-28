"""Language registry.

Phase 1: the Top-10 non-Chinese, non-English languages by total speakers (Ethnologue, Wikipedia table).
Phase 2: + Simplified / Traditional Chinese, English, Japanese, Korean, Vietnamese, Thai, Turkish, Persian, Italian,
Polish and Dutch (selection logic in docs/languages.md).
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
    # phase 2
    segment: str = "space"    # word segmentation: space | cjk (character tokens + kinsoku) | thai (dictionary words)
    web_dataset: str = "HuggingFaceFW/fineweb-2"
    zh_script: str = ""       # hans | hant: keep only documents in this Chinese script (FineWeb-2 cmn_Hani mixes both)
    variants: tuple = ()      # regional variants ((tag, probability), ...), e.g. zh-Hant TW / HK, ko KR / KP
    zh_name: str = ""         # Chinese display name (portal)


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

LANGS.update({
    "zh-Hans": Lang("zh-Hans", "Simplified Chinese", "简体中文", "hans", False, "20231101.zh", "cmn_Hani",
                    (".cn", ".sg"),
                    ("people.com.cn", "xinhuanet.com", "news.cn", "chinadaily.com.cn", "gmw.cn", "cctv.com",
                     "chinanews.com.cn", "chinanews.com", "thepaper.cn", "ifeng.com", "sina.com.cn", "sohu.com",
                     "163.com", "qq.com", "caixin.com", "bjnews.com.cn", "infzm.com", "yicai.com", "jiemian.com",
                     "huanqiu.com", "cnr.cn", "ce.cn", "stdaily.com", "workercn.cn", "youth.cn", "eastday.com",
                     "ynet.com", "dzwww.com", "zaobao.com", "21jingji.com", "eeo.com.cn", "cyol.com"),
                    quotes=("“", "”"), countries=("China", "Singapore"), segment="cjk", zh_script="hans",
                    zh_name="简体中文"),
    "zh-Hant": Lang("zh-Hant", "Traditional Chinese", "繁體中文", "hant", False, "20231101.zh", "cmn_Hani",
                    (".tw", ".hk", ".mo"),
                    ("udn.com", "chinatimes.com", "ltn.com.tw", "cna.com.tw", "storm.mg", "ettoday.net", "setn.com",
                     "tvbs.com.tw", "nownews.com", "rti.org.tw", "pts.org.tw", "mingpao.com", "hk01.com",
                     "singtao.com", "hket.com", "on.cc", "rthk.hk", "cw.com.tw", "businessweekly.com.tw",
                     "thenewslens.com", "upmedia.mg", "mirrormedia.mg", "cts.com.tw", "ftvnews.com.tw",
                     "stheadline.com", "inmediahk.net", "commonhealth.com.tw", "gvm.com.tw", "taiwannews.com.tw"),
                    quotes=("「", "」"), countries=("Taiwan", "Hong Kong"), segment="cjk", zh_script="hant",
                    variants=(("TW", 0.7), ("HK", 0.3)), zh_name="繁体中文"),
    "en": Lang("en", "English", "English", "latin", False, "20231101.en", "sample-10BT",
               (".uk", ".us", ".au", ".ca", ".nz", ".ie", ".za", ".gov", ".edu"),
               ("bbc.co.uk", "bbc.com", "theguardian.com", "nytimes.com", "washingtonpost.com", "wsj.com",
                "reuters.com", "apnews.com", "cnn.com", "npr.org", "latimes.com", "usatoday.com", "independent.co.uk",
                "telegraph.co.uk", "thetimes.co.uk", "ft.com", "economist.com", "bloomberg.com", "abc.net.au",
                "smh.com.au", "theage.com.au", "cbc.ca", "theglobeandmail.com", "irishtimes.com", "nzherald.co.nz",
                "stuff.co.nz", "chicagotribune.com", "bostonglobe.com", "theatlantic.com", "politico.com", "sky.com"),
               hyphenate=True, pyphen_lang="en_US", quotes=("“", "”"),
               countries=("United States", "United Kingdom", "Canada", "Australia"),
               web_dataset="HuggingFaceFW/fineweb", zh_name="英文"),
    "ja": Lang("ja", "Japanese", "日本語", "japanese", False, "20231101.ja", "jpn_Jpan",
               (".jp",),
               ("asahi.com", "yomiuri.co.jp", "mainichi.jp", "nikkei.com", "sankei.com", "nhk.or.jp", "jiji.com",
                "kyodo.co.jp", "tokyo-np.co.jp", "chunichi.co.jp", "nishinippon.co.jp", "hokkaido-np.co.jp",
                "kahoku.news", "kobe-np.co.jp", "sponichi.co.jp", "nikkansports.com", "sanspo.com", "toyokeizai.net",
                "diamond.jp", "president.jp", "itmedia.co.jp", "impress.co.jp", "j-cast.com", "bunshun.jp",
                "news.yahoo.co.jp", "fnn.jp", "tbs.co.jp", "tv-asahi.co.jp", "ntv.co.jp", "shizushin.com"),
               quotes=("「", "」"), countries=("Japan",), segment="cjk", zh_name="日文"),
    "ko": Lang("ko", "Korean", "한국어", "hangul", False, "20231101.ko", "kor_Hang",
               (".kr",),
               ("chosun.com", "joongang.co.kr", "donga.com", "hani.co.kr", "khan.co.kr", "yna.co.kr", "hankyung.com",
                "mk.co.kr", "kmib.co.kr", "seoul.co.kr", "segye.com", "munhwa.com", "hankookilbo.com", "sedaily.com",
                "mt.co.kr", "edaily.co.kr", "newsis.com", "news1.kr", "ohmynews.com", "pressian.com", "kbs.co.kr",
                "imbc.com", "sbs.co.kr", "ytn.co.kr", "jtbc.co.kr", "nocutnews.co.kr", "etnews.com", "zdnet.co.kr",
                "heraldcorp.com", "asiae.co.kr"),
               quotes=("“", "”"), countries=("South Korea",), variants=(("KR", 0.95), ("KP", 0.05)),
               zh_name="韩文"),
    "vi": Lang("vi", "Vietnamese", "Tiếng Việt", "vietnamese", False, "20231101.vi", "vie_Latn",
               (".vn",),
               ("vnexpress.net", "tuoitre.vn", "thanhnien.vn", "dantri.com.vn", "vietnamnet.vn", "nhandan.vn",
                "laodong.vn", "tienphong.vn", "vov.vn", "vtv.vn", "zingnews.vn", "znews.vn", "24h.com.vn",
                "kenh14.vn", "cafef.vn", "cafebiz.vn", "vietnamplus.vn", "baochinhphu.vn", "qdnd.vn", "cand.com.vn",
                "plo.vn", "nld.com.vn", "sggp.org.vn", "baomoi.com", "soha.vn", "vneconomy.vn", "genk.vn"),
               quotes=("“", "”"), countries=("Vietnam",), zh_name="越南文"),
    "th": Lang("th", "Thai", "ไทย", "thai", False, "20231101.th", "tha_Thai",
               (".th",),
               ("thairath.co.th", "matichon.co.th", "khaosod.co.th", "dailynews.co.th", "bangkokbiznews.com",
                "prachachat.net", "posttoday.com", "thansettakij.com", "mgronline.com", "naewna.com", "sanook.com",
                "kapook.com", "pptvhd36.com", "thaipbs.or.th", "ch3plus.com", "ch7.com", "amarintv.com",
                "tnnthailand.com", "springnews.co.th", "workpointtoday.com", "thestandard.co", "thaipost.net",
                "siamrath.co.th", "komchadluek.net", "nationtv.tv", "voathai.com"),
               native_digits="๐๑๒๓๔๕๖๗๘๙", native_digit_prob=0.12,
               quotes=("“", "”"), countries=("Thailand",), segment="thai", zh_name="泰文"),
    "tr": Lang("tr", "Turkish", "Türkçe", "latin", False, "20231101.tr", "tur_Latn",
               (".tr",),
               ("hurriyet.com.tr", "milliyet.com.tr", "sabah.com.tr", "sozcu.com.tr", "cumhuriyet.com.tr",
                "haberturk.com", "ntv.com.tr", "cnnturk.com", "trthaber.com", "aa.com.tr", "star.com.tr",
                "yenisafak.com", "haber7.com", "ensonhaber.com", "takvim.com.tr", "posta.com.tr", "karar.com",
                "t24.com.tr", "bianet.org", "dunya.com", "ekonomim.com", "gazeteduvar.com.tr", "birgun.net",
                "evrensel.net", "mynet.com", "internethaber.com", "ahaber.com.tr"),
               quotes=("“", "”"), countries=("Türkiye",), zh_name="土耳其文"),
    "fa": Lang("fa", "Persian", "فارسی", "persian", True, "20231101.fa", "fas_Arab",
               (".ir", ".af"),
               ("hamshahrionline.ir", "irna.ir", "isna.ir", "farsnews.ir", "tasnimnews.com", "mehrnews.com",
                "khabaronline.ir", "entekhab.ir", "tabnak.ir", "asriran.com", "donya-e-eqtesad.com",
                "etemadonline.com", "shargdaily.com", "iribnews.ir", "yjc.ir", "mashreghnews.ir", "eghtesadonline.com",
                "ecoiran.com", "radiofarda.com", "iranintl.com", "independentpersian.com", "zoomit.ir", "digiato.com",
                "ilna.ir", "aftabnews.ir", "bbc.com", "dw.com"),
               native_digits="۰۱۲۳۴۵۶۷۸۹", native_digit_prob=0.85,
               quotes=("«", "»"), countries=("Iran", "Afghanistan"), zh_name="波斯文"),
    "it": Lang("it", "Italian", "Italiano", "latin", False, "20231101.it", "ita_Latn",
               (".it", ".ch", ".sm"),
               ("corriere.it", "repubblica.it", "lastampa.it", "ilsole24ore.com", "ilmessaggero.it", "ilgiornale.it",
                "ilfattoquotidiano.it", "ansa.it", "rainews.it", "tgcom24.mediaset.it", "avvenire.it", "ilpost.it",
                "ilsecoloxix.it", "gazzetta.it", "liberoquotidiano.it", "ilmattino.it", "lanazione.it",
                "ilrestodelcarlino.it", "ilgazzettino.it", "unionesarda.it", "quotidiano.net", "open.online",
                "today.it", "fanpage.it", "agi.it", "adnkronos.com", "rsi.ch", "swissinfo.ch"),
               hyphenate=True, pyphen_lang="it_IT", quotes=("«", "»"), countries=("Italy", "Switzerland"),
               zh_name="意大利文"),
    "pl": Lang("pl", "Polish", "Polski", "latin", False, "20231101.pl", "pol_Latn",
               (".pl",),
               ("gazeta.pl", "wyborcza.pl", "rp.pl", "onet.pl", "wp.pl", "interia.pl", "tvn24.pl", "polsatnews.pl",
                "money.pl", "bankier.pl", "businessinsider.com.pl", "newsweek.pl", "polityka.pl", "wprost.pl",
                "dziennik.pl", "gazetaprawna.pl", "se.pl", "fakt.pl", "natemat.pl", "pap.pl", "tvp.info",
                "polskieradio.pl", "rmf24.pl", "radiozet.pl", "dorzeczy.pl", "wnp.pl"),
               hyphenate=True, pyphen_lang="pl_PL", quotes=("„", "”"), countries=("Poland",), zh_name="波兰文"),
    "nl": Lang("nl", "Dutch", "Nederlands", "latin", False, "20231101.nl", "nld_Latn",
               (".nl", ".be", ".sr"),
               ("nos.nl", "nu.nl", "volkskrant.nl", "nrc.nl", "telegraaf.nl", "trouw.nl", "ad.nl", "parool.nl",
                "fd.nl", "rtlnieuws.nl", "nieuwsblad.be", "standaard.be", "hln.be", "demorgen.be", "vrt.be",
                "tijd.be", "gva.be", "hbvl.be", "omroepbrabant.nl", "dvhn.nl", "lc.nl", "tubantia.nl",
                "bndestem.nl", "pzc.nl", "ed.nl", "limburger.nl", "noordhollandsdagblad.nl"),
               hyphenate=True, pyphen_lang="nl_NL", quotes=("‘", "’"), countries=("Netherlands", "Belgium"),
               zh_name="荷兰文"),
})

_ZH = {"hi": "印地文", "es": "西班牙文", "ar": "阿拉伯文", "fr": "法文", "bn": "孟加拉文", "pt": "葡萄牙文",
       "id": "印尼文", "ur": "乌尔都文", "ru": "俄文", "de": "德文"}
for _c, _n in _ZH.items():
    object.__setattr__(LANGS[_c], "zh_name", _n)

# Phase-1 ranking order (Ethnologue total speakers, excluding Chinese & English) -- the default language set.
LANG_ORDER = ["hi", "es", "ar", "fr", "bn", "pt", "id", "ur", "ru", "de"]
# Phase-2 additions, in production priority order (CCG round 2, docs/ccg_phase2_synthesis.md).
LANG_ORDER_P2 = ["en", "zh-Hans", "ja", "vi", "ko", "zh-Hant", "tr", "fa", "th", "it", "pl", "nl"]
ALL_LANGS = LANG_ORDER + LANG_ORDER_P2
# Top-15 (>= 100k pages each for the open library) and Top-20 (production stress test).
TOP15 = ["en", "zh-Hans", "hi", "es", "ar", "fr", "bn", "pt", "id", "ur", "ru", "de", "ja", "vi", "ko"]
TOP20 = TOP15 + ["zh-Hant", "tr", "fa", "th", "it"]


def get(code: str) -> Lang:
    return LANGS[code]

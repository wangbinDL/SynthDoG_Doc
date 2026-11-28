"""Fetch per-language text corpora through the HF datasets-server REST API.

The cluster proxy reaches huggingface.co APIs but not the LFS CDN, so we sample rows
via /rows (random offsets, 100 rows per call) instead of downloading parquet shards.

Outputs (JSONL, one record per article/page):
  <out>/<lang>/wiki.jsonl   {"title","sections":[{"heading","paras":[...]}],"url"}
  <out>/<lang>/web.jsonl    {"url","domain","kind":"news|national","title","paras":[...],"date"}

Usage:
  python3 -m synthdog_doc.corpus_fetch --out /data/synthdog-doc/corpus --langs hi,es --wiki-calls 40 --web-calls 150
"""
import argparse
import json
import random
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .langs import LANG_ORDER, LANGS

API = "https://datasets-server.huggingface.co"
SCRIPT_RANGES = {
    "latin": [(0x41, 0x24F)],
    "cyrillic": [(0x400, 0x4FF)],
    "devanagari": [(0x900, 0x97F)],
    "bengali": [(0x980, 0x9FF)],
    "arabic": [(0x600, 0x6FF), (0x750, 0x77F), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF)],
}
_HAN = [(0x4E00, 0x9FFF), (0x3400, 0x4DBF), (0xF900, 0xFAFF), (0x3005, 0x3007)]
SCRIPT_RANGES.update({
    "hans": _HAN, "hant": _HAN,
    "japanese": _HAN + [(0x3040, 0x30FF), (0x31F0, 0x31FF)],
    "hangul": [(0xAC00, 0xD7AF), (0x1100, 0x11FF), (0x3130, 0x318F)],
    "thai": [(0x0E00, 0x0E7F)],
    "vietnamese": [(0x41, 0x24F), (0x1E00, 0x1EFF)],
    "persian": SCRIPT_RANGES["arabic"],
})
SCRIPT_RANGES["latin"] = [(0x41, 0x24F), (0x1E00, 0x1EFF)]
# Characters that differ between Simplified and Traditional Chinese (frequent pairs); a document is classified by
# which side dominates. FineWeb-2 / Wikipedia "zh" mix both scripts.
_SIMP = set("这个们国说对时会还来过为发经动应样么问题实现话钱铁门风飞马鸟鱼龙书车长东乐爱开关听见观让认识计设记论读写"
            "买卖头体学业产电线网级结组织给终统华万与专两严丰临举义乡乱争亚亲价众优传伤伦余侠儿党兰兴养内册军农冲决况"
            "净准几凤击刘则刚创删别剂剧劝办务劳势区医协单卫厂历压厅县参双变叶号叹后吗吓员听启响团园围图圆圣场坏块坚坛"
            "坏垄备复够头夹夺奋奖妇妈姜娱孙宁宝实审宪宫宽宾对寻导尔尘尝层岁岛岭币师帅带帮应库庙废开异弃张弹强归当录彻"
            "征径忆忧怀态总恋恶悬惊惯戏战户执扩扫扬扰抚抢护报担拟拥拦择挂挡挤挥损换据掳无旧时显晒晓暂术杀杂权条来杨极构"
            "枪柜标栏树样桥档检楼横欢欧歼毁气汇汉沟没泪泽洁浅测济浑涂润涛涨渊渐温湾湿满滚滞滤灭灯灵灾炉点炼烂热焕爱爷牵"
            "犹狱献环现玛理瓯电画畅疗疮痒监盖盘着矿码础确碍礼祷祸离种积称稳穷窃竞笔笋笼筑简粮紧纪约红纤纯纲纳纵纸纹线练"
            "组细织终绍经绑结绕绘给络绝统继绩绪续维综绿缓编缘缩缴网罗罚罢职联聪肠肤肾肿胀胁胜胶脉脑脚脱腊舰艺节芦苏苹范"
            "荐药莱获营萝蒋虑虽虾蚀蛮补衬袭见规视览觉触计订认讨让训议讯记讲许论设访证评识诉词译试诗诚话诞询该详语误说请"
            "诸读课谁调谈谋谓谢谣谱贝负贡财责贤败货质贩贪贫购贯贱贴贵贷贸费贺资赋赌赏赔赖赚赛赞赠赢赶趋跃践踪轨轩转轮软轰"
            "轻载较辅辆辈辉辑输辖边辽达迁过迈运还这进远违连迟适选递逻遗邓邮邻郑酱释里鉴针钓钟钢钥钦钱钻铁铃铅铜银铸铺链销"
            "锁锅锋错锡锦键镇镜长门闪闭问闲间闹闻阀阁阅阐队阳阴阵阶际陆陈险随隐难雾霁静韩页顶项顺须顾顿预领颇频颗题颜额"
            "风飘飞饭饮饰饱饼馆首驱驶驻驾验骑骗骚骤鱼鲁鲜鸟鸡鸣鸿鹅黄齐齿龄龙龟")
_TRAD = set("這個們國說對時會還來過為發經動應樣麼問題實現話錢鐵門風飛馬鳥魚龍書車長東樂愛開關聽見觀讓認識計設記論讀寫"
            "買賣頭體學業產電線網級結組織給終統華萬與專兩嚴豐臨舉義鄉亂爭亞親價眾優傳傷倫餘俠兒黨蘭興養內冊軍農衝決況"
            "淨準幾鳳擊劉則剛創刪別劑劇勸辦務勞勢區醫協單衛廠歷壓廳縣參雙變葉號嘆後嗎嚇員啟響團園圍圖圓聖場壞塊堅壇"
            "壟備復夠夾奪奮獎婦媽薑娛孫寧寶審憲宮寬賓尋導爾塵嘗層歲島嶺幣師帥帶幫庫廟廢異棄張彈強歸當錄徹"
            "徵徑憶憂懷態總戀惡懸驚慣戲戰戶執擴掃揚擾撫搶護報擔擬擁攔擇掛擋擠揮損換據擄無舊顯曬曉暫術殺雜權條楊極構"
            "槍櫃標欄樹橋檔檢樓橫歡歐殲毀氣匯漢溝沒淚澤潔淺測濟渾塗潤濤漲淵漸溫灣濕滿滾滯濾滅燈靈災爐點煉爛熱煥爺牽"
            "猶獄獻環瑪理甌畫暢療瘡癢監蓋盤著礦碼礎確礙禮禱禍離種積稱穩窮竊競筆筍籠築簡糧緊紀約紅纖純綱納縱紙紋練"
            "細紹綁繞繪絡絕繼績緒續維綜綠緩編緣縮繳羅罰罷職聯聰腸膚腎腫脹脅勝膠脈腦腳脫臘艦藝節蘆蘇蘋範"
            "薦藥萊獲營蘿蔣慮雖蝦蝕蠻補襯襲規視覽覺觸訂討訓議訊講許設訪證評訴詞譯試詩誠誕詢該詳語誤請"
            "諸課誰調談謀謂謝謠譜貝負貢財責賢敗貨質販貪貧購貫賤貼貴貸貿費賀資賦賭賞賠賴賺賽贊贈贏趕趨躍踐蹤軌軒轉輪軟轟"
            "輕載較輔輛輩輝輯輸轄邊遼達遷邁運進遠違連遲適選遞邏遺鄧郵鄰鄭醬釋裡鑒針釣鐘鋼鑰欽鑽鈴鉛銅銀鑄鋪鏈銷"
            "鎖鍋鋒錯錫錦鍵鎮鏡閃閉閒間鬧聞閥閣閱闡隊陽陰陣階際陸陳險隨隱難霧霽靜韓頁頂項順須顧頓預領頗頻顆顏額"
            "飄飯飲飾飽餅館驅駛駐駕驗騎騙騷驟魯鮮雞鳴鴻鵝黃齊齒齡龜")


def zh_variant(text):
    s = sum(1 for c in text if c in _SIMP)
    t = sum(1 for c in text if c in _TRAD)
    if s + t < 8:
        return None
    return "hans" if s >= 4 * t else ("hant" if t >= 4 * s else None)


def http_json(url, timeout=60, tries=6):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "synthdog-doc-research/0.1"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(min(60, 2 ** i + random.random()))
    raise RuntimeError(f"failed {url}: {last}")


def num_rows(dataset, config):
    q = urllib.parse.urlencode({"dataset": dataset, "config": config, "split": "train", "offset": 0, "length": 1})
    return http_json(f"{API}/rows?{q}")["num_rows_total"]


def rows(dataset, config, offset, length=100):
    q = urllib.parse.urlencode({"dataset": dataset, "config": config, "split": "train",
                                "offset": offset, "length": length})
    return [r["row"] for r in http_json(f"{API}/rows?{q}")["rows"]]


def script_ratio(text, script):
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    rng = SCRIPT_RANGES[script]
    hit = sum(1 for c in letters if any(a <= ord(c) <= b for a, b in rng))
    return hit / len(letters)


def clean_para(p):
    p = unicodedata.normalize("NFC", p).strip()
    p = re.sub(r"\s+", " ", p)
    return p


def wiki_sections(text, script):
    """Split a Wikipedia plaintext article into (heading, paragraphs) sections."""
    lines = [clean_para(x) for x in text.split("\n")]
    sections, cur = [], {"heading": "", "paras": []}
    for ln in lines:
        if not ln:
            continue
        is_heading = len(ln) < 80 and not re.search(r"[.!?।۔؟。！？]$", ln) and len(ln.split()) <= 10
        if is_heading:
            if cur["paras"]:
                sections.append(cur)
            cur = {"heading": ln, "paras": []}
        elif len(ln) >= 40 and script_ratio(ln, script) >= 0.6:
            cur["paras"].append(ln)
    if cur["paras"]:
        sections.append(cur)
    # drop typical tail sections (references, see also...) by keeping sections with real prose only
    return [s for s in sections if sum(len(p) for p in s["paras"]) >= 120]


def domain_of(url):
    try:
        return urllib.parse.urlparse(url).netloc.lower().split(":")[0].removeprefix("www.")
    except Exception:  # noqa: BLE001
        return ""


def classify_web(url, lang):
    d = domain_of(url)
    for nd in lang.news_domains:
        if d == nd or d.endswith("." + nd):
            return d, "news"
    for t in lang.country_tlds:
        if d.endswith(t):
            return d, "national"
    return d, None


def fetch_wiki(lang, out_dir, calls, workers, seed):
    cfg = lang.wiki_config
    try:
        n = num_rows("wikimedia/wikipedia", cfg)
    except Exception as e:  # noqa: BLE001
        print(f"[{lang.code}] wiki num_rows failed: {e}", file=sys.stderr, flush=True)
        return 0
    rnd = random.Random(seed)
    offsets = sorted({rnd.randrange(0, max(1, n - 100)) for _ in range(calls)})
    out = open(out_dir / "wiki.jsonl", "w", encoding="utf-8")
    kept = 0
    with ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(rows, "wikimedia/wikipedia", cfg, o): o for o in offsets}
        for f in as_completed(futs):
            try:
                rs = f.result()
            except Exception as e:  # noqa: BLE001
                print(f"[{lang.code}] wiki offset {futs[f]} failed: {e}", file=sys.stderr)
                continue
            for r in rs:
                if lang.zh_script and zh_variant(r.get("text", "")[:3000]) != lang.zh_script:
                    continue
                secs = wiki_sections(r.get("text", ""), lang.script)
                if sum(len(p) for s in secs for p in s["paras"]) < 600:
                    continue
                out.write(json.dumps({"title": clean_para(r.get("title", "")), "url": r.get("url", ""),
                                      "sections": secs}, ensure_ascii=False) + "\n")
                kept += 1
    out.close()
    print(f"[{lang.code}] wiki rows_total={n} calls={len(offsets)} kept={kept}", flush=True)
    return kept


WEB_DATASET = "HuggingFaceFW/fineweb-2"
WEB_CONFIG = {}   # lang -> config override (e.g. when the fineweb-2 config is unavailable server-side)
WEB_DATASET_OVERRIDE = False   # True when --web-dataset forces one dataset for all languages


def fetch_web(lang, out_dir, calls, workers, seed):
    cfg = WEB_CONFIG.get(lang.code, lang.fineweb_config)
    ds = WEB_DATASET if WEB_DATASET_OVERRIDE else lang.web_dataset
    try:
        n = num_rows(ds, cfg)
    except Exception as e:  # noqa: BLE001
        print(f"[{lang.code}] web num_rows failed: {e}", file=sys.stderr, flush=True)
        return {}
    rnd = random.Random(seed + 1)
    offsets = sorted({rnd.randrange(0, max(1, n - 100)) for _ in range(calls)})
    out = open(out_dir / "web.jsonl", "w", encoding="utf-8")
    stats = {"rows": 0, "news": 0, "national": 0}
    with ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(rows, ds, cfg, o): o for o in offsets}
        for f in as_completed(futs):
            try:
                rs = f.result()
            except Exception as e:  # noqa: BLE001
                print(f"[{lang.code}] web offset {futs[f]} failed: {e}", file=sys.stderr)
                continue
            for r in rs:
                stats["rows"] += 1
                d, kind = classify_web(r.get("url", ""), lang)
                if not kind or (r.get("language_score") if "language_score" in r else 1.0) < 0.75:
                    continue
                if lang.zh_script and zh_variant((r.get("text") or "")[:3000]) != lang.zh_script:
                    continue
                lines = [clean_para(x) for x in (r.get("text") or "").split("\n")]
                lines = [x for x in lines if x]
                if not lines:
                    continue
                title = lines[0] if len(lines[0]) <= 160 else ""
                paras = [x for x in lines[1 if title else 0:]
                         if len(x) >= 60 and script_ratio(x, lang.script) >= 0.6]
                if sum(len(p) for p in paras) < 400:
                    continue
                stats[kind] += 1
                out.write(json.dumps({"url": r.get("url"), "domain": d, "kind": kind, "title": title,
                                      "paras": paras, "date": r.get("date")}, ensure_ascii=False) + "\n")
    out.close()
    print(f"[{lang.code}] web rows_total={n} calls={len(offsets)} {stats}", flush=True)
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--langs", default=",".join(LANG_ORDER))
    ap.add_argument("--wiki-calls", type=int, default=40)
    ap.add_argument("--web-calls", type=int, default=150)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--seed", type=int, default=20261127)
    ap.add_argument("--skip-wiki", action="store_true")
    ap.add_argument("--skip-web", action="store_true")
    ap.add_argument("--web-dataset", default=None, help="override, e.g. allenai/c4")
    ap.add_argument("--web-config", default=None, help="override config for all langs, e.g. es")
    a = ap.parse_args()
    global WEB_DATASET, WEB_DATASET_OVERRIDE
    if a.web_dataset:
        WEB_DATASET = a.web_dataset
        WEB_DATASET_OVERRIDE = True
    if a.web_config:
        for code in a.langs.split(","):
            WEB_CONFIG[code] = a.web_config
    for code in a.langs.split(","):
        lang = LANGS[code]
        od = Path(a.out) / code
        od.mkdir(parents=True, exist_ok=True)
        if not a.skip_wiki:
            fetch_wiki(lang, od, a.wiki_calls, a.workers, a.seed)
        if not a.skip_web:
            fetch_web(lang, od, a.web_calls, a.workers, a.seed)


if __name__ == "__main__":
    main()

"""Headless-Chromium renderer: PageSpec -> (PNG bytes, raw ground truth from the in-page engine)."""
import asyncio
import json
import math
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from .textkit import esc

ASSETS = Path(__file__).resolve().parent / "assets"
KATEX_DIR = ASSETS / "katex"

BASE_CSS = """
html,body{margin:0;padding:0;background:#ffffff;overflow:hidden;}
#page{position:absolute;left:0;top:0;overflow:hidden;box-sizing:border-box;background:var(--paper,#fff);color:var(--ink,#111);
  font-kerning:normal;font-synthesis:none;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility;}
#page *{box-sizing:border-box;}
.zone{position:absolute;}
.cols{display:flex;flex-direction:row;width:100%;height:100%;}
.col{flex:1 1 0;min-width:0;height:100%;overflow:hidden;display:flex;flex-direction:column;}
.col>*{flex:0 0 auto;}
.col>.fbottom{margin-top:auto;}
.crule{flex:0 0 0;width:0;align-self:stretch;}
.src{display:none;}
p{margin:0;}
.split-head{text-align-last:justify;}
.cont{text-indent:0!important;}
.m{display:inline-block;unicode-bidi:isolate;direction:ltr;}
.katex{direction:ltr;unicode-bidi:isolate;}
.shrunk img,.shrunk svg{max-height:calc(var(--h0,9999px)*var(--shrink,1));}
.b{font-weight:var(--bw,700);} .i{font-style:italic;} .bi{font-weight:var(--bw,700);font-style:italic;}
.u{text-decoration:underline;} .code{font-family:var(--f-mono);}
.fontwarm{position:fixed;left:0;top:0;width:1px;height:1px;overflow:hidden;opacity:0;pointer-events:none;}
.katex{font-size:1.05em;}
/* phase 2: space-less scripts. Tokens never break inside (the line breaker may only cut between tokens, which keeps
   one rectangle per token for the ground truth); CJK uses strict kinsoku and inter-character justification. */
#page:lang(zh) .w,#page:lang(ja) .w,#page:lang(th) .w{white-space:nowrap;}
#page:lang(zh),#page:lang(ja){line-break:strict;text-justify:inter-character;font-feature-settings:"palt" 0;}
#page:lang(ko){word-break:keep-all;}
#page:lang(th){line-break:auto;}
"""


@dataclass
class PageSpec:
    doc_type: str
    lang: str
    width_in: float
    height_in: float
    dpi: float
    body: str                      # inner HTML of #page
    css: str = ""                  # page-specific CSS
    font_css: str = ""             # @font-face rules
    font_warm: list = field(default_factory=list)   # ["700 italic 16px 'PT Serif'", ...]
    rtl: bool = False
    page_style: str = ""           # extra inline style for #page
    meta: dict = field(default_factory=dict)

    @property
    def css_w(self):
        return self.width_in * 96.0

    @property
    def css_h(self):
        return self.height_in * 96.0

    @property
    def dpr(self):
        return self.dpi / 96.0

    @property
    def px_size(self):
        return round(self.css_w * self.dpr), round(self.css_h * self.dpr)


def assemble_html(spec: PageSpec) -> str:
    d = "rtl" if spec.rtl else "ltr"
    return f"""<!doctype html><html lang="{spec.lang}" dir="{d}"><head><meta charset="utf-8">
<link rel="stylesheet" href="file://{KATEX_DIR}/katex.min.css">
<style>{spec.font_css}</style>
<style>{BASE_CSS}</style>
<style>#page{{width:{spec.css_w:.3f}px;height:{spec.css_h:.3f}px;}}
{spec.css}</style>
</head><body>
<div id="page" lang="{spec.lang}" dir="{d}" style="{spec.page_style}">{spec.body}</div>
<script src="file://{KATEX_DIR}/katex.min.js"></script>
<script src="file://{ASSETS}/engine.js"></script>
</body></html>"""


WARM_JS = """async (specs) => {
  await Promise.all(specs.map(s => document.fonts.load(s[0], s[1]).catch(() => null)));
  // KaTeX fonts
  const k = document.createElement('span'); k.className = 'fontwarm';
  document.body.appendChild(k);
  try { katex.render('x^2+\\\\int_0^1\\\\sum_{i}\\\\frac{a}{b}\\\\mathbb{R}\\\\mathcal{L}\\\\alpha', k); } catch (e) {}
  await document.fonts.ready;
  k.remove();
  return Array.from(document.fonts).filter(f => f.status === 'error').map(f => f.family);
}"""


class Renderer:
    """One Chromium process; render pages concurrently with an asyncio semaphore."""

    def __init__(self, concurrency=2, tmpdir=None, timeout_ms=90000, shot="png"):
        self.concurrency = concurrency
        self.shot = shot          # png (lossless, default) | jpeg (faster to encode / decode)
        self.pages = 0
        self.tmpdir = Path(tmpdir or tempfile.mkdtemp(prefix="sdd_r_"))
        self.tmpdir.mkdir(parents=True, exist_ok=True)
        self.timeout_ms = timeout_ms
        self._pw = None
        self._browser = None
        self._sem = None

    async def __aenter__(self):
        from playwright.async_api import async_playwright
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            args=["--allow-file-access-from-files", "--disable-web-security", "--font-render-hinting=none",
                  "--disable-gpu", "--no-sandbox"])
        self._sem = asyncio.Semaphore(self.concurrency)
        return self

    async def __aexit__(self, *a):
        try:
            await self._browser.close()
        finally:
            await self._pw.stop()

    async def render(self, spec: PageSpec, name: str, keep_html=False):
        async with self._sem:
            t0 = time.time()
            html_path = self.tmpdir / f"{name}.html"
            html_path.write_text(assemble_html(spec), encoding="utf-8")
            vw, vh = math.ceil(spec.css_w), math.ceil(spec.css_h)
            ctx = await self._browser.new_context(viewport={"width": vw, "height": vh},
                                                  device_scale_factor=spec.dpr)
            page = await ctx.new_page()
            page.set_default_timeout(self.timeout_ms)
            tm = {}
            try:
                t1 = time.time()
                await page.goto(f"file://{html_path}", wait_until="load")
                t2 = time.time()
                font_err = await page.evaluate(WARM_JS, spec.font_warm)
                t3 = time.time()
                lay = await page.evaluate("SDD.layout()")
                await page.evaluate("document.fonts.ready.then(() => 1)")
                t4 = time.time()
                gt = await page.evaluate("SDD.extract()")
                box = await page.evaluate("(() => { const r = document.getElementById('page')"
                                          ".getBoundingClientRect(); return [r.left + window.scrollX, "
                                          "r.top + window.scrollY, r.width, r.height]; })()")
                t5 = time.time()
                png = await page.screenshot(type=self.shot, clip={"x": box[0], "y": box[1], "width": box[2],
                                                                  "height": box[3]},
                                            **({"quality": 95} if self.shot == "jpeg" else {}))
                t6 = time.time()
                tm = {"open": round(t1 - t0, 3), "goto": round(t2 - t1, 3), "fonts": round(t3 - t2, 3),
                      "layout": round(t4 - t3, 3), "extract": round(t5 - t4, 3), "screenshot": round(t6 - t5, 3)}
            finally:
                await ctx.close()
                if not keep_html:
                    try:
                        os.remove(html_path)
                    except OSError:
                        pass
            gt["layout"] = lay
            gt["font_errors"] = font_err
            gt["render_sec"] = round(time.time() - t0, 3)
            gt["timing"] = tm
            self.pages += 1
            return png, gt


def run_sync(specs_named, concurrency=2, keep_html=False):
    """Convenience: render [(name, spec)] in one browser; returns list of (name, png, gt)."""
    async def _go():
        out = []
        async with Renderer(concurrency=concurrency) as r:
            tasks = [r.render(s, n, keep_html=keep_html) for n, s in specs_named]
            res = await asyncio.gather(*tasks, return_exceptions=True)
            for (n, _), x in zip(specs_named, res):
                out.append((n, x))
        return out
    return asyncio.run(_go())

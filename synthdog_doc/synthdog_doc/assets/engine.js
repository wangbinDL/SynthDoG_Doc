/* SynthDoG-Doc in-page layout + ground-truth engine.
 *
 * Contract with the Python page builders:
 *  - #page is the physical page (CSS px, 96 px/in); everything annotated lives inside it.
 *  - Annotated blocks carry data-cat (ODB category) and data-bid (block id).
 *  - Text inside annotated blocks is tokenised into <span class="w"> (word + trailing space)
 *    and <span class="m" data-latex> (inline math). This keeps splitting and line extraction exact.
 *  - Flow zones: <div class="zone flow" data-cols data-gap data-rule data-zorder>
 *      <div class="src"> ...ordered blocks... </div></div>
 *    Blocks with data-split="1" may be split across columns at token boundaries.
 *    Blocks with data-kwn="1" (headings) are kept with the next block.
 *    Blocks with data-col="i" data-place="top|bottom" are column floats placed before text.
 */
(function () {
  'use strict';
  const SDD = (window.SDD = { log: [], dropped: 0, splits: 0, mathErrors: 0 });

  const TEXT_CATS = new Set(['title', 'text_block', 'header', 'footer', 'page_number', 'figure_caption',
    'table_caption', 'table_footnote', 'figure_footnote', 'page_footnote', 'reference', 'code_txt',
    'equation_caption', 'abandon', 'list_group']);
  const SHY = /[\u00AD\u2066-\u2069\u200E\u200F]/g;

  // ---------------------------------------------------------------- math
  SDD.renderMath = function (root) {
    (root || document).querySelectorAll('[data-latex]').forEach((el) => {
      if (el.dataset.mathDone) return;
      try {
        katex.render(el.dataset.latex, el, {
          displayMode: el.dataset.display === '1', throwOnError: true, strict: 'ignore', output: 'html',
        });
        el.dataset.mathDone = '1';
      } catch (e) {
        el.dataset.mathError = String((e && e.message) || e).slice(0, 160);
        SDD.mathErrors++;
      }
    });
    // drop blocks whose math failed (display) or the failed inline token
    document.querySelectorAll('[data-math-error]').forEach((el) => {
      const blk = el.closest('[data-cat="equation_isolated"]');
      if (blk) {
        const grp = blk.closest('.eqrow') || blk;
        grp.remove();
      } else el.remove();
    });
  };

  // ---------------------------------------------------------------- geometry helpers
  function bottomOf(el) {
    let b = -Infinity;
    for (const c of el.children) {
      const r = c.getBoundingClientRect();
      if (r.height > 0 || r.width > 0) {
        const mb = parseFloat(getComputedStyle(c).marginBottom) || 0;
        b = Math.max(b, r.bottom + Math.max(0, mb) * 0);
      }
    }
    return b;
  }
  function fits(box) {
    const r = box.getBoundingClientRect();
    if (!box.children.length) return true;
    // a 1-3px horizontal overflow (inline math / last glyph of a justified line) is invisible: do not treat it
    // as "does not fit", which used to split a paragraph after 3 lines and leave the column empty
    return bottomOf(box) <= r.bottom + 0.5 && box.scrollWidth <= box.clientWidth + Math.max(3, box.clientWidth * 0.015);
  }
  function lineHeightPx(el) {
    const cs = getComputedStyle(el);
    const lh = parseFloat(cs.lineHeight);
    return Number.isFinite(lh) ? lh : parseFloat(cs.fontSize) * 1.25;
  }
  function nLines(el) {
    const h = el.getBoundingClientRect().height;
    return Math.round(h / lineHeightPx(el));
  }

  // ---------------------------------------------------------------- paragraph split
  function cloneShell(p) {
    const t = p.cloneNode(false);
    t.classList.add('cont');
    t.classList.remove('split-head', 'first', 'dropcap');
    t.dataset.bid = (p.dataset.bid || 'b') + 'c';
    t.dataset.contOf = p.dataset.bid || '';
    return t;
  }
  // Move tokens from the end of p into tail until p fits in col. Returns tail or null.
  function splitPara(p, col, minHead, minTail) {
    const toks = Array.from(p.childNodes);
    const n = toks.length;
    if (n < 4) return null;
    const tail = cloneShell(p);
    const setK = (k) => {
      while (p.childNodes.length > k) tail.insertBefore(p.lastChild, tail.firstChild);
      while (p.childNodes.length < k && tail.firstChild) p.appendChild(tail.firstChild);
    };
    let lo = 0, hi = n;
    while (lo < hi) {
      const mid = Math.ceil((lo + hi) / 2);
      setK(mid);
      if (fits(col)) lo = mid; else hi = mid - 1;
    }
    setK(lo);
    if (lo === 0 || lo === n) { setK(n); return null; }
    // widow control: a tail of 1-3 tokens would sit alone at the top of the next column; move the head's last
    // line down with it
    if (n - lo <= 3 && lo > 8) {
      const topOf = (nd) => (nd && nd.nodeType === 1 ? nd.getBoundingClientRect().top : null);
      let lastTop = null;
      for (let i = lo - 1; i >= 0 && lastTop === null; i--) lastTop = topOf(p.childNodes[i]);
      let k = lo;
      while (k > 1) {
        const t = topOf(p.childNodes[k - 1]);
        if (t !== null && Math.abs(t - lastTop) > 2) break;
        k--;
      }
      if (k < lo && k > 0) setK(k);
    }
    // avoid splitting inside a trailing <br>
    if (nLines(p) < minHead) { setK(n); return null; }
    // widow control: tail needs >= minTail lines; measure by temporarily attaching
    p.classList.add('split-head');
    SDD.splits++;
    return tail;
  }

  // ---------------------------------------------------------------- flow zones
  function makeColumns(zone) {
    const n = Math.max(1, parseInt(zone.dataset.cols || '1', 10));
    const wrap = document.createElement('div');
    wrap.className = 'cols';
    wrap.style.columnGap = '0';
    const gap = zone.dataset.gap || '1em';
    wrap.style.gap = gap;
    const cols = [];
    for (let i = 0; i < n; i++) {
      if (i > 0 && zone.dataset.rule && zone.dataset.rule !== '0') {
        const r = document.createElement('div');
        r.className = 'crule';
        r.style.borderInlineStart = zone.dataset.rule;
        wrap.appendChild(r);
      }
      const c = document.createElement('div');
      c.className = 'col';
      c.dataset.ci = String(i);
      cols.push(c);
      wrap.appendChild(c);
    }
    if (zone.dataset.colh) wrap.style.height = zone.dataset.colh + 'px';
    zone.appendChild(wrap);
    return cols;
  }

  SDD.flowZone = function (zone) {
    const src = zone.querySelector(':scope > .src');
    if (!src) return;
    const cols = makeColumns(zone);
    const blocks = Array.from(src.children);
    // column floats first
    const floats = blocks.filter((b) => b.dataset.place);
    floats.forEach((f) => {
      const ci = Math.min(cols.length - 1, parseInt(f.dataset.col || '0', 10));
      if (f.dataset.place === 'bottom') f.classList.add('fbottom');
      cols[ci].appendChild(f);
      SDD.fitText(f);
      SDD.fitOptions(f);
      if (!fits(cols[ci])) { f.remove(); SDD.dropped++; }
    });
    const flow = blocks.filter((b) => !b.dataset.place);
    const minHead = parseInt(zone.dataset.minhead || '2', 10);
    const dropped0 = SDD.dropped;
    const pending = [];
    let stopRest = false;
    let ci = 0;
    const insertBeforeBottom = (col, b) => {
      const fb = col.querySelector(':scope > .fbottom');
      if (fb) col.insertBefore(b, fb); else col.appendChild(b);
    };
    for (let bi = 0; bi < flow.length; bi++) {
      const b = flow[bi];
      const filler = b.dataset.filler === '1';
      if (stopRest) { SDD.dropped++; continue; }   // exams: never print question 14 after a missing question 13
      // filler briefs only use leftover space of a story that fitted completely; never counted as dropped
      if (filler && (SDD.dropped > dropped0 || ci >= cols.length)) { b.remove(); continue; }
      if (ci >= cols.length) { SDD.dropped++; continue; }
      const col = cols[ci];
      insertBeforeBottom(col, b);
      SDD.fitText(b);
      SDD.fitOptions(b);
      SDD.fitEquations(b);
      SDD.fitTables(b);
      if (!b.isConnected) continue;
      if (fits(col)) continue;
      // LaTeX-like float deferral: a figure/table that does not fit is held back and placed at the top of the
      // next column, while the following text keeps filling the current column.
      if (b.dataset.float === '1' && !b.dataset.deferred && col.querySelectorAll(':scope > :not(.fbottom)').length > 1 &&
          ci + 1 < cols.length) {
        b.remove();
        b.dataset.deferred = '1';
        pending.push(b);
        continue;
      }
      // ... and in the last column it goes to the next page while the following text keeps filling this one
      if (b.dataset.float === '1' && ci + 1 >= cols.length && col.querySelectorAll(':scope > :not(.fbottom)').length > 1) {
        b.remove();
        SDD.dropped++;
        SDD.floatsOut = (SDD.floatsOut || 0) + 1;
        continue;
      }
      const isFirst = col.querySelectorAll(':scope > :not(.fbottom)').length === 1 &&
        !col.querySelector(':scope > [data-place="top"]');
      if (b.dataset.split === '1') {
        const tail = splitPara(b, col, isFirst ? 1 : minHead, 1);
        if (tail) {
          flow.splice(bi + 1, 0, tail);
          ci++;
          if (pending.length && ci < cols.length) { flow.splice(bi + 1, 0, ...pending); pending.length = 0; }
          continue;
        }
      }
      // cannot place here: move to next column (with keep-with-next predecessor)
      b.remove();
      if (zone.dataset.compact === '1' && !isFirst && ci + 1 >= cols.length) {
        // last column of the page: first compact the answer space, then lay the question out part by part,
        // so its beginning still fits here instead of the rest of the page staying empty
        if (b.querySelector('[data-grow]') && !b.dataset.compacted) {
          b.dataset.compacted = '1';
          b.querySelectorAll('[data-grow]').forEach((g) => {
            const st = parseFloat(g.dataset.grow) || 12;
            g.style.height = Math.max(st, 6) + 'px';
          });
          bi--; continue;
        }
        if ((b.classList.contains('qwrap') || b.classList.contains('secwrap')) && !b.dataset.unwrapped) {
          const parts = [];
          Array.from(b.children).forEach((k) => {
            if (k.classList.contains('passage')) Array.from(k.children).forEach((p) => parts.push(p));
            else parts.push(k);
          });
          parts.forEach((k) => { if (!k.classList.contains('qwrap')) k.dataset.unwrapped = '1'; });
          flow.splice(bi + 1, 0, ...parts);
          SDD.unwrapped = (SDD.unwrapped || 0) + 1;
          continue;
        }
      }
      if (isFirst) {
        // block does not fit even in an empty column: shrink images once, else drop
        if (b.dataset.shrink === '1' && !b.dataset.shrunk) {
          b.dataset.shrunk = '1';
          b.style.setProperty('--shrink', '0.6');
          b.classList.add('shrunk');
          bi--; continue;
        }
        // answer space can be compacted to a single line before giving up on a question
        if (zone.dataset.compact === '1' && b.querySelector('[data-grow]') && !b.dataset.compacted) {
          b.dataset.compacted = '1';
          b.querySelectorAll('[data-grow]').forEach((g) => {
            const st = parseFloat(g.dataset.grow) || 12;
            g.style.height = Math.max(st, 6) + 'px';
          });
          bi--; continue;
        }
        // a question taller than a whole column is laid out part by part (its passage can then break)
        if (zone.dataset.compact === '1' && (b.classList.contains('qwrap') || b.classList.contains('secwrap')) &&
            !b.dataset.unwrapped) {
          const parts = [];
          Array.from(b.children).forEach((k) => {
            if (k.classList.contains('passage')) Array.from(k.children).forEach((p) => parts.push(p));
            else parts.push(k);
          });
          // nested question blocks keep the right to be unwrapped themselves
          parts.forEach((k) => { if (!k.classList.contains('qwrap')) k.dataset.unwrapped = '1'; });
          flow.splice(bi + 1, 0, ...parts);
          SDD.unwrapped = (SDD.unwrapped || 0) + 1;
          continue;
        }
        if (!filler) SDD.dropped++;
        if (zone.dataset.stopondrop === '1' && !filler) { stopRest = true; }
        continue;
      }
      const prev = Array.from(col.querySelectorAll(':scope > :not(.fbottom)')).pop();
      if (prev && prev.dataset.kwn === '1') { prev.remove(); flow.splice(bi, 0, prev); bi--; }
      bi--; ci++;
      if (pending.length && ci < cols.length) { flow.splice(bi + 1, 0, ...pending); pending.length = 0; }
    }
    src.remove();
    // a filler heading must not end a column without its text
    cols.forEach((col) => {
      const kids = Array.from(col.children).filter((c) => !c.classList.contains('fbottom'));
      const lastKid = kids[kids.length - 1];
      if (lastKid && lastKid.dataset.filler === '1' && lastKid.dataset.kwn === '1') lastKid.remove();
    });
    // Jump line ("continued on page N"): only when the story did not fit; trim the last paragraph to make room.
    if (zone.dataset.jump && SDD.dropped > dropped0 && zone.querySelector('.col > p:not(.jump)')) {
      const lastCol = cols[cols.length - 1];
      const j = document.createElement('p');
      j.className = 'jump';
      j.dataset.cat = 'text_block';
      j.dataset.bid = 'jump' + Math.floor(Math.random() * 1e9);
      j.innerHTML = zone.dataset.jump;
      lastCol.appendChild(j);
      let guard = 0;
      while (!fits(lastCol) && guard++ < 400) {
        const prev = j.previousElementSibling;
        if (!prev) break;
        if (prev.querySelectorAll(':scope > .w').length > 3) {
          prev.removeChild(prev.lastChild);
          prev.classList.remove('split-head');
        } else prev.remove();
      }
      if (!fits(lastCol)) j.remove();
    }
    // Vertical justification (exam papers): spread free space over the gaps between items.
    if (zone.dataset.vjustify) {
      const vmax = parseFloat(zone.dataset.vjmax || '30');
      cols.forEach((col) => {
        const items = Array.from(col.querySelectorAll(':scope > ' + zone.dataset.vjustify));
        if (items.length < 2) return;
        const free = col.getBoundingClientRect().bottom - bottomOf(col) - 2;
        if (free <= 4) return;
        const per = Math.min(vmax, free / (items.length - 1));
        items.slice(0, -1).forEach((it) => {
          const mb = parseFloat(getComputedStyle(it).marginBottom) || 0;
          it.style.marginBottom = (mb + per) + 'px';
        });
        if (!fits(col)) items.slice(0, -1).forEach((it) => {
          it.style.marginBottom = (parseFloat(it.style.marginBottom) - per) + 'px';
        });
      });
    }
    // Fill leftover space at the bottom of each column by growing the last growable element
    // (exam answer space, writing lines) instead of leaving an unexplained gap.
    cols.forEach((col) => {
      const kids = Array.from(col.children).filter((c) => !c.classList.contains('fbottom'));
      if (!kids.length) return;
      if (zone.dataset.growall === '1') {
        // worksheet style: share the leftover space evenly between all answer areas of the column
        const gs = Array.from(col.querySelectorAll('[data-grow]'));
        const free = col.getBoundingClientRect().bottom - bottomOf(col) - 2;
        if (!gs.length || free <= 4) return;
        const step = parseFloat(gs[0].dataset.grow) || 1;
        let units = Math.floor(free / step);
        const per = Math.floor(units / gs.length);
        gs.forEach((g, i) => {
          const add = per + (i >= gs.length - (units - per * gs.length) ? 1 : 0);
          g.style.height = (g.getBoundingClientRect().height + add * step) + 'px';
        });
        let guard = 0;
        while (!fits(col) && guard++ < 50) {
          const g = gs[guard % gs.length];
          g.style.height = Math.max(step, g.getBoundingClientRect().height - step) + 'px';
        }
        return;
      }
      const g = kids[kids.length - 1].querySelector('[data-grow]') ||
        (kids[kids.length - 1].matches('[data-grow]') ? kids[kids.length - 1] : null);
      if (!g) return;
      const cr = col.getBoundingClientRect();
      const free = cr.bottom - bottomOf(col) - 2;
      if (free > 4) {
        const step = parseFloat(g.dataset.grow) || 1;
        const add = Math.floor(free / step) * step;
        g.style.height = (g.getBoundingClientRect().height + add) + 'px';
        if (!fits(col)) g.style.height = (g.getBoundingClientRect().height - step) + 'px';
      }
    });
  };

  // Column balancing (multicol-like): when a multi-column flow fits with the last column mostly empty, re-flow
  // with the smallest column height that still holds everything, so text spreads evenly over the columns.
  SDD.flowZoneBalanced = function (zone) {
    SDD.flowZoneBalanced0(zone);
    // a flow zone that received no content at all must not leave empty column rules behind
    const wrap = zone.querySelector(':scope > .cols');
    if (wrap && !wrap.querySelector('.col > *')) { wrap.remove(); SDD.emptyZones = (SDD.emptyZones || 0) + 1; }
    // footnotes whose reference mark did not make it onto the page are removed (no orphan notes)
    zone.querySelectorAll('[data-fnnote]').forEach((n) => {
      if (!zone.querySelector(`.fnm[data-fn="${n.dataset.fnnote}"]`)) {
        const box = n.parentElement;
        n.remove();
        if (box && box.classList.contains('fnbox') && !box.querySelector('[data-cat]')) box.remove();
      }
    });
  };
  SDD.flowZoneBalanced0 = function (zone) {
    const src = zone.querySelector(':scope > .src');
    if (!src) return;
    const want = zone.dataset.balance === '1' && parseInt(zone.dataset.cols || '1', 10) > 1 &&
      !src.querySelector('img');
    const snap = want ? src.cloneNode(true) : null;
    const d0 = SDD.dropped, s0 = SDD.splits;
    SDD.flowZone(zone);
    if (!want || SDD.dropped > d0) return;
    const wrap = zone.querySelector(':scope > .cols');
    if (!wrap) return;
    const cols = Array.from(wrap.querySelectorAll(':scope > .col'));
    const full = wrap.getBoundingClientRect().height;
    const last = cols[cols.length - 1];
    const usedLast = last.children.length ? bottomOf(last) - last.getBoundingClientRect().top : 0;
    if (usedLast > 0.8 * full || full < 40) return;
    const d1 = SDD.dropped, s1 = SDD.splits;
    const reflow = (h) => {
      const w = zone.querySelector(':scope > .cols');
      if (w) w.remove();
      zone.insertBefore(snap.cloneNode(true), zone.firstChild);
      zone.dataset.colh = String(h);
      SDD.dropped = d0; SDD.splits = s0;
      SDD.flowZone(zone);
      return SDD.dropped === d0;
    };
    let lo = full * 0.08, hi = full, best = full;
    for (let it = 0; it < 9; it++) {
      const mid = (lo + hi) / 2;
      if (reflow(mid)) { best = mid; hi = mid; } else lo = mid;
    }
    if (best < full - 1 && reflow(best)) { SDD.balanced = (SDD.balanced || 0) + 1; return; }
    delete zone.dataset.colh;
    reflow(full);
    SDD.dropped = d1; SDD.splits = s1;
  };

  // Manuscript line numbers (lineno-style): number every text line of the zone in the outer margin,
  // printing every data-lineno-th number. Each printed number is an 'abandon' block in the ground truth.
  SDD.lineNumbers = function (zone) {
    const step = parseInt(zone.dataset.lineno || '0', 10);
    if (!step) return;
    const page = document.getElementById('page');
    const pr = page.getBoundingClientRect();
    const zr = zone.getBoundingClientRect();
    const rtl = getComputedStyle(page).direction === 'rtl';
    const tops = [];
    zone.querySelectorAll('.col .w, .col .m').forEach((t) => {
      const r = t.getBoundingClientRect();
      if (r.height > 0 && r.bottom <= zr.bottom + 1) tops.push([r.top, r.height]);
    });
    tops.sort((a, b) => a[0] - b[0]);
    const lines = [];
    tops.forEach(([t, h]) => {
      const last = lines[lines.length - 1];
      if (!last || t > last[0] + Math.max(3, last[1] * 0.5)) lines.push([t, h]);
    });
    const start = parseInt(zone.dataset.lnstart || '1', 10);
    const off = parseFloat(zone.dataset.lnx || '30');
    const fs = parseFloat(getComputedStyle(zone).fontSize) * 0.78;
    lines.forEach(([t, h], i) => {
      const n = start + i;
      if (n % step !== 0) return;
      const d = document.createElement('div');
      d.className = 'lnum';
      d.dataset.cat = 'abandon';
      d.dataset.bid = 'ln' + n;
      d.innerHTML = '<span class="w">' + n + '</span>';
      d.style.cssText = `position:absolute;top:${t - pr.top}px;height:${h}px;line-height:${h}px;font-size:${fs}px;` +
        `color:#555;width:${off * 0.8}px;text-align:${rtl ? 'left' : 'right'};` +
        (rtl ? `left:${zr.right - pr.left + off * 0.2}px;` : `left:${zr.left - pr.left - off}px;`);
      page.appendChild(d);
    });
  };

  // ---------------------------------------------------------------- local fitting
  function within(root, sel) {
    const r = root || document;
    const list = Array.from(r.querySelectorAll(sel));
    if (root && root.matches && root.matches(sel)) list.unshift(root);
    return list;
  }

  SDD.fitOptions = function (root) {
    within(root, '.opts').forEach((box) => {
      if (box.closest('.src')) return;
      const prefs = (box.dataset.prefs || '4,2,1').split(',');
      for (const g of prefs) {
        box.classList.remove('g4', 'g3', 'g2', 'g1');
        box.classList.add('g' + g);
        let ok = true;
        for (const o of box.querySelectorAll(':scope > .opt')) {
          if (o.scrollWidth > o.clientWidth + 1) { ok = false; break; }
          if (g !== '1' && nLines(o) > 1) { ok = false; break; }
        }
        if (ok) break;
      }
    });
  };

  // Shrink display equations that overflow their container; drop them if they would become unreadable.
  // Shrink tables wider than their container (min 72% font size).
  SDD.fitTables = function (root) {
    within(root, 'table').forEach((t) => {
      if (t.closest('.src') || t.dataset.tFit) return;
      t.dataset.tFit = '1';
      const box = t.parentElement;
      let fs = parseFloat(getComputedStyle(t).fontSize);
      const min = fs * 0.72;
      let guard = 0;
      while (t.scrollWidth > box.clientWidth + 1 && fs > min && guard++ < 30) {
        fs *= 0.95;
        t.style.fontSize = fs + 'px';
      }
    });
  };

  function removeEqGroup(row) {
    // an equation that cannot be shown takes its lead-in sentence and its 'where ...' paragraph with it
    const prev = row.previousElementSibling;
    const next = row.nextElementSibling;
    if (prev && prev.dataset && prev.dataset.kwn === '1' && prev.dataset.eqlead === '1') prev.remove();
    if (next && next.dataset && next.dataset.eqwhere === '1') next.remove();
    row.remove();
  }

  // width of the rendered formula itself (the KaTeX block is as wide as its container, the glyph runs are not)
  function eqContentWidth(eq) {
    let l = Infinity, r = -Infinity;
    eq.querySelectorAll('.katex-html > .base, .katex-html > .tag').forEach((p) => {
      const b = p.getBoundingClientRect();
      if (b.width > 0) { l = Math.min(l, b.left); r = Math.max(r, b.right); }
    });
    return r > l ? r - l : 0;
  }
  SDD.fitEquations = function (root) {
    within(root, '.eq').forEach((eq) => {
      if (eq.closest('.src') || eq.dataset.eqFit) return;
      eq.dataset.eqFit = '1';
      const row = eq.closest('.eqrow');
      const no = row ? row.querySelector('.eqno') : null;
      const rowW = (row || eq.parentElement || eq).clientWidth;
      // the formula is centred: keep clear of the equation number on BOTH sides
      const noW = no ? no.getBoundingClientRect().width + 8 : 0;
      const avail = Math.max(24, rowW - 2 * noW - 4);
      let fs = parseFloat(getComputedStyle(eq).fontSize);
      const min = fs * 0.62;
      let guard = 0;
      while (eqContentWidth(eq) > avail && fs > min && guard++ < 30) {
        fs *= 0.94;
        eq.style.fontSize = fs + 'px';
      }
      if (eqContentWidth(eq) > avail + 1) {
        const r = row || eq;
        if (r.isConnected) removeEqGroup(r);
        SDD.dropped++;
      }
    });
  };

  // Auto-height head zones (headline / deck / byline / photo) must not run into the module below:
  // drop optional parts (highest data-opt first), then shrink the headline.
  SDD.fitHeads = function () {
    document.querySelectorAll('.zone[data-maxh]').forEach((z) => {
      const maxh = parseFloat(z.dataset.maxh);
      const over = () => z.getBoundingClientRect().height > maxh + 0.5;
      let guard = 0;
      while (over() && guard++ < 12) {
        const opts = Array.from(z.querySelectorAll('[data-opt]'));
        if (!opts.length) break;
        opts.sort((a, b) => parseFloat(b.dataset.opt) - parseFloat(a.dataset.opt));
        opts[0].remove();
        SDD.headTrim = (SDD.headTrim || 0) + 1;
      }
      const hl = z.querySelector('.hl');
      guard = 0;
      if (hl) {
        let fs = parseFloat(getComputedStyle(hl).fontSize);
        const min = fs * 0.62;
        while (over() && fs > min && guard++ < 30) { fs *= 0.95; hl.style.fontSize = fs + 'px'; }
      }
      if (over()) SDD.headOverflow = (SDD.headOverflow || 0) + 1;
    });
  };

  SDD.fitText = function (root) {
    within(root, '[data-fit-lines]').forEach((el) => {
      if (el.closest('.src') || el.dataset.fitDone) return;
      el.dataset.fitDone = '1';
      const maxL = parseInt(el.dataset.fitLines, 10);
      let fs = parseFloat(getComputedStyle(el).fontSize);
      const minFs = fs * parseFloat(el.dataset.fitMin || '0.6');
      let guard = 0;
      while ((nLines(el) > maxL || el.scrollWidth > el.clientWidth + 1) && fs > minFs && guard++ < 40) {
        fs *= 0.95;
        el.style.fontSize = fs + 'px';
      }
    });
  };

  SDD.fitBoxes = function () {
    document.querySelectorAll('[data-fitbox]').forEach((box) => {
      SDD.fitEquations(box);
      let k = 1.0;
      const grow = parseFloat(box.dataset.grow || '0');
      if (grow > 1 && box.children.length) {
        let guard = 0;
        const target = parseFloat(box.dataset.fill || '0.72');
        while (guard++ < 30) {
          const used = bottomOf(box) - box.getBoundingClientRect().top;
          if (used >= target * box.getBoundingClientRect().height || k >= grow) break;
          k *= 1.04;
          box.style.setProperty('--k', String(k));
          if (!fits(box)) { k /= 1.04; box.style.setProperty('--k', String(k)); break; }
        }
      }
      const minK = parseFloat(box.dataset.fitbox || '0.7');
      let guard = 0;
      while (!fits(box) && guard++ < 60) {
        if (k > minK) {
          k *= 0.96;
          box.style.setProperty('--k', String(k));
        } else {
          const rem = box.querySelectorAll('[data-removable="1"]');
          if (!rem.length) break;
          rem[rem.length - 1].remove();
          SDD.dropped++;
        }
      }
    });
  };

  // Zones whose top/bottom depend on auto-height siblings (front matter, spanning floats, footnote bands).
  //   data-top-from="#id"    top = bottom(#id) + data-gap-top
  //   data-bottom-from="#id" bottom = top(#id) - data-gap-bottom   (else data-bottom = absolute px)
  SDD.anchorZones = function () {
    const page = document.getElementById('page');
    const pr = page.getBoundingClientRect();
    document.querySelectorAll('.zone[data-top-from], .zone[data-bottom-from]').forEach((z) => {
      const hasH = z.style.height !== '';
      let top = parseFloat(z.style.top) || 0;
      let bottom = top + (parseFloat(z.style.height) || 0);
      if (z.dataset.topFrom) {
        const ref = document.querySelector(z.dataset.topFrom);
        if (ref && ref.getBoundingClientRect().height > 0) {
          top = ref.getBoundingClientRect().bottom - pr.top + parseFloat(z.dataset.gapTop || '0');
        }
      }
      if (z.dataset.bottomFrom) {
        const ref = document.querySelector(z.dataset.bottomFrom);
        if (ref && ref.getBoundingClientRect().height > 0) {
          bottom = ref.getBoundingClientRect().top - pr.top - parseFloat(z.dataset.gapBottom || '0');
        }
      }
      z.style.top = top + 'px';
      if (hasH || z.dataset.bottomFrom) z.style.height = Math.max(0, bottom - top) + 'px';
    });
  };

  // Thai has no spaces between words: split the Python-emitted '.w.seg' runs into dictionary words with the same
  // ICU segmenter Chromium uses for line breaking, so tokens are line-break units (one rectangle each).
  SDD.segmentThai = function () {
    const segs = document.querySelectorAll('.w.seg');
    if (!segs.length || typeof Intl === 'undefined' || !Intl.Segmenter) return;
    const sg = new Intl.Segmenter('th', { granularity: 'word' });
    const glue = /^[\s.,;:!?)\]»”’ๆฯ%]+$/;
    segs.forEach((w) => {
      const toks = [];
      for (const s of sg.segment(w.textContent || '')) {
        if (toks.length && glue.test(s.segment)) toks[toks.length - 1] += s.segment;
        else toks.push(s.segment);
      }
      w.classList.remove('seg');
      if (toks.length <= 1) return;
      const frag = document.createDocumentFragment();
      toks.forEach((t, i) => {
        const e = w.cloneNode(false);
        e.textContent = t;
        frag.appendChild(e);
        if (i < toks.length - 1) frag.appendChild(document.createElement('wbr'));
      });
      w.replaceWith(frag);
      SDD.thaiSplit = (SDD.thaiSplit || 0) + 1;
    });
  };

  SDD.layout = function () {
    const t0 = performance.now();
    SDD.segmentThai();
    SDD.renderMath();
    SDD.fitText();
    SDD.fitOptions();
    SDD.fitHeads();
    SDD.anchorZones();
    const zones = Array.from(document.querySelectorAll('.zone.flow'));
    zones.sort((a, b) => (parseFloat(a.dataset.zorder || 0) - parseFloat(b.dataset.zorder || 0)));
    zones.forEach(SDD.flowZoneBalanced);
    zones.forEach(SDD.lineNumbers);
    SDD.fitBoxes();
    // empty-zone cleanup: remove annotated blocks fully outside the page
    return { ms: performance.now() - t0, dropped: SDD.dropped, splits: SDD.splits, mathErrors: SDD.mathErrors };
  };

  // ---------------------------------------------------------------- ground truth
  function rel(r, pr) { return [r.left - pr.left, r.top - pr.top, r.right - pr.left, r.bottom - pr.top]; }
  function union(a, b) { return a ? [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[2], b[2]), Math.max(a[3], b[3])] : b.slice(); }

  function tokText(w) {
    if (w.classList.contains('m')) return '$' + w.dataset.latex + '$';
    return (w.textContent || '').replace(SHY, '');
  }

  // split a hyphen-broken token into per-line pieces
  function brokenPieces(w, rects) {
    const tn = w.firstChild;
    const full = w.textContent || '';
    if (!tn || tn.nodeType !== 3) return [[rects[0], full.replace(SHY, '')]];
    const out = [];
    let start = 0;
    const range = document.createRange();
    let lineTop = rects[0].top, lineBottom = rects[0].bottom;
    for (let i = 0; i < full.length; i++) {
      if (full[i] !== '­') continue;
      if (i + 1 >= full.length) break;
      range.setStart(tn, i + 1); range.setEnd(tn, Math.min(full.length, i + 2));
      const r = range.getBoundingClientRect();
      if (r.top >= lineBottom - 0.4 * (lineBottom - lineTop)) {
        const piece = full.slice(start, i).replace(SHY, '') + '-';
        range.setStart(tn, start); range.setEnd(tn, i + 1);
        out.push([range.getBoundingClientRect(), piece, true]);
        start = i + 1; lineTop = r.top; lineBottom = r.bottom;
      }
    }
    range.setStart(tn, start); range.setEnd(tn, full.length);
    out.push([range.getBoundingClientRect(), full.slice(start).replace(SHY, ''), false]);
    return out;
  }

  function linesOf(el, pr) {
    const toks = el.querySelectorAll('.w, .m');
    const lines = [];
    let cur = null;
    const push = (r, txt, hyph) => {
      if (r.width <= 0 && r.height <= 0) return;
      const box = rel(r, pr);
      const h = box[3] - box[1];
      if (cur && box[1] < cur.box[3] - 0.45 * Math.min(h, cur.box[3] - cur.box[1]) &&
          box[3] > cur.box[1] + 0.3 * h) {
        cur.box = union(cur.box, box); cur.text += txt;
      } else {
        cur = { box, text: txt };
        lines.push(cur);
      }
      if (hyph) cur.hyph = true;
    };
    toks.forEach((w) => {
      if (w.closest('.katex') && !w.classList.contains('m')) return;
      const rs = w.getClientRects();
      if (!rs.length) return;
      if (rs.length === 1 || w.classList.contains('m')) {
        push(w.getBoundingClientRect(), tokText(w), false);
      } else {
        for (const [r, t, h] of brokenPieces(w, rs)) push(r, t, h);
      }
    });
    lines.forEach((l) => { l.text = l.text.replace(/\s+/g, ' ').trim(); });
    return lines.filter((l) => l.text.length);
  }

  function semanticText(el) {
    let out = '';
    const walk = (n) => {
      if (n.nodeType === 3) {
        if (!n.parentElement.closest('.katex')) out += n.textContent;
        return;
      }
      if (n.nodeType !== 1) return;
      if (n.classList.contains('nogt')) return;
      if (n.dataset && n.dataset.latex !== undefined && !n.dataset.cat) { out += '$' + n.dataset.latex + '$'; return; }
      if (n.tagName === 'BR') { out += '\n'; return; }
      for (const c of n.childNodes) walk(c);
      if (n.classList.contains('nl')) out += '\n';
    };
    walk(el);
    return out.replace(SHY, '').replace(/[ \t ]+\n/g, '\n').replace(/[ \t]+/g, ' ').trim();
  }

  function tableHTML(tbl) {
    const t = tbl.tagName === 'TABLE' ? tbl : tbl.querySelector('table');
    if (!t) return '';
    const rows = [];
    t.querySelectorAll('tr').forEach((tr) => {
      const cells = [];
      tr.querySelectorAll(':scope > td, :scope > th').forEach((c) => {
        let a = '';
        if (c.rowSpan > 1) a += ` rowspan="${c.rowSpan}"`;
        if (c.colSpan > 1) a += ` colspan="${c.colSpan}"`;
        cells.push(`<td${a}>${semanticText(c).replace(/\n/g, ' ')}</td>`);
      });
      rows.push('<tr>' + cells.join('') + '</tr>');
    });
    return '<table>' + rows.join('') + '</table>';
  }

  function visibleRect(el, pr) {
    const r = el.getBoundingClientRect();
    if (r.width < 0.5 || r.height < 0.5) return null;
    const b = rel(r, pr);
    const c = [Math.max(0, b[0]), Math.max(0, b[1]), Math.min(pr.width, b[2]), Math.min(pr.height, b[3])];
    if (c[2] - c[0] < 0.5 || c[3] - c[1] < 0.5) return null;
    return c;
  }

  SDD.extract = function () {
    const page = document.getElementById('page');
    const pr = page.getBoundingClientRect();
    const blocks = [];
    const all = Array.from(page.querySelectorAll('[data-cat]'));
    all.forEach((el, domIdx) => {
      if (el.closest('.src')) return;
      const box = visibleRect(el, pr);
      if (!box) return;
      const cat = el.dataset.cat;
      const zone = el.closest('.zone');
      const col = el.closest('.col');
      const rec = {
        cat, bid: el.dataset.bid || ('d' + domIdx), dom: domIdx,
        zorder: parseFloat((el.dataset.zorder) || (zone && zone.dataset.zorder) || '0'),
        col: col ? parseInt(col.dataset.ci, 10) : 0,
        cont_of: el.dataset.contOf || null, group: el.dataset.group || null,
        sub: el.dataset.sub || null,
      };
      if (cat === 'equation_isolated') {
        const k = el.querySelector('.katex-html') || el.querySelector('.katex') || el;
        rec.box = visibleRect(k, pr) || box;
        rec.text = '$$' + (el.dataset.latex || (el.querySelector('[data-latex]') || {}).dataset?.latex || '') + '$$';
        rec.latex = el.dataset.latex || ((el.querySelector('[data-latex]') || {}).dataset || {}).latex || '';
      } else if (cat === 'table') {
        rec.box = box;
        rec.html = tableHTML(el);
        rec.text = rec.html;
      } else if (TEXT_CATS.has(cat)) {
        const lines = linesOf(el, pr);
        rec.lines = lines;
        let u = null;
        lines.forEach((l) => { u = union(u, l.box); });
        if (el.classList.contains('dropcap')) u = union(u, box.slice(0, 2).concat(box.slice(0, 2)));
        rec.box = u || box;
        rec.text = el.dataset.textmode === 'lines' ? lines.map((l) => l.text).join('\n') : semanticText(el);
      } else {
        rec.box = box;
        rec.text = '';
      }
      // clip to page
      rec.box = [Math.max(0, rec.box[0]), Math.max(0, rec.box[1]), Math.min(pr.width, rec.box[2]), Math.min(pr.height, rec.box[3])];
      if (rec.box[2] - rec.box[0] < 1 || rec.box[3] - rec.box[1] < 1) return;
      if (TEXT_CATS.has(cat) && !rec.text) return;
      blocks.push(rec);
    });
    // overflow audit: any token outside its column / page
    let clipped = 0;
    page.querySelectorAll('.col').forEach((c) => {
      const cr = c.getBoundingClientRect();
      c.querySelectorAll('.w').forEach((w) => {
        const r = w.getBoundingClientRect();
        // a token counts as clipped when less than ~60% of its glyph box lies inside the column
        // (inline content areas legitimately poke 1-3px past the first/last line box)
        const tol = Math.max(2, 0.4 * Math.min(r.height, 40));
        if (r.height > 0 && (r.bottom > cr.bottom + tol || r.top < cr.top - tol)) clipped++;
      });
    });
    // image upscale audit (device px / natural px; object-fit:cover -> the larger axis ratio)
    let upscale = 0;
    page.querySelectorAll('img').forEach((im) => {
      if (im.closest('.src') || !im.naturalWidth) return;
      const r = im.getBoundingClientRect();
      if (r.width < 2 || r.height < 2) return;
      const dpr = window.devicePixelRatio || 1;
      upscale = Math.max(upscale, r.width * dpr / im.naturalWidth, r.height * dpr / im.naturalHeight);
    });
    // CSS background photos (background-size: cover) carry their pixel size in data-nw / data-nh
    page.querySelectorAll('[data-nw]').forEach((el) => {
      const r = el.getBoundingClientRect();
      const nw = parseFloat(el.dataset.nw), nh = parseFloat(el.dataset.nh);
      if (r.width < 2 || r.height < 2 || !nw || !nh) return;
      const dpr = window.devicePixelRatio || 1;
      upscale = Math.max(upscale, Math.max(r.width / nw, r.height / nh) * dpr);
    });
    return { blocks, page: { w: pr.width, h: pr.height }, stats: { clipped_tokens: clipped, dropped: SDD.dropped, splits: SDD.splits, mathErrors: SDD.mathErrors, img_upscale: Math.round(upscale * 100) / 100, head_overflow: SDD.headOverflow || 0, head_trim: SDD.headTrim || 0 } };
  };
})();

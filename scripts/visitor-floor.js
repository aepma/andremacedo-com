#!/usr/bin/env node
// Visitor-floor gate for andremacedo.com (SOUL.md "Visitor floor", INV-17).
// Usage: node scripts/visitor-floor.js <path/to/index.html | https://url>
// Output: JSON to stdout (same shape as mobile-gate.js: {gate, checks, summary})
// Exit: 0 = every check passed at both viewports, 1 = any check failed, 2 = script error
//
// Three elements are law: data-floor="name" (text "André Macedo"), data-floor="role"
// (one line under 90 chars), data-floor="contact" (<a href="mailto:me@andremacedo.com">
// with visible text me@andremacedo.com). Each must be visible in the first viewport
// with NO interaction of any kind (no scroll, click, hover, key) at 390x844 and at
// 1280x800, at first paint and still at three seconds: fully inside the viewport,
// effective opacity 1, not clipped, font size >= 14px at phone width, and contrast
// >= 4.5:1 measured against the rendered pixels behind the element.
//
// Pixel sampling: like audit-contrast.js, the background is read from rendered
// pixels via canvas readback. Here the readback source is a real viewport
// screenshot drawn into an in-page canvas, taken with the element's text colour
// set to transparent so the samples are the pixels BEHIND the glyphs, not the
// glyphs themselves. The element's style is restored immediately afterwards.
// Visibility on screen is proven the same way: the normal screenshot and the
// text-transparent screenshot must differ inside the element's box.

const { chromium } = require('playwright');
const path = require('path');

const VIEWPORTS = [
  { name: 'phone', width: 390, height: 844 },
  { name: 'desktop', width: 1280, height: 800 },
];
const TIMINGS = [
  { name: 'first-paint', settleMs: 0 },
  { name: '3s', settleMs: 3000 },
];
const WCAG_THRESHOLD = 4.5;
const MIN_FONT_PX_PHONE = 14;
const ROLE_MAX_CHARS = 90;
const MAILTO = 'mailto:me@andremacedo.com';
const EMAIL = 'me@andremacedo.com';
const NAME = 'André Macedo';
const FLOOR_KEYS = ['name', 'role', 'contact'];
const SAMPLE_GRID = { cols: 9, rows: 3 };

function usageTarget() {
  const arg = process.argv[2];
  if (!arg) {
    throw new Error('usage: visitor-floor.js <path/to/index.html | https://url>');
  }
  if (/^https?:\/\//i.test(arg)) return { url: arg, label: arg };
  const abs = path.resolve(arg);
  return { url: 'file://' + abs, label: abs };
}

function relativeLuminance([r, g, b]) {
  const ch = (v) => {
    const s = v / 255;
    return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b);
}

function contrastRatio(a, b) {
  const l1 = relativeLuminance(a);
  const l2 = relativeLuminance(b);
  const hi = Math.max(l1, l2);
  const lo = Math.min(l1, l2);
  return (hi + 0.05) / (lo + 0.05);
}

function parseColor(str) {
  const m = String(str).match(/rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)/);
  if (!m) throw new Error('unparseable computed color: ' + str);
  return { rgb: [+m[1], +m[2], +m[3]], alpha: m[4] === undefined ? 1 : parseFloat(m[4]) };
}

function hex(rgb) {
  return '#' + rgb.map((v) => Math.round(v).toString(16).padStart(2, '0')).join('');
}

// Runs inside the page. Returns a DOM-level report per floor key.
function domReport(vw, vh) {
  const keys = ['name', 'role', 'contact'];
  const out = {};
  for (const key of keys) {
    const nodes = document.querySelectorAll('[data-floor="' + key + '"]');
    const r = { count: nodes.length };
    if (nodes.length !== 1) { out[key] = r; continue; }
    const el = nodes[0];
    r.tag = el.tagName.toLowerCase();
    r.text = (el.textContent || '').replace(/\s+/g, ' ').trim();
    r.href = el.getAttribute('href');
    const cs = getComputedStyle(el);
    r.color = cs.color;
    r.fontSize = parseFloat(cs.fontSize);
    r.display = cs.display;
    r.visibility = cs.visibility;
    const rect = el.getBoundingClientRect();
    r.rect = { left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom,
               width: rect.width, height: rect.height };
    // Effective opacity: product over the ancestor chain. Also collect
    // display:none / visibility:hidden on any ancestor, and clipping by any
    // ancestor whose overflow is not visible or that carries a clip-path.
    let opacity = parseFloat(cs.opacity);
    let hidden = cs.display === 'none' || cs.visibility === 'hidden';
    let clipped = null;
    if (cs.clipPath && cs.clipPath !== 'none') clipped = 'self clip-path ' + cs.clipPath;
    let p = el.parentElement;
    while (p) {
      const ps = getComputedStyle(p);
      opacity *= parseFloat(ps.opacity);
      if (ps.display === 'none' || ps.visibility === 'hidden') hidden = true;
      if (ps.clipPath && ps.clipPath !== 'none') clipped = clipped || (sel(p) + ' clip-path');
      const clips = ['hidden', 'clip', 'scroll', 'auto'];
      if (clips.includes(ps.overflowX) || clips.includes(ps.overflowY)) {
        const pr = p.getBoundingClientRect();
        const eps = 0.5;
        if (rect.left < pr.left - eps || rect.top < pr.top - eps ||
            rect.right > pr.right + eps || rect.bottom > pr.bottom + eps) {
          clipped = clipped || (sel(p) + ' overflow ' + ps.overflowX + '/' + ps.overflowY);
        }
      }
      p = p.parentElement;
    }
    r.effectiveOpacity = opacity;
    r.hidden = hidden;
    r.clipped = clipped;
    out[key] = r;
  }
  function sel(el) {
    if (el.id) return '#' + el.id;
    const cls = (typeof el.className === 'string' ? el.className : '').trim().split(/\s+/).filter(Boolean).slice(0, 2).join('.');
    return el.tagName.toLowerCase() + (cls ? '.' + cls : '');
  }
  return { vw, vh, report: out };
}

async function screenshotPixels(page, pngBuffer, width, height) {
  // Draw the screenshot into an in-page canvas and return the RGBA byte array
  // (deviceScaleFactor is 1, so screenshot pixels map 1:1 onto CSS pixels).
  const dataUrl = 'data:image/png;base64,' + pngBuffer.toString('base64');
  const arr = await page.evaluate(async ([src, w, h]) => {
    const img = new Image();
    await new Promise((res, rej) => { img.onload = res; img.onerror = rej; img.src = src; });
    const c = document.createElement('canvas');
    c.width = w; c.height = h;
    const ctx = c.getContext('2d');
    ctx.drawImage(img, 0, 0);
    return Array.from(ctx.getImageData(0, 0, w, h).data);
  }, [dataUrl, width, height]);
  if (arr.length !== width * height * 4) {
    throw new Error('screenshot readback size mismatch: ' + arr.length);
  }
  return Uint8ClampedArray.from(arr);
}

function pixelAt(data, width, x, y) {
  const i = (y * width + x) * 4;
  return [data[i], data[i + 1], data[i + 2]];
}

async function setTextTransparent(page, on) {
  await page.evaluate((flag) => {
    for (const el of document.querySelectorAll('[data-floor]')) {
      if (flag) {
        el.__floorPrev = { color: el.style.color, shadow: el.style.textShadow, deco: el.style.textDecorationColor };
        el.style.color = 'transparent';
        el.style.textShadow = 'none';
        el.style.textDecorationColor = 'transparent';
      } else if (el.__floorPrev) {
        el.style.color = el.__floorPrev.color;
        el.style.textShadow = el.__floorPrev.shadow;
        el.style.textDecorationColor = el.__floorPrev.deco;
        delete el.__floorPrev;
      }
    }
  }, on);
}

async function measure(page, vp, timing) {
  const { width, height } = vp;
  const dom = await page.evaluate(([w, h]) => window.__floorDomReport(w, h), [width, height]);
  const normal = await page.screenshot({ type: 'png', clip: { x: 0, y: 0, width, height } });
  await setTextTransparent(page, true);
  const blank = await page.screenshot({ type: 'png', clip: { x: 0, y: 0, width, height } });
  await setTextTransparent(page, false);
  const normalPx = await screenshotPixels(page, normal, width, height);
  const blankPx = await screenshotPixels(page, blank, width, height);

  const checks = [];
  const ctx = `${vp.name} ${width}x${height} @${timing.name}`;
  const add = (element, name, passed, details, measured) =>
    checks.push({ name, element, viewport: vp.name, timing: timing.name, passed, details, measured });

  for (const key of FLOOR_KEYS) {
    const r = dom.report[key];
    if (r.count !== 1) {
      add(key, 'PRESENT_ONCE', false, `${ctx}: data-floor="${key}" found ${r.count} time(s), need exactly 1`, { count: r.count });
      continue;
    }
    add(key, 'PRESENT_ONCE', true, `${ctx}: present once (<${r.tag}>)`, { count: 1, tag: r.tag });

    // Content rules
    if (key === 'name') {
      add(key, 'TEXT', r.text === NAME, `${ctx}: text ${JSON.stringify(r.text)} (need ${JSON.stringify(NAME)})`, { text: r.text });
    } else if (key === 'role') {
      const ok = r.text.length > 0 && r.text.length < ROLE_MAX_CHARS;
      add(key, 'TEXT', ok, `${ctx}: role ${r.text.length} chars (need 1..${ROLE_MAX_CHARS - 1}): ${JSON.stringify(r.text)}`, { text: r.text, chars: r.text.length });
    } else {
      const ok = r.tag === 'a' && r.href === MAILTO && r.text === EMAIL;
      add(key, 'TEXT', ok, `${ctx}: <${r.tag} href=${JSON.stringify(r.href)}> text ${JSON.stringify(r.text)} (need <a href="${MAILTO}"> text "${EMAIL}")`, { tag: r.tag, href: r.href, text: r.text });
    }

    // Geometry: fully inside the viewport, non-degenerate
    const rc = r.rect;
    const inside = rc.width > 0 && rc.height > 0 && rc.left >= 0 && rc.top >= 0 && rc.right <= width && rc.bottom <= height;
    add(key, 'IN_VIEWPORT', inside, `${ctx}: box l=${rc.left.toFixed(1)} t=${rc.top.toFixed(1)} r=${rc.right.toFixed(1)} b=${rc.bottom.toFixed(1)} (viewport ${width}x${height})`, rc);

    // Opacity / display / clipping
    add(key, 'OPACITY', !r.hidden && r.effectiveOpacity >= 0.999, `${ctx}: effective opacity ${r.effectiveOpacity.toFixed(3)}, hidden=${r.hidden}`, { effectiveOpacity: r.effectiveOpacity, display: r.display, visibility: r.visibility });
    add(key, 'NOT_CLIPPED', r.clipped === null, `${ctx}: ${r.clipped === null ? 'no clipping ancestor' : 'clipped by ' + r.clipped}`, { clipped: r.clipped });

    // Font size (enforced at phone width; reported at desktop)
    const fontOk = vp.width > 600 || r.fontSize >= MIN_FONT_PX_PHONE;
    add(key, 'FONT_SIZE', fontOk, `${ctx}: font-size ${r.fontSize}px (min ${MIN_FONT_PX_PHONE}px at phone width)`, { fontSize: r.fontSize });

    if (!inside) continue; // pixel checks need a box inside the buffer

    // Pixel-level: rendered on screen (normal vs text-transparent differ inside the box)
    const x0 = Math.max(0, Math.floor(rc.left)), y0 = Math.max(0, Math.floor(rc.top));
    const x1 = Math.min(width, Math.ceil(rc.right)), y1 = Math.min(height, Math.ceil(rc.bottom));
    let differing = 0, total = 0;
    for (let y = y0; y < y1; y++) {
      for (let x = x0; x < x1; x++) {
        total++;
        const a = pixelAt(normalPx, width, x, y), b = pixelAt(blankPx, width, x, y);
        if (Math.abs(a[0] - b[0]) + Math.abs(a[1] - b[1]) + Math.abs(a[2] - b[2]) > 24) differing++;
      }
    }
    const rendered = differing > 0 && differing / Math.max(1, total) >= 0.01;
    add(key, 'RENDERED', rendered, `${ctx}: ${differing} of ${total} box pixels change when the text is hidden (${(100 * differing / Math.max(1, total)).toFixed(1)}%)`, { differing, total });

    // Contrast: text colour vs the pixels behind the glyphs, worst sample wins
    const fg = parseColor(r.color);
    let worst = Infinity, worstBg = null, sum = 0, n = 0;
    for (let gy = 0; gy < SAMPLE_GRID.rows; gy++) {
      for (let gx = 0; gx < SAMPLE_GRID.cols; gx++) {
        const x = Math.min(width - 1, Math.floor(rc.left + ((gx + 0.5) / SAMPLE_GRID.cols) * rc.width));
        const y = Math.min(height - 1, Math.floor(rc.top + ((gy + 0.5) / SAMPLE_GRID.rows) * rc.height));
        const bg = pixelAt(blankPx, width, x, y);
        // composite a translucent text colour over the sampled background
        const fgc = fg.alpha >= 1 ? fg.rgb : fg.rgb.map((c, i) => c * fg.alpha + bg[i] * (1 - fg.alpha));
        const ratio = contrastRatio(fgc, bg);
        sum += ratio; n++;
        if (ratio < worst) { worst = ratio; worstBg = bg; }
      }
    }
    const wr = Math.round(worst * 100) / 100;
    add(key, 'CONTRAST', worst >= WCAG_THRESHOLD, `${ctx}: worst ${wr}:1 (mean ${(sum / n).toFixed(2)}) fg ${hex(fg.rgb)} vs bg ${hex(worstBg)} over ${n} samples (min ${WCAG_THRESHOLD})`, { worst: wr, mean: Math.round((sum / n) * 100) / 100, fg: hex(fg.rgb), worstBg: hex(worstBg), samples: n });
  }
  return checks;
}

async function runGate() {
  const target = usageTarget();
  const browser = await chromium.launch({ args: ['--no-sandbox'] });
  const checks = [];
  try {
    for (const vp of VIEWPORTS) {
      const page = await browser.newPage({
        viewport: { width: vp.width, height: vp.height },
        deviceScaleFactor: 1,
      });
      // No interaction of any kind: no scroll, click, hover, or key is ever sent.
      await page.addInitScript(`window.__floorDomReport = ${domReport.toString()};`);
      try {
        await page.goto(target.url, { waitUntil: 'domcontentloaded', timeout: 30000 });
      } catch (err) {
        throw new Error(`navigation to ${target.url} failed at ${vp.name}: ${err.message}`);
      }
      // First paint: two animation frames after DOMContentLoaded, nothing more.
      await page.evaluate(() => new Promise((res) => requestAnimationFrame(() => requestAnimationFrame(res))));
      const t0 = Date.now();
      for (const timing of TIMINGS) {
        const remaining = timing.settleMs - (Date.now() - t0);
        if (remaining > 0) await page.waitForTimeout(remaining);
        checks.push(...(await measure(page, vp, timing)));
      }
      await page.close();
    }
    await browser.close();
    return { target: target.label, checks };
  } catch (err) {
    await browser.close().catch(() => {});
    throw err;
  }
}

runGate()
  .then(({ target, checks }) => {
    const failed = checks.filter((c) => !c.passed);
    const gate = failed.length === 0 ? 'pass' : 'fail';
    const names = [...new Set(failed.map((c) => `${c.element}:${c.name}@${c.viewport}/${c.timing}`))];
    const summary = gate === 'pass'
      ? `All visitor-floor checks passed (${checks.length} checks, 2 viewports, 2 timings)`
      : 'Failed: ' + names.join(', ');
    console.log(JSON.stringify({ gate, target, checks, summary }, null, 2));
    process.exit(gate === 'pass' ? 0 : 1);
  })
  .catch((err) => {
    console.log(JSON.stringify({ gate: 'error', checks: [], summary: 'Script error: ' + err.message }, null, 2));
    process.exit(2);
  });

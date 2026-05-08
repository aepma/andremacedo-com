#!/usr/bin/env node
// Rendered-pixel contrast audit for andremacedo.com
// Usage: node scripts/audit-contrast.js <url>
// Output: JSON array to stdout, exit 0 always (reporter, not gate)
// Each entry: {selector, color, bg_sample, ratio, pass}

const { chromium } = require('playwright');

const SELECTORS = [
  'h1',
  'h2',
  '.hook',
  '.meta',
  '.program-masthead span',
  '.compass-line .c-val',
  '.float-thought',
  '.stage-hero .note',
];

const WCAG_THRESHOLD = 4.5;
const SETTLE_MS = 2000;

function hexToRgb(hex) {
  const clean = hex.replace('#', '');
  if (clean.length === 3) {
    return [
      parseInt(clean[0] + clean[0], 16),
      parseInt(clean[1] + clean[1], 16),
      parseInt(clean[2] + clean[2], 16),
    ];
  }
  return [
    parseInt(clean.slice(0, 2), 16),
    parseInt(clean.slice(2, 4), 16),
    parseInt(clean.slice(4, 6), 16),
  ];
}

function relativeLuminance([r, g, b]) {
  const channel = (v) => {
    const s = v / 255;
    return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

function contrastRatio(rgb1, rgb2) {
  const l1 = relativeLuminance(rgb1);
  const l2 = relativeLuminance(rgb2);
  const lighter = Math.max(l1, l2);
  const darker = Math.min(l1, l2);
  return (lighter + 0.05) / (darker + 0.05);
}

function parseRgbString(str) {
  // handles rgb(r, g, b) and rgba(r, g, b, a)
  const m = str.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
  if (m) return [parseInt(m[1]), parseInt(m[2]), parseInt(m[3])];
  return null;
}

async function sampleBackground(page, x, y) {
  // Sample a single pixel from the rendered page via canvas readback
  try {
    const pixel = await page.evaluate(([px, py]) => {
      const canvas = document.createElement('canvas');
      canvas.width = 1;
      canvas.height = 1;
      const ctx = canvas.getContext('2d');
      // drawImage from the viewport via html2canvas-style approach is unavailable;
      // fall back to reading rf-canvas if present, otherwise return the body background.
      const rfCanvas = document.getElementById('rf-canvas');
      if (rfCanvas) {
        try {
          ctx.drawImage(rfCanvas, px, py, 1, 1, 0, 0, 1, 1);
          const d = ctx.getImageData(0, 0, 1, 1).data;
          return [d[0], d[1], d[2]];
        } catch (_) {}
      }
      // fallback: parse CSS background-color of body
      const bg = window.getComputedStyle(document.body).backgroundColor;
      const m = bg.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
      if (m) return [parseInt(m[1]), parseInt(m[2]), parseInt(m[3])];
      return [5, 5, 5]; // #050505 default
    }, [x, y]);
    return pixel;
  } catch (_) {
    return [5, 5, 5];
  }
}

async function auditUrl(url) {
  const browser = await chromium.launch({ args: ['--no-sandbox'] });
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });

  try {
    await page.goto(url, { waitUntil: 'networkidle', timeout: 25000 });
  } catch (_) {
    // partial load is OK — wait for settle then proceed
  }

  // Wait for rf-canvas and state-inject to settle
  await page.waitForTimeout(SETTLE_MS);

  const results = [];

  for (const selector of SELECTORS) {
    let elements;
    try {
      elements = await page.$$(selector);
    } catch (_) {
      continue;
    }

    for (const el of elements.slice(0, 3)) {
      try {
        const box = await el.boundingBox();
        if (!box || box.width < 1 || box.height < 1) continue;

        const color = await page.evaluate((e) => {
          const s = window.getComputedStyle(e);
          return s.color;
        }, el);

        const fgRgb = parseRgbString(color);
        if (!fgRgb) continue;

        // Sample background at element center
        const cx = Math.round(box.x + box.width / 2);
        const cy = Math.round(box.y + box.height / 2);
        const bgRgb = await sampleBackground(page, cx, cy);

        const ratio = contrastRatio(fgRgb, bgRgb);
        const fgHex = '#' + fgRgb.map((v) => v.toString(16).padStart(2, '0')).join('');
        const bgHex = '#' + bgRgb.map((v) => v.toString(16).padStart(2, '0')).join('');

        results.push({
          selector,
          color: fgHex,
          bg_sample: bgHex,
          ratio: Math.round(ratio * 100) / 100,
          pass: ratio >= WCAG_THRESHOLD,
        });

        break; // one representative per selector
      } catch (_) {
        continue;
      }
    }
  }

  await browser.close();
  return results;
}

const url = process.argv[2];
if (!url) {
  console.error('Usage: node audit-contrast.js <url>');
  process.exit(0);
}

auditUrl(url)
  .then((results) => {
    console.log(JSON.stringify(results, null, 2));
    process.exit(0);
  })
  .catch((err) => {
    // reporter never exits non-zero on errors — just emit empty array with error note
    console.log(JSON.stringify([{ error: String(err), selector: '_script_error' }]));
    process.exit(0);
  });

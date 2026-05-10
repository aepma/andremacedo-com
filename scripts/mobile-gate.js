#!/usr/bin/env node
// Pre-deploy mobile DOM gate for andremacedo.com
// Usage: node scripts/mobile-gate.js [path/to/index.html]
// Output: JSON to stdout
// Exit: 0=pass, 1=any check failed, 2=script error

const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const INDEX_PATH = path.resolve(
  process.argv[2] || path.join(process.env.HOME, 'andremacedo.com/index.html')
);
const SITE_DIR = path.dirname(INDEX_PATH);
const METRICS_PATH = path.join(SITE_DIR, 'state/page-metrics.json');

async function runGate() {
  const browser = await chromium.launch({ args: ['--no-sandbox'] });
  try {
    const page = await browser.newPage({
      viewport: { width: 390, height: 844 },
      deviceScaleFactor: 2,
    });

    const fileUrl = 'file://' + INDEX_PATH;
    try {
      await page.goto(fileUrl, { waitUntil: 'load', timeout: 15000 });
    } catch (_) {}

    await page.waitForTimeout(2500);

    const checks = [];

    // CHECK 1 - HORIZONTAL_OVERFLOW
    const overflowResult = await page.evaluate(() => {
      const EPSILON = 5;
      const VIEWPORT_WIDTH = 390;
      const EXCLUDED_IDS = new Set(['scene-canvas', 'swarmPanel']);

      function isVisible(el) {
        const s = window.getComputedStyle(el);
        return (
          el.offsetWidth > 0 &&
          el.offsetHeight > 0 &&
          s.display !== 'none' &&
          s.visibility !== 'hidden' &&
          parseFloat(s.opacity) > 0.05
        );
      }

      // html and body set overflow-x:hidden to suppress scrollbar — that is intentional
      // and should not mask layout bugs. Only intermediate elements count as clip parents.
      function hasClippingAncestor(el) {
        let parent = el.parentElement;
        while (parent) {
          const tag = parent.tagName.toLowerCase();
          if (tag === 'html' || tag === 'body') break;
          const ox = window.getComputedStyle(parent).overflowX;
          if (ox === 'hidden' || ox === 'auto' || ox === 'scroll') return true;
          parent = parent.parentElement;
        }
        return false;
      }

      function getSelector(el) {
        if (el.id) return '#' + el.id;
        const cls = (typeof el.className === 'string' ? el.className : '')
          .trim()
          .split(/\s+/)
          .filter(Boolean)
          .slice(0, 2)
          .join('.');
        return el.tagName.toLowerCase() + (cls ? '.' + cls : '');
      }

      let worst = null;
      for (const el of document.querySelectorAll('*')) {
        const tag = el.tagName.toLowerCase();
        if (tag === 'html' || tag === 'body') continue;
        if (EXCLUDED_IDS.has(el.id)) continue;
        if (!isVisible(el)) continue;
        if (hasClippingAncestor(el)) continue;

        const rect = el.getBoundingClientRect();
        if (rect.right > VIEWPORT_WIDTH + EPSILON) {
          if (!worst || rect.right > worst.right) {
            worst = { selector: getSelector(el), right: Math.round(rect.right * 10) / 10 };
          }
        }
      }
      return worst;
    });

    checks.push({
      name: 'HORIZONTAL_OVERFLOW',
      passed: overflowResult === null,
      details: overflowResult
        ? `"${overflowResult.selector}" extends to ${overflowResult.right}px (viewport 390px + 5px epsilon)`
        : 'No overflow detected',
    });

    // CHECK 2 - TEXT_OVERLAP
    const textOverlapResult = await page.evaluate(() => {
      function isVisible(el) {
        const s = window.getComputedStyle(el);
        return (
          el.offsetWidth > 0 &&
          el.offsetHeight > 0 &&
          s.display !== 'none' &&
          s.visibility !== 'hidden' &&
          parseFloat(s.opacity) > 0.05
        );
      }

      // background-color is not inherited in CSS; checks whether the element
      // itself has an opaque card that would visually separate it from neighbors.
      function hasOpaqueBackground(el) {
        const bg = window.getComputedStyle(el).backgroundColor;
        if (!bg || bg === 'transparent') return false;
        const m = bg.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)/);
        if (!m) return false;
        const a = m[4] !== undefined ? parseFloat(m[4]) : 1;
        return a > 0.1;
      }

      function rectArea(r) {
        return Math.max(0, r.right - r.left) * Math.max(0, r.bottom - r.top);
      }

      function intersectArea(r1, r2) {
        return (
          Math.max(0, Math.min(r1.right, r2.right) - Math.max(r1.left, r2.left)) *
          Math.max(0, Math.min(r1.bottom, r2.bottom) - Math.max(r1.top, r2.top))
        );
      }

      function getSelector(el) {
        if (el.id) return '#' + el.id;
        const cls = (typeof el.className === 'string' ? el.className : '')
          .trim()
          .split(/\s+/)
          .filter(Boolean)
          .slice(0, 2)
          .join('.');
        return el.tagName.toLowerCase() + (cls ? '.' + cls : '');
      }

      const candidates = [];
      for (const el of document.querySelectorAll('*')) {
        if (!isVisible(el)) continue;
        if ((el.textContent || '').trim().length <= 4) continue;
        candidates.push(el);
      }

      // Leaf-ish: keep only elements that contain no other candidate
      const leafish = candidates.filter(
        (el) => !candidates.some((other) => other !== el && el.contains(other))
      );

      let worst = null;
      for (let i = 0; i < leafish.length; i++) {
        for (let j = i + 1; j < leafish.length; j++) {
          const a = leafish[i];
          const b = leafish[j];
          if (a.contains(b) || b.contains(a)) continue;

          const ra = a.getBoundingClientRect();
          const rb = b.getBoundingClientRect();
          const ia = intersectArea(ra, rb);
          if (ia <= 0) continue;

          const minArea = Math.min(rectArea(ra), rectArea(rb));
          if (minArea <= 0) continue;

          const ratio = ia / minArea;
          if (ratio > 0.4 && !hasOpaqueBackground(a) && !hasOpaqueBackground(b)) {
            if (!worst || ratio > worst.ratio) {
              worst = {
                ratio: Math.round(ratio * 100) / 100,
                a: getSelector(a),
                b: getSelector(b),
              };
            }
          }
        }
      }
      return worst;
    });

    checks.push({
      name: 'TEXT_OVERLAP',
      passed: textOverlapResult === null,
      details: textOverlapResult
        ? `Overlap ${textOverlapResult.ratio} between "${textOverlapResult.a}" and "${textOverlapResult.b}"`
        : 'No significant text overlap detected',
    });

    // CHECK 3 - HEIGHT_RATIO (metrics file read in Node.js context, not browser)
    const mobileHeight = await page.evaluate(
      () => document.documentElement.scrollHeight
    );
    let heightPassed = true;
    let heightDetails;

    try {
      const metrics = JSON.parse(fs.readFileSync(METRICS_PATH, 'utf8'));
      const desktopHeight = metrics.rendered_height_px;
      if (!desktopHeight || desktopHeight <= 0) {
        heightDetails = 'rendered_height_px missing from page-metrics.json — skipping';
      } else {
        const ratio = mobileHeight / desktopHeight;
        const ratioStr = Math.round(ratio * 100) / 100;
        heightDetails = `mobile=${mobileHeight}px desktop=${desktopHeight}px ratio=${ratioStr}`;
        if (ratio > 1.8) {
          heightPassed = false;
          heightDetails = `FAIL: mobile=${mobileHeight}px > desktop=${desktopHeight}px × 1.8 (ratio=${ratioStr})`;
        }
      }
    } catch (_) {
      heightDetails = 'state/page-metrics.json not found — skipping';
    }

    checks.push({ name: 'HEIGHT_RATIO', passed: heightPassed, details: heightDetails });

    // CHECK 4 - MASTHEAD_WHITESPACE
    const mastheadResult = await page.evaluate(() => {
      const masthead = document.querySelector('.program-masthead');
      if (!masthead) return { skipped: true };

      const text = masthead.innerText || '';
      const camelCollision = /[a-z][A-Z]/.test(text);

      const spans = masthead.querySelectorAll('span');
      let adjacentCollision = false;
      let adjacentDetails = null;
      if (spans.length >= 2) {
        const r1 = spans[0].getBoundingClientRect();
        const r2 = spans[1].getBoundingClientRect();
        if (r1.width > 0 && r2.width > 0 && Math.abs(r1.right - r2.left) < 1) {
          adjacentCollision = true;
          adjacentDetails = `span[0].right=${Math.round(r1.right)} span[1].left=${Math.round(r2.left)}`;
        }
      }

      return {
        skipped: false,
        camelCollision,
        adjacentCollision,
        text: text.slice(0, 120),
        adjacentDetails,
      };
    });

    let mastheadPassed = true;
    let mastheadDetails;
    if (mastheadResult.skipped) {
      mastheadDetails = '.program-masthead not found — skipping';
    } else if (mastheadResult.camelCollision) {
      mastheadPassed = false;
      mastheadDetails = `camelCase collision in masthead text: "${mastheadResult.text}"`;
    } else if (mastheadResult.adjacentCollision) {
      mastheadPassed = false;
      mastheadDetails = `Adjacent spans with zero gap: ${mastheadResult.adjacentDetails}`;
    } else {
      mastheadDetails = 'No whitespace issues';
    }

    checks.push({
      name: 'MASTHEAD_WHITESPACE',
      passed: mastheadPassed,
      details: mastheadDetails,
    });

    // CHECK 5 - MOBILE_INTERACTIVITY
    const interactivityResult = await page.evaluate(() => {
      const results = {};

      // 5a: __telosMobileInvariantsInstalled flag
      results.invariantsFlagSet = window.__telosMobileInvariantsInstalled === true;

      // 5b: virtual keyboard present and visible with ≥5 keys
      const kb = document.querySelector('.telos-virtual-keyboard');
      results.kbExists = !!kb;
      if (kb) {
        const s = window.getComputedStyle(kb);
        results.kbVisible = (
          kb.offsetWidth > 0 && kb.offsetHeight > 0 &&
          s.display !== 'none' && s.visibility !== 'hidden' &&
          parseFloat(s.opacity || '1') > 0.05
        );
        results.kbKeyCount = kb.querySelectorAll('.telos-virtual-key').length;
        results.kbHasEnoughKeys = results.kbKeyCount >= 5;
      } else {
        results.kbVisible = false;
        results.kbKeyCount = 0;
        results.kbHasEnoughKeys = false;
      }

      // 5c: touch-to-mouse bridge — synthesize touchstart and verify mousedown fires
      let bridgeMousedownFired = false;
      const listener = () => { bridgeMousedownFired = true; };
      document.addEventListener('mousedown', listener, {once: true, capture: true});
      try {
        const touch = new Touch({
          identifier: 1, target: document.body,
          clientX: 195, clientY: 400, screenX: 195, screenY: 400,
          pageX: 195, pageY: 400, radiusX: 5, radiusY: 5, rotationAngle: 0, force: 1
        });
        const touchEvt = new TouchEvent('touchstart', {
          bubbles: true, cancelable: true, view: window,
          touches: [touch], targetTouches: [touch], changedTouches: [touch]
        });
        document.body.dispatchEvent(touchEvt);
      } catch (_) {}
      document.removeEventListener('mousedown', listener, {capture: true});
      results.bridgeWorks = bridgeMousedownFired;

      return results;
    });

    const int = interactivityResult;
    const subFails = [];
    if (!int.invariantsFlagSet)  subFails.push('__telosMobileInvariantsInstalled not true');
    if (!int.kbExists)            subFails.push('.telos-virtual-keyboard not found');
    else if (!int.kbVisible)      subFails.push('.telos-virtual-keyboard not visible');
    else if (!int.kbHasEnoughKeys) subFails.push(`.telos-virtual-keyboard has only ${int.kbKeyCount} keys (need ≥5)`);
    if (!int.bridgeWorks)         subFails.push('touch-to-mouse bridge did not fire mousedown');

    checks.push({
      name: 'MOBILE_INTERACTIVITY',
      passed: subFails.length === 0,
      details: subFails.length === 0
        ? `invariants installed, keyboard visible (${int.kbKeyCount} keys), touch bridge works`
        : subFails.join('; '),
    });

    await browser.close();
    return checks;
  } catch (err) {
    await browser.close().catch(() => {});
    throw err;
  }
}

runGate()
  .then((checks) => {
    const failed = checks.filter((c) => !c.passed);
    const gate = failed.length === 0 ? 'pass' : 'fail';
    const summary =
      gate === 'pass'
        ? 'All mobile checks passed'
        : 'Failed: ' + failed.map((c) => c.name).join(', ');
    console.log(JSON.stringify({ gate, checks, summary }, null, 2));
    process.exit(gate === 'pass' ? 0 : 1);
  })
  .catch((err) => {
    console.log(
      JSON.stringify(
        { gate: 'error', checks: [], summary: 'Script error: ' + err.message },
        null,
        2
      )
    );
    process.exit(2);
  });

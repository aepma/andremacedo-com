#!/usr/bin/env python3
"""
Playwright click-intercept test.
Determines what element is on top at .ar-feature and .ar-row coordinates,
and attempts an actual click to verify navigation.
"""
import asyncio
from playwright.async_api import async_playwright

URL = "https://andremacedo.com"
VIEWPORT = {"width": 1440, "height": 900}

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport=VIEWPORT)
        page = await context.new_page()

        print(f"[STEP 1] Loading {URL} ...")
        await page.goto(URL, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(4000)
        print(f"  Page loaded. URL: {page.url}")
        print(f"  Viewport: {VIEWPORT['width']}x{VIEWPORT['height']}")

        # Scroll to .ar-feature
        print("\n[STEP 2] Scrolling to .ar-feature ...")
        await page.evaluate("""
            (function() {
                var el = document.querySelector('.ar-feature');
                if (el) el.scrollIntoView({behavior: 'instant', block: 'center'});
            })()
        """)
        await page.wait_for_timeout(1500)
        scrollY = await page.evaluate("window.scrollY")
        print(f"  scrollY after scroll: {scrollY}")

        # Overlay state
        overlay_state = await page.evaluate("""
            (function() {
                var o = document.getElementById('overlay');
                return {
                    classes: o ? o.className : 'not found',
                    opacity: o ? window.getComputedStyle(o).opacity : 'n/a',
                    pointerEvents: o ? window.getComputedStyle(o).pointerEvents : 'n/a'
                };
            })()
        """)
        print(f"\n  #overlay state: {overlay_state}")

        # elementFromPoint for .ar-feature
        print("\n[STEP 3a] elementFromPoint at .ar-feature center:")
        feature_info = await page.evaluate("""
            (function() {
                var el = document.querySelector('.ar-feature');
                if (!el) return {error: 'element not found'};
                var r = el.getBoundingClientRect();
                var cx = r.left + r.width / 2;
                var cy = r.top  + r.height / 2;
                var top = document.elementFromPoint(cx, cy);
                function info(e) {
                    if (!e) return null;
                    var cs = window.getComputedStyle(e);
                    return {
                        tag: e.tagName,
                        id: e.id || '',
                        cls: (e.className || '').toString().slice(0, 100),
                        zIndex: cs.zIndex,
                        position: cs.position,
                        pointerEvents: cs.pointerEvents,
                        href: e.href || '',
                        text: (e.innerText || '').slice(0, 80)
                    };
                }
                return {
                    target: info(el),
                    topmost: info(top),
                    cx: Math.round(cx),
                    cy: Math.round(cy),
                    sameElement: top === el
                };
            })()
        """)
        if 'error' in feature_info:
            print(f"  ERROR: {feature_info['error']}")
        else:
            print(f"  Center coords: ({feature_info['cx']}, {feature_info['cy']})")
            t = feature_info['topmost']
            print(f"  TOPMOST ELEMENT: <{t['tag'].lower()}> id='{t['id']}' class='{t['cls']}'")
            print(f"    z-index={t['zIndex']} position={t['position']} pointer-events={t['pointerEvents']}")
            if t['href']:
                print(f"    href={t['href']}")
            print(f"    text: {repr(t['text'])}")
            print(f"  Target (.ar-feature) is topmost? {feature_info['sameElement']}")

        # elementFromPoint for first .ar-row
        print("\n[STEP 3b] elementFromPoint at first .ar-row center:")
        row_info = await page.evaluate("""
            (function() {
                var el = document.querySelector('.ar-row');
                if (!el) return {error: 'element not found'};
                var r = el.getBoundingClientRect();
                var cx = r.left + r.width / 2;
                var cy = r.top  + r.height / 2;
                var top = document.elementFromPoint(cx, cy);
                function info(e) {
                    if (!e) return null;
                    var cs = window.getComputedStyle(e);
                    return {
                        tag: e.tagName,
                        id: e.id || '',
                        cls: (e.className || '').toString().slice(0, 100),
                        zIndex: cs.zIndex,
                        position: cs.position,
                        pointerEvents: cs.pointerEvents,
                        href: e.href || '',
                        text: (e.innerText || '').slice(0, 80)
                    };
                }
                return {
                    target: info(el),
                    topmost: info(top),
                    cx: Math.round(cx),
                    cy: Math.round(cy),
                    sameElement: top === el
                };
            })()
        """)
        if 'error' in row_info:
            print(f"  ERROR: {row_info['error']} (ar-row may not be in DOM yet)")
        else:
            print(f"  Center coords: ({row_info['cx']}, {row_info['cy']})")
            t = row_info['topmost']
            print(f"  TOPMOST ELEMENT: <{t['tag'].lower()}> id='{t['id']}' class='{t['cls']}'")
            print(f"    z-index={t['zIndex']} position={t['position']} pointer-events={t['pointerEvents']}")
            if t['href']:
                print(f"    href={t['href']}")
            print(f"  Target (.ar-row) is topmost? {row_info['sameElement']}")

        # Stacking context chain for .ar-feature
        print("\n[STEP 3c] Stacking context chain for .ar-feature:")
        chain = await page.evaluate("""
            (function() {
                var el = document.querySelector('.ar-feature');
                if (!el) return [];
                var chain = [];
                var e = el;
                while (e && e.tagName !== 'HTML') {
                    var cs = window.getComputedStyle(e);
                    chain.push({
                        tag: e.tagName,
                        id: e.id || '',
                        cls: (e.className || '').toString().slice(0, 50),
                        zIndex: cs.zIndex,
                        position: cs.position,
                        pointerEvents: cs.pointerEvents
                    });
                    e = e.parentElement;
                }
                return chain;
            })()
        """)
        for item in chain:
            print(f"  <{item['tag'].lower()}> id='{item['id']}' cls='{item['cls']}' z={item['zIndex']} pos={item['position']} pe={item['pointerEvents']}")

        # Attempt actual click
        print("\n[STEP 3d] Attempting .click() on .ar-feature link ...")
        url_before = page.url
        navigated = False
        url_after = url_before
        try:
            ar_feature = page.locator('.ar-feature').first
            await ar_feature.click(timeout=5000, force=False)
            await page.wait_for_timeout(2000)
            url_after = page.url
            navigated = url_after != url_before
            print(f"  URL before: {url_before}")
            print(f"  URL after:  {url_after}")
            if navigated and '/experiments/' in url_after:
                print(f"  RESULT: SUCCESS — clicked and navigated to {url_after}")
            elif navigated:
                print(f"  RESULT: PARTIAL — navigated but not to /experiments/: {url_after}")
            else:
                print(f"  RESULT: FAILED — no navigation occurred")
        except Exception as e:
            print(f"  Click raised exception: {type(e).__name__}: {e}")
            url_after = page.url
            print(f"  URL after exception: {url_after}")

        await browser.close()
        print("\n[DONE]")

asyncio.run(main())

// End-to-end test in headless Chrome against a running copy of the site (local or live).
//   node scripts/e2e.mjs http://localhost:4651/land-index-fund
// Exits 1 on any failed step or any console error.
import { launch } from "./cdp.mjs";

const base = (process.argv[2] || "http://localhost:4651/land-index-fund").replace(/\/$/, "");
const { page, close } = await launch();
const results = [];
async function step(name, fn) {
  try { await fn(); results.push(["ok", name]); }
  catch (e) { results.push(["FAIL", name + ": " + e.message]); }
}
function assert(cond, msg) { if (!cond) throw new Error(msg); }

try {
  await page.viewport(1280, 900, false);
  await step("home page renders with map, tiles and notice", async () => {
    await page.goto(base + "/");
    assert(await page.eval("document.querySelectorAll('h1').length === 1"), "no single h1");
    assert(await page.eval("document.querySelectorAll('.tile').length >= 2"), "tiles missing");
    assert(await page.eval("!!document.querySelector('object[data$=\"us-counties.svg\"]')"), "map missing");
    assert(await page.eval("document.body.innerText.includes('Not investment advice')"), "notice missing");
  });
  await step("county finder finds Story County, Iowa and opens it", async () => {
    await page.eval("document.getElementById('q').focus()");
    await page.send("Input.insertText", { text: "story county iowa" });
    await page.waitFor("document.querySelectorAll('#q-results a').length > 0");
    const first = await page.eval("document.querySelector('#q-results a').textContent");
    assert(first.includes("Story County"), "first result is " + first);
    const nav = page.once("Page.loadEventFired");
    await page.send("Input.dispatchKeyEvent", { type: "keyDown", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13 });
    await nav;
    await new Promise((r) => setTimeout(r, 300));
    const href = await page.eval("location.pathname");
    assert(href.endsWith("/iowa/story-county/"), "landed on " + href);
  });
  await step("county page shows value tiles, chart and source tables", async () => {
    assert(await page.eval("document.querySelectorAll('.tile').length >= 2"), "tiles missing");
    assert(await page.eval("/\\$[0-9,]+/.test(document.querySelector('.tile .tv').textContent)"), "tile has no dollar value");
    assert(await page.eval("document.querySelectorAll('table.data').length >= 2"), "tables missing");
  });
  await step("chart hover shows a tooltip with values", async () => {
    const box = await page.eval("(() => { const s = [...document.querySelectorAll('.chart-wrap')].find(w => w.offsetParent).querySelector('svg').getBoundingClientRect(); return {x: s.left + s.width * 0.6, y: s.top + s.height / 2}; })()");
    await page.send("Input.dispatchMouseEvent", { type: "mouseMoved", x: box.x, y: box.y });
    await page.waitFor("[...document.querySelectorAll('.tip')].some(t => !t.hidden && /\\$/.test(t.textContent))");
  });
  await step("state page table sorts by value", async () => {
    await page.goto(base + "/iowa/");
    const col = await page.eval("[...document.querySelectorAll('table.sortable')[0].tHead.rows[0].cells].findIndex(c => /census/.test(c.textContent))");
    assert(col >= 0, "no census column");
    const read = `[...document.querySelector('table.sortable').tBodies[0].rows].map(r => parseFloat(r.cells[${col}].getAttribute('data-v'))).filter(v => !isNaN(v))`;
    await page.eval(`document.querySelector('table.sortable').tHead.rows[0].cells[${col}].click()`);
    const desc = await page.eval(read);
    assert(desc.length > 2 && desc.every((v, i) => i === 0 || desc[i - 1] >= v), "not sorted descending");
    await page.eval(`document.querySelector('table.sortable').tHead.rows[0].cells[${col}].click()`);
    const asc = await page.eval(read);
    assert(asc.every((v, i) => i === 0 || asc[i - 1] <= v), "not sorted ascending");
  });
  await step("embed card renders a county", async () => {
    await page.goto(base + "/embed/?fips=19169");
    await page.waitFor("(document.querySelector('#card h1') || {}).textContent?.includes('Story County')");
    assert(await page.eval("/\\$[0-9,]+/.test(document.getElementById('card').textContent)"), "no value in card");
  });
  await step("pages fit a 375px phone screen", async () => {
    await page.viewport(375, 812, true);
    const bad = [];
    for (const p of ["/", "/iowa/", "/iowa/story-county/", "/rankings/", "/data/", "/methodology/"]) {
      await page.goto(base + p);
      const w = await page.eval("document.documentElement.scrollWidth");
      if (w > 376) {
        const culprits = await page.eval("[...document.querySelectorAll('main *')].filter(e => e.getBoundingClientRect().right > 376 && !e.closest('.scroll')).slice(0, 3).map(e => e.tagName + '.' + e.className).join(', ')");
        bad.push(p + " is " + w + "px wide (" + culprits + ")");
      }
      if (p === "/iowa/story-county/") {
        const narrow = await page.eval("!!document.querySelector('.chart-wrap.narrow').offsetParent");
        if (!narrow) bad.push("phone chart not shown");
      }
    }
    assert(!bad.length, bad.join("; "));
  });
  await step("no console errors", async () => {
    assert(!page.errors.length, page.errors.slice(0, 5).join(" | "));
  });
} finally {
  await close();
}
for (const [s, n] of results) console.log(s.padEnd(5), n);
if (results.some(([s]) => s !== "ok")) process.exitCode = 1;

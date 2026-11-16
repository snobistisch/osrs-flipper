/* Execute the real inline browser code with deterministic storage/HTTP/DOM. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '../docs/index.html'), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
new vm.Script(script); // Syntax-check event wiring as well as the tested functions.
const library = script.slice(0, script.indexOf('$("#start").addEventListener'));

function setup() {
  const storage = new Map(), elements = new Map();
  const context = vm.createContext({
    console, URL, AbortController, setTimeout, clearTimeout,
    alert() {},
    localStorage: {
      getItem: (key) => storage.get(key) ?? null,
      setItem: (key, value) => storage.set(key, value),
      removeItem: (key) => storage.delete(key),
      key: (index) => [...storage.keys()][index],
      get length() { return storage.size; },
    },
    document: {
      addEventListener() {}, querySelectorAll: () => [],
      querySelector: (selector) => {
        if (!elements.has(selector)) elements.set(selector, {
          classList: { add() {}, remove() {}, toggle() {} }, style: {},
          innerHTML: '', textContent: '', value: '',
        });
        return elements.get(selector);
      },
    },
  });
  vm.runInContext(library, context);
  return { context, storage, elements, run: (code) => vm.runInContext(code, context) };
}

test('tax thresholds, cap and free undercut preserve exact proceeds', () => {
  const { run } = setup();
  for (const sell of [49, 50, 99, 100, 249999999, 250000000, 1800000000]) {
    assert.equal(run(`geTax(${sell}, false)`), Math.min(5000000, Math.floor(sell / 50)));
    assert.equal(run(`netRevenue(taxBoundaryUndercut(${sell}, false), false)`),
      run(`netRevenue(${sell}, false)`));
  }
  assert.equal(run('geTax(1800000000, true)'), 0);
  assert.equal(run('bondConversionFee(5000000, true)'), 500000);
  assert.equal(run('netMargin(4800000, 5000000, true, true)'), -300000);
  assert.throws(() => run('parseGp("999999999999999999999b")'));
  assert.equal(run('parseGp("1.0005k")'), 1001);
});

test('null and array API envelopes fail; malformed rows are sanitized', async () => {
  const { run, context } = setup();
  for (const data of [null, [], 'invalid']) {
    run('retryAt.clear()');
    context.fetch = async () => ({ ok: true, json: async () => ({ data }) });
    await assert.rejects(run('fetchLatest()'), /data object/);
  }
  run('retryAt.clear()');
  context.fetch = async () => ({ ok: true, json: async () => ({ data: {
    1: { high: '100', low: -1, highTime: true, lowTime: 1e30 }, 2: null,
  } }) });
  const result = await run('fetchLatest()');
  assert.equal(result[1].high, null);
  assert.equal(result[1].lowTime, null);
  assert.equal(result[2], undefined);
});

test('concurrent refreshes share a request; permanent errors are not retried', async () => {
  const { run, context } = setup();
  let calls = 0;
  context.fetch = async () => {
    calls++;
    return { ok: true, json: async () => ({ data: {} }) };
  };
  await Promise.all([run('fetchLatest()'), run('fetchLatest()')]);
  assert.equal(calls, 1);
  context.fetch = async () => { calls++; return { ok: false, status: 404 }; };
  await assert.rejects(run('getJson("/missing")'), /404/);
  assert.equal(calls, 2);
});

test('stale data is bounded and history is sorted and sanitized', async () => {
  const { run } = setup();
  run('memo.set("test", {at: Date.now() - 400000, value: 42})');
  await assert.rejects(run('cached("test", 30, async () => {throw new Error("offline")})'));
  const result = run('cleanHistory([null, {timestamp: 2, avgHighPrice: 0, highPriceVolume: 50}, {timestamp: 1}])');
  assert.equal(result[0].timestamp, 1);
  assert.equal(result[1].highPriceVolume, 0);
});

test('decimal averages are rounded half up; unreadable responses throw', async () => {
  const { run, context } = setup();
  const rows = run(`cleanHistory([{timestamp: 1794825000, avgHighPrice: 649036.25,
    avgLowPrice: 643121, highPriceVolume: 4, lowPriceVolume: 7}])`);
  assert.equal(rows[0].avgHighPrice, 649036);
  assert.equal(rows[0].highPriceVolume, 4);
  assert.equal(rows[0].avgLowPrice, 643121);
  assert.equal(rows[0].lowPriceVolume, 7);
  for (const [raw, expected] of [['648416.5', 648417], ['0.4', null], ['-3', null],
    ['"12"', null], ['true', null], ['12', 12]]) {
    assert.equal(run(`averagePrice(${raw})`), expected, raw);
    const row = run(`cleanHistory([{timestamp: 1, avgHighPrice: ${raw}, highPriceVolume: 5}])`)[0];
    assert.equal(row.avgHighPrice, expected, raw);
    assert.equal(row.highPriceVolume, expected ? 5 : 0, raw);
  }
  assert.throws(() => run(`cleanHistory(Array.from({length: 10}, (_, i) => ({timestamp: i + 1,
    avgHighPrice: "100", avgLowPrice: 99.5, highPriceVolume: 1, lowPriceVolume: 1})))`), /\/timeseries/);
  assert.equal(run(`cleanHistory(Array.from({length: 10}, (_, i) => ({timestamp: i + 1,
    avgHighPrice: 100, avgLowPrice: i < 4 ? "x" : 99})))`).length, 10);
  const data = Object.fromEntries(Array.from({ length: 40 }, (_, i) => [String(i + 1), {
    avgHighPrice: i % 2 ? null : '1', avgLowPrice: 10.25, highPriceVolume: 1, lowPriceVolume: 1 }]));
  context.fetch = async () => ({ ok: true, json: async () => ({ data }) });
  await assert.rejects(run('fetchInterval("5m")'), /\/5m/);
});

test('reservations survive profile changes and derive commitment from quantity', () => {
  const { run, storage } = setup();
  const lock = { slot: 0, id: 1, name: 'Test', qty: 10, buy: 100, sell: 110,
    commit: 0, expected: 10, lockedAt: 1 };
  storage.set('osrs-flipper.slot-locks.v1', JSON.stringify({ 'members:active:0': [lock] }));
  assert.equal(run('locksFor({account:"members", strategy:"overnight", horizonHours:8, slots:8})[0].commit'), 1000);
  run('saveProfileLocks({account:"members", strategy:"overnight", horizonHours:8}, locksFor({slots:8}))');
  assert.equal(run('locksFor({account:"members", strategy:"active", slots:8}).length'), 1);
});

test('manual offer sizing respects remaining bank and connected buy limits', () => {
  const { run, storage } = setup();
  storage.set('osrs-flipper.slot-locks.v1', JSON.stringify({ old: [
    { slot: 0, id: 1, name: 'Potion', qty: 9, buy: 100, sell: 110,
      commit: 900, expected: 10, lockedAt: 1, limitGroup: 'potion' },
  ] }));
  run('state.config = {capital:1000, maxPositionCapital:1000}; rescoreAllocated = () => {}');
  const row = '{id:2, buy:100, qty:10, limit:10, limitGroup:"potion", mode:"active", horizonHours:4}';
  assert.equal(run(`monitorableRow(${row}).allocatedQty`), 1);
  run('state.config.capital = 900');
  assert.equal(run(`monitorableRow(${row}).allocatedQty`), 0);
});

test('invalid stored records cannot crash rendering', () => {
  const { run, storage } = setup();
  storage.set('osrs-flipper.executions.v1', '{}');
  assert.equal(run('loadExecutions().length'), 0);
  storage.set('osrs-flipper.executions.v1', '[null, {}, {"qty":0}]');
  assert.doesNotThrow(() => run('renderExecutions()'));
  storage.set('osrs-flipper.holdings.v1', '[null, {}]');
  assert.doesNotThrow(() => run('renderPortfolio()'));
  assert.equal(run('saveExecutions([])'), false);
  assert.equal(storage.get('osrs-flipper.executions.v1'), '[null, {}, {"qty":0}]');
});

test('legacy monitored offers reserve bank even without a stored slot lock', () => {
  const { run, storage } = setup();
  storage.set('osrs-flipper.executions.v1', JSON.stringify([
    { key:'one', itemId:1, name:'Test', qty:10, buy:100, sell:110, status:'watching', createdAt:1 },
  ]));
  assert.equal(run('locksFor({slots:8})[0].commit'), 1000);
  run('state.config = {slots:8, account:"members", strategy:"active"}; replanFromCurrentData = () => {}; unlockSlot(0)');
  assert.equal(run('locksFor({slots:8}).length'), 0);
  assert.equal(run('loadExecutions()[0].status'), 'cancelled');
});

test('late chart responses cannot replace the latest selected item', async () => {
  const { run, context, elements } = setup();
  const resolve = {};
  context.fetch = (url) => new Promise((done) => {
    const id = new URL(url).searchParams.get('id');
    resolve[id] = (data) => done({ok:true, json:async () => ({data})});
  });
  run('renderSessionStats = () => {}; wireChartHover = () => {}; renderChart = (points) => String(points[0].timestamp); state.selected = 1; state.timestep = "1h"');
  const first = run('loadChart()');
  run('state.selected = 2');
  const second = run('loadChart()');
  resolve[2]([{ timestamp: 222 }]);
  await second;
  resolve[1]([{ timestamp: 111 }]);
  await first;
  assert.equal(elements.get('#chart').innerHTML, '222');
});

/* ---- audit 2026-10-01 ---- */

const bondRow = (extra = '') => `{id:13190, buy:9000000, sell:10000000,
  bondFee:1000000, qty:5, fillLowQty:5, fillHighQty:5, capitalNeeded:50000000,
  rankingValue:10, expected:10, category:"other", mode:"active", horizonHours:4,
  modelBuyVolume1h:100, modelSellVolume1h:100, buyShare:.1, sellShare:.1,
  margin:100, age:1, ofi:0, drift:0, scoredAt:1785000000, competitors:8,
  buyImprovement:0, sellImprovement:0${extra}}`;

test('bond allocation and reservations fund the conversion fee', () => {
  const { run, storage } = setup();
  const [qty, allocated, binding] = run(`(() => { const rows = [${bondRow(
    ', bond:true, pFill:1, deep:true')}];
    const selection = allocatePortfolio(rows, 19000000, 8, [],
      { strategy: "active", fundingEvidence: "history", maxPositionCapital: 19000000 });
    return [rows[0].allocatedQty, rows[0].allocated, selection.binding]; })()`);
  // 9m + 1m fee per bond: a 19m bank holds one, not the two the buy price fits.
  assert.equal(qty, 1);
  assert.equal(allocated, 10000000);
  assert.equal(binding, 'capital');
  storage.set('osrs-flipper.slot-locks.v1', JSON.stringify({ any: [
    { slot: 0, id: 13190, name: 'Old school bond', qty: 2, buy: 9000000,
      sell: 10000000, commit: 0, expected: 1, lockedAt: 1 },
  ] }));
  assert.equal(run('locksFor({slots:8})[0].commit'), 20000000);
  assert.equal(run('bondConversionFee(2147483647, true)'), 214748364);
});

test('a stale per-item history does not mark the price feed stale', async () => {
  const { run } = setup();
  run('memo.set("ts:1:6h", {at: Date.now() - 1900000, value: [], stale: false})');
  await run('cached("ts:1:6h", TIMESERIES_TTL, async () => { throw new Error("down") })');
  assert.equal(run('feedIsStale()'), false);
  run('memo.set("latest", {at: Date.now() - 40000, value: {}, stale: false}); retryAt.clear()');
  await run('cached("latest", LATEST_TTL, async () => { throw new Error("down") })');
  assert.equal(run('feedIsStale()'), true);
});

test('confidence sorts by its derived rank', () => {
  const { run } = setup();
  run(`confidenceLabel = (row) => row.label;
       state.rows = [{name:"a", label:"medium"}, {name:"b", label:"high"},
                     {name:"c", label:"speculative"}];
       state.sortKey = "confidence"; state.sortDesc = true`);
  assert.equal(run('sortedRows().map((row) => row.name).join()'), 'b,a,c');
});

test('edge probability matches the Python posterior rule', () => {
  const { run } = setup();
  assert.equal(run('probabilityAboveMean(empiricalBayes([1, 1, 1], [1, 1, 1]), 0)'), 0.5);
  const fit = 'empiricalBayes([0, 1, 5, 9], [0.1, 0.1, 0.1, 0.1])';
  assert.ok(run(`probabilityAboveMean(${fit}, 3)`) > 0.99);
  assert.ok(run(`probabilityAboveMean(${fit}, 0)`) < 0.01);
});

test('an expired mapping serves an outage and exemptions are applied on read', async () => {
  const { run, storage, context } = setup();
  storage.set('osrs-flipper.mapping.v3', JSON.stringify({ at: 1, items: {
    379: { name: 'Lobster', members: false, limit: 13000, exempt: false },
  } }));
  context.fetch = async () => ({ ok: false, status: 503 });
  const items = await run('fetchMapping()');
  assert.equal(items[379].exempt, true);
});

test('saved Active offers get a reprice reminder, then a cancel deadline', () => {
  const { run } = setup();
  const offer = '({ mode: "active", createdAt: 0, qty: 100, bought: 0, sold: 0,' +
    ' repriceCheckSeconds: 900, cancelBySeconds: 7200 })';
  assert.equal(run(`executionTimingNote(${offer}, 600 * 1000)`), null);
  assert.match(run(`executionTimingNote(${offer}, 1000 * 1000)`), /not one unit has bought/);
  assert.equal(run(`executionTimingNote({ ...${offer}, bought: 5 }, 1000 * 1000)`), null);
  assert.match(run(`executionTimingNote({ ...${offer}, bought: 5 }, 7300 * 1000)`),
    /cancel what is left/);
  assert.equal(run(`executionTimingNote({ ...${offer}, mode: "overnight" }, 9e9)`), null);
  // Offers saved before the band existed still get the 45-minute rule.
  assert.match(run('executionTimingNote({ mode: "active", createdAt: 0, qty: 1 }, 2800 * 1000)'),
    /check at 45m/);
});

test('the ETA is shown as a band and Active funding meets the completion target', () => {
  const { run } = setup();
  const b = run(`scoreFlip({ buy: 1000, sell: 1080, margin: 58, qty: 200, depth: 0,
    buyVolume1h: 2000, sellVolume1h: 2000, quoteAge: 60, ofi: 0, drift: 0,
    now: 1785000000, buyShare: 0.125, sellShare: 0.125 })`);
  assert.ok(b.roundTripP50Seconds < b.roundTripP80Seconds);
  assert.ok(b.roundTripP80Seconds < b.roundTripP90Seconds);
  assert.equal(b.totalSeconds, b.roundTripP50Seconds);
  const band = run(`etaBand(${JSON.stringify(b)})`);
  assert.match(band, /TYPICAL .* 80% BY .* 90% BY /);
  const choice = run(`optimiseExecution({ baseBuy: 1000, baseSell: 1100, exempt: false,
    bond: false, limit: 10000, config: { capital: 5000000, maxPositionCapital: 5000000,
    strategy: "active", horizonHours: 4 }, buyVolume1h: 3000, sellVolume1h: 2500,
    quoteAge: 60, ofi: 0, drift: 0, now: 1785000000, competitors: 9,
    highalch: null, natureCost: 100 })`);
  assert.ok(choice.breakdown.pFill >= run('CAL.active_target_completion') - 1e-9);
  assert.ok(choice.meanCapacityQty > choice.qty);
});

test('switching to Away advises on Active offers still running', () => {
  const { run } = setup();
  run('state.config = { strategy: "overnight" }');
  const offer = '({ mode: "active", createdAt: 0, qty: 100, sold: 0, repriceCheckSeconds: 900 })';
  assert.match(run(`executionTimingNote({ ...${offer}, bought: 0 }, 60 * 1000)`),
    /Cancel it, or replace it with the Away plan/);
  assert.match(run(`executionTimingNote({ ...${offer}, bought: 40 }, 60 * 1000)`),
    /leave the sell offer listed/);
  run('state.config = { strategy: "active" }');
  assert.equal(run(`executionTimingNote({ ...${offer}, bought: 0 }, 60 * 1000)`), null);
});

test('Max profit ranks profit per flip, caps one buy limit and charges unsold stock', () => {
  const { run } = setup();
  const execution = (strategy, buy, sell, volume, limit) => run(`optimiseExecution({
    baseBuy: ${buy}, baseSell: ${sell}, exempt: false, bond: false, limit: ${limit},
    config: { capital: 50000000, maxPositionCapital: 50000000, strategy: "${strategy}",
      horizonHours: ${strategy === 'profit' ? 'PROFIT_HORIZON_HOURS' : 4} },
    buyVolume1h: ${volume}, sellVolume1h: ${volume}, quoteAge: 60, ofi: 0, drift: 0,
    now: 1785000000, competitors: 8, highalch: null, natureCost: 100 })`);
  const fast = [1000, 1030, 6000, 2000], slow = [20000, 21500, 30, 100];
  assert.ok(execution('active', ...fast).breakdown.rankingValue >
    execution('active', ...slow).breakdown.rankingValue);
  const profitFast = execution('profit', ...fast), profitSlow = execution('profit', ...slow);
  assert.ok(profitSlow.breakdown.rankingValue > profitFast.breakdown.rankingValue);
  assert.equal(profitSlow.breakdown.rankingValue, profitSlow.breakdown.expected);
  assert.equal(profitFast.breakdown.horizonHours, 24);
  // A deep book still buys one window, not the six a 24h Away horizon reaches.
  assert.equal(execution('profit', 1000, 1100, 200000, 500).qty, 500);
  assert.equal(run('effectiveBuyLimit(500, 24, "profit")'), 500);

  const score = (qty) => run(`scoreFlip({ buy: 1000, sell: 1080, margin: 58, qty: ${qty},
    depth: 0, buyVolume1h: 150, sellVolume1h: 150, quoteAge: 60, ofi: 0, drift: 0,
    now: 1785000000, buyShare: 0.125, sellShare: 0.125, mode: "profit" })`);
  const heavy = score(450);
  assert.ok(heavy.downsideRisk > score(50).downsideRisk);
  assert.ok(score(1000).rankingValue < score(200).rankingValue);
  assert.ok(heavy.roundTripP50Seconds < heavy.roundTripP90Seconds);
  assert.ok('holding risk' in heavy.factors);
  const notes = run(`timingWarnings(${JSON.stringify(heavy)})`);
  assert.ok(notes.some((note) => /^inventory risk: .*24h deadline/.test(note)), notes.join(' | '));
  assert.ok(notes.some((note) => note.startsWith('fill odds:')));
});

test('Max profit is a selectable, saved strategy and old saves load as before', () => {
  const { run, storage } = setup();
  const prefs = 'osrs-flipper.preferences.v2';
  for (const [saved, restored] of [['profit', 'profit'], ['overnight', 'overnight'],
    ['active', 'active'], ['away', 'active'], [undefined, 'active']]) {
    storage.set(prefs, JSON.stringify({ strategy: saved }));
    run('restorePreferences()');
    assert.equal(run('$("#f-strategy").value'), restored, String(saved));
  }
  run('state.capital = 20000000; $("#f-strategy").value = "profit"; $("#f-horizon").value = "2"; $("#f-bank-risk").value = "25"');
  const config = run('readConfig()');
  assert.equal(config.strategy, 'profit');
  assert.equal(config.horizonHours, 24);
  assert.equal(config.minVolume1h, run('automaticFilterProfile(20000000, "members", "overnight", 25).minVolume1h'));
  assert.equal(config.maxQuoteAge, run('automaticFilterProfile(20000000, "members", "active", 25).maxQuoteAge'));

  const lock = { slot: 0, id: 1, name: 'Test', qty: 10, buy: 100, sell: 110,
    commit: 0, expected: 10, lockedAt: 1 };
  storage.set('osrs-flipper.slot-locks.v1', JSON.stringify({
    'members:profit:0': [{ ...lock, mode: 'profit', horizonHours: 24 }],
    'members:overnight:8': [{ ...lock, slot: 1, id: 2, mode: 'overnight', horizonHours: 8 }],
    'members:active:0': [{ ...lock, slot: 2, id: 3 }],
  }));
  const modes = run('locksFor({account:"members", strategy:"profit", horizonHours:24, slots:8})' +
    '.map((l) => [l.id, l.mode, l.horizonHours])');
  assert.deepEqual(JSON.parse(JSON.stringify(modes)).sort(),
    [[1, 'profit', 24], [2, 'overnight', 8], [3, 'active', 4]]);

  // A saved Max profit offer is relisted at once, so it keeps the reminders.
  const offer = '({ mode: "profit", createdAt: 0, qty: 100, bought: 0, sold: 0,' +
    ' repriceCheckSeconds: 900, cancelBySeconds: 30000 })';
  assert.match(run(`executionTimingNote(${offer}, 1000 * 1000)`), /not one unit has bought/);
  run('state.config = { strategy: "overnight" }');
  assert.match(run(`executionTimingNote(${offer}, 60 * 1000)`), /Cancel it, or replace it/);
});

test('the Max profit plan card and note describe profit per flip', () => {
  const { run, elements } = setup();
  run(`(() => {
    const b = scoreFlip({ buy: 1000, sell: 1080, margin: 58, qty: 200, depth: 0,
      buyVolume1h: 150, sellVolume1h: 150, quoteAge: 60, ofi: 0, drift: 0,
      now: 1785000000, buyShare: 0.125, sellShare: 0.125, mode: "profit" });
    const row = { ...b, id: 1, name: "Test", buy: 1000, sell: 1080, listAt: 1080,
      roi: 0.058, allocatedQty: b.qty, allocated: b.qty * 1000,
      allocatedExpected: b.expected, warnings: timingWarnings(b), deep: true,
      edgeProbability: 0.9, volume: 500, age: 60, rawRankingValue: b.rankingValue,
      shrinkRetention: 1, tags: [] };
    state.planRows = [row]; state.slotLocks = []; state.sourceRows = [];
    renderPlan({ slots: 8, strategy: "profit", horizonHours: 24, capital: 20000000,
      bankRiskPercent: 25, maxPositionCapital: 5000000 });
  })()`);
  assert.match(elements.get('#plan-cards').innerHTML, /FULL TRIP WITHIN 24H/);
  const note = elements.get('#plan-note').textContent;
  assert.match(note, /Max profit ranks that profit per flip, not per hour/);
  // The note says what EXPECTED rests on and what it cannot know.
  assert.match(note, /replayed on the item's own last day/);
  assert.match(note, /an assumption until you log real offers\./);
  // Max profit rests unwatched and keeps the queue share: no size claim.
  assert.doesNotMatch(note, /Active offers are sized on/);
});

/* ---- audit 2026-11 ---- */

test('the automatic plan funds on replay evidence and states its reason', async () => {
  const { run, storage, elements } = setup();
  const now = Math.floor(Date.now() / 1000);
  // Steady: trades 100/110 all day. Fluke: quoted 100/110, but buyers have
  // only been paying 102, which leaves no margin after tax.
  const recent = (high) => Array.from({ length: 365 }, (_, i) => ({
    timestamp: now - (365 - i) * 300, avgLowPrice: 100, lowPriceVolume: 400,
    avgHighPrice: high, highPriceVolume: 400 }));
  const history = Array.from({ length: 60 }, (_, i) => ({
    timestamp: now - (60 - i) * 21600, avgLowPrice: 100, lowPriceVolume: 20000,
    avgHighPrice: 110, highPriceVolume: 20000 }));
  for (const [id, high] of [[1, 110], [2, 102]]) {
    storage.set(`osrs-flipper.ts.6h.${id}`, JSON.stringify({ at: Date.now(), data: history }));
    storage.set(`osrs-flipper.ts.5m.${id}`, JSON.stringify({ at: Date.now(), data: recent(high) }));
  }
  const result = await run(`(async () => {
    const items = withExemptions({
      1: { name: "Steady", members: true, limit: 1000, highalch: null },
      2: { name: "Fluke", members: true, limit: 1000, highalch: null } });
    const quote = { high: 110, low: 100, highTime: ${now} - 30, lowTime: ${now} - 30 };
    const act = { avgHighPrice: 110, highPriceVolume: 4000, avgLowPrice: 100, lowPriceVolume: 4000 };
    const config = { capital: 1000000, account: "members", slots: 8,
      includeMembers: true, strategy: "active", horizonHours: 4, natureCost: 100,
      ...automaticFilterProfile(1000000, "members", "active", 25) };
    state.capital = config.capital; state.items = items;
    const { rows } = screen(items, { 1: quote, 2: quote }, { 1: act, 2: act },
                            { 1: act, 2: act }, config, ${now});
    // Before the deep check there is no evidence, so nothing is funded.
    state.deepReady = false;
    const early = buildPlan(rows.map((r) => ({ ...r })), config, []);
    await refineTopRows(rows, config, ${now});
    state.deepReady = true;
    show(rows, config, "");
    const funded = state.planRows.filter((r) => r.allocatedQty > 0);
    const fluke = state.rows.find((r) => r.name === "Fluke");
    return { early: early.candidates.length,
      funded: funded.map((r) => [r.name, r.buy, r.sell, r.allocatedExpected === r.replay.stableProfit]),
      flukeFunded: fluke.allocatedQty, flukeReplay: fluke.replay && fluke.replay.stableProfit,
      binding: state.planSelection.binding, qualified: state.planQualified,
      listed: state.rows.find((r) => r.name === "Steady").allocatedQty > 0 };
  })()`);
  assert.equal(result.early, 0);
  assert.equal(result.funded.length, 1);
  const [name, buy, sell, expectedIsReplay] = result.funded[0];
  assert.equal(name, 'Steady');
  assert.ok(buy > 100 && sell < 110, 'priced inside what traded');
  assert.ok(expectedIsReplay, 'EXPECTED is the replayed result');
  assert.equal(result.flukeFunded, 0);
  assert.ok(result.flukeReplay == null || result.flukeReplay <= 0);
  assert.equal(result.binding, 'none');
  assert.equal(result.qualified, 1);
  assert.ok(result.listed, 'the full list shows the funded copy');
  assert.match(elements.get('#plan-cards').innerHTML, /Steady/);
  assert.doesNotMatch(elements.get('#plan-cards').innerHTML, /Fluke/);
  const note = elements.get('#plan-note').textContent;
  assert.match(note, /Neither bank nor slots ran out/);
  assert.match(note, /made money in both halves/);
  // An Active plan says what its order sizes rest on.
  assert.match(note, /Active offers are sized on 30% of the volume that trades through their price/);
  assert.match(elements.get('#status').textContent, /1 flip made money when replayed/);
});

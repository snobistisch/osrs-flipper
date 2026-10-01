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
  const [qty, allocated] = run(`(() => { const rows = [${bondRow()}];
    allocateCapital(rows, 19000000, 8, [], Infinity, 100);
    return [rows[0].allocatedQty, rows[0].allocated]; })()`);
  // 9m + 1m fee per bond: a 19m bank holds one, not the two the buy price fits.
  assert.equal(qty, 1);
  assert.equal(allocated, 10000000);
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

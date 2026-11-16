/* Run the browser app's whole planning path on one market snapshot.

   Used by tests/test_parity.py and by the backtest (backtest/browser.py) so
   the JavaScript port is exercised on exactly the inputs the Python model
   sees: screen -> automatic gates -> 14-day check -> plan selection ->
   allocation. Nothing here reimplements model logic; it calls the functions
   of the inline script in docs/index.html (or the file named in argv[2]).

   Protocol: one JSON request per line on stdin, one JSON reply per line.

     {"op":"targets","key":K,"snapshot":{items,quotes,act5m,act1h,now,
                                         capital,account,strategy,
                                         horizonHours,bankRiskPercent}}
        -> {"key":K,"targets":[item ids the app would fetch history for]}
     {"op":"prepare","key":K,"history":{id:[6h points]},"recent":{id:[5m points]}}
        -> {"key":K,"scored":n,"eligible":n,"candidates":n}
           screen + 14-day check + automatic gates + plan ordering, kept in
           memory under K
     {"op":"allocate","key":K,"capital":gp,"slots":n,"exclude":[ids]}
        -> {"key":K,"plan":[funded rows]}   (repeatable: works on copies)
     {"op":"release","key":K} -> {"key":K}

   Per-item history is injected through localStorage, which fetchTimeseries
   reads before it touches the network; fetch itself answers 404, so a missing
   series behaves like a failed request and nothing leaves the machine. */
const fs = require('node:fs');
const path = require('node:path');
const readline = require('node:readline');
const vm = require('node:vm');

const htmlPath = process.argv[2] || path.join(__dirname, '../docs/index.html');
const html = fs.readFileSync(htmlPath, 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const library = script.slice(0, script.indexOf('$("#start").addEventListener'));

function makeContext(store, requested) {
  const element = () => ({ classList: { add() {}, remove() {}, toggle() {} },
    style: {}, innerHTML: '', textContent: '', value: '' });
  const context = vm.createContext({
    console, URL, AbortController, setTimeout, clearTimeout,
    fetch: async () => ({ ok: false, status: 404 }),
    localStorage: {
      getItem: (key) => {
        if (key.startsWith('osrs-flipper.ts.')) {
          requested.add(key);
          return store.has(key) ? store.get(key) : null;
        }
        return null;
      },
      setItem() {}, removeItem() {}, key: () => null, length: 0,
    },
    document: { addEventListener() {}, querySelectorAll: () => [],
      querySelector: element },
  });
  vm.runInContext(library, context);
  return context;
}

const PREPARE = `(async (snapshot) => {
  const items = withExemptions(snapshot.items);
  const risk = normalizeBankRiskPercent(snapshot.bankRiskPercent ?? DEFAULT_BANK_RISK_PERCENT);
  const config = {
    capital: snapshot.capital, account: snapshot.account,
    slots: accountSlots(snapshot.account),
    includeMembers: snapshot.account === "members",
    strategy: snapshot.strategy, horizonHours: snapshot.horizonHours,
    natureCost: snapshot.natureCost,
    ...automaticFilterProfile(snapshot.capital, snapshot.account,
                              snapshot.strategy, risk),
  };
  // Order size (pages from 16 November 2026 on): the Active capture share.
  if (typeof ORDER_SIZES !== "undefined") {
    config.orderSize = snapshot.orderSize ?? DEFAULT_ORDER_SIZE;
    config.crossingCaptureShare = ORDER_SIZES[config.orderSize];
  }
  state.capital = snapshot.capital;
  state.natureCost = snapshot.natureCost;
  state.items = items;
  const { rows } = screen(items, snapshot.quotes, snapshot.act5m,
                          snapshot.act1h, config, snapshot.now,
                          snapshot.limitUsed ?? null);
  await refineTopRows(rows, config, snapshot.now);
  state.deepReady = true;
  const eligible = applyPreferences(rows, config).kept;
  // Pages from before the November 2026 audit pick plan candidates with
  // isAutomaticPlanCandidate and a risk-tier sort; later ones use buildPlan.
  const legacy = typeof buildPlan !== "function";
  let candidates = eligible;
  if (legacy) {
    candidates = eligible.filter(isAutomaticPlanCandidate);
    candidates.sort((a, b) => quickPlanRiskTier(a) - quickPlanRiskTier(b) ||
      b.rankingValue - a.rankingValue);
  }
  return { config, candidates, legacy, scored: rows.length,
           eligible: eligible.length };
})`;

/* The same steps show() takes: disposable copies, then allocateCapital with
   the bank and slots that are still free. */
const ALLOCATE = `((prepared, capital, slots, exclude) => {
  const skip = new Set(exclude);
  const candidates = prepared.candidates.filter((row) => !skip.has(row.id))
    .map((row) => ({ ...row, warnings: [...(row.warnings || [])],
      tags: [...(row.tags || [])], factors: { ...(row.factors || {}) } }));
  const config = prepared.config;
  let planned = candidates;
  if (prepared.legacy) {
    allocateCapital(candidates, Math.max(0, capital), Math.max(0, slots), [],
      config.maxPositionCapital, config.bankRiskPercent);
  } else {
    // The same call show() makes, with the free bank and slots as the whole
    // bank and every slot: nothing is locked in a backtest or a parity test.
    planned = buildPlan(candidates, { ...config, capital: Math.max(0, capital),
      slots: Math.max(0, slots) }, []).candidates;
  }
  return planned.filter((row) => row.allocatedQty > 0).map((row) => ({
    id: row.id, name: row.name, buy: row.buy, sell: row.sell,
    qty: row.allocatedQty, exempt: Boolean(row.exempt), bond: Boolean(row.bond),
    limit: row.limit ?? null, margin: row.margin, roi: row.roi,
    pFill: row.pFill, expected: row.expected,
    p50: row.roundTripP50Seconds, p80: row.roundTripP80Seconds,
    p90: row.roundTripP90Seconds, occupancy: row.expectedOccupancySeconds,
    rawPerSlotHour: row.rawPerSlotHour, rankingValue: row.rankingValue,
    volume: row.volume, age: row.age, deep: Boolean(row.deep),
    pricedFromReference: Boolean(row.pricedFromReference), depth: row.depth,
    expectedBuyQty: row.expectedBuyQty, expectedSellQty: row.expectedSellQty,
    capital: row.allocated, confidence: confidenceLabel(row),
    reason: row.planReason ?? null,
    replayProfit: row.replay ? row.replay.meanProfit : null,
    replayStable: row.replay ? row.replay.stableProfit : null,
    replayDone: row.replay ? row.replay.completionRate : null,
  }));
})`;

const snapshots = new Map();
const prepared = new Map();
const encode = (key, value) => (typeof value === 'number' && !Number.isFinite(value)
  ? null : value);

async function handle(request) {
  if (request.op === 'targets') {
    snapshots.set(request.key, request.snapshot);
    const requested = new Set();
    const context = makeContext(new Map(), requested);
    await vm.runInContext(PREPARE, context)(structuredClone(request.snapshot));
    const targets = [...new Set([...requested].map((key) => Number(key.split('.').pop())))];
    return { key: request.key, targets };
  }
  if (request.op === 'prepare') {
    const snapshot = snapshots.get(request.key);
    snapshots.delete(request.key);
    const store = new Map();
    const at = Date.now();
    for (const [id, data] of Object.entries(request.history || {})) {
      store.set(`osrs-flipper.ts.6h.${id}`, JSON.stringify({ at, data }));
    }
    for (const [id, data] of Object.entries(request.recent || {})) {
      store.set(`osrs-flipper.ts.5m.${id}`, JSON.stringify({ at, data }));
    }
    const context = makeContext(store, new Set());
    const result = await vm.runInContext(PREPARE, context)(snapshot);
    prepared.set(request.key, { context, result });
    return { key: request.key, scored: result.scored, eligible: result.eligible,
             candidates: result.candidates.length };
  }
  if (request.op === 'allocate') {
    const entry = prepared.get(request.key);
    if (!entry) return { key: request.key, error: 'unknown key' };
    const plan = vm.runInContext(ALLOCATE, entry.context)(
      entry.result, request.capital, request.slots, request.exclude || []);
    return { key: request.key, plan };
  }
  if (request.op === 'release') {
    prepared.delete(request.key);
    snapshots.delete(request.key);
    return { key: request.key };
  }
  return { key: request.key, error: 'unknown op' };
}

const lines = readline.createInterface({ input: process.stdin });
let chain = Promise.resolve();
lines.on('line', (line) => {
  if (!line.trim()) return;
  chain = chain.then(async () => {
    let reply;
    try {
      reply = await handle(JSON.parse(line));
    } catch (error) {
      reply = { error: String(error && error.stack || error) };
    }
    process.stdout.write(JSON.stringify(reply, encode) + '\n');
  });
});

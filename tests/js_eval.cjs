/* Evaluate browser-app expressions for tests/test_parity.py.

   Reads a JSON array of JavaScript expressions on stdin, runs each against the
   real inline library from docs/index.html (everything before the DOM wiring),
   and prints a JSON array of results. Non-finite numbers are encoded as
   strings so they survive JSON. */
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '../docs/index.html'), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const library = script.slice(0, script.indexOf('$("#start").addEventListener'));

const element = () => ({ classList: { add() {}, remove() {}, toggle() {} },
  style: {}, innerHTML: '', textContent: '', value: '' });
const context = vm.createContext({
  console, URL, AbortController, setTimeout, clearTimeout,
  localStorage: { getItem: () => null, setItem() {}, removeItem() {},
    key: () => null, length: 0 },
  document: { addEventListener() {}, querySelectorAll: () => [],
    querySelector: element },
});
vm.runInContext(library, context);

const expressions = JSON.parse(fs.readFileSync(0, 'utf8'));
const encode = (key, value) => (typeof value === 'number' && !Number.isFinite(value)
  ? String(value) : value);
const results = expressions.map((expression) =>
  JSON.parse(JSON.stringify(vm.runInContext(`(${expression})`, context) ?? null, encode)));
process.stdout.write(JSON.stringify(results));

// End-to-end smoke test against a running hub (stand-ins are fine):
//   uv run uvicorn hub.main:app --port 8000   (in another terminal, with CUEON_FAKE=1)
//   node hud/e2e/smoke.mjs [http://127.0.0.1:8000] [screenshot-dir]
// Uploads the sample deck, prepares cards, asks a prepared and a new question, runs presentation
// mode, and checks what the glasses view shows at each step.
import {chromium} from 'playwright';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';

const hub = process.argv[2] ?? 'http://127.0.0.1:8000';
const shots = process.argv[3];
const root = fileURLToPath(new URL('../../', import.meta.url));
const post = (path, body) =>
  fetch(hub + path, {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify(body ?? {})}).then(r => r.json());

async function upload(file, alias, role) {
  const form = new FormData();
  form.append('file', new Blob([await readFile(root + file)]), file.split('/').pop());
  form.append('alias', alias);
  form.append('role', role);
  const reply = await fetch(hub + '/api/docs', {method: 'POST', body: form});
  if (!reply.ok) throw new Error(`upload ${file}: ${reply.status}`);
}

function expect(ok, what) {
  if (!ok) throw new Error('FAILED: ' + what);
  console.log('ok  ', what);
}

const browser = await chromium.launch({executablePath: process.env.CHROMIUM});
const glasses = await browser.newPage({viewport: {width: 600, height: 600}});
const text = async () => (await glasses.locator('main').innerText()).replace(/\s+/g, ' ');
const shot = async name => shots && glasses.screenshot({path: `${shots}/${name}.png`});

await upload('samples/cueon-pitch.pdf', 'DECK', 'main');
await upload('samples/research-notes.pdf', 'RESEARCH', 'evidence');
await post('/api/prep', {limit: 12});
for (let i = 0; i < 100 && (await fetch(hub + '/api/status').then(r => r.json())).prep.running; i++) {
  await new Promise(r => setTimeout(r, 200));
}
const bank = await fetch(hub + '/api/bank').then(r => r.json());
expect(bank.entries.length > 0, `prep wrote ${bank.entries.length} cards`);

await glasses.goto(hub + '/glasses');
await post('/api/mode', {mode: 'qa'});
await glasses.waitForTimeout(500);
expect((await text()).includes('READY'), 'glasses idle and connected');

const first = bank.entries.find(e => !e.parent);
const asked = await post('/api/ask', {text: first.question});
await glasses.waitForTimeout(500);
expect(asked.record.path === 'bank', 'prepared question takes the bank path');
expect((await text()).includes(first.card.lead), 'prepared card is on the lens unchanged');
await shot('card');

await post('/api/ask', {text: 'Where did you buy that shirt?'});
await glasses.waitForTimeout(800);
expect(/LIVE|Ask to repeat/.test(await text()), 'unknown question gets a live card or a repeat prompt');

await post('/api/talk', {minutes: 3});
await post('/api/mode', {mode: 'present'});
await glasses.waitForTimeout(500);
expect((await text()).includes('1/'), 'presentation mode shows the page counter');
await shot('present');

const stats = await fetch(hub + '/api/stats').then(r => r.json());
expect(stats.paths.bank.rendered_p50 != null, 'render latency was acknowledged by the glasses');
await post('/api/mode', {mode: 'qa'});
await browser.close();
console.log('smoke test passed');

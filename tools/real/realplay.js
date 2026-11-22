// Observation only: H3 (unchanged bot/main.py) plays public matches. The game socket is proxied in Node:
// server frames go to the page as usual and to H3; H3's action for each obs goes straight to the server;
// the page's own action messages are dropped (the headless page runs seconds behind). Other page messages pass.
const { chromium } = require('playwright');
const { spawn } = require('child_process');
const fs = require('fs'), path = require('path');
const BOT = process.argv[2], LOGDIR = process.argv[3], NMATCH = Number(process.argv[4] || 6), NAME = process.argv[5] || 'Goonies-H3';
let bot = null, out = null, matchN = 0, ended = 0, server = null, pending = {}, buf = '', page = null;
const now = () => Date.now();
function log(o) { if (out) out.write(JSON.stringify(Object.assign({ ts: now() }, o)) + '\n'); }
function startBot(hello) {
  if (bot) { try { bot.kill(); } catch (e) {} }
  matchN += 1; buf = ''; pending = {};
  const f = path.join(LOGDIR, `match_${now()}.jsonl`);
  if (out) out.end();
  out = fs.createWriteStream(f);
  console.log(`[match ${matchN}] -> ${f}`);
  bot = spawn('python3', ['-u', path.join(BOT, 'bot/main.py')], { stdio: ['pipe', 'pipe', 'pipe'] });
  bot.stderr.on('data', d => log({ k: 'bot_stderr', s: String(d).slice(0, 500) }));
  bot.stdout.on('data', d => {
    buf += String(d);
    let i;
    while ((i = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, i); buf = buf.slice(i + 1);
      let a; try { a = JSON.parse(line); } catch (e) { continue; }
      if (a.type === 'ready') { log({ k: 'ready', a }); continue; }
      const label = a.debug && a.debug.label; delete a.debug;
      const t0 = pending[a.tick]; delete pending[a.tick];
      if (server) server.send(JSON.stringify(a));
      log({ k: 'action', a, ms: t0 ? now() - t0 : null, label });
    }
  });
  const h = JSON.parse(JSON.stringify(hello));
  h.map = Object.assign({}, h.map || {}, { dir: path.join(BOT, 'arena') });
  bot.stdin.write(JSON.stringify(h) + '\n');
}
function onServer(raw) {
  let m; try { m = JSON.parse(raw); } catch (e) { return; }
  if (m.type === 'hello') { startBot(m); log({ k: 'hello', m }); return; }
  if (m.type === 'obs') { if (!bot) return; pending[m.tick] = now(); log({ k: 'obs', m }); bot.stdin.write(raw + '\n'); return; }
  if (m.type === 'end') { log({ k: 'end', m }); ended += 1; console.log(`[match ${matchN}] end ${JSON.stringify(m).slice(0, 200)}`); return; }
  if (m.type === 'results') { log({ k: 'results', m }); try { bot.stdin.end(); } catch (e) {} return; }
  log({ k: 'other', type: m.type, m: JSON.stringify(m).slice(0, 3000) });
}
(async () => {
  const b = await chromium.launch({ args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  page = await b.newPage({ viewport: { width: 400, height: 260 } });
  // the page's rendering is not needed (H3 talks to the server through this proxy): 1 frame a second frees the CPUs
  await page.addInitScript(() => {
    const raf = window.requestAnimationFrame.bind(window);
    window.requestAnimationFrame = cb => setTimeout(() => raf(cb), 1000);
  });
  await page.routeWebSocket(/.*/, ws => {
    const srv = ws.connectToServer();
    console.log('ws', ws.url());
    const isPlay = /\/play\?/.test(ws.url());
    if (isPlay) server = srv;
    srv.onMessage(msg => { const s = typeof msg === 'string' ? msg : String(msg); if (isPlay) onServer(s); ws.send(msg); });
    ws.onMessage(msg => {
      const s = typeof msg === 'string' ? msg : String(msg);
      try {
        const m = JSON.parse(s);
        if (isPlay && m && typeof m.tick === 'number' && ('move' in m || 'aim' in m || 'fire' in m)) { log({ k: 'page_action_dropped', tick: m.tick }); return; }
      } catch (e) {}
      log({ k: 'page_msg', s: s.slice(0, 300) });
      srv.send(msg);
    });
  });
  await page.goto('https://play.joinbuilders.org', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(4000);
  await page.fill('input >> nth=0', NAME).catch(e => console.log('fill', e.message));
  await page.click('text=PLAY NOW').catch(e => console.log('play', e.message));
  const t0 = now();
  while (ended < NMATCH && now() - t0 < 150 * 60 * 1000) {
    for (const label of ['START NOW', 'READY', 'PLAY AGAIN', 'PLAY NOW']) {
      try {
        const el = await page.$(`button:has-text("${label}")`);
        if (el && await el.isVisible()) { await el.click(); console.log(`[${Math.round((now() - t0) / 1000)} s] clicked ${label}`); await page.waitForTimeout(1500); }
      } catch (e) {}
    }
    await page.waitForTimeout(2000);
  }
  console.log('done, matches ended:', ended);
  if (out) out.end();
  await b.close();
  process.exit(0);
})();

'use strict';
// Jádro Spark Chatu bez závislosti na VS Code: přístup ke Sparku, streamování odpovědi, příprava review.
// Adresa a klíč se čtou jen z proměnných prostředí a nikdy se nevypisují.
const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const EMPTY_TREE = '4b825dc642cb6eb9a060e54bf8d69288fbee4904';
// Citlivé soubory: k modelu se nedostanou (stejně jako review/spark_review.py).
const EXCLUDE = ['.env', '.env.*', '*.env', 'device_config.h', 'release.py', '*.key', '*.pem', '*.p12', '*.pfx',
  'id_rsa*', 'id_ed25519*', '*secret*', '*credential*', '*.token', 'sdkconfig', 'sdkconfig.old'];
const EXCLUDE_DIRS = ['build', '.venv', 'node_modules', 'managed_components'];
const CODE_EXT = new Set(['.c', '.h', '.cpp', '.hpp', '.cc', '.py', '.ts', '.js', '.cs', '.java', '.go', '.rs',
  '.cmake', '.txt', '.md', '.json', '.yml', '.yaml', '.ini', '.csv', '.ps1', '.sh']);
const GENERIC = [
  [/\bsk-[A-Za-z0-9_-]{16,}/, 'klíč sk-…'],
  [/\bgh[pousr]_[A-Za-z0-9]{20,}/, 'GitHub token'],
  [/BEGIN [A-Z ]*PRIVATE KEY/, 'privátní klíč'],
  [/\bAKIA[0-9A-Z]{16}\b/, 'AWS klíč'],
];
const MAX_FILE_CHARS = 60000;
const MAX_PROMPT_CHARS = 300000;

function userEnv(name) {
  if (process.env[name]) return process.env[name];
  if (process.platform !== 'win32') return undefined;
  try {  // VS Code spuštěný před nastavením proměnné ji v prostředí nemá, vezme se z registru uživatele
    const out = execFileSync('reg', ['query', 'HKCU\\Environment', '/v', name],
      { encoding: 'utf8', windowsHide: true, stdio: ['ignore', 'pipe', 'ignore'] });
    const m = out.match(new RegExp('^\\s*' + name + '\\s+REG_(?:EXPAND_)?SZ\\s+(.+)$', 'm'));
    return m ? m[1].trim() : undefined;
  } catch {
    return undefined;
  }
}

function getSpark() {
  const url = userEnv('SPARK_URL');
  const key = userEnv('LITELLM_API_KEY');
  if (!url) throw new Error('Chybí adresa Sparku: nastavte proměnnou prostředí SPARK_URL (adresu dá správce Sparku) a restartujte VS Code.');
  if (!key) throw new Error('Chybí klíč: nastavte proměnnou prostředí LITELLM_API_KEY (osobní klíč dá správce Sparku) a restartujte VS Code.');
  const base = url.trim().replace(/\/+$/, '').replace(/\/v1$/, '');
  let host = '';
  try { host = new URL(base).hostname; } catch { /* neplatná adresa ohlásí fetch */ }
  return { base, key: key.trim(), host };
}

// Z chybových hlášek odstraní adresu i klíč, aby se nikdy neobjevily v okně.
function sanitize(text, spark) {
  let s = String(text || '');
  if (spark) {
    for (const [v, r] of [[spark.key, '[klíč]'], [spark.base, '[Spark]'], [spark.host, '[Spark]']]) {
      if (v && v.length >= 4) s = s.split(v).join(r);
    }
  }
  return s.replace(/\b(?:\d{1,3}\.){3}\d{1,3}\b/g, '[IP]').replace(/[a-z0-9-]+\.ts\.net/gi, '[Spark]');
}

function secretHits(text, spark) {
  const hits = GENERIC.filter(([rx]) => rx.test(text)).map(([, n]) => n);
  if (spark && spark.key && text.includes(spark.key)) hits.push('váš klíč ke Sparku');
  if (spark && spark.host && text.includes(spark.host)) hits.push('adresa Sparku');
  return hits;
}

async function streamChat(spark, { messages, model, effort, maxTokens, signal }, on) {
  const body = { model, messages, stream: true, stream_options: { include_usage: true }, max_tokens: maxTokens };
  if (effort) body.reasoning_effort = effort;
  const res = await fetch(spark.base + '/v1/chat/completions', {
    method: 'POST', signal,
    headers: { Authorization: 'Bearer ' + spark.key, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const t = await res.text().catch(() => '');
    throw new Error(`Spark odmítl požadavek (HTTP ${res.status}): ${t.slice(0, 300)}`);
  }
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = '';
  let usage = null;
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, i).trim();
      buf = buf.slice(i + 1);
      if (!line.startsWith('data:')) continue;
      const data = line.slice(5).trim();
      if (data === '[DONE]') continue;
      let j;
      try { j = JSON.parse(data); } catch { continue; }
      if (j.usage) usage = j.usage;
      const d = j.choices && j.choices[0] && j.choices[0].delta;
      if (!d) continue;
      const r = d.reasoning_content || d.reasoning;
      if (r) on.reasoning(r);
      if (d.content) on.content(d.content);
    }
  }
  return usage;
}

// ---------------------------------------------------------------- review (jako review/spark_review.py)

function git(cwd, args) {
  try {
    return execFileSync('git', ['-C', cwd, ...args],
      { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] })
      .replace(/\r\n/g, '\n');
  } catch (e) {
    throw new Error('git ' + args[0] + ': ' + String(e.stderr || e.message).trim().split('\n')[0]);
  }
}

function globRx(p) {
  return new RegExp('^' + p.replace(/[.+^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '.*') + '$', 'i');
}
const EXCLUDE_RX = EXCLUDE.map(globRx);

function excluded(p) {
  const parts = p.split('/');
  return EXCLUDE_RX.some(rx => rx.test(parts[parts.length - 1])) || parts.some(x => EXCLUDE_DIRS.includes(x));
}

function pathspec() {
  return ['--', '.', ...EXCLUDE.map(p => `:(exclude,glob)**/${p}`), ...EXCLUDE_DIRS.map(d => `:(exclude,glob)**/${d}/**`)];
}

function buildPrompt(rules, log, diff, files) {
  const parts = [rules ? `# Pravidla projektu\n\n${rules.trim()}\n` : '',
    `# Commity\n\n${log.trim()}\n`, '# Změny (diff)\n\n```diff\n' + diff.trim() + '\n```\n',
    '# Plné znění změněných souborů\n'];
  for (const [p, t] of Object.entries(files)) parts.push(`## ${p}\n\n\`\`\`\n${t}\n\`\`\`\n`);
  return parts.filter(Boolean).join('\n');
}

// Větve k výběru: aktuální (HEAD), místní a vzdálené, u každé poslední commit.
function listRefs(dir) {
  const root = git(dir, ['rev-parse', '--show-toplevel']).trim();
  const out = git(root, ['for-each-ref', '--format=%(refname:short)\t%(objectname:short) %(subject)', 'refs/heads', 'refs/remotes']);
  const refs = [{ ref: 'HEAD', label: 'Aktuální větev (HEAD)', detail: git(root, ['log', '-1', '--format=%h %s']).trim() }];
  for (const line of out.split('\n')) {
    const [ref, detail] = line.split('\t');
    if (ref && detail && !/\/HEAD$/.test(ref) && ref !== 'origin') refs.push({ ref, label: ref, detail });
  }
  return refs;
}

// Review posledního commitu větve `ref` v repozitáři, ve kterém leží `dir`. Vrací text pro model a popis pro okno.
function prepareReview(dir, extDir, spark, ref = 'HEAD') {
  const root = git(dir, ['rev-parse', '--show-toplevel']).trim();
  const end = git(root, ['rev-parse', '--verify', ref + '^{commit}']).trim();
  let base;
  try { base = git(root, ['rev-parse', '--verify', '-q', end + '~1']).trim(); } catch { base = EMPTY_TREE; }
  const subject = git(root, ['log', '-1', '--format=%h %s', end]).trim();
  const log = base !== EMPTY_TREE ? git(root, ['log', '--format=- %h %s', `${base}..${end}`]) : git(root, ['log', '--format=- %h %s', end]);
  const diff = git(root, ['diff', '--no-color', '-U5', base, end, ...pathspec()]);
  if (!diff.trim()) throw new Error('Poslední commit nemá žádné změny ke kontrole.');
  const files = {};
  for (const p of git(root, ['diff', '--name-only', '--diff-filter=AM', base, end, ...pathspec()]).split('\n')) {
    if (!p || excluded(p) || !CODE_EXT.has(path.extname(p).toLowerCase())) continue;
    let t;
    try { t = git(root, ['show', `${end}:${p}`]); } catch { continue; }
    if (t.includes('\u0000')) continue;
    files[p] = t.length <= MAX_FILE_CHARS ? t : t.slice(0, MAX_FILE_CHARS) + '\n... (zkráceno)';
  }
  const rulesFile = [path.join(root, 'REVIEW-PRAVIDLA.md'), path.join(root, 'review', 'pravidla-vychozi.md'),
    path.join(extDir, 'prompts', 'pravidla-vychozi.md')].find(f => fs.existsSync(f));
  const read = f => fs.readFileSync(f, 'utf8').replace(/\r\n/g, '\n');
  const rules = rulesFile ? read(rulesFile) : '';
  const instructions = read(path.join(extDir, 'prompts', 'reviewer.md')).trim();
  const prompt = buildPrompt(rules, log, diff, files);
  const hits = secretHits(prompt, spark);
  if (hits.length) throw new Error('STOP: ve změnách jsou tajné údaje (' + hits.join(', ') + '). Nic se neodeslalo.');
  if (prompt.length > MAX_PROMPT_CHARS) throw new Error(`STOP: změna je moc velká (${prompt.length} znaků, limit ${MAX_PROMPT_CHARS}).`);
  return {
    text: instructions + '\n\n' + prompt,
    title: subject, ref, repo: path.basename(root), nFiles: Object.keys(files).length, chars: prompt.length,
    rules: rulesFile ? path.basename(rulesFile) : 'žádná',
  };
}

module.exports = { userEnv, getSpark, sanitize, secretHits, streamChat, prepareReview, listRefs, excluded, buildPrompt, git };

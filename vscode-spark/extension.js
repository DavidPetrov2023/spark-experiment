'use strict';
// Spark Chat: okno chatu ve VS Code napojené na model na DGX Sparku (LiteLLM, rozhraní kompatibilní s OpenAI).
const vscode = require('vscode');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const core = require('./spark');

const CHAT_SYSTEM = 'Jsi asistent pro vývojáře (firmware ESP32, C, Python a další). Odpovídej česky, stručně a věcně. '
  + 'Když si nejsi jistý, řekni to. Nevymýšlej si API ani fakta.';
const MAX_ATTACH = 60000;

class SparkChatView {
  constructor(context) {
    this.context = context;
    this.view = undefined;
    this.messages = [];
    this.abort = undefined;
  }

  resolveWebviewView(view) {
    this.view = view;
    view.webview.options = { enableScripts: true, localResourceRoots: [vscode.Uri.joinPath(this.context.extensionUri, 'media')] };
    view.webview.html = this.html(view.webview);
    view.webview.onDidReceiveMessage(m => this.onMessage(m));
  }

  post(m) {
    if (this.view) this.view.webview.postMessage(m);
  }

  config() {
    const c = vscode.workspace.getConfiguration('sparkChat');
    return { model: c.get('model', 'gpt-oss-120b'), effort: c.get('effort', 'medium') };
  }

  async onMessage(m) {
    if (m.type === 'ready') this.post({ type: 'info', ...this.config() });
    else if (m.type === 'send') await this.send(m.text, m.attach, m.effort);
    else if (m.type === 'review') await this.review(m.effort);
    else if (m.type === 'stop') this.stop();
    else if (m.type === 'new') this.reset();
  }

  reset() {
    this.stop();
    this.messages = [];
    this.post({ type: 'reset' });
  }

  stop() {
    if (this.abort) this.abort.abort();
  }

  attachment(spark) {
    const ed = vscode.window.activeTextEditor;
    if (!ed) throw new Error('Není otevřený žádný soubor k přiložení.');
    const rel = vscode.workspace.asRelativePath(ed.document.uri).replace(/\\/g, '/');
    if (core.excluded(rel)) throw new Error(`Soubor ${rel} je citlivý (hesla, klíče, adresy), k modelu se neposílá.`);
    const sel = ed.selection && !ed.selection.isEmpty ? ed.document.getText(ed.selection) : ed.document.getText();
    if (sel.length > MAX_ATTACH) throw new Error(`Soubor je moc velký (${sel.length} znaků, limit ${MAX_ATTACH}). Označte jen část.`);
    const hits = core.secretHits(sel, spark);
    if (hits.length) throw new Error(`V souboru jsou tajné údaje (${hits.join(', ')}). Nic se neodeslalo.`);
    const what = ed.selection && !ed.selection.isEmpty ? `výběr ze souboru ${rel}` : `soubor ${rel}`;
    return { label: what, text: `Přiložený ${what}:\n\n\`\`\`\n${sel}\n\`\`\`\n\n` };
  }

  async send(text, attach, effort) {
    let spark;
    try {
      spark = core.getSpark();
      const att = attach ? this.attachment(spark) : null;
      const hits = core.secretHits(text, spark);
      if (hits.length) throw new Error(`Ve zprávě jsou tajné údaje (${hits.join(', ')}). Nic se neodeslalo.`);
      if (!this.messages.length) this.messages.push({ role: 'system', content: CHAT_SYSTEM });
      this.messages.push({ role: 'user', content: (att ? att.text : '') + text });
      this.post({ type: 'user', text, note: att ? '📎 ' + att.label : '' });
    } catch (e) {
      this.post({ type: 'error', text: core.sanitize(e.message, spark) });
      return;
    }
    await this.run(spark, effort, 16000);
  }

  // Repozitář k review: složka otevřeného souboru, otevřená složka, nebo její podsložka s gitem.
  findRepo() {
    const cands = [];
    const ed = vscode.window.activeTextEditor;
    if (ed && ed.document.uri.scheme === 'file') cands.push(path.dirname(ed.document.uri.fsPath));
    for (const f of vscode.workspace.workspaceFolders || []) {
      cands.push(f.uri.fsPath);
      try {
        for (const d of fs.readdirSync(f.uri.fsPath, { withFileTypes: true })) {
          if (d.isDirectory() && fs.existsSync(path.join(f.uri.fsPath, d.name, '.git'))) cands.push(path.join(f.uri.fsPath, d.name));
        }
      } catch { /* nečitelná složka */ }
    }
    for (const c of cands) {
      try { core.git(c, ['rev-parse', '--show-toplevel']); return c; } catch { /* není repozitář */ }
    }
    throw new Error('V otevřené složce není git repozitář. Otevřete složku s repozitářem (File → Open Folder).');
  }

  async review(effort) {
    let spark;
    try {
      spark = core.getSpark();
      const repo = this.findRepo();
      const pick = await vscode.window.showQuickPick(
        core.listRefs(repo).map(r => ({ label: r.label, description: r.detail, ref: r.ref })),
        { title: 'Spark: review posledního commitu', placeHolder: 'Vyberte větev (poslední commit se pošle Sparku)', matchOnDescription: true });
      if (!pick) return;
      const r = core.prepareReview(repo, this.context.extensionPath, spark, pick.ref);
      this.messages.push({ role: 'user', content: r.text });
      this.post({
        type: 'user', text: `Review posledního commitu${r.ref === 'HEAD' ? '' : ' ve větvi ' + r.ref}: ${r.title}`,
        note: `🔍 ${r.repo}: ${r.nFiles} ${r.nFiles === 1 ? 'soubor' : 'souborů'}, ${r.chars.toLocaleString('cs-CZ')} znaků, pravidla: ${r.rules}`,
      });
    } catch (e) {
      this.post({ type: 'error', text: core.sanitize(e.message, spark) });
      return;
    }
    await this.run(spark, effort, 32000);
  }

  async run(spark, effort, maxTokens) {
    const { model } = this.config();
    this.abort = new AbortController();
    this.post({ type: 'start', model, effort });
    let answer = '';
    let reasoningChars = 0;
    try {
      const usage = await core.streamChat(spark, { messages: this.messages, model, effort, maxTokens, signal: this.abort.signal }, {
        reasoning: s => { reasoningChars += s.length; this.post({ type: 'reasoning', chars: reasoningChars }); },
        content: s => { answer += s; this.post({ type: 'delta', text: s }); },
      });
      this.messages.push({ role: 'assistant', content: answer });
      this.post({ type: 'done', usage });
    } catch (e) {
      if (answer) this.messages.push({ role: 'assistant', content: answer });
      else this.messages.pop();
      const msg = e.name === 'AbortError' ? 'Zastaveno.' : 'Spark neodpověděl: ' + core.sanitize(e.message, spark)
        + (/fetch failed|ENOTFOUND|ECONNREFUSED|ETIMEDOUT|EAI_AGAIN/.test(String(e.message) + String(e.cause)) ? ' Je připojený Tailscale?' : '');
      this.post({ type: 'done', error: core.sanitize(msg, spark) });
    } finally {
      this.abort = undefined;
    }
  }

  html(webview) {
    const nonce = crypto.randomBytes(16).toString('base64');
    const uri = f => webview.asWebviewUri(vscode.Uri.joinPath(this.context.extensionUri, 'media', f));
    return `<!DOCTYPE html>
<html lang="cs"><head><meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src ${webview.cspSource}; img-src ${webview.cspSource}; script-src 'nonce-${nonce}';">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="stylesheet" href="${uri('chat.css')}">
<title>Spark Chat</title></head>
<body>
<header>
  <div class="brand"><img src="${uri('spark-color.svg')}" alt=""><b>Spark</b><span class="model" id="model">gpt-oss-120b</span></div>
  <label class="effort" title="Jak dlouho model přemýšlí">přemýšlení
    <select id="effort"><option value="low">low</option><option value="medium">medium</option><option value="high">high</option></select></label>
</header>
<div class="actions">
  <button id="review" title="Pošle poslední commit otevřeného repozitáře Sparku k review">🔍 Review posledního commitu</button>
  <button id="new" class="secondary" title="Začít nový rozhovor">Nový chat</button>
</div>
<main id="log">
  <div id="empty" class="empty">
    <p><b>Chat s modelem na serveru DGX Spark.</b></p>
    <p>Zeptejte se na cokoli, přiložte otevřený soubor, nebo spusťte review posledního commitu.</p>
    <p class="muted">Běží na soukromém serveru, ne v cloudu. Co pošlete, vidí správce Sparku. Citlivé soubory a tajné údaje se neodesílají.</p>
  </div>
</main>
<footer>
  <label class="attach"><input type="checkbox" id="attach"> přiložit otevřený soubor (nebo výběr)</label>
  <div class="row">
    <textarea id="input" rows="3" placeholder="Zeptejte se Sparku… (Enter odešle, Shift+Enter nový řádek)"></textarea>
    <button id="send">Odeslat</button><button id="stop" class="danger" hidden>Zastavit</button>
  </div>
</footer>
<script nonce="${nonce}" src="${uri('chat.js')}"></script>
</body></html>`;
  }
}

function activate(context) {
  const view = new SparkChatView(context);
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider('sparkChat.view', view, { webviewOptions: { retainContextWhenHidden: true } }),
    vscode.commands.registerCommand('sparkChat.review', async () => {
      await vscode.commands.executeCommand('sparkChat.view.focus');
      await view.review(view.config().effort);
    }),
    vscode.commands.registerCommand('sparkChat.new', () => view.reset()),
  );
}

function deactivate() {}

module.exports = { activate, deactivate };

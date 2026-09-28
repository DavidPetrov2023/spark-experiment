// Okno Spark Chatu (webview). Adresa ani klíč sem nikdy nechodí.
(function () {
  const vscode = acquireVsCodeApi();
  const $ = id => document.getElementById(id);
  const log = $('log'), input = $('input'), send = $('send'), stop = $('stop'), effort = $('effort');
  let current = null;   // {el, body, status, text, t0, timer, reasoning}
  let busy = false;

  // ------------------------------------------------------------ jednoduchý Markdown (bez externích knihoven)
  function esc(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }
  function inline(s) {
    const codes = [];
    s = s.replace(/`([^`]+)`/g, (_, c) => { codes.push(c); return '\u0000' + (codes.length - 1) + '\u0000'; });
    s = esc(s)
      .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
      .replace(/(^|[^*\w])\*([^*\n]+)\*(?!\w)/g, '$1<i>$2</i>');
    return s.replace(/\u0000(\d+)\u0000/g, (_, i) => '<code>' + esc(codes[+i]) + '</code>');
  }
  function md(src) {
    const lines = src.replace(/\r\n/g, '\n').split('\n');
    let out = '', i = 0;
    const isTableSep = l => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(l);
    const cells = l => l.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(c => c.trim());
    while (i < lines.length) {
      const l = lines[i];
      const fence = l.match(/^\s*```(\w*)/);
      if (fence) {
        const buf = [];
        i++;
        while (i < lines.length && !/^\s*```/.test(lines[i])) buf.push(lines[i++]);
        i++;
        out += '<pre><code>' + esc(buf.join('\n')) + '</code></pre>';
        continue;
      }
      if (/^\s*\|/.test(l) && i + 1 < lines.length && isTableSep(lines[i + 1])) {
        const head = cells(l);
        i += 2;
        let rows = '';
        while (i < lines.length && /^\s*\|/.test(lines[i])) {
          rows += '<tr>' + cells(lines[i++]).map(c => '<td>' + inline(c) + '</td>').join('') + '</tr>';
        }
        out += '<div class="tbl"><table><thead><tr>' + head.map(c => '<th>' + inline(c) + '</th>').join('')
          + '</tr></thead><tbody>' + rows + '</tbody></table></div>';
        continue;
      }
      const h = l.match(/^(#{1,4})\s+(.*)$/);
      if (h) { out += `<h${h[1].length + 2}>` + inline(h[2]) + `</h${h[1].length + 2}>`; i++; continue; }
      if (/^\s*(-{3,}|\*{3,})\s*$/.test(l)) { out += '<hr>'; i++; continue; }
      const li = l.match(/^\s*([-*•]|\d+[.)])\s+(.*)$/);
      if (li) {
        const ordered = /\d/.test(li[1]);
        let items = '';
        while (i < lines.length) {
          const m = lines[i].match(/^\s*([-*•]|\d+[.)])\s+(.*)$/);
          if (!m) {
            if (lines[i].trim() && /^\s{2,}/.test(lines[i])) { items = items.replace(/<\/li>$/, ' ' + inline(lines[i].trim()) + '</li>'); i++; continue; }
            break;
          }
          items += '<li>' + inline(m[2]) + '</li>';
          i++;
        }
        out += ordered ? '<ol>' + items + '</ol>' : '<ul>' + items + '</ul>';
        continue;
      }
      if (!l.trim()) { i++; continue; }
      const para = [];
      while (i < lines.length && lines[i].trim() && !/^\s*```/.test(lines[i]) && !/^(#{1,4})\s/.test(lines[i])
        && !/^\s*([-*•]|\d+[.)])\s+/.test(lines[i]) && !/^\s*\|/.test(lines[i])) para.push(lines[i++]);
      if (para.length) out += '<p>' + para.map(inline).join('<br>') + '</p>';
      else i++;
    }
    return out;
  }

  // ------------------------------------------------------------ okno
  function scroll() { log.scrollTop = log.scrollHeight; }
  function add(cls, html) {
    $('empty').hidden = true;
    const el = document.createElement('div');
    el.className = 'msg ' + cls;
    el.innerHTML = html;
    log.appendChild(el);
    scroll();
    return el;
  }
  function setBusy(b) {
    busy = b;
    send.hidden = b; stop.hidden = !b;
    $('review').disabled = b;
  }
  function secs(t0) { return Math.round((Date.now() - t0) / 1000); }

  function submit() {
    const text = input.value.trim();
    if (!text || busy) return;
    input.value = '';
    vscode.postMessage({ type: 'send', text, attach: $('attach').checked, effort: effort.value });
  }
  send.onclick = submit;
  stop.onclick = () => vscode.postMessage({ type: 'stop' });
  $('review').onclick = () => { if (!busy) vscode.postMessage({ type: 'review', effort: effort.value }); };
  $('new').onclick = () => vscode.postMessage({ type: 'new' });
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); }
  });

  window.addEventListener('message', ({ data: m }) => {
    if (m.type === 'info') {
      $('model').textContent = m.model;
      effort.value = m.effort;
    } else if (m.type === 'user') {
      add('user', '<div class="who">Vy</div><div class="body">' + esc(m.text).replace(/\n/g, '<br>') + '</div>'
        + (m.note ? '<div class="note">' + esc(m.note) + '</div>' : ''));
    } else if (m.type === 'start') {
      setBusy(true);
      const el = add('spark', '<div class="who"><span class="dot"></span>Spark · ' + esc(m.model) + ' · ' + esc(m.effort)
        + '</div><div class="status">Spark přemýšlí…</div><div class="body"></div>');
      current = { el, body: el.querySelector('.body'), status: el.querySelector('.status'), text: '', t0: Date.now(), reasoning: 0, tAnswer: 0 };
      current.timer = setInterval(() => {
        if (!current) return;
        current.status.textContent = current.text
          ? 'Spark odpovídá… ' + secs(current.t0) + ' s'
          : 'Spark přemýšlí… ' + secs(current.t0) + ' s' + (current.reasoning ? ' (' + current.reasoning.toLocaleString('cs-CZ') + ' znaků úvah)' : '');
      }, 500);
    } else if (m.type === 'reasoning' && current) {
      current.reasoning = m.chars;
    } else if (m.type === 'delta' && current) {
      if (!current.text) current.tAnswer = Date.now();
      current.text += m.text;
      current.body.innerHTML = md(current.text);
      scroll();
    } else if (m.type === 'done' && current) {
      clearInterval(current.timer);
      const total = secs(current.t0);
      const think = current.tAnswer ? Math.round((current.tAnswer - current.t0) / 1000) : total;
      const tok = m.usage && m.usage.completion_tokens ? ' · ' + m.usage.completion_tokens.toLocaleString('cs-CZ') + ' tokenů' : '';
      current.status.textContent = m.error ? m.error : 'Přemýšlel ' + think + ' s · celkem ' + total + ' s' + tok;
      if (m.error) current.status.classList.add('err');
      current.el.querySelector('.dot').classList.add('off');
      current = null;
      setBusy(false);
      input.focus();
    } else if (m.type === 'error') {
      add('error', esc(m.text));
    } else if (m.type === 'reset') {
      log.querySelectorAll('.msg').forEach(e => e.remove());
      $('empty').hidden = false;
      if (current) { clearInterval(current.timer); current = null; }
      setBusy(false);
    }
  });
  vscode.postMessage({ type: 'ready' });
})();

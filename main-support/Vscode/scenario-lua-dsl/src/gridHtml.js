// gridHtml.js
//
// 「シナリオ選択グリッド」のHTML/CSS/JS本体。
// サイドバーの常設ビュー(WebviewView)と、コマンドから開く大きいパネル(WebviewPanel)の
// 両方から同じ見た目・同じ挙動で使い回すために、HTML生成部分だけをここに切り出している。

function getNonce() {
  const possible = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  let text = '';
  for (let i = 0; i < 32; i++) text += possible.charAt(Math.floor(Math.random() * possible.length));
  return text;
}

/**
 * @param {import('vscode').Webview} webview
 * @param {{ compact?: boolean }} [opts] compact: サイドバーの狭い幅向けに列を減らした表示にする
 */
function getGridHtml(webview, opts = {}) {
  const nonce = getNonce();
  const compact = !!opts.compact;
  const csp = [
    `default-src 'none'`,
    `img-src ${webview.cspSource} data:`,
    `style-src ${webview.cspSource} 'unsafe-inline'`,
    `script-src 'nonce-${nonce}'`,
  ].join('; ');

  return `<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="${csp}">
<title>Scenario Lua: 編集するシナリオを選択</title>
<style>
  :root { color-scheme: light dark; }
  body {
    font-family: var(--vscode-font-family);
    color: var(--vscode-foreground);
    background: var(--vscode-editor-background);
    padding: ${compact ? '8px 8px' : '12px 16px'};
    margin: 0;
  }
  .toolbar { display: flex; gap: 6px; align-items: center; margin-bottom: 8px; }
  #search {
    flex: 1;
    min-width: 0;
    padding: 5px 7px;
    background: var(--vscode-input-background);
    color: var(--vscode-input-foreground);
    border: 1px solid var(--vscode-input-border, transparent);
    border-radius: 3px;
    font-size: 12px;
  }
  button {
    padding: 4px 9px;
    background: var(--vscode-button-background);
    color: var(--vscode-button-foreground);
    border: none;
    border-radius: 3px;
    cursor: pointer;
    font-size: 11px;
    white-space: nowrap;
  }
  button:hover { background: var(--vscode-button-hoverBackground); }
  button.secondary {
    background: var(--vscode-button-secondaryBackground);
    color: var(--vscode-button-secondaryForeground);
  }
  button.secondary:hover { background: var(--vscode-button-secondaryHoverBackground); }
  button.icon { padding: 4px 6px; }
  table { width: 100%; border-collapse: collapse; font-size: ${compact ? '11px' : '13px'}; table-layout: fixed; }
  thead th {
    position: sticky; top: 0;
    text-align: left;
    padding: ${compact ? '4px 5px' : '6px 8px'};
    background: var(--vscode-editorWidget-background, var(--vscode-editor-background));
    border-bottom: 1px solid var(--vscode-panel-border, #444);
    cursor: pointer;
    user-select: none;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  thead th:hover { color: var(--vscode-textLink-foreground); }
  thead th .arrow { opacity: 0.6; font-size: 10px; margin-left: 4px; }
  tbody tr { border-bottom: 1px solid var(--vscode-panel-border, #333); }
  tbody tr:hover { background: var(--vscode-list-hoverBackground); }
  tbody tr.all-row { background: var(--vscode-list-inactiveSelectionBackground, transparent); }
  td {
    padding: ${compact ? '4px 5px' : '5px 8px'};
    vertical-align: middle;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  td.op { text-align: right; white-space: nowrap; }
  .badge {
    display: inline-block;
    font-size: 10px;
    padding: 1px 6px;
    border-radius: 8px;
    margin-left: 6px;
    background: var(--vscode-badge-background);
    color: var(--vscode-badge-foreground);
  }
  .muted { color: var(--vscode-descriptionForeground); }
  .empty, .error, .loading { padding: 24px 4px; color: var(--vscode-descriptionForeground); font-size: 12px; }
  .error { color: var(--vscode-errorForeground); }
  .col-eventName, .col-subName { ${compact ? 'display: none;' : ''} }
</style>
</head>
<body>
  <div class="toolbar">
    <input id="search" type="text" placeholder="検索 (Event ID / 名前 / Sub)" />
    <button id="refreshBtn" class="secondary icon" title="再取得">⟳</button>
  </div>
  <div id="status"></div>
  <table id="grid" style="display:none">
    <thead>
      <tr>
        <th data-key="eventId">Event ID<span class="arrow"></span></th>
        <th data-key="eventName" class="col-eventName">Event名<span class="arrow"></span></th>
        <th data-key="scope">Sub<span class="arrow"></span></th>
        <th data-key="subName" class="col-subName">Sub名<span class="arrow"></span></th>
        <th></th>
      </tr>
    </thead>
    <tbody id="gridBody"></tbody>
  </table>

<script nonce="${nonce}">
  const vscodeApi = acquireVsCodeApi();
  let rows = [];
  let openKeys = new Set();
  let sortKey = 'eventId';
  let sortAsc = true;

  const statusEl = document.getElementById('status');
  const gridEl = document.getElementById('grid');
  const bodyEl = document.getElementById('gridBody');
  const searchEl = document.getElementById('search');

  function setStatus(html) {
    statusEl.innerHTML = html;
    gridEl.style.display = html ? 'none' : '';
  }

  function keyFor(eventId, subId) {
    return eventId + '::' + (subId === null ? 'ALL' : subId);
  }

  function buildRows(events) {
    const out = [];
    (events || []).forEach((ev) => {
      const subs = ev.subEvents || [];
      out.push({
        eventId: String(ev.id != null ? ev.id : ''),
        eventName: ev.name || ev.title || '',
        scope: '▶ 全Sub一括',
        subName: subs.length + ' 件のSub',
        subId: null,
        isAll: true,
      });
      subs.forEach((s) => {
        out.push({
          eventId: String(ev.id != null ? ev.id : ''),
          eventName: ev.name || ev.title || '',
          scope: 'Sub: ' + s.subId,
          subName: s.name || s.title || '',
          subId: String(s.subId),
          isAll: false,
        });
      });
    });
    return out;
  }

  function render() {
    const q = searchEl.value.trim().toLowerCase();
    let filtered = rows.filter((r) => {
      if (!q) return true;
      return (r.eventId + ' ' + r.eventName + ' ' + r.scope + ' ' + r.subName).toLowerCase().includes(q);
    });
    filtered.sort((a, b) => {
      const av = String(a[sortKey] ?? '');
      const bv = String(b[sortKey] ?? '');
      const cmp = av.localeCompare(bv, 'ja', { numeric: true });
      return sortAsc ? cmp : -cmp;
    });

    document.querySelectorAll('thead th[data-key]').forEach((th) => {
      const arrow = th.querySelector('.arrow');
      arrow.textContent = th.dataset.key === sortKey ? (sortAsc ? '▲' : '▼') : '';
    });

    if (filtered.length === 0) {
      setStatus('<div class="empty">' + (rows.length === 0 ? 'イベントが見つかりませんでした' : '検索条件に一致する行がありません') + '</div>');
      return;
    }
    setStatus('');

    bodyEl.innerHTML = '';
    filtered.forEach((r) => {
      const tr = document.createElement('tr');
      if (r.isAll) tr.className = 'all-row';

      const tdEvent = document.createElement('td');
      tdEvent.textContent = r.eventId;
      tdEvent.title = r.eventId;
      tr.appendChild(tdEvent);

      const tdEventName = document.createElement('td');
      tdEventName.textContent = r.eventName;
      tdEventName.title = r.eventName;
      tdEventName.className = 'muted col-eventName';
      tr.appendChild(tdEventName);

      const tdScope = document.createElement('td');
      tdScope.appendChild(document.createTextNode(r.scope));
      tdScope.title = r.scope;
      if (openKeys.has(keyFor(r.eventId, r.subId))) {
        const badge = document.createElement('span');
        badge.className = 'badge';
        badge.textContent = '編集中';
        tdScope.appendChild(badge);
      }
      tr.appendChild(tdScope);

      const tdSubName = document.createElement('td');
      tdSubName.textContent = r.subName;
      tdSubName.title = r.subName;
      tdSubName.className = 'muted col-subName';
      tr.appendChild(tdSubName);

      const tdOp = document.createElement('td');
      tdOp.className = 'op';
      const btn = document.createElement('button');
      btn.textContent = '編集';
      btn.addEventListener('click', () => {
        vscodeApi.postMessage({ type: 'open', eventId: r.eventId, subId: r.subId });
      });
      tdOp.appendChild(btn);
      tr.appendChild(tdOp);

      bodyEl.appendChild(tr);
    });
  }

  document.querySelectorAll('thead th[data-key]').forEach((th) => {
    th.addEventListener('click', () => {
      const key = th.dataset.key;
      if (sortKey === key) { sortAsc = !sortAsc; } else { sortKey = key; sortAsc = true; }
      render();
    });
  });
  searchEl.addEventListener('input', render);
  document.getElementById('refreshBtn').addEventListener('click', () => {
    vscodeApi.postMessage({ type: 'refresh' });
  });

  window.addEventListener('message', (event) => {
    const msg = event.data;
    if (msg.type === 'loading') {
      setStatus('<div class="loading">読み込み中...</div>');
    } else if (msg.type === 'error') {
      setStatus('<div class="error">' + msg.message + '</div>');
    } else if (msg.type === 'setData') {
      rows = buildRows(msg.events);
      render();
    } else if (msg.type === 'openKeys') {
      openKeys = new Set(msg.openKeys || []);
      render();
    }
  });

  vscodeApi.postMessage({ type: 'ready' });
</script>
</body>
</html>`;
}

module.exports = { getGridHtml };

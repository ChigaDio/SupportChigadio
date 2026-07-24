import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';

// ============================================================
// DebugCommandConsole
//   ・DebugCommandの登録（コマンド名 + 引数[名前,型] + 戻り値[名前,型]）
//   ・登録済みDebugCommandからC#クラスを生成
//   ・WebSocket(ws://localhost:8765)経由でコマンドを実行し、結果をログ表示
//   ・入力中は Tab / Space 等で予測変換候補を表示
// ============================================================

const WS_URL = 'ws://localhost:8765';
const FIELD_TYPES = ['int', 'uint', 'float', 'double', 'bool', 'string', 'vector2', 'vector3'];

// ---- 見た目（ハッカー端末風） ----
const COLOR_BG = '#0a0e0a';
const COLOR_PANEL = '#0f1710';
const COLOR_GREEN = '#33ff66';
const COLOR_GREEN_DIM = '#1f9c44';
const COLOR_RED = '#ff5555';
const COLOR_AMBER = '#ffcc33';
const FONT = '"Consolas", "SF Mono", "Fira Code", monospace';

function uid() {
  return `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function castValue(raw, type) {
  switch (type) {
    case 'int':
    case 'uint': {
      const v = parseInt(raw, 10);
      return Number.isNaN(v) ? 0 : v;
    }
    case 'float':
    case 'double': {
      const v = parseFloat(raw);
      return Number.isNaN(v) ? 0 : v;
    }
    case 'bool':
      return raw === 'true' || raw === '1';
    case 'vector2': {
      const [x, y] = raw.split(',').map(Number);
      return { x: x || 0, y: y || 0 };
    }
    case 'vector3': {
      const [x, y, z] = raw.split(',').map(Number);
      return { x: x || 0, y: y || 0, z: z || 0 };
    }
    case 'string':
    default:
      return raw ?? '';
  }
}

function buildArgsObject(cmdDef, tokens) {
  const argsObj = {};
  for (const t of tokens.slice(1)) {
    const eq = t.indexOf('=');
    if (eq === -1) continue;
    const key = t.slice(0, eq);
    const rawVal = t.slice(eq + 1);
    const argDef = cmdDef.args.find((a) => a.name === key);
    if (!argDef) continue;
    argsObj[key] = castValue(rawVal, argDef.type);
  }
  return argsObj;
}

function formatData(data) {
  if (data === null || data === undefined) return '(データなし)';
  try {
    return JSON.stringify(data);
  } catch {
    return String(data);
  }
}

function nowStr() {
  return new Date().toLocaleTimeString('ja-JP', { hour12: false });
}

// ============================================================
// フィールドリストエディタ（引数 / 戻り値の定義に共用）
// ============================================================
function FieldListEditor({ title, fields, onChange }) {
  const addField = () => {
    onChange([...fields, { name: '', type: 'int' }]);
  };
  const updateField = (idx, patch) => {
    onChange(fields.map((f, i) => (i === idx ? { ...f, ...patch } : f)));
  };
  const removeField = (idx) => {
    onChange(fields.filter((_, i) => i !== idx));
  };

  return (
    <div style={{ marginTop: 8, marginBottom: 8 }}>
      <div style={{ color: COLOR_GREEN_DIM, fontSize: 12, marginBottom: 4 }}>
        {'>'} {title}
      </div>
      {fields.map((f, idx) => (
        <div key={idx} style={{ display: 'flex', gap: 6, marginBottom: 4 }}>
          <input
            value={f.name}
            placeholder="name"
            onChange={(e) => updateField(idx, { name: e.target.value })}
            style={inputStyle(120)}
          />
          <select
            value={f.type}
            onChange={(e) => updateField(idx, { type: e.target.value })}
            style={selectStyle}
          >
            {FIELD_TYPES.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
          <button onClick={() => removeField(idx)} style={btnStyle(COLOR_RED)}>
            削除
          </button>
        </div>
      ))}
      <button onClick={addField} style={btnStyle(COLOR_GREEN_DIM)}>
        + フィールド追加
      </button>
    </div>
  );
}

const inputStyle = (width) => ({
  width,
  background: '#000',
  color: COLOR_GREEN,
  border: `1px solid ${COLOR_GREEN_DIM}`,
  fontFamily: FONT,
  fontSize: 13,
  padding: '4px 6px',
  outline: 'none',
});

const selectStyle = {
  background: '#000',
  color: COLOR_GREEN,
  border: `1px solid ${COLOR_GREEN_DIM}`,
  fontFamily: FONT,
  fontSize: 13,
  padding: '4px 6px',
};

const btnStyle = (color) => ({
  background: 'transparent',
  color,
  border: `1px solid ${color}`,
  fontFamily: FONT,
  fontSize: 12,
  padding: '4px 10px',
  cursor: 'pointer',
});

// ============================================================
// コマンド新規登録フォーム
// ============================================================
function NewCommandForm({ onCreated }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [args, setArgs] = useState([]);
  const [hasReturn, setHasReturn] = useState(false);
  const [returnFields, setReturnFields] = useState([]);
  const [busy, setBusy] = useState(false);

  const reset = () => {
    setName('');
    setDescription('');
    setArgs([]);
    setHasReturn(false);
    setReturnFields([]);
  };

  const submit = async () => {
    if (!name.trim()) {
      alert('コマンド名は必須です');
      return;
    }
    setBusy(true);
    try {
      const createRes = await fetch('/api/debug-command', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name.trim() }),
      });
      const createJson = await createRes.json();
      if (!createRes.ok) throw new Error(createJson.error || '作成失敗');

      const detailRes = await fetch(`/api/debug-command/${encodeURIComponent(name.trim())}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ args, hasReturn, returnFields, description }),
      });
      const detailJson = await detailRes.json();
      if (!detailRes.ok) throw new Error(detailJson.error || '詳細保存失敗');

      reset();
      setOpen(false);
      onCreated();
    } catch (e) {
      alert('エラー: ' + e.message);
    } finally {
      setBusy(false);
    }
  };

  if (!open) {
    return (
      <button onClick={() => setOpen(true)} style={{ ...btnStyle(COLOR_GREEN), marginBottom: 12 }}>
        [+] NEW_DEBUG_COMMAND
      </button>
    );
  }

  return (
    <div
      style={{
        border: `1px solid ${COLOR_GREEN_DIM}`,
        padding: 12,
        marginBottom: 12,
        background: '#050805',
      }}
    >
      <div style={{ color: COLOR_AMBER, marginBottom: 8 }}>&gt;&gt; NEW_DEBUG_COMMAND._init</div>
      <div style={{ display: 'flex', gap: 6, marginBottom: 8, alignItems: 'center' }}>
        <span style={{ color: COLOR_GREEN_DIM, fontSize: 12 }}>name:</span>
        <input value={name} onChange={(e) => setName(e.target.value)} style={inputStyle(220)} />
      </div>

      <div style={{ display: 'flex', gap: 6, marginBottom: 8, alignItems: 'flex-start' }}>
        <span style={{ color: COLOR_GREEN_DIM, fontSize: 12, marginTop: 4 }}>desc:</span>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="このコマンドの説明（何をするコマンドか）"
          rows={2}
          style={{ ...inputStyle(360), resize: 'vertical', fontFamily: FONT }}
        />
      </div>

      <FieldListEditor title="ARGS" fields={args} onChange={setArgs} />

      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8 }}>
        <input
          type="checkbox"
          checked={hasReturn}
          onChange={(e) => setHasReturn(e.target.checked)}
          id="hasReturnChk"
        />
        <label htmlFor="hasReturnChk" style={{ color: COLOR_GREEN_DIM, fontSize: 12 }}>
          このコマンドはデータを返す
        </label>
      </div>
      {hasReturn && <FieldListEditor title="RETURN_FIELDS" fields={returnFields} onChange={setReturnFields} />}

      <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
        <button onClick={submit} disabled={busy} style={btnStyle(COLOR_GREEN)}>
          {busy ? '登録中...' : '登録'}
        </button>
        <button onClick={() => { reset(); setOpen(false); }} style={btnStyle(COLOR_RED)}>
          キャンセル
        </button>
      </div>
    </div>
  );
}

// ============================================================
// 登録済みコマンド一覧
// ============================================================
function CommandTable({ commands, onDelete, onGenerate, onGenerateAll }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <div style={{ color: COLOR_AMBER, fontSize: 13 }}>&gt;&gt; REGISTERED_COMMANDS ({commands.length})</div>
        <button onClick={onGenerateAll} style={btnStyle(COLOR_GREEN)}>全コマンドCS生成</button>
      </div>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
        <thead>
          <tr style={{ color: COLOR_GREEN_DIM, textAlign: 'left', borderBottom: `1px solid ${COLOR_GREEN_DIM}` }}>
            <th style={{ padding: '4px 6px' }}>NAME</th>
            <th style={{ padding: '4px 6px' }}>DESCRIPTION</th>
            <th style={{ padding: '4px 6px' }}>ARGS</th>
            <th style={{ padding: '4px 6px' }}>RETURN</th>
            <th style={{ padding: '4px 6px' }}>ACTION</th>
          </tr>
        </thead>
        <tbody>
          {commands.map((c) => (
            <tr key={c.id} style={{ borderBottom: `1px solid #0f2413` }}>
              <td style={{ padding: '4px 6px', color: COLOR_GREEN }}>{c.name}</td>
              <td style={{ padding: '4px 6px', color: COLOR_GREEN_DIM, maxWidth: 260 }}>
                {c.description || '-'}
              </td>
              <td style={{ padding: '4px 6px', color: COLOR_GREEN_DIM }}>
                {c.args.map((a) => `${a.name}:${a.type}`).join(', ') || '(なし)'}
              </td>
              <td style={{ padding: '4px 6px', color: c.hasReturn ? COLOR_AMBER : COLOR_GREEN_DIM }}>
                {c.hasReturn ? c.returnFields.map((r) => `${r.name}:${r.type}`).join(', ') : '-'}
              </td>
              <td style={{ padding: '4px 6px' }}>
                <button onClick={() => onGenerate(c.name)} style={{ ...btnStyle(COLOR_GREEN), marginRight: 6 }}>
                  CS生成
                </button>
                <button onClick={() => onDelete(c.name)} style={btnStyle(COLOR_RED)}>
                  削除
                </button>
              </td>
            </tr>
          ))}
          {commands.length === 0 && (
            <tr>
              <td colSpan={5} style={{ padding: '8px 6px', color: COLOR_GREEN_DIM }}>
                (登録済みのDebugCommandはありません)
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

// ============================================================
// メインコンポーネント
// ============================================================
function DebugCommandConsole() {
  const [commands, setCommands] = useState([]);
  const [connected, setConnected] = useState(false);
  const [input, setInput] = useState('');
  const [history, setHistory] = useState([]);
  const [selectedSuggestion, setSelectedSuggestion] = useState(0);
  const [commandHistory, setCommandHistory] = useState([]); // 入力送信履歴（古い→新しい順）

  const socketRef = useRef(null);
  const inputRef = useRef(null);
  const logEndRef = useRef(null);
  const historyIndexRef = useRef(null); // null = 履歴を辿っていない（現在入力中）。0が最新履歴。
  const draftRef = useRef(''); // 履歴を辿り始める直前に入力していた内容（↓で戻ってくる用）

  const fetchCommands = useCallback(() => {
    fetch('/api/debug-command-full')
      .then((res) => res.json())
      .then((data) => setCommands(Array.isArray(data) ? data : []))
      .catch((e) => console.error('DebugCommand一覧取得エラー:', e));
  }, []);

  useEffect(() => {
    fetchCommands();
  }, [fetchCommands]);

  // ---- WebSocket接続 ----
  useEffect(() => {
    const socket = new WebSocket(WS_URL);
    socketRef.current = socket;

    socket.onopen = () => setConnected(true);
    socket.onclose = () => setConnected(false);
    socket.onerror = () => setConnected(false);

    socket.onmessage = (event) => {
      let data;
      try {
        data = JSON.parse(event.data);
      } catch {
        return;
      }
      if (data.type !== 'response') return; // DebugLog等の通常ログは無視
      setHistory((prev) =>
        prev.map((h) => {
          if (h.id !== data.id) return h;
          if (data.error) {
            return { ...h, status: 'error', error: data.error, responseTime: data.time || nowStr() };
          }
          return { ...h, status: 'ok', response: data.data, responseTime: data.time || nowStr() };
        })
      );
    };

    return () => socket.close();
  }, []);

  // ---- ログ自動スクロール ----
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ block: 'end' });
  }, [history.length]);

  // ---- 予測変換候補 ----
  const suggestions = useMemo(() => {
    const tokens = input.split(/\s+/);
    if (tokens.length <= 1) {
      const partial = (tokens[0] || '').toLowerCase();
      if (!partial) return [];
      return commands
        .filter((c) => c.name.toLowerCase().startsWith(partial))
        .map((c) => ({
          type: 'command',
          label: c.name,
          hint: `${c.args.length}引数${c.hasReturn ? ' / 戻り値あり' : ''}${c.description ? ' - ' + c.description : ''}`,
        }));
    }
    const cmdDef = commands.find((c) => c.name === tokens[0]);
    if (!cmdDef) return [];
    const lastToken = tokens[tokens.length - 1];
    const usedNames = tokens.slice(1, -1).map((t) => t.split('=')[0]);
    const partialName = lastToken.split('=')[0].toLowerCase();
    return cmdDef.args
      .filter((a) => !usedNames.includes(a.name) && a.name.toLowerCase().startsWith(partialName))
      .map((a) => ({ type: 'arg', label: `${a.name}=`, hint: a.type }));
  }, [input, commands]);

  useEffect(() => {
    setSelectedSuggestion(0);
  }, [suggestions.length, input]);

  const acceptSuggestion = (sugg) => {
    if (!sugg) return;
    const tokens = input.split(/\s+/);
    tokens[tokens.length - 1] = sugg.label;
    let newInput = tokens.join(' ');
    if (sugg.type === 'command') newInput += ' ';
    setInput(newInput);
    inputRef.current?.focus();
  };

  const sendCommand = () => {
    const trimmed = input.trim();
    if (!trimmed) return;

    // コマンド履歴に記録（直前と同じ内容は積み増ししない）
    setCommandHistory((prev) => (prev[prev.length - 1] === trimmed ? prev : [...prev, trimmed]));
    historyIndexRef.current = null;
    draftRef.current = '';

    const tokens = trimmed.split(/\s+/);
    const cmdName = tokens[0];
    const cmdDef = commands.find((c) => c.name === cmdName);
    const id = uid();
    const time = nowStr();

    if (!cmdDef) {
      setHistory((prev) => [
        ...prev,
        { id, time, name: cmdName, argsText: trimmed, status: 'error', error: `未登録のコマンドです: ${cmdName}` },
      ]);
      setInput('');
      return;
    }

    const argsObj = buildArgsObject(cmdDef, tokens);
    const message = { type: 'command', id, name: cmdName, args: argsObj, time };

    if (!socketRef.current || socketRef.current.readyState !== WebSocket.OPEN) {
      setHistory((prev) => [
        ...prev,
        { id, time, name: cmdName, argsText: trimmed, status: 'error', error: 'WebSocket未接続です' },
      ]);
      setInput('');
      return;
    }

    socketRef.current.send(JSON.stringify(message));
    setHistory((prev) => [
      ...prev,
      { id, time, name: cmdName, argsText: trimmed, status: 'pending', sentArgs: argsObj },
    ]);
    setInput('');
  };

  // ↑↓でこれまで送信したコマンドを呼び出す（シェルのコマンド履歴と同じ挙動）。
  // dir: 'up' = より古い履歴へ, 'down' = より新しい履歴へ（さらに進むと入力途中の内容に戻る）
  const recallHistory = (dir) => {
    if (commandHistory.length === 0) return;
    if (dir === 'up') {
      if (historyIndexRef.current === null) {
        draftRef.current = input;
        historyIndexRef.current = 0;
      } else if (historyIndexRef.current < commandHistory.length - 1) {
        historyIndexRef.current += 1;
      }
      const idx = commandHistory.length - 1 - historyIndexRef.current;
      setInput(commandHistory[idx]);
    } else {
      if (historyIndexRef.current === null) return;
      if (historyIndexRef.current === 0) {
        historyIndexRef.current = null;
        setInput(draftRef.current);
      } else {
        historyIndexRef.current -= 1;
        const idx = commandHistory.length - 1 - historyIndexRef.current;
        setInput(commandHistory[idx]);
      }
    }
    // カーソルを末尾に置く
    requestAnimationFrame(() => {
      const el = inputRef.current;
      if (el) el.setSelectionRange(el.value.length, el.value.length);
    });
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Tab') {
      e.preventDefault();
      if (suggestions.length > 0) acceptSuggestion(suggestions[selectedSuggestion] || suggestions[0]);
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (suggestions.length > 0) {
        setSelectedSuggestion((s) => Math.min(s + 1, Math.max(suggestions.length - 1, 0)));
      } else {
        recallHistory('down');
      }
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (suggestions.length > 0) {
        setSelectedSuggestion((s) => Math.max(s - 1, 0));
      } else {
        recallHistory('up');
      }
    } else if (e.key === 'Enter') {
      e.preventDefault();
      sendCommand();
    }
  };

  const handleGenerate = (name) => {
    fetch(`/api/generate-debug-command/${encodeURIComponent(name)}`, { method: 'POST' })
      .then((res) => res.json())
      .then((result) => alert(result.message || result.error))
      .catch((e) => alert('エラー: ' + e.message));
  };

  const handleGenerateAll = () => {
    fetch('/api/generate-all-debug-command', { method: 'POST' })
      .then((res) => res.json())
      .then((result) => alert(result.message || result.error))
      .catch((e) => alert('エラー: ' + e.message));
  };

  const handleDelete = (name) => {
    if (!window.confirm(`DebugCommand「${name}」を削除しますか？`)) return;
    fetch('/api/debug-command', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    })
      .then((res) => res.json())
      .then(() => fetchCommands())
      .catch((e) => alert('削除エラー: ' + e.message));
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        background: COLOR_BG,
        color: COLOR_GREEN,
        fontFamily: FONT,
        padding: 20,
      }}
    >
      <style>{`
        @keyframes dbg-blink { 0%, 49% { opacity: 1; } 50%, 100% { opacity: 0; } }
        .dbg-cursor { animation: dbg-blink 1s step-start infinite; }
        ::selection { background: ${COLOR_GREEN}; color: #000; }
      `}</style>

      {/* --- タイトルバー --- */}
      <div
        style={{
          background: COLOR_PANEL,
          border: `1px solid ${COLOR_GREEN_DIM}`,
          padding: '8px 14px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 16,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#ff5f56', display: 'inline-block' }} />
          <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#ffbd2e', display: 'inline-block' }} />
          <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#27c93f', display: 'inline-block' }} />
          <span style={{ marginLeft: 10, color: COLOR_GREEN, letterSpacing: 1 }}>
            DEBUG_COMMAND_CONSOLE
          </span>
        </div>
        <div style={{ color: connected ? COLOR_GREEN : COLOR_RED, fontSize: 12 }}>
          {connected ? '● CONNECTED' : '○ DISCONNECTED'} :: {WS_URL}
        </div>
      </div>

      {/* --- コマンド定義エリア --- */}
      <NewCommandForm onCreated={fetchCommands} />
      <CommandTable
        commands={commands}
        onDelete={handleDelete}
        onGenerate={handleGenerate}
        onGenerateAll={handleGenerateAll}
      />

      {/* --- ターミナルログ --- */}
      <div
        style={{
          border: `1px solid ${COLOR_GREEN_DIM}`,
          background: '#000',
          height: 360,
          overflowY: 'auto',
          padding: 10,
          fontSize: 13,
          lineHeight: 1.6,
        }}
      >
        {history.length === 0 && (
          <div style={{ color: COLOR_GREEN_DIM }}>{'>'} コマンド実行ログはここに表示されます...</div>
        )}
        {history.map((h) => (
          <div key={h.id} style={{ marginBottom: 6 }}>
            <div>
              <span style={{ color: COLOR_GREEN_DIM }}>[{h.time}]</span>{' '}
              <span style={{ color: COLOR_AMBER }}>&gt;</span>{' '}
              <span style={{ color: COLOR_GREEN }}>{h.argsText}</span>
            </div>
            {h.status === 'pending' && (
              <div style={{ color: COLOR_GREEN_DIM }}>
                <span style={{ color: COLOR_GREEN_DIM }}>[....]</span> &lt; 応答待ち...
              </div>
            )}
            {h.status === 'ok' && (
              <div>
                <span style={{ color: COLOR_GREEN_DIM }}>[{h.responseTime}]</span>{' '}
                <span style={{ color: COLOR_AMBER }}>&lt;</span>{' '}
                <span style={{ color: COLOR_GREEN }}>{formatData(h.response)}</span>
              </div>
            )}
            {h.status === 'error' && (
              <div>
                <span style={{ color: COLOR_GREEN_DIM }}>[{h.responseTime || h.time}]</span>{' '}
                <span style={{ color: COLOR_RED }}>&lt; ERROR: {h.error}</span>
              </div>
            )}
          </div>
        ))}
        <div ref={logEndRef} />
      </div>

      {/* --- コマンド入力ライン --- */}
      <div style={{ position: 'relative', marginTop: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', border: `1px solid ${COLOR_GREEN_DIM}`, padding: '6px 10px', background: '#000' }}>
          <span style={{ color: COLOR_AMBER, marginRight: 8 }}>root@debug:~$</span>
          <input
            ref={inputRef}
            value={input}
            onChange={(e) => {
              historyIndexRef.current = null;
              setInput(e.target.value);
            }}
            onKeyDown={handleKeyDown}
            placeholder="command arg1=value1 arg2=value2 ..."
            style={{
              flex: 1,
              background: 'transparent',
              border: 'none',
              outline: 'none',
              color: COLOR_GREEN,
              fontFamily: FONT,
              fontSize: 14,
            }}
            spellCheck={false}
            autoComplete="off"
          />
          <span className="dbg-cursor" style={{ color: COLOR_GREEN }}>_</span>
        </div>

        {suggestions.length > 0 && (
          <div
            style={{
              position: 'absolute',
              bottom: '100%',
              left: 0,
              right: 0,
              background: COLOR_PANEL,
              border: `1px solid ${COLOR_GREEN_DIM}`,
              marginBottom: 4,
              maxHeight: 180,
              overflowY: 'auto',
              zIndex: 10,
            }}
          >
            {suggestions.map((s, i) => (
              <div
                key={s.label}
                onMouseDown={() => acceptSuggestion(s)}
                style={{
                  padding: '4px 10px',
                  display: 'flex',
                  justifyContent: 'space-between',
                  cursor: 'pointer',
                  background: i === selectedSuggestion ? '#123a1f' : 'transparent',
                  color: COLOR_GREEN,
                  fontSize: 13,
                }}
              >
                <span>{s.label}</span>
                <span style={{ color: COLOR_GREEN_DIM }}>{s.hint}</span>
              </div>
            ))}
          </div>
        )}
      </div>
      <div style={{ color: COLOR_GREEN_DIM, fontSize: 11, marginTop: 6 }}>
        Tab: 候補確定 / ↑↓: 候補選択(候補表示中) or 送信済みコマンド履歴を呼び出す / Enter: 実行 &nbsp;|&nbsp; 例: SpawnEnemy posX=1.5 posY=2.0
      </div>
    </div>
  );
}

export default DebugCommandConsole;
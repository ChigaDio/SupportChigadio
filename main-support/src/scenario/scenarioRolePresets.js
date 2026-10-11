// scenarioRolePresets.js
//
// Role の「名前付きプリセット」と「Roleクリップボード(コピー&貼り付け)」(React非依存)。
//  - プリセット: Role名ごとに、名前を付けたフィールド値のセットを複数保存し、後から呼び出す。
//    保存先は「サーバー(チーム共有)」。サーバーに繋がらないときだけ、このブラウザ(localStorage)に
//    保存しておき、後から「サーバーへ移行」できる。
//  - クリップボード: 別のサブグループへRoleを値ごとコピーするための一時置き場(ブラウザ内)。
//    別タブでもコピーした内容を貼り付けられるよう、storageイベントでキャッシュを更新する。
//
// 画面から同期的に読めるよう、プリセットは「メモリ上のキャッシュ」から返す。
// サーバーとの同期(refreshPresets/savePreset/deletePreset/migrateLocalPresets)は非同期。
// キャッシュが変わったら subscribePresets の購読者へ通知する(メニューの再描画用)。

const PRESET_KEY = 'scn-role-presets-v1'; // 旧バージョンがブラウザへ保存していた場所(未接続時の退避先も兼ねる)
const CLIPBOARD_KEY = 'scn-role-clipboard-v1';
const MAX_PRESETS_PER_ROLE = 30;
const PRESET_API = '/api/scenario-role-presets';

const safeStorage = () => {
  try {
    if (typeof window !== 'undefined' && window.localStorage) return window.localStorage;
  } catch (e) { /* アクセス不可(プライベートモード等) */ }
  return null;
};

const readJson = (key, fallback) => {
  const s = safeStorage();
  if (!s) return fallback;
  try {
    const raw = s.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch (e) {
    return fallback;
  }
};

const writeJson = (key, value) => {
  const s = safeStorage();
  if (!s) return false;
  try {
    s.setItem(key, JSON.stringify(value));
    return true;
  } catch (e) {
    return false; // 容量超過など
  }
};

const deepCopy = (v) => JSON.parse(JSON.stringify(v));

// ------------------------------------------------------------------
// プリセット
// ------------------------------------------------------------------
let serverCache = null; // { Role名: [{name, data, savedAt}] } / まだ取得していなければ null
let localCache = null; // ブラウザ内(未接続時の退避 / 旧バージョンの保存分)
const listeners = new Set();
const notify = () => listeners.forEach((fn) => { try { fn(); } catch (e) { /* 購読側のエラーは無視 */ } });

/** プリセットの変更通知を購読する。戻り値は解除関数。 */
export function subscribePresets(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

const loadLocal = () => {
  if (localCache === null) {
    const raw = readJson(PRESET_KEY, {});
    localCache = raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : {};
  }
  return localCache;
};
const saveLocal = (obj) => {
  if (!writeJson(PRESET_KEY, obj)) return false;
  localCache = obj;
  return true;
};

const asList = (x) => (Array.isArray(x) ? x : []);

/**
 * Role名のプリセット一覧: [{ name, data, savedAt, local? }] (新しい順)。
 * サーバーのものに加えて、サーバーに無い(未移行の)ブラウザ内のものを local:true で末尾に出す。
 */
export function listPresets(roleName) {
  const server = serverCache ? asList(serverCache[roleName]) : [];
  const names = new Set(server.map((p) => p.name));
  const local = asList(loadLocal()[roleName]).filter((p) => !names.has(p.name)).map((p) => ({ ...p, local: true }));
  return [...server, ...local];
}

/** サーバーに未移行の、ブラウザ内のプリセット件数。 */
export function getLocalOnlyCount() {
  const local = loadLocal();
  return Object.keys(local).reduce((n, role) => {
    const names = new Set(serverCache ? asList(serverCache[role]).map((p) => p.name) : []);
    return n + asList(local[role]).filter((p) => !names.has(p.name)).length;
  }, 0);
}

const requestJson = async (url, options) => {
  const res = await fetch(url, options);
  let body = null;
  try { body = await res.json(); } catch (e) { /* 本文なし */ }
  return { ok: res.ok, status: res.status, body };
};

/** サーバーから最新のプリセットを取得する。戻り値: 取得できたか */
export async function refreshPresets() {
  try {
    const r = await requestJson(PRESET_API);
    if (!r.ok || !r.body || typeof r.body.presets !== 'object') return false;
    serverCache = r.body.presets || {};
    notify();
    return true;
  } catch (e) {
    return false;
  }
}

/**
 * プリセットを保存する(同名なら上書き)。
 * 戻り値: { ok, shared }  shared=true: サーバー(チーム共有)に保存 / false: このブラウザにだけ保存
 */
export async function savePreset(roleName, presetName, data) {
  const name = String(presetName || '').trim();
  if (!roleName || !name || !Array.isArray(data)) return { ok: false, shared: false };
  try {
    const r = await requestJson(PRESET_API, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ roleName, name, data }),
    });
    if (r.ok && r.body && Array.isArray(r.body.presets)) {
      serverCache = { ...(serverCache || {}), [roleName]: r.body.presets };
      // 同名のブラウザ内の古いものは不要(サーバー側が正)
      const local = { ...loadLocal() };
      if (local[roleName]) {
        local[roleName] = local[roleName].filter((p) => p.name !== name);
        if (local[roleName].length === 0) delete local[roleName];
        saveLocal(local);
      }
      notify();
      return { ok: true, shared: true };
    }
    if (r.status >= 400 && r.status < 500) return { ok: false, shared: false, error: (r.body && r.body.error) || `HTTP ${r.status}` };
  } catch (e) { /* 未接続 → ブラウザ内へ退避 */ }
  const local = { ...loadLocal() };
  const others = asList(local[roleName]).filter((p) => p.name !== name);
  local[roleName] = [{ name, data: deepCopy(data), savedAt: Date.now() }, ...others].slice(0, MAX_PRESETS_PER_ROLE);
  if (!saveLocal(local)) return { ok: false, shared: false };
  notify();
  return { ok: true, shared: false };
}

/** プリセットを削除する(サーバーとブラウザ内の両方から)。戻り値: 削除できたか */
export async function deletePreset(roleName, presetName) {
  let removed = false;
  const onServer = serverCache && asList(serverCache[roleName]).some((p) => p.name === presetName);
  if (onServer) {
    try {
      const r = await requestJson(`${PRESET_API}?roleName=${encodeURIComponent(roleName)}&name=${encodeURIComponent(presetName)}`, { method: 'DELETE' });
      if (r.ok || r.status === 404) {
        const next = { ...serverCache };
        const list = asList(next[roleName]).filter((p) => p.name !== presetName);
        if (list.length > 0) next[roleName] = list; else delete next[roleName];
        serverCache = next;
        removed = true;
      } else {
        return false; // サーバー側で消せなかった(ブラウザ内だけ消すと食い違うので何もしない)
      }
    } catch (e) {
      return false;
    }
  }
  const local = { ...loadLocal() };
  if (local[roleName] && local[roleName].some((p) => p.name === presetName)) {
    local[roleName] = local[roleName].filter((p) => p.name !== presetName);
    if (local[roleName].length === 0) delete local[roleName];
    saveLocal(local);
    removed = true;
  }
  if (removed) notify();
  return removed;
}

/** ブラウザ内にだけあるプリセットを、サーバーへ移行する(同名がサーバーにあれば上書きしない)。 */
export async function migrateLocalPresets() {
  const local = loadLocal();
  const payload = {};
  Object.keys(local).forEach((role) => {
    const names = new Set(serverCache ? asList(serverCache[role]).map((p) => p.name) : []);
    const items = asList(local[role]).filter((p) => !names.has(p.name));
    if (items.length > 0) payload[role] = items;
  });
  if (Object.keys(payload).length === 0) return { ok: true, imported: 0, skipped: 0 };
  try {
    const r = await requestJson(`${PRESET_API}/import`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ presets: payload }),
    });
    if (!r.ok || !r.body) return { ok: false, imported: 0, skipped: 0 };
    serverCache = r.body.presets || serverCache;
    // 取り込めたもの(サーバーに存在するようになったもの)をブラウザ内から外す
    const remaining = {};
    Object.keys(local).forEach((role) => {
      const names = new Set(asList(serverCache && serverCache[role]).map((p) => p.name));
      const rest = asList(local[role]).filter((p) => !names.has(p.name));
      if (rest.length > 0) remaining[role] = rest;
    });
    saveLocal(remaining);
    notify();
    return { ok: true, imported: r.body.imported || 0, skipped: r.body.skipped || 0 };
  } catch (e) {
    return { ok: false, imported: 0, skipped: 0 };
  }
}

/** 呼び出し用に、データを複製して返す(フォーム側が参照を保持しても元データが変わらないように)。 */
export function getPresetData(roleName, presetName) {
  const p = listPresets(roleName).find((x) => x.name === presetName);
  return p ? deepCopy(p.data) : null;
}

// ------------------------------------------------------------------
// Roleクリップボード
// ------------------------------------------------------------------
let clipCache = null;
const loadClip = () => {
  if (clipCache === null) {
    const raw = readJson(CLIPBOARD_KEY, []);
    clipCache = Array.isArray(raw) ? raw : [];
  }
  return clipCache;
};

if (typeof window !== 'undefined' && window.addEventListener) {
  window.addEventListener('storage', (e) => {
    if (e.key === CLIPBOARD_KEY) clipCache = null;
    if (e.key === PRESET_KEY) localCache  = null;
  });
}

/** クリップボードの中身: [{ id, name, branchType, data }] (メモリ上のキャッシュなので何度呼んでも軽い) */
export function getRoleClipboard() {
  return loadClip();
}

/** roles: [{ id, name, branchType, data }]。uniqueIdは貼り付け時に新しく採番するので保存しない。 */
export function setRoleClipboard(roles) {
  const items = (roles || []).map((r) => ({
    id: r.id, name: r.name, branchType: r.branchType || 'General', data: deepCopy(r.data || []),
  }));
  clipCache = items;
  writeJson(CLIPBOARD_KEY, items);
  return items.length;
}

/**
 * 貼り付け用の uniqueId を count 個、重複しないように採番する。
 * 既存の採番は Date.now() だが、連続して貼り付けると同一ミリ秒で衝突しうるため、
 * 「現在時刻」と「既存IDの最大値+1」の大きい方から連番を振る。
 */
export function makeUniqueIds(count, existingIds = []) {
  let base = Date.now();
  existingIds.forEach((id) => {
    const n = Number(id);
    if (Number.isFinite(n) && n >= base) base = n + 1;
  });
  return Array.from({ length: count }, (_, i) => String(base + i));
}

// テスト用: キャッシュを捨てる
export function __resetCachesForTest() { serverCache = null; localCache = null; clipCache = null; listeners.clear(); }

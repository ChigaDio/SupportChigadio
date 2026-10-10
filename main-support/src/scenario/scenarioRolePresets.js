// scenarioRolePresets.js
//
// Role の「名前付きプリセット」と「Roleクリップボード(コピー&貼り付け)」(React非依存)。
// どちらもブラウザの localStorage に保存する(このPC・このブラウザ専用)。
//  - プリセット: Role名ごとに、名前を付けたフィールド値のセットを複数保存し、後から呼び出す。
//  - クリップボード: 別のサブグループへRoleを値ごとコピーするための一時置き場。
//    別タブでもコピーした内容を貼り付けられるよう、storageイベントでメモリ上のキャッシュを更新する。

const PRESET_KEY = 'scn-role-presets-v1';
const CLIPBOARD_KEY = 'scn-role-clipboard-v1';
const MAX_PRESETS_PER_ROLE = 30;

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
let presetCache = null;
const loadPresets = () => {
  if (presetCache === null) {
    const raw = readJson(PRESET_KEY, {});
    presetCache = raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : {};
  }
  return presetCache;
};

/** Role名のプリセット一覧: [{ name, data, savedAt }] (新しい順) */
export function listPresets(roleName) {
  const list = loadPresets()[roleName];
  return Array.isArray(list) ? list : [];
}

/** プリセットを保存する(同名なら上書き)。戻り値: 保存できたか */
export function savePreset(roleName, presetName, data) {
  const name = String(presetName || '').trim();
  if (!roleName || !name || !Array.isArray(data)) return false;
  const all = { ...loadPresets() };
  const others = (all[roleName] || []).filter((p) => p.name !== name);
  const next = [{ name, data: deepCopy(data), savedAt: Date.now() }, ...others].slice(0, MAX_PRESETS_PER_ROLE);
  all[roleName] = next;
  if (!writeJson(PRESET_KEY, all)) return false;
  presetCache = all;
  return true;
}

export function deletePreset(roleName, presetName) {
  const all = { ...loadPresets() };
  if (!all[roleName]) return false;
  all[roleName] = all[roleName].filter((p) => p.name !== presetName);
  if (all[roleName].length === 0) delete all[roleName];
  if (!writeJson(PRESET_KEY, all)) return false;
  presetCache = all;
  return true;
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
    if (e.key === PRESET_KEY) presetCache = null;
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
export function __resetCachesForTest() { presetCache = null; clipCache = null; }

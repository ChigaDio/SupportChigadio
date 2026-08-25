// scenarioTransactionDsl.js
//
// Transactionのロール入力を「上から順にRoleを呼び出す」テキストDSLとして
// 読み書きするための、独立した（React/DOM非依存の）コア実装。
// ScenarioTransactionCodeEditor.js（CodeMirror統合）と
// ScenarioEventTransition.js（GUIモードとの相互変換）の両方から利用する。
//
// 文法（1行1コマンド）:
//   line       := blank | comment | call
//   comment    := '#' 任意の文字列（行全体 or 行末コメント）
//   call       := RoleName (WS argument)*
//   argument   := fieldName '=' value
//   value      := string | number | bool | vector | array | bareword
//   string     := "..." （\" \\ エスケープ対応）
//   number     := -?数字(.数字)?
//   bool       := true | false
//   vector     := '(' number (',' number)+ ')'
//   array      := '[' (value (',' value)*)? ']'
//   bareword   := 上記以外の連続文字（enum値・ID参照名などに使う）
//
// 例:
//   # 主人公が挨拶する
//   Say text="こんにちは" speed=1.5 wait=true
//   VoiceLine voiceId=Scenario_Line001
//   Move target=(1.0, 0, 2.5)
//   SetFlags flags=[Flag1, Flag3]

// ============================================================
// トークナイザ
// ============================================================

const TOKEN_PATTERN = /#.*$|"(?:[^"\\]|\\.)*"|[(){}[\],=:]|-?\d+(?:\.\d+)?|[^\s(){}[\],="#:]+/g;

export function tokenizeLine(line) {
  const tokens = [];
  for (const m of line.matchAll(TOKEN_PATTERN)) {
    const raw = m[0];
    const from = m.index;
    const to = from + raw.length;
    let type;
    if (raw.startsWith('#')) type = 'COMMENT';
    else if (raw.startsWith('"')) type = 'STRING';
    else if (raw === '(') type = 'LPAREN';
    else if (raw === ')') type = 'RPAREN';
    else if (raw === '[') type = 'LBRACKET';
    else if (raw === ']') type = 'RBRACKET';
    else if (raw === '{') type = 'LBRACE';
    else if (raw === '}') type = 'RBRACE';
    else if (raw === ':') type = 'COLON';
    else if (raw === ',') type = 'COMMA';
    else if (raw === '=') type = 'EQUALS';
    else if (/^-?\d/.test(raw)) type = 'NUMBER';
    else type = 'IDENT';
    tokens.push({ type, value: raw, from, to });
  }
  return tokens;
}

// ============================================================
// 診断（エラー/警告）
// ============================================================

export class DslIssue {
  constructor(message, from, to, line, severity = 'error') {
    this.message = message;
    this.from = from;
    this.to = to;
    this.line = line;
    this.severity = severity;
  }
}

// ============================================================
// 行パーサー: 1行 → AST
// ============================================================

function collectValueTokens(tokens, start) {
  if (start >= tokens.length) return { valueTokens: [], nextIndex: start, error: '値が指定されていません' };
  const t = tokens[start];
  const OPEN_CLOSE = { LPAREN: 'RPAREN', LBRACKET: 'RBRACKET', LBRACE: 'RBRACE' };
  if (OPEN_CLOSE[t.type]) {
    const closeType = OPEN_CLOSE[t.type];
    let depth = 1;
    let j = start + 1;
    const collected = [t];
    while (j < tokens.length && depth > 0) {
      if (tokens[j].type === t.type) depth += 1;
      if (tokens[j].type === closeType) depth -= 1;
      collected.push(tokens[j]);
      j += 1;
    }
    if (depth !== 0) return { valueTokens: collected, nextIndex: j, error: '括弧が閉じられていません' };
    return { valueTokens: collected, nextIndex: j, error: null };
  }
  if (t.type === 'STRING' || t.type === 'NUMBER' || t.type === 'IDENT') {
    return { valueTokens: [t], nextIndex: start + 1, error: null };
  }
  return { valueTokens: [t], nextIndex: start + 1, error: `予期しないトークンです: ${t.value}` };
}

/**
 * 1行をパースしてASTノードを返す。
 * 戻り値の type: 'blank' | 'comment' | 'call'
 */
export function parseLine(rawLine, lineNumber) {
  const tokens = tokenizeLine(rawLine);
  const errors = [];

  if (tokens.length === 0) {
    return { type: 'blank', line: lineNumber, raw: rawLine, errors };
  }
  if (tokens[0].type === 'COMMENT') {
    return { type: 'comment', line: lineNumber, raw: rawLine, errors };
  }

  let trailingComment = null;
  if (tokens[tokens.length - 1].type === 'COMMENT') {
    trailingComment = tokens.pop();
  }

  const nameToken = tokens[0];
  if (nameToken.type !== 'IDENT') {
    errors.push(new DslIssue('Role名を指定してください', nameToken.from, nameToken.to, lineNumber));
    return { type: 'call', line: lineNumber, raw: rawLine, name: null, args: [], trailingComment, errors };
  }

  const args = [];
  let i = 1;
  while (i < tokens.length) {
    const keyToken = tokens[i];
    if (keyToken.type !== 'IDENT') {
      errors.push(new DslIssue(`引数名を指定してください（fieldName=value 形式）`, keyToken.from, keyToken.to, lineNumber));
      i += 1;
      continue;
    }
    const eqToken = tokens[i + 1];
    if (!eqToken || eqToken.type !== 'EQUALS') {
      errors.push(new DslIssue(`'=' が必要です: ${keyToken.value}=...`, keyToken.from, keyToken.to, lineNumber));
      i += 1;
      continue;
    }
    const { valueTokens, nextIndex, error } = collectValueTokens(tokens, i + 2);
    if (error) {
      errors.push(new DslIssue(error, keyToken.from, eqToken.to, lineNumber));
    }
    const to = valueTokens.length ? valueTokens[valueTokens.length - 1].to : eqToken.to;
    args.push({ key: keyToken, valueTokens, from: keyToken.from, to });
    i = nextIndex;
  }

  return { type: 'call', line: lineNumber, raw: rawLine, name: nameToken, args, trailingComment, errors };
}

export function parseDocument(text) {
  const lines = text.split('\n');
  return lines.map((line, idx) => parseLine(line, idx));
}

// ============================================================
// 値の型変換（トークン列 → 実際の値）
// スキーマのfield.typeに応じて変換する。GameCore側の型付け
// （BaseRoleInputForm.js の getDefaultValue と同じ型集合）に揃えている。
// ============================================================

function stripQuotes(raw) {
  return raw.slice(1, -1).replace(/\\"/g, '"').replace(/\\\\/g, '\\');
}

function tokensToSourceText(tokens) {
  if (tokens.length === 0) return '';
  const from = tokens[0].from;
  const to = tokens[tokens.length - 1].to;
  return { from, to };
}

const NUMERIC_TYPES = new Set(['int', 'uint', 'short', 'long', 'byte']);
const FLOAT_TYPES = new Set(['float', 'double', 'decimal']);
const VECTOR_SIZES = { vector2: 2, vector3: 3, vector4: 4 };

/**
 * トークン列を、指定された型に応じた実値へ変換する。
 * 失敗時は { value: undefined, error: string } を返す（例外を投げない。
 * リンター/コンパイラ双方から使い回せるようにするため）。
 * lineText: bit/color/bezier/dictionary（JSONリテラル）の復元に使う元の行文字列。
 */
export function coerceValueTokens(valueTokens, fieldType, fieldOptions, lineText) {
  const baseType = (fieldType || 'string').endsWith('[]') ? fieldType.slice(0, -2) : fieldType;
  const isArrayType = (fieldType || '').endsWith('[]');

  if (baseType === 'bit' || baseType === 'color' || baseType === 'bezier' || baseType === 'dictionary') {
    if (valueTokens.length === 0) return { value: undefined, error: '値が指定されていません' };
    const from = valueTokens[0].from;
    const to = valueTokens[valueTokens.length - 1].to;
    const raw = typeof lineText === 'string' ? lineText.slice(from, to) : valueTokens.map((t) => t.value).join('');
    try {
      return { value: JSON.parse(raw), error: null };
    } catch (e) {
      return { value: undefined, error: `${baseType}はJSON形式で指定してください（例: {"size":8,"bits":[0,2]}）` };
    }
  }

  if (isArrayType) {
    if (valueTokens.length === 0 || valueTokens[0].type !== 'LBRACKET') {
      return { value: undefined, error: `配列は [値, 値, ...] の形式で指定してください` };
    }
    const inner = valueTokens.slice(1, -1);
    const items = splitByComma(inner);
    const result = [];
    for (const itemTokens of items) {
      const { value, error } = coerceValueTokens(itemTokens, baseType, fieldOptions, lineText);
      if (error) return { value: undefined, error };
      result.push(value);
    }
    return { value: result, error: null };
  }

  if (baseType in VECTOR_SIZES) {
    const size = VECTOR_SIZES[baseType];
    if (valueTokens.length === 0 || valueTokens[0].type !== 'LPAREN') {
      return { value: undefined, error: `${baseType}は (x, y${size > 2 ? ', z' : ''}${size > 3 ? ', w' : ''}) の形式で指定してください` };
    }
    const inner = valueTokens.slice(1, -1);
    const parts = splitByComma(inner);
    if (parts.length !== size) {
      return { value: undefined, error: `${baseType}には${size}個の数値が必要です（${parts.length}個指定されています）` };
    }
    const nums = [];
    for (const p of parts) {
      if (p.length !== 1 || p[0].type !== 'NUMBER') {
        return { value: undefined, error: `${baseType}の要素は数値で指定してください` };
      }
      nums.push(Number(p[0].value));
    }
    return { value: nums, error: null };
  }

  if (valueTokens.length !== 1) {
    return { value: undefined, error: `値の形式が不正です` };
  }
  const tok = valueTokens[0];

  if (NUMERIC_TYPES.has(baseType)) {
    if (tok.type !== 'NUMBER') return { value: undefined, error: `整数を指定してください` };
    return { value: Math.trunc(Number(tok.value)), error: null };
  }
  if (FLOAT_TYPES.has(baseType)) {
    if (tok.type !== 'NUMBER') return { value: undefined, error: `数値を指定してください` };
    return { value: Number(tok.value), error: null };
  }
  if (baseType === 'bool') {
    if (tok.type === 'IDENT' && (tok.value === 'true' || tok.value === 'false')) {
      return { value: tok.value === 'true', error: null };
    }
    return { value: undefined, error: `true または false を指定してください` };
  }
  if (baseType === 'char') {
    const raw = tok.type === 'STRING' ? stripQuotes(tok.value) : tok.value;
    if (raw.length !== 1) return { value: undefined, error: `1文字だけ指定してください` };
    return { value: raw, error: null };
  }

  // string / enum / class_data_id / custom_class_data_id / voice_ref など:
  // 文字列としてそのまま扱う。field.optionsがあれば候補チェックする。
  const raw = tok.type === 'STRING' ? stripQuotes(tok.value) : tok.value;
  if (Array.isArray(fieldOptions) && fieldOptions.length > 0 && !fieldOptions.includes(raw)) {
    return { value: raw, error: `候補にありません: ${raw}（候補: ${fieldOptions.slice(0, 5).join(', ')}${fieldOptions.length > 5 ? '...' : ''}）`, warningOnly: true };
  }
  return { value: raw, error: null };
}

function splitByComma(tokens) {
  const groups = [];
  let current = [];
  let depth = 0;
  for (const t of tokens) {
    if (t.type === 'LPAREN' || t.type === 'LBRACKET') depth += 1;
    if (t.type === 'RPAREN' || t.type === 'RBRACKET') depth -= 1;
    if (t.type === 'COMMA' && depth === 0) {
      groups.push(current);
      current = [];
    } else {
      current.push(t);
    }
  }
  if (current.length > 0 || groups.length > 0) groups.push(current);
  return groups.filter((g) => g.length > 0);
}

// ============================================================
// 値のシリアライズ（実値 → DSLソーステキスト）。decompile用。
// ============================================================

function serializeValue(value, fieldType) {
  const baseType = (fieldType || 'string').endsWith('[]') ? fieldType.slice(0, -2) : fieldType;
  const isArrayType = (fieldType || '').endsWith('[]');

  if (isArrayType) {
    const arr = Array.isArray(value) ? value : [];
    return `[${arr.map((v) => serializeValue(v, baseType)).join(', ')}]`;
  }
  if (baseType in VECTOR_SIZES) {
    const arr = Array.isArray(value) ? value : [];
    return `(${arr.join(', ')})`;
  }
  if (NUMERIC_TYPES.has(baseType) || FLOAT_TYPES.has(baseType)) {
    return String(value ?? 0);
  }
  if (baseType === 'bool') {
    return value ? 'true' : 'false';
  }
  if (baseType === 'bit' || baseType === 'color' || baseType === 'bezier' || baseType === 'dictionary') {
    return JSON.stringify(value ?? {});
  }
  // string / enum / ID参照 / char 等
  const s = value === undefined || value === null ? '' : String(value);
  if (s === '' || /[\s"#=()[\],]/.test(s)) {
    return `"${s.replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"`;
  }
  return s;
}

// ============================================================
// コンパイル: DSLテキスト → roles[]（アプリ内部データ形式）
// roleSchemas: { [roleName]: { fields: [{name, type, options}] } }
// ============================================================

export function compileDocument(text, roleSchemas, existingRoles = []) {
  const parsedLines = parseDocument(text);
  const diagnostics = [];
  const roles = [];

  // 既存のuniqueIdを可能な限り引き継ぐ（同名Roleの出現順で対応付け、
  // GUIモードとテキストモードを往復してもID安定性を保つため）
  const existingByName = new Map();
  for (const r of existingRoles) {
    if (!existingByName.has(r.name)) existingByName.set(r.name, []);
    existingByName.get(r.name).push(r.uniqueId);
  }
  const usedCount = new Map();

  for (const node of parsedLines) {
    if (node.type !== 'call') {
      for (const e of node.errors) diagnostics.push(e);
      continue;
    }
    for (const e of node.errors) diagnostics.push(e);
    if (!node.name) continue;

    const roleName = node.name.value;
    const schema = roleSchemas[roleName];
    if (!schema) {
      diagnostics.push(new DslIssue(`未知のRoleです: ${roleName}`, node.name.from, node.name.to, node.line));
      continue;
    }

    const fieldByName = new Map(schema.fields.map((f) => [f.name, f]));
    const seenFields = new Set();
    const data = [];

    for (const arg of node.args) {
      const fieldName = arg.key.value;
      const field = fieldByName.get(fieldName);
      if (!field) {
        diagnostics.push(new DslIssue(
          `Role「${roleName}」に存在しないフィールドです: ${fieldName}`,
          arg.key.from, arg.key.to, node.line
        ));
        continue;
      }
      if (seenFields.has(fieldName)) {
        diagnostics.push(new DslIssue(`フィールド ${fieldName} が重複しています`, arg.key.from, arg.key.to, node.line, 'warning'));
      }
      seenFields.add(fieldName);

      const { value, error, warningOnly } = coerceValueTokens(arg.valueTokens, field.type, field.options, node.raw);
      if (error) {
        diagnostics.push(new DslIssue(error, arg.from, arg.to, node.line, warningOnly ? 'warning' : 'error'));
      }
      data.push({ name: fieldName, type: field.type, value: value === undefined ? null : value });
    }

    const idx = usedCount.get(roleName) || 0;
    usedCount.set(roleName, idx + 1);
    const candidates = existingByName.get(roleName) || [];
    const uniqueId = candidates[idx] || `${roleName}_${Date.now()}_${roles.length}_${Math.random().toString(36).slice(2, 7)}`;

    roles.push({ uniqueId, name: roleName, data });
  }

  return { roles, diagnostics };
}

// ============================================================
// デコンパイル: roles[]（アプリ内部データ形式） → DSLテキスト
// ============================================================

export function decompileRoles(roles, roleSchemas) {
  const lines = [];
  for (const role of roles || []) {
    const schema = roleSchemas[role.name];
    const parts = [role.name];
    for (const field of role.data || []) {
      const fieldDef = schema?.fields?.find((f) => f.name === field.name);
      const type = fieldDef?.type || field.type || 'string';
      parts.push(`${field.name}=${serializeValue(field.value, type)}`);
    }
    lines.push(parts.join(' '));
  }
  return lines.join('\n');
}

// ============================================================
// 診断一覧の取得（Linter用）
// ============================================================

export function lintDocument(text, roleSchemas) {
  const { diagnostics } = compileDocument(text, roleSchemas, []);
  return diagnostics;
}

// ============================================================
// 補完候補の算出（Autocomplete用）
// cursorLine: 0-indexed行番号, cursorCh: 行内の文字位置
// ============================================================

export function getCompletionsAt(text, cursorLine, cursorCh, roleNames, roleSchemas) {
  const lines = text.split('\n');
  const line = lines[cursorLine] ?? '';
  const tokens = tokenizeLine(line).filter((t) => t.type !== 'COMMENT');

  if (tokens.length === 0) {
    return roleNames.map((n) => ({ label: n, type: 'role' }));
  }

  // 最初のトークン（Role名）を編集中かどうか
  const first = tokens[0];
  if (cursorCh <= first.to) {
    if (first.type !== 'IDENT') return [];
    const prefix = line.slice(first.from, cursorCh);
    return roleNames
      .filter((n) => n.toLowerCase().startsWith(prefix.toLowerCase()))
      .map((n) => ({ label: n, type: 'role' }));
  }

  const roleName = first.value;
  const schema = roleSchemas[roleName];
  if (!schema) return [];

  // "fieldName=値" の値部分（=の直後〜値トークンの終わりまで）にカーソルがあれば値候補を返す
  for (let i = 1; i < tokens.length; i++) {
    const t = tokens[i];
    if (t.type !== 'EQUALS') continue;
    const valueToken = tokens[i + 1];
    const regionStart = t.to;
    const regionEnd = valueToken ? valueToken.to : Infinity;
    if (cursorCh < regionStart || cursorCh > regionEnd) continue;

    const fieldName = tokens[i - 1]?.value;
    const field = schema.fields.find((f) => f.name === fieldName);
    if (!field) return [];
    const prefix = valueToken && cursorCh > valueToken.from ? line.slice(valueToken.from, cursorCh) : '';
    if (field.options?.length) {
      return field.options
        .filter((o) => o.toLowerCase().startsWith(prefix.toLowerCase()))
        .map((o) => ({ label: o, type: 'value' }));
    }
    if (field.type === 'bool') {
      return ['true', 'false']
        .filter((o) => o.startsWith(prefix))
        .map((o) => ({ label: o, type: 'value' }));
    }
    return [];
  }

  // それ以外（Role名の後、いずれの"="の値域にも該当しない）→ フィールド名を補完
  const usedFields = new Set();
  for (let i = 1; i < tokens.length; i++) {
    if (tokens[i].type === 'IDENT' && tokens[i + 1]?.type === 'EQUALS') usedFields.add(tokens[i].value);
  }
  const currentToken = tokens.find((t) => t !== first && t.type === 'IDENT' && cursorCh >= t.from && cursorCh <= t.to);
  const prefix = currentToken ? line.slice(currentToken.from, cursorCh) : '';
  return schema.fields
    .filter((f) => !usedFields.has(f.name) || f.name === currentToken?.value)
    .filter((f) => f.name.toLowerCase().startsWith(prefix.toLowerCase()))
    .map((f) => ({ label: `${f.name}=`, type: 'field', detail: f.type }));
}

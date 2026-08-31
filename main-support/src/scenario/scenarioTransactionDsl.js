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
//   value      := string | number | bool | object | array | bareword
//   string     := "..." （\" \\ エスケープ対応）
//   number     := -?数字(.数字)?
//   bool       := true | false
//   object     := '{' (fieldName ':' value (',' fieldName ':' value)*)? '}'
//                 class_data・Vector2/3/4・bit・color・bezier はすべてこの
//                 { フィールド名: 値, ... } という同じ形式で読み書きする
//                 （何段ネストしていても同じルールが再帰的に適用される）。
//   array      := '[' (value (',' value)*)? ']'
//   bareword   := 上記以外の連続文字（enum値・ID参照名などに使う）
//
// 例:
//   # 主人公が挨拶する
//   Say text="こんにちは" speed=1.5 wait=true
//   VoiceLine voiceId=Scenario_Line001
//   Move target={ x: 1.0, y: 0, z: 2.5 }
//   SetFlags flags=[Flag1, Flag3]
//   SetColor color={ r: 1, g: 0.5, b: 0, a: 1 }
//   SetCurve curve={ points: [{ time: 0, value: 0, inTangent: 0, outTangent: 0 }, { time: 1, value: 1, inTangent: 0, outTangent: 0 }] }
//   SetFlagBits bits={ size: 8, bits: [0, 2, 5] }

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
const VECTOR_FIELD_NAMES = { vector2: ['x', 'y'], vector3: ['x', 'y', 'z'], vector4: ['x', 'y', 'z', 'w'] };

// bit / color / bezier は、GUI側(BaseRoleInputForm.js)では専用エディタで組み立てているが、
// 実際に保存される値の形はどれも固定された名前付きフィールドを持つ「ただのオブジェクト」
// （bit: {size, bits}、color: {r,g,b,a}、bezier: {points: [{time,value,inTangent,outTangent}, ...]}）。
// class_dataと全く同じ「{ フィールド名: 値, ... }」の構文・パーサー・補完をそのまま
// 再利用できるよう、スキーマ側から subFields が来なくてもここで固定のsubFieldsを与える。
// (dictionary型だけはキー自体が動的なため、引き続きJSON直書きのままにしている)
const BEZIER_POINT_SUBFIELDS = [
  { name: 'time', type: 'float' },
  { name: 'value', type: 'float' },
  { name: 'inTangent', type: 'float' },
  { name: 'outTangent', type: 'float' },
];
const BUILTIN_STRUCT_SUBFIELDS = {
  bit: [
    { name: 'size', type: 'int' },
    { name: 'bits', type: 'int[]' },
  ],
  color: [
    { name: 'r', type: 'float' },
    { name: 'g', type: 'float' },
    { name: 'b', type: 'float' },
    { name: 'a', type: 'float' },
  ],
  bezier: [
    { name: 'points', type: 'BezierPoint[]', subFields: BEZIER_POINT_SUBFIELDS },
  ],
};

// フィールドが実際に使うべきsubFieldsを解決する。
// class_dataのようにスキーマ側(バックエンド)からsubFieldsが渡ってくる場合はそれを優先し、
// 渡ってこない組み込み構造体型(bit/color/bezier/vector2/3/4)の場合はここで補う。
function getEffectiveSubFields(fieldType, subFields) {
  if (Array.isArray(subFields) && subFields.length > 0) return subFields;
  const baseType = (fieldType || '').endsWith('[]') ? fieldType.slice(0, -2) : fieldType;
  if (BUILTIN_STRUCT_SUBFIELDS[baseType]) return BUILTIN_STRUCT_SUBFIELDS[baseType];
  if (VECTOR_FIELD_NAMES[baseType]) {
    return VECTOR_FIELD_NAMES[baseType].map((n) => ({ name: n, type: 'float' }));
  }
  return subFields;
}

function incrementTrailingNumber(id) {
  const m = String(id ?? '').match(/^(.*?)(\d+)$/);
  if (m) {
    const digits = m[2];
    const next = String(Number(digits) + 1).padStart(digits.length, '0');
    return m[1] + next;
  }
  return `${id}_2`;
}

// ============================================================
// 見出し(# ==== SUB:x NODE:y ====)を走査するためのヘルパー。
// 「新しいグループ/サブグループを、直前の兄弟からIDをインクリメントして追加する」
// ショートカットキー(Web版のScenarioTransactionCodeEditor.js・VSCode拡張の
// 両方から共通で使う)のために切り出してある。
// ============================================================

const GROUP_HEADER_RE = /^#\s*====\s*SUB:(\S+)\s+NODE:(\S+).*?====\s*$/;

/**
 * ドキュメント全文から見出し行(# ==== SUB:x NODE:y ====)を全て抜き出す。
 * 戻り値は出現順(=行番号順)の配列。
 */
export function findGroupHeaders(docText) {
  const lines = docText.split('\n');
  const headers = [];
  lines.forEach((line, idx) => {
    const m = line.match(GROUP_HEADER_RE);
    if (m) headers.push({ subId: m[1], pathKey: m[2], lineIndex: idx });
  });
  return headers;
}

/**
 * カーソル位置(0始まりの行番号)から見て、新しいグループ(トップレベルのノード)を
 * 追加する際に使う { subId, newPathKey } を求める。
 * 直近(カーソルより上)の見出しからSubIdの文脈を特定し、同じSubId・トップレベル
 * (pathKeyに "/" を含まない)の見出しのうち、ドキュメント中で最後に出てくるものの
 * IDをインクリメントする。見出しが1つも無い場合は SUB:1 の "1" から始める。
 */
export function computeNextGroupHeader(docText, cursorLine) {
  const headers = findGroupHeaders(docText);
  let currentSubId = null;
  for (let i = headers.length - 1; i >= 0; i--) {
    if (headers[i].lineIndex <= cursorLine) { currentSubId = headers[i].subId; break; }
  }
  if (!currentSubId) currentSubId = headers.length > 0 ? headers[0].subId : '1';

  const topLevel = headers.filter((h) => h.subId === currentSubId && !h.pathKey.includes('/'));
  const newPathKey = topLevel.length > 0
    ? incrementTrailingNumber(topLevel[topLevel.length - 1].pathKey)
    : '1';
  return { subId: currentSubId, newPathKey };
}

/**
 * カーソル位置(0始まりの行番号)から見て、新しいサブグループ(現在カーソルが
 * 属しているグループの中に、さらにネストしたノード)を追加する際に使う
 * { subId, newPathKey } を求める。カーソルがどのグループにも属していない
 * (直近に見出しが1つも見つからない)場合は null を返す。
 */
export function computeNextSubgroupHeader(docText, cursorLine) {
  const headers = findGroupHeaders(docText);
  let currentSubId = null;
  let currentParentId = null;
  for (let i = headers.length - 1; i >= 0; i--) {
    if (headers[i].lineIndex <= cursorLine) {
      currentSubId = headers[i].subId;
      currentParentId = headers[i].pathKey.split('/')[0];
      break;
    }
  }
  if (!currentSubId || !currentParentId) return null;

  const siblings = headers.filter(
    (h) => h.subId === currentSubId && h.pathKey.startsWith(`${currentParentId}/`)
  );
  const newLastSegment = siblings.length > 0
    ? incrementTrailingNumber(siblings[siblings.length - 1].pathKey.split('/').pop())
    : '1';
  return { subId: currentSubId, newPathKey: `${currentParentId}/${newLastSegment}` };
}

/**
 * DSLの "{ フィールド名: 値, ... }" オブジェクトリテラルを、指定されたsubFieldsの
 * スキーマに従ってパースする。class_data・bit・color・bezier・vector2/3/4のいずれの
 * オブジェクトリテラルもこの共通関数を通る（何段ネストしても再帰的に同じ処理になる）。
 */
function parseObjectLiteralTokens(valueTokens, subFields, lineText) {
  if (valueTokens.length === 0 || valueTokens[0].type !== 'LBRACE') {
    return { value: undefined, error: `{ フィールド名: 値, ... } の形式で指定してください（例: { x: 0, y: 0 }）` };
  }
  if (valueTokens[valueTokens.length - 1].type !== 'RBRACE') {
    return { value: undefined, error: '{ が閉じられていません' };
  }
  const inner = valueTokens.slice(1, -1);
  const groups = splitByComma(inner);
  const subFieldByName = new Map(subFields.map((f) => [f.name, f]));
  const result = {};
  for (const g of groups) {
    if (g.length === 0) continue;
    if (g[0].type !== 'IDENT' || g[1]?.type !== 'COLON') {
      return { value: undefined, error: `{ フィールド名: 値 } の形式で指定してください（例: { x: 0, y: 0 }）` };
    }
    const subName = g[0].value;
    const subField = subFieldByName.get(subName);
    if (!subField) {
      return { value: undefined, error: `存在しないフィールドです: ${subName}` };
    }
    const subValueTokens = g.slice(2);
    const { value, error } = coerceValueTokens(subValueTokens, subField.type, subField.options, lineText, subField.subFields);
    if (error) return { value: undefined, error: `${subName}: ${error}` };
    result[subName] = value;
  }
  return { value: result, error: null };
}

/**
 * トークン列を、指定された型に応じた実値へ変換する。
 * 失敗時は { value: undefined, error: string } を返す（例外を投げない。
 * リンター/コンパイラ双方から使い回せるようにするため）。
 * lineText: dictionary（JSONリテラル）の復元に使う元の行文字列。
 */
export function coerceValueTokens(valueTokens, fieldType, fieldOptions, lineText, subFields) {
  const baseType = (fieldType || 'string').endsWith('[]') ? fieldType.slice(0, -2) : fieldType;
  const isArrayType = (fieldType || '').endsWith('[]');
  const effectiveSubFields = getEffectiveSubFields(fieldType, subFields);

  // 配列型([] 付き)は、まず [ 値, 値, ... ] を分解してから、各要素を
  // baseType(=[]を外した型)としてcoerceValueTokensに再帰させる。
  // class_data型の配列(例: MyItem[])の場合、各要素が { フィールド名: 値, ... } になる。
  if (isArrayType) {
    if (valueTokens.length === 0 || valueTokens[0].type !== 'LBRACKET') {
      return { value: undefined, error: `配列は [値, 値, ...] の形式で指定してください` };
    }
    const inner = valueTokens.slice(1, -1);
    const items = splitByComma(inner);
    const result = [];
    for (const itemTokens of items) {
      const { value, error } = coerceValueTokens(itemTokens, baseType, fieldOptions, lineText, subFields);
      if (error) return { value: undefined, error };
      result.push(value);
    }
    return { value: result, error: null };
  }

  // vector2/3/4: アプリ内部では [x, y, ...] という配列で保持するが、DSL上は
  // class_data等と同じ { x: .., y: .. } の名前付きオブジェクトリテラルとして読み書きする
  // ("(0, 0)" のような位置だけの表記や "0,0" のような生の値は分かりにくいため)。
  if (baseType in VECTOR_SIZES) {
    const names = VECTOR_FIELD_NAMES[baseType];
    const vecFields = names.map((n) => ({ name: n, type: 'float' }));
    const { value: obj, error } = parseObjectLiteralTokens(valueTokens, vecFields, lineText);
    if (error) return { value: undefined, error };
    const missing = names.filter((n) => !(n in obj));
    if (missing.length > 0) {
      return { value: undefined, error: `${missing.join(', ')} が指定されていません（例: { ${names.map((n) => `${n}: 0`).join(', ')} }）` };
    }
    return { value: names.map((n) => obj[n]), error: null };
  }

  // class_data型・bit・color・bezier(いずれもネストした構造体): { フィールド名: 値, ... } の
  // 独自オブジェクトリテラルとして扱う(JSON.parseではなく、subFieldsのスキーマに従って
  // 1つ1つcoerceValueTokensを再帰適用する。フィールド名の予測変換もこれに合わせて
  // getCompletionsAt側で対応している)。
  if (Array.isArray(effectiveSubFields) && effectiveSubFields.length > 0) {
    return parseObjectLiteralTokens(valueTokens, effectiveSubFields, lineText);
  }

  // dictionary型のみ、キーが動的なため引き続きJSONリテラルとして扱う
  if (baseType === 'dictionary') {
    if (valueTokens.length === 0) return { value: undefined, error: '値が指定されていません' };
    const from = valueTokens[0].from;
    const to = valueTokens[valueTokens.length - 1].to;
    const raw = typeof lineText === 'string' ? lineText.slice(from, to) : valueTokens.map((t) => t.value).join('');
    try {
      return { value: JSON.parse(raw), error: null };
    } catch (e) {
      return { value: undefined, error: `dictionaryはJSON形式で指定してください（例: {"key":"value"}）` };
    }
  }

  if (valueTokens.length !== 1) {
    if (baseType === 'string') {
      return {
        value: undefined,
        error: '文字列は "" で囲んでください（例: text="Hello {name}"）。{ } , ( ) # = などの記号を含む文字列は、'
          + '必ず "" で囲む必要があります',
      };
    }
    return { value: undefined, error: `値の形式が不正です（"" で囲んでいない文字列に、区切り記号として扱われる文字（{ } , ( ) # = など）が含まれていませんか？）` };
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
  // enum / class_data_id は "TypeName.Property"（例: FadeID.In）の完全修飾形式で
  // 保存する規約になっている(GUI側のAutocompleteやC#生成側もこの形式を前提としている)。
  // DSL側では入力の手間を減らすため "In" のような短縮形も許容し、内部的には
  // 完全修飾形式へ正規化してから保存する。
  // ただし素の "string"型(自由入力のテキストフィールド)だけは、必ず ""
  // で囲むことを必須にする。バレワードのまま許してしまうと、値の中に
  // { } , ( ) # = のようなDSL予約記号が含まれた瞬間に複数トークンへ分裂して
  // しまい、原因の分かりにくい構文エラーになるため（enum等は元々候補が
  // 短い識別子中心なので、この問題が起きにくくバレワードを許容し続ける）。
  if (baseType === 'string' && tok.type !== 'STRING') {
    return {
      value: undefined,
      error: '文字列は "" で囲んでください（例: text="Hello {name}"）',
    };
  }
  const raw = tok.type === 'STRING' ? stripQuotes(tok.value) : tok.value;
  if (Array.isArray(fieldOptions) && fieldOptions.length > 0) {
    if (fieldOptions.includes(raw)) {
      return { value: raw, error: null };
    }
    const qualified = `${fieldType}.${raw}`;
    if (fieldOptions.includes(qualified)) {
      return { value: qualified, error: null };
    }
    return {
      value: raw,
      error: `候補にありません: ${raw}（候補: ${fieldOptions.slice(0, 5).join(', ')}${fieldOptions.length > 5 ? '...' : ''}）`,
      warningOnly: true,
    };
  }
  return { value: raw, error: null };
}

function splitByComma(tokens) {
  const groups = [];
  let current = [];
  let depth = 0;
  for (const t of tokens) {
    if (t.type === 'LPAREN' || t.type === 'LBRACKET' || t.type === 'LBRACE') depth += 1;
    if (t.type === 'RPAREN' || t.type === 'RBRACKET' || t.type === 'RBRACE') depth -= 1;
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

function serializeValue(value, fieldType, subFields) {
  const baseType = (fieldType || 'string').endsWith('[]') ? fieldType.slice(0, -2) : fieldType;
  const isArrayType = (fieldType || '').endsWith('[]');
  const effectiveSubFields = getEffectiveSubFields(fieldType, subFields);

  // vector2/3/4: 内部的には [x, y, ...] という配列で保持されているが、DSL上は
  // { x: .., y: .. } の名前付きオブジェクトリテラルとして出力する
  // ("(0, 0)"のような位置だけの表記や生の"0,0"は分かりにくいため)。
  if (baseType in VECTOR_SIZES && !isArrayType) {
    const names = VECTOR_FIELD_NAMES[baseType];
    const arr = Array.isArray(value) ? value : [];
    const parts = names.map((n, idx) => `${n}: ${arr[idx] ?? 0}`);
    return `{ ${parts.join(', ')} }`;
  }

  if (Array.isArray(effectiveSubFields) && effectiveSubFields.length > 0) {
    if (isArrayType) {
      const arr = Array.isArray(value) ? value : [];
      return `[${arr.map((v) => serializeValue(v, baseType, effectiveSubFields)).join(', ')}]`;
    }
    const obj = value && typeof value === 'object' ? value : {};
    const parts = effectiveSubFields.map((f) => `${f.name}: ${serializeValue(obj[f.name], f.type, f.subFields)}`);
    return `{ ${parts.join(', ')} }`;
  }

  if (isArrayType) {
    const arr = Array.isArray(value) ? value : [];
    return `[${arr.map((v) => serializeValue(v, baseType)).join(', ')}]`;
  }
  if (NUMERIC_TYPES.has(baseType) || FLOAT_TYPES.has(baseType)) {
    return String(value ?? 0);
  }
  if (baseType === 'bool') {
    return value ? 'true' : 'false';
  }
  // dictionary型のみ、キーが動的なため引き続きJSONリテラルとして出力する
  if (baseType === 'dictionary') {
    return JSON.stringify(value ?? {});
  }
  // string / enum / ID参照 / char 等
  const s = value === undefined || value === null ? '' : String(value);
  // fieldType(baseType)が素の "string"（自由入力のテキストフィールド）の場合は、
  // 中身に関わらず必ず "" で囲む。中に { } , ( ) 等のDSL予約記号が含まれていても
  // 安全に往復できるようにするため（例: talk_text="こんにちは{name}さん"）。
  if (baseType === 'string') {
    return `"${s.replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"`;
  }
  // enum / class_data_id / voice_ref / char など、通常は素のまま（無引用）で
  // 保存したい型については、DSLの予約記号（空白 " # = ( ) [ ] , { } :）を
  // 1つでも含む場合のみ "" で囲む。
  if (s === '' || /[\s"#=()[\]{},:]/.test(s)) {
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

      const { value, error, warningOnly } = coerceValueTokens(arg.valueTokens, field.type, field.options, node.raw, field.subFields);
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
      parts.push(`${field.name}=${serializeValue(field.value, type, fieldDef?.subFields)}`);
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

// class_data型(ネストした構造体)の { フィールド名: 値, ... } リテラルの中で、
// カーソル位置に応じてフィールド名 or 値の候補を返す(入れ子のclass_dataにも再帰対応)。
// valueTokens: このフィールドの値領域全体のトークン列（先頭が '{' のはず）。
// regionEnd: この値がまだ閉じられていない('}'が無い)場合に、どこまでを
//   「入力中の領域」とみなすかの文字位置(行末、または親の領域の終端)。
function completeObjectLiteral(line, valueTokens, cursorCh, subFields, regionEnd) {
  if (valueTokens.length === 0 || valueTokens[0].type !== 'LBRACE') {
    // '{' を打つ前の位置。ここでは候補を出さない({の入力を促す形)。
    return [];
  }

  // 対応する '}' を探す(depthを見て、ネストした{}を跨がないようにする)
  let depth = 0;
  let closeIdx = -1;
  for (let k = 0; k < valueTokens.length; k++) {
    if (valueTokens[k].type === 'LBRACE') depth += 1;
    if (valueTokens[k].type === 'RBRACE') {
      depth -= 1;
      if (depth === 0) { closeIdx = k; break; }
    }
  }
  const effectiveEnd = closeIdx >= 0 ? valueTokens[closeIdx].from : regionEnd;
  const inner = valueTokens.slice(1, closeIdx >= 0 ? closeIdx : valueTokens.length);

  // トップレベルのカンマで区切り、各エントリの [start, end) をカンマの位置を基準に求める。
  // (カンマの直後〜次エントリの手前は、どのエントリにも属さない「新しいキーの入力開始位置」になる)
  const entries = [];
  let current = [];
  let entryStart = null;
  let braceDepth = 0;
  for (const tok of inner) {
    if (entryStart === null) entryStart = tok.from;
    if (tok.type === 'LPAREN' || tok.type === 'LBRACKET' || tok.type === 'LBRACE') braceDepth += 1;
    if (tok.type === 'RPAREN' || tok.type === 'RBRACKET' || tok.type === 'RBRACE') braceDepth -= 1;
    if (tok.type === 'COMMA' && braceDepth === 0) {
      entries.push({ tokens: current, start: entryStart, end: tok.from });
      current = [];
      entryStart = null;
    } else {
      current.push(tok);
    }
  }
  if (current.length > 0) {
    entries.push({ tokens: current, start: entryStart, end: effectiveEnd });
  }

  const usedNames = new Set(entries.map((e) => e.tokens[0]?.value).filter(Boolean));

  const cursorEntry = entries.find((e) => cursorCh >= e.start && cursorCh <= e.end);

  if (!cursorEntry) {
    // カンマの直後や { の直後など、新しいキーを入力し始める位置 → フィールド名候補
    return subFields
      .filter((f) => !usedNames.has(f.name))
      .map((f) => ({ label: `${f.name}: `, type: 'field', detail: f.type }));
  }

  const cursorGroup = cursorEntry.tokens;
  const keyTok = cursorGroup[0];
  if (!keyTok) {
    return subFields
      .filter((f) => !usedNames.has(f.name))
      .map((f) => ({ label: `${f.name}: `, type: 'field', detail: f.type }));
  }
  const colonTok = cursorGroup[1];
  if (keyTok.type !== 'IDENT' || !colonTok || colonTok.type !== 'COLON' || cursorCh <= keyTok.to
    || (cursorCh > keyTok.to && cursorCh <= colonTok.from)) {
    // ':' より前(キー名を入力中) → フィールド名候補
    const prefix = cursorCh > keyTok.from ? line.slice(keyTok.from, cursorCh) : '';
    return subFields
      .filter((f) => f.name === keyTok.value || !usedNames.has(f.name))
      .filter((f) => f.name.toLowerCase().startsWith(prefix.toLowerCase()))
      .map((f) => ({ label: `${f.name}: `, type: 'field', detail: f.type }));
  }

  // ':' より後ろ(値を入力中) → そのサブフィールドの型に応じた値候補
  const subField = subFields.find((f) => f.name === keyTok.value);
  if (!subField) return [];
  const subValueTokens = cursorGroup.slice(2);

  const nestedSubFields = getEffectiveSubFields(subField.type, subField.subFields);
  if (Array.isArray(nestedSubFields) && nestedSubFields.length > 0) {
    if ((subField.type || '').endsWith('[]')) {
      return completeArrayOfObjectLiteral(line, subValueTokens, cursorCh, nestedSubFields, cursorEntry.end);
    }
    return completeObjectLiteral(line, subValueTokens, cursorCh, nestedSubFields, cursorEntry.end);
  }
  return completeScalarValue(line, subValueTokens, cursorCh, subField);
}

// class_data型の配列(例: MyItem[])向け: [ {...}, {...} ] の中で、カーソルが
// どの要素の中にいるかを判定し、その要素の { フィールド名: 値, ... } をcompleteObjectLiteralに委譲する。
function completeArrayOfObjectLiteral(line, valueTokens, cursorCh, subFields, regionEnd) {
  if (valueTokens.length === 0 || valueTokens[0].type !== 'LBRACKET') return [];

  let depth = 0;
  let closeIdx = -1;
  for (let k = 0; k < valueTokens.length; k++) {
    if (valueTokens[k].type === 'LBRACKET') depth += 1;
    if (valueTokens[k].type === 'RBRACKET') {
      depth -= 1;
      if (depth === 0) { closeIdx = k; break; }
    }
  }
  const effectiveEnd = closeIdx >= 0 ? valueTokens[closeIdx].from : regionEnd;
  const inner = valueTokens.slice(1, closeIdx >= 0 ? closeIdx : valueTokens.length);

  const entries = [];
  let current = [];
  let entryStart = null;
  let braceDepth = 0;
  for (const tok of inner) {
    if (entryStart === null) entryStart = tok.from;
    if (tok.type === 'LPAREN' || tok.type === 'LBRACKET' || tok.type === 'LBRACE') braceDepth += 1;
    if (tok.type === 'RPAREN' || tok.type === 'RBRACKET' || tok.type === 'RBRACE') braceDepth -= 1;
    if (tok.type === 'COMMA' && braceDepth === 0) {
      entries.push({ tokens: current, start: entryStart, end: tok.from });
      current = [];
      entryStart = null;
    } else {
      current.push(tok);
    }
  }
  if (current.length > 0) entries.push({ tokens: current, start: entryStart, end: effectiveEnd });

  const cursorEntry = entries.find((e) => cursorCh >= e.start && cursorCh <= e.end);
  if (!cursorEntry) return []; // 新しい要素の先頭( "{" をまだ打っていない) → 候補なし
  return completeObjectLiteral(line, cursorEntry.tokens, cursorCh, subFields, cursorEntry.end);
}

// enum / class_data_id 等、"TypeName.Property" の完全修飾形式で保存するフィールドの
// 値予測変換・boolの true/false 候補などをまとめて処理する。
function completeScalarValue(line, valueTokens, cursorCh, field) {
  const lastTok = valueTokens[valueTokens.length - 1];
  const typedPrefix = lastTok && cursorCh > lastTok.from ? line.slice(lastTok.from, cursorCh) : '';
  if (field.options?.length) {
    // field.options は既に "TypeName.Property" の完全修飾形式で渡ってくる
    // (generate_role_form_schema参照)。1つのフィールドが持つ候補は全部同じ
    // "TypeName." を共有しているため、マッチ判定に完全修飾文字列(TypeName込み)を
    // 使ってしまうと、例えば "I" 一文字だけで "FadeTypeID" 側の "I" にまで
    // ヒットしてしまい、絞り込みにならず全候補が出てしまう。
    // そのため判定は必ずドットより後ろの名前(bare)だけに対して行う。
    //
    // 表示上も "TypeName." の部分(型のqualifier)は見せず、ドットより後ろの
    // 名前だけを候補として出す。実際に選んで確定したときには、これまで通り
    // 完全修飾形式("TypeName.Property")を挿入する
    // ("label" は表示専用、"insertText" が実際に挿入される値)。
    const bareOf = (o) => (o.includes('.') ? o.slice(o.indexOf('.') + 1) : o);
    const toItem = (o) => ({ label: bareOf(o), insertText: o, type: 'value' });

    const prefixLower = typedPrefix.toLowerCase();
    if (!prefixLower) {
      return field.options.map(toItem);
    }
    const startsWithMatches = [];
    const containsMatches = [];
    field.options.forEach((o) => {
      const bareLower = bareOf(o).toLowerCase();
      if (bareLower.startsWith(prefixLower)) {
        startsWithMatches.push(o);
      } else if (bareLower.includes(prefixLower)) {
        containsMatches.push(o);
      }
    });
    return [...startsWithMatches, ...containsMatches].map(toItem);
  }
  if (field.type === 'bool') {
    return ['true', 'false']
      .filter((o) => o.startsWith(typedPrefix))
      .map((o) => ({ label: o, type: 'value' }));
  }
  return [];
}

// Role名を補完で選んだときに実際に挿入するテキストを組み立てる。
// デフォルト値が保存されているフィールド(field.default が設定されている)があれば、
// "RoleName field1=default1 field2=default2 ..." のように、Roleを追加したその瞬間に
// デフォルト値ごと書き込む(GUI側でRoleを新規追加した際に初期値が自動で入るのと同じ体験を
// テキストDSL側でも再現する)。デフォルトが設定されていないフィールドは、ユーザーが
// 自分で入力できるようそのままにしておく(勝手に埋めない)。
function buildRoleInsertText(roleName, schema) {
  if (!schema || !Array.isArray(schema.fields)) return roleName;
  const parts = [];
  for (const field of schema.fields) {
    if (field.default === undefined || field.default === null) continue;
    const subFields = getEffectiveSubFields(field.type, field.subFields);
    parts.push(`${field.name}=${serializeValue(field.default, field.type, subFields)}`);
  }
  if (parts.length === 0) return roleName;
  return `${roleName} ${parts.join(' ')}`;
}

export function getCompletionsAt(text, cursorLine, cursorCh, roleNames, roleSchemas) {
  const lines = text.split('\n');
  const line = lines[cursorLine] ?? '';
  const tokens = tokenizeLine(line).filter((t) => t.type !== 'COMMENT');

  if (tokens.length === 0) {
    return roleNames.map((n) => ({ label: n, type: 'role', insertText: buildRoleInsertText(n, roleSchemas[n]) }));
  }

  // 最初のトークン（Role名）を編集中かどうか
  const first = tokens[0];
  if (cursorCh <= first.to) {
    if (first.type !== 'IDENT') return [];
    const prefix = line.slice(first.from, cursorCh);
    return roleNames
      .filter((n) => n.toLowerCase().startsWith(prefix.toLowerCase()))
      .map((n) => ({ label: n, type: 'role', insertText: buildRoleInsertText(n, roleSchemas[n]) }));
  }

  const roleName = first.value;
  const schema = roleSchemas[roleName];
  if (!schema) return [];

  // "fieldName=値" の値部分にカーソルがあれば値候補を返す。
  // 値領域は collectValueTokens と同じ括弧マッチングで求める(閉じている場合は
  // 対応する閉じ括弧まで、閉じていない場合は行末までを「入力中の値」とみなす)。
  for (let i = 1; i < tokens.length; i++) {
    const t = tokens[i];
    if (t.type !== 'EQUALS') continue;
    const fieldName = tokens[i - 1]?.value;
    const field = schema.fields.find((f) => f.name === fieldName);
    if (!field) continue;

    const { valueTokens, error: spanError } = collectValueTokens(tokens, i + 1);
    const isUnclosed = !!spanError && spanError.includes('閉じられていません');
    const regionStart = t.to;
    const regionEnd = isUnclosed
      ? line.length
      : (valueTokens.length > 0 ? valueTokens[valueTokens.length - 1].to : regionStart);
    if (cursorCh < regionStart || cursorCh > regionEnd) continue;

    // class_data型・bit・color・bezier・vector2/3/4(いずれもネストした構造体):
    // { フィールド名: 値, ... } の中を予測変換する
    const fieldSubFields = getEffectiveSubFields(field.type, field.subFields);
    if (Array.isArray(fieldSubFields) && fieldSubFields.length > 0) {
      if ((field.type || '').endsWith('[]')) {
        return completeArrayOfObjectLiteral(line, valueTokens, cursorCh, fieldSubFields, regionEnd);
      }
      return completeObjectLiteral(line, valueTokens, cursorCh, fieldSubFields, regionEnd);
    }

    return completeScalarValue(line, valueTokens, cursorCh, field);
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
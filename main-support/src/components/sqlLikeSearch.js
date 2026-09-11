// sqlLikeSearch.js
//
// ClassDataIdDetailGrid / ClassDataMatrixIdDetailGrid で共通利用する、
// SQLのWHERE句に近い簡易DSLのトークナイザ・パーサー・評価器。
//
// 対応構文:
//   識別子 演算子 値   例: hp > 100 / name = "Hero" / name LIKE "%Hero%"
//   条件 AND 条件 / 条件 OR 条件 / NOT 条件 / (条件)
//   演算子: = != > >= < <= LIKE
//
// 仕様(要件定義で確定した内容):
//   - 文字列の "=" 比較・LIKE は大文字小文字を区別しない
//   - LIKEのワイルドカードは "%"（0文字以上の任意文字列）のみサポート（"_"は非対応）
//   - AND/ORは混在・括弧によるネストに対応
//
// 評価は evaluate(ast, context) で行う。context はプレーンオブジェクト
// { 識別子: 値, ... }。値は string / number / boolean を想定。
// 大文字小文字を区別しない識別子引き当てが必要な場合は、呼び出し側で
// context のキーを正規化しておくこと（本モジュールは識別子は大文字小文字を
// 区別してcontextを引く）。

// ---------------------------------------------------------------------------
// 1. トークナイザ
// ---------------------------------------------------------------------------

const KEYWOROperators = ['AND', 'OR', 'NOT', 'LIKE'];

function tokenize(text) {
  const tokens = [];
  let i = 0;
  const n = text.length;

  const isIdentStart = (c) => /[A-Za-z_]/.test(c);
  const isIdentPart = (c) => /[A-Za-z0-9_.]/.test(c);

  while (i < n) {
    const c = text[i];

    if (/\s/.test(c)) { i++; continue; }

    if (c === '(') { tokens.push({ type: 'LPAREN', value: '(', from: i, to: i + 1 }); i++; continue; }
    if (c === ')') { tokens.push({ type: 'RPAREN', value: ')', from: i, to: i + 1 }); i++; continue; }

    if (c === '"' || c === "'") {
      const quote = c;
      let j = i + 1;
      let value = '';
      while (j < n && text[j] !== quote) {
        value += text[j];
        j++;
      }
      tokens.push({ type: 'STRING', value, from: i, to: Math.min(j + 1, n) });
      i = j + 1;
      continue;
    }

    if (/[0-9]/.test(c) || (c === '-' && /[0-9]/.test(text[i + 1] || ''))) {
      let j = i + 1;
      while (j < n && /[0-9.]/.test(text[j])) j++;
      tokens.push({ type: 'NUMBER', value: parseFloat(text.slice(i, j)), from: i, to: j });
      i = j;
      continue;
    }

    if (c === '=' ) { tokens.push({ type: 'OP', value: '=', from: i, to: i + 1 }); i++; continue; }
    if (c === '!' && text[i + 1] === '=') { tokens.push({ type: 'OP', value: '!=', from: i, to: i + 2 }); i += 2; continue; }
    if (c === '>' && text[i + 1] === '=') { tokens.push({ type: 'OP', value: '>=', from: i, to: i + 2 }); i += 2; continue; }
    if (c === '<' && text[i + 1] === '=') { tokens.push({ type: 'OP', value: '<=', from: i, to: i + 2 }); i += 2; continue; }
    if (c === '>') { tokens.push({ type: 'OP', value: '>', from: i, to: i + 1 }); i++; continue; }
    if (c === '<') { tokens.push({ type: 'OP', value: '<', from: i, to: i + 1 }); i++; continue; }

    if (isIdentStart(c)) {
      let j = i + 1;
      while (j < n && isIdentPart(text[j])) j++;
      const raw = text.slice(i, j);
      const upper = raw.toUpperCase();
      if (KEYWOROperators.includes(upper)) {
        tokens.push({ type: upper, value: raw, from: i, to: j });
      } else {
        tokens.push({ type: 'IDENT', value: raw, from: i, to: j });
      }
      i = j;
      continue;
    }

    // 未知の文字は読み飛ばす（構文エラーとしてパーサー側で検知させる）
    tokens.push({ type: 'UNKNOWN', value: c, from: i, to: i + 1 });
    i++;
  }

  tokens.push({ type: 'EOF', value: null, from: n, to: n });
  return tokens;
}

// ---------------------------------------------------------------------------
// 2. パーサー（再帰下降。優先順位: OR < AND < NOT < 比較 < 括弧）
// ---------------------------------------------------------------------------

class ParseError extends Error {}

function parse(text) {
  const tokens = tokenize(text);
  let pos = 0;

  const peek = () => tokens[pos];
  const next = () => tokens[pos++];
  const expect = (type) => {
    if (peek().type !== type) {
      throw new ParseError(`"${type}" が期待されましたが "${peek().value ?? 'EOF'}" が見つかりました`);
    }
    return next();
  };

  function parseOr() {
    let left = parseAnd();
    while (peek().type === 'OR') {
      next();
      const right = parseAnd();
      left = { kind: 'or', left, right };
    }
    return left;
  }

  function parseAnd() {
    let left = parseNot();
    while (peek().type === 'AND') {
      next();
      const right = parseNot();
      left = { kind: 'and', left, right };
    }
    return left;
  }

  function parseNot() {
    if (peek().type === 'NOT') {
      next();
      const operand = parseNot();
      return { kind: 'not', operand };
    }
    return parseComparison();
  }

  function parseComparison() {
    if (peek().type === 'LPAREN') {
      next();
      const inner = parseOr();
      expect('RPAREN');
      return inner;
    }
    const identTok = expect('IDENT');
    const opTok = next();
    if (!['OP', 'LIKE'].includes(opTok.type)) {
      throw new ParseError(`演算子が期待されましたが "${opTok.value ?? 'EOF'}" が見つかりました`);
    }
    const operator = opTok.type === 'LIKE' ? 'LIKE' : opTok.value;
    const valueTok = next();
    if (!['STRING', 'NUMBER', 'IDENT'].includes(valueTok.type)) {
      throw new ParseError(`値が期待されましたが "${valueTok.value ?? 'EOF'}" が見つかりました`);
    }
    let value;
    if (valueTok.type === 'NUMBER') value = { type: 'number', raw: valueTok.value };
    else value = { type: 'string', raw: String(valueTok.value) };

    return { kind: 'cmp', field: identTok.value, operator, value };
  }

  const ast = parseOr();
  if (peek().type !== 'EOF') {
    throw new ParseError(`余分なトークン "${peek().value}" があります`);
  }
  return ast;
}

// ---------------------------------------------------------------------------
// 3. 評価器
// ---------------------------------------------------------------------------

function likeToRegExp(pattern) {
  // "%" のみをワイルドカードとしてサポートする（"_" は非対応、リテラルとして扱う）
  const escaped = pattern.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const withWildcard = escaped.replace(/%/g, '.*');
  return new RegExp(`^${withWildcard}$`, 'i');
}

function compareValues(actual, cmpValue) {
  if (actual === undefined || actual === null) return { asNumber: null, asString: '' };
  if (cmpValue.type === 'number') {
    const n = typeof actual === 'number' ? actual : parseFloat(actual);
    return { asNumber: Number.isNaN(n) ? null : n, asString: String(actual) };
  }
  return { asNumber: typeof actual === 'number' ? actual : null, asString: String(actual) };
}

function evalComparison(node, context) {
  const actual = context[node.field];
  const { asNumber, asString } = compareValues(actual, node.value);

  if (node.operator === 'LIKE') {
    const re = likeToRegExp(node.value.raw);
    return re.test(asString);
  }

  if (node.value.type === 'number') {
    if (asNumber === null) return false;
    const target = node.value.raw;
    switch (node.operator) {
      case '=': return asNumber === target;
      case '!=': return asNumber !== target;
      case '>': return asNumber > target;
      case '>=': return asNumber >= target;
      case '<': return asNumber < target;
      case '<=': return asNumber <= target;
      default: return false;
    }
  }

  // 文字列比較（大文字小文字を区別しない）
  const a = asString.toLowerCase();
  const b = node.value.raw.toLowerCase();
  switch (node.operator) {
    case '=': return a === b;
    case '!=': return a !== b;
    case '>': return a > b;
    case '>=': return a >= b;
    case '<': return a < b;
    case '<=': return a <= b;
    default: return false;
  }
}

function evaluate(ast, context) {
  switch (ast.kind) {
    case 'and': return evaluate(ast.left, context) && evaluate(ast.right, context);
    case 'or': return evaluate(ast.left, context) || evaluate(ast.right, context);
    case 'not': return !evaluate(ast.operand, context);
    case 'cmp': return evalComparison(ast, context);
    default: return false;
  }
}

/**
 * クエリ文字列をパースして評価関数を返す。
 * 空文字列の場合は常にtrueを返す関数（絞り込みなし）を返す。
 * 構文エラーの場合は { error } を返す。
 */
function compileQuery(text) {
  const trimmed = (text || '').trim();
  if (!trimmed) {
    return { matches: () => true, error: null };
  }
  try {
    const ast = parse(trimmed);
    return { matches: (context) => evaluate(ast, context), error: null };
  } catch (e) {
    return { matches: () => true, error: e.message || String(e) };
  }
}

// ---------------------------------------------------------------------------
// 4. オートコンプリート候補計算
// ---------------------------------------------------------------------------

/**
 * カーソル位置までのテキストを軽く解析し、次に入力されうる候補一覧を返す。
 * fieldNames: 候補として出すカラム名/識別子の配列（例: ['row','col','hp',...]）
 * valuesByField: { fieldName: [候補値, ...] } 値の予測変換用（Enum/参照型など）
 */
function getSuggestions(text, cursorPos, { fieldNames = [], valuesByField = {} } = {}) {
  const before = text.slice(0, cursorPos);
  const tokens = tokenize(before);
  // EOFトークンを除いた最後のトークンで状態判定する
  const relevant = tokens.filter((t) => t.type !== 'EOF');
  const last = relevant[relevant.length - 1];

  // 現在入力中の単語（識別子や数値の途中）かどうかを判定し、
  // 候補をその単語で絞り込むためのprefixとして使う。
  const isTypingIdent = last && last.type === 'IDENT' && last.to === cursorPos;
  const isTypingString = last && last.type === 'STRING' && last.to === cursorPos;
  const prefix = isTypingIdent ? last.value : '';

  const prevMeaningful = isTypingIdent ? relevant[relevant.length - 2] : last;

  const wantsFieldOrKeyword = (
    !prevMeaningful ||
    ['AND', 'OR', 'NOT', 'LPAREN'].includes(prevMeaningful.type)
  );
  const wantsOperator = prevMeaningful && prevMeaningful.type === 'IDENT' && !isTypingIdent;
  const wantsValue = prevMeaningful && (prevMeaningful.type === 'OP' || prevMeaningful.type === 'LIKE');
  const wantsConjunctionOrClose = prevMeaningful && (
    prevMeaningful.type === 'STRING' || prevMeaningful.type === 'NUMBER' || prevMeaningful.type === 'RPAREN'
    || (prevMeaningful.type === 'IDENT' && !isTypingIdent)
  );

  const suggestions = [];

  if (wantsFieldOrKeyword || isTypingIdent) {
    fieldNames.forEach((f) => {
      if (!prefix || f.toLowerCase().startsWith(prefix.toLowerCase())) {
        suggestions.push({ label: f, kind: 'field' });
      }
    });
    if (!prefix || 'NOT'.startsWith(prefix.toUpperCase())) suggestions.push({ label: 'NOT', kind: 'keyword' });
    suggestions.push({ label: '(', kind: 'paren' });
  } else if (wantsOperator) {
    ['=', '!=', '>', '>=', '<', '<=', 'LIKE'].forEach((op) => suggestions.push({ label: op, kind: 'operator' }));
  } else if (wantsValue) {
    const fieldTok = [...relevant].reverse().find((t) => t.type === 'IDENT');
    const candidates = (fieldTok && valuesByField[fieldTok.value]) || [];
    candidates.forEach((v) => suggestions.push({ label: `"${v}"`, kind: 'value' }));
  } else if (wantsConjunctionOrClose && !isTypingString) {
    suggestions.push({ label: 'AND', kind: 'keyword' });
    suggestions.push({ label: 'OR', kind: 'keyword' });
    suggestions.push({ label: ')', kind: 'paren' });
  }

  return suggestions;
}

export { tokenize, parse, evaluate, compileQuery, getSuggestions, ParseError };

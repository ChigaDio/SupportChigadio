import React, { useMemo } from 'react';
import CodeMirror from '@uiw/react-codemirror';
import { StreamLanguage } from '@codemirror/language';
import { linter as createLinter } from '@codemirror/lint';
import { autocompletion } from '@codemirror/autocomplete';
import { EditorView, keymap } from '@codemirror/view';
import { indentWithTab } from '@codemirror/commands';
import {
  tokenizeLine, lintDocument, getCompletionsAt,
} from '../scenario/scenarioTransactionDsl';

// Transactionのロール入力を「1行1コマンド」のテキストDSLとして編集する
// CodeMirror 6ベースのコードエディタ。
// - シンタックスハイライト: scenarioTransactionDsl.js の tokenizeLine を
//   そのまま流用（ハイライトとコンパイルで別々の文法を持たない）
// - リンター: 未知のRole/フィールド、型不一致等をリアルタイムに波線表示
// - オートコンプリート: Role名 → フィールド名 → 値（enum等の場合は候補一覧）
//   の順にカスケードで補完
// - 自動インデント/コメント/Tabキー: CodeMirmirrorの標準機能を利用

export function buildDslLanguage() {
  return StreamLanguage.define({
    token(stream) {
      if (stream.sol()) {
        stream._dslTokens = tokenizeLine(stream.string);
        stream._dslIndex = 0;
      }
      const tokens = stream._dslTokens || [];
      const idx = stream._dslIndex || 0;
      if (idx >= tokens.length) {
        stream.skipToEnd();
        return null;
      }
      const tok = tokens[idx];
      if (stream.pos < tok.from) stream.pos = tok.from;
      stream.pos = tok.to;
      stream._dslIndex = idx + 1;

      const isRoleName = idx === 0;
      switch (tok.type) {
        case 'COMMENT': return 'comment';
        case 'STRING': return 'string';
        case 'NUMBER': return 'number';
        case 'EQUALS': return 'operator';
        case 'LPAREN': case 'RPAREN': case 'LBRACKET': case 'RBRACKET':
        case 'LBRACE': case 'RBRACE': case 'COMMA': case 'COLON':
          return 'punctuation';
        case 'IDENT':
          if (isRoleName) return 'keyword';
          if (tok.value === 'true' || tok.value === 'false') return 'atom';
          return 'variableName';
        default:
          return null;
      }
    },
  });
}

export function buildLintSource(roleSchemas) {
  return (view) => {
    const text = view.state.doc.toString();
    const issues = lintDocument(text, roleSchemas || {});
    const diagnostics = [];
    for (const issue of issues) {
      const line = view.state.doc.line(Math.min(issue.line + 1, view.state.doc.lines));
      const from = Math.min(line.from + issue.from, line.to);
      const to = Math.min(line.from + issue.to, line.to);
      diagnostics.push({
        from: Math.max(from, line.from),
        to: Math.max(to, from),
        severity: issue.severity === 'warning' ? 'warning' : 'error',
        message: issue.message,
      });
    }
    return diagnostics;
  };
}

export function buildLinter(roleSchemas) {
  // delay: ドキュメント変更のたびに即リント(=毎キー入力でcompileDocumentが走る)すると
  // 特に「全体編集(全Sub一括)」のような長いドキュメントで入力がもたつくため、
  // 入力が少し落ち着いてからリントする(デフォルトの750msのままだと重い環境では
  // まだ長く感じるため、体感速度とのバランスで400msに短縮)。
  return createLinter(buildLintSource(roleSchemas), { delay: 400 });
}

export function buildCompletionSource(roleNames, roleSchemas) {
  return (context) => {
    const line = context.state.doc.lineAt(context.pos);
    const cursorCh = context.pos - line.from;
    const cursorLine = line.number - 1;
    const fullText = context.state.doc.toString();

    const items = getCompletionsAt(fullText, cursorLine, cursorCh, roleNames, roleSchemas || {});
    if (items.length === 0) return null;

    // 補完のトリガー開始位置（現在編集中の単語の先頭）を求める。
    // enum/class_data_id は "GuestCharacterID.GuestCharacter_01" のように
    // ドット(.)を含む完全修飾形で保存するため、ドットも「単語の一部」に含めて
    // 判定する。ここでドットを含めていないと、"GuestCharacterID.Guest" まで
    // 打った状態で補完したときに「編集中の単語」が "." より後ろの "Guest" だけだと
    // 誤判定され、"GuestCharacterID." が置換されずに残ったまま完全修飾形の候補が
    // 継ぎ足されて "GuestCharacterID.GuestCharacterID.GuestCharacter_01" のように
    // 二重挿入されてしまう(カンマ区切りの2つ目以降の値を補完する場合も同様)。
    const beforeCursor = line.text.slice(0, cursorCh);
    const wordMatch = beforeCursor.match(/[A-Za-z0-9_.]*$/);
    const from = line.from + cursorCh - (wordMatch ? wordMatch[0].length : 0);

    return {
      from,
      // to を明示しておく（context.pos = 呼び出し時点のカーソル位置）。
      // 未指定のままだと、CodeMirror内部の「入力継続中は前回の結果を使い回す」
      // 最適化(validForによる再フィルタ)が、あいまい一致(部分一致)の候補を
      // 選んだときに置換範囲がずれ、「Character」+「CharacterID.Test」のように
      // 元の入力が消えずに二重挿入される不具合の原因になっていた。
      to: context.pos,
      options: items.map((it) => ({
        label: it.label,
        type: it.type === 'role' ? 'class' : it.type === 'field' ? 'property' : 'text',
        detail: it.detail,
        // apply を明示し、候補選択時に挿入されるテキストを label と完全に一致させる
        // (from/toで指定した範囲を、常にこのテキストで置き換える)。
        apply: it.label,
      })),
      // validForは指定しない: 1文字打つごとにこの関数を再実行させ、常に最新の
      // from/to・候補一覧を計算し直す(上記の二重挿入バグの根本対策)。
      // このDSLの補完計算は1行だけを見て行う軽い処理なので、キー入力毎に
      // 再計算しても体感できるほどのコストにはならない。
    };
  };
}

// CodeMirrorに渡すbasicSetupは、コンポーネントのレンダーごとに新しいオブジェクト
// リテラルを作らないよう、モジュールスコープの定数として1つだけ用意しておく
// (毎回新しい参照を渡すと、ラッパー側で不要な再初期化が走りやすくなるため)。
// autocompletion: false にしているのは、下のextensionsで独自の
// autocompletion({ override: [...] }) を明示的に登録しているため。
// basicSetup側のデフォルト補完(汎用の単語補完)も同時に有効なままだと、
// 2つの補完ソースが競合し、候補選択時に意図しないテキストが挿入される
// 原因になっていた。
const BASIC_SETUP = {
  lineNumbers: true,
  foldGutter: false,
  highlightActiveLine: true,
  autocompletion: false,
  tabSize: 2,
};

function ScenarioTransactionCodeEditor({ value, onChange, roleNames, roleSchemas, height = '420px' }) {
  const extensions = useMemo(() => [
    buildDslLanguage(),
    buildLinter(roleSchemas),
    autocompletion({ override: [buildCompletionSource(roleNames || [], roleSchemas || {})] }),
    keymap.of([indentWithTab]),
    EditorView.lineWrapping,
  ], [roleNames, roleSchemas]);

  return (
    <CodeMirror
      value={value}
      height={height}
      extensions={extensions}
      onChange={onChange}
      basicSetup={BASIC_SETUP}
    />
  );
}

export default ScenarioTransactionCodeEditor;
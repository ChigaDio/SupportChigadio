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
  return createLinter(buildLintSource(roleSchemas));
}

export function buildCompletionSource(roleNames, roleSchemas) {
  return (context) => {
    const line = context.state.doc.lineAt(context.pos);
    const cursorCh = context.pos - line.from;
    const cursorLine = line.number - 1;
    const fullText = context.state.doc.toString();

    const items = getCompletionsAt(fullText, cursorLine, cursorCh, roleNames, roleSchemas || {});
    if (items.length === 0) return null;

    // 補完のトリガー開始位置（現在編集中の単語の先頭）を求める
    const beforeCursor = line.text.slice(0, cursorCh);
    const wordMatch = beforeCursor.match(/[A-Za-z0-9_]*$/);
    const from = line.from + cursorCh - (wordMatch ? wordMatch[0].length : 0);

    return {
      from,
      options: items.map((it) => ({
        label: it.label,
        type: it.type === 'role' ? 'class' : it.type === 'field' ? 'property' : 'text',
        detail: it.detail,
      })),
      validFor: /^[A-Za-z0-9_]*$/,
    };
  };
}

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
      onChange={(v) => onChange(v)}
      basicSetup={{
        lineNumbers: true,
        foldGutter: false,
        highlightActiveLine: true,
        autocompletion: true,
        tabSize: 2,
      }}
    />
  );
}

export default ScenarioTransactionCodeEditor;

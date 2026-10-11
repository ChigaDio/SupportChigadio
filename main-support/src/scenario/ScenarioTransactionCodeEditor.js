import React, { useMemo, useEffect, useRef, useState } from 'react';
import {
  Box, Button, Divider, ListItemText, Menu, MenuItem, Tooltip, Typography,
} from '@mui/material';
import BuildIcon from '@mui/icons-material/Build';
import CodeMirror from '@uiw/react-codemirror';
import { StreamLanguage } from '@codemirror/language';
import { linter as createLinter } from '@codemirror/lint';
import { autocompletion } from '@codemirror/autocomplete';
import { EditorView, keymap } from '@codemirror/view';
import { indentWithTab } from '@codemirror/commands';
import {
  tokenizeLine, lintDocument, getCompletionsAt,
  computeNextGroupHeader, computeNextSubgroupHeader,
  isSubGroupSettingLine, renumberDuplicateNodeIds,
} from '../scenario/scenarioTransactionDsl';
import {
  findSiblingSections, planIndexAdjustInDsl, collectIndexFieldsInDsl,
} from '../scenario/scenarioIndexTools';
import ScenarioIndexToolsDialog from '../scenario/ScenarioIndexToolsDialog';

// Transactionのロール入力を「1行1コマンド」のテキストDSLとして編集する
// CodeMirror 6ベースのコードエディタ。
// - シンタックスハイライト: scenarioTransactionDsl.js の tokenizeLine を
//   そのまま流用（ハイライトとコンパイルで別々の文法を持たない）
// - リンター: 未知のRole/フィールド、型不一致等をリアルタイムに波線表示
// - オートコンプリート: Role名 → フィールド名 → 値（enum等の場合は候補一覧）
//   の順にカスケードで補完。Role名を選ぶと、デフォルト値が設定済みのフィールドは
//   自動でその値ごと挿入される。
// - 自動インデント/コメント/Tabキー: CodeMirrorの標準機能を利用
// - Ctrl/Cmd+Alt+G: 新しいグループ(トップレベルの見出し)を、直前のグループの
//   IDをインクリメントして挿入
// - Ctrl/Cmd+Alt+H: 新しいサブグループ(カーソルが今いるグループの中の見出し)を、
//   直前のサブグループのIDをインクリメントして挿入
// - 「Utils」メニュー(エディタ右上のボタン): 上記ショートカットと同じ操作をメニューから選べる。
//   ・新しいグループ/サブグループの見出しを挿入(Ctrl/Cmd+Alt+G / H と同じ)
//   ・重複しているIDを振り直す(コピー&ペースト直後など)
//   ・インデックス(text_list_index / voice_ref)の一括調整: カーソルのあるサブグループ以降を
//     「+N/-Nずらす」「連番にする」(適用前にプレビュー)。Ctrl+Z で元に戻せる。
// - サブグループ設定行('#@ is_wait_key=false ...'): 見出しの直下に書くコメント形式の1行。
//   ハイライト・リンター・補完の対象。ショートカットで新しいグループ/サブグループを挿入する
//   ときは、この設定行もデフォルト値(手動デフォルト→自動デフォルト)で一緒に挿入する。

export function buildDslLanguage() {
  return StreamLanguage.define({
    token(stream) {
      if (stream.sol()) {
        // '#@ ...' のサブグループ設定行は、同じ桁数の疑似Role呼び出し('@@ ...')として
        // トークン化し、コメントではなく「フィールド=値」としてハイライトする。
        const raw = stream.string;
        stream._dslTokens = tokenizeLine(isSubGroupSettingLine(raw) ? `@@${raw.slice(2)}` : raw);
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

export function buildLintSource(roleSchemas, classDataSchemas, settingSchema = null) {
  return (view) => {
    const text = view.state.doc.toString();
    const issues = lintDocument(text, roleSchemas || {}, classDataSchemas || {}, settingSchema);
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

export function buildLinter(roleSchemas, classDataSchemas, settingSchema = null) {
  // delay: ドキュメント変更のたびに即リント(=毎キー入力でcompileDocumentが走る)すると
  // 特に「全体編集(全Sub一括)」のような長いドキュメントで入力がもたつくため、
  // 入力が少し落ち着いてからリントする(デフォルトの750msのままだと重い環境では
  // まだ長く感じるため、体感速度とのバランスで400msに短縮)。
  return createLinter(buildLintSource(roleSchemas, classDataSchemas, settingSchema), { delay: 400 });
}

// 見出し行 ('# ==== SUB:1 NODE:1/2 ... ====')
const HEADER_LINE_RE = /^#\s*====\s*SUB:\S+\s+NODE:\S+.*?====\s*$/;

export function buildCompletionSource(roleNames, roleSchemas, classDataSchemas, settingSchema = null, settingDefaultLine = '') {
  return (context) => {
    const line = context.state.doc.lineAt(context.pos);
    const cursorCh = context.pos - line.from;
    const cursorLine = line.number - 1;
    const fullText = context.state.doc.toString();

    // サブグループ設定行のひな形('#@ is_wait_key=false ...' = デフォルト値入りの1行)の候補:
    //  ・行頭で '#' / '#@' と打ったとき
    //  ・見出しの直下の空行で候補を出したとき(Role名の候補と一緒に。まだ設定行が無いセクションのみ)
    const beforeCursorRaw = line.text.slice(0, cursorCh);
    if (settingSchema && settingDefaultLine && /^#@?$/.test(beforeCursorRaw)) {
      return {
        from: line.from,
        to: context.pos,
        filter: false,
        options: [{
          label: '#@ サブグループ設定',
          detail: settingDefaultLine,
          type: 'keyword',
          boost: 99,
          apply: settingDefaultLine,
        }],
      };
    }

    const items = getCompletionsAt(fullText, cursorLine, cursorCh, roleNames, roleSchemas || {}, classDataSchemas || {}, settingSchema);
    let settingTemplate = null;
    if (settingSchema && settingDefaultLine && line.text.trim() === '' && cursorLine > 0) {
      const prev = context.state.doc.line(line.number - 1).text;
      if (HEADER_LINE_RE.test(prev)) {
        settingTemplate = {
          label: '#@ サブグループ設定',
          detail: settingDefaultLine,
          type: 'keyword',
          boost: 99,
          apply: settingDefaultLine,
        };
      }
    }
    if (items.length === 0 && !settingTemplate) return null;

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
      options: [
        ...(settingTemplate ? [settingTemplate] : []),
        ...items.map((it) => ({
          label: it.label,
          type: it.type === 'role' ? 'class' : it.type === 'field' ? 'property' : 'text',
          detail: it.detail,
          // apply を明示し、候補選択時に挿入されるテキストを完全に制御する
          // (from/toで指定した範囲を、常にこのテキストで置き換える)。
          // Role名の場合は it.insertText に「デフォルト値付きの呼び出し」が
          // 入っていることがあるので、それを優先する。
          apply: it.insertText || it.label,
        })),
      ],
      // validForは指定しない: 1文字打つごとにこの関数を再実行させ、常に最新の
      // from/to・候補一覧を計算し直す(上記の二重挿入バグの根本対策)。
      // このDSLの補完計算は1行だけを見て行う軽い処理なので、キー入力毎に
      // 再計算しても体感できるほどのコストにはならない。
    };
  };
}

// ── ショートカットキー: 新しいグループ/サブグループを、直前の兄弟から
// IDをインクリメントして挿入する ──
// 「見出しをまた1から手で書く」手間を減らすためのもの。あくまで見出し行を
// カーソル位置に挿し込むだけで、実際にノードとして生成されるのは
// (Web版の場合)全体編集/Sub編集ダイアログの「適用」時、DSLのコンパイルを
// 経てから。既存の「見出しから新規グループを作る」仕組み・
// 「新しいグループの追加を許可する」設定はそのまま活きる。
// getSettingLine: サブグループ設定行のデフォルト('#@ is_wait_key=false ...')を返す関数。
// 見出しと一緒に、デフォルト値の設定行も挿入する(設定が未取得/空なら見出しだけ)。
const buildHeaderInsertText = (subId, pathKey, getSettingLine) => {
  const settingLine = getSettingLine ? getSettingLine() : '';
  return `# ==== SUB:${subId} NODE:${pathKey} ====\n${settingLine ? `${settingLine}\n` : ''}\n`;
};

const makeInsertNewGroupCommand = (getSettingLine) => (view) => {
  const doc = view.state.doc;
  const text = doc.toString();
  const cursorLine = doc.lineAt(view.state.selection.main.head).number - 1; // 0始まり
  const { subId, newPathKey } = computeNextGroupHeader(text, cursorLine);

  const insertLine = doc.lineAt(view.state.selection.main.head);
  const insertText = buildHeaderInsertText(subId, newPathKey, getSettingLine);
  view.dispatch({
    changes: { from: insertLine.from, insert: insertText },
    selection: { anchor: insertLine.from + insertText.length },
    scrollIntoView: true,
  });
  return true;
};

const makeInsertNewSubgroupCommand = (getSettingLine) => (view) => {
  const doc = view.state.doc;
  const text = doc.toString();
  const cursorLine = doc.lineAt(view.state.selection.main.head).number - 1;
  const next = computeNextSubgroupHeader(text, cursorLine);
  if (!next) return false; // カーソルがどのグループの中にいるか判定できない場合は何もしない

  const insertLine = doc.lineAt(view.state.selection.main.head);
  const insertText = buildHeaderInsertText(next.subId, next.newPathKey, getSettingLine);
  view.dispatch({
    changes: { from: insertLine.from, insert: insertText },
    selection: { anchor: insertLine.from + insertText.length },
    scrollIntoView: true,
  });
  return true;
};

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

function ScenarioTransactionCodeEditor({
  value, onChange, roleNames, roleSchemas, classDataSchemas, height = '420px',
  // サブグループ設定(is_wait_key など)の共通スキーマと、新しい見出しに添えるデフォルトの設定行。
  // どちらも省略可能(省略時は '#@' 行の診断・補完・デフォルト挿入を行わない)。
  subGroupSettingSchema = null, subGroupSettingDefaultLine = '',
  // 右上の「Utils」メニューを出すか(既定: 出す)
  showUtils = true,
}) {
  // roleNames/roleSchemas/classDataSchemas は、呼び出し元(GUI側)の state から
  // 毎レンダー新しい参照で渡されてくることが多い。そのままextensionsのuseMemoの
  // 依存配列に入れると、内容が同じでも参照が変わるたびにCodeMirrorの
  // 言語定義・リンター・オートコンプリートが丸ごと再構築されてしまい、
  // (GUI側でのClassData関連の入力遅延と同種の原因で)DSLエディタ側でも
  // 入力がもたつく要因になる。
  // 最新値はrefで持ち、linter/補完は「呼ばれた時点のrefを読む」薄いラッパーに
  // することで、extensions自体は中身が実際に変わった時だけ作り直せばよいようにする。
  const roleNamesRef = useRef(roleNames);
  const roleSchemasRef = useRef(roleSchemas);
  const classDataSchemasRef = useRef(classDataSchemas);
  useEffect(() => { roleNamesRef.current = roleNames; });
  useEffect(() => { roleSchemasRef.current = roleSchemas; });
  useEffect(() => { classDataSchemasRef.current = classDataSchemas; });
  const settingSchemaRef = useRef(subGroupSettingSchema);
  const settingDefaultLineRef = useRef(subGroupSettingDefaultLine);
  useEffect(() => { settingSchemaRef.current = subGroupSettingSchema; });
  useEffect(() => { settingDefaultLineRef.current = subGroupSettingDefaultLine; });

  // 依存配列を「参照」ではなく「中身」で比較するためのキー。
  // これらは1ドキュメント分のスキーマ情報であり、頻繁に変わるものでもないため
  // JSON.stringifyのコストは無視できる。
  const roleNamesKey = useMemo(() => (roleNames || []).join(','), [roleNames]);
  const roleSchemasKey = useMemo(() => JSON.stringify(roleSchemas || {}), [roleSchemas]);
  const classDataSchemasKey = useMemo(() => JSON.stringify(classDataSchemas || {}), [classDataSchemas]);
  const settingSchemaKey = useMemo(() => JSON.stringify(subGroupSettingSchema || null), [subGroupSettingSchema]);

  // ── Utils メニュー ──
  // CodeMirror の view は onCreateEditor で受け取って ref に持つ(メニュー操作から直接編集するため)。
  const viewRef = useRef(null);
  const [utilsAnchor, setUtilsAnchor] = useState(null);
  const [utilsInfo, setUtilsInfo] = useState(null); // メニューを開いた時点の { hasHeaders, current }
  const [utilsMsg, setUtilsMsg] = useState('');
  const [indexDlg, setIndexDlg] = useState(null); // { text, siblings, current }
  const msgTimerRef = useRef(null);
  const flashMsg = (m) => {
    setUtilsMsg(m);
    if (msgTimerRef.current) clearTimeout(msgTimerRef.current);
    msgTimerRef.current = setTimeout(() => setUtilsMsg(''), 5000);
  };
  useEffect(() => () => { if (msgTimerRef.current) clearTimeout(msgTimerRef.current); }, []);

  const openUtils = (e) => {
    const view = viewRef.current;
    let info = { hasHeaders: false, current: null };
    if (view) {
      const text = view.state.doc.toString();
      const cursorLine = view.state.doc.lineAt(view.state.selection.main.head).number - 1;
      const { current, sections } = findSiblingSections(text, cursorLine);
      info = { hasHeaders: sections.length > 0, current };
    }
    setUtilsInfo(info);
    setUtilsAnchor(e.currentTarget);
  };
  const closeUtils = () => setUtilsAnchor(null);

  const runInsert = (makeCommand) => {
    closeUtils();
    const view = viewRef.current;
    if (!view) return;
    const ok = makeCommand(() => settingDefaultLineRef.current)(view);
    if (ok === false) flashMsg('カーソルがどのグループの中にもありません(見出しの下で実行してください)');
    view.focus();
  };

  const runRenumberDuplicates = () => {
    closeUtils();
    const view = viewRef.current;
    if (!view) return;
    const { text: newText, renamed } = renumberDuplicateNodeIds(view.state.doc.toString());
    if (renamed.length === 0) { flashMsg('重複しているIDは見つかりませんでした'); return; }
    view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: newText } });
    flashMsg(`ID重複を解消しました: ${renamed.map((r) => `${r.oldPath} → ${r.newPath}`).join(', ')}`);
    view.focus();
  };

  const openIndexTools = () => {
    closeUtils();
    const view = viewRef.current;
    if (!view) return;
    const text = view.state.doc.toString();
    const cursorLine = view.state.doc.lineAt(view.state.selection.main.head).number - 1;
    const { current, siblings } = findSiblingSections(text, cursorLine);
    if (!current) { flashMsg('カーソルを見出し(# ==== SUB:… NODE:… ====)の下に置いてから実行してください'); return; }
    setIndexDlg({ text, siblings, current });
  };

  const applyIndexPlan = (plan) => {
    const view = viewRef.current;
    setIndexDlg(null);
    if (!view || !plan || plan.changes.length === 0) return;
    // 全文を置き換えず、変更のあった数値だけを書き換える(Ctrl+Zで1操作として戻せる・カーソルも保たれる)
    const doc = view.state.doc;
    view.dispatch({
      changes: plan.changes.map((c) => {
        const ln = doc.line(c.line + 1);
        return { from: ln.from + c.from, to: ln.from + c.to, insert: String(c.toValue) };
      }),
    });
    flashMsg(`${plan.changes.length}件のインデックスを書き換えました(Ctrl+Zで元に戻せます)`);
    view.focus();
  };

  const extensions = useMemo(() => [
    buildDslLanguage(),
    createLinter(
      (view) => buildLintSource(roleSchemasRef.current, classDataSchemasRef.current, settingSchemaRef.current)(view),
      { delay: 400 }
    ),
    autocompletion({
      override: [
        (context) => buildCompletionSource(roleNamesRef.current || [], roleSchemasRef.current || {}, classDataSchemasRef.current || {}, settingSchemaRef.current, settingDefaultLineRef.current)(context),
      ],
    }),
    keymap.of([
      indentWithTab,
      // デフォルトの設定行は呼ばれた時点のrefを読む(スキーマ取得後に変わってもextensionsの作り直しは不要)
      { key: 'Mod-Alt-g', run: makeInsertNewGroupCommand(() => settingDefaultLineRef.current), preventDefault: true },
      { key: 'Mod-Alt-h', run: makeInsertNewSubgroupCommand(() => settingDefaultLineRef.current), preventDefault: true },
    ]),
    EditorView.lineWrapping,
    // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [roleNamesKey, roleSchemasKey, classDataSchemasKey, settingSchemaKey]);

  return (
    <Box>
      {showUtils && (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
          <Button size="small" variant="outlined" startIcon={<BuildIcon fontSize="small" />} onClick={openUtils}>
            Utils
          </Button>
          <Typography variant="caption" color="text.secondary" sx={{ flex: 1 }} noWrap>
            {utilsMsg || '見出しの挿入・ID振り直し・インデックス一括調整など'}
          </Typography>
        </Box>
      )}
      <CodeMirror
        value={value}
        height={height}
        extensions={extensions}
        onChange={onChange}
        basicSetup={BASIC_SETUP}
        onCreateEditor={(view) => { viewRef.current = view; }}
      />
      <Menu anchorEl={utilsAnchor} open={Boolean(utilsAnchor)} onClose={closeUtils}>
        <MenuItem onClick={() => runInsert(makeInsertNewGroupCommand)}>
          <ListItemText primary="新しいグループの見出しを挿入" secondary="直前のグループのIDに+1（Ctrl/Cmd+Alt+G）" />
        </MenuItem>
        <MenuItem onClick={() => runInsert(makeInsertNewSubgroupCommand)}>
          <ListItemText primary="新しいサブグループの見出しを挿入" secondary="今いるグループ内の直前のサブグループのIDに+1（Ctrl/Cmd+Alt+H）" />
        </MenuItem>
        <Divider />
        <MenuItem onClick={runRenumberDuplicates} disabled={!utilsInfo || !utilsInfo.hasHeaders}>
          <ListItemText primary="重複しているIDを振り直す" secondary="コピー&ペースト直後などで、同じ親の中でIDが重複した見出しを解消" />
        </MenuItem>
        <Tooltip title={utilsInfo && !utilsInfo.current ? 'カーソルを見出しの下に置いてください' : ''} placement="left">
          <span>
            <MenuItem onClick={openIndexTools} disabled={!utilsInfo || !utilsInfo.current}>
              <ListItemText primary="インデックスを一括調整…" secondary="カーソルのサブグループ以降の text_list_index / voice_ref をずらす・連番にする" />
            </MenuItem>
          </span>
        </Tooltip>
      </Menu>
      {indexDlg && (
        <ScenarioIndexToolsDialog
          open
          onClose={() => setIndexDlg(null)}
          title="インデックス一括調整（DSL）"
          startOptions={indexDlg.siblings.map((s) => ({ value: s.pathKey, label: `SUB:${s.subId} NODE:${s.pathKey}` }))}
          initialStart={indexDlg.current.pathKey}
          getFields={(includeInt) => collectIndexFieldsInDsl(indexDlg.text, roleSchemas || {}, { includeInt })}
          makePlan={(o) => {
            const sec = indexDlg.siblings.find((s) => s.pathKey === o.start);
            return planIndexAdjustInDsl(indexDlg.text, roleSchemas || {}, {
              cursorLine: sec ? sec.headerLine : indexDlg.current.headerLine, endPathKey: o.end,
              mode: o.mode, delta: o.delta, step: o.step, base: o.base, includeStart: o.includeStart,
              includeInt: o.includeInt, target: o.target,
            });
          }}
          describeChange={(c) => ({ where: `NODE:${c.pathKey}`, field: `${c.roleName}.${c.fieldName}（${c.line + 1}行目）` })}
          onApply={applyIndexPlan}
        />
      )}
    </Box>
  );
}

export default ScenarioTransactionCodeEditor;
// extension.js
//
// Scenario Lua DSL Editor
// ------------------------------------------------------------
// Web版(ScenarioEventTransition.js)の「全体編集(全Sub一括)」「Sub編集
// (現在のSubのみ)」と全く同じDSL・同じルールで、VSCode上からシナリオイベントの
// Transactionを直接編集・保存できるようにする拡張機能。
//
// 使い方:
//   1. 左のアクティビティバーにある Scenario Lua アイコンをクリックする
//      → サイドバーに検索・ソート可能なグリッド(表)が常に表示されるので、
//        編集したいイベント/Subの行の「編集」ボタンを押す
//      （コマンドパレットから「Scenario Lua: どのイベント/Subを編集するか選ぶ」を
//        実行すると、同じグリッドを大きなタブとして開くこともできる）
//   2. 選ぶと仮想ファイルとして開く
//   3. 通常のテキストエディタとして編集（Role名・フィールド名・値の補完、
//      リアルタイムのエラー表示つき）
//   4. Ctrl+S (Cmd+S) で保存すると、コンパイル・検証してからサーバーへPOSTする
//      （エラーがある場合は保存されず、内容を確認するよう表示される）
//
// 設定:
//   scenarioLuaDsl.apiBaseUrl          … バックエンドのベースURL
//   scenarioLuaDsl.allowCreateNewGroups … 未知の見出しから新規グループを
//                                          自動作成してよいか(Web版と同じ安全策。既定OFF)

const vscode = require('vscode');
const { ScenarioApi } = require('./api');
const { lintDocument, getCompletionsAt, computeNextGroupHeader, computeNextSubgroupHeader } = require('./dslCore');
const { buildEditLinesForSub, parseEditSections, applyEditSections } = require('./treeEdit');
const { ScenarioGridPanel } = require('./scenarioGridPanel');
const { ScenarioGridViewProvider } = require('./scenarioGridView');
const { GridController } = require('./gridController');

const SCHEME = 'scenario-lua';
const LANGUAGE_ID = 'scenario-lua';

// uriString -> { eventId, subIds: string[], trees: {[subId]: {nodes, edges}},
//                targets: {"subId::path": node}, roleSchemas, roleNames }
const sessions = new Map();

// ============================================================
// 仮想ファイルシステム(MemFS) ── ディスクに書き込まず、メモリ上だけで
// 「編集可能なファイル」としてVSCodeに見せるためのFileSystemProvider実装。
// writeFile(=Ctrl+Sで呼ばれる)をフックして、保存時にコンパイル→サーバーPOSTする。
// ============================================================
class ScenarioLuaFs {
  constructor(context, diagnostics, output) {
    this.context = context;
    this.diagnostics = diagnostics;
    this.output = output;
    this.files = new Map(); // uriString -> Uint8Array
    this._emitter = new vscode.EventEmitter();
    this.onDidChangeFile = this._emitter.event;
  }

  watch() {
    return new vscode.Disposable(() => {});
  }

  stat(uri) {
    const content = this.files.get(uri.toString());
    if (!content) throw vscode.FileSystemError.FileNotFound(uri);
    return { type: vscode.FileType.File, ctime: Date.now(), mtime: Date.now(), size: content.byteLength };
  }

  readDirectory() {
    return [];
  }

  createDirectory() {
    // ディレクトリ概念は使わないので何もしない
  }

  readFile(uri) {
    const content = this.files.get(uri.toString());
    if (!content) throw vscode.FileSystemError.FileNotFound(uri);
    return content;
  }

  writeFile(uri, content) {
    const key = uri.toString();
    const session = sessions.get(key);
    const text = Buffer.from(content).toString('utf8');

    if (!session) {
      // セッション情報が無い(拡張機能の再起動直後など) → そのまま保持するだけにする
      this.files.set(key, content);
      this._emitter.fire([{ type: vscode.FileChangeType.Changed, uri }]);
      return;
    }

    const allowNewGroups = vscode.workspace.getConfiguration('scenarioLuaDsl').get('allowCreateNewGroups', false);
    const sections = parseEditSections(text);
    const { diagnostics, touchedSubIds } = applyEditSections(
      sections, session.trees, session.targets, session.roleSchemas, allowNewGroups
    );

    if (diagnostics.length > 0) {
      this.output.clear();
      this.output.appendLine('保存できませんでした。以下のエラーを解消してから、もう一度保存してください:');
      diagnostics.forEach((d) => this.output.appendLine(`  - ${d.message}`));
      this.output.show(true);
      vscode.window.showErrorMessage(
        `保存に失敗しました（${diagnostics.length}件のエラー）。出力パネル「Scenario Lua DSL」を確認してください。`
      );
      // ここでファイルシステム上のバッファは更新しない = VSCode側は保存失敗として
      // 扱われ、ドキュメントは未保存(dirty)のままになる。
      throw vscode.FileSystemError.Unavailable('DSLの内容にエラーがあるため保存できません');
    }

    // 保存対象のSubだけサーバーへPOSTする(非同期。完了・失敗は通知で知らせる)
    const api = new ScenarioApi(vscode.workspace.getConfiguration('scenarioLuaDsl').get('apiBaseUrl', ''));
    const savePromises = Array.from(touchedSubIds).map((subId) =>
      api.saveSubTransition(session.eventId, subId, session.trees[subId])
    );

    Promise.all(savePromises)
      .then(() => {
        vscode.window.showInformationMessage(
          touchedSubIds.size > 0
            ? `Scenario Lua: 保存しました（${touchedSubIds.size}件のSubを更新）`
            : 'Scenario Lua: 変更はありませんでした'
        );
      })
      .catch((err) => {
        vscode.window.showErrorMessage(`Scenario Lua: サーバーへの保存に失敗しました: ${err.message}`);
      });

    this.files.set(key, content);
    this._emitter.fire([{ type: vscode.FileChangeType.Changed, uri }]);
  }

  delete(uri) {
    this.files.delete(uri.toString());
    sessions.delete(uri.toString());
  }

  rename(oldUri, newUri) {
    const content = this.files.get(oldUri.toString());
    if (content) this.files.set(newUri.toString(), content);
    this.files.delete(oldUri.toString());
    const session = sessions.get(oldUri.toString());
    if (session) sessions.set(newUri.toString(), session);
    sessions.delete(oldUri.toString());
  }

  // openEvent/refreshDocumentから直接呼ぶ、初期内容の書き込み用ヘルパー
  seedFile(uri, text) {
    const content = Buffer.from(text, 'utf8');
    this.files.set(uri.toString(), content);
    this._emitter.fire([{ type: vscode.FileChangeType.Changed, uri }]);
  }
}

// ============================================================
// セッション構築: イベント/Subのツリーとロールスキーマを取得し、
// Lua形式テキスト・見出し⇔ノード対応表を組み立てる
// ============================================================
async function buildSession(api, eventId, subIds) {
  const [roles] = await Promise.all([api.listRoles()]);
  const roleNames = (roles || []).map((r) => r.name).filter(Boolean);

  // 補完・リントに必要な全Roleのスキーマを先読みしておく
  const roleSchemas = {};
  await Promise.all(roleNames.map(async (name) => {
    try {
      const schema = await api.getRoleFormSchema(name);
      if (schema && !schema.error) roleSchemas[name] = schema;
    } catch (e) {
      // 1つのRole取得に失敗しても全体は止めない
    }
  }));

  const trees = {};
  const targets = {};
  const lines = [];
  for (const subId of subIds) {
    const tree = (await api.getSubTransition(eventId, subId)) || { nodes: [], edges: [] };
    trees[subId] = tree;
    lines.push(...buildEditLinesForSub(subId, tree, roleSchemas, targets));
  }

  return {
    eventId,
    subIds,
    trees,
    targets,
    roleSchemas,
    roleNames,
    text: lines.join('\n'),
  };
}

function sessionUri(eventId, scopeLabel) {
  const safeEvent = encodeURIComponent(String(eventId));
  const safeScope = encodeURIComponent(String(scopeLabel));
  return vscode.Uri.parse(`${SCHEME}:/${safeEvent}/${safeScope}.scenariolua`);
}

// ============================================================
// リアルタイムリント(保存前でも赤波線でエラーを見せる)
// ヘッダ行(# ==== SUB:x NODE:y ====)や案内コメント(# 例: ...)はいずれも
// "#"始まりのコメントとしてtokenizeLineに無視されるため、compileDocument/
// lintDocumentはドキュメント全体にそのままかけて問題ない
// (Web版のCodeMirrorリンターと全く同じ考え方)。
// ============================================================
function refreshLiveDiagnostics(document, diagnosticCollection) {
  if (document.languageId !== LANGUAGE_ID) return;
  const session = sessions.get(document.uri.toString());
  const roleSchemas = session ? session.roleSchemas : {};
  const text = document.getText();
  const issues = lintDocument(text, roleSchemas);

  const diags = issues.map((issue) => {
    const lineNum = Math.min(issue.line, Math.max(document.lineCount - 1, 0));
    const line = document.lineAt(lineNum);
    const from = Math.max(0, Math.min(issue.from, line.text.length));
    const to = Math.max(from, Math.min(issue.to, line.text.length));
    const range = new vscode.Range(lineNum, from, lineNum, to === from ? from + 1 : to);
    const diag = new vscode.Diagnostic(
      range,
      issue.message,
      issue.severity === 'warning' ? vscode.DiagnosticSeverity.Warning : vscode.DiagnosticSeverity.Error
    );
    diag.source = 'scenario-lua';
    return diag;
  });
  diagnosticCollection.set(document.uri, diags);
}

// ============================================================
// activate
// ============================================================
function activate(context) {
  const output = vscode.window.createOutputChannel('Scenario Lua DSL');
  const diagnosticCollection = vscode.languages.createDiagnosticCollection('scenario-lua');
  context.subscriptions.push(diagnosticCollection, output);

  const fs = new ScenarioLuaFs(context, diagnosticCollection, output);
  context.subscriptions.push(vscode.workspace.registerFileSystemProvider(SCHEME, fs, { isCaseSensitive: true }));

  const getApi = () => new ScenarioApi(vscode.workspace.getConfiguration('scenarioLuaDsl').get('apiBaseUrl', ''));

  // 現在開いているセッションの一覧("eventId::subId" / "eventId::ALL")を
  // グリッド(サイドバー常設ビュー・パネル両方)の「編集中」バッジ表示に反映する
  const notifyOpenKeysChanged = () => {
    const keys = Array.from(sessions.values()).map((s) => `${s.eventId}::${s.scopeLabel}`);
    gridController.notifyOpenKeysChanged(keys);
  };

  // イベント/Sub(または全Sub)を選んでLua形式エディタとして開く、共通処理。
  // コマンドパレット・グリッドUIの両方から呼ばれる。
  const openScenarioSession = async (eventId, subId) => {
    const api = getApi();

    // グリッドUIからは eventId しか渡らないため(全Subの一覧はここで取り直す)、
    // 「全Sub一括」を選んだ場合はイベント一覧を再取得してSub一覧を得る
    let subIds;
    if (subId) {
      subIds = [String(subId)];
    } else {
      const events = await api.listEvents();
      const eventEntry = (events || []).find((e) => String(e.id) === String(eventId));
      subIds = ((eventEntry && eventEntry.subEvents) || []).map((s) => String(s.subId));
      if (subIds.length === 0) {
        vscode.window.showWarningMessage('このイベントにはSubがありません');
        return;
      }
    }

    const scopeLabel = subId ? String(subId) : 'ALL';
    const uri = sessionUri(eventId, scopeLabel);

    const session = await vscode.window.withProgress(
      { location: vscode.ProgressLocation.Notification, title: `Scenario Lua: ${eventId} を読み込み中...` },
      () => buildSession(api, eventId, subIds)
    );
    session.scopeLabel = scopeLabel;

    sessions.set(uri.toString(), session);
    fs.seedFile(uri, session.text);

    const doc = await vscode.workspace.openTextDocument(uri);
    await vscode.languages.setTextDocumentLanguage(doc, LANGUAGE_ID);
    await vscode.window.showTextDocument(doc, { preview: false });
    refreshLiveDiagnostics(doc, diagnosticCollection);
    notifyOpenKeysChanged();
  };

  // サイドバー常設ビュー・パネルの両方から共有するグリッドの状態・データ取得ロジック
  const gridController = new GridController(getApi, openScenarioSession);

  // ── コマンド: どのイベント/Subを編集するか選ぶ(検索・ソート可能なグリッドUIを大きなタブで開く) ──
  context.subscriptions.push(vscode.commands.registerCommand('scenarioLuaDsl.openEvent', async () => {
    ScenarioGridPanel.createOrShow(context, gridController);
  }));

  // ── サイドバーの常設グリッドビュー(コマンド不要でアイコンから直接開ける本体) ──
  const gridViewProvider = new ScenarioGridViewProvider(gridController);
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider(ScenarioGridViewProvider.viewType, gridViewProvider)
  );

  // ── コマンド: サーバーから最新の内容を再取得(未保存の変更は破棄される) ──
  context.subscriptions.push(vscode.commands.registerCommand('scenarioLuaDsl.refreshDocument', async () => {
    const editor = vscode.window.activeTextEditor;
    if (!editor || editor.document.uri.scheme !== SCHEME) {
      vscode.window.showWarningMessage('Scenario Lua DSLのファイルを開いている状態で実行してください');
      return;
    }
    const doc = editor.document;
    const oldSession = sessions.get(doc.uri.toString());
    if (!oldSession) return;

    if (doc.isDirty) {
      const answer = await vscode.window.showWarningMessage(
        '保存していない変更があります。サーバーから再取得すると、この変更は失われます。続けますか？',
        { modal: true }, 'サーバーから再取得する'
      );
      if (answer !== 'サーバーから再取得する') return;
    }

    const api = getApi();
    let session;
    try {
      session = await vscode.window.withProgress(
        { location: vscode.ProgressLocation.Notification, title: 'Scenario Lua: 再取得中...' },
        () => buildSession(api, oldSession.eventId, oldSession.subIds)
      );
    } catch (e) {
      vscode.window.showErrorMessage(`再取得に失敗しました: ${e.message}`);
      return;
    }
    session.scopeLabel = oldSession.scopeLabel;
    sessions.set(doc.uri.toString(), session);

    const fullRange = new vscode.Range(0, 0, doc.lineCount, 0);
    const edit = new vscode.WorkspaceEdit();
    edit.replace(doc.uri, fullRange, session.text);
    await vscode.workspace.applyEdit(edit);
    fs.seedFile(doc.uri, session.text);
    refreshLiveDiagnostics(doc, diagnosticCollection);
    vscode.window.showInformationMessage('Scenario Lua: サーバーの最新内容を反映しました');
  }));

  // ── コマンド: 新しいグループの追加を許可する/しない を切り替え ──
  context.subscriptions.push(vscode.commands.registerCommand('scenarioLuaDsl.toggleAllowCreateNewGroups', async () => {
    const config = vscode.workspace.getConfiguration('scenarioLuaDsl');
    const current = config.get('allowCreateNewGroups', false);
    await config.update('allowCreateNewGroups', !current, vscode.ConfigurationTarget.Global);
    vscode.window.showInformationMessage(
      `Scenario Lua: 新しいグループの追加を ${!current ? '許可する' : '許可しない'} に切り替えました`
    );
  }));

  // ── コマンド: 新しいグループ/サブグループの見出しを、直前の兄弟からIDを
  //    自動でインクリメントして、カーソル位置に挿入する ──
  const insertHeaderAtCursor = async (compute, notFoundMessage) => {
    const editor = vscode.window.activeTextEditor;
    if (!editor || editor.document.languageId !== LANGUAGE_ID) {
      vscode.window.showWarningMessage('Scenario Lua DSLのファイルを編集している状態で実行してください');
      return;
    }
    const doc = editor.document;
    const cursorLine = editor.selection.active.line;
    const text = doc.getText();
    const next = compute(text, cursorLine);
    if (!next) {
      vscode.window.showWarningMessage(notFoundMessage);
      return;
    }
    const insertPos = new vscode.Position(cursorLine, 0);
    const insertText = `# ==== SUB:${next.subId} NODE:${next.newPathKey} ====\n\n`;
    await editor.edit((editBuilder) => editBuilder.insert(insertPos, insertText));
    const newPos = insertPos.translate(2, 0);
    editor.selection = new vscode.Selection(newPos, newPos);
  };

  context.subscriptions.push(vscode.commands.registerCommand('scenarioLuaDsl.insertNewGroup', () => (
    insertHeaderAtCursor(computeNextGroupHeader, '新しいグループの見出しを挿入できませんでした')
  )));
  context.subscriptions.push(vscode.commands.registerCommand('scenarioLuaDsl.insertNewSubgroup', () => (
    insertHeaderAtCursor(
      computeNextSubgroupHeader,
      'カーソルがどのグループの中にいるか判定できませんでした（既存の見出しの下にカーソルを置いてから実行してください）'
    )
  )));

  // ── 補完 ──
  context.subscriptions.push(vscode.languages.registerCompletionItemProvider(
    { language: LANGUAGE_ID },
    {
      provideCompletionItems(document, position) {
        const session = sessions.get(document.uri.toString());
        const roleNames = session ? session.roleNames : [];
        const roleSchemas = session ? session.roleSchemas : {};
        const text = document.getText();
        const items = getCompletionsAt(text, position.line, position.character, roleNames, roleSchemas);
        if (items.length === 0) return null;

        // 補完の置換範囲を明示的に計算する。VSCodeのデフォルト(range未指定)は
        // 言語設定のwordPatternから「現在の単語」を判定するが、それに頼らず
        // ここでも同じロジックで明示しておく(Web版のCodeMirror側と同じ対策)。
        // enum/class_data_id は "GuestCharacterID.GuestCharacter_01" のように
        // ドット(.)を含む完全修飾形で保存するため、ドットも「単語の一部」に含めて
        // 判定しないと、"GuestCharacterID.Guest" まで打った状態で補完したときに
        // "GuestCharacterID." が置換されずに残ったまま候補が継ぎ足されてしまう
        // (例: "GuestCharacterID.GuestCharacterID.GuestCharacter_01"。
        //  カンマ区切りの2つ目以降の値を補完する場合も同様)。
        const lineText = document.lineAt(position.line).text;
        const beforeCursor = lineText.slice(0, position.character);
        const wordMatch = beforeCursor.match(/[A-Za-z0-9_.]*$/);
        const startCh = position.character - (wordMatch ? wordMatch[0].length : 0);
        const range = new vscode.Range(position.line, startCh, position.line, position.character);

        return items.map((it) => {
          const kind = it.type === 'role'
            ? vscode.CompletionItemKind.Class
            : it.type === 'field'
              ? vscode.CompletionItemKind.Property
              : vscode.CompletionItemKind.Value;
          const item = new vscode.CompletionItem(it.label, kind);
          if (it.detail) item.detail = it.detail;
          item.range = range;
          // Role名の場合、it.insertText に「デフォルト値付きの呼び出し」が入っている
          // ことがある(未設定フィールドは自動で埋めない。設定済みのものだけ挿入する)。
          item.insertText = it.insertText || it.label;
          return item;
        });
      },
    },
    '=', ':', ' ', '"', '{', '['
  ));

  // ── リアルタイムリント ──
  context.subscriptions.push(vscode.workspace.onDidOpenTextDocument((doc) => {
    if (doc.languageId === LANGUAGE_ID) refreshLiveDiagnostics(doc, diagnosticCollection);
  }));
  let lintTimer = null;
  context.subscriptions.push(vscode.workspace.onDidChangeTextDocument((e) => {
    if (e.document.languageId !== LANGUAGE_ID) return;
    if (lintTimer) clearTimeout(lintTimer);
    // 全体編集は長いドキュメントになりがちなので、キー入力のたびに即リントせず
    // 少し待ってからまとめてリントする(Web版のCodeMirrorリンターと同じ考え方)。
    lintTimer = setTimeout(() => refreshLiveDiagnostics(e.document, diagnosticCollection), 400);
  }));
  context.subscriptions.push(vscode.workspace.onDidCloseTextDocument((doc) => {
    diagnosticCollection.delete(doc.uri);
    if (doc.uri.scheme === SCHEME) {
      sessions.delete(doc.uri.toString());
      notifyOpenKeysChanged();
    }
  }));
}

function deactivate() {}

module.exports = { activate, deactivate };

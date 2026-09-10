// gridController.js
//
// サイドバーの常設グリッド(WebviewView)と、コマンドから開く大きいグリッド(WebviewPanel)の
// 両方から共通で使う「データ取得・メッセージ処理・複数Webviewへの一斉配信」をまとめたもの。
// 同じイベント一覧・同じ「編集中」バッジ状態を、開いているすべてのグリッド表示に反映する。

const vscode = require('vscode');

class GridController {
  /**
   * @param {() => import('./api').ScenarioApi} getApi 常に最新の設定を反映したAPIクライアントを返す関数
   * @param {(eventId: string, subId: string|null) => Promise<void>} onOpen
   */
  constructor(getApi, onOpen) {
    this.getApi = getApi;
    this.onOpen = onOpen;
    this.webviews = new Set(); // 現在表示中の vscode.Webview 一覧(サイドバー分・パネル分)
    this.lastOpenKeys = [];
  }

  // 1つのWebviewを制御下に追加し、メッセージハンドリングを配線する
  attach(webview) {
    this.webviews.add(webview);
    webview.onDidReceiveMessage(async (msg) => {
      if (!msg) return;
      if (msg.type === 'ready' || msg.type === 'refresh') {
        await this.refresh();
      } else if (msg.type === 'open') {
        try {
          await this.onOpen(msg.eventId, msg.subId || null);
        } catch (e) {
          vscode.window.showErrorMessage(`開けませんでした: ${e.message}`);
        }
      } else if (msg.type === 'migrateLegacy') {
        await this.migrateLegacy();
      }
    });
    // 開いた直後に、既に取得済みのデータがあれば即反映する
    webview.postMessage({ type: 'openKeys', openKeys: this.lastOpenKeys });
  }

  detach(webview) {
    this.webviews.delete(webview);
  }

  broadcast(msg) {
    this.webviews.forEach((w) => w.postMessage(msg));
  }

  async refresh() {
    this.broadcast({ type: 'loading' });
    try {
      const events = await this.getApi().listEvents();
      this.broadcast({ type: 'setData', events: events || [] });
    } catch (e) {
      this.broadcast({
        type: 'error',
        message: `イベント一覧の取得に失敗しました: ${e.message}（設定 scenarioLuaDsl.apiBaseUrl を確認してください）`,
      });
    }
  }

  // 旧形式(イベントID直下に1ファイルへ全Subをまとめて保存)のまま残っている
  // イベントデータを、新形式(イベント名フォルダ + Subごとの個別ファイル)へ
  // まとめて更新する。Web版のScenarioEventGridの「旧形式を一括更新」ボタンと同じ
  // /api/scenario-event/migrate-legacy を叩くだけ(実処理はサーバー側)。
  async migrateLegacy() {
    const answer = await vscode.window.showWarningMessage(
      '旧形式のまま残っているイベントデータを、新しい保存形式へ一括更新しますか？',
      { modal: true },
      '更新する'
    );
    if (answer !== '更新する') return;

    try {
      const result = await vscode.window.withProgress(
        { location: vscode.ProgressLocation.Notification, title: 'Scenario Lua: 旧形式のデータを更新中...' },
        () => this.getApi().migrateLegacyEvents()
      );
      const migrated = (result && result.migrated) ? result.migrated.length : 0;
      const failed = (result && result.failed) ? result.failed.length : 0;
      if (failed > 0) {
        vscode.window.showWarningMessage(
          `更新完了: ${migrated}件更新（${failed}件失敗。詳細はサーバーログを確認してください）`
        );
      } else if (migrated > 0) {
        vscode.window.showInformationMessage(`${migrated}件のイベントを新しい形式に更新しました`);
      } else {
        vscode.window.showInformationMessage('更新が必要なイベントはありませんでした（すでに最新形式です）');
      }
    } catch (e) {
      vscode.window.showErrorMessage(`更新に失敗しました: ${e.message}`);
    }
    await this.refresh();
  }

  notifyOpenKeysChanged(openKeys) {
    this.lastOpenKeys = openKeys;
    this.broadcast({ type: 'openKeys', openKeys });
  }
}

module.exports = { GridController };

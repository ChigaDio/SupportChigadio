// gridController.js
//
// サイドバーの常設グリッド(WebviewView)と、コマンドから開く大きいグリッド(WebviewPanel)の
// 両方から共通で使う「データ取得・メッセージ処理・複数Webviewへの一斉配信」をまとめたもの。
// 同じイベント一覧・同じ「編集中」バッジ状態を、開いているすべてのグリッド表示に反映する。

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
          // eslint-disable-next-line global-require
          require('vscode').window.showErrorMessage(`開けませんでした: ${e.message}`);
        }
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

  notifyOpenKeysChanged(openKeys) {
    this.lastOpenKeys = openKeys;
    this.broadcast({ type: 'openKeys', openKeys });
  }
}

module.exports = { GridController };

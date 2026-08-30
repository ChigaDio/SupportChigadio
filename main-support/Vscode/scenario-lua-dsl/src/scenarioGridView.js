// scenarioGridView.js
//
// アクティビティバーに常設されるサイドバービュー。
// コマンドパレットで何かを打つ必要はなく、左端のアイコンをクリックするだけで
// シナリオ選択グリッドが開く、いわば「GUIから選ぶ」ための本体。

const { getGridHtml } = require('./gridHtml');

class ScenarioGridViewProvider {
  static viewType = 'scenarioLuaDsl.grid';

  /**
   * @param {import('./gridController').GridController} controller
   */
  constructor(controller) {
    this.controller = controller;
  }

  resolveWebviewView(webviewView) {
    webviewView.webview.options = { enableScripts: true, localResourceRoots: [] };
    webviewView.webview.html = getGridHtml(webviewView.webview, { compact: true });
    this.controller.attach(webviewView.webview);

    webviewView.onDidDispose(() => {
      this.controller.detach(webviewView.webview);
    });

    // ビューが再表示される(タブを閉じて開き直す等)たびに最新化しておく
    webviewView.onDidChangeVisibility(() => {
      if (webviewView.visible) this.controller.refresh();
    });
  }
}

module.exports = { ScenarioGridViewProvider };

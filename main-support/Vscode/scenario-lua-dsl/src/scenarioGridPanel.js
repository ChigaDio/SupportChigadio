// scenarioGridPanel.js
//
// コマンドパレットから開く、大きめのタブとしてのグリッドパネル。
// 中身(HTML/データ取得)はサイドバーの常設ビュー(scenarioGridView.js)と共通の
// GridController / gridHtml を使っている。

const vscode = require('vscode');
const { getGridHtml } = require('./gridHtml');

class ScenarioGridPanel {
  /**
   * @param {import('vscode').ExtensionContext} context
   * @param {import('./gridController').GridController} controller
   */
  static createOrShow(context, controller) {
    const column = vscode.window.activeTextEditor
      ? vscode.window.activeTextEditor.viewColumn
      : undefined;

    if (ScenarioGridPanel.currentPanel) {
      ScenarioGridPanel.currentPanel.panel.reveal(column);
      controller.refresh();
      return ScenarioGridPanel.currentPanel;
    }

    const panel = vscode.window.createWebviewPanel(
      'scenarioLuaDslGrid',
      'Scenario Lua: 編集するシナリオを選択',
      column || vscode.ViewColumn.One,
      { enableScripts: true, retainContextWhenHidden: true, localResourceRoots: [] }
    );

    ScenarioGridPanel.currentPanel = new ScenarioGridPanel(panel, controller);
    return ScenarioGridPanel.currentPanel;
  }

  constructor(panel, controller) {
    this.panel = panel;
    this.controller = controller;
    this.panel.webview.html = getGridHtml(this.panel.webview, { compact: false });
    this.controller.attach(this.panel.webview);

    this.panel.onDidDispose(() => {
      this.controller.detach(this.panel.webview);
      if (ScenarioGridPanel.currentPanel === this) ScenarioGridPanel.currentPanel = undefined;
    });
  }
}

module.exports = { ScenarioGridPanel };

import React from 'react';
import ScenarioRoleDetailGrid from './ScenarioRoleDetailGrid';

// サブグループ設定（全イベント共通のフィールド定義）の編集ページ。
// Roleのフィールド定義編集(ScenarioRoleDetailGrid)と同じ画面・同じ型
// (class_data_id / class_data / enum / bezier / color / bit / 配列 / dictionary / ネスト等)で、
// 先頭に組み込みの is_wait_key（入力待ち）を持つ。デフォルト値の設定もここから行う。
//
// ルート登録例:
//   <Route path="/scenario-subgroup-setting" element={<ScenarioSubGroupSettingGrid />} />
function ScenarioSubGroupSettingGrid() {
  return <ScenarioRoleDetailGrid settingMode />;
}

export default ScenarioSubGroupSettingGrid;
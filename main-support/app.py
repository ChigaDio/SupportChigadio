# -*- coding: utf-8 -*-
"""
app.py

ツール本体のFlaskサーバー。

役割分担:
- Scenario / Assets / DbgServer / AddressableInit / Behavior(本体) / Animation / Scene /
  SaveData / CustomClassData / DebugCommand: 各 pythonSrc/*.py に実装（既存のまま）
- ClassData(+Enum) / ClassDataID / Matrix(ClassDataMatrixID) / State / Behavior(APIルート):
  pythonSrc/class_data.py, class_data_id.py, matrix.py, state.py, behavior_routes.py に分離
- ScenarioRole / Texture / GameObject / Material / Sound / Animator / Scene / SaveData /
  ConstClassData など、上記以外のAPIルートはこのファイルに残置

起動時にプロジェクト用ボイラープレート（C#/Python/JS の基底クラス等）を一度だけ生成し、
その後 Flask ルートを提供する。
"""
from math import isnan, isfinite
import copy
import logging
import re
import shutil
import struct
import subprocess
import sys
from flask import Flask, send_file, send_from_directory, jsonify, request
import os
import json
import textwrap
import threading
from pathlib import Path

import psutil

import pythonSrc.generators as generators
import pythonSrc.scenario as scenario
import pythonSrc.assets as assets
import pythonSrc.dbgServer as dbgServer
import pythonSrc.addressableInit
import pythonSrc.behavior
import pythonSrc.animation
import pythonSrc.scene as scene
import pythonSrc.savedata as savedata
import pythonSrc.expansion as expansion
import pythonSrc.customclassdata
import pythonSrc.debugcommand as dbgcommand

# 本ファイルから切り出したカテゴリ別ルートモジュール
import pythonSrc.data_utils as data_utils
import pythonSrc.class_data
import pythonSrc.class_data_id
import pythonSrc.matrix
import pythonSrc.state
import pythonSrc.behavior_routes

# サーバーモード関連（認証/権限/バージョン管理/お知らせ/ワークスペース/ダウンロード）
import pythonSrc.activity_log as activity_log
import pythonSrc.auth as auth
import pythonSrc.versioning as versioning
import pythonSrc.announcements as announcements
import pythonSrc.workspace_routes as workspace_routes
import pythonSrc.download as download_module
import pythonSrc.csproj_sync as csproj_sync
import pythonSrc.file_locator as file_locator
import pythonSrc.reference_check as reference_check
import pythonSrc.lint_check as lint_check
import pythonSrc.trash as trash
import pythonSrc.generate_all as generate_all
import pythonSrc.history as history
import pythonSrc.spreadsheet_io as spreadsheet_io
import pythonSrc.project_stats as project_stats
import pythonSrc.story_setting as story_setting
import pythonSrc.upload as upload_module

# `python app.py Server` で起動した場合のみサーバー専用モード（ログイン必須・権限制御）になる。
# 引数なしの通常起動では、これまで通り誰でも編集可能。
def _prompt_launch_mode_dialog():
    """コマンドライン引数で起動モードが指定されなかった場合、
    起動時にダイアログでサーバーモード／通常モードを選択させる。"""
    import tkinter as tk

    result = {"server_mode": False}
    root = tk.Tk()
    root.title("起動モード選択")
    root.configure(bg="#0a0e17")
    root.geometry("440x260")
    root.resizable(False, False)
    root.attributes("-topmost", True)

    tk.Label(
        root, text="起動モードを選択してください", fg="#00eaff", bg="#0a0e17",
        font=("Meiryo", 14, "bold")
    ).pack(pady=(28, 8))
    tk.Label(
        root,
        text="サーバーモード：ログイン必須。役職(管理人/編集者/閲覧者)ごとの\n"
             "編集権限・バージョン管理・ワークスペースが有効になります。\n"
             "通常モード：これまで通り、誰でも自由に編集できます。",
        fg="#8fa3b8", bg="#0a0e17", font=("Meiryo", 9), justify="center"
    ).pack(pady=(0, 20))

    def choose_server():
        result["server_mode"] = True
        root.destroy()

    def choose_normal():
        result["server_mode"] = False
        root.destroy()

    btn_frame = tk.Frame(root, bg="#0a0e17")
    btn_frame.pack()
    tk.Button(
        btn_frame, text="🖧  サーバーモードで起動", command=choose_server,
        bg="#00eaff", fg="#0a0e17", activebackground="#33f0ff",
        font=("Meiryo", 10, "bold"), width=26, height=2, relief="flat", bd=0,
        cursor="hand2"
    ).pack(pady=6)
    tk.Button(
        btn_frame, text="通常モードで起動", command=choose_normal,
        bg="#1c2536", fg="#e6f7ff", activebackground="#2a3650",
        font=("Meiryo", 10), width=26, height=2, relief="flat", bd=0,
        cursor="hand2"
    ).pack(pady=6)

    root.protocol("WM_DELETE_WINDOW", choose_normal)  # ×で閉じたら通常モード扱い
    root.mainloop()
    return result["server_mode"]


def _determine_server_mode():
    args = [a.lower() for a in sys.argv[1:]]
    if "server" in args:
        return True
    if "normal" in args:
        return False
    # 明示的な引数が無ければ、起動時にUIで選択させる
    # （PyInstaller等でダブルクリック起動された場合を想定）
    try:
        return _prompt_launch_mode_dialog()
    except Exception as e:
        # tkinterが使えない環境（純粋なCLIサーバー等）ではデフォルトで通常モード起動
        print(f"起動モード選択ダイアログを表示できませんでした（通常モードで起動します）: {e}")
        return False


# `python app.py Server` / `python app.py Normal` で明示指定できるほか、
# 引数無しで起動した場合は上記ダイアログでの選択になる。
SERVER_MODE = _determine_server_mode()

from pythonSrc.constants import (
    ENUM,
    CLASS_DATA,
    CLASS_DATA_ID,
    CLASS_DATA_MATRIX_ID,
    STATE_DATA,
    CONST_CLASS_DATA,
    SCRIPT,
    OBJECTPOOL,
    EDITOR,
    DEBUG,
    LOG,
    PYTHON,
    SUBMODULE,
    PLUGIN,
    TYPE_MAP,
    CONST_TYPE_MAP,
)
from pythonSrc.data_utils import get_type_lists, build_custom_type_info, generate_csharp_field

if getattr(sys, 'frozen', False):
    # exe実行時（一つ前のディレクトリ）
    base_dir = os.path.abspath(os.path.join(sys.executable, ".."))
else:
    # 開発時
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

if base_dir not in sys.path:
    sys.path.append(base_dir)

isDbg = True
# 実行可能ファイルのディレクトリを取得（PyInstaller対応）
if getattr(sys, 'frozen', False):
    # PyInstallerでビルドされた場合
    BASE_DIR = os.path.dirname(sys.executable)
    isDbg = False
else:
    # デバッグ環境（VS Codeなど）
    # main-support/ の1つ上のディレクトリ（project/）を基準にする
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ディレクトリパスをプロジェクトルート基準に設定
STATIC_FOLDER = os.path.join(BASE_DIR, 'build')
DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "data"))

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder=STATIC_FOLDER)

SAVE_DATA_DIR = os.path.join(DATA_DIR, "save_data")
SAVE_DATA_CUSTOM_DIR = os.path.join(SAVE_DATA_DIR, "custom_data")

os.makedirs(DATA_DIR, exist_ok=True)

# --- META_DIR: バージョン管理(data/のバージョン切替)の影響を受けない固定フォルダ ---
# ユーザーアカウント・編集ログ・お知らせは「今どのバージョンがアクティブか」に
# 関わらず常に同じ場所に保存したいため、versionsの対象外である
# DATA_DIR(=project/data、バージョン切替時にリンク先が変わる)ではなく、
# ここ(project/app_meta)に保存する。
META_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "app_meta"))
os.makedirs(META_DIR, exist_ok=True)

activity_log.init(META_DIR)
# 認証(ログイン必須化・役職/権限チェック)をFlaskアプリへ組み込む。
# SERVER_MODE=False（通常起動）の場合はチェックを行わないため、既存の挙動は変わらない。
auth.register(app, META_DIR, SERVER_MODE)
if SERVER_MODE:
    print(f"[Server Mode] ログインが必要です。デフォルト管理者: "
          f"{auth.DEFAULT_ADMIN_USERNAME} / {auth.DEFAULT_ADMIN_PASSWORD}（マイページで変更してください）")


def find_highest_assets_folder(base_folder=BASE_DIR):
    """
    BASE_FOLDERから親ディレクトリを遡って、最も上位のAssetsフォルダを検索する。
    見つからない場合はNoneを返す。
    """
    current_path = Path(base_folder).resolve()

    # ディスクのルートに達するまで親ディレクトリを遡る
    while current_path != current_path.parent:
        # 現在のディレクトリ内にAssetsフォルダがあるかチェック
        assets_path = current_path / "Assets"
        if assets_path.exists() and assets_path.is_dir():
            return assets_path
        # 親ディレクトリに移動
        current_path = current_path.parent

    # ルートディレクトリにもAssetsフォルダがあるかチェック
    assets_path = current_path / "Assets"
    if assets_path.exists() and assets_path.is_dir():
        return assets_path

    return None


def move_dll_files(base_folder=BASE_DIR, plugin_folder_name=os.path.join(SUBMODULE, PLUGIN)):
    """
    Pluginフォルダ内のDLLファイルを、最も上位のAssetsフォルダに移動する。
    """
    if isDbg:
        return
    # Assetsフォルダを検索
    assets_folder = find_highest_assets_folder(base_folder)
    if not assets_folder:
        print("Assetsフォルダが見つかりませんでした。")
        return

    print(f"Assetsフォルダが見つかりました: {assets_folder}")

    # Pluginフォルダのパスを構築
    plugin_folder = Path(base_folder) / plugin_folder_name
    if not plugin_folder.exists() or not plugin_folder.is_dir():
        print(f"Pluginフォルダが見つかりません: {plugin_folder}")
        return

    # DLLファイルを検索して移動
    dll_files = list(plugin_folder.glob("*.dll"))
    if not dll_files:
        print(f"Pluginフォルダ内にDLLファイルが見つかりません: {plugin_folder}")
        return

    for dll_file in dll_files:
        destination = assets_folder / dll_file.name
        try:
            shutil.move(str(dll_file), str(destination))
            print(f"移動成功: {dll_file} -> {destination}")
        except Exception as e:
            print(f"移動失敗: {dll_file} -> {destination}, エラー: {e}")


move_dll_files()

scenario.generate_scenario_folder(DATA_DIR)
scenario.generate_base_script_file(DATA_DIR)
assets.generate_base()

# 分離したカテゴリ別モジュールへ DATA_DIR を共有（ルート登録は起動処理内で行う）
data_utils.init(DATA_DIR)

pythonSrc.addressableInit.generate_base()
pythonSrc.behavior.generate_base()
pythonSrc.animation.generate_base()
pythonSrc.scene.generate_base()
pythonSrc.savedata.generate_base()
expansion.get_static_file_path()


# ============================================================
# プロジェクト用ボイラープレートファイルの生成（初回起動時のみ）
#
# カテゴリ固有の基底クラス（BaseState / BaseClassDataID / BaseClassDataMatrixID /
# BaseCustomClassData 等）の生成は、それぞれ pythonSrc/state.py, class_data_id.py,
# matrix.py, class_data.py の generate_base(DATA_DIR) に移動済み
# （register(app, DATA_DIR) の呼び出し時に自動実行される）。
#
# ここに残っているのは、特定のカテゴリに属さない共通基盤のみ：
# - Script/Editor フォルダ、SupportFiles.cs / SupportFilesPostprocessor.cs
# - Debug/Log ブリッジ、BaseSingleton.cs、FastEnumBitFlags.cs
# - JS側 BinaryReader.js
# - Python側ワークスペース雛形、ObjectPool フォルダ
# ============================================================
if not os.path.exists(os.path.join(DATA_DIR, SCRIPT)):
    os.makedirs(os.path.join(DATA_DIR, SCRIPT))
    
if not os.path.exists(os.path.join(DATA_DIR, SCRIPT,EDITOR)):
    os.makedirs(os.path.join(DATA_DIR, SCRIPT,EDITOR))
    
if not os.path.exists(os.path.join(DATA_DIR, SCRIPT,"SupportFiles.cs")):
    code_str = """
using UnityEngine;
using System;
using System.IO;
#if UNITY_EDITOR
using UnityEditor;
#endif

namespace GameCore
{
    /// <summary>
    /// サポートデータ内の代表的なファイルを一箇所で定義して取得できるヘルパー。
    /// ALL_SOUND_BIN など、呼び出し側はその名前だけ参照すればフルパスが返る。
    /// </summary>
    public static class SupportFiles
    {
        public const string SUPPORT_ROOT_NAME = "SupportChigadio";
        public const string SUPPORT_DATA_NAME = "data";

        // data直下のフォルダ
        public const string ASSETS_FOLDER = "assets-data";
        public const string SOUND_FOLDER = "sound";
        public const string TEXTURE_FOLDER = "texture";
        public const string GAMEOBJECT_FOLDER = "gameobject";
        public const string MATERIAL_FOLDER = "material";

        //dataID
        public const string ID_FOLDER = "class_data_id";
        public const string ID_BIN_FILE = "all_class_data.bytes";

        //matrixID
        public const string MATRIX_DATA_ID_FOLDER = "class_data_matrix_id";
        public const string MATRIX_ID_BIN_FILE = "all_class_data_matrix.bytes";

        // ファイル名（ここだけ定義すればOK）
        public const string ALL_SOUND_BIN_FILE = "sound_data.bytes";
        public const string ALL_TEXTURE_BIN_FILE = "texture_data.bytes";
        public const string ALL_GAMEOBJECT_BIN_FILE = "gameobject_data.bytes";
        public const string ALL_MATERIAL_BIN_FILE = "material_data.bytes";

        //Scenario
        public const string SCENARIO_FOLDER = "scenario_data";
        public const string SCENARIO_EVEMT_FOLDER = "scenario_event_data";
        public const string ALL_SCENARIO_EVENT_BIN_FILE = "all_events.bytes";
        public const string ALL_STORY_SETTING_BIN_FILE = "story_settings.bytes";
        
        //CustomClassDataID
        public const string CUSTOM_CLASS_DATA_FOLDER = "custom_class_data_id";
        public const string CUSTOM_CLASS_DATA_ID_BIN_FILE = "all_custom_class_data_id.bytes";

        // キャッシュ（最初に解決したパスを保持）
        public static string s_cachedSupportDataPath = null;

        /// <summary>
        /// SupportChigadio/data のフルパスを取得（キャッシュあり／EditorではAssetDatabaseを試行）
        /// </summary>
        private static string SupportDataPath
        {
            get
            {
                if (!string.IsNullOrEmpty(s_cachedSupportDataPath)) return s_cachedSupportDataPath;

#if UNITY_EDITOR
                // EditorならAssetDatabaseでまず探す（ただしメインスレッドでないと例外になる可能性があるので try/catch）
                try
                {
                    string assetsRelative = FindFolderPathByAssetDatabase(SUPPORT_ROOT_NAME); // "Assets/..."
                    if (!string.IsNullOrEmpty(assetsRelative))
                    {
                        string projectRoot = Path.GetFullPath(Path.Combine(Application.dataPath, ".."));
                        string absoluteSupportRoot = Path.GetFullPath(Path.Combine(projectRoot, assetsRelative)); // -> .../Project/Assets/.../SupportChigadio
                        string dataPath = Path.Combine(absoluteSupportRoot, "..", SUPPORT_DATA_NAME);
                        s_cachedSupportDataPath = Path.GetFullPath(dataPath).Replace("\\\\", "/");
                        return s_cachedSupportDataPath;
                    }
                }
                catch (Exception e)
                {
                    Debug.LogWarning($"AssetDatabase lookup failed (maybe called from background thread): {e.Message}. Falling back to filesystem.");
                }
#endif
                // ファイルシステム上での候補（projectRoot/SupportChigadio/data）
                string projectRootFs = Path.GetFullPath(Path.Combine(Application.dataPath, ".."));
                string candidate = Path.Combine(projectRootFs, SUPPORT_ROOT_NAME, SUPPORT_DATA_NAME);
                if (Directory.Exists(candidate))
                {
                    s_cachedSupportDataPath = Path.GetFullPath(candidate).Replace("\\\\", "/");
                    return s_cachedSupportDataPath;
                }

                // それでも見つからなければプロジェクト内を検索（重い可能性あり）
                try
                {
                    var dirs = Directory.GetDirectories(projectRootFs, SUPPORT_ROOT_NAME, SearchOption.AllDirectories);
                    if (dirs != null && dirs.Length > 0)
                    {
                        string found = dirs[0];
                        string dataPath = Path.Combine(found, SUPPORT_DATA_NAME);
                        s_cachedSupportDataPath = Path.GetFullPath(dataPath).Replace("\\\\", "/");
                        return s_cachedSupportDataPath;
                    }
                }
                catch (Exception ex)
                {
                    Debug.LogWarning($"Fallback search failed: {ex.Message}");
                }

                // 最後の最終手段：Project直下の GameData を使う
                string fallback = Path.Combine(projectRootFs, "GameData");
                s_cachedSupportDataPath = Path.GetFullPath(fallback).Replace("\\\\", "/");
                return s_cachedSupportDataPath;
            }
        }

        /// <summary>
        /// これだけ参照すれば all_sound.bytes のフルパスが得られる（呼び出し側はこれだけ見れば良い）
        /// </summary>
        public static string ALL_SOUND_BIN => Path.GetFullPath(Path.Combine(SupportDataPath, ASSETS_FOLDER, SOUND_FOLDER, ALL_SOUND_BIN_FILE)).Replace("\\\\", "/");
        public static string ALL_TEXTURE_BIN => Path.GetFullPath(Path.Combine(SupportDataPath, ASSETS_FOLDER, TEXTURE_FOLDER, ALL_TEXTURE_BIN_FILE)).Replace("\\\\", "/");
        public static string ALL_GAMEOBJECT_BIN => Path.GetFullPath(Path.Combine(SupportDataPath, ASSETS_FOLDER, GAMEOBJECT_FOLDER, ALL_GAMEOBJECT_BIN_FILE)).Replace("\\\\", "/");
        public static string ALL_MATERIAL_BIN => Path.GetFullPath(Path.Combine(SupportDataPath, ASSETS_FOLDER, MATERIAL_FOLDER, ALL_MATERIAL_BIN_FILE)).Replace("\\\\", "/");
        public static string ALL_MATRIX_ID_BIN => Path.GetFullPath(Path.Combine(SupportDataPath, MATRIX_DATA_ID_FOLDER, MATRIX_ID_BIN_FILE)).Replace("\\\\", "/");
        public static string ALL_ID_BIN => Path.GetFullPath(Path.Combine(SupportDataPath, ID_FOLDER, ID_BIN_FILE)).Replace("\\\\", "/");
        public static string ALL_CUSTOM_CLASS_DATA_ID_BIN => Path.GetFullPath(Path.Combine(SupportDataPath, CUSTOM_CLASS_DATA_FOLDER, CUSTOM_CLASS_DATA_ID_BIN_FILE)).Replace("\\\\", "/");
        public static string ALL_SCENARIO_EVENTS_BIN => Path.GetFullPath(Path.Combine(SupportDataPath, SCENARIO_FOLDER, SCENARIO_EVEMT_FOLDER, ALL_SCENARIO_EVENT_BIN_FILE)).Replace("\\\\", "/");
        public static string ALL_STORY_SETTING_BIN => Path.GetFullPath(Path.Combine(SupportDataPath, SCENARIO_FOLDER, ALL_STORY_SETTING_BIN_FILE)).Replace("\\\\", "/");

#if UNITY_EDITOR
        // Editor専用：AssetDatabaseで探して "Assets/..." を返す（失敗すれば null）
        private static string FindFolderPathByAssetDatabase(string folderName)
        {
            string[] guids = AssetDatabase.FindAssets("t:folder " + folderName, new[] { "Assets" });
            foreach (var guid in guids)
            {
                string path = AssetDatabase.GUIDToAssetPath(guid); // "Assets/...."
                if (AssetDatabase.IsValidFolder(path) && Path.GetFileName(path) == folderName)
                    return path;
            }
            return null;
        }
#endif

        /// <summary>
        /// 補助：絶対パスがプロジェクト内（Projectルート）に含まれるなら "Assets/..." 相対パスを返す。AssetDatabase系APIに渡したいときに使える。
        /// </summary>
        public static string GetAssetRelativePath(string absolutePath)
        {
            if (string.IsNullOrEmpty(absolutePath)) return null;
            string projectRoot = Path.GetFullPath(Path.Combine(Application.dataPath, "..")).Replace("\\\\", "/");
            absolutePath = Path.GetFullPath(absolutePath).Replace("\\\\", "/");
            if (absolutePath.StartsWith(projectRoot, StringComparison.OrdinalIgnoreCase))
            {
                string rel = absolutePath.Substring(projectRoot.Length).TrimStart('/', '\\\\');
                return rel;
            }
            return null;
        }

        /// <summary>
        /// 存在確認のショートカット
        /// </summary>
        public static bool ALL_SOUND_BIN_Exists => File.Exists(ALL_SOUND_BIN);
        
                /// <summary>
        /// Addressableのチェック
        /// </summary>
        public static bool ADDRESSABLE_CHECK = true;
    }
}

"""
    with open(os.path.join(DATA_DIR, SCRIPT,"SupportFiles.cs"), 'w', encoding='utf-8') as f:
        f.write(code_str.strip() + "\n")

if not os.path.exists(os.path.join(DATA_DIR, SCRIPT,EDITOR,"SupportFilesPostprocessor.cs")):
    code_str = """
    #if UNITY_EDITOR
using UnityEditor.Build;
using UnityEditor.Build.Reporting;
using UnityEngine;
using System.IO;
using System.Collections.Generic;
using GameCore;

public class SupportFilesPostprocessor : IPostprocessBuildWithReport
{
    public int callbackOrder => 100;

    public void OnPostprocessBuild(BuildReport report)
    {
        string buildDir = Path.GetDirectoryName(report.summary.outputPath);
        if (string.IsNullOrEmpty(buildDir)) return;

        // コピー対象のファイルと、それぞれの SupportChigadio/data 以下の相対フォルダ
        var allFiles = new List<(string filePath, string targetSubFolder)>
        {
            (SupportFiles.ALL_SOUND_BIN, Path.Combine(SupportFiles.ASSETS_FOLDER, SupportFiles.SOUND_FOLDER)),
            (SupportFiles.ALL_TEXTURE_BIN, Path.Combine(SupportFiles.ASSETS_FOLDER, SupportFiles.TEXTURE_FOLDER)),
            (SupportFiles.ALL_GAMEOBJECT_BIN, Path.Combine(SupportFiles.ASSETS_FOLDER, SupportFiles.GAMEOBJECT_FOLDER)),
            (SupportFiles.ALL_MATERIAL_BIN, Path.Combine(SupportFiles.ASSETS_FOLDER, SupportFiles.MATERIAL_FOLDER)),
            (SupportFiles.ALL_MATRIX_ID_BIN, SupportFiles.MATRIX_DATA_ID_FOLDER),
            (SupportFiles.ALL_ID_BIN, SupportFiles.ID_FOLDER),
            (SupportFiles.ALL_SCENARIO_EVENTS_BIN,Path.Combine(SupportFiles.SCENARIO_FOLDER,SupportFiles.SCENARIO_EVEMT_FOLDER)),
            (SupportFiles.ALL_CUSTOM_CLASS_DATA_ID_BIN, SupportFiles.CUSTOM_CLASS_DATA_FOLDER)
        };

        foreach (var (filePath, targetFolder) in allFiles)
        {
            CopySupportFileToTargetFolder(filePath, buildDir, targetFolder);
        }
    }

    private void CopySupportFileToTargetFolder(string sourceFilePath, string buildRoot, string targetSubFolder)
    {
        if (!File.Exists(sourceFilePath))
        {
            Debug.LogWarning($"[SupportFilesPostprocessor] Source file not found: {sourceFilePath}");
            return;
        }

        string destPath = Path.Combine(buildRoot, SupportFiles.SUPPORT_ROOT_NAME, SupportFiles.SUPPORT_DATA_NAME, targetSubFolder, Path.GetFileName(sourceFilePath));

        // コピー先フォルダを作成
        string destDir = Path.GetDirectoryName(destPath);
        if (!Directory.Exists(destDir))
            Directory.CreateDirectory(destDir);

        // 上書きコピー
        File.Copy(sourceFilePath, destPath, true);
        Debug.Log($"[SupportFilesPostprocessor] Copied {sourceFilePath} -> {destPath}");
    }
}
#endif

    """
    
    with open(os.path.join(DATA_DIR, SCRIPT,EDITOR,"SupportFilesPostprocessor.cs"), 'w', encoding='utf-8') as f:
        f.write(code_str.strip() + "\n")
        
if not os.path.exists(os.path.join(DATA_DIR,SCRIPT,DEBUG)):
    os.mkdir(os.path.join(DATA_DIR,SCRIPT,DEBUG))
if not os.path.exists(os.path.join(DATA_DIR,SCRIPT,DEBUG,LOG)):
    os.makedirs(os.path.join(DATA_DIR,SCRIPT,DEBUG,LOG))
if not os.path.exists(os.path.join(DATA_DIR,SCRIPT,DEBUG,LOG,"DebugLogBridgeRuntime.cs")):
    code_str = '''
    using System;
using System.Net.WebSockets;
using UnityEngine;
using WebSocketSharp;
using WebSocket = WebSocketSharp.WebSocket;

public class DebugLogBridgeRuntime : MonoBehaviour
{
    private WebSocket ws;
    private const string WebSocketUrl = "ws://localhost:8765"; // Python WebSocketサーバーのURL
    private float reconnectTimer;
    private bool isConnecting;

    void Awake()
    {
        TryConnect();
        DontDestroyOnLoad(this);
    }

    void Update()
    {
        // 再接続監視
        reconnectTimer += Time.deltaTime;
        if (reconnectTimer > 5f)
        {
            reconnectTimer = 0f;
            if (ws == null || ws.ReadyState != WebSocketSharp.WebSocketState.Open)
            {
                TryConnect();
            }
        }
    }

    private void TryConnect()
    {
        if (isConnecting) return; // 接続試行中の重複防止
        isConnecting = true;

        try
        {
            // 既存の接続を閉じる
            ws?.Close();

            // 新しいWebSocketを作成
            ws = new WebSocket(WebSocketUrl);

            // イベントハンドラを設定（メインスレッドで実行）
            ws.OnOpen += (sender, e) =>
            {
                UnityEngine.Debug.Log("WebSocket connected successfully!");
            };

            ws.OnError += (sender, e) =>
            {
                UnityEngine.Debug.LogWarning($"WebSocket error: {e.Message}");
                ws = null; // 再接続をトリガー
            };

            ws.OnClose += (sender, e) =>
            {
                UnityEngine.Debug.Log($"WebSocket disconnected. Reason: {e.Reason}");
                ws = null; // 再接続をトリガー
            };

            // オプション: サーバーからのメッセージ受信（必要に応じて有効化）
            // ws.OnMessage += (sender, e) =>
            // {
            //     UnityEngine.Debug.Log($"Received message: {e.Data}");
            // };

            // 非同期接続を試行
            ws.ConnectAsync();
        }
        catch (Exception e)
        {
            UnityEngine.Debug.LogWarning($"DebugBridge WebSocket connection failed: {e.Message}");
            ws = null;
        }
        finally
        {
            isConnecting = false;
        }
    }

    public void SendLog(string message, string type)
    {
        if (ws == null || ws.ReadyState != WebSocketSharp.WebSocketState.Open)
        {
            UnityEngine.Debug.LogWarning("WebSocket not connected. Skipping send.");
            return;
        }

        var json = JsonUtility.ToJson(new LogData
        {
            message = message,
            type = type,
            time = DateTime.Now.ToString("HH:mm:ss")
        });

        try
        {
            ws.Send(json);
            UnityEngine.Debug.Log($"Sent log: [{type}] {message}");
        }
        catch (Exception e)
        {
            UnityEngine.Debug.LogWarning($"Failed to send log: {e.Message}");
            ws = null; // 再接続をトリガー
        }
    }

    [Serializable]
    private class LogData
    {
        public string message;
        public string type;
        public string time;
    }

    void OnDestroy()
    {
        if (ws != null)
        {
            ws.Close();
            ws = null;
        }
    }
}
    '''
    with open(os.path.join(DATA_DIR,SCRIPT,DEBUG,LOG,"DebugLogBridgeRuntime.cs"), 'w', encoding='utf-8') as f:
        f.write(code_str.strip() + "\n")
        

if not os.path.exists(os.path.join(DATA_DIR,SCRIPT,DEBUG,LOG,"DebugLogBridge.cs")):
    code_str = '''
using System.Diagnostics;
using UnityEngine;

/// <summary>
/// デバッグ汎用関数
/// </summary>
public static class DebugLogBridge
{
    private static DebugLogBridgeRuntime runtime;

    [Conditional("UNITY_EDITOR")]
    [Conditional("UNITY_ENABLE_CHECKS")]
    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
    private static void Init()
    {
        if (UnityEngine.Debug.isDebugBuild || Application.isEditor)
        {
            var go = new GameObject("DebugBridge");
            Object.DontDestroyOnLoad(go);
            runtime = go.AddComponent<DebugLogBridgeRuntime>();
        }
    }

    [Conditional("UNITY_EDITOR")]
    [Conditional("UNITY_ENABLE_CHECKS")]
    public static void Log(string message)
    {
        UnityEngine.Debug.Log(message);
        runtime?.SendLog(message, "Log");
    }

    [Conditional("UNITY_EDITOR")]
    [Conditional("UNITY_ENABLE_CHECKS")]
    public static void LogWarning(string message)
    {
        UnityEngine.Debug.LogWarning(message);
        runtime?.SendLog(message, "Warning");
    }

    [Conditional("UNITY_EDITOR")]
    [Conditional("UNITY_ENABLE_CHECKS")]
    public static void LogError(string message)
    {
        UnityEngine.Debug.LogError(message);
        runtime?.SendLog(message, "Error");
    }
}

    '''
    with open(os.path.join(DATA_DIR,SCRIPT,DEBUG,LOG,"DebugLogBridge.cs"), 'w', encoding='utf-8') as f:
        f.write(code_str.strip() + "\n")
        
if not os.path.exists(os.path.join(DATA_DIR,SCRIPT,"BaseSingleton.cs")):
    code_str = '''
using NUnit.Framework;
using UnityEngine;

namespace GameCore
{
    public class BaseSingleton<T> : MonoBehaviour where T : MonoBehaviour
    {
        protected static T instance;

        public static T Instance
        {
            get
            {
                if (instance == null)
                {
                    // まず、既にシーン内にあるかチェック
                    instance =  GameObject.FindAnyObjectByType<T>(FindObjectsInactive.Exclude);

                    if (instance == null)
                    {
                        // まだなければ新しく生成
                        GameObject instanceObj = new GameObject();
                        instance = instanceObj.AddComponent<T>();
                        instanceObj.name = typeof(T).Name;
                    }
                }

                return instance;
            }
        }

        public virtual void AwakeSingleton()
        {
            if (instance == null)
            {
                instance = gameObject.GetComponent<T>();
            }
        }

        public void Awake()
        {
            AwakeSingleton();
        }

    }
}


    '''
    with open(os.path.join(DATA_DIR,SCRIPT,"BaseSingleton.cs"), 'w', encoding='utf-8') as f:
        f.write(code_str.strip() + "\n")
        
    
if not os.path.exists(os.path.join(DATA_DIR,SCRIPT,"FastEnumBitFlags.cs")):
        code_str = """
using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
namespace GameCore.Utils
{
    public sealed class FastEnumBitFlags<TEnum> where TEnum : struct, Enum
    {
        private readonly ulong[] _bits;
        private readonly int _bitCount;
        private readonly int _arrayLength;

        public FastEnumBitFlags()
        {
            var values = (TEnum[])Enum.GetValues(typeof(TEnum));
            int maxValue = values.Select(v => Convert.ToInt32(v)).Max();
            _bitCount = maxValue + 1;
            if (_bitCount <= 0)
                throw new ArgumentException("Enum must contain at least one non-negative value.");

            _arrayLength = (_bitCount + 63) / 64;
            _bits = new ulong[_arrayLength];
        }


        private FastEnumBitFlags(ulong[] bits, int bitCount, int arrayLength)
        {
            _bits = bits;
            _bitCount = bitCount;
            _arrayLength = arrayLength;
        }

        #region 基本操作（従来通り）

        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        public bool IsSet(TEnum flag)
        {
            int index = Convert.ToInt32(flag);
            return index > 0 && index < _bitCount && GetBit(index);
        }

        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        public void Set(TEnum flag)
        {
            int index = Convert.ToInt32(flag);
            if (index > 0 && index < _bitCount) SetBit(index);
        }

        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        public void Clear(TEnum flag)
        {
            int index = Convert.ToInt32(flag);
            if (index > 0 && index < _bitCount) ClearBit(index);
        }

        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        public void Toggle(TEnum flag)
        {
            int index = Convert.ToInt32(flag);
            if (index >= 0 && index < _bitCount)
                FlipBit(index);
        }

        #endregion

        #region 演算付きビット操作（XOR / AND / OR）

        /// <summary>
        /// XOR 演算でビット操作
        /// flag = true  → 反転
        /// flag = false → 何もしない
        /// </summary>
        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        public void XORBit(TEnum flag, bool value)
        {
            if (!value) return;
            int index = Convert.ToInt32(flag);
            if (index > 0 && index < _bitCount)
                FlipBit(index);
        }

        /// <summary>
        /// AND 演算でビット操作
        /// flag = true  → 何もしない
        /// flag = false → クリア
        /// </summary>
        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        public void ANDBit(TEnum flag, bool value)
        {
            if (value) return;
            int index = Convert.ToInt32(flag);
            if (index > 0 && index < _bitCount)
                ClearBit(index);
        }

        /// <summary>
        /// OR 演算でビット操作
        /// flag = true  → セット
        /// flag = false → 何もしない
        /// </summary>
        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        public void ORBit(TEnum flag, bool value)
        {
            if (!value) return;
            int index = Convert.ToInt32(flag);
            if (index > 0 && index < _bitCount)
                SetBit(index);
        }

        #endregion

        #region 内部ヘルパー（インライン）

        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        private bool GetBit(int index)
        {
            int arrayIdx = index >> 6;
            int bitIdx = index & 63;
            return (_bits[arrayIdx] & (1UL << bitIdx)) != 0;
        }

        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        private void SetBit(int index)
        {
            int arrayIdx = index >> 6;
            int bitIdx = index & 63;
            _bits[arrayIdx] |= 1UL << bitIdx;
        }

        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        private void ClearBit(int index)
        {
            int arrayIdx = index >> 6;
            int bitIdx = index & 63;
            _bits[arrayIdx] &= ~(1UL << bitIdx);
        }

        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        private void FlipBit(int index)
        {
            int arrayIdx = index >> 6;
            int bitIdx = index & 63;
            _bits[arrayIdx] ^= 1UL << bitIdx;
        }

        #endregion

        #region ユーティリティ

        public void ClearAll() => Array.Clear(_bits, 0, _arrayLength);

        public void SetAll()
        {
            for (int i = 0; i < _arrayLength - 1; i++)
                _bits[i] = ulong.MaxValue;
            int rem = _bitCount & 63;
            _bits[_arrayLength - 1] = rem > 0 ? (1UL << rem) - 1 : ulong.MaxValue;
        }

        public FastEnumBitFlags<TEnum> Clone()
        {
            var clone = new ulong[_arrayLength];
            Buffer.BlockCopy(_bits, 0, clone, 0, _bits.Length * 8);
            return new FastEnumBitFlags<TEnum>(clone, _bitCount, _arrayLength);
        }

        public IEnumerable<TEnum> GetSetFlags()
        {
            for (int i = 1; i < _bitCount; i++)
            {
                if (GetBit(i) && Enum.IsDefined(typeof(TEnum), i))
                    yield return (TEnum)(object)i;
            }
        }

        #endregion
    }
}
        """
        with open(os.path.join(DATA_DIR,SCRIPT,"FastEnumBitFlags.cs"),"w",encoding="utf-8") as f:
            f.write(code_str)
            

#js版　-BinaryReader-
if not os.path.exists(os.path.join(DATA_DIR,SCRIPT,"BinaryReader.js")):
    code = """
export class BinaryReader {
    constructor(buffer) {
        this._buffer = buffer;   // ArrayBuffer 推奨
        this._offset = 0;
    }

    readInt32() {
        const value = new Int32Array(this._buffer, this._offset, 1)[0];
        this._offset += 4;
        return value;
    }
    
    readInt16() {
        const value = new Int16Array(this._buffer, this._offset, 1)[0];
        this._offset += 2;
        return value;
    }
    
    readInt64() {
        const value = new BigInt64Array(this._buffer, this._offset, 1)[0];
        this._offset += 8;
        return value;

    }

    readFloat32() {
        const value = new Float32Array(this._buffer, this._offset, 1)[0];
        this._offset += 4;
        return value;
    }

    readBoolean() {
        const value = new Uint8Array(this._buffer, this._offset, 1)[0] !== 0;
        this._offset += 1;
        return value;
    }

    readString() {
        const len = this.readInt32();
        if (len <= 0) return "";
        const bytes = new Uint8Array(this._buffer, this._offset, len);
        this._offset += len;
        return new TextDecoder("utf-8").decode(bytes);
    }

    readDouble() {
        const value = new Float64Array(this._buffer, this._offset, 1)[0];
        this._offset += 8;
        return value;
    }

    readUint() {
        const value = new Uint32Array(this._buffer, this._offset, 1)[0];
        this._offset += 4;
        return value;
    }

    readVector2() {
        return {
            x: this.readFloat32(),
            y: this.readFloat32()
        };
    }

    readVector3() {
        return {
            x: this.readFloat32(),
            y: this.readFloat32(),
            z: this.readFloat32()
        };
    }
    
    readChar()
    {
        const value = new Uint16Array(this._buffer, this._offset, 1)[0];
        this._offset += 2;
        return value;

    }
}
    """
    with open(os.path.join(DATA_DIR,SCRIPT,"BinaryReader.js"), 'w', encoding='utf-8') as f:
        f.write(code)


#Pythonのワークスペース場所作成
if not os.path.exists(os.path.join(DATA_DIR,SCRIPT,PYTHON)):
    os.mkdir(os.path.join(DATA_DIR,SCRIPT,PYTHON))

if not os.path.exists(os.path.join(DATA_DIR,SCRIPT,PYTHON,"app.py")):
    code = """
import os
import sys

if getattr(sys, 'frozen', False):
    # exe実行時
    # 一つ前
    base_dir = os.path.abspath(os.path.join(sys.executable, ".."))
else:
    # 開発時
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

if base_dir not in sys.path:
    sys.path.append(base_dir)

isDbg = True
# 実行可能ファイルのディレクトリを取得（PyInstaller対応）
if getattr(sys, 'frozen', False):
    # PyInstallerでビルドされた場合
    BASE_DIR = os.path.dirname(sys.executable)
    isDbg = False
else:
    # デバッグ環境（VS Codeなど）
    # main-support/ の1つ上のディレクトリ（project/）を基準にする
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    
def main():
    pass

if __name__ == "__main__":
    main()
    """
    
    with open(os.path.join(DATA_DIR,SCRIPT,PYTHON,"app.py"), 'w', encoding='utf-8') as f:
        f.write(code + "\n")
        
if not os.path.exists(os.path.join(DATA_DIR,SCRIPT,PYTHON,"myproject.code-workspace")):
    code = """
{
  "folders": [
    {
      "path": "."
    }
  ]
}
"""
    with open(os.path.join(DATA_DIR,SCRIPT,PYTHON,"myproject.code-workspace"), 'w', encoding='utf-8') as f:
        f.write(code.strip() + "\n")
        
if not os.path.exists(os.path.join(DATA_DIR,SCRIPT,PYTHON,"vscode.bat")):
    code = """
@echo off
cd /d "%~dp0"
code "%~dp0myproject.code-workspace"
exit
    """
    with open(os.path.join(DATA_DIR,SCRIPT,PYTHON,"vscode.bat"), 'w', encoding='utf-8') as f:
        f.write(code.strip() + "\n")


if not os.path.exists(os.path.join(DATA_DIR,SCRIPT,OBJECTPOOL)):
    os.mkdir(os.path.join(DATA_DIR,SCRIPT,OBJECTPOOL))
            



        


# ============================================================
# ScenarioRole / Texture / GameObject / Material / Sound API
# ============================================================

    
    
##--------------------------------------------------
# Scenario
def generate_scenario_role_factory():
    list_path = os.path.join(DATA_DIR, scenario.SCENARIO_ROLE, 'scenario_role_list.json')
    roles = []
    if os.path.exists(list_path):
        with open(list_path, 'r', encoding='utf-8') as f:
            roles = json.load(f)

    # Generate ScenarioRoleID enum
    enum_content = """using System;

namespace GameCore.Scenario {
    public enum ScenarioRoleID {
        None = 0,
"""
    for role in roles:
        enum_content += f"        {role['name']} = {role['id']},\n"
    enum_content += """        Max
    }
}
"""
    with open(os.path.join(DATA_DIR, scenario.SCENARIO_ROLE, "ScenarioRoleID.cs"), 'w', encoding='utf-8') as f:
        f.write(enum_content)

    # Generate ScenarioRoleFactory class
    factory_content = """
using System;
using System.Collections.Generic;
using System.Threading;
using Cysharp.Threading.Tasks;

namespace GameCore.Scenario {
    public static class ScenarioRoleFactory {
        public static BaseScenarioRoleData CreateRoleData(ScenarioRoleID id) {
            switch (id) {
"""
    for role in roles:
        factory_content += f"""                case ScenarioRoleID.{role['name']}:
                    return new {role['name']}RoleData();
"""
    factory_content += """                default:
                    return null;
            }
        }
        
        public static BaseOrigintScenarioRoleAction CreateNewRoleAction(BaseScenarioRoleData data) {
            if (data == null) return null;
            switch (data.RoleID) {
"""
    for role in roles:
        factory_content += f"""                case ScenarioRoleID.{role['name']}:
                    return new {role['name']}RoleAction(data as {role['name']}RoleData);
"""
    factory_content += """                default:
                    return null;
            }
        }
        
        public static void SetData(BaseOrigintScenarioRoleAction action,BaseScenarioRoleData data) {s
            if (data == null) return;
            switch (data.RoleID) {
"""
    for role in roles:
        factory_content += f"""                case ScenarioRoleID.{role['name']}:
                    (action as {role['name']}RoleAction).SetRoleData(data as {role['name']}RoleData);
                    break;
"""
    factory_content += """                default:
                    return;
            }
        }
        
        // 役職ごとのプール構造：
        // freePool: 未使用インスタンスを O(1) で出し入れする Stack
        // activeSet: 解放時に正しいアクションか確認、あるいは線形探索を避けるための管理
        private class RolePool {
            public readonly Stack<BaseOrigintScenarioRoleAction> FreeStack = new Stack<BaseOrigintScenarioRoleAction>();
            // どのアクションが使われているかをO(1)で判定・管理したい場合のセット
            public readonly HashSet<BaseOrigintScenarioRoleAction> ActiveSet = new HashSet<BaseOrigintScenarioRoleAction>();
        }

        private static readonly Dictionary<ScenarioRoleID, RolePool> actionPool
            = new Dictionary<ScenarioRoleID, RolePool>();

        private static RolePool GetOrCreatePool(ScenarioRoleID id) {
            if (!actionPool.TryGetValue(id, out var pool)) {
                pool = new RolePool();
                actionPool[id] = pool;
            }
            return pool;
        }

        public static void WarmUpPool(BaseScenarioRoleData data,int count) {
            var pool = GetOrCreatePool(data.RoleID);
            int currentTotal = pool.FreeStack.Count + pool.ActiveSet.Count;
            int needed = count - currentTotal;
            
            for (int i = 0; i < needed; i++) {
                var newAction = CreateNewRoleAction(data);
                if (newAction != null) {
                    pool.FreeStack.Push(newAction);
                }
            }
        }

        public static async UniTask<BaseOrigintScenarioRoleAction> CreateRoleActionAsync(BaseScenarioRoleData data, CancellationToken ct = default) {
            if (data == null) return null;
            var pool = GetOrCreatePool(data.RoleID);

            BaseOrigintScenarioRoleAction action;

            if (pool.FreeStack.Count > 0) {
                action = pool.FreeStack.Pop();
                SetData(action,data);
            } else {
                action = CreateNewRoleAction(data);
                if (action == null) return null;
            }

            action.Reset();

            try {
                // キャンセルトークンを紐付けて非同期リセットを実行
                await action.ResetAsync().AttachExternalCancellation(ct);
            } catch (System.OperationCanceledException) {
                // 万が一キャンセルされた場合は、プールからポップしたアクションを再度スタックに戻すか、
                // もし新規生成したものであれば破棄・未使用に戻すなどの配慮が必要です
                pool.FreeStack.Push(action);
                throw;
            }

            pool.ActiveSet.Add(action);
            return action;
        }

        public static void ReleaseRoleAction(ScenarioRoleID id, BaseOrigintScenarioRoleAction action) {
            if (action == null) return;
            if (!actionPool.TryGetValue(id, out var pool)) return;

            // O(1) でアクティブセットから外し、未使用スタックに戻す
            if (pool.ActiveSet.Remove(action)) {
                pool.FreeStack.Push(action);
            }
        }

        public static void AllClear() {
            actionPool.Clear();
        }
    }
}
"""
    with open(os.path.join(DATA_DIR, scenario.SCENARIO_ROLE, "ScenarioRoleFactory.cs"), 'w', encoding='utf-8') as f:
        f.write(factory_content)

@app.route('/api/scenario-role', methods=['GET', 'POST', 'PATCH'])
def handle_scenario_role_list():
    list_path = os.path.join(DATA_DIR, scenario.SCENARIO_ROLE, 'scenario_role_list.json')
    if request.method == 'GET':
        if os.path.exists(list_path):
            with open(list_path, 'r', encoding='utf-8') as f:
                return jsonify(json.load(f))
        with open(list_path, 'w', encoding='utf-8') as f:
            json.dump([], f)
        return jsonify([])
    elif request.method == 'POST':
        data = request.json
        name = data.get('name')
        description = data.get('description', '')
        branchType = data.get('branchType', 'General')
        if not name:
            return jsonify({"error": "Name is required"}), 400
        if os.path.exists(list_path):
            with open(list_path, 'r+', encoding='utf-8') as f:
                roles = json.load(f)
                max_id = max([r['id'] for r in roles], default=0) + 1
                new_role = {"id": max_id, "name": name, "description": description, "branchType": branchType}
                roles.append(new_role)
                f.seek(0)
                json.dump(roles, f)
        else:
            new_role = {"id": 1, "name": name, "description": description, "branchType": branchType}
            with open(list_path, 'w', encoding='utf-8') as f:
                json.dump([new_role], f)
        role_dir = os.path.join(DATA_DIR, scenario.SCENARIO_ROLE, name)
        os.makedirs(role_dir, exist_ok=True)
        with open(os.path.join(role_dir, f"{name}.json"), 'w', encoding='utf-8') as f:
            json.dump([], f)
        generate_scenario_role_factory()  # Generate enum and factory
        return jsonify({"message": "Role created", "data": new_role})
    elif request.method == 'PATCH':  # Used for delete
        data = request.json
        name = data.get('name')
        if not name:
            return jsonify({"error": "Name is required"}), 400
        deleted_entry = None
        if os.path.exists(list_path):
            with open(list_path, 'r+', encoding='utf-8') as f:
                roles = json.load(f)
                deleted_entry = next((r for r in roles if r.get('name') == name), None)
                roles = [r for r in roles if r['name'] != name]
                f.seek(0)
                f.truncate()
                json.dump(roles, f)
        role_dir = os.path.join(DATA_DIR, scenario.SCENARIO_ROLE, name)
        if os.path.exists(role_dir):
            trash.move_to_trash('scenario_role', name, role_dir, list_entry=deleted_entry)
        generate_scenario_role_factory()  # Regenerate enum and factory
        return jsonify({"message": "Role deleted"})

@app.route('/api/scenario-role/<name>', methods=['GET', 'POST', 'DELETE'])
def handle_scenario_role_detail(name):
    role_dir = os.path.join(DATA_DIR, scenario.SCENARIO_ROLE, name)
    data_path = os.path.join(role_dir, f"{name}.json")
    if request.method == 'GET':
        if os.path.exists(data_path):
            with open(data_path, 'r', encoding='utf-8') as f:
                return jsonify(json.load(f))
        return jsonify([])
    elif request.method == 'POST':
        data = request.json
        with open(data_path, 'w', encoding='utf-8') as f:
            json.dump(data, f)
        generate_scenario_role_factory()
        return jsonify({"message": "Data saved"})
    elif request.method == 'DELETE':
        list_path = os.path.join(DATA_DIR, scenario.SCENARIO_ROLE, 'scenario_role_list.json')
        deleted_entry = None
        if os.path.exists(list_path):
            with open(list_path, 'r+', encoding='utf-8') as f:
                roles = json.load(f)
                deleted_entry = next((r for r in roles if r.get('name') == name), None)
                roles = [r for r in roles if r['name'] != name]
                f.seek(0)
                f.truncate()
                json.dump(roles, f)
        if os.path.exists(role_dir):
            trash.move_to_trash('scenario_role', name, role_dir, list_entry=deleted_entry)
        return jsonify({"message": "Role deleted"})

@app.route('/api/generate-scenario-role/<name>', methods=['POST'])
def generate_scenario_role_cs(name):
    role_dir = os.path.join(DATA_DIR, scenario.SCENARIO_ROLE, name)
    data_path = os.path.join(role_dir, f"{name}.json")
    
    basic_types, unity_types, enum_list, class_list, class_data_id_list,enum_data,class_data_id,class_data = get_type_lists()
    custom_type_info = build_custom_type_info(enum_list, class_list, class_data_id_list)  # ← 追加
    if not os.path.exists(data_path):
        return jsonify({"error": "Data not found"}), 404
    with open(data_path, 'r', encoding='utf-8') as f:
        json_data = json.load(f)
    data = json_data.get('data', [])
    branch_type = json_data.get('branchType', 'General')
    
    cs_data_path = os.path.join(role_dir, f"{name}RoleData.cs")
    with open(cs_data_path, 'w', encoding='utf-8') as f:
        f.write("using System;\nusing System.IO;\nusing System.Collections.Generic;\nusing UnityEngine;\n")
        f.write("namespace GameCore.Scenario \n{\n")
        f.write(f"   public class {name}RoleData : BaseScenarioRoleData \n    {{\n")
        read_codes = []
        for item in data:
            field_data = generate_csharp_field(
                item, enum_list, class_list, unity_types, basic_types, class_data_id_list,
                custom_type_info=custom_type_info,  # ← 追加
            )
            f.write(field_data['field'])
            read_codes.append(field_data['read'])
        f.write(f"\n        public {name}RoleData() : base() {{  RoleID = ScenarioRoleID.{name};  }}\n       public override void ReadBinary(BinaryReader reader)        {{\n")
        for read_code in read_codes:
            f.write(read_code)
        f.write("        }\n")
        f.write("    }\n}\n")
    
  
    base_action_class = "BaseScenarioRoleBranchAction" if branch_type == 'Branch' else "BaseScenarioRoleAction"
    # Generate Action class inheriting from BaseScenarioRoleAction
    cs_action_content = f"""
using Cysharp.Threading.Tasks;
using System;
using System.Threading;
using UnityEngine;

namespace GameCore.Scenario {{
    public class {name}RoleAction : {base_action_class}<{name}RoleData> {{
        public {name}RoleAction({name}RoleData roleData) : base(roleData) {{
        }}

        public override void OnInitialize(ScenarioExecuteData executeData, CancellationTokenSource ct) {{
            // Custom initialization logic
            base.OnInitialize(executeData,ct);
            IsEnter = true;
        }}
        
        public override void OnOneExecute(ScenarioExecuteData executeData, CancellationTokenSource ct) {{
            IsOneUpdate = true;
        }}

        public override void OnExecute(ScenarioExecuteData executeData, CancellationTokenSource ct) {{
            // Custom action logic using RoleData
            Debug.Log($"Executing {name} with RoleID: {{RoleData.RoleID}}");
            IsUpdate = true;
        }}

        public override void OnFinalize(ScenarioExecuteData executeData, CancellationTokenSource ct) {{
            // Custom cleanup logic
            IsFinish = true;
        }}
        
        public override async UniTask OnInitializeAsync(ScenarioExecuteData executeData, CancellationTokenSource ct)
        {{

            await base.OnInitializeAsync(executeData, ct);
            IsEnterAsync = true;
        }}
        public override async UniTask OnOneExecuteAsync(ScenarioExecuteData executeData, CancellationTokenSource ct)
        {{
            // Implement action logic here
            await UniTask.CompletedTask;
            IsOneUpdateAsync = true;
        }}
        public override async UniTask OnExecuteAsync(ScenarioExecuteData executeData, CancellationTokenSource ct)
        {{
            // Implement action logic here
            await UniTask.CompletedTask;
            IsUpdateAsync = true;
        }}
        public override async UniTask OnFinalizeAsync(ScenarioExecuteData executeData, CancellationTokenSource ct)
        {{
            await UniTask.CompletedTask;
            IsFinishAsync = true;
        }}
    }}
}}
"""
    
    # Write both files
    cs_action_path = os.path.join(role_dir, f"{name}RoleAction.cs")

    if not os.path.exists(cs_action_path):
        with open(cs_action_path, 'w', encoding='utf-8') as f:
            f.write(cs_action_content)
    
    return jsonify({"message": "C# data and action classes generated"})

#============================================================================
#ScenarioEvent管理
@app.route('/api/scenario-event', methods=['GET', 'POST'])
def handle_scenario_event_list():
    list_path = os.path.join(DATA_DIR, scenario.SCENARIO_EVENT, 'scenario_event_list.json')
    if request.method == 'GET':
        if os.path.exists(list_path):
            with open(list_path, 'r', encoding='utf-8') as f:
                return jsonify(json.load(f))
        return jsonify([])
    elif request.method == 'POST':
        data = request.json
        id = data.get('id')
        name = data.get('name')
        description = data.get('description', '')
        if not id or not name:
            return jsonify({"error": "ID and Name are required"}), 400
        if os.path.exists(list_path):
            with open(list_path, 'r+', encoding='utf-8') as f:
                events = json.load(f)
                if any(e['id'] == id for e in events):
                    return jsonify({"error": "ID already exists"}), 400
                new_event = {"id": id, "name": name, "description": description, "subEvents": []}
                events.append(new_event)
                f.seek(0)
                f.truncate()
                json.dump(events, f)
        else:
            new_event = {"id": id, "name": name, "description": description, "subEvents": []}
            with open(list_path, 'w', encoding='utf-8') as f:
                json.dump([new_event], f)
        event_dir = os.path.join(DATA_DIR, scenario.SCENARIO_EVENT, id)
        os.makedirs(event_dir, exist_ok=True)
        with open(os.path.join(event_dir, f"{id}.json"), 'w', encoding='utf-8') as f:
            json.dump(new_event, f)
        # ClassDataID側のScenario_{親}/{サブ}を最新の構成へ同期(項目6)
        with open(list_path, 'r', encoding='utf-8') as f:
            scenario.sync_all_scenario_class_data(json.load(f))
        return jsonify({"message": "Event created"})

@app.route('/api/scenario-event/<id>', methods=['PATCH', 'DELETE'])
def handle_scenario_event(id):
    list_path = os.path.join(DATA_DIR, scenario.SCENARIO_EVENT, 'scenario_event_list.json')
    event_dir = os.path.join(DATA_DIR, scenario.SCENARIO_EVENT, id)
    event_path = os.path.join(event_dir, f"{id}.json")
    if request.method == 'PATCH':
        data = request.json
        name = data.get('name')
        description = data.get('description')
        if not os.path.exists(list_path):
            return jsonify({"error": "Event not found"}), 404
        with open(list_path, 'r+', encoding='utf-8') as f:
            events = json.load(f)
            for event in events:
                if event['id'] == id:
                    if name is not None:
                        event['name'] = name
                    if description is not None:
                        event['description'] = description
                    f.seek(0)
                    f.truncate()
                    json.dump(events, f)
                    with open(event_path, 'w', encoding='utf-8') as ef:
                        json.dump(event, ef)
                    return jsonify({"message": "Event updated"})
        return jsonify({"error": "Event not found"}), 404
    elif request.method == 'DELETE':
        if os.path.exists(list_path):
            with open(list_path, 'r+', encoding='utf-8') as f:
                events = json.load(f)
                events = [e for e in events if e['id'] != id]
                f.seek(0)
                f.truncate()
                json.dump(events, f)
            # ClassDataID側のScenario_{親}/{サブ}を最新の構成へ同期(項目6)
            scenario.sync_all_scenario_class_data(events)
        if os.path.exists(event_dir):
            shutil.rmtree(event_dir)
        return jsonify({"message": "Event deleted"})

@app.route('/api/scenario-event/<id>/sub', methods=['POST'])
def add_sub_event(id):
    data = request.json
    name = data.get('name')
    description = data.get('description', '')
    if not name:
        return jsonify({"error": "Name is required"}), 400
    list_path = os.path.join(DATA_DIR, scenario.SCENARIO_EVENT, 'scenario_event_list.json')
    event_path = os.path.join(DATA_DIR, scenario.SCENARIO_EVENT, id, f"{id}.json")
    if os.path.exists(list_path):
        with open(list_path, 'r+', encoding='utf-8') as f:
            events = json.load(f)
            for event in events:
                if event['id'] == id:
                    max_sub_id = max([s['subId'] for s in event.get('subEvents', [])], default=0) + 1
                    new_sub = {"subId": max_sub_id, "name": name, "description": description}
                    event['subEvents'].append(new_sub)
                    f.seek(0)
                    f.truncate()
                    json.dump(events, f)
                    with open(event_path, 'r+', encoding='utf-8') as ef:
                        eventData = json.load(ef)
                        for subEv in eventData["subEvents"]:
                            if subEv['name'] == name:
                                return jsonify({"message": "すでに存在しています", "subId": max_sub_id})
                        eventData["subEvents"].append(new_sub)
                        ef.seek(0)
                        ef.truncate()
                        json.dump(eventData, ef)
                    # ClassDataID側のScenario_{親}/{サブ}を最新の構成へ同期(項目6)
                    scenario.sync_all_scenario_class_data(events)
                    return jsonify({"message": "Sub event added", "subId": max_sub_id})
        return jsonify({"error": "Event not found"}), 404
    return jsonify({"error": "Event not found"}), 404

@app.route('/api/scenario-event/<id>/sub/<int:subId>', methods=['PATCH', 'DELETE'])
def handle_sub_event(id, subId):
    list_path = os.path.join(DATA_DIR, scenario.SCENARIO_EVENT, 'scenario_event_list.json')
    event_path = os.path.join(DATA_DIR, scenario.SCENARIO_EVENT, id, f"{id}.json")
    if request.method == 'PATCH':
        data = request.json
        name = data.get('name')
        description = data.get('description')
        if not os.path.exists(list_path):
            return jsonify({"error": "Event not found"}), 404
        with open(list_path, 'r+', encoding='utf-8') as f:
            events = json.load(f)
            for event in events:
                if event['id'] == id:
                    for sub in event['subEvents']:
                        if sub['subId'] == subId:
                            if name is not None:
                                sub['name'] = name
                            if description is not None:
                                sub['description'] = description
                            f.seek(0)
                            f.truncate()
                            json.dump(events, f)
                            with open(event_path, 'w', encoding='utf-8') as ef:
                                json.dump(event, ef)
                            # ClassDataID側のScenario_{親}/{サブ}を最新の構成へ同期(項目6)
                            scenario.sync_all_scenario_class_data(events)
                            return jsonify({"message": "Sub event updated"})
            return jsonify({"error": "Sub event not found"}), 404
    elif request.method == 'DELETE':
        if os.path.exists(list_path):
            with open(list_path, 'r+', encoding='utf-8') as f:
                events = json.load(f)
                for event in events:
                    if event['id'] == id:
                        event['subEvents'] = [s for s in event['subEvents'] if s['subId'] != subId]
                        f.seek(0)
                        f.truncate()
                        json.dump(events, f)
                        with open(event_path, 'w', encoding='utf-8') as ef:
                            json.dump(event, ef)
                        # ClassDataID側のScenario_{親}/{サブ}を最新の構成へ同期(項目6)
                        scenario.sync_all_scenario_class_data(events)
                        return jsonify({"message": "Sub event deleted"})
        return jsonify({"error": "Event or sub event not found"}), 404


# ============================================================
# コピー機能(項目5)
# ============================================================
@app.route('/api/scenario-event/<id>/copy', methods=['POST'])
def copy_scenario_event(id):
    """親イベントをコピーする。copySubs(デフォルトTrue)でサブイベントも
    まとめてコピーするかを選べる。IDは自動採番、名前は "{元の名前} のコピー"。
    """
    data = request.json or {}
    copy_subs = data.get('copySubs', True)

    list_path = os.path.join(DATA_DIR, scenario.SCENARIO_EVENT, 'scenario_event_list.json')
    if not os.path.exists(list_path):
        return jsonify({"error": "Event not found"}), 404

    with open(list_path, 'r+', encoding='utf-8') as f:
        events = json.load(f)
        source = next((e for e in events if e['id'] == id), None)
        if not source:
            return jsonify({"error": "Event not found"}), 404

        numeric_ids = [int(e['id']) for e in events if str(e['id']).isdigit()]
        new_id = str(max(numeric_ids, default=0) + 1)

        new_sub_events = []
        if copy_subs:
            for i, sub in enumerate(source.get('subEvents', []), start=1):
                new_sub_events.append({
                    "subId": i,
                    "name": sub['name'],
                    "description": sub.get('description', ''),
                })

        new_event = {
            "id": new_id,
            "name": f"{source['name']} のコピー",
            "description": source.get('description', ''),
            "subEvents": new_sub_events,
        }
        events.append(new_event)
        f.seek(0)
        f.truncate()
        json.dump(events, f)

    # 個別ファイル(遷移図データ含む)も作成
    src_event_dir = os.path.join(DATA_DIR, scenario.SCENARIO_EVENT, id)
    src_event_path = os.path.join(src_event_dir, f"{id}.json")
    new_event_dir = os.path.join(DATA_DIR, scenario.SCENARIO_EVENT, new_id)
    os.makedirs(new_event_dir, exist_ok=True)
    new_event_path = os.path.join(new_event_dir, f"{new_id}.json")

    if copy_subs and os.path.exists(src_event_path):
        with open(src_event_path, 'r', encoding='utf-8') as f:
            src_data = json.load(f)
        src_subgroups = src_data.get('subgroups', {})
        new_subgroups = {}
        for old_sub, new_sub in zip(source.get('subEvents', []), new_sub_events):
            old_sub_id_str = str(old_sub['subId'])
            if old_sub_id_str in src_subgroups:
                # 遷移図データ(nodes/edges、サブグループ含む)をそのままコピー
                new_subgroups[str(new_sub['subId'])] = copy.deepcopy(src_subgroups[old_sub_id_str])
        new_event = {**new_event, "subgroups": new_subgroups}
    with open(new_event_path, 'w', encoding='utf-8') as f:
        json.dump(new_event, f)

    # ClassDataID側のScenario_{親}/{サブ}を最新の構成へ同期(項目6)
    scenario.sync_all_scenario_class_data(events)

    return jsonify({"message": "イベントをコピーしました", "id": new_id})


@app.route('/api/scenario-event/<id>/sub/<int:subId>/copy', methods=['POST'])
def copy_sub_event(id, subId):
    """サブイベントをコピーする。targetEventId で別の親/同じ親どちらへも
    コピーできる(省略時は同じ親へコピー)。"""
    data = request.json or {}
    target_event_id = data.get('targetEventId', id)

    list_path = os.path.join(DATA_DIR, scenario.SCENARIO_EVENT, 'scenario_event_list.json')
    if not os.path.exists(list_path):
        return jsonify({"error": "Event not found"}), 404

    with open(list_path, 'r+', encoding='utf-8') as f:
        events = json.load(f)
        source_event = next((e for e in events if e['id'] == id), None)
        if not source_event:
            return jsonify({"error": "Event not found"}), 404
        source_sub = next((s for s in source_event.get('subEvents', []) if s['subId'] == subId), None)
        if not source_sub:
            return jsonify({"error": "Sub event not found"}), 404

        target_event = next((e for e in events if e['id'] == target_event_id), None)
        if not target_event:
            return jsonify({"error": "Copy target event not found"}), 404

        max_sub_id = max([s['subId'] for s in target_event.get('subEvents', [])], default=0) + 1
        new_sub = {
            "subId": max_sub_id,
            "name": source_sub['name'] if target_event_id != id else f"{source_sub['name']} のコピー",
            "description": source_sub.get('description', ''),
        }
        target_event['subEvents'].append(new_sub)
        f.seek(0)
        f.truncate()
        json.dump(events, f)

    # 遷移図データ(nodes/edges)もコピー
    src_event_path = os.path.join(DATA_DIR, scenario.SCENARIO_EVENT, id, f"{id}.json")
    target_event_dir = os.path.join(DATA_DIR, scenario.SCENARIO_EVENT, target_event_id)
    os.makedirs(target_event_dir, exist_ok=True)
    target_event_path = os.path.join(target_event_dir, f"{target_event_id}.json")

    src_subgroup_data = {'nodes': [], 'edges': []}
    if os.path.exists(src_event_path):
        with open(src_event_path, 'r', encoding='utf-8') as f:
            src_data = json.load(f)
        src_subgroup_data = src_data.get('subgroups', {}).get(str(subId), {'nodes': [], 'edges': []})

    target_data = {}
    if os.path.exists(target_event_path):
        with open(target_event_path, 'r', encoding='utf-8') as f:
            target_data = json.load(f)
    target_data.setdefault('subgroups', {})[str(max_sub_id)] = copy.deepcopy(src_subgroup_data)
    with open(target_event_path, 'w', encoding='utf-8') as f:
        json.dump(target_data, f)

    # ClassDataID側のScenario_{親}/{サブ}を最新の構成へ同期(項目6)
    scenario.sync_all_scenario_class_data(events)

    return jsonify({"message": "サブイベントをコピーしました", "subId": max_sub_id, "targetEventId": target_event_id})


# Transition管理
# 既存のエンドポイント（省略された部分は前のコードと同じ）
@app.route('/api/scenario-event/<eventId>/sub/<subId>/transition', methods=['GET', 'POST'])
def handle_transition(eventId, subId):
    app.logger.debug(f"Received eventId: {eventId}, subId: {subId}")
    if not eventId or eventId == 'undefined' or not subId or subId == 'undefined':
        app.logger.error(f"Invalid parameters: eventId={eventId}, subId={subId}")
        return jsonify({'error': 'Invalid eventId or subId'}), 400
    file_path = os.path.join(DATA_DIR, scenario.SCENARIO_EVENT, eventId, f"{eventId}.json")
    if request.method == 'GET':
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return jsonify(data.get('subgroups', {}).get(subId, {'nodes': [], 'edges': []}))
            return jsonify({'nodes': [], 'edges': []})
        except Exception as e:
            app.logger.error(f"Error reading {file_path}: {str(e)}")
            return jsonify({'error': str(e)}), 500
    else:  # POST
        try:
            data = request.get_json()
            current_data = {}
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    current_data = json.load(f)
            # 物語設定(storySetting)など、遷移グラフ(nodes/edges)以外の
            # キーが既存のsubgroups[subId]に同居している場合があるため、
            # 丸ごと置き換えず非破壊マージする（このAPIは遷移グラフの
            # 保存専用であり、物語設定を書き潰さないようにするため）。
            current_data.setdefault('subgroups', {})
            existing_sub = current_data['subgroups'].get(subId, {})
            merged_sub = dict(existing_sub)
            merged_sub.update(data)
            current_data['subgroups'][subId] = merged_sub
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(current_data, f, ensure_ascii=False, indent=2)
            return jsonify({'message': 'Transition saved'})
        except Exception as e:
            app.logger.error(f"Error saving {file_path}: {str(e)}")
            return jsonify({'error': str(e)}), 500

@app.route('/api/scenario-event/<eventId>/sub/<subId>/transition/<parentId>/subgroup', methods=['GET', 'POST'])
def handle_subgroup(eventId, subId, parentId):
    app.logger.debug(f"Subgroup request: eventId={eventId}, subId={subId}, parentId={parentId}")
    if not eventId or eventId == 'undefined' or not subId or subId == 'undefined' or not parentId:
        app.logger.error(f"Invalid parameters: eventId={eventId}, subId={subId}, parentId={parentId}")
        return jsonify({'error': 'Invalid parameters'}), 400
    file_path = os.path.join(DATA_DIR, scenario.SCENARIO_EVENT, eventId, f"{eventId}.json")
    if request.method == 'GET':
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                subgroups = data.get('subgroups', {}).get(subId, {}).get('nodes', [])
                for node in subgroups:
                    if node['id'] == parentId:
                        return jsonify(node['data'].get('subgroups', {}).get(parentId, {'nodes': [], 'edges': []}))
                return jsonify({'nodes': [], 'edges': []})
            return jsonify({'nodes': [], 'edges': []})
        except Exception as e:
            app.logger.error(f"Error reading {file_path}: {str(e)}")
            return jsonify({'error': str(e)}), 500
    else:  # POST
        try:
            data = request.get_json()
            current_data = {}
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    current_data = json.load(f)
            subgroups = current_data.get('subgroups', {}).get(subId, {}).get('nodes', [])
            updated_nodes = subgroups
            for node in updated_nodes:
                if node['id'] == parentId:
                    node['data']['subgroups'] = node['data'].get('subgroups', {})
                    node['data']['subgroups'][parentId] = data
            current_data.setdefault('subgroups', {}).setdefault(subId, {})['nodes'] = updated_nodes
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(current_data, f, ensure_ascii=False, indent=2)
            return jsonify({'message': 'Subgroup saved'})
        except Exception as e:
            app.logger.error(f"Error saving {file_path}: {str(e)}")
            return jsonify({'error': str(e)}), 500

@app.route('/api/scenario-event/<eventId>/sub/<int:subId>/transition/<nodeId>/role', methods=['POST'])
def add_role(eventId, subId, nodeId):
    try:
        data = request.get_json()
        file_path = os.path.join(DATA_DIR, scenario.SCENARIO_EVENT, eventId, f"{eventId}.json")
        current_data = {}
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                current_data = json.load(f)
        subgroups = current_data.get('subgroups', {}).get(subId, {}).get('nodes', [])
        for node in subgroups:
            if node['id'] == nodeId:
                node['data']['roles'] = node['data'].get('roles', []) + [{
                    'id': data['roleId'],
                    'name': data['name'],
                    'branchType': data['branchType'],
                    'data': []
                }]
                break
            if node['data'].get('subgroups', {}).get(nodeId):
                node['data']['subgroups'][nodeId]['nodes'][0]['data']['roles'] = (
                    node['data']['subgroups'][nodeId]['nodes'][0]['data'].get('roles', []) + [{
                        'id': data['roleId'],
                        'name': data['name'],
                        'branchType': data['branchType'],
                        'data': []
                    }]
                )
                break
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(current_data, f, ensure_ascii=False, indent=2)
        return jsonify({'message': 'Role added'})
    except Exception as e:
        app.logger.error(f"Error adding role: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/scenario-role', methods=['GET', 'POST'])
def handle_roles():
    roles_path = os.path.join(DATA_DIR, 'scenario_role.json')
    if request.method == 'GET':
        try:
            if os.path.exists(roles_path):
                with open(roles_path, 'r', encoding='utf-8') as f:
                    return jsonify(json.load(f))
            return jsonify([])
        except Exception as e:
            app.logger.error(f"Error reading roles {roles_path}: {str(e)}")
            return jsonify({"error": "Failed to read roles"}), 500
    elif request.method == 'POST':
        try:
            data = request.json
            role_id = data.get('id')
            name = data.get('name')
            description = data.get('description', '')
            actions = data.get('actions', [])
            if not role_id or not name:
                return jsonify({"error": "ID and name are required"}), 400
            roles = []
            if os.path.exists(roles_path):
                with open(roles_path, 'r', encoding='utf-8') as f:
                    roles = json.load(f)
            if any(r['id'] == role_id for r in roles):
                return jsonify({"error": "Role ID already exists"}), 400
            roles.append({"id": role_id, "name": name, "description": description, "actions": actions})
            with open(roles_path, 'w', encoding='utf-8') as f:
                json.dump(roles, f, ensure_ascii=False, indent=2)
            return jsonify({"message": "Role added", "data": roles})
        except Exception as e:
            app.logger.error(f"Error adding role to {roles_path}: {str(e)}")
            return jsonify({"error": "Failed to add role"}), 500

@app.route('/api/scenario-role/<roleId>', methods=['PATCH', 'DELETE'])
def handle_role(roleId):
    roles_path = os.path.join(DATA_DIR, 'scenario_role.json')
    try:
        if not os.path.exists(roles_path):
            return jsonify({"error": "No roles found"}), 404
        with open(roles_path, 'r', encoding='utf-8') as f:
            roles = json.load(f)
        if request.method == 'PATCH':
            data = request.json
            for role in roles:
                if role['id'] == roleId:
                    role.update({
                        "name": data.get('name', role['name']),
                        "description": data.get('description', role['description']),
                        "actions": data.get('actions', role['actions'])
                    })
                    with open(roles_path, 'w', encoding='utf-8') as f:
                        json.dump(roles, f, ensure_ascii=False, indent=2)
                    return jsonify({"message": "Role updated", "data": roles})
            return jsonify({"error": "Role not found"}), 404
        elif request.method == 'DELETE':
            roles = [role for role in roles if role['id'] != roleId]
            with open(roles_path, 'w', encoding='utf-8') as f:
                json.dump(roles, f, ensure_ascii=False, indent=2)
            return jsonify({"message": "Role deleted", "data": roles})
    except Exception as e:
        app.logger.error(f"Error handling role {roleId}: {str(e)}")
        return jsonify({"error": "Failed to handle role"}), 500
    
    
# API追加
@app.route('/api/role-form-schema/<roleName>', methods=['GET'])
def get_role_form_schema(roleName):
    try:
        schema = scenario.generate_role_form_schema(roleName,DATA_DIR)
        return jsonify(schema)
    except Exception as e:
        app.logger.error(f"Error fetching role schema: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/scenario-role', methods=['GET'])
def get_roles():
    try:
        roles = []
        for file in os.listdir('data/scenario-role'):
            if file.endswith('.json'):
                with open(f'data/scenario-role/{file}', 'r', encoding='utf-8') as f:
                    role_data = json.load(f)
                    roles.append({
                        'id': file.replace('.json', ''),
                        'name': file.replace('.json', ''),
                        'description': role_data.get('description', ''),
                        'branchType': role_data.get('branchType', 'General')
                    })
        return jsonify(roles)
    except Exception as e:
        app.logger.error(f"Error fetching roles: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/save-role-data/<eventId>/<subId>/<nodeId>/<roleId>', methods=['POST'])
def save_role_data(eventId, subId, nodeId, roleId):
    try:
        data = request.get_json()
        formData = data.get('formData', {})
        file_path = os.path.join(DATA_DIR, scenario.SCENARIO_EVENT, eventId, f"{eventId}.json")
        current_data = {}
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                current_data = json.load(f)
        subgroups = current_data.get('subgroups', {}).get(subId, {}).get('nodes', [])
        for node in subgroups:
            if node['id'] == nodeId:
                node['data']['roles'] = [
                    role if role['id'] != roleId else { **role, 'data': formData }
                    for role in node['data'].get('roles', [])
                ]
                break
            if node['data'].get('subgroups', {}).get(nodeId):
                node['data']['subgroups'][nodeId]['nodes'][0]['data']['roles'] = [
                    role if role['id'] != roleId else { **role, 'data': formData }
                    for role in node['data']['subgroups'][nodeId]['nodes'][0]['data'].get('roles', [])
                ]
                break
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(current_data, f, ensure_ascii=False, indent=2)
        return jsonify({'message': 'Role data saved'})
    except Exception as e:
        app.logger.error(f"Error saving role data: {str(e)}")
        return jsonify({'error': str(e)}), 500
    
# エンドポイント
@app.route('/api/fix-all-events', methods=['POST'])
def fix_all_events_endpoint():
    try:
        scenario.fix_all_events()
        return jsonify({"message": "All events fixed successfully"})
    except Exception as e:
        logger.error(f"Error fixing all events: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/generate-all-event-bin', methods=['POST'])
def generate_all_event_bin_endpoint():
    try:
        scenario.fix_all_events()  # 先に Fix
        basic_types, unity_types, enum_list, class_list, class_data_id_list,enum_data,class_data_id,class_data = get_type_lists()
        result = scenario.generate_all_event_bin(basic_types, unity_types, enum_list, class_list, class_data_id_list,enum_data,class_data_id,class_data)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error generating all event bin: {str(e)}")
        return jsonify({"error": str(e)}), 500
    

#===============================================================================
#Assets

# Texture
@app.route('/api/texture', methods=['GET'])
def get_texture():
    return jsonify(assets.get_texture_data())

@app.route('/api/texture/add_group', methods=['POST'])
def add_texture_group():
    data = request.json
    assets.add_texture_group(data['group_name'])
    return jsonify({'status': 'success'})

@app.route('/api/texture/delete_group', methods=['POST'])
def delete_texture_group():
    data = request.json
    assets.delete_texture_group(data['group_name'])
    return jsonify({'status': 'success'})

@app.route('/api/texture/add_subgroup', methods=['POST'])
def add_texture_subgroup():
    data = request.json
    try:
        assets.add_texture_subgroup(data['group_name'], data['subgroup_name'])
        return jsonify({'status': 'success'})
    except Exception as e:
        logger.error(f"Texture SubGroup追加エラー: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/texture/delete_subgroup', methods=['POST'])
def delete_texture_subgroup():
    data = request.json
    try:
        assets.delete_texture_subgroup(data['group_name'], data['subgroup_name'])
        return jsonify({'status': 'success'})
    except Exception as e:
        logger.error(f"Texture SubGroup削除エラー: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/texture/add_texture', methods=['POST'])
def add_texture():
    data = request.json
    try:
        assets.add_texture(
            data['group_name'],
            data['name'],
            data['desc'],
            data['isSpriteRender'],
            subgroup_name=data.get('subgroup_name')
        )
        return jsonify({'status': 'success'})
    except Exception as e:
        logger.error(f"Texture追加エラー: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/texture/delete_texture', methods=['POST'])
def delete_texture():
    data = request.json
    assets.delete_texture(data['group_name'], data['index'])
    return jsonify({'status': 'success'})

@app.route('/api/texture/edit_texture', methods=['POST'])
def edit_texture():
    """
    既存テクスチャエントリの編集（ファイルの再選択は行わない）
    """
    data = request.json
    try:
        assets.edit_texture(
            data['group_name'],
            data['index'],
            name=data.get('name'),
            desc=data.get('desc'),
            isSpriteRender=data.get('isSpriteRender'),
            subgroup_name=data.get('subgroup_name')
        )
        return jsonify({'status': 'success'})
    except Exception as e:
        logger.error(f"Texture編集エラー: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/texture/reload_texture', methods=['POST'])
def reload_texture():
    """
    既存テクスチャエントリのファイル参照を再選択する。
    エクスプローラーは、以前保存していたファイルのパスから開く。
    """
    data = request.json
    try:
        entry = assets.reload_texture_file(data['group_name'], data['index'])
        return jsonify({'status': 'success', 'entry': entry})
    except Exception as e:
        logger.error(f"Textureリロードエラー: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/texture/generate', methods=['POST'])
def generate_texture_files():
    assets.generate_texture_csharp()
    assets.generate_texture_bin()
    return jsonify({'status': 'success'})

@app.route('/api/texture/serve/<group_name>/<int:index>')
def serve_texture(group_name, index):
    file_path = assets.get_texture_file_path(group_name, index)
    if file_path and os.path.exists(file_path):
        return send_file(file_path, mimetype='image/png')
    return jsonify({'error': 'File not found'}), 404

# GameObject
@app.route('/api/gameobject', methods=['GET'])
def get_gameobject():
    return jsonify(assets.get_gameobject_data())

@app.route('/api/gameobject/add_group', methods=['POST'])
def add_gameobject_group():
    data = request.json
    assets.add_gameobject_group(data['group_name'])
    return jsonify({'status': 'success'})

@app.route('/api/gameobject/delete_group', methods=['POST'])
def delete_gameobject_group():
    data = request.json
    assets.delete_gameobject_group(data['group_name'])
    return jsonify({'status': 'success'})

@app.route('/api/gameobject/add_subgroup', methods=['POST'])
def add_gameobject_subgroup():
    data = request.json
    try:
        assets.add_gameobject_subgroup(data['group_name'], data['subgroup_name'])
        return jsonify({'status': 'success'})
    except Exception as e:
        logger.error(f"GameObject SubGroup追加エラー: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/gameobject/delete_subgroup', methods=['POST'])
def delete_gameobject_subgroup():
    data = request.json
    try:
        assets.delete_gameobject_subgroup(data['group_name'], data['subgroup_name'])
        return jsonify({'status': 'success'})
    except Exception as e:
        logger.error(f"GameObject SubGroup削除エラー: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/gameobject/add_gameobject', methods=['POST'])
def add_gameobject():
    data = request.json
    try:
        assets.add_gameobject(
            data['group_name'],
            data['name'],
            data['desc'],
            subgroup_name=data.get('subgroup_name')
        )
        return jsonify({'status': 'success'})
    except Exception as e:
        logger.error(f"GameObject追加エラー: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/gameobject/delete_gameobject', methods=['POST'])
def delete_gameobject():
    data = request.json
    assets.delete_gameobject(data['group_name'], data['index'])
    return jsonify({'status': 'success'})

@app.route('/api/gameobject/edit_gameobject', methods=['POST'])
def edit_gameobject():
    """
    既存ゲームオブジェクトエントリの編集（ファイルの再選択は行わない）
    """
    data = request.json
    try:
        assets.edit_gameobject(
            data['group_name'],
            data['index'],
            name=data.get('name'),
            desc=data.get('desc'),
            subgroup_name=data.get('subgroup_name')
        )
        return jsonify({'status': 'success'})
    except Exception as e:
        logger.error(f"GameObject編集エラー: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/gameobject/reload_gameobject', methods=['POST'])
def reload_gameobject():
    """
    既存ゲームオブジェクトエントリのファイル参照を再選択する。
    エクスプローラーは、以前保存していたファイルのパスから開く。
    """
    data = request.json
    try:
        entry = assets.reload_gameobject_file(data['group_name'], data['index'])
        return jsonify({'status': 'success', 'entry': entry})
    except Exception as e:
        logger.error(f"GameObjectリロードエラー: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/gameobject/generate', methods=['POST'])
def generate_gameobject_files():
    assets.generate_gameobject_csharp()
    assets.generate_gameobject_bin()
    return jsonify({'status': 'success'})


#=================================================-----
# Material（Shader / Material の プロパティからCS生成）

@app.route('/api/material', methods=['GET'])
def get_material():
    return jsonify(assets.get_material_data())

@app.route('/api/material/add_group', methods=['POST'])
def add_material_group():
    data = request.get_json()
    try:
        assets.add_material_group(data['group_name'])
        return jsonify({"message": "グループを追加しました。"}), 200
    except Exception as e:
        logger.error(f"Materialグループ追加エラー: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/material/delete_group', methods=['POST'])
def delete_material_group():
    data = request.get_json()
    try:
        assets.delete_material_group(data['group_name'])
        return jsonify({"message": "グループを削除しました。"}), 200
    except Exception as e:
        logger.error(f"Materialグループ削除エラー: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/material/add_subgroup', methods=['POST'])
def add_material_subgroup():
    data = request.get_json()
    try:
        assets.add_material_subgroup(data['group_name'], data['subgroup_name'])
        return jsonify({"message": "SubGroupを追加しました。"}), 200
    except Exception as e:
        logger.error(f"Material SubGroup追加エラー: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/material/delete_subgroup', methods=['POST'])
def delete_material_subgroup():
    data = request.get_json()
    try:
        assets.delete_material_subgroup(data['group_name'], data['subgroup_name'])
        return jsonify({"message": "SubGroupを削除しました。"}), 200
    except Exception as e:
        logger.error(f"Material SubGroup削除エラー: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/material/select_file', methods=['POST'])
def select_material_file():
    """
    エクスプローラーを開いて .shader / .shadergraph / .mat を選択し、
    プロパティ名・型・Addressableパスを取得する
    """
    try:
        result = assets.get_material_properties()
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Materialプロパティ取得エラー: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/material/generate', methods=['POST'])
def generate_material():
    """
    グループ・クラス名・説明・選択されたプロパティ名を元に、
    Unityへ再通信して最新のプロパティ(型含む)とAddressableパスを取得し直し、
    MaterialData用のC#（クラス本体・Group/ID Enum・Core一式・バイナリ）を生成する
    """
    data = request.get_json()
    try:
        selected_names = [p['name'] for p in data.get('properties', []) if p.get('name')]
        assets.generate_material_entry(
            data.get('group_name'),
            data.get('class_name'),
            data.get('desc', ''),
            data.get('absolute_path'),
            selected_names,
            subgroup_name=data.get('subgroup_name')
        )
        return jsonify({"message": "C#ファイルを生成しました。"}), 200
    except Exception as e:
        logger.error(f"Material生成エラー: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/material/regenerate', methods=['POST'])
def regenerate_material():
    """
    既存エントリの再生成。jsonに保持したabsolute_pathと選択済みプロパティ名を使い、
    Unityへ再通信してからCS・Enum・Core・バイナリを再生成する
    """
    data = request.get_json()
    try:
        assets.regenerate_material_entry(data['group_name'], data['class_name'])
        return jsonify({"message": "再生成しました。"}), 200
    except Exception as e:
        logger.error(f"Material再生成エラー: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/material/delete', methods=['POST'])
def delete_material():
    data = request.get_json()
    try:
        assets.delete_material_entry(data['group_name'], data['class_name'])
        return jsonify({"message": "削除しました。"}), 200
    except Exception as e:
        logger.error(f"Material削除エラー: {str(e)}")
        return jsonify({"error": str(e)}), 500


#=================================================-----
# Material CS-only（Group/SubGroup/Enum/バイナリに一切含めない、クラス生成のみのモード）

@app.route('/api/material/cs_only', methods=['GET'])
def get_material_cs_only():
    return jsonify(assets.get_material_cs_only_data())

@app.route('/api/material/cs_only/generate', methods=['POST'])
def generate_material_cs_only():
    """
    クラス名・説明・選択されたプロパティ名を元に、Unityへ再通信して
    最新のプロパティ(型含む)とAddressableパスを取得し直し、
    MaterialPropertyBlock操作用のC#クラスだけを生成する。
    Group/SubGroupへの追加、MaterialGroup/MaterialID Enumへの登録、
    バイナリへの梱包はいずれも行わない。
    """
    data = request.get_json()
    try:
        selected_names = [p['name'] for p in data.get('properties', []) if p.get('name')]
        assets.generate_material_cs_only(
            data.get('class_name'),
            data.get('desc', ''),
            data.get('absolute_path'),
            selected_names
        )
        return jsonify({"message": "C#ファイルを生成しました（CS-only）。"}), 200
    except Exception as e:
        logger.error(f"Material CS-only生成エラー: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/material/cs_only/regenerate', methods=['POST'])
def regenerate_material_cs_only():
    data = request.get_json()
    try:
        assets.regenerate_material_cs_only(data['class_name'])
        return jsonify({"message": "再生成しました（CS-only）。"}), 200
    except Exception as e:
        logger.error(f"Material CS-only再生成エラー: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/material/cs_only/delete', methods=['POST'])
def delete_material_cs_only():
    data = request.get_json()
    try:
        assets.delete_material_cs_only(data['class_name'])
        return jsonify({"message": "削除しました（CS-only）。"}), 200
    except Exception as e:
        logger.error(f"Material CS-only削除エラー: {str(e)}")
        return jsonify({"error": str(e)}), 500


#=================================================-----
# Sound

@app.route('/api/sound', methods=['GET'])
def get_sound():
    return jsonify(assets.get_sound_data())

@app.route('/api/sound/add_group', methods=['POST'])
def add_group():
    data = request.json
    assets.add_sound_group(data['group_name'])
    return jsonify({'status': 'success'})

@app.route('/api/sound/delete_group', methods=['POST'])
def delete_group():
    data = request.json
    assets.delete_sound_group(data['group_name'])
    return jsonify({'status': 'success'})

@app.route('/api/sound/add_subgroup', methods=['POST'])
def add_sound_subgroup():
    data = request.json
    try:
        assets.add_sound_subgroup(data['group_name'], data['subgroup_name'])
        return jsonify({'status': 'success'})
    except Exception as e:
        logger.error(f"Sound SubGroup追加エラー: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/sound/delete_subgroup', methods=['POST'])
def delete_sound_subgroup():
    data = request.json
    try:
        assets.delete_sound_subgroup(data['group_name'], data['subgroup_name'])
        return jsonify({'status': 'success'})
    except Exception as e:
        logger.error(f"Sound SubGroup削除エラー: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/sound/add_sound', methods=['POST'])
def add_sound():
    data = request.json
    try:
        assets.add_sound(
            data['group_name'],
            data['name'],
            data['desc'],
            data['volume'],
            data['type'],
            subgroup_name=data.get('subgroup_name')
        )
        return jsonify({'status': 'success'})
    except Exception as e:
        logger.error(f"Sound追加エラー: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/sound/bulk_add_from_folder', methods=['POST'])
def bulk_add_sounds_from_folder():
    """フォルダを1つ選択し、直下の音声ファイルをまとめて登録する。
    VOICEのようにファイル数が非常に多いカテゴリを想定した一括登録用。"""
    data = request.json
    try:
        result = assets.bulk_add_sounds_from_folder(
            data['group_name'],
            data['type'],
            subgroup_name=data.get('subgroup_name'),
            use_folder_name_as_subgroup=data.get('use_folder_name_as_subgroup', True),
        )
        return jsonify({'status': 'success', **result})
    except Exception as e:
        logger.error(f"Sound一括追加エラー: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/sound/delete_sound', methods=['POST'])
def delete_sound():
    data = request.json
    assets.delete_sound(data['group_name'], data['index'])
    return jsonify({'status': 'success'})

@app.route('/api/sound/edit_sound', methods=['POST'])
def edit_sound():
    """
    既存サウンドエントリの編集（ファイルの再選択は行わない）
    """
    data = request.json
    try:
        assets.edit_sound(
            data['group_name'],
            data['index'],
            name=data.get('name'),
            desc=data.get('desc'),
            volume=data.get('volume'),
            sound_type=data.get('type'),
            subgroup_name=data.get('subgroup_name')
        )
        return jsonify({'status': 'success'})
    except Exception as e:
        logger.error(f"Sound編集エラー: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/sound/reload_sound', methods=['POST'])
def reload_sound():
    """
    既存サウンドエントリのファイル参照を再選択する。
    エクスプローラーは、以前保存していたファイルのパスから開く。
    """
    data = request.json
    try:
        entry = assets.reload_sound_file(data['group_name'], data['index'])
        return jsonify({'status': 'success', 'entry': entry})
    except Exception as e:
        logger.error(f"Soundリロードエラー: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/sound/generate', methods=['POST'])
def generate_files():
    assets.generate_sound_csharp()
    assets.generate_sound_bin()
    return jsonify({'status': 'success'})
    
    
# Sound serve endpoint for playback
@app.route('/api/sound/serve/<group_name>/<int:index>')
def serve_sound(group_name, index):
    file_path = assets.get_sound_file_path(group_name, index)
    if file_path and os.path.exists(file_path):
        return send_file(file_path, mimetype='audio/mpeg')
    return jsonify({'error': 'File not found'}), 404



# ============================================================
# Animator / Scene / SaveData / 静的配信 / ConstClassData API
# ============================================================

#======================================================--
#animator
# ========================================
# 1. 全データ取得（Grid表示用）
# ========================================
@app.route('/api/animator-data', methods=['GET'])
def api_animator_data():
    registered = pythonSrc.animation.load_index()               # ["Player", "Enemy", ...]
    rows = []
    id_counter = 0

    for name in registered:
        try:
            meta = pythonSrc.animation.load_individual(name)
            group = meta.get("group", "Default")
            desc  = meta.get("desc", "")
            path  = meta.get("absolute_path", "")
            ctrl  = os.path.basename(path) if path else ""
        except Exception:
            group = desc = path = ctrl = ""

        id_counter += 1
        rows.append({
            "id": id_counter,
            "name": name,
            "group": group,
            "desc": desc,
            "path": path,
            "controller": ctrl
        })

    return jsonify(rows)

# ========================================
# 2. 新規作成（Gridの「作成」ボタン）
# ========================================
@app.route('/api/animator-create', methods=['POST'])
def api_animator_create():
    try:
        payload = request.get_json(silent=True) or {}
        group = payload.get('group', 'Default').strip()
        name  = payload.get('name', '').strip()

        if not name:
            return jsonify({"error": "名前は必須です"}), 400
        if ':' in name:
            return jsonify({"error": ": は使用できません"}), 400

        # 重複チェック（indexにあればNG）
        if name in pythonSrc.animation.load_index():
            return jsonify({"error": f"{name} は既に存在します"}), 400

        # assets.py の関数呼び出し（内部で個別保存＋index登録）
        pythonSrc.animation.add_animator(group, name, "Created via Grid")
        return jsonify({"message": f"{name} 作成＆自動生成完了！"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ========================================
# 3. 削除（Gridの削除ボタン → PATCH）
# ========================================
@app.route('/api/animator-data', methods=['PATCH'])
def api_animator_delete():
    try:
        payload = request.get_json(silent=True) or {}
        target_name = payload.get('name')
        if not target_name:
            return jsonify({"error": "name 必須"}), 400

        index = pythonSrc.animation.load_index()
        if target_name not in index:
            return jsonify({"error": f"{target_name} が見つかりません"}), 404

        # 1. 個別フォルダごと削除
        individual_dir = os.path.dirname(pythonSrc.animation.get_individual_path(target_name))
        if os.path.exists(individual_dir):
            import shutil
            shutil.rmtree(individual_dir)

        # 2. 生成済み.cs削除（従来通り）
        cs_path = os.path.join(pythonSrc.animation.ANIM_DATA, f"{target_name}", 
                               f"{target_name}AnimationManager.g.cs")
        if os.path.exists(cs_path):
            os.remove(cs_path)

        # 3. indexから除去
        index.remove(target_name)
        pythonSrc.animation.save_index(index)

        return jsonify({"message": f"{target_name} 削除完了"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ========================================
# 4. 全自動生成（Gridの「全Animator自動生成」ボタン）
# ========================================
@app.route('/api/generate-all-animator', methods=['POST'])
def api_generate_all_animator():
    try:
        basic_types, unity_types, enum_list, class_list, class_data_id_list,enum_data,class_data_id,class_data = get_type_lists()
        pythonSrc.animation.generate_all_animator_csharp(basic_types, unity_types, enum_list, class_list, class_data_id_list,enum_data,class_data_id,class_data)
        return jsonify({"message": "全Animator自動生成完了！\nUnityでリフレッシュしてね"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
    # /api/animator-data/{name} (GET) - 個別取得
@app.route('/api/animator-data/<name>', methods=['GET'])
def api_get_animator_detail(name):
    try:
        data = pythonSrc.animation.load_individual(name)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 404

# /api/animator-data/{name} (POST) - 保存
@app.route('/api/animator-data/<name>', methods=['POST'])
def api_save_animator_detail(name):
    try:
        payload = request.get_json()
        pythonSrc.animation.save_individual(name, payload)
        return jsonify({"message": f"{name} 保存完了"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# /api/generate-animator/{name} (POST) - 個別生成
@app.route('/api/generate-animator/<name>', methods=['POST'])
def api_generate_single_animator(name):
    try:
        ctrl = pythonSrc.animation.load_individual(name)
        basic_types, unity_types, enum_list, class_list, class_data_id_list,enum_data,class_data_id,class_data = get_type_lists()
        pythonSrc.animation.generate_single_animator_csharp(ctrl,basic_types, unity_types, enum_list, class_list, class_data_id_list,enum_data,class_data_id,class_data)  # ← 新規関数
        return jsonify({"message": f"{name}AnimationManager.g.cs 生成完了！"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

#==================================================================
# Scene
#==================================================================

@app.route('/api/scene/get', methods=['GET'])
def get_scenes():
    data = scene.load_scene_data()
    return jsonify(data)

@app.route('/api/scene/add', methods=['POST'])
def add_scene():
    data = request.json
    enum_name = data.get('enum_name')
    scene_type = data.get('scene_type') # Added scene_type
    result = scene.add_scene(enum_name, scene_type)
    return jsonify(result)

@app.route('/api/scene/delete', methods=['POST'])
def delete_scene():
    data = request.json
    enum_name = data.get('enum_name')
    result = scene.delete_scene(enum_name)
    return jsonify(result)

@app.route('/api/scene/generate', methods=['POST'])
def generate_scene_code():
    result = scene.generate_cs_files() # Changed function name
    return jsonify(result)

# --- SaveData (SystemData/PlayerData) Management ---

@app.route('/api/save-data/<name>', methods=['GET', 'POST'])
def manage_save_data_schema(name):
    if name not in ['SystemData', 'PlayerData']:
        return jsonify({"error": "Invalid save data type"}), 400

    file_path = os.path.join(SAVE_DATA_CUSTOM_DIR, f"{name}.json")

    if request.method == 'GET':
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return jsonify(data)
            except Exception as e:
                logger.error(f"Error reading {name} schema: {e}")
                return jsonify([]), 500 # Return empty list if error or file empty
        else:
            return jsonify([]) # Return empty list if file doesn't exist

    elif request.method == 'POST':
        try:
            data = request.get_json()
            # Ensure directory exists
            if not os.path.exists(SAVE_DATA_CUSTOM_DIR):
                os.makedirs(SAVE_DATA_CUSTOM_DIR)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return jsonify({"message": f"{name} schema saved successfully"})
        except Exception as e:
            logger.error(f"Error saving {name} schema: {e}")
            return jsonify({"error": str(e)}), 500
        
def resolve_save_field_cs_type(type_name, custom_type_info):
    """SaveData(SystemData/PlayerData)の1フィールド分のC#型名と初期化式を解決する。
    generate_csharp_field / pythonSrc.customclassdata.generate_custom_field と
    同じ型解決ルールを使う(Save側はBinaryFormatterでのフルオブジェクト
    シリアライズなので、ReadBinary相当のコードまでは不要で型名の解決だけで足りる)。
    戻り値: (cs_type: str, initial_expr: str|None)
    """
    enum_list = custom_type_info['enum_list']
    class_list = custom_type_info['class_list']
    class_data_id_list = custom_type_info['class_data_id_list']
    custom_class_list = custom_type_info['custom_class_list']
    custom_class_id_list = custom_type_info['custom_class_id_list']

    if type_name == 'bit':
        # SaveData側の変数定義には現状 options を持たせていないため、
        # 手動指定(size=8)のCustomBitFieldとして解決する。
        return pythonSrc.customclassdata._bit_cs_type_and_initial({})
    if type_name == 'color':
        return 'UnityEngine.Color', 'new UnityEngine.Color(1f, 1f, 1f, 1f)'
    if type_name == 'bezier':
        return 'UnityEngine.AnimationCurve', 'new UnityEngine.AnimationCurve()'
    if type_name in enum_list:
        cs = f"GameCore.Enums.{type_name}ID"
        return cs, f"{cs}.None"
    if type_name in class_list:
        cs = f"GameCore.Classes.{type_name}"
        return cs, f"new {cs}()"
    if type_name in class_data_id_list or type_name in custom_class_id_list:
        # CustomClassDataIDもClassDataID同様、TableID enumとして扱う
        cs = f"GameCore.Tables.ID.{type_name}TableID"
        return cs, f"{cs}.None"
    if type_name in custom_class_list:
        cs = f"GameCore.Classes.{type_name}"
        return cs, f"new {cs}()"
    if type_name.lower() == 'vector2':
        return 'UnityEngine.Vector2', 'new UnityEngine.Vector2()'
    if type_name.lower() == 'vector3':
        return 'UnityEngine.Vector3', 'new UnityEngine.Vector3()'
    if type_name.lower() == 'string':
        return 'string', '""'
    return type_name, None  # 基本型(int/float/bool等)はそのままの型名でOK

@app.route('/api/generate-save-data/<name>', methods=['POST'])
def generate_save_data_cs(name):
    if name not in ['SystemData', 'PlayerData']:
        return jsonify({"error": "Invalid save data type"}), 400

    # Get data from request or file
    data = request.get_json()
    if not data:
        file_path = os.path.join(SAVE_DATA_CUSTOM_DIR, f"{name}.json")
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            data = []

    try:
        # 型解決に enum/class/class_data_id/CustomClassData(ID) を使えるようにする
        basic_types, unity_types, enum_list, class_list, class_data_id_list, enum_data, class_data_id, class_data = get_type_lists()
        custom_type_info = build_custom_type_info(enum_list, class_list, class_data_id_list)

        # Generate C# Code
        field_declarations = ""
        for item in data:
            type_name = item.get('type', 'int')
            var_name = item.get('name', 'Variable')
            array_size = item.get('arraySize', 0)
            description = item.get('description', '')

            cs_type, initial = resolve_save_field_cs_type(type_name, custom_type_info)

            # Basic comment
            if description:
                field_declarations += f"        /// <summary>\n        /// {description}\n        /// </summary>\n"

            # Field definition
            if array_size > 0:
                field_declarations += f"        public {cs_type}[] {var_name} = new {cs_type}[{array_size}];\n"
            elif array_size == -1:
                field_declarations += f"        public List<{cs_type}> {var_name} = new List<{cs_type}>();\n"
            else:
                init_suffix = f" = {initial}" if initial is not None else ""
                field_declarations += f"        public {cs_type} {var_name}{init_suffix};\n"

        code_str = f"""using System;
using UnityEngine;
using System.Collections.Generic;
using GameCore.Enums;
using GameCore.Tables;
using GameCore.Classes;

namespace GameCore.SaveSystem
{{
    [Serializable]
    public class Base{name}
    {{
{field_declarations}
    }}
}}
"""
        cs_path = os.path.join(SAVE_DATA_CUSTOM_DIR, f"Base{name}.cs")
        with open(cs_path, 'w', encoding='utf-8') as f:
            f.write(code_str)
        
        return jsonify({"message": f"{name}.cs generated successfully"})
    except Exception as e:
        logger.error(f"Error generating {name}.cs: {e}")
        return jsonify({"error": str(e)}), 500
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_static(path):
    logger.debug(f"Serving static file: {path}")
    if path != '' and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, 'index.html')

def _validate_const_value(type_str, value):
    """サーバー側でも型に応じた値のバリデーションを行う"""
    if type_str in ('int', 'uint'):
        try:
            iv = int(value)
        except (TypeError, ValueError):
            return False
        if type_str == 'uint' and iv < 0:
            return False
        return True
    if type_str == 'float':
        try:
            float(value)
        except (TypeError, ValueError):
            return False
        return True
    if type_str == 'string':
        return isinstance(value, str)
    if type_str in ('vector2', 'vector3'):
        expected_len = 2 if type_str == 'vector2' else 3
        if not isinstance(value, (list, tuple)) or len(value) != expected_len:
            return False
        for v in value:
            try:
                float(v)
            except (TypeError, ValueError):
                return False
        return True
    return False
 
 
def _format_cs_literal(type_str, value):
    """C#のリテラル表現に変換"""
    if type_str == 'int':
        return str(int(value))
    if type_str == 'uint':
        return f"{int(value)}u"
    if type_str == 'float':
        return f"{float(value)}f"
    if type_str == 'string':
        escaped = str(value).replace('\\', '\\\\').replace('"', '\\"')
        return f"\"{escaped}\""
    if type_str == 'vector2':
        x, y = value
        return f"new Vector2({float(x)}f, {float(y)}f)"
    if type_str == 'vector3':
        x, y, z = value
        return f"new Vector3({float(x)}f, {float(y)}f, {float(z)}f)"
    return "null"
 
 
# ------------------------------------------------------------
# 2) ConstClassData 一覧管理（GET / POST / PATCH）
#    ClassDataIdGrid の /api/class-data-id と同じパターン
# ------------------------------------------------------------
@app.route('/api/const-class-data', methods=['GET', 'POST', 'PATCH'])
def manage_const_class_data():
    const_class_dir = os.path.join(DATA_DIR, CONST_CLASS_DATA)
    os.makedirs(const_class_dir, exist_ok=True)
    file_path = os.path.join(const_class_dir, 'const_class_data_list.json')
 
    if request.method == 'GET':
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return jsonify(data), 200
        except FileNotFoundError:
            return jsonify([]), 200
        except json.JSONDecodeError:
            logger.error("const_class_data_list.jsonの形式が不正です")
            return jsonify({"error": "const_class_data_list.jsonの形式が不正です"}), 500
        except Exception as e:
            logger.error(f"ConstClassDataリストの読み込みエラー: {str(e)}")
            return jsonify({"error": f"データ読み込みエラー: {str(e)}"}), 500
 
    elif request.method == 'POST':
        try:
            new_item = request.get_json()
            if not new_item or not new_item.get('name'):
                return jsonify({"error": "名前は必須です"}), 400
            name = new_item['name']
            if ':' in name:
                return jsonify({"error": "名前に':'を含めることはできません"}), 400
 
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except FileNotFoundError:
                data = []
 
            if any(item['name'] == name for item in data):
                return jsonify({"error": f"ConstClass {name} はすでに存在します"}), 400
 
            max_id = max([item['id'] for item in data], default=0) + 1
            new_entry = {"id": max_id, "name": name}
            data.append(new_entry)
 
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
 
            # 定数データ用の空ファイルを作成
            data_file_path = os.path.join(const_class_dir, name, f"{name}.json")
            os.makedirs(os.path.dirname(data_file_path), exist_ok=True)
            with open(data_file_path, 'w', encoding='utf-8') as f:
                json.dump({"constants": []}, f, ensure_ascii=False, indent=2)
 
            logger.info(f"ConstClassDataを作成しました: {name}")
            return jsonify({"message": f"ConstClass {name} を正常に作成しました", "data": new_entry}), 201
 
        except Exception as e:
            logger.error(f"ConstClassData作成エラー: {str(e)}")
            return jsonify({"error": f"作成エラー: {str(e)}"}), 500
 
    elif request.method == 'PATCH':
        try:
            delete_name = request.get_json().get('name')
            if not delete_name:
                return jsonify({"error": "削除する名前を指定してください"}), 400
 
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
 
            if not any(item['name'] == delete_name for item in data):
                return jsonify({"error": f"ConstClass {delete_name} が見つかりません"}), 404
 
            data = [item for item in data if item['name'] != delete_name]
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
 
            data_dir = os.path.join(const_class_dir, delete_name)
            if os.path.exists(data_dir):
                shutil.rmtree(data_dir)
 
            logger.info(f"ConstClassDataを削除しました: {delete_name}")
            return jsonify({"message": f"ConstClass {delete_name} を正常に削除しました"}), 200
 
        except FileNotFoundError:
            return jsonify({"error": "const_class_data_list.jsonが見つかりません"}), 404
        except Exception as e:
            logger.error(f"ConstClassData削除エラー: {str(e)}")
            return jsonify({"error": f"削除エラー: {str(e)}"}), 500
 
 
# ------------------------------------------------------------
# 3) ConstClassData 詳細（定数リストの取得・保存・削除）
# ------------------------------------------------------------
@app.route('/api/const-class-data/<name>', methods=['GET', 'POST', 'DELETE'])
def const_class_data_detail(name):
    file_path = os.path.join(DATA_DIR, CONST_CLASS_DATA, name, f"{name}.json")
 
    if request.method == 'GET':
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return jsonify(data), 200
        except FileNotFoundError:
            return jsonify({"constants": []}), 200
        except Exception as e:
            logger.error(f"ConstClassData詳細読み込みエラー {name}: {str(e)}")
            return jsonify({"error": str(e)}), 500
 
    elif request.method == 'POST':
        try:
            body = request.get_json()
            constants = body.get('constants', [])
 
            # サーバー側バリデーション
            seen_names = set()
            for c in constants:
                if c.get('type') not in CONST_TYPE_MAP:
                    return jsonify({"error": f"不正な型です: {c.get('type')}"}), 400
                if not c.get('name') or not re.match(r'^[A-Za-z0-9_]+$', c['name']):
                    return jsonify({"error": f"不正な定数名です: {c.get('name')}"}), 400
                if c['name'] in seen_names:
                    return jsonify({"error": f"定数名が重複しています: {c['name']}"}), 400
                seen_names.add(c['name'])
                if not _validate_const_value(c['type'], c.get('value')):
                    return jsonify({"error": f"値が不正です（{c['name']}）: 数値のみ入力してください"}), 400
 
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump({"constants": constants}, f, ensure_ascii=False, indent=2)
 
            logger.info(f"ConstClassDataを保存しました: {name}")
            return jsonify({"message": f"{name} の定数データを保存しました"}), 200
 
        except Exception as e:
            logger.error(f"ConstClassData保存エラー {name}: {str(e)}")
            return jsonify({"error": str(e)}), 500
 
    elif request.method == 'DELETE':
        try:
            os.remove(file_path)
            return jsonify({"message": f"{name}.json deleted"}), 200
        except FileNotFoundError:
            return jsonify({"error": "File not found"}), 404
        except Exception as e:
            logger.error(f"ConstClassData削除エラー {name}: {str(e)}")
            return jsonify({"error": str(e)}), 500
 
 
# ------------------------------------------------------------
# 4) C# static class 生成
# ------------------------------------------------------------
def _write_const_class_cs(name, constants):
    class_dir = os.path.join(DATA_DIR, CONST_CLASS_DATA, name)
    os.makedirs(class_dir, exist_ok=True)
    cs_path = os.path.join(class_dir, f"{name}ConstData.cs")
 
    with open(cs_path, 'w', encoding='utf-8') as f:
        f.write("using UnityEngine;\n\n")
        f.write("namespace GameCore.Consts\n{\n")
        f.write(f"    public static class {name}ConstData\n    {{\n")
        for c in constants:
            type_str = c['type']
            info = CONST_TYPE_MAP[type_str]
            literal = _format_cs_literal(type_str, c['value'])
            if info['is_const']:
                f.write(f"        // {c['comment']}\n")
                f.write(f"        public const {info['cs_type']} {c['name']} = {literal};\n")
            else:
                # Vector2 / Vector3 は const 不可のため static readonly
                f.write(f"        public static readonly {info['cs_type']} {c['name']} = {literal};\n")
        f.write("    }\n}\n")
    return cs_path
 
 
@app.route('/api/generate-const-class/<name>', methods=['POST'])
def generate_const_class_cs(name):
    try:
        body = request.get_json() or {}
        constants = body.get('constants')
 
        # bodyに定数が渡されなかった場合は保存済みデータを使用
        if constants is None:
            file_path = os.path.join(DATA_DIR, CONST_CLASS_DATA, name, f"{name}.json")
            with open(file_path, 'r', encoding='utf-8') as f:
                constants = json.load(f).get('constants', [])
 
        for c in constants:
            if c.get('type') not in CONST_TYPE_MAP:
                return jsonify({"error": f"不正な型です: {c.get('type')}"}), 400
            if not _validate_const_value(c['type'], c.get('value')):
                return jsonify({"error": f"値が不正です（{c.get('name')}）"}), 400
 
        cs_path = _write_const_class_cs(name, constants)
        logger.info(f"ConstClass C#を生成しました: {cs_path}")
        return jsonify({"message": f"C#ファイルを生成しました: {cs_path}"}), 200
 
    except Exception as e:
        logger.error(f"ConstClass生成エラー {name}: {str(e)}")
        return jsonify({"error": str(e)}), 500
 
 
@app.route('/api/generate-all-const-class', methods=['POST'])
def generate_all_const_class():
    try:
        list_path = os.path.join(DATA_DIR, CONST_CLASS_DATA, 'const_class_data_list.json')
        if not os.path.exists(list_path):
            return jsonify({"message": "ConstClassDataがありません"}), 200
        with open(list_path, 'r', encoding='utf-8') as f:
            class_list = json.load(f)
 
        generated = []
        for item in class_list:
            name = item['name']
            data_path = os.path.join(DATA_DIR, CONST_CLASS_DATA, name, f"{name}.json")
            if not os.path.exists(data_path):
                continue
            with open(data_path, 'r', encoding='utf-8') as f:
                constants = json.load(f).get('constants', [])
            _write_const_class_cs(name, constants)
            generated.append(name)
 
        return jsonify({"message": f"{len(generated)}件の静的クラスを生成しました: {', '.join(generated)}"}), 200
    except Exception as e:
        logger.error(f"全ConstClass生成エラー: {str(e)}")
        return jsonify({"error": str(e)}), 500
 
 


def flask_main():
    app.run(debug=True, port=8000, use_reloader=False)


if __name__ == '__main__':
    websocket_thread = threading.Thread(target=dbgServer.mainServer, daemon=True)
    flask_thread = threading.Thread(target=flask_main, daemon=True)

    # Start both threads
    flask_thread.start()
    websocket_thread.start()

    # ディレクトリ作成やルート定義が終わったあたり（app生成後ならどこでもOK）に追加
    pythonSrc.customclassdata.register(app, DATA_DIR)
    pythonSrc.debugcommand.register(app, DATA_DIR)

    # class_data / class_data_id / matrix / state / behavior の各ルートを登録
    pythonSrc.class_data.register(app, DATA_DIR)
    pythonSrc.class_data_id.register(app, DATA_DIR)
    pythonSrc.matrix.register(app, DATA_DIR)
    pythonSrc.state.register(app, DATA_DIR)
    pythonSrc.behavior_routes.register(app, DATA_DIR)

    # お知らせ / ワークスペース / ダウンロード
    # announcements(お知らせ)はバージョン管理の対象外(META_DIR)に保存する。
    # download_module はプロジェクトデータ(DATA_DIR)を対象にする。
    announcements.register(app, META_DIR)
    workspace_routes.register(app, DATA_DIR, SERVER_MODE)
    download_module.register(app, DATA_DIR)
    csproj_sync.register(app, DATA_DIR)
    file_locator.register(app, DATA_DIR, SERVER_MODE)
    reference_check.register(app, DATA_DIR)
    lint_check.register(app, DATA_DIR)
    trash.register(app, DATA_DIR)
    generate_all.register(app, DATA_DIR)
    history.register(app, DATA_DIR)
    spreadsheet_io.register(app, DATA_DIR)
    project_stats.register(app, DATA_DIR)
    story_setting.register(app, DATA_DIR)
    upload_module.register(app, DATA_DIR)

    # バージョン管理（DATA_DIR＝Unityデータのみを対象に、他の初期化が終わった最後に登録する）
    versioning.register(app, DATA_DIR, BASE_DIR, SERVER_MODE)

    if SERVER_MODE:
        # サーバー起動中は、編集ログ＆自動バージョンスナップショットを
        # 直近7日分だけ保持するようにローテーションする。
        activity_log.start_rotation_thread(interval_seconds=3600, retention_days=7)
        versioning.start_rotation_thread(interval_seconds=6 * 3600, retention_days=7)

    # Keep the main thread alive
    try:
        websocket_thread.join()
        flask_thread.join()
    except KeyboardInterrupt:
        print("Shutting down servers...")
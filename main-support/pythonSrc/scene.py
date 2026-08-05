import json
import os
import sys
import tkinter as tk
from tkinter import filedialog
import socket
import struct

import pythonSrc.class_data as class_data
from pythonSrc.constants import ENUM


# 実行可能ファイルのディレクトリを取得（PyInstaller対応）
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ディレクトリパス設定
DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "data"))
SCENE_DATA_DIR = os.path.join(DATA_DIR, "scene_data")
SCENE_JSON = os.path.join(SCENE_DATA_DIR, "scenes.json")
EDITOR_DIR = os.path.join(SCENE_DATA_DIR, "Editor")

# シーンのenumは、ClassData/Enum側で管理される共有enumシステムの
# "GameScene" という名前のenumとして扱う（C#での型名は GameSceneID になる）。
SCENE_ENUM_NAME = "GameScene"

def init(data_dir):
    """app.py から呼び出す初期化関数。"""
    global DATA_DIR, SCENE_DATA_DIR, SCENE_JSON, EDITOR_DIR
    DATA_DIR = os.path.abspath(data_dir)
    SCENE_DATA_DIR = os.path.join(DATA_DIR, "scene_data")
    SCENE_JSON = os.path.join(SCENE_DATA_DIR, "scenes.json")
    EDITOR_DIR = os.path.join(SCENE_DATA_DIR, "Editor")


def generate_base():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
    if not os.path.exists(SCENE_DATA_DIR):
        os.makedirs(SCENE_DATA_DIR)
    if not os.path.exists(EDITOR_DIR):
        os.makedirs(EDITOR_DIR)
    if not os.path.exists(SCENE_JSON):
        with open(SCENE_JSON, 'w', encoding='utf-8') as f:
            json.dump({'scenes': []}, f, ensure_ascii=False, indent=4)


def load_scene_data():
    """
    scenes.jsonを読み込む
    """
    if os.path.exists(SCENE_JSON):
        with open(SCENE_JSON, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'scenes': []}

def save_scene_data(data):
    """
    scenes.jsonを保存
    """
    if not os.path.exists(SCENE_DATA_DIR):
        os.makedirs(SCENE_DATA_DIR)
    with open(SCENE_JSON, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def select_file(initial_dir, filetypes):
    """
    ファイル選択ダイアログを表示
    """
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True) # 最前面に表示
    file_path = filedialog.askopenfilename(initialdir=initial_dir, filetypes=filetypes)
    root.destroy()
    return file_path if file_path else None

# Unity communication functions (assets.pyから流用)
def connect_to_unity():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('localhost', 12345))
    return sock

def send_to_unity(command, data=None):
    sock = connect_to_unity()
    try:
        msg = json.dumps({'command': command, 'data': data}).encode('utf-8')
        sock.sendall(struct.pack('I', len(msg)) + msg)
        response_len = struct.unpack('I', sock.recv(4))[0]
        response = json.loads(sock.recv(response_len).decode('utf-8'))
        return response.get('result')
    finally:
        sock.close()

def get_unity_project_path():
    return send_to_unity('get_project_path')


# ============================================================
# Scene用enumを ClassData/Enum 側の管理下(json)に同期する
# ============================================================
def _load_scene_enum_values():
    """
    ENUM/GameScene/GameScene.json を読み込む（無ければ空リスト）。
    フォーマットは他のenumと同じ: [{"property":..,"value":..,"description":..}, ...]
    """
    enum_dir = os.path.join(DATA_DIR, ENUM, SCENE_ENUM_NAME)
    enum_json_path = os.path.join(enum_dir, f"{SCENE_ENUM_NAME}.json")
    if os.path.exists(enum_json_path):
        with open(enum_json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def _save_scene_enum_values(values):
    enum_dir = os.path.join(DATA_DIR, ENUM, SCENE_ENUM_NAME)
    os.makedirs(enum_dir, exist_ok=True)
    enum_json_path = os.path.join(enum_dir, f"{SCENE_ENUM_NAME}.json")
    with open(enum_json_path, 'w', encoding='utf-8') as f:
        json.dump(values, f, ensure_ascii=False, indent=2)


def _ensure_scene_enum_registered():
    """
    ENUM/enum_list.json に "GameScene" エントリが無ければ追加する。
    （/api/enum-id が管理しているenum一覧に、シーン用enumも登録しておく）
    """
    enum_list_path = os.path.join(DATA_DIR, ENUM, 'enum_list.json')
    try:
        with open(enum_list_path, 'r', encoding='utf-8') as f:
            enum_list = json.load(f)
    except FileNotFoundError:
        enum_list = []

    if not any(item.get('name') == SCENE_ENUM_NAME for item in enum_list):
        max_id = max([item['id'] for item in enum_list], default=0) + 1
        enum_list.append({"id": max_id, "name": SCENE_ENUM_NAME})
        os.makedirs(os.path.join(DATA_DIR, ENUM), exist_ok=True)
        with open(enum_list_path, 'w', encoding='utf-8') as f:
            json.dump(enum_list, f, ensure_ascii=False, indent=2)

        # 個別enumの値ファイルが無ければ空リストで初期化
        enum_dir = os.path.join(DATA_DIR, ENUM, SCENE_ENUM_NAME)
        os.makedirs(enum_dir, exist_ok=True)
        value_path = os.path.join(enum_dir, f"{SCENE_ENUM_NAME}.json")
        if not os.path.exists(value_path):
            with open(value_path, 'w', encoding='utf-8') as f:
                json.dump([], f, ensure_ascii=False, indent=2)


def sync_scene_enum():
    """
    scenes.json の内容を ENUM/GameScene/GameScene.json に反映し、
    class_data.generate_enum_files() を使って GameSceneID.cs / .py / .js を
    （他の全enumと同じパイプラインで）再生成する。

    - 追加: 既存の値を保持しつつ、新しいシーンには次の連番valueを割り当てる
    - 削除: scenes.json に無くなったシーンの値エントリも取り除く
    - 呼び出しタイミング: シーンの追加/削除の度（add_scene / delete_scene から呼ばれる）
    """
    _ensure_scene_enum_registered()

    scenes = load_scene_data().get('scenes', [])
    existing_values = _load_scene_enum_values()
    existing_by_name = {item['property']: item for item in existing_values}

    next_value = max([item['value'] for item in existing_values], default=0) + 1

    new_values = []
    for s in scenes:
        enum_name = s['enum']
        if enum_name in existing_by_name:
            # 既存のvalueを維持（C#側の値が変わらないように）
            item = existing_by_name[enum_name]
            item['description'] = s.get('sceneName', item.get('description', ''))
            new_values.append(item)
        else:
            new_values.append({
                "property": enum_name,
                "value": next_value,
                "description": s.get('sceneName', ''),
            })
            next_value += 1

    _save_scene_enum_values(new_values)

    # class_data.py の /api/generate-enum/<name> と全く同じ生成ロジックを共有で使う。
    # これにより GameSceneID.cs / GameSceneIDExtensions.cs / .py / .js が
    # ENUM/GameScene/ 配下に、他のenumと同じ形式で出力される。
    class_data.generate_enum_files(SCENE_ENUM_NAME, new_values)


def add_scene(enum_name, scene_type):
    """
    シーンを追加（ファイル選択ダイアログを表示）
    """
    data = load_scene_data()
    
    # Unityプロジェクトのパスを取得して初期ディレクトリにする
    try:
        project_path = get_unity_project_path()
    except:
        project_path = BASE_DIR # 取得できない場合はカレント

    file_path = select_file(project_path, [("Unity Scene", "*.unity")])
    
    if not file_path:
        return {"success": False, "message": "No file selected"}

    # シーン名を取得 (ファイル名から拡張子を除く)
    scene_name = os.path.splitext(os.path.basename(file_path))[0]

    # 重複チェック
    for s in data['scenes']:
        if s['enum'] == enum_name:
             return {"success": False, "message": f"Enum '{enum_name}' already exists."}

    data['scenes'].append({
        "enum": enum_name,
        "sceneName": scene_name,
        "path": file_path, # 参考用にパスも保存しておく
        "type": scene_type # Client or Server
    })
    save_scene_data(data)
    sync_scene_enum()
    return {"success": True, "message": "Scene added successfully"}

def delete_scene(enum_name):
    """
    シーンを削除
    """
    data = load_scene_data()
    initial_count = len(data['scenes'])
    data['scenes'] = [s for s in data['scenes'] if s['enum'] != enum_name]
    
    if len(data['scenes']) < initial_count:
        save_scene_data(data)
        sync_scene_enum()
        return {"success": True, "message": "Scene deleted successfully"}
    else:
        return {"success": False, "message": "Scene not found"}


def generate_scene_list_cs(scenes):
    """
    SceneList.cs (Dictionary) を生成
    GameSceneID は ClassData/Enum システム側で生成されるため、ここでは参照するのみ。
    """
    dict_lines = []
    for s in scenes:
        dict_lines.append(f"{{ GameSceneID.{s['enum']}, \"{s['sceneName']}\" }}")
    dict_content = ",\n        ".join(dict_lines)

    code = f"""using System;
using System.Collections.Generic;
using GameCore.Enums;

public class SceneList
{{
    // シーン名管理
    public static readonly Dictionary<GameSceneID, string> sceneNames = new Dictionary<GameSceneID, string>
    {{
        {dict_content}
    }};
}}
"""
    output_path = os.path.join(SCENE_DATA_DIR, "SceneList.cs")
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(code)

def generate_scene_build_cs(scenes):
    """
    SceneBuild.cs (Editor Script) を生成
    """
    if not os.path.exists(EDITOR_DIR):
        os.makedirs(EDITOR_DIR)

    project_path = get_unity_project_path()
    if not project_path:
        project_path = "" # 失敗時は空文字、変換できない可能性あり

    client_scenes = []
    server_scenes = []

    for s in scenes:
        # パスの正規化
        full_path = s['path'].replace("\\\\", "/")
        unity_path = full_path
        
        if project_path:
            proj_root = project_path.replace("\\\\", "/").rstrip("/")
            if full_path.startswith(proj_root):
                unity_path = full_path[len(proj_root):].lstrip("/")
                if not unity_path.startswith("Assets/"):
                    unity_path = "Assets/" + unity_path
        
        # クォートで囲む
        quoted_path = f'"{unity_path}"'

        if s['type'] == 'Client':
            client_scenes.append(quoted_path)
        elif s['type'] == 'Server':
            server_scenes.append(quoted_path)
    
    client_scenes_str = ",\n            ".join(client_scenes)
    server_scenes_str = ",\n            ".join(server_scenes)

    code = f"""using UnityEditor;
using UnityEngine;
using System.IO;
using System.Collections.Generic;

public class SceneBuild : EditorWindow
{{
    [MenuItem("Tools/Build/Build All")]
    public static void BuildAll()
    {{
        string path = EditorUtility.OpenFolderPanel("Select Build Folder", Application.dataPath, "");
        if (string.IsNullOrEmpty(path)) return;

        // Build Client
        string clientPath = Path.Combine(path, "Client");
        if (!Directory.Exists(clientPath)) Directory.CreateDirectory(clientPath);

        BuildPlayerOptions clientOptions = new BuildPlayerOptions();
        clientOptions.scenes = new string[] {{
            {client_scenes_str}
        }};
        clientOptions.locationPathName = Path.Combine(clientPath, "Client.exe");
        clientOptions.target = BuildTarget.StandaloneWindows64;
        
        var clientReport = BuildPipeline.BuildPlayer(clientOptions);
        if (clientReport.summary.result == UnityEditor.Build.Reporting.BuildResult.Succeeded)
        {{
            Debug.Log("Client Build Succeeded: " + clientOptions.locationPathName);
        }}
        else
        {{
            Debug.LogError("Client Build Failed");
        }}

        // Build Server
        string serverPath = Path.Combine(path, "Server");
        if (!Directory.Exists(serverPath)) Directory.CreateDirectory(serverPath);

        BuildPlayerOptions serverOptions = new BuildPlayerOptions();
        serverOptions.scenes = new string[] {{
            {server_scenes_str}
        }};
        serverOptions.locationPathName = Path.Combine(serverPath, "Server.x86_64");
        serverOptions.target = BuildTarget.StandaloneLinux64;
        serverOptions.subtarget = (int)StandaloneBuildSubtarget.Server; // Headless mode
        
        var serverReport = BuildPipeline.BuildPlayer(serverOptions);
        if (serverReport.summary.result == UnityEditor.Build.Reporting.BuildResult.Succeeded)
        {{
            Debug.Log("Server Build Succeeded: " + serverOptions.locationPathName);
        }}
        else
        {{
            Debug.LogError("Server Build Failed");
        }}
    }}
}}
"""
    output_path = os.path.join(EDITOR_DIR, "SceneBuild.cs")
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(code)



def generate_scene_loader_cs():
    """
    SceneLoader.cs (Logic) を生成

    GameSceneID は ClassData/Enum システム側 (GameCore.Enums) で生成される。
    追加で、シーン内のオブジェクトから GetComponent 相当を行う汎用関数
    (単数取得 / 複数取得のジェネリック版) を用意している。
    """
    code = """using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using UnityEngine.SceneManagement;
using Cysharp.Threading.Tasks;
using GameCore.Enums;

public class SceneLoader
{
    private static readonly HashSet<GameSceneID> loadedScenes = new HashSet<GameSceneID>();
    private static readonly Dictionary<GameSceneID, UniTask> loadingTasks = new Dictionary<GameSceneID, UniTask>();

    #region Load / Unload

    public static async UniTask LoadSceneAsync(GameSceneID scene, bool additive = false, Action action = null)
    {
        if (loadedScenes.Contains(scene))
        {
            DebugLog($"Scene '{scene}' is already loaded.");
            return;
        }

        if (loadingTasks.TryGetValue(scene, out UniTask existingTask))
        {
            DebugLog($"Scene '{scene}' is already loading, waiting...");
            await existingTask;
            return;
        }

        var task = InternalLoadSceneAsync(scene, additive, action);
        loadingTasks.Add(scene, task);

        try
        {
            await task;
        }
        finally
        {
            loadingTasks.Remove(scene);
        }
    }

    private static async UniTask InternalLoadSceneAsync(GameSceneID scene, bool additive, Action action = null)
    {
        if (!SceneList.sceneNames.TryGetValue(scene, out string sceneName))
        {
            Debug.LogError($"Scene enum '{scene}' is not mapped to a scene name.");
            return;
        }

        if (!Application.CanStreamedLevelBeLoaded(sceneName))
        {
            Debug.LogError($"Scene '{sceneName}' does not exist in build settings.");
            return;
        }

        AsyncOperation asyncOp = SceneManager.LoadSceneAsync(sceneName, additive ? LoadSceneMode.Additive : LoadSceneMode.Single);
        asyncOp.allowSceneActivation = true;

        while (!asyncOp.isDone)
            await UniTask.Yield();

        loadedScenes.Add(scene);
        action?.Invoke();
        DebugLog($"Scene '{scene}' loaded successfully.");
    }

    public static async UniTask UnloadSceneAsync(GameSceneID scene, Action action = null)
    {
        if (!loadedScenes.Contains(scene))
        {
            DebugLog($"Scene '{scene}' is not loaded, cannot unload.");
            return;
        }

        if (!SceneList.sceneNames.TryGetValue(scene, out string sceneName))
        {
            Debug.LogError($"Scene enum '{scene}' is not mapped to a scene name.");
            return;
        }

        AsyncOperation asyncOp = SceneManager.UnloadSceneAsync(sceneName);
        if (asyncOp == null)
        {
            Debug.LogError($"Failed to unload scene '{sceneName}'.");
            return;
        }

        while (!asyncOp.isDone)
            await UniTask.Yield();

        loadedScenes.Remove(scene);
        GC.Collect();
        await Resources.UnloadUnusedAssets();
        action?.Invoke();   
        DebugLog($"Scene '{scene}' unloaded successfully.");
    }

    /// <summary>
    /// 現在ロード済みのシーンをすべてアンロード
    /// </summary>
    /// <param name="keepScenes">残したいシーン</param>
    public static async UniTask UnloadAllScenesAsync(GameSceneID[] keepScenes, Action action = null)
    {
        var toKeep = new HashSet<GameSceneID>(keepScenes);
        var toUnload = new List<GameSceneID>();

        foreach (var scene in loadedScenes)
            if (!toKeep.Contains(scene))
                toUnload.Add(scene);

        foreach (var scene in toUnload)
            await UnloadSceneAsync(scene);

        action?.Invoke();
    }

    #endregion

    #region Instantiate in Scene

    /// <summary>
    /// 指定シーンに GameObject を生成
    /// </summary>
    public static GameObject InstantiateInScene(GameObject prefab, GameSceneID scene)
    {
        if (!TryGetLoadedScene(scene, out Scene targetScene))
            return null;

        GameObject obj = GameObject.Instantiate(prefab);
        SceneManager.MoveGameObjectToScene(obj, targetScene); // 安全に所属させる
        return obj;
    }

    #endregion

    #region GetComponent In Scene

    /// <summary>
    /// 指定シーンのルートオブジェクト（およびその子）から、型Tのコンポーネントを1つ取得する。
    /// 見つからない場合は null を返す。
    /// </summary>
    public static T GetComponentInScene<T>(GameSceneID scene, bool includeInactive = true) where T : Component
    {
        if (!TryGetLoadedScene(scene, out Scene targetScene))
            return null;

        foreach (GameObject root in targetScene.GetRootGameObjects())
        {
            T found = root.GetComponentInChildren<T>(includeInactive);
            if (found != null)
                return found;
        }
        return null;
    }

    /// <summary>
    /// 指定シーンのルートオブジェクト（およびその子）から、型Tのコンポーネントを全て取得する。
    /// </summary>
    public static List<T> GetComponentsInScene<T>(GameSceneID scene, bool includeInactive = true) where T : Component
    {
        var results = new List<T>();
        if (!TryGetLoadedScene(scene, out Scene targetScene))
            return results;

        foreach (GameObject root in targetScene.GetRootGameObjects())
        {
            results.AddRange(root.GetComponentsInChildren<T>(includeInactive));
        }
        return results;
    }

    private static bool TryGetLoadedScene(GameSceneID scene, out Scene targetScene)
    {
        if (!SceneList.sceneNames.TryGetValue(scene, out string sceneName))
        {
            Debug.LogError($"Scene enum '{scene}' is not mapped to a scene name.");
            targetScene = default;
            return false;
        }

        targetScene = SceneManager.GetSceneByName(sceneName);
        if (!targetScene.isLoaded)
        {
            Debug.LogError($"Scene '{sceneName}' is not loaded.");
            return false;
        }
        return true;
    }

    #endregion

    #region Utility

    public static IReadOnlyCollection<GameSceneID> GetLoadedScenes() => loadedScenes;

    [System.Diagnostics.Conditional("UNITY_EDITOR")]
    private static void DebugLog(string message) => Debug.Log("[SceneLoader] " + message);

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
    private static void RegisterActiveScene()
    {
        var active = SceneManager.GetActiveScene();
        foreach (var kv in SceneList.sceneNames)
        {
            if (kv.Value == active.name)
            {
                loadedScenes.Add(kv.Key);
                break;
            }
        }
    }

    #endregion
}
"""
    output_path = os.path.join(SCENE_DATA_DIR, "SceneLoader.cs")
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(code)

    

def generate_cs_files():
    """
    全てのC#ファイルを生成
    GameSceneID (enum) は ClassData/Enum システム側で生成されるため、
    ここでは SceneList / SceneBuild / SceneLoader のみを生成する。
    """
    data = load_scene_data()
    scenes = data.get('scenes', [])

    sync_scene_enum()
    generate_scene_list_cs(scenes)
    generate_scene_build_cs(scenes)
    generate_scene_loader_cs()
    
    return {"success": True, "message": "All C# files generated successfully"}

if __name__ == "__main__":
    # テスト用
    pass

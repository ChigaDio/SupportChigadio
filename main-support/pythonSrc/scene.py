import json
import os
import sys
import tkinter as tk
from tkinter import filedialog
import socket
import struct

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
        return {"success": True, "message": "Scene deleted successfully"}
    else:
        return {"success": False, "message": "Scene not found"}

def generate_game_scene_cs(scenes):
    """
    GameScene.cs (Enum) を生成
    """
    enum_lines = []
    for s in scenes:
        enum_lines.append(f"    {s['enum']}")
    enum_content = ",\n".join(enum_lines)

    code = f"""using System;

public enum GameScene
{{
{enum_content}
}}
"""
    output_path = os.path.join(SCENE_DATA_DIR, "GameScene.cs")
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(code)

def generate_scene_list_cs(scenes):
    """
    SceneList.cs (Dictionary) を生成
    """
    dict_lines = []
    for s in scenes:
        dict_lines.append(f"{{ GameScene.{s['enum']}, \"{s['sceneName']}\" }}")
    dict_content = ",\n        ".join(dict_lines)

    code = f"""using System;
using System.Collections.Generic;

public class SceneList
{{
    // シーン名管理
    public static readonly Dictionary<GameScene, string> sceneNames = new Dictionary<GameScene, string>
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

    # Client用とServer用のシーンリストを作成
    # ここでは、Typeが一致するものだけをビルドに含めるか、
    # あるいは全てのシーンを含めるが、特定のシーン（Titleなど）は必須にするなどのロジックが必要かもしれない。
    # ユーザー要望は「Clientはwindows標準のビルド、ServerはLinuxのビルド」
    # 単純に、TypeがClientのものはClientビルドに、ServerのものはServerビルドに含める形にする。
    # ただし、共通のシーン（例えばTitle）があるかもしれないが、現状のデータ構造ではTypeは1つ。
    # 必要ならTypeをリストにするか、Bothを追加するが、今回はシンプルに実装する。
    
    # パスは絶対パスで保存されているが、Unityのビルド設定には "Assets/..." から始まる相対パスが必要。
    # get_addressable_path のロジックなどを参考にパスを変換する必要があるが、
    # ここでは簡易的に、保存されているパスが絶対パスなら、Unityプロジェクトルートからの相対パスに変換を試みる。
    # ただし、Python側で正確なUnityプロジェクトルートを知るのは難しい場合がある（get_unity_project_pathは使える）。
    
    # ここでは、C#側でパス解決をするロジックを埋め込むのが安全だが、
    # BuildPlayerOptions.scenes にはパスの文字列配列を渡す必要がある。
    # EditorBuildSettings.scenes から有効なシーンを取得してフィルタリングするのが一般的だが、
    # ここでは scenes.json にあるパス（絶対パス）を "Assets/..." に変換して埋め込む。
    
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
    """
    code = """using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.SceneManagement;
using Cysharp.Threading.Tasks;
using GameCore;

public class SceneLoader
{
    private static readonly HashSet<GameScene> loadedScenes = new HashSet<GameScene>();
    private static readonly Dictionary<GameScene, UniTask> loadingTasks = new Dictionary<GameScene, UniTask>();

    #region Load / Unload

    public static async UniTask LoadSceneAsync(GameScene scene, bool additive = false, Action action = null)
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

    private static async UniTask InternalLoadSceneAsync(GameScene scene, bool additive, Action action = null)
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

    public static async UniTask UnloadSceneAsync(GameScene scene, Action action = null)
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
    public static async UniTask UnloadAllScenesAsync(GameScene[] keepScenes, Action action = null)
    {
        var toKeep = new HashSet<GameScene>(keepScenes);
        var toUnload = new List<GameScene>();

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
    public static GameObject InstantiateInScene(GameObject prefab, GameScene scene)
    {
        if (!SceneList.sceneNames.TryGetValue(scene, out string sceneName))
        {
            Debug.LogError($"Scene enum '{scene}' is not mapped to a scene name.");
            return null;
        }

        Scene targetScene = SceneManager.GetSceneByName(sceneName);

        if (!targetScene.isLoaded)
        {
            Debug.LogError($"Scene '{sceneName}' is not loaded.");
            return null;
        }

        GameObject obj = GameObject.Instantiate(prefab);
        SceneManager.MoveGameObjectToScene(obj, targetScene); // 安全に所属させる
        return obj;
    }

    #endregion

    #region Utility

    public static IReadOnlyCollection<GameScene> GetLoadedScenes() => loadedScenes;

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
    """
    data = load_scene_data()
    scenes = data.get('scenes', [])

    generate_game_scene_cs(scenes)
    generate_scene_list_cs(scenes)
    generate_scene_build_cs(scenes)
    generate_scene_loader_cs()
    
    return {"success": True, "message": "All C# files generated successfully"}

if __name__ == "__main__":
    # テスト用
    pass

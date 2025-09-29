import json
import os
import socket
import struct
import sys
import tkinter as tk
from tkinter import filedialog
from PIL import Image
import shutil
import uuid

# 実行可能ファイルのディレクトリを取得（PyInstaller対応）
if getattr(sys, 'frozen', False):
    # PyInstallerでビルドされた場合
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # デバッグ環境（VS Codeなど）
    # main-support/ の1つ上のディレクトリ（project/）を基準にする
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ディレクトリパスをプロジェクトルート基準に設定
DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "data"))
ASSETS_DATA = os.path.join(DATA_DIR, "assets-data")
SOUND_DATA = os.path.join(ASSETS_DATA, 'sound')
SOUND_JSON = os.path.join(SOUND_DATA, 'assets_sound.json')
TEXTURE_DATA = os.path.join(ASSETS_DATA, 'texture')
TEXTURE_JSON = os.path.join(TEXTURE_DATA, 'assets_texture.json')
GAMEOBJECT_DATA = os.path.join(ASSETS_DATA, 'gameobject')
GAMEOBJECT_JSON = os.path.join(GAMEOBJECT_DATA, 'assets_gameobject.json')
EDITOR_DATA = os.path.join(ASSETS_DATA, 'Editor')
ENUM_DIR = os.path.join(DATA_DIR, 'enum')

def generate_base():
    """
    必要なディレクトリと初期JSONファイルを作成し、enum_list.jsonを更新
    """
    if not os.path.exists(ASSETS_DATA):
        os.makedirs(ASSETS_DATA)
    if not os.path.exists(SOUND_DATA):
        os.makedirs(SOUND_DATA)
    if not os.path.exists(TEXTURE_DATA):
        os.makedirs(TEXTURE_DATA)
    if not os.path.exists(GAMEOBJECT_DATA):
        os.makedirs(GAMEOBJECT_DATA)
    if not os.path.exists(EDITOR_DATA):
        os.makedirs(EDITOR_DATA)
    if not os.path.exists(ENUM_DIR):
        os.makedirs(ENUM_DIR)

    # enum_list.jsonの初期化
    enum_list_path = os.path.join(ENUM_DIR, 'enum_list.json')
    if not os.path.exists(enum_list_path):
        with open(enum_list_path, 'w', encoding='utf-8') as f:
            json.dump([], f)

    # Sound, Texture, GameObjectのエントリを追加（SpriteIDは削除）
    with open(enum_list_path, 'r+', encoding='utf-8') as f:
        enum_list = json.load(f)
        existing_names = [e['name'] for e in enum_list]
        # 既存のIDの最大値を取得（エントリがない場合は0）
        max_id = max([e['id'] for e in enum_list], default=0)
        new_entries = [
            {'name': 'Sound', 'path': SOUND_JSON},
            {'name': 'Texture', 'path': TEXTURE_JSON},
            {'name': 'GameObject', 'path': GAMEOBJECT_JSON}
        ]
        for entry in new_entries:
            if entry['name'] not in existing_names:
                max_id += 1
                enum_list.append({'id': max_id, 'name': entry['name'],'view' : False})
                os.makedirs(os.path.dirname(entry['path']), exist_ok=True)
                with open(entry['path'], 'w', encoding='utf-8') as ef:
                    json.dump([], ef)
        f.seek(0)
        json.dump(enum_list, f, ensure_ascii=False, indent=4)
        f.truncate()

    # EditorCommunication.cs
    if not os.path.exists(os.path.join(EDITOR_DATA, "EditorCommunication.cs")):
        code_str = """
using System;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Threading;
using UnityEditor;
using UnityEditor.AddressableAssets;
using UnityEditor.AddressableAssets.Settings;
using UnityEngine;
using UnityEditorInternal;
using System.Collections.Generic;
using UnityEditor.U2D.Sprites;

public class EditorCommunication : EditorWindow
{
    private static TcpListener listener;
    private static Thread listenerThread;
    private static volatile bool pendingCommand;
    private static string pendingCommandName;
    private static CommData pendingCommandData;
    private static string commandResult;

    // ウィンドウを表示するためのメニュー項目を追加
    [MenuItem("Window/Communication Server")]
    public static void ShowWindow()
    {
        GetWindow<EditorCommunication>("Comm Server");
    }

    // JsonUtility は List を直列化できないのでラッパーが必要
    [System.Serializable]
    private class Wrapper<T>
    {
        public List<T> items;
    }

    [MenuItem("Tools/通信サーバー開始")]
    public static void StartServer()
    {
        if (listener != null) return;
        listener = new TcpListener(IPAddress.Loopback, 12345);
        listener.Start();
        listenerThread = new Thread(new ThreadStart(ListenForClients));
        listenerThread.IsBackground = true;
        listenerThread.Start();
        EditorApplication.update += ProcessPendingCommand;
        Debug.Log("通信サーバーを開始しました。");
    }

    [MenuItem("Tools/通信サーバー停止")]
    public static void StopServer()
    {
        listener?.Stop();
        listener = null;
        EditorApplication.update -= ProcessPendingCommand;
        Debug.Log("通信サーバーを停止しました。");
    }

    // EditorウィンドウのGUIを描画
    private void OnGUI()
    {
        GUILayout.Label("Communication Server Status", EditorStyles.boldLabel);

        // サーバー状態に応じてインジケーターの色を設定
        Color indicatorColor = listener != null ? Color.green : Color.red;
        string statusText = listener != null ? "Running" : "Stopped";

        // インジケーターの描画
        Rect indicatorRect = GUILayoutUtility.GetRect(20, 20);
        EditorGUI.DrawRect(indicatorRect, indicatorColor);

        // ステータステキストの表示
        GUILayout.Label($"Status: {statusText}", EditorStyles.label);

        // サーバー開始/停止ボタン
        if (listener == null)
        {
            if (GUILayout.Button("Start Server"))
            {
                StartServer();
            }
        }
        else
        {
            if (GUILayout.Button("Stop Server"))
            {
                StopServer();
            }
        }
    }

    private static void ListenForClients()
    {
        while (true)
        {
            try
            {
                using (TcpClient client = listener.AcceptTcpClient())
                using (NetworkStream stream = client.GetStream())
                {
                    byte[] lenBytes = new byte[4];
                    stream.Read(lenBytes, 0, 4);
                    int len = BitConverter.ToInt32(lenBytes, 0);
                    byte[] msgBytes = new byte[len];
                    stream.Read(msgBytes, 0, len);
                    string msg = System.Text.Encoding.UTF8.GetString(msgBytes);
                    var json = JsonUtility.FromJson<CommMessage>(msg);

                    pendingCommandName = json.command;
                    pendingCommandData = json.data;
                    pendingCommand = true;

                    while (pendingCommand)
                    {
                        Thread.Sleep(10);
                    }

                    var response = new CommMessage { result = commandResult };
                    byte[] respBytes = System.Text.Encoding.UTF8.GetBytes(JsonUtility.ToJson(response));
                    stream.Write(BitConverter.GetBytes(respBytes.Length), 0, 4);
                    stream.Write(respBytes, 0, respBytes.Length);
                }
            }
            catch (Exception e)
            {
                if (listener == null) break;
                Debug.LogError(e);
            }
        }
    }

    private static void ProcessPendingCommand()
    {
        if (!pendingCommand) return;
        commandResult = HandleCommand(pendingCommandName, pendingCommandData);
        pendingCommand = false;
    }

    private static string HandleCommand(string command, CommData data)
    {
        if (command == "get_project_path")
        {
            return Path.GetFullPath(Path.Combine(Application.dataPath, ".."));
        }
        else if (command == "get_addressable_path")
        {
            string filePath = data.file_path;
            Debug.Log($"Received filePath: {filePath}");

            string projectRoot = Path.GetFullPath(Path.Combine(Application.dataPath, "..")).Replace("\\", "/").TrimEnd('/');
            Debug.Log($"Project root (normalized): {projectRoot}");

            string normalizedFilePath = filePath.Replace("\\", "/").TrimEnd('/');
            Debug.Log($"Normalized filePath: {normalizedFilePath}");

            string assetPath = normalizedFilePath;
            if (normalizedFilePath.StartsWith(projectRoot, StringComparison.OrdinalIgnoreCase))
            {
                assetPath = normalizedFilePath.Substring(projectRoot.Length).TrimStart('/');
                Debug.Log($"Trimmed assetPath: {assetPath}");
            }
            else
            {
                Debug.LogWarning($"filePath does not start with project root: {projectRoot}");
            }

            assetPath = assetPath.Replace("\\", "/").Trim();
            if (!assetPath.StartsWith("Assets/", StringComparison.OrdinalIgnoreCase))
            {
                assetPath = "Assets/" + assetPath.TrimStart('/');
            }
            Debug.Log($"Final assetPath: {assetPath}");

            string fullPath = Path.Combine(projectRoot, assetPath).Replace("\\", "/");
            if (!AssetDatabase.IsValidFolder(Path.GetDirectoryName(assetPath)) && !File.Exists(fullPath))
            {
                Debug.LogWarning($"Invalid asset path for AssetDatabase: {assetPath}");
                return assetPath;
            }

            string guid = AssetDatabase.AssetPathToGUID(assetPath);
            Debug.Log($"GUID: {guid}");

            if (string.IsNullOrEmpty(guid) || guid == "00000000000000000000000000000000")
            {
                Debug.LogWarning($"No valid GUID found for assetPath: {assetPath}");
                return assetPath;
            }

            AddressableAssetSettings settings = AddressableAssetSettingsDefaultObject.Settings;
            if (settings == null)
            {
                Debug.LogWarning("AddressableAssetSettings is not initialized.");
                return assetPath;
            }

            var entry = settings.FindAssetEntry(guid);
            if (entry != null)
            {
                Debug.Log($"Found Addressable entry: {entry.address}");
                return entry.address;
            }
            else
            {
                Debug.LogWarning($"Asset not Addressable: {assetPath}. Returning relative path.");
                return assetPath;
            }
        }
        else if (command == "get_sprite_info")
        {
            string filePath = data.file_path;
            string assetPath = filePath.Replace("\\", "/");
            string projectRoot = Path.GetFullPath(Path.Combine(Application.dataPath, "..")).Replace("\\", "/").TrimEnd('/');
            if (assetPath.StartsWith(projectRoot, StringComparison.OrdinalIgnoreCase))
            {
                assetPath = assetPath.Substring(projectRoot.Length).TrimStart('/');
            }
            if (!assetPath.StartsWith("Assets/", StringComparison.OrdinalIgnoreCase))
            {
                assetPath = "Assets/" + assetPath.TrimStart('/');
            }

            TextureImporter importer = AssetImporter.GetAtPath(assetPath) as TextureImporter;
            if (importer == null || importer.spriteImportMode != SpriteImportMode.Multiple)
            {
                return "[]";
            }

            var assets = AssetDatabase.LoadAllAssetsAtPath(assetPath);

            var sprites = new List<string>();
            foreach (var obj in assets)
            {
                if (obj is Sprite sprite)
                {
                    sprites.Add(sprite.name);
                }
            }

            return JsonUtility.ToJson(new Wrapper<string> { items = sprites });
        }
        return null;
    }

    [System.Serializable]
    private class CommMessage
    {
        public string command;
        public CommData data;
        public string result;
    }

    [System.Serializable]
    private class CommData
    {
        public string file_path;
    }
}
"""
        with open(os.path.join(EDITOR_DATA, "EditorCommunication.cs"), 'w', encoding='utf-8') as f:
            f.write(code_str)

# Sound data management
sound_data = {'groups': {}}
texture_data = {'groups': {}}
gameobject_data = {'groups': {}}

def load_sound_data():
    """
    assets_sound.jsonを読み込む
    """
    global sound_data
    if os.path.exists(SOUND_JSON):
        with open(SOUND_JSON, 'r', encoding='utf-8') as f:
            sound_data = json.load(f)

def save_sound_data():
    """
    assets_sound.jsonを保存
    """
    with open(SOUND_JSON, 'w', encoding='utf-8') as f:
        json.dump(sound_data, f, ensure_ascii=False, indent=4)

def load_texture_data():
    """
    assets_texture.jsonを読み込む
    """
    global texture_data
    if os.path.exists(TEXTURE_JSON):
        with open(TEXTURE_JSON, 'r', encoding='utf-8') as f:
            texture_data = json.load(f)

def save_texture_data():
    """
    assets_texture.jsonを保存
    """
    with open(TEXTURE_JSON, 'w', encoding='utf-8') as f:
        json.dump(texture_data, f, ensure_ascii=False, indent=4)

def load_gameobject_data():
    """
    assets_gameobject.jsonを読み込む
    """
    global gameobject_data
    if os.path.exists(GAMEOBJECT_JSON):
        with open(GAMEOBJECT_JSON, 'r', encoding='utf-8') as f:
            gameobject_data = json.load(f)

def save_gameobject_data():
    """
    assets_gameobject.jsonを保存
    """
    with open(GAMEOBJECT_JSON, 'w', encoding='utf-8') as f:
        json.dump(gameobject_data, f, ensure_ascii=False, indent=4)

load_sound_data()
load_texture_data()
load_gameobject_data()

# Unity communication functions
def connect_to_unity():
    """
    UnityエディタとTCP接続を確立
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('localhost', 12345))
    return sock

def send_to_unity(command, data=None):
    """
    Unityエディタにコマンドを送信
    """
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
    """
    Unityプロジェクトのパスを取得
    """
    return send_to_unity('get_project_path')

def get_addressable_path(file_path):
    """
    アドレス指定可能なパスを取得
    """
    return send_to_unity('get_addressable_path', {'file_path': file_path})

def get_sprite_info(file_path):
    """
    スプライト情報を取得
    """
    return send_to_unity('get_sprite_info', {'file_path': file_path})

def select_file(initial_dir, filetypes):
    """
    ファイル選択ダイアログを表示
    """
    root = tk.Tk()
    root.withdraw()
    file_path = filedialog.askopenfilename(initialdir=initial_dir, filetypes=filetypes)
    root.destroy()
    return file_path if file_path else None

# Sound data management
def get_sound_data():
    """
    サウンドデータを取得
    """
    return sound_data

def add_sound_group(group_name):
    """
    サウンドグループを追加
    """
    if group_name and group_name not in sound_data['groups']:
        sound_data['groups'][group_name] = []
        save_sound_data()

def delete_sound_group(group_name):
    """
    サウンドグループを削除
    """
    sound_data['groups'].pop(group_name, None)
    save_sound_data()

def add_sound(group_name, name, desc, volume, sound_type):
    """
    サウンドをグループに追加
    """
    project_path = get_unity_project_path()
    if not project_path:
        raise Exception("Unityプロジェクトのパスを取得できませんでした。")
    file_path = select_file(project_path, [("音声ファイル", "*.mp3 *.wav")])
    if not file_path:
        raise Exception("ファイルが選択されていません。")
    addr_path = get_addressable_path(file_path)
    if not addr_path:
        raise Exception("アドレス指定可能なパスを取得できませんでした。")
    sound_data['groups'][group_name].append({
        'name': name, 
        'desc': desc, 
        'path': addr_path,
        'absolute_path': os.path.abspath(file_path),
        'volume': volume, 
        'type': sound_type
    })
    save_sound_data()

def delete_sound(group_name, index):
    """
    サウンドをグループから削除
    """
    del sound_data['groups'][group_name][index]
    save_sound_data()

def generate_sound_csharp():
    """
    サウンド関連のC#コードとJSONを生成
    - SoundEnums.cs, SoundCore.cs, SoundDatabase.cs を生成
    - assets_sound.json を更新
    - ENUM_DIR/Sound/Sound.json を生成
    """
    # SoundEnums.cs
    with open(os.path.join(SOUND_DATA, 'SoundEnums.cs'), 'w', encoding='utf-8') as f:
        f.write('namespace GameCore.Sound {\n')
        f.write('    public enum SoundGroup { None')
        for group in sound_data['groups']:
            f.write(f', {group}')
        f.write(' ,Max\n  };\n')
        f.write('    public enum SoundType { SE, BGM };\n')
        f.write('    public enum SoundID { None')
        sound_id_counter = 1
        sound_id_map = {'None': 0}
        for group, sounds in sound_data['groups'].items():
            for sound in sounds:
                sound_id = f"{group}_{sound['name']}"
                if sound_id not in sound_id_map:
                    sound_id_map[sound_id] = sound_id_counter
                    f.write(f', {sound_id}')
                    sound_id_counter += 1
        f.write(' ,Max\n  };\n')
        f.write('}\n')

    # SoundCore.cs
    if not os.path.exists(os.path.join(SOUND_DATA, "SoundCore.cs")):
        code_str = """
using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using UnityEngine;
using Cysharp.Threading.Tasks;
using AddressableSystem;
using GameCore.SaveSystem;

namespace GameCore.Sound
{
    public class SoundCore : BaseSingleton<SoundCore>
    {
        private SoundDatabase database;
        private Dictionary<SoundGroup, Dictionary<SoundID, AddressableData<AudioClip>>> loadedClips =
            new Dictionary<SoundGroup, Dictionary<SoundID, AddressableData<AudioClip>>>();
        private AudioSource bgmSource;
        private AudioSource crossFadeTempSource;
        private List<AudioSource> sePool = new List<AudioSource>();
        private const int PoolSize = 30;
        private bool isLoadDatabase = false;
        public bool IsLoadDatabase => isLoadDatabase;

        private CancellationToken destroyToken;

        public void SetSystemBGMVolume()
        {
            if (bgmSource == null) return;
            if (!bgmSource.isPlaying) return;
            bgmSource.volume = SaveManagerCore.instance.SystemSettings.bgmVolume;
        }

        public void SetSystemSEVolume()
        {
            foreach(var clip in sePool)
            {
                clip.volume = SaveManagerCore.instance.SystemSettings.seVolume;
            }
        }

        public override void AwakeSingleton()
        {
            base.AwakeSingleton();
            instance = this;
            DontDestroyOnLoad(gameObject);

            // OnDestroy に紐づくキャンセルトークン
            destroyToken = this.GetCancellationTokenOnDestroy();

            bgmSource = gameObject.AddComponent<AudioSource>();
            bgmSource.loop = true;

            for (int i = 0; i < PoolSize; i++)
            {
                var source = gameObject.AddComponent<AudioSource>();
                source.playOnAwake = false;
                sePool.Add(source);
            }

            LoadDatabaseAsync().Forget();
        }

        private async UniTask LoadDatabaseAsync()
        {
            database = SoundBinaryReader.LoadSoundDatabaseFromBinary(SupportFiles.ALL_SOUND_BIN);
            if (database == null)
            {
                Debug.LogError("Failed to load SoundDatabase from binary.");
            }
            await UniTask.CompletedTask.AttachExternalCancellation(destroyToken);
            isLoadDatabase = true;
        }

        public void LoadGroup(SoundGroup group, GroupCategory groupCategory, Action action = null)
        {
            LoadGroupAsync(group, groupCategory, action).Forget();
        }

        public async UniTask LoadGroupAsync(SoundGroup group, GroupCategory groupCategory, Action action = null)
        {
            while (database == null)
            {
                await UniTask.Yield(cancellationToken: destroyToken);
            }
            if (loadedClips.ContainsKey(group)) return;
            var sounds = database.GroupedSoundsList.FirstOrDefault(data => data.Group == group);
            if (sounds == null) return;

            loadedClips[group] = new Dictionary<SoundID, AddressableData<AudioClip>>();
            var tasks = new List<UniTask>();

            foreach (var sound in sounds.Sounds)
            {
                var addressable = new AddressableData<AudioClip>(groupCategory, AssetCategory.Audio);
                AddressableDataCore.Instance.AddAddressableData(groupCategory, AssetCategory.Audio, addressable);
                tasks.Add(addressable.LoadAsync(sound.AddressablePath, clip =>
                {
                    if (addressable.IsLoadedAndSetup)
                    {
                        loadedClips[group][sound.SoundID] = addressable;
                    }
                }, ex =>
                {
                    Debug.LogError($"Failed to load audio clip for {sound.SoundID} at {sound.AddressablePath}: {ex.Message}");
                }).AttachExternalCancellation(destroyToken));
            }

            await UniTask.WhenAll(tasks);
            action?.Invoke();
        }

        public void UnloadGroup(SoundGroup group, GroupCategory groupCategory, Action action = null)
        {
            UnloadGroupAsync(group, groupCategory, action).Forget();
        }

        public async UniTask UnloadGroupAsync(SoundGroup group, GroupCategory groupCategory, Action action = null)
        {
            if (!loadedClips.TryGetValue(group, out var clips)) return;

            foreach (var addressable in clips.Values)
            {
                addressable.Release();
            }
            loadedClips.Remove(group);
            AddressableDataCore.Instance.ReleaseCategory(groupCategory, AssetCategory.Audio);
            action?.Invoke();
            await UniTask.CompletedTask.AttachExternalCancellation(destroyToken);
        }

        public void PlaySE(SoundGroup group, SoundID id, float volume = 1.0f, bool is3D = false, Vector3 position = default, float maxDistance = 500f)
        {
            PlaySEInternal(group, id, volume, is3D, position, maxDistance, async: true).Forget();
        }

        public async UniTask PlaySEAsync(SoundGroup group, SoundID id, float volume = 1.0f, bool is3D = false, Vector3 position = default, float maxDistance = 500f)
        {
            await PlaySEInternal(group, id, volume, is3D, position, maxDistance, async: true);
        }

        private async UniTask PlaySEInternal(SoundGroup group, SoundID id, float volume, bool is3D, Vector3 position, float maxDistance, bool async)
        {
            if (!TryGetClipAndData(group, id, out AddressableData<AudioClip> addressable, out SoundDatabase.SoundData data) || data.Type != SoundType.SE) return;

            var source = GetPooledSource();
            if (source == null) return;

            source.clip = addressable.GetAddressableObjectResult();
            source.volume = (data.BaseVolume * volume) * SaveManagerCore.instance.SystemSettings.seVolume;
            source.loop = false;
            source.spatialBlend = is3D ? 1f : 0f;
            source.maxDistance = maxDistance;
            if (is3D) source.transform.position = position;

            source.Play();

            if (async)
            {
                await UniTask.WaitUntil(() => !source.isPlaying, cancellationToken: destroyToken);
                ResetSource(source);
            }
        }

        public void PlayBGM(SoundGroup group, SoundID id, float volume = 1.0f, float fadeTime = 0f)
        {
            PlayBGMAsync(group, id, volume, fadeTime).Forget();
        }

        public async UniTask PlayBGMAsync(SoundGroup group, SoundID id, float volume = 1.0f, float fadeTime = 0f)
        {
            if (!TryGetClipAndData(group, id, out AddressableData<AudioClip> addressable, out SoundDatabase.SoundData data) || data.Type != SoundType.BGM) return;

            if (bgmSource.isPlaying && fadeTime > 0)
            {
                await FadeOutAsync(fadeTime);
            }

            bgmSource.clip = addressable.GetAddressableObjectResult();
            bgmSource.volume = 0f;
            bgmSource.Play();

            float fadeVolue = (data.BaseVolume * volume) * SaveManagerCore.instance.SystemSettings.bgmVolume;

            if (fadeTime > 0)
            {
                await FadeInAsync(fadeVolue, fadeTime);
            }
            else
            {
                bgmSource.volume = fadeVolue;
            }
        }

        public void FadeOutBGM(float fadeTime)
        {
            FadeOutAsync(fadeTime).Forget();
        }

        public async UniTask FadeOutAsync(float fadeTime, Action action = null)
        {
            if (!bgmSource.isPlaying)
            {
                action?.Invoke();
                return;
            }

            float startVolume = bgmSource.volume;
            float timer = 0f;
            while (timer < fadeTime)
            {
                timer += Time.deltaTime;
                bgmSource.volume = Mathf.Lerp(startVolume, 0f, timer / fadeTime);
                if (fadeTime >= timer)
                {
                    bgmSource.volume = 0.0f;
                    break;
                }
                await UniTask.Yield(cancellationToken: destroyToken);
            }
            bgmSource.Stop();
            ResetSource(bgmSource);
            action?.Invoke();
        }

        private async UniTask FadeInAsync(float targetVolume, float fadeTime, Action action = null)
        {
            float timer = 0f;
            while (timer < fadeTime)
            {
                timer += Time.deltaTime;
                bgmSource.volume = Mathf.Lerp(0f, targetVolume, timer / fadeTime);
                if (fadeTime >= timer)
                {
                    bgmSource.volume = targetVolume;
                    break;
                }
                await UniTask.Yield(cancellationToken: destroyToken);
            }
            action?.Invoke();
        }

        public void CrossFadeBGM(SoundGroup group, SoundID id, float volume = 1.0f, float fadeTime = 1f)
        {
            CrossFadeBGMAsync(group, id, volume, fadeTime).Forget();
        }

        public async UniTask CrossFadeBGMAsync(SoundGroup group, SoundID id, float volume = 1.0f, float fadeTime = 1f)
        {
            if (!TryGetClipAndData(group, id, out AddressableData<AudioClip> addressable, out SoundDatabase.SoundData data) || data.Type != SoundType.BGM) return;

            crossFadeTempSource = gameObject.AddComponent<AudioSource>();
            crossFadeTempSource.loop = true;
            crossFadeTempSource.clip = addressable.GetAddressableObjectResult();
            crossFadeTempSource.volume = 0f;
            crossFadeTempSource.Play();

            float timer = 0f;
            float startBGMVolume = bgmSource.volume;

            while (timer < fadeTime)
            {
                timer += Time.deltaTime;
                float t = timer / fadeTime;
                bgmSource.volume = Mathf.Lerp(startBGMVolume, 0f, t);
                crossFadeTempSource.volume = Mathf.Lerp(0f, (data.BaseVolume * volume) * SaveManagerCore.instance.SystemSettings.bgmVolume, t);
                await UniTask.Yield(cancellationToken: destroyToken);
            }

            bgmSource.Stop();
            ResetSource(bgmSource);
            Destroy(bgmSource);
            bgmSource = crossFadeTempSource;
            crossFadeTempSource = null;
        }

        private bool TryGetClipAndData(SoundGroup group, SoundID id, out AddressableData<AudioClip> addressable, out SoundDatabase.SoundData data)
        {
            addressable = null;
            data = null;
            if (!loadedClips.TryGetValue(group, out var groupClips) || !groupClips.TryGetValue(id, out addressable)) return false;
            data = database.GroupedSoundsList.FirstOrDefault(g => g.Group == group)?.Sounds.FirstOrDefault(s => s.SoundID == id);
            return data != null && addressable.IsLoadedAndSetup;
        }

        private AudioSource GetPooledSource()
        {
            return sePool.FirstOrDefault(s => !s.isPlaying && s.clip == null);
        }

        private void ResetSource(AudioSource source)
        {
            source.Stop();
            source.clip = null;
            source.volume = 0f;
            source.spatialBlend = 0f;
        }

        private void Update()
        {
            sePool.RemoveAll(s => s == null);
            if (bgmSource == null) bgmSource = gameObject.AddComponent<AudioSource>();
        }

        private void OnDestroy()
        {
            // destroyToken 経由ですべての UniTask がキャンセルされるので
            // ここでは loadedClips の解放などに専念できる
            foreach (var group in loadedClips.Values)
            {
                foreach (var clip in group.Values)
                {
                    clip.Release();
                }
            }
            loadedClips.Clear();
        }
    }
}
"""
        with open(os.path.join(SOUND_DATA, "SoundCore.cs"), 'w', encoding='utf-8') as f:
            f.write(code_str)

    # SoundDatabase.cs
    if not os.path.exists(os.path.join(SOUND_DATA, 'SoundDatabase.cs')):
        code_str = """
using System.Collections.Generic;

namespace GameCore.Sound
{
    public class SoundDatabase
    {
        [System.Serializable]
        public class SoundData
        {
            private readonly string idName;
            private readonly string addressablePath;
            private readonly float baseVolume;
            private readonly SoundType type;
            private readonly SoundID soundID;
            public SoundData(SoundID soundID, string idName, string addressablePath, float baseVolume, SoundType type)
            {
                this.idName = idName;
                this.addressablePath = addressablePath;
                this.baseVolume = baseVolume;
                this.type = type;
                this.soundID = soundID;
            }
            public string IdName => idName;
            public string AddressablePath => addressablePath;
            public float BaseVolume => baseVolume;
            public SoundID SoundID => soundID;
            public SoundType Type => type;
        }
        [System.Serializable]
        public class GroupedSounds
        {
            private readonly SoundGroup group;
            private readonly List<SoundData> sounds;
            public GroupedSounds(SoundGroup group, List<SoundData> sounds)
            {
                this.group = group;
                this.sounds = sounds ?? new List<SoundData>();
            }
            public SoundGroup Group => group;
            public List<SoundData> Sounds => sounds;
        }
        private readonly List<GroupedSounds> groupedSounds;
        public SoundDatabase()
        {
            groupedSounds = new List<GroupedSounds>();
        }
        public List<GroupedSounds> GroupedSoundsList => groupedSounds;
    }
}
"""
        with open(os.path.join(SOUND_DATA, 'SoundDatabase.cs'), 'w', encoding='utf-8') as f:
            f.write(code_str)


        
    # ENUM_DIR/Sound ディレクトリを作成
    if not os.path.exists(os.path.join(ENUM_DIR, "Sound")):
        os.makedirs(os.path.join(ENUM_DIR, "Sound"))
    
    # Sound.json を生成
    with open(os.path.join(ENUM_DIR, "Sound", "Sound.json"), 'w', encoding='utf-8') as f:
        sound_id_list = []
        for group, sounds in sound_data['groups'].items():
            for sound in sounds:
                sound_id = f"{group}_{sound['name']}"
                sound_id_list.append({
                    'description': sound['desc'],
                    'id': sound_id_map[sound_id],
                    'property': sound_id,
                    'value': sound_id_map[sound_id]
                })
        json.dump(sound_id_list, f, ensure_ascii=False, indent=4)

def generate_sound_bin():
    """
    サウンドデータのバイナリファイルを生成
    """
    with open(os.path.join(SOUND_DATA, 'sound_data.bin'), 'wb') as f:
        groups = list(sound_data['groups'].keys())
        group_count = len(groups)
        f.write(struct.pack('i', group_count))
        offsets = [0] * group_count
        offset_pos = f.tell()
        f.write(struct.pack('i' * group_count, *offsets))
        current_offset = f.tell()

        sound_id_map = {'None': 0}
        sound_id_counter = 1
        for group, sounds in sound_data['groups'].items():
            for sound in sounds:
                sound_id = f"{group}_{sound['name']}"
                if sound_id not in sound_id_map:
                    sound_id_map[sound_id] = sound_id_counter
                    sound_id_counter += 1

        for i, group in enumerate(groups):
            offsets[i] = current_offset
            sounds = sound_data['groups'][group]
            f.write(struct.pack('i', len(sounds)))
            for sound in sounds:
                sound_id = sound_id_map.get(f"{group}_{sound['name']}", 0)
                f.write(struct.pack('i', sound_id))
                path_bytes = sound['path'].encode('utf-8') + b'\0'
                f.write(path_bytes)
                f.write(struct.pack('f', sound['volume']))
                type_byte = 0 if sound['type'] == 'SE' else 1
                f.write(struct.pack('B', type_byte))
            current_offset = f.tell()
        f.seek(offset_pos)
        f.write(struct.pack('i' * group_count, *offsets))

# Texture data management
def get_texture_data():
    """
    テクスチャデータを取得
    """
    return texture_data

def add_texture_group(group_name):
    """
    テクスチャグループを追加
    """
    if group_name and group_name not in texture_data['groups']:
        texture_data['groups'][group_name] = []
        save_texture_data()

def delete_texture_group(group_name):
    """
    テクスチャグループを削除
    """
    texture_data['groups'].pop(group_name, None)
    save_texture_data()

def add_texture(group_name, name, desc):
    """
    テクスチャをグループに追加
    """
    project_path = get_unity_project_path()
    if not project_path:
        raise Exception("Unityプロジェクトのパスを取得できませんでした。")
    file_path = select_file(project_path, [("画像ファイル", "*.png *.jpg *.jpeg")])
    if not file_path:
        raise Exception("ファイルが選択されていません。")
    addr_path = get_addressable_path(file_path)
    if not addr_path:
        raise Exception("アドレス指定可能なパスを取得できませんでした。")
    sprite_info_raw = get_sprite_info(file_path)
    sprite_info = []
    if sprite_info_raw:
        try:
            sprite_data = json.loads(sprite_info_raw)
            sprite_info = sprite_data.get('items', []) if isinstance(sprite_data, dict) else []
        except json.JSONDecodeError:
            print(f"スプライト情報の解析に失敗しました: {sprite_info_raw}")
    texture_data['groups'][group_name].append({
        'name': name, 
        'desc': desc, 
        'path': addr_path,
        'absolute_path': os.path.abspath(file_path),
        'sprites': sprite_info
    })
    save_texture_data()

def delete_texture(group_name, index):
    """
    テクスチャをグループから削除
    """
    del texture_data['groups'][group_name][index]
    save_texture_data()

def generate_texture_csharp():
    """
    テクスチャ関連のC#コードとJSONを生成
    - TextureEnums.cs を生成
    - assets_texture.json を更新
    - ENUM_DIR/Texture/TextureSpriteID.json を生成
    """
    # TextureEnums.cs
    with open(os.path.join(TEXTURE_DATA, 'TextureEnums.cs'), 'w', encoding='utf-8') as f:
        f.write('namespace GameCore.Texture {\n')
        f.write('    public enum TextureGroup { None')
        for group in texture_data['groups']:
            f.write(f', {group}')
        f.write(' ,Max\n  };\n')
        f.write('    public enum TextureID { None')
        texture_id_counter = 1
        texture_id_map = {'None': 0}
        for group, textures in texture_data['groups'].items():
            for texture in textures:
                texture_id = f"{group}_{texture['name']}"
                if texture_id not in texture_id_map:
                    texture_id_map[texture_id] = texture_id_counter
                    f.write(f', {texture_id}')
                    texture_id_counter += 1
        f.write(' ,Max\n  };\n')
        
        # SpriteID の生成
        f.write('    public enum SpriteID { None')
        sprite_id_counter = 1
        sprite_id_map = {'None': 0}
        for group, textures in texture_data['groups'].items():
            for texture in textures:
                texture_id = f"{group}_{texture['name']}"
                if len(texture.get('sprites', [])) <= 1:
                    for sprite in texture.get('sprites', []):
                        sprite_id = f"{group}_{texture['name']}_{sprite}"
                        if sprite_id not in sprite_id_map:
                            sprite_id_map[sprite_id] = sprite_id_counter
                            f.write(f', {sprite_id}')
                            sprite_id_counter += 1
                else:
                    sprite_id = texture_id
                    if sprite_id not in sprite_id_map:
                        sprite_id_map[sprite_id] = sprite_id_counter
                        f.write(f', {sprite_id}')
                        sprite_id_counter += 1
        f.write(' ,Max\n  };\n')
        
        # スプライトシート用の専用列挙型
        for group, textures in texture_data['groups'].items():
            for texture in textures:
                if len(texture.get('sprites', [])) > 1:
                    sprite_enum_name = f"{group}_{texture['name']}"
                    f.write(f'    public enum {sprite_enum_name} {{ None = -1')
                    sprite_id_counter = 0
                    for sprite in texture.get('sprites', []):
                        f.write(f', {sprite}')
                        sprite_id_counter += 1
                    f.write(' ,Max\n  };\n')
        
        f.write('}\n')

    # TextureCore.cs
    if not os.path.exists(os.path.join(TEXTURE_DATA, "TextureCore.cs")):
        code_str = """
using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using UnityEngine;
using Cysharp.Threading.Tasks;
using AddressableSystem;

namespace GameCore.Texture
{
    public class TextureCore : BaseSingleton<TextureCore>
    {
        private TextureDatabase database;
        private Dictionary<TextureGroup, Dictionary<TextureID, AddressableData<Texture2D>>> loadedTextures =
            new Dictionary<TextureGroup, Dictionary<TextureID, AddressableData<Texture2D>>>();
        private Dictionary<TextureGroup, Dictionary<SpriteID, AddressableData<IList<Sprite>>>> loadedSpriteArrays =
            new Dictionary<TextureGroup, Dictionary<SpriteID, AddressableData<IList<Sprite>>>>();
        private bool isLoadDatabase = false;
        public bool IsLoadDatabase => isLoadDatabase;
        private CancellationToken destroyToken;

        public override void AwakeSingleton()
        {
            base.AwakeSingleton();
            instance = this;
            DontDestroyOnLoad(gameObject);
            destroyToken = this.GetCancellationTokenOnDestroy();
            LoadDatabaseAsync().Forget();
        }

        private async UniTask LoadDatabaseAsync()
        {
            database = TextureBinaryReader.LoadTextureDatabaseFromBinary(SupportFiles.ALL_TEXTURE_BIN);
            if (database == null)
            {
                Debug.LogError("Failed to load TextureDatabase from binary.");
            }
            await UniTask.CompletedTask.AttachExternalCancellation(destroyToken);
            isLoadDatabase = true;
        }

        public void LoadGroup(TextureGroup group, GroupCategory groupCategory, Action action = null)
        {
            LoadGroupAsync(group, groupCategory, action).Forget();
        }

        public async UniTask LoadGroupAsync(TextureGroup group, GroupCategory groupCategory, Action action = null)
        {
            while (database == null)
            {
                await UniTask.Yield(cancellationToken: destroyToken);
            }
            if (loadedTextures.ContainsKey(group)) return;
            var textures = database.GroupedTexturesList.FirstOrDefault(data => data.Group == group);
            if (textures == null) return;

            loadedTextures[group] = new Dictionary<TextureID, AddressableData<Texture2D>>();
            loadedSpriteArrays[group] = new Dictionary<SpriteID, AddressableData<IList<Sprite>>>();
            var tasks = new List<UniTask>();

            foreach (var texture in textures.Textures)
            {
                var addressableTexture = new AddressableData<Texture2D>(groupCategory, AssetCategory.Texture);
                AddressableDataCore.Instance.AddAddressableData(groupCategory, AssetCategory.Texture, addressableTexture);
                tasks.Add(addressableTexture.LoadAsync(texture.AddressablePath, tex =>
                {
                    if (addressableTexture.IsLoadedAndSetup)
                    {
                        loadedTextures[group][texture.TextureID] = addressableTexture;
                    }
                }, ex =>
                {
                    Debug.LogError($"Failed to load texture for {texture.TextureID} at {texture.AddressablePath}: {ex.Message}");
                }).AttachExternalCancellation(destroyToken));

                if (texture.Sprites != null && texture.Sprites.Count > 1)
                {
                    var addressableSpriteArray = new AddressableData<IList<Sprite>>(groupCategory, AssetCategory.Sprite);
                    AddressableDataCore.Instance.AddAddressableData(groupCategory, AssetCategory.Sprite, addressableSpriteArray);
                    SpriteID spriteId = (SpriteID)Enum.Parse(typeof(SpriteID), $"{group}_{texture.IdName}");
                    tasks.Add(addressableSpriteArray.LoadArrayAsync(texture.AddressablePath, sprites =>
                    {
                        if (addressableSpriteArray.IsLoadedAndSetup)
                        {
                            loadedSpriteArrays[group][spriteId] = addressableSpriteArray;
                        }
                    }, ex =>
                    {
                        Debug.LogError($"Failed to load sprite array for {spriteId} at {texture.AddressablePath}: {ex.Message}");
                    }).AttachExternalCancellation(destroyToken));
                }
                else if (texture.Sprites != null && texture.Sprites.Count == 1)
                {
                    var addressableSprite = new AddressableData<Sprite>(groupCategory, AssetCategory.Sprite);
                    AddressableDataCore.Instance.AddAddressableData(groupCategory, AssetCategory.Sprite, addressableSprite);
                    SpriteID spriteId = (SpriteID)Enum.Parse(typeof(SpriteID), $"{group}_{texture.IdName}_{texture.Sprites[0].IdName}");
                    tasks.Add(addressableSprite.LoadAsync($"{texture.AddressablePath}#{texture.Sprites[0].IdName}", spr =>
                    {
                        if (addressableSprite.IsLoadedAndSetup)
                        {
                            loadedSpriteArrays[group][spriteId] = new AddressableData<IList<Sprite>>(groupCategory, AssetCategory.Sprite)
                            {
                                typedAddressableArray = new List<Sprite> { spr },
                                isLoaded = true,
                                isSetup = true
                            };
                        }
                    }, ex =>
                    {
                        Debug.LogError($"Failed to load sprite for {spriteId} at {texture.AddressablePath}: {ex.Message}");
                    }).AttachExternalCancellation(destroyToken));
                }
            }

            await UniTask.WhenAll(tasks);
            action?.Invoke();
        }

        public void UnloadGroup(TextureGroup group, GroupCategory groupCategory, Action action = null)
        {
            UnloadGroupAsync(group, groupCategory, action).Forget();
        }

        public async UniTask UnloadGroupAsync(TextureGroup group, GroupCategory groupCategory, Action action = null)
        {
            if (!loadedTextures.TryGetValue(group, out var textures)) return;

            foreach (var addressable in textures.Values)
            {
                addressable.Release();
            }
            foreach (var addressable in loadedSpriteArrays[group].Values)
            {
                addressable.Release();
            }
            loadedTextures.Remove(group);
            loadedSpriteArrays.Remove(group);
            AddressableDataCore.Instance.ReleaseCategory(groupCategory, AssetCategory.Texture);
            AddressableDataCore.Instance.ReleaseCategory(groupCategory, AssetCategory.Sprite);
            action?.Invoke();
            await UniTask.CompletedTask.AttachExternalCancellation(destroyToken);
        }

        public Texture2D GetTexture(TextureGroup group, TextureID id)
        {
            if (loadedTextures.TryGetValue(group, out var groupTextures) && groupTextures.TryGetValue(id, out var addressable))
            {
                return addressable.GetAddressableObjectResult();
            }
            return null;
        }

        public Sprite GetSprite<TEnum>(TextureGroup group, TEnum spriteId, int spriteIndex = -1) where TEnum : Enum
        {
            if (loadedSpriteArrays.TryGetValue(group, out var groupSprites) && 
                groupSprites.TryGetValue((SpriteID)Enum.Parse(typeof(SpriteID), spriteId.ToString()), out var addressable))
            {
                if (spriteIndex >= 0 && spriteIndex < addressable.GetAddressableObjectResult().Count)
                {
                    return addressable.GetAddressableObjectResult()[spriteIndex];
                }
                return addressable.GetAddressableObjectResult().Count > 0 ? addressable.GetAddressableObjectResult()[0] : null;
            }
            return null;
        }

        private void OnDestroy()
        {
            foreach (var group in loadedTextures.Values)
            {
                foreach (var texture in group.Values)
                {
                    texture.Release();
                }
            }
            foreach (var group in loadedSpriteArrays.Values)
            {
                foreach (var spriteArray in group.Values)
                {
                    spriteArray.Release();
                }
            }
            loadedTextures.Clear();
            loadedSpriteArrays.Clear();
        }
    }
}
"""
        with open(os.path.join(TEXTURE_DATA, "TextureCore.cs"), 'w', encoding='utf-8') as f:
            f.write(code_str)

    # TextureDatabase.cs
    if not os.path.exists(os.path.join(TEXTURE_DATA, 'TextureDatabase.cs')):
        code_str = """
using System.Collections.Generic;

namespace GameCore.Texture
{
    public class TextureDatabase
    {
        [System.Serializable]
        public class SpriteData
        {
            private readonly string idName;
            private readonly string addressablePath;
            private readonly SpriteID spriteID;
            public SpriteData(SpriteID spriteID, string idName, string addressablePath)
            {
                this.idName = idName;
                this.addressablePath = addressablePath;
                this.spriteID = spriteID;
            }
            public string IdName => idName;
            public string AddressablePath => addressablePath;
            public SpriteID SpriteID => spriteID;
        }

        [System.Serializable]
        public class TextureData
        {
            private readonly string idName;
            private readonly string addressablePath;
            private readonly TextureID textureID;
            private readonly List<SpriteData> sprites;
            public TextureData(TextureID textureID, string idName, string addressablePath, List<SpriteData> sprites)
            {
                this.idName = idName;
                this.addressablePath = addressablePath;
                this.textureID = textureID;
                this.sprites = sprites ?? new List<SpriteData>();
            }
            public string IdName => idName;
            public string AddressablePath => addressablePath;
            public TextureID TextureID => textureID;
            public List<SpriteData> Sprites => sprites;
        }

        [System.Serializable]
        public class GroupedTextures
        {
            private readonly TextureGroup group;
            private readonly List<TextureData> textures;
            public GroupedTextures(TextureGroup group, List<TextureData> textures)
            {
                this.group = group;
                this.textures = textures ?? new List<TextureData>();
            }
            public TextureGroup Group => group;
            public List<TextureData> Textures => textures;
        }

        private readonly List<GroupedTextures> groupedTextures;
        public TextureDatabase()
        {
            groupedTextures = new List<GroupedTextures>();
        }
        public List<GroupedTextures> GroupedTexturesList => groupedTextures;
    }
}
"""
        with open(os.path.join(TEXTURE_DATA, 'TextureDatabase.cs'), 'w', encoding='utf-8') as f:
            f.write(code_str)

    # ENUM_DIR/Texture ディレクトリを作成
    if not os.path.exists(os.path.join(ENUM_DIR, "Texture")):
        os.makedirs(os.path.join(ENUM_DIR, "Texture"))
    
    # TextureSprite.json を生成（TextureとSpriteを統合）
    with open(os.path.join(ENUM_DIR, "Texture", "TextureSprite.json"), 'w', encoding='utf-8') as f:
        texture_sprite_id_list = []
        # TextureおよびSpriteのエントリ
        for group, textures in texture_data['groups'].items():
            for texture in textures:
                texture_id = f"{group}_{texture['name']}"
                if len(texture.get('sprites', [])) <= 1:
                    # spritesが1つ以下の場合、Textureのエントリのみ追加
                    texture_sprite_id_list.append({
                        'description': texture['desc'],
                        'id': texture_id_map[texture_id],
                        'property': texture_id,
                        'value': texture_id_map[texture_id]
                    })
                else:
                    # spritesが2つ以上の場合、各スプライトごとにエントリを追加
                    for sprite in texture.get('sprites', []):
                        sprite_id = f"{group}_{texture['name']}_{sprite}"
                        texture_sprite_id_list.append({
                            'description': f"{texture['desc']}(Sprite:{sprite})",
                            'id': sprite_id_map[sprite_id],
                            'property': sprite_id,
                            'value': sprite_id_map[sprite_id]
                        })
        json.dump(texture_sprite_id_list, f, ensure_ascii=False, indent=4)

def generate_texture_bin():
    """
    テクスチャデータのバイナリファイルを生成
    """
    with open(os.path.join(TEXTURE_DATA, 'texture_data.bin'), 'wb') as f:
        groups = list(texture_data['groups'].keys())
        group_count = len(groups)
        f.write(struct.pack('i', group_count))
        offsets = [0] * group_count
        offset_pos = f.tell()
        f.write(struct.pack('i' * group_count, *offsets))
        current_offset = f.tell()

        texture_id_map = {'None': 0}
        sprite_id_map = {'None': 0}
        texture_id_counter = 1
        sprite_id_counter = 1
        for group, textures in texture_data['groups'].items():
            for texture in textures:
                texture_id = f"{group}_{texture['name']}"
                if texture_id not in texture_id_map:
                    texture_id_map[texture_id] = texture_id_counter
                    texture_id_counter += 1
                if len(texture.get('sprites', [])) <= 1:
                    for sprite in texture.get('sprites', []):
                        sprite_id = f"{group}_{texture['name']}_{sprite}"
                        if sprite_id not in sprite_id_map:
                            sprite_id_map[sprite_id] = sprite_id_counter
                            sprite_id_counter += 1
                else:
                    sprite_id = texture_id
                    if sprite_id not in sprite_id_map:
                        sprite_id_map[sprite_id] = sprite_id_counter
                        sprite_id_counter += 1

        for i, group in enumerate(groups):
            offsets[i] = current_offset
            textures = texture_data['groups'][group]
            f.write(struct.pack('i', len(textures)))
            for texture in textures:
                texture_id = texture_id_map.get(f"{group}_{texture['name']}", 0)
                f.write(struct.pack('i', texture_id))
                path_bytes = texture['path'].encode('utf-8') + b'\0'
                f.write(path_bytes)
                sprites = texture.get('sprites', [])
                f.write(struct.pack('i', len(sprites)))
                for sprite in sprites:
                    sprite_id = sprite_id_map.get(f"{group}_{texture['name']}_{sprite}", sprite_id_map.get(f"{group}_{texture['name']}", 0))
                    f.write(struct.pack('i', sprite_id))
                    sprite_path = f"{texture['path']}#{sprite}".encode('utf-8') + b'\0'
                    f.write(sprite_path)
            current_offset = f.tell()
        f.seek(offset_pos)
        f.write(struct.pack('i' * group_count, *offsets))

# GameObject data management
def get_gameobject_data():
    """
    ゲームオブジェクトデータを取得
    """
    return gameobject_data

def add_gameobject_group(group_name):
    """
    ゲームオブジェクトグループを追加
    """
    if group_name and group_name not in gameobject_data['groups']:
        gameobject_data['groups'][group_name] = []
        save_gameobject_data()

def delete_gameobject_group(group_name):
    """
    ゲームオブジェクトグループを削除
    """
    gameobject_data['groups'].pop(group_name, None)
    save_gameobject_data()

def add_gameobject(group_name, name, desc):
    """
    ゲームオブジェクトをグループに追加
    """
    project_path = get_unity_project_path()
    if not project_path:
        raise Exception("Unityプロジェクトのパスを取得できませんでした。")
    file_path = select_file(project_path, [("プレハブファイル", "*.prefab")])
    if not file_path:
        raise Exception("ファイルが選択されていません。")
    addr_path = get_addressable_path(file_path)
    if not addr_path:
        raise Exception("アドレス指定可能なパスを取得できませんでした。")
    gameobject_data['groups'][group_name].append({
        'name': name, 
        'desc': desc, 
        'path': addr_path,
        'absolute_path': os.path.abspath(file_path)
    })
    save_gameobject_data()

def delete_gameobject(group_name, index):
    """
    ゲームオブジェクトをグループから削除
    """
    del gameobject_data['groups'][group_name][index]
    save_gameobject_data()

def generate_gameobject_csharp():
    """
    ゲームオブジェクト関連のC#コードとJSONを生成
    - GameObjectEnums.cs を生成
    - assets_gameobject.json を更新
    - ENUM_DIR/GameObject/GameObject.json を生成
    """
    # GameObjectEnums.cs
    with open(os.path.join(GAMEOBJECT_DATA, 'GameObjectEnums.cs'), 'w', encoding='utf-8') as f:
        f.write('namespace GameCore.GameObject {\n')
        f.write('    public enum GameObjectGroup { None')
        for group in gameobject_data['groups']:
            f.write(f', {group}')
        f.write(' ,Max\n  };\n')
        f.write('    public enum GameObjectID { None')
        gameobject_id_counter = 1
        gameobject_id_map = {'None': 0}
        for group, gameobjects in gameobject_data['groups'].items():
            for go in gameobjects:
                go_id = f"{group}_{go['name']}"
                if go_id not in gameobject_id_map:
                    gameobject_id_map[go_id] = gameobject_id_counter
                    f.write(f', {go_id}')
                    gameobject_id_counter += 1
        f.write(' ,Max\n  };\n')
        f.write('}\n')

    # GameObjectCore.cs
    if not os.path.exists(os.path.join(GAMEOBJECT_DATA, "GameObjectCore.cs")):
        code_str = """
using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using UnityEngine;
using Cysharp.Threading.Tasks;
using AddressableSystem;

namespace GameCore.GameObject
{
    public class GameObjectCore : BaseSingleton<GameObjectCore>
    {
        private GameObjectDatabase database;
        private Dictionary<GameObjectGroup, Dictionary<GameObjectID, AddressableData<GameObject>>> loadedGameObjects =
            new Dictionary<GameObjectGroup, Dictionary<GameObjectID, AddressableData<GameObject>>>();
        private bool isLoadDatabase = false;
        public bool IsLoadDatabase => isLoadDatabase;
        private CancellationToken destroyToken;

        public override void AwakeSingleton()
        {
            base.AwakeSingleton();
            instance = this;
            DontDestroyOnLoad(gameObject);
            destroyToken = this.GetCancellationTokenOnDestroy();
            LoadDatabaseAsync().Forget();
        }

        private async UniTask LoadDatabaseAsync()
        {
            database = GameObjectBinaryReader.LoadGameObjectDatabaseFromBinary(SupportFiles.ALL_GAMEOBJECT_BIN);
            if (database == null)
            {
                Debug.LogError("Failed to load GameObjectDatabase from binary.");
            }
            await UniTask.CompletedTask.AttachExternalCancellation(destroyToken);
            isLoadDatabase = true;
        }

        public void LoadGroup(GameObjectGroup group, GroupCategory groupCategory, Action action = null)
        {
            LoadGroupAsync(group, groupCategory, action).Forget();
        }

        public async UniTask LoadGroupAsync(GameObjectGroup group, GroupCategory groupCategory, Action action = null)
        {
            while (database == null)
            {
                await UniTask.Yield(cancellationToken: destroyToken);
            }
            if (loadedGameObjects.ContainsKey(group)) return;
            var gameObjects = database.GroupedGameObjectsList.FirstOrDefault(data => data.Group == group);
            if (gameObjects == null) return;

            loadedGameObjects[group] = new Dictionary<GameObjectID, AddressableData<GameObject>>();
            var tasks = new List<UniTask>();

            foreach (var go in gameObjects.GameObjects)
            {
                var addressable = new AddressableData<GameObject>(groupCategory, AssetCategory.GameObject);
                AddressableDataCore.Instance.AddAddressableData(groupCategory, AssetCategory.GameObject, addressable);
                tasks.Add(addressable.LoadAsync(go.AddressablePath, obj =>
                {
                    if (addressable.IsLoadedAndSetup)
                    {
                        loadedGameObjects[group][go.GameObjectID] = addressable;
                    }
                }, ex =>
                {
                    Debug.LogError($"Failed to load gameobject for {go.GameObjectID} at {go.AddressablePath}: {ex.Message}");
                }).AttachExternalCancellation(destroyToken));
            }

            await UniTask.WhenAll(tasks);
            action?.Invoke();
        }

        public void UnloadGroup(GameObjectGroup group, GroupCategory groupCategory, Action action = null)
        {
            UnloadGroupAsync(group, groupCategory, action).Forget();
        }

        public async UniTask UnloadGroupAsync(GameObjectGroup group, GroupCategory groupCategory, Action action = null)
        {
            if (!loadedGameObjects.TryGetValue(group, out var gameObjects)) return;

            foreach (var addressable in gameObjects.Values)
            {
                addressable.Release();
            }
            loadedGameObjects.Remove(group);
            AddressableDataCore.Instance.ReleaseCategory(groupCategory, AssetCategory.GameObject);
            action?.Invoke();
            await UniTask.CompletedTask.AttachExternalCancellation(destroyToken);
        }

        public GameObject GetGameObject(GameObjectGroup group, GameObjectID id)
        {
            if (loadedGameObjects.TryGetValue(group, out var groupGameObjects) && groupGameObjects.TryGetValue(id, out var addressable))
            {
                return addressable.GetAddressableObjectResult();
            }
            return null;
        }

        private void OnDestroy()
        {
            foreach (var group in loadedGameObjects.Values)
            {
                foreach (var go in group.Values)
                {
                    go.Release();
                }
            }
            loadedGameObjects.Clear();
        }
    }
}
"""
        with open(os.path.join(GAMEOBJECT_DATA, "GameObjectCore.cs"), 'w', encoding='utf-8') as f:
            f.write(code_str)

    # GameObjectDatabase.cs
    if not os.path.exists(os.path.join(GAMEOBJECT_DATA, 'GameObjectDatabase.cs')):
        code_str = """
using System.Collections.Generic;

namespace GameCore.GameObject
{
    public class GameObjectDatabase
    {
        [System.Serializable]
        public class GameObjectData
        {
            private readonly string idName;
            private readonly string addressablePath;
            private readonly GameObjectID gameObjectID;
            public GameObjectData(GameObjectID gameObjectID, string idName, string addressablePath)
            {
                this.idName = idName;
                this.addressablePath = addressablePath;
                this.gameObjectID = gameObjectID;
            }
            public string IdName => idName;
            public string AddressablePath => addressablePath;
            public GameObjectID GameObjectID => gameObjectID;
        }

        [System.Serializable]
        public class GroupedGameObjects
        {
            private readonly GameObjectGroup group;
            private readonly List<GameObjectData> gameObjects;
            public GroupedGameObjects(GameObjectGroup group, List<GameObjectData> gameObjects)
            {
                this.group = group;
                this.gameObjects = gameObjects ?? new List<GameObjectData>();
            }
            public GameObjectGroup Group => group;
            public List<GameObjectData> GameObjects => gameObjects;
        }

        private readonly List<GroupedGameObjects> groupedGameObjects;
        public GameObjectDatabase()
        {
            groupedGameObjects = new List<GroupedGameObjects>();
        }
        public List<GroupedGameObjects> GroupedGameObjectsList => groupedGameObjects;
    }
}
"""
        with open(os.path.join(GAMEOBJECT_DATA, 'GameObjectDatabase.cs'), 'w', encoding='utf-8') as f:
            f.write(code_str)


    # ENUM_DIR/GameObject ディレクトリを作成
    if not os.path.exists(os.path.join(ENUM_DIR, "GameObject")):
        os.makedirs(os.path.join(ENUM_DIR, "GameObject"))
    
    # GameObject.json を生成
    with open(os.path.join(ENUM_DIR, "GameObject", "GameObject.json"), 'w', encoding='utf-8') as f:
        gameobject_id_list = []
        for group, gameobjects in gameobject_data['groups'].items():
            for go in gameobjects:
                go_id = f"{group}_{go['name']}"
                gameobject_id_list.append({
                    'description': go['desc'],
                    'id': gameobject_id_map[go_id],
                    'property': go_id,
                    'value': gameobject_id_map[go_id]
                })
        json.dump(gameobject_id_list, f, ensure_ascii=False, indent=4)

def generate_gameobject_bin():
    """
    ゲームオブジェクトデータのバイナリファイルを生成
    """
    with open(os.path.join(GAMEOBJECT_DATA, 'gameobject_data.bin'), 'wb') as f:
        groups = list(gameobject_data['groups'].keys())
        group_count = len(groups)
        f.write(struct.pack('i', group_count))
        offsets = [0] * group_count
        offset_pos = f.tell()
        f.write(struct.pack('i' * group_count, *offsets))
        current_offset = f.tell()

        gameobject_id_map = {'None': 0}
        gameobject_id_counter = 1
        for group, gameobjects in gameobject_data['groups'].items():
            for go in gameobjects:
                go_id = f"{group}_{go['name']}"
                if go_id not in gameobject_id_map:
                    gameobject_id_map[go_id] = gameobject_id_counter
                    gameobject_id_counter += 1

        for i, group in enumerate(groups):
            offsets[i] = current_offset
            gameobjects = gameobject_data['groups'][group]
            f.write(struct.pack('i', len(gameobjects)))
            for go in gameobjects:
                go_id = gameobject_id_map.get(f"{group}_{go['name']}", 0)
                f.write(struct.pack('i', go_id))
                path_bytes = go['path'].encode('utf-8') + b'\0'
                f.write(path_bytes)
            current_offset = f.tell()
        f.seek(offset_pos)
        f.write(struct.pack('i' * group_count, *offsets))

def get_texture_file_path(group_name, index):
    """
    テクスチャの絶対パスを取得
    """
    if group_name in texture_data['groups'] and index < len(texture_data['groups'][group_name]):
        return texture_data['groups'][group_name][index]['absolute_path']
    return None

def get_sound_file_path(group_name, index):
    """
    サウンドの絶対パスを取得
    """
    if group_name in sound_data['groups'] and index < len(sound_data['groups'][group_name]):
        return sound_data['groups'][group_name][index]['absolute_path']
    return None

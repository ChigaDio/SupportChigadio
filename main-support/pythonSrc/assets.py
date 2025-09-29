import json
import os
import socket
import struct
import sys
import tkinter as tk
from tkinter import filedialog
from PIL import Image
import shutil

# 実行可能ファイルのディレクトリを取得（PyInstaller対応）
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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

    # Sound, Texture, GameObjectのエントリを追加
    with open(enum_list_path, 'r+', encoding='utf-8') as f:
        enum_list = json.load(f)
        existing_names = [e['name'] for e in enum_list]
        new_entries = [
            {'name': 'SoundID', 'path': os.path.join(SOUND_DATA, 'SoundID.json')},
            {'name': 'TextureID', 'path': os.path.join(TEXTURE_DATA, 'TextureID.json')},
            {'name': 'GameObjectID', 'path': os.path.join(GAMEOBJECT_DATA, 'GameObjectID.json')}
        ]
        for entry in new_entries:
            if entry['name'] not in existing_names:
                enum_list.append({'name': entry['name']})
                os.makedirs(os.path.dirname(entry['path']), exist_ok=True)
                with open(entry['path'], 'w', encoding='utf-8') as ef:
                    json.dump([], ef)
        f.seek(0)
        json.dump(enum_list, f, ensure_ascii=False, indent=4)

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

public class EditorCommunication : EditorWindow
{
    private static TcpListener listener;
    private static Thread listenerThread;
    private static volatile bool pendingCommand;
    private static string pendingCommandName;
    private static CommData pendingCommandData;
    private static string commandResult;

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

            string projectRoot = Path.GetFullPath(Path.Combine(Application.dataPath, "..")).Replace("\\\\", "/").TrimEnd('/');
            Debug.Log($"Project root (normalized): {projectRoot}");

            string normalizedFilePath = filePath.Replace("\\\\", "/").TrimEnd('/');
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

            assetPath = assetPath.Replace("\\\\", "/").Trim();
            if (!assetPath.StartsWith("Assets/", StringComparison.OrdinalIgnoreCase))
            {
                assetPath = "Assets/" + assetPath.TrimStart('/');
            }
            Debug.Log($"Final assetPath: {assetPath}");

            string fullPath = Path.Combine(projectRoot, assetPath).Replace("\\\\", "/");
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
            string assetPath = filePath.Replace("\\\\", "/");
            string projectRoot = Path.GetFullPath(Path.Combine(Application.dataPath, "..")).Replace("\\\\", "/").TrimEnd('/');
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

            var sprites = new List<string>();
            foreach (var sprite in importer.spritesheet)
            {
                sprites.Add(sprite.name);
            }
            return JsonUtility.ToJson(sprites);
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
        private Dictionary<TextureGroup, Dictionary<SpriteID, AddressableData<Sprite>>> loadedSprites =
            new Dictionary<TextureGroup, Dictionary<SpriteID, AddressableData<Sprite>>>();
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
            loadedSprites[group] = new Dictionary<SpriteID, AddressableData<Sprite>>();
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

                foreach (var sprite in texture.Sprites)
                {
                    var addressableSprite = new AddressableData<Sprite>(groupCategory, AssetCategory.Sprite);
                    AddressableDataCore.Instance.AddAddressableData(groupCategory, AssetCategory.Sprite, addressableSprite);
                    tasks.Add(addressableSprite.LoadAsync(sprite.AddressablePath, spr =>
                    {
                        if (addressableSprite.IsLoadedAndSetup)
                        {
                            loadedSprites[group][sprite.SpriteID] = addressableSprite;
                        }
                    }, ex =>
                    {
                        Debug.LogError($"Failed to load sprite for {sprite.SpriteID} at {sprite.AddressablePath}: {ex.Message}");
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
            foreach (var addressable in loadedSprites[group].Values)
            {
                addressable.Release();
            }
            loadedTextures.Remove(group);
            loadedSprites.Remove(group);
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

        public Sprite GetSprite(TextureGroup group, SpriteID id)
        {
            if (loadedSprites.TryGetValue(group, out var groupSprites) && groupSprites.TryGetValue(id, out var addressable))
            {
                return addressable.GetAddressableObjectResult();
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
            foreach (var group in loadedSprites.Values)
            {
                foreach (var sprite in group.Values)
                {
                    sprite.Release();
                }
            }
            loadedTextures.Clear();
            loadedSprites.Clear();
        }
    }
}
"""
        with open(os.path.join(TEXTURE_DATA, "TextureCore.cs"), 'w', encoding='utf-8') as f:
            f.write(code_str)

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

# Sound data management
sound_data = {'groups': {}}
texture_data = {'groups': {}}
gameobject_data = {'groups': {}}

def load_sound_data():
    global sound_data
    if os.path.exists(SOUND_JSON):
        with open(SOUND_JSON, 'r', encoding='utf-8') as f:
            sound_data = json.load(f)

def save_sound_data():
    with open(SOUND_JSON, 'w', encoding='utf-8') as f:
        json.dump(sound_data, f, ensure_ascii=False, indent=4)

def load_texture_data():
    global texture_data
    if os.path.exists(TEXTURE_JSON):
        with open(TEXTURE_JSON, 'r', encoding='utf-8') as f:
            texture_data = json.load(f)

def save_texture_data():
    with open(TEXTURE_JSON, 'w', encoding='utf-8') as f:
        json.dump(texture_data, f, ensure_ascii=False, indent=4)

def load_gameobject_data():
    global gameobject_data
    if os.path.exists(GAMEOBJECT_JSON):
        with open(GAMEOBJECT_JSON, 'r', encoding='utf-8') as f:
            gameobject_data = json.load(f)

def save_gameobject_data():
    with open(GAMEOBJECT_JSON, 'w', encoding='utf-8') as f:
        json.dump(gameobject_data, f, ensure_ascii=False, indent=4)

load_sound_data()
load_texture_data()
load_gameobject_data()

# Unity communication functions
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

def get_addressable_path(file_path):
    return send_to_unity('get_addressable_path', {'file_path': file_path})

def get_sprite_info(file_path):
    return send_to_unity('get_sprite_info', {'file_path': file_path})

def select_file(initial_dir, filetypes):
    root = tk.Tk()
    root.withdraw()
    file_path = filedialog.askopenfilename(initialdir=initial_dir, filetypes=filetypes)
    root.destroy()
    return file_path if file_path else None

# Sound data management
def get_sound_data():
    return sound_data

def add_sound_group(group_name):
    if group_name and group_name not in sound_data['groups']:
        sound_data['groups'][group_name] = []
        save_sound_data()

def delete_sound_group(group_name):
    sound_data['groups'].pop(group_name, None)
    save_sound_data()

def add_sound(group_name, name, desc, volume, sound_type):
    project_path = get_unity_project_path()
    if not project_path:
        raise Exception("Failed to get Unity project path.")
    file_path = select_file(project_path, [("Audio files", "*.mp3 *.wav")])
    if not file_path:
        raise Exception("No file selected.")
    addr_path = get_addressable_path(file_path)
    if not addr_path:
        raise Exception("Failed to get Addressable path.")
    sound_data['groups'][group_name].append({
        'name': name, 'desc': desc, 'path': addr_path, 'volume': volume, 'type': sound_type
    })
    save_sound_data()

def delete_sound(group_name, index):
    del sound_data['groups'][group_name][index]
    save_sound_data()

def generate_sound_csharp():
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

    # Update SoundID.json
    sound_id_path = os.path.join(SOUND_DATA, 'SoundID.json')
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
    with open(sound_id_path, 'w', encoding='utf-8') as f:
        json.dump(sound_id_list, f, ensure_ascii=False, indent=4)

def generate_sound_bin():
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
    return texture_data

def add_texture_group(group_name):
    if group_name and group_name not in texture_data['groups']:
        texture_data['groups'][group_name] = []
        save_texture_data()

def delete_texture_group(group_name):
    texture_data['groups'].pop(group_name, None)
    save_texture_data()

def add_texture(group_name, name, desc):
    project_path = get_unity_project_path()
    if not project_path:
        raise Exception("Failed to get Unity project path.")
    file_path = select_file(project_path, [("Image files", "*.png *.jpg *.jpeg")])
    if not file_path:
        raise Exception("No file selected.")
    addr_path = get_addressable_path(file_path)
    if not addr_path:
        raise Exception("Failed to get Addressable path.")
    sprite_info = json.loads(get_sprite_info(file_path)) if get_sprite_info(file_path) else []
    texture_data['groups'][group_name].append({
        'name': name, 'desc': desc, 'path': addr_path, 'sprites': sprite_info
    })
    save_texture_data()

def delete_texture(group_name, index):
    del texture_data['groups'][group_name][index]
    save_texture_data()

def generate_texture_csharp():
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
        f.write('    public enum SpriteID { None')
        sprite_id_counter = 1
        sprite_id_map = {'None': 0}
        for group, textures in texture_data['groups'].items():
            for texture in textures:
                for sprite in texture.get('sprites', []):
                    sprite_id = f"{group}_{texture['name']}_{sprite}"
                    if sprite_id not in sprite_id_map:
                        sprite_id_map[sprite_id] = sprite_id_counter
                        f.write(f', {sprite_id}')
                        sprite_id_counter += 1
        f.write(' ,Max\n  };\n')
        f.write('}\n')

    # Update TextureID.json
    texture_id_path = os.path.join(TEXTURE_DATA, 'TextureID.json')
    texture_id_list = []
    for group, textures in texture_data['groups'].items():
        for texture in textures:
            texture_id = f"{group}_{texture['name']}"
            texture_id_list.append({
                'description': texture['desc'],
                'id': texture_id_map[texture_id],
                'property': texture_id,
                'value': texture_id_map[texture_id]
            })
    with open(texture_id_path, 'w', encoding='utf-8') as f:
        json.dump(texture_id_list, f, ensure_ascii=False, indent=4)

    # Update SpriteID.json
    sprite_id_path = os.path.join(TEXTURE_DATA, 'SpriteID.json')
    sprite_id_list = []
    for group, textures in texture_data['groups'].items():
        for texture in textures:
            for sprite in texture.get('sprites', []):
                sprite_id = f"{group}_{texture['name']}_{sprite}"
                sprite_id_list.append({
                    'description': f"Sprite of {texture['desc']}",
                    'id': sprite_id_map[sprite_id],
                    'property': sprite_id,
                    'value': sprite_id_map[sprite_id]
                })
    with open(sprite_id_path, 'w', encoding='utf-8') as f:
        json.dump(sprite_id_list, f, ensure_ascii=False, indent=4)

def generate_texture_bin():
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
                for sprite in texture.get('sprites', []):
                    sprite_id = f"{group}_{texture['name']}_{sprite}"
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
                    sprite_id = sprite_id_map.get(f"{group}_{texture['name']}_{sprite}", 0)
                    f.write(struct.pack('i', sprite_id))
                    sprite_path = f"{texture['path']}#{sprite}".encode('utf-8') + b'\0'
                    f.write(sprite_path)
            current_offset = f.tell()
        f.seek(offset_pos)
        f.write(struct.pack('i' * group_count, *offsets))

# GameObject data management
def get_gameobject_data():
    return gameobject_data

def add_gameobject_group(group_name):
    if group_name and group_name not in gameobject_data['groups']:
        gameobject_data['groups'][group_name] = []
        save_gameobject_data()

def delete_gameobject_group(group_name):
    gameobject_data['groups'].pop(group_name, None)
    save_gameobject_data()

def add_gameobject(group_name, name, desc):
    project_path = get_unity_project_path()
    if not project_path:
        raise Exception("Failed to get Unity project path.")
    file_path = select_file(project_path, [("Prefab files", "*.prefab")])
    if not file_path:
        raise Exception("No file selected.")
    addr_path = get_addressable_path(file_path)
    if not addr_path:
        raise Exception("Failed to get Addressable path.")
    gameobject_data['groups'][group_name].append({
        'name': name, 'desc': desc, 'path': addr_path
    })
    save_gameobject_data()

def delete_gameobject(group_name, index):
    del gameobject_data['groups'][group_name][index]
    save_gameobject_data()

def generate_gameobject_csharp():
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

    # Update GameObjectID.json
    gameobject_id_path = os.path.join(GAMEOBJECT_DATA, 'GameObjectID.json')
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
    with open(gameobject_id_path, 'w', encoding='utf-8') as f:
        json.dump(gameobject_id_list, f, ensure_ascii=False, indent=4)

def generate_gameobject_bin():
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
    if group_name in texture_data['groups'] and index < len(texture_data['groups'][group_name]):
        return texture_data['groups'][group_name][index]['path']
    return None

def get_sound_file_path(group_name, index):
    if group_name in sound_data['groups'] and index < len(sound_data['groups'][group_name]):
        return sound_data['groups'][group_name][index]['path']
    return None
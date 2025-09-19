import json
import os
import socket
import struct
import sys
import tkinter as tk
from tkinter import filedialog





# 実行可能ファイルのディレクトリを取得（PyInstaller対応）
if getattr(sys, 'frozen', False):
    # PyInstallerでビルドされた場合
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # デバッグ環境（VS Codeなど）
    # main-support/ の1つ上のディレクトリ（project/）を基準にする
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ディレクトリパスをプロジェクトルート基準に設定
DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "data"))
ASSETS_DIATA = os.path.join(DATA_DIR, "assets-data")

SOUND_DATA = os.path.join(ASSETS_DIATA, 'sound')
SOUND_JSON = os.path.join(SOUND_DATA, 'assets_sound.json')
EDITOR_DATA = os.path.join(ASSETS_DIATA, 'Editor')  

def generate_base():
    
    if not os.path.exists(ASSETS_DIATA):
        os.makedirs(ASSETS_DIATA)
    if not os.path.exists(SOUND_DATA):
        os.makedirs(SOUND_DATA)
    if not os.path.exists(EDITOR_DATA):
        os.makedirs(EDITOR_DATA)

    if not os.path.exists(os.path.join(EDITOR_DATA,"EditorCommunication.cs")):
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

public class EditorCommunication : EditorWindow
{
    private static TcpListener listener;
    private static Thread listenerThread;
    private static volatile bool pendingCommand;
    private static string pendingCommandName;
    private static CommData pendingCommandData; // 修正: string から CommData に変更
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

                    // メインスレッドで処理するためにコマンドを保存
                    pendingCommandName = json.command;
                    pendingCommandData = json.data; // 修正: string から CommData に変更
                    pendingCommand = true;

                    // メインスレッドが処理を終えるまで待機
                    while (pendingCommand)
                    {
                        Thread.Sleep(10);
                    }

                    // レスポンスを送信
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

        // メインスレッドでコマンドを処理
        commandResult = HandleCommand(pendingCommandName, pendingCommandData);
        pendingCommand = false;
    }

    private static string HandleCommand(string command, CommData data)
    {
        if (command == "get_project_path")
        {
            return Path.GetFullPath(Application.dataPath + "/..");
        }
        else if (command == "get_addressable_path")
        {
            string filePath = data.file_path;
            Debug.Log($"Received filePath: {filePath}");
    
            // プロジェクトルートからの相対パスを作成
            string projectRoot = Path.GetFullPath(Path.Combine(Application.dataPath, ".."));
            Debug.Log($"Project root: {projectRoot}");
    
            string assetPath = filePath;
            if (filePath.StartsWith(projectRoot, StringComparison.OrdinalIgnoreCase))
            {
                assetPath = filePath.Substring(projectRoot.Length).TrimStart(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
            }
            assetPath = assetPath.Replace("\\", "/");
            if (!assetPath.StartsWith("Assets/"))
            {
                assetPath = "Assets/" + assetPath;
            }
            Debug.Log($"Computed assetPath: {assetPath}");
    
            // GUID を取得
            string guid = AssetDatabase.AssetPathToGUID(assetPath);
            Debug.Log($"GUID: {guid}");
    
            if (string.IsNullOrEmpty(guid))
            {
                Debug.LogWarning($"No GUID found for assetPath: {assetPath}");
                return assetPath; // 相対パスを返す
            }
    
            // Addressable 設定からエントリを検索
            AddressableAssetSettings settings = AddressableAssetSettingsDefaultObject.Settings;
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
        return null;
    }

    [System.Serializable]
    private class CommMessage
    {
        public string command;
        public CommData data; // 修正: string から CommData に変更
        public string result;
    }

    [System.Serializable]
    private class CommData
    {
        public string file_path; // JSON の "file_path" に対応
    }
}

        """
        with open(os.path.join(EDITOR_DATA,"EditorCommunication.cs"), 'w', encoding='utf-8') as f:
            f.write(code_str)

    if not os.path.exists(os.path.join(SOUND_DATA,"SoundBinaryReader.cs")):
        code_str = """
using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;

namespace GameCore.Sound
{
    public class SoundBinaryReader
    {
        public static SoundDatabase LoadSoundDatabaseFromBinary(string filePath)
        {
            if (!File.Exists(filePath))
            {
                Debug.LogError($"Binary file not found: {filePath}");
                return null;
            }

            SoundDatabase database = new SoundDatabase();

            using (BinaryReader reader = new BinaryReader(File.Open(filePath, FileMode.Open)))
            {
                // Read group count
                int groupCount = reader.ReadInt32();
                int[] offsets = new int[groupCount];

                // Read offsets
                for (int i = 0; i < groupCount; i++)
                {
                    offsets[i] = reader.ReadInt32();
                }

                // Read each group
                string[] groupNames = Enum.GetNames(typeof(SoundGroup));
                if (groupCount > groupNames.Length - 1) // -1 for None
                {
                    Debug.LogError("Binary contains more groups than defined in SoundGroup enum.");
                    return null;
                }

                for (int i = 0; i < groupCount; i++)
                {
                    reader.BaseStream.Seek(offsets[i], SeekOrigin.Begin);
                    int soundCount = reader.ReadInt32();
                    List<SoundDatabase.SoundData> sounds = new List<SoundDatabase.SoundData>();

                    for (int j = 0; j < soundCount; j++)
                    {
                        int id = reader.ReadInt32();
                        string addressablePath = ReadNullTerminatedString(reader);
                        float volume = reader.ReadSingle();
                        byte typeByte = reader.ReadByte();
                        SoundType type = (typeByte == 0) ? SoundType.SE : SoundType.BGM;

                        // Map ID to name using per-group enum
                        string enumName;
                        try
                        {
                            Type enumType = Type.GetType($"GameCore.Sound.{groupNames[i + 1]}_SoundID");
                            enumName = Enum.GetName(enumType, id) ?? $"Unknown_{id}";
                        }
                        catch
                        {
                            enumName = $"Unknown_{id}";
                            Debug.LogWarning($"Enum {groupNames[i + 1]}_SoundID not found for group {groupNames[i + 1]}.");
                        }

                        sounds.Add(new SoundDatabase.SoundData(
                            idName: enumName,
                            addressablePath: addressablePath,
                            baseVolume: volume,
                            type: type
                        ));
                    }

                    database.GroupedSounds.Add(new SoundDatabase.GroupedSounds(
                        group: (SoundGroup)(i + 1), // +1 because None=0
                        sounds: sounds
                    ));
                }
            }

            return database;
        }

        private static string ReadNullTerminatedString(BinaryReader reader)
        {
            List<byte> bytes = new List<byte>();
            byte b;
            while ((b = reader.ReadByte()) != 0)
            {
                bytes.Add(b);
            }
            return System.Text.Encoding.UTF8.GetString(bytes.ToArray());
        }
    }
}
        """""
        with open(os.path.join(SOUND_DATA,"SoundBinaryReader.cs"), 'w', encoding='utf-8') as f:
            f.write(code_str)
            
    if not os.path.exists(os.path.join(SOUND_DATA,"SoundCore.cs")):
        
        code_str = """
        using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using UnityEngine.AddressableAssets;
using UnityEngine.ResourceManagement.AsyncOperations;
using Cysharp.Threading.Tasks;

namespace GameCore.Sound
{
    public class SoundCore : BaseGameSingleton<SoundCore>
    {
        private SoundDatabase database;
        private Dictionary<SoundGroup, Dictionary<SoundID, AudioClip>> loadedClips = new Dictionary<SoundGroup, Dictionary<SoundID, AudioClip>>();
        private AudioSource bgmSource; // BGM専用ソース
        private AudioSource crossFadeTempSource; // CrossFade用一時ソース
        private List<AudioSource> sePool = new List<AudioSource>(); // SEプール
        private const int PoolSize = 30;

        public void Awake()
        {
            instance = this;
            DontDestroyOnLoad(gameObject);

            bgmSource = gameObject.AddComponent<AudioSource>();
            bgmSource.loop = true;

            // SEプール初期化
            for (int i = 0; i < PoolSize; i++)
            {
                var source = gameObject.AddComponent<AudioSource>();
                source.playOnAwake = false;
                sePool.Add(source);
            }

            // Databaseロード (Binary)
            LoadDatabaseAsync().Forget();
        }

        private async UniTask LoadDatabaseAsync()
        {
            database = SoundBinaryReader.LoadSoundDatabaseFromBinary(Application.dataPath + "/../sound_data.bin");
            if (database == null)
            {
                Debug.LogError("Failed to load SoundDatabase from binary.");
            }
            await UniTask.CompletedTask;
        }

        // グループロード (同期)
        public void LoadGroup(SoundGroup group, Action action = null)
        {
            LoadGroupAsync(group, action).Forget();
        }

        // グループロード (非同期)
        public async UniTask LoadGroupAsync(SoundGroup group, Action action = null)
        {
            while (true)
            {
                if (database != null) break;
                await UniTask.Yield();
            }
            if (loadedClips.ContainsKey(group)) return;
            if (database.GroupedSounds.Find(data => data.Group == group) == null) return;

            var sounds = database.GroupedSounds.Find(data => data.Group == group);
            loadedClips[group] = new Dictionary<SoundID, AudioClip>();
            foreach (var sound in sounds.Sounds)
            {
                var handle = Addressables.LoadAssetAsync<AudioClip>(sound.AddressablePath);
                await handle;
                if (handle.Status == AsyncOperationStatus.Succeeded)
                {
                    SoundID id = (SoundID)Enum.Parse(typeof(SoundID), sound.IdName);
                    loadedClips[group][id] = handle.Result;
                }
            }

            action?.Invoke();
        }

        // グループアンロード (同期)
        public void UnloadGroup(SoundGroup group)
        {
            UnloadGroupAsync(group).Forget();
        }

        // グループアンロード (非同期)
        public async UniTask UnloadGroupAsync(SoundGroup group)
        {
            if (!loadedClips.TryGetValue(group, out var clips)) return;

            foreach (var clip in clips.Values)
            {
                Addressables.Release(clip);
            }
            loadedClips.Remove(group);
            await UniTask.CompletedTask;
        }

        // SE再生 (同期)
        public void PlaySE(SoundGroup group, SoundID id, float volume = 1.0f, bool is3D = false, Vector3 position = default, float maxDistance = 500f)
        {
            PlaySEInternal(group, id, volume, is3D, position, maxDistance, async: true).Forget();
        }

        // SE再生 (非同期)
        public async UniTask PlaySEAsync(SoundGroup group, SoundID id, float volume = 1.0f, bool is3D = false, Vector3 position = default, float maxDistance = 500f)
        {
            await PlaySEInternal(group, id, volume, is3D, position, maxDistance, async: true);
        }

        private async UniTask PlaySEInternal(SoundGroup group, SoundID id, float volume, bool is3D, Vector3 position, float maxDistance, bool async)
        {
            if (!TryGetClipAndData(group, id, out AudioClip clip, out SoundDatabase.SoundData data) || data.Type != SoundType.SE) return;

            var source = GetPooledSource();
            if (source == null) return; // プール満杯時、無視

            source.clip = clip;
            source.volume = data.BaseVolume * volume;
            source.loop = false;
            source.spatialBlend = is3D ? 1f : 0f;
            source.maxDistance = maxDistance;
            if (is3D) source.transform.position = position;

            source.Play();

            if (async)
            {
                await UniTask.WaitUntil(() => !source.isPlaying);
                ResetSource(source);
            }
        }

        // BGM再生 (同期, FadeIn対応)
        public void PlayBGM(SoundGroup group, SoundID id, float volume = 1.0f, float fadeTime = 0f)
        {
            PlayBGMAsync(group, id, volume, fadeTime).Forget();
        }

        // BGM再生 (非同期, FadeIn対応)
        public async UniTask PlayBGMAsync(SoundGroup group, SoundID id, float volume = 1.0f, float fadeTime = 0f)
        {
            if (!TryGetClipAndData(group, id, out AudioClip clip, out SoundDatabase.SoundData data) || data.Type != SoundType.BGM) return;

            if (bgmSource.isPlaying && fadeTime > 0)
            {
                await FadeOutAsync(fadeTime);
            }

            bgmSource.clip = clip;
            bgmSource.volume = 0f;
            bgmSource.Play();

            if (fadeTime > 0)
            {
                await FadeInAsync(data.BaseVolume * volume, fadeTime);
            }
            else
            {
                bgmSource.volume = data.BaseVolume * volume;
            }
        }

        // BGM FadeOut (同期)
        public void FadeOutBGM(float fadeTime)
        {
            FadeOutAsync(fadeTime).Forget();
        }

        // BGM FadeOut (非同期)
        public async UniTask FadeOutAsync(float fadeTime)
        {
            if (!bgmSource.isPlaying) return;

            float startVolume = bgmSource.volume;
            float timer = 0f;
            while (timer < fadeTime)
            {
                timer += Time.deltaTime;
                bgmSource.volume = Mathf.Lerp(startVolume, 0f, timer / fadeTime);
                await UniTask.Yield();
            }
            bgmSource.Stop();
            ResetSource(bgmSource);
        }

        // BGM FadeIn (内部用)
        private async UniTask FadeInAsync(float targetVolume, float fadeTime)
        {
            float timer = 0f;
            while (timer < fadeTime)
            {
                timer += Time.deltaTime;
                bgmSource.volume = Mathf.Lerp(0f, targetVolume, timer / fadeTime);
                await UniTask.Yield();
            }
        }

        // BGM CrossFade (同期)
        public void CrossFadeBGM(SoundGroup group, SoundID id, float volume = 1.0f, float fadeTime = 1f)
        {
            CrossFadeBGMAsync(group, id, volume, fadeTime).Forget();
        }

        // BGM CrossFade (非同期)
        public async UniTask CrossFadeBGMAsync(SoundGroup group, SoundID id, float volume = 1.0f, float fadeTime = 1f)
        {
            if (!TryGetClipAndData(group, id, out AudioClip clip, out SoundDatabase.SoundData data) || data.Type != SoundType.BGM) return;

            // 一時ソース作成
            crossFadeTempSource = gameObject.AddComponent<AudioSource>();
            crossFadeTempSource.loop = true;
            crossFadeTempSource.clip = clip;
            crossFadeTempSource.volume = 0f;
            crossFadeTempSource.Play();

            float timer = 0f;
            float startBGMVolume = bgmSource.volume;

            while (timer < fadeTime)
            {
                timer += Time.deltaTime;
                float t = timer / fadeTime;
                bgmSource.volume = Mathf.Lerp(startBGMVolume, 0f, t);
                crossFadeTempSource.volume = Mathf.Lerp(0f, data.BaseVolume * volume, t);
                await UniTask.Yield();
            }

            bgmSource.Stop();
            ResetSource(bgmSource);
            Destroy(bgmSource);
            bgmSource = crossFadeTempSource;
            crossFadeTempSource = null;
        }

        private bool TryGetClipAndData(SoundGroup group, SoundID id, out AudioClip clip, out SoundDatabase.SoundData data)
        {
            clip = null;
            data = null;
            if (!loadedClips.TryGetValue(group, out var groupClips) || !groupClips.TryGetValue(id, out clip)) return false;
            data = database.GroupedSounds.Find(g => g.Group == group)?.Sounds.FirstOrDefault(s => s.IdName == id.ToString());
            return data != null;
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
            // 懸念点対応: 再生中ソースの監視
            sePool.RemoveAll(s => s == null);
            if (bgmSource == null) bgmSource = gameObject.AddComponent<AudioSource>();
        }

        private void OnDestroy()
        {
            // 全アンロード
            foreach (var group in loadedClips.Keys.ToArray())
            {
                UnloadGroup(group);
            }
            // No Addressables.Release for database since it's not a ScriptableObject
        }
    }
}"""
        with open(os.path.join(SOUND_DATA,"SoundCore.cs"), 'w', encoding='utf-8') as f:
            f.write(code_str)



    if not os.path.exists(os.path.join(SOUND_DATA,'SoundEnums.cs')):
        with open(os.path.join(SOUND_DATA,'SoundEnums.cs'), 'w', encoding='utf-8') as f:
            f.write('namespace GameCore.Sound {\n')
            f.write('    public enum SoundGroup { None, UI, Battle, BGM };\n')
            f.write('    public enum SoundType { SE, BGM };\n')
            f.write('}\n')
            
    # SoundDatabase.cs
    if not os.path.exists(os.path.join(SOUND_DATA,'SoundDatabase.cs')):
        with open(os.path.join(SOUND_DATA,'SoundDatabase.cs'), 'w', encoding='utf-8') as f:
            f.write('using System.Collections.Generic;\n\n')
            f.write('namespace GameCore.Sound {\n')
            f.write('    public class SoundDatabase {\n')
            f.write('        [System.Serializable]\n')
            f.write('        public class SoundData {\n')
            f.write('            private readonly string idName;\n')
            f.write('            private readonly string addressablePath;\n')
            f.write('            private readonly float baseVolume;\n')
            f.write('            private readonly SoundType type;\n')
            f.write('            public SoundData(string idName, string addressablePath, float baseVolume, SoundType type) {\n')
            f.write('                this.idName = idName;\n')
            f.write('                this.addressablePath = addressablePath;\n')
            f.write('                this.baseVolume = baseVolume;\n')
            f.write('                this.type = type;\n')
            f.write('            }\n')
            f.write('            public string IdName => idName;\n')
            f.write('            public string AddressablePath => addressablePath;\n')
            f.write('            public float BaseVolume => baseVolume;\n')
            f.write('            public SoundType Type => type;\n')
            f.write('        }\n')
            f.write('        [System.Serializable]\n')
            f.write('        public class GroupedSounds {\n')
            f.write('            private readonly SoundGroup group;\n')
            f.write('            private readonly List<SoundData> sounds;\n')
            f.write('            public GroupedSounds(SoundGroup group, List<SoundData> sounds) {\n')
            f.write('                this.group = group;\n')
            f.write('                this.sounds = sounds ?? new List<SoundData>();\n')
            f.write('            }\n')
            f.write('            public SoundGroup Group => group;\n')
            f.write('            public IReadOnlyList<SoundData> Sounds => sounds.AsReadOnly();\n')
            f.write('        }\n')
            f.write('        private readonly List<GroupedSounds> groupedSounds;\n')
            f.write('        public SoundDatabase() {\n')
            f.write('            groupedSounds = new List<GroupedSounds>();\n')
            f.write('        }\n')
            f.write('        public IReadOnlyList<GroupedSounds> GroupedSoundsList => groupedSounds.AsReadOnly();\n')
            f.write('    }\n')
            f.write('}\n')
        
    


sound_data = {'groups': {}}

def load_sound_data():
    global sound_data
    if os.path.exists(SOUND_JSON):
        with open(SOUND_JSON, 'r', encoding='utf-8') as f:
            sound_data = json.load(f)

def save_sound_data():
    with open(SOUND_JSON, 'w', encoding='utf-8') as f:
        json.dump(sound_data, f, ensure_ascii=False, indent=4)

load_sound_data()

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

def select_audio_file(initial_dir):
    root = tk.Tk()
    root.withdraw()
    file_path = filedialog.askopenfilename(initialdir=initial_dir, filetypes=[("Audio files", "*.mp3 *.wav")])
    if not file_path:
        return None
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in ('.mp3', '.wav'):
        raise ValueError("Only MP3 or WAV files allowed.")
    return file_path

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
    file_path = select_audio_file(project_path)
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

def generate_csharp():
    with open('SoundEnums.cs', 'w') as f:
        f.write('namespace GameCore.Sound {\n')
        # SoundGroup enum
        f.write('public enum SoundGroup { None')
        for group in sound_data['groups']:
            f.write(f', {group}')
        f.write(' };\n')
        # SoundType enum
        f.write('public enum SoundType { SE, BGM };\n')
        # Per-group enums
        for group, sounds in sound_data['groups'].items():
            f.write(f'public enum {group}_SoundID {{ None')
            for sound in sounds:
                f.write(f', {sound["name"]}')
            f.write(' };\n')
        f.write('}\n')

    with open('SoundDatabase.cs', 'w') as f:
        f.write('using System.Collections.Generic;\n\n')
        f.write('namespace GameCore.Sound {\n')
        f.write('    public class SoundDatabase {\n')
        f.write('        [System.Serializable]\n')
        f.write('        public class SoundData {\n')
        f.write('            private readonly string idName;\n')
        f.write('            private readonly string addressablePath;\n')
        f.write('            private readonly float baseVolume;\n')
        f.write('            private readonly SoundType type;\n')
        f.write('            public SoundData(string idName, string addressablePath, float baseVolume, SoundType type) {\n')
        f.write('                this.idName = idName;\n')
        f.write('                this.addressablePath = addressablePath;\n')
        f.write('                this.baseVolume = baseVolume;\n')
        f.write('                this.type = type;\n')
        f.write('            }\n')
        f.write('            public string IdName => idName;\n')
        f.write('            public string AddressablePath => addressablePath;\n')
        f.write('            public float BaseVolume => baseVolume;\n')
        f.write('            public SoundType Type => type;\n')
        f.write('        }\n')
        f.write('        [System.Serializable]\n')
        f.write('        public class GroupedSounds {\n')
        f.write('            private readonly SoundGroup group;\n')
        f.write('            private readonly List<SoundData> sounds;\n')
        f.write('            public GroupedSounds(SoundGroup group, List<SoundData> sounds) {\n')
        f.write('                this.group = group;\n')
        f.write('                this.sounds = sounds ?? new List<SoundData>();\n')
        f.write('            }\n')
        f.write('            public SoundGroup Group => group;\n')
        f.write('            public IReadOnlyList<SoundData> Sounds => sounds.AsReadOnly();\n')
        f.write('        }\n')
        f.write('        private readonly List<GroupedSounds> groupedSounds;\n')
        f.write('        public SoundDatabase() {\n')
        f.write('            groupedSounds = new List<GroupedSounds>();\n')
        f.write('        }\n')
        f.write('        public IReadOnlyList<GroupedSounds> GroupedSoundsList => groupedSounds.AsReadOnly();\n')
        f.write('    }\n')
        f.write('}\n')
def generate_bin():
    with open('sound_data.bin', 'wb') as f:
        groups = list(sound_data['groups'].keys())
        group_count = len(groups)
        f.write(struct.pack('i', group_count))
        offsets = [0] * group_count
        offset_pos = f.tell()
        f.write(struct.pack('i' * group_count, *offsets))
        current_offset = f.tell()
        for i, group in enumerate(groups):
            offsets[i] = current_offset
            sounds = sound_data['groups'][group]
            f.write(struct.pack('i', len(sounds)))
            for j, sound in enumerate(sounds, 1):  # ID from 1 (None=0)
                f.write(struct.pack('i', j))
                path_bytes = sound['path'].encode('utf-8') + b'\0'
                f.write(path_bytes)
                f.write(struct.pack('f', sound['volume']))
                type_byte = 0 if sound['type'] == 'SE' else 1
                f.write(struct.pack('B', type_byte))
            current_offset = f.tell()
        f.seek(offset_pos)
        f.write(struct.pack('i' * group_count, *offsets))
import json
import math
import os
import socket
import struct
import sys
import tkinter as tk
from tkinter import filedialog
import shutil
import uuid
from collections import defaultdict

def generate_enum_csharp(json_path, name, enum_dir):
    """
    指定されたJSONファイルからC#のenumコードを生成する

    Args:
        json_path (str): JSONファイルのパス
        name (str): 生成するenumの名前（{name}ID.csとして使用）
        data_dir (str): データディレクトリのベースパス
        enum_dir (str): ENUMディレクトリの相対パス
    """
    # JSONデータを読み込む
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)


    # valueが数値で有効なアイテムをフィルタリング
    valid_data = [item for item in data if not math.isnan(item['value']) and math.isfinite(item['value'])]

    # C# enumコードを生成
    cs_content = "namespace GameCore.Enums\n{\n"
    cs_content += f"    public enum {name}ID\n    {{\n"
    cs_content += "        None = 0, // デフォルト値\n"
    for item in valid_data:
        cs_content += f"        {item['property']} = {item['value']}, // {item['description']}\n"
    max_value = max([item['value'] for item in valid_data], default=-1) + 1
    cs_content += f"        Max = {max_value}\n"
    cs_content += "    }\n}"

    # 出力パスを構築
    cs_path = os.path.join(enum_dir, name, f"{name}ID.cs")
    os.makedirs(os.path.dirname(cs_path), exist_ok=True)

    # C#ファイルを保存
    with open(cs_path, 'w', encoding='utf-8') as f:
        f.write(cs_content)

def generate_subgroup_enum_details_csharp(enum_dir, category_name, group_name, subgroup_name,items):
    
    target_dir = os.path.join(enum_dir, f"{category_name}_{group_name}_{subgroup_name}")
    os.makedirs(target_dir, exist_ok=True)
    enum_name = f"{category_name}_{group_name}_{subgroup_name}"
    
    #enum作成
    cs_content = "namespace GameCore.Enums\n{\n"
    cs_content += f"    public enum {enum_name}ID\n    {{\n"
    cs_content += "        None = 0, // デフォルト値\n"
    for i, id in enumerate(items, start=1):
        cs_content += f"        {id.get("name", id.get("class_name",""))} = {i},\n"
    cs_content += f"        Max = {len(items) + 1}\n"
    cs_content += "    }\n}"
    
    cs_path = os.path.join(target_dir, f"{enum_name}ID.cs")
    with open(cs_path, 'w', encoding='utf-8') as f:
        f.write(cs_content)
    
    
    
    #json作成
    json_dict: list[dict[str, object]] = []
    js_path = os.path.join(target_dir, f"{category_name}_{group_name}_{subgroup_name}.json")
    with open(js_path,'w',encoding='utf-8') as f:
        for i, item in enumerate(items, start=1):
            json_dict.append({
                "description": f"{item["desc"]}",
                "id": i,
                "property": f"{item.get("name", item.get("class_name",""))}",
                "value": i
            })
        json.dump(json_dict, f, ensure_ascii=False, indent=4)
        
    #enum_list.jsonに追加

    return enum_name

def generate_subgroup_enum_csharp(enum_dir, category_name, group_name, subgroup_names):
    """
    グループの中に定義されたSubGroup用のenumを生成する。

    カテゴリ全体のGroup enum（例: GameObjectGroup）と同じ考え方で、
    「そのグループの中にあるSubGroup一覧」を表す専用enumを1つ作る。
    命名規則: {category_name}_{group_name}ID
    例: GameObjectカテゴリの "Enemy" グループなら GameObject_EnemyID を
        ENUM_DIR/{category_name}/{category_name}_{group_name}ID.cs に生成する。

    Args:
        enum_dir (str): ENUM_DIRのパス
        category_name (str): カテゴリ名（GameObject/Texture/Sound/Material）
        group_name (str): SubGroupの親となるGroup名
        subgroup_names (list[str]): そのグループに登録されているSubGroup名のリスト（登録順）

    Returns:
        str: 生成したenum名（{category_name}_{group_name}ID）
    """
    target_dir = os.path.join(enum_dir, f"{category_name}_{group_name}")
    os.makedirs(target_dir, exist_ok=True)

    enum_name = f"{category_name}_{group_name}"
    cs_content = "namespace GameCore.Enums\n{\n"
    cs_content += f"    public enum {enum_name}ID\n    {{\n"
    cs_content += "        None = 0, // デフォルト値\n"
    for i, sub_name in enumerate(subgroup_names, start=1):
        cs_content += f"        {sub_name} = {i},\n"
    cs_content += f"        Max = {len(subgroup_names) + 1}\n"
    cs_content += "    }\n}"
    

    cs_path = os.path.join(target_dir, f"{enum_name}ID.cs")
    with open(cs_path, 'w', encoding='utf-8') as f:
        f.write(cs_content)
        
    #json作成
    json_dict: list[dict[str, object]] = []
    js_path = os.path.join(target_dir, f"{category_name}_{group_name}.json")
    with open(js_path,'w',encoding='utf-8') as f:
        for i, sub_name in enumerate(subgroup_names, start=1):
            json_dict.append({
                "description": f"{category_name}_{group_name}_{sub_name}",
                "id": i,
                "property": f"{sub_name}",
                "value": i
            })
        json.dump(json_dict, f, ensure_ascii=False, indent=4)
        
    return enum_name


def sync_subgroup_enum_files(enum_dir, category_name, groups_dict,
                              data_dir=None, namespace=None, class_name=None,
                              group_enum_name=None, id_enum_name=None,
                              global_key_field='name'):
    """
    現在のgroups_dict（{group_name: {'items':[...], 'subgroups':[...]}}）に基づいて
    SubGroup enumファイル一式を再生成し、既に存在しない（削除された）グループ／
    SubGroupのenumファイルは掃除する。

    data_dir/namespace/class_name/group_enum_name/id_enum_name が指定された場合は、
    SubGroup詳細enum（{category_name}_{group}_{subgroup}）の値を
    {id_enum_name}（グローバルなID enum）へ static readonly 配列で高速変換したうえで
    LoadSingle/UnloadSingle を呼び出すオーバーロードを {class_name}Single.cs に生成する。
    （ローカルenumの値をそのまま配列インデックスとして使うのでO(1)変換）

    Returns:
        list[str]: 生成された{category_name}_{group}ID の一覧（enum_list.json登録用）
    """
    target_dir = os.path.join(enum_dir, category_name)
    os.makedirs(target_dir, exist_ok=True)

    expected_files = set()
    generated_names = []

    generate_single_file = all([data_dir, namespace, class_name, group_enum_name, id_enum_name])
    single_lines = []
    if generate_single_file:
        single_lines.append("// 自動生成ファイルです。手動編集しても generate 実行時に上書きされます。")
        single_lines.append("using System;")
        single_lines.append("using GameCore.Enums;")
        single_lines.append("using Cysharp.Threading.Tasks;")
        single_lines.append("")
        single_lines.append(f"namespace {namespace}")
        single_lines.append("{")
        single_lines.append(f"    public partial class {class_name}")
        single_lines.append("    {")

    for group_name, group_value in groups_dict.items():
        subgroups = group_value.get('subgroups', []) if isinstance(group_value, dict) else []
        if not subgroups:
            continue
        enum_name = generate_subgroup_enum_csharp(enum_dir, category_name, group_name, subgroups)
        expected_files.add(f"{enum_name}.cs")
        generated_names.append(enum_name)
        #さらにサブグループごとのIDを作成
        #まずはグループ分け
        subgroup_dict = defaultdict(list)
        for item in group_value["items"]:
            subgroup_dict[item["subgroup"]].append(item)
        for key, value in subgroup_dict.items():
            detail_enum_name = generate_subgroup_enum_details_csharp(enum_dir, category_name, group_name, key, value)
            generated_names.append(detail_enum_name)

            if generate_single_file:
                table_name = f"_{detail_enum_name}To{id_enum_name}"
                single_lines.append(f"        private static readonly {id_enum_name}[] {table_name} = new {id_enum_name}[]")
                single_lines.append("        {")
                single_lines.append(f"            {id_enum_name}.None, // {detail_enum_name}.None")
                for item in value:
                    global_key = item.get(global_key_field) or item.get("name", item.get("class_name",""))
                    global_name = f"{group_name}_{global_key}"
                    single_lines.append(f"            {id_enum_name}.{global_name}, // {detail_enum_name}.{item.get("name",item.get("class_name",""))}")
                single_lines.append("        };")
                single_lines.append("")
                single_lines.append(f"        public void LoadSingle({detail_enum_name}ID id, AddressableSystem.GroupCategory groupCategory, Action onCompleted = null)")
                single_lines.append(f"            => LoadSingle({group_enum_name}.{group_name}, {table_name}[(int)id], groupCategory, onCompleted);")
                single_lines.append("")
                single_lines.append(f"        public async UniTask LoadSingleAsync({detail_enum_name}ID id, AddressableSystem.GroupCategory groupCategory, Action onCompleted = null)")
                single_lines.append(f"            => await LoadSingleAsync({group_enum_name}.{group_name}, {table_name}[(int)id], groupCategory, onCompleted);")
                single_lines.append("")
                single_lines.append(f"        public void UnloadSingle({detail_enum_name}ID id, Action onCompleted = null)")
                single_lines.append(f"            => UnloadSingle({group_enum_name}.{group_name}, {table_name}[(int)id], onCompleted);")
                single_lines.append("")
                single_lines.append(f"       public async UniTask UnloadSingleAsync({detail_enum_name}ID id, Action onCompleted = null)")
                single_lines.append(f"            => await UnloadSingleAsync({group_enum_name}.{group_name}, {table_name}[(int)id], onCompleted);")
                single_lines.append("")
                
                #各自のGetの修正
                if "GameObjectCore" == class_name:
                    single_lines.append(f"       public UnityEngine.GameObject GetGameObject({detail_enum_name}ID id)")
                    single_lines.append(f"            => GetGameObject({group_enum_name}.{group_name}, {table_name}[(int)id]);")
                    single_lines.append("")
                elif "SoundCore" == class_name:
                    single_lines.append(f"       public void PlayBGM({detail_enum_name} id, float volume = 1f, float fadeTime = 0f)")
                    single_lines.append(f"            => PlayBGM({group_enum_name}.{group_name},{table_name}[(int)id],volume,fadeTime);")
                    single_lines.append("")
                    single_lines.append(f"       public void CrossFadeBGM({detail_enum_name} id, float volume = 1f, float fadeTime = 1f)")
                    single_lines.append(f"            => CrossFadeBGM({group_enum_name}.{group_name},{table_name}[(int)id],volume,fadeTime);")
                    single_lines.append("")   
                elif "MaterialCore" == class_name:
                    single_lines.append(f"       public Material GetMaterial({detail_enum_name}ID id)")
                    single_lines.append(f"            => GetMaterial({group_enum_name}.{group_name}, {table_name}[(int)id]);")
                    single_lines.append("")
                                     
                    

    # 削除されたグループ／SubGroupが無くなった分の残骸ファイルを掃除
    if os.path.isdir(target_dir):
        for fname in os.listdir(target_dir):
            if fname.endswith("ID.cs") and fname not in expected_files:
                try:
                    os.remove(os.path.join(target_dir, fname))
                except OSError:
                    pass

    if generate_single_file:
        single_lines.append("    }")
        single_lines.append("}")
        with open(os.path.join(data_dir, f"{class_name}Single.cs"), 'w', encoding='utf-8') as f:
            f.write("\n".join(single_lines))

    return generated_names


def register_enum_names(enum_dir, names):
    """
    enum_list.json に生成済みenum名を（重複を避けつつ）一括登録する
    """
    if not names:
        return
    enum_list_path = os.path.join(enum_dir, 'enum_list.json')
    if not os.path.exists(enum_list_path):
        return
    with open(enum_list_path, 'r+', encoding='utf-8') as f:
        enum_list = json.load(f)
        existing_names = [e['name'] for e in enum_list]
        max_id = max([e['id'] for e in enum_list if 'id' in e], default=0)
        for name in names:
            if name not in existing_names:
                max_id += 1
                enum_list.append({'id': max_id, 'name': name, 'view': False})
                existing_names.append(name)
        f.seek(0)
        json.dump(enum_list, f, ensure_ascii=False, indent=4)
        f.truncate()


def _migrate_group_value(value):
    """
    旧形式（アイテムのリストのみ）を新形式（items/subgroupsを持つdict）へ移行する
    """
    if isinstance(value, list):
        return {'items': value, 'subgroups': []}
    if isinstance(value, dict):
        value.setdefault('items', [])
        value.setdefault('subgroups', [])
        return value
    return {'items': [], 'subgroups': []}


def migrate_groups_data(data):
    """
    data['groups'] の各グループ値を新形式（{'items':[...], 'subgroups':[...]}）へ移行する。
    既に新形式の場合はそのまま返す（冪等）。
    """
    data.setdefault('groups', {})
    for group_name, value in list(data['groups'].items()):
        data['groups'][group_name] = _migrate_group_value(value)
    return data


def add_subgroup_to_group(data, group_name, subgroup_name):
    """
    指定グループにSubGroup名を登録する（登録順がそのままSubGroup enumのID順になる）
    """
    if group_name not in data['groups']:
        raise Exception(f"グループ '{group_name}' が見つかりません。")
    if not subgroup_name:
        raise Exception("SubGroup名を入力してください。")
    group = data['groups'][group_name]
    if subgroup_name not in group['subgroups']:
        group['subgroups'].append(subgroup_name)
    return data


def delete_subgroup_from_group(data, group_name, subgroup_name):
    """
    指定グループからSubGroupを削除する。
    そのSubGroupに属していたアイテムはグループ直下（SubGroup無し）に戻す
    （アイテム自体は削除しない）。
    """
    if group_name not in data['groups']:
        return data
    group = data['groups'][group_name]
    if subgroup_name in group['subgroups']:
        group['subgroups'].remove(subgroup_name)
    for item in group['items']:
        if item.get('subgroup') == subgroup_name:
            item['subgroup'] = None
    return data


def _subgroup_index_map(subgroup_names):
    """
    SubGroup名 -> SubGroup ID（1始まり、Noneは0）の対応表を作る
    """
    return {name: i for i, name in enumerate(subgroup_names, start=1)}


# 実行可能ファイルのディレクトリを取得（PyInstaller対応）
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ディレクトリパスをプロジェクトルート基準に設定
DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "data"))
ASSETS_DATA = os.path.join(DATA_DIR, "assets_data")
SOUND_DATA = os.path.join(ASSETS_DATA, 'sound')
SOUND_JSON = os.path.join(SOUND_DATA, 'assets_sound.json')
TEXTURE_DATA = os.path.join(ASSETS_DATA, 'texture')
TEXTURE_JSON = os.path.join(TEXTURE_DATA, 'assets_texture.json')
GAMEOBJECT_DATA = os.path.join(ASSETS_DATA, 'gameobject')
GAMEOBJECT_JSON = os.path.join(GAMEOBJECT_DATA, 'assets_gameobject.json')
MATERIAL_DATA = os.path.join(ASSETS_DATA, 'material')
MATERIAL_JSON = os.path.join(MATERIAL_DATA, 'assets_material.json')
# Material「CS生成のみ」モード用（Enumへの登録・バイナリへの梱包を一切行わない、独立した保管場所）
MATERIAL_CS_ONLY_DATA = os.path.join(MATERIAL_DATA, 'cs_only')
MATERIAL_CS_ONLY_JSON = os.path.join(MATERIAL_CS_ONLY_DATA, 'assets_material_cs_only.json')
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
    if not os.path.exists(MATERIAL_DATA):
        os.makedirs(MATERIAL_DATA)
    if not os.path.exists(MATERIAL_CS_ONLY_DATA):
        os.makedirs(MATERIAL_CS_ONLY_DATA)
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
        print(enum_list_path)
        print(enum_list)
        max_id = max([e['id'] for e in enum_list], default=0)
        new_entries = [
            {'name': 'Sound', 'path': SOUND_JSON, 'default': {'groups': {}}},
            {'name': 'Texture', 'path': TEXTURE_JSON, 'default': {'groups': {}}},
            {'name': 'GameObject', 'path': GAMEOBJECT_JSON, 'default': {'groups': {}}},
            {'name': 'Material', 'path': MATERIAL_JSON, 'default': {'groups': {}}}
        ]
        for entry in new_entries:
            if entry['name'] not in existing_names:
                max_id += 1
                enum_list.append({'id': max_id, 'name': entry['name'],'view' : False})
                os.makedirs(os.path.dirname(entry['path']), exist_ok=True)
                if not os.path.exists(entry['path']):
                    with open(entry['path'], 'w', encoding='utf-8') as ef:
                        json.dump(entry['default'], ef, ensure_ascii=False, indent=4)
        f.seek(0)
        json.dump(enum_list, f, ensure_ascii=False, indent=4)
        f.truncate()
        
    # 各IDの作成
    for entry in new_entries:
        if not os.path.exists(os.path.join(ENUM_DIR,entry["name"])):
            os.makedirs(os.path.join(ENUM_DIR,entry["name"]))
        code_str = f"""
namespace GameCore.Enums
{{
    public enum {entry["name"]}ID
    {{
        None = 0, // デフォルト値
        Max
    }}
}}
        """
        if not os.path.exists(os.path.join(ENUM_DIR,entry["name"],f"{entry['name']}ID.cs")):
            with open(os.path.join(ENUM_DIR,entry["name"],f"{entry['name']}ID.cs"),"w",encoding="utf-8") as f:
                f.write(code_str)
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
using System.Linq;
using UnityEditor.Animations;

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
            string assetPath = NormalizeAssetPath(data.file_path);
            Debug.Log($"[get_addressable_path] assetPath: {assetPath}");
            return ResolveAddressableAddress(assetPath);
        }
        else if (command == "get_sprite_info")
        {
            string filePath = data.file_path;
            string assetPath = filePath.Replace(@"\\", "/");
            string projectRoot = Path.GetFullPath(Path.Combine(Application.dataPath, "..")).Replace(@"\\", "/").TrimEnd('/');
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
            var sprites = new List<Sprite>();  // Sprite型でリストにする
            foreach (var obj in assets)
            {
                if (obj is Sprite sprite)
                {
                    sprites.Add(sprite);
                }
            }

            // 名前から数値部分を抽出してソート（例: "sprite_10" の "10" をintに変換）
            sprites.Sort((a, b) =>
            {
                int numA = int.Parse(a.name.Split('_').Last());  // 名前が "sprite_数字" 形式の場合
                int numB = int.Parse(b.name.Split('_').Last());
                return numA.CompareTo(numB);
            });

            // 名前リストにする場合
            var spriteNames = sprites.Select(s => s.name).ToList();

            return JsonUtility.ToJson(new Wrapper<string> { items = spriteNames });
        }
        else if (command == "get_animator_controller_info")
        {
            string filePath = data.file_path;
            string assetPath = NormalizeAssetPath(filePath);

            var controller = AssetDatabase.LoadAssetAtPath<UnityEditor.Animations.AnimatorController>(assetPath);
            if (controller == null) return "[]";
            
            var info = new AnimatorFullInfo
            {
                parameters = controller.parameters.Select(p => new ParamInfo
                {
                    name = p.name,
                    type = p.type.ToString(),
                    defaultFloat = p.defaultFloat,
                    defaultInt = p.defaultInt,
                    defaultBool = p.defaultBool
                }).ToList(),


                layers = controller.layers.Select((l,i) => new LayerFullInfo
                {
                    name = l.name ?? "BaseLayer",
                    index = i,
                    states = GetAllStatesInLayer(l.stateMachine).ToList()
                }).ToList()
            };

            return JsonUtility.ToJson(info);
        }
        else if (command == "get_material_properties")
        {
            string filePath = data.file_path;
            string assetPath = NormalizeAssetPath(filePath);

            Shader shader = null;
            string ext = Path.GetExtension(assetPath).ToLowerInvariant();
            if (ext == ".mat")
            {
                Material mat = AssetDatabase.LoadAssetAtPath<Material>(assetPath);
                if (mat != null) shader = mat.shader;
            }
            else if (ext == ".shader" || ext == ".shadergraph")
            {
                // .shadergraph はインポート後に通常のShaderアセットとして
                // AssetDatabaseから読み込める（ShaderGraphImporterを直接使う必要はない）
                shader = AssetDatabase.LoadAssetAtPath<Shader>(assetPath);
            }

            if (shader == null) return "{}";

            // 【重要】UnityEditor.ShaderUtil（旧型式・非推奨寄りのエディタ専用API）は使わない。
            // 代わりにUnityEngine.Shaderのインスタンスメソッド（Runtime/Editor共通、
            // ShaderGraph生成のShaderにも同じように使える）でプロパティを列挙する。
            var props = new List<ShaderPropertyInfo>();
            int propCount = shader.GetPropertyCount();
            for (int i = 0; i < propCount; i++)
            {
                var flags = shader.GetPropertyFlags(i);
                if ((flags & UnityEngine.Rendering.ShaderPropertyFlags.HideInInspector) != 0) continue;

                props.Add(new ShaderPropertyInfo
                {
                    name = shader.GetPropertyName(i),
                    type = shader.GetPropertyType(i).ToString()
                });
            }

            var materialResult = new MaterialPropertiesResult
            {
                items = props
            };

            return JsonUtility.ToJson(materialResult);
        }
        return null;
    }

    // assetPath（"Assets/..."形式、正規化済み）からAddressableのアドレスを取得する。
    // Addressableでなければ assetPath をそのまま返す。
    // get_addressable_path / get_material_properties など、Addressableパスが必要な
    // すべてのコマンドはこのメソッドだけを経由する（duplicate実装の禁止・唯一の実装元）。
    private static string ResolveAddressableAddress(string assetPath)
    {
        if (string.IsNullOrEmpty(assetPath)) return assetPath;

        string guid = AssetDatabase.AssetPathToGUID(assetPath);
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
        if (entry == null)
        {
            Debug.LogWarning($"Asset not Addressable: {assetPath}. Returning relative path.");
            return assetPath;
        }
        return entry.address;
    }

    [System.Serializable]
    private class ShaderPropertyInfo
    {
        public string name;
        public string type;
    }

    [System.Serializable]
    private class MaterialPropertiesResult
    {
        public List<ShaderPropertyInfo> items;
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

    private static string NormalizeAssetPath(string filePath)
    {
        if (string.IsNullOrEmpty(filePath)) return "";

        string projectRoot = Path.GetFullPath(Path.Combine(Application.dataPath, ".."))
            .Replace(@"\\", "/").TrimEnd('/');

        string normalized = filePath.Replace(@"\\", "/").Trim();

        if (normalized.StartsWith(projectRoot, StringComparison.OrdinalIgnoreCase))
        {
            normalized = normalized.Substring(projectRoot.Length).TrimStart('/');
        }

        if (!normalized.StartsWith("Assets/", StringComparison.OrdinalIgnoreCase))
        {
            normalized = "Assets/" + normalized.TrimStart('/');
        }

        return normalized;
    }

    private static IEnumerable<StateFullInfo> GetAllStatesInLayer(AnimatorStateMachine sm)
    {
        foreach (var child in sm.stateMachines)
            foreach (var s in GetAllStatesInLayer(child.stateMachine))
                yield return s;

        foreach (var childState in sm.states)
        {
            var state = childState.state;
            var stateInfo = new StateFullInfo
            {
                name = state.name,
                isBlendTree = state.motion is UnityEditor.Animations.BlendTree,
                blendTree = state.motion is UnityEditor.Animations.BlendTree bt ? GetBlendTreeInfo(bt) : null,
                motions = state.motion is UnityEditor.Animations.BlendTree ? null : new List<string> { state.motion ? state.motion.name : "None" }
            };
            yield return stateInfo;
        }
    }

    private static BlendTreeInfo GetBlendTreeInfo(UnityEditor.Animations.BlendTree bt)
    {
        return new BlendTreeInfo
        {
            blendType = bt.blendType.ToString(),
            blendParameter = bt.blendParameter,
            blendParameterY = bt.blendParameterY,
            children = bt.children.Select(c => new BlendTreeChildInfo
            {
                motionName = c.motion ? c.motion.name : "None",
                threshold = c.threshold,
                timeScale = c.timeScale,
                directBlendParameter = c.directBlendParameter
            }).ToList()
        };
    }

    // シリアライズ用クラス
    [Serializable]
    private class AnimatorFullInfo
    {
        public List<ParamInfo> parameters = new List<ParamInfo>();
        public List<LayerFullInfo> layers = new List<LayerFullInfo>();
    }
    [Serializable]
    private class ParamInfo
    {
        public string name;
        public string type;         // "Float", "Int", "Bool", "Trigger"
        public float defaultFloat;
        public int defaultInt;
        public bool defaultBool;
    }
    [Serializable] private class LayerFullInfo { public string name; public int index; public List<StateFullInfo> states; }
    [Serializable] private class StateFullInfo { public string name; public bool isBlendTree; public List<string> motions; public BlendTreeInfo blendTree; }
    [Serializable] private class BlendTreeInfo { public string blendType; public string blendParameter; public string blendParameterY; public List<BlendTreeChildInfo> children; }
    [Serializable] private class BlendTreeChildInfo { public string motionName; public float threshold; public float timeScale; public string directBlendParameter; }
}
"""
        with open(os.path.join(EDITOR_DATA, "EditorCommunication.cs"), 'w', encoding='utf-8') as f:
            f.write(code_str)
            
    if not os.path.exists(os.path.join(EDITOR_DATA, "AddressableBinCustomizer.cs")):
        code_str = """
        using UnityEngine;
using System.Collections.Generic;
using GameCore;

#if UNITY_EDITOR
using UnityEditor;
using UnityEditor.AddressableAssets;
using UnityEditor.AddressableAssets.Settings;
using System.IO;

[InitializeOnLoad]   // ← 必須
public class AddressableBinCustomizer
{
    private static bool _isProcessing = false;

    static AddressableBinCustomizer()
    {
        AddressableAssetSettings.OnModificationGlobal += OnAddressableModification;
        Debug.Log("[Addressable Bin] カスタムAddress自動設定スクリプトが起動しました");
    }

    private static void OnAddressableModification(AddressableAssetSettings settings,
        AddressableAssetSettings.ModificationEvent e, object obj)
    {
        if (_isProcessing) return;

        // EntryCreated か EntryModified のときだけ処理
        if (e != AddressableAssetSettings.ModificationEvent.EntryCreated &&
            e != AddressableAssetSettings.ModificationEvent.EntryModified &&
            e != AddressableAssetSettings.ModificationEvent.EntryAdded)
            return;

        // ★★★ ここを修正：objが配列の場合も単体のEntryの場合も両方対応 ★★★
        ProcessEntries(settings, obj);
    }

    private static void ProcessEntries(AddressableAssetSettings settings, object data)
    {
        // 1. 単体のEntryの場合
        if (data is AddressableAssetEntry singleEntry)
        {
            ProcessSingleEntry(settings, singleEntry);
            return;
        }

        // 2. 配列（object[]）の場合 ← これがあなたの環境で起きているやつ
        if (data is object[] entryArray)
        {
            foreach (var item in entryArray)
            {
                if (item is AddressableAssetEntry entry)
                    ProcessSingleEntry(settings, entry);
            }
            return;
        }

        // 3. List<AddressableAssetEntry> の場合（念のため）
        if (data is IList<AddressableAssetEntry> entryList)
        {
            foreach (var entry in entryList)
                ProcessSingleEntry(settings, entry);
        }
    }

    private static void ProcessSingleEntry(AddressableAssetSettings settings, AddressableAssetEntry entry)
    {
        if (entry == null) return;

        string assetPath = AssetDatabase.GUIDToAssetPath(entry.guid);
        if (string.IsNullOrEmpty(assetPath) || !assetPath.EndsWith(".bytes", System.StringComparison.OrdinalIgnoreCase))
            return;

        string newAddress = GetCustomAddressForBin(assetPath);

        if (entry.address != newAddress)
        {
            _isProcessing = true;

            entry.address = newAddress;
            settings.SetDirty(AddressableAssetSettings.ModificationEvent.EntryModified, entry, true);

            Debug.Log($"[Addressable Bin] .bytes のAddressを自動設定 → {newAddress}  ({assetPath})");

            _isProcessing = false;
        }
    }

    private static string GetCustomAddressForBin(string assetPath)
    {
        string fileNameWithExt = Path.GetFileName(assetPath);

        List<string> fileDataPath = new List<string>
        {
            SupportFiles.ID_BIN_FILE,
            SupportFiles.MATRIX_ID_BIN_FILE,
            SupportFiles.ALL_GAMEOBJECT_BIN_FILE,
            SupportFiles.ALL_TEXTURE_BIN_FILE,
            SupportFiles.ALL_SOUND_BIN_FILE,
            SupportFiles.ALL_SCENARIO_EVENT_BIN_FILE
        };

        var findData = fileDataPath.Find(x => x.Equals(fileNameWithExt));

        // リストに一致したらファイル名だけ、それ以外は元のフルパス（デフォルト）のまま
        return findData != null ? fileNameWithExt : assetPath;
    }
}
#endif
        """
        with open(os.path.join(EDITOR_DATA, "AddressableBinCustomizer.cs"), 'w', encoding='utf-8') as f:
            f.write(code_str)

def load_sound_data():
    """
    assets_sound.jsonを読み込む
    """
    if os.path.exists(SOUND_JSON):
        with open(SOUND_JSON, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return migrate_groups_data(data)
    return {'groups': {}}

def save_sound_data(data):
    """
    assets_sound.jsonを保存
    """
    with open(SOUND_JSON, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def load_texture_data():
    """
    assets_texture.jsonを読み込む
    """
    if os.path.exists(TEXTURE_JSON):
        with open(TEXTURE_JSON, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return migrate_groups_data(data)
    return {'groups': {}}

def save_texture_data(data):
    """
    assets_texture.jsonを保存
    """
    with open(TEXTURE_JSON, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def load_gameobject_data():
    """
    assets_gameobject.jsonを読み込む
    """
    if os.path.exists(GAMEOBJECT_JSON):
        with open(GAMEOBJECT_JSON, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return migrate_groups_data(data)
    return {'groups': {}}

def save_gameobject_data(data):
    """
    assets_gameobject.jsonを保存
    """
    with open(GAMEOBJECT_JSON, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def load_material_data():
    """
    assets_material.jsonを読み込む
    GameObject/Sound/Textureと同じ「groups」形式（グループ紐づけ）で保持する。
    旧形式（entries直下フラット）で保存されていた場合は、Defaultグループへ自動移行する。
    """
    if os.path.exists(MATERIAL_JSON):
        with open(MATERIAL_JSON, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if 'groups' not in data:
            old_entries = data.get('entries', [])
            data = {'groups': ({'Default': old_entries} if old_entries else {})}
        return migrate_groups_data(data)
    return {'groups': {}}

def save_material_data(data):
    """
    assets_material.jsonを保存
    """
    with open(MATERIAL_JSON, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

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
    return load_sound_data()

def add_sound_group(group_name):
    """
    サウンドグループを追加
    """
    data = load_sound_data()
    if group_name and group_name not in data['groups']:
        data['groups'][group_name] = {'items': [], 'subgroups': []}
        save_sound_data(data)

def delete_sound_group(group_name):
    """
    サウンドグループを削除
    """
    data = load_sound_data()
    data['groups'].pop(group_name, None)
    save_sound_data(data)

def add_sound_subgroup(group_name, subgroup_name):
    """
    サウンドグループの中にSubGroupを追加する
    """
    data = load_sound_data()
    add_subgroup_to_group(data, group_name, subgroup_name)
    save_sound_data(data)

def delete_sound_subgroup(group_name, subgroup_name):
    """
    サウンドグループからSubGroupを削除する
    """
    data = load_sound_data()
    delete_subgroup_from_group(data, group_name, subgroup_name)
    save_sound_data(data)

def add_sound(group_name, name, desc, volume, sound_type, subgroup_name=None):
    """
    サウンドをグループ（必要であればSubGroup）に追加
    """
    data = load_sound_data()
    if subgroup_name and subgroup_name not in data['groups'][group_name]['subgroups']:
        raise Exception(f"SubGroup '{subgroup_name}' が見つかりません。先にSubGroupを作成してください。")
    project_path = get_unity_project_path()
    if not project_path:
        raise Exception("Unityプロジェクトのパスを取得できませんでした。")
    file_path = select_file(project_path, [("音声ファイル", "*.mp3 *.wav")])
    if not file_path:
        raise Exception("ファイルが選択されていません。")
    addr_path = get_addressable_path(file_path)
    if not addr_path:
        raise Exception("アドレス指定可能なパスを取得できませんでした。")
    data['groups'][group_name]['items'].append({
        'name': name, 
        'desc': desc, 
        'path': addr_path,
        'absolute_path': os.path.abspath(file_path),
        'volume': volume, 
        'type': sound_type,
        'subgroup': subgroup_name or None
    })
    save_sound_data(data)

def delete_sound(group_name, index):
    """
    サウンドをグループから削除
    """
    data = load_sound_data()
    del data['groups'][group_name]['items'][index]
    save_sound_data(data)

def edit_sound(group_name, index, name=None, desc=None, volume=None, sound_type=None, subgroup_name=None):
    """
    既存のサウンドエントリを編集する（ファイルの再選択は行わない）
    """
    data = load_sound_data()
    if group_name not in data['groups']:
        raise Exception(f"グループ '{group_name}' が見つかりません。")
    items = data['groups'][group_name]['items']
    if index < 0 or index >= len(items):
        raise Exception("対象のデータが見つかりません。")
    if subgroup_name and subgroup_name not in data['groups'][group_name]['subgroups']:
        raise Exception(f"SubGroup '{subgroup_name}' が見つかりません。先にSubGroupを作成してください。")

    entry = items[index]
    if name is not None:
        entry['name'] = name
    if desc is not None:
        entry['desc'] = desc
    if volume is not None:
        entry['volume'] = volume
    if sound_type is not None:
        entry['type'] = sound_type
    entry['subgroup'] = subgroup_name or None
    save_sound_data(data)

def reload_sound_file(group_name, index):
    """
    既存エントリのファイル参照だけを再選択・再取得する。
    エクスプローラーは、そのエントリで前回選択済みのパスのフォルダから開く。
    """
    data = load_sound_data()
    if group_name not in data['groups']:
        raise Exception(f"グループ '{group_name}' が見つかりません。")
    items = data['groups'][group_name]['items']
    if index < 0 or index >= len(items):
        raise Exception("対象のデータが見つかりません。")

    entry = items[index]
    prev_path = entry.get('absolute_path')
    initial_dir = os.path.dirname(prev_path) if prev_path and os.path.isdir(os.path.dirname(prev_path)) else get_unity_project_path()
    if not initial_dir:
        raise Exception("Unityプロジェクトのパスを取得できませんでした。")

    file_path = select_file(initial_dir, [("音声ファイル", "*.mp3 *.wav")])
    if not file_path:
        raise Exception("ファイルが選択されていません。")
    addr_path = get_addressable_path(file_path)
    if not addr_path:
        raise Exception("アドレス指定可能なパスを取得できませんでした。")

    entry['path'] = addr_path
    entry['absolute_path'] = os.path.abspath(file_path)
    save_sound_data(data)
    return entry

def generate_sound_csharp():
    """
    サウンド関連のC#コードとJSONを生成
    - SoundEnums.cs, SoundCore.cs, SoundDatabase.cs を生成
    - assets_sound.json を更新
    - ENUM_DIR/Sound/Sound.json を生成
    """
    data = load_sound_data()

    # SoundEnums.cs
    with open(os.path.join(SOUND_DATA, 'SoundEnums.cs'), 'w', encoding='utf-8') as f:
        f.write('namespace GameCore.Sound {\n')
        f.write('    public enum SoundGroup { None')
        for group in data['groups']:
            f.write(f', {group}')
        f.write(' ,Max\n  };\n')
        f.write('    public enum SoundType { SE, BGM };\n')
        sound_id_counter = 1
        sound_id_map = {'None': 0}
        for group, group_value in data['groups'].items():
            for sound in group_value['items']:
                sound_id = f"{group}_{sound['name']}"
                if sound_id not in sound_id_map:
                    sound_id_map[sound_id] = sound_id_counter
                    sound_id_counter += 1
        f.write('}\n')

    # SubGroup用enum（Sound_{Group}ID）を各グループごとに生成／同期
    subgroup_enum_names = sync_subgroup_enum_files(
    ENUM_DIR, "Sound", data['groups'],
    data_dir=SOUND_DATA, namespace="GameCore.Sound", class_name="SoundCore",
    group_enum_name="SoundGroup", id_enum_name="SoundID"
    )
    register_enum_names(ENUM_DIR, subgroup_enum_names)

    # SoundCore.cs
    if not os.path.exists(os.path.join(SOUND_DATA, "SoundCore.cs")):
        code_str = """
using System;
using System.Collections.Generic;
using UnityEngine;
using Cysharp.Threading.Tasks;
using AddressableSystem;
using GameCore.SaveSystem;
using GameCore.Enums;
using System.Linq;
using System.Threading;

namespace GameCore.Sound
{
    public partial class SoundCore : BaseSingleton<SoundCore>
    {
        // =============================================================
        // 爆速キャッシュ（LINQ完全排除、Dictionary 1段）
        // =============================================================
        private readonly Dictionary<(SoundGroup group, SoundID id), AudioClip> clipCache = new();
        private readonly Dictionary<(SoundGroup group, SoundID id), float> volumeCache = new();
        private readonly Dictionary<(SoundGroup group, SoundID id), SoundType> typeCache = new();
        private readonly HashSet<(SoundGroup group, SoundID id)> loadingKeys = new();

        // Addressable本体は (group, id) 単位で保持。
        // グループ一括ロード／個別ロード／SubGroupロードのいずれでも同じ辞書を使い、
        // 専用の管理は持たない（Unloadは対象のkeyを絞り込んで、このDictionaryから解放するだけ）。
        private readonly Dictionary<(SoundGroup group, SoundID id), AddressableData<AudioClip>> soundAddressables = new();

        private SoundDatabase database;

        // =============================================================
        // AudioSource管理（プールは循環インデックスで最速）
        // =============================================================
        private AudioSource bgmSource;
        private AudioSource crossFadeTempSource;
        private readonly List<AudioSource> sePool = new();
        private const int PoolSize = 30;
        private int poolIndex = 0;

        private bool isCrossFading = false;

        // =============================================================
        // キャンセルトークン（シーン遷移時の完全停止＆ゾンビタスク防止）
        // =============================================================
        private CancellationToken destroyToken;
        private CancellationTokenSource manualCancelSource = new();
        private CancellationToken combinedToken;

        public bool IsLoadDatabase { get; private set; }

        public override void AwakeSingleton()
        {
            base.AwakeSingleton();
            instance = this;
            DontDestroyOnLoad(gameObject);

            destroyToken = this.GetCancellationTokenOnDestroy();
            manualCancelSource = new CancellationTokenSource();
            combinedToken = CancellationTokenSource.CreateLinkedTokenSource(destroyToken, manualCancelSource.Token).Token;

            bgmSource = gameObject.AddComponent<AudioSource>();
            bgmSource.loop = true;
            bgmSource.playOnAwake = false;

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
            string path = SupportFiles.ADDRESSABLE_CHECK ? SupportFiles.ALL_SOUND_BIN_FILE : SupportFiles.ALL_SOUND_BIN;
            database =  await SoundBinaryReader.LoadSoundDatabaseFromBinaryAsync(path,SupportFiles.ADDRESSABLE_CHECK);
            if (database == null)
                Debug.LogError("[SoundCore] Failed to load SoundDatabase.");
            await UniTask.CompletedTask.AttachExternalCancellation(destroyToken);

            IsLoadDatabase = true;
        }

        // =============================================================
        // シーン遷移時に必ず呼ぶ！！（これが全てを守る）
        // =============================================================
        public void StopAllAndCancelAllTasks()
        {
            manualCancelSource.Cancel();
            manualCancelSource.Dispose();
            manualCancelSource = new CancellationTokenSource();
            combinedToken = CancellationTokenSource.CreateLinkedTokenSource(destroyToken, manualCancelSource.Token).Token;

            foreach (var source in sePool)
            {
                if (source != null)
                {
                    if (source.isPlaying) source.Stop();
                    source.clip = null;
                }
            }

            if (bgmSource != null)
            {
                if (bgmSource.isPlaying) bgmSource.Stop();
                bgmSource.clip = null;
            }

            if (crossFadeTempSource != null)
            {
                crossFadeTempSource.Stop();
                Destroy(crossFadeTempSource);
                crossFadeTempSource = null;
            }

            isCrossFading = false;
        }

        /// <summary>
        /// その音のBaseVolume（データベースに登録された元の音量）を取得
        /// 存在しない場合は1.0fを返す
        /// </summary>
        public float GetSoundVolume(SoundGroup group, SoundID id)
        {
            var key = (group, id);
            return volumeCache.TryGetValue(key, out var volume) ? volume : 1f;
        }

        /// <summary>
        /// ロード済みのAudioClipを直接取得（UIプレビューや特殊処理用）
        /// ロードされてなければnull
        /// </summary>
        public AudioClip GetSoundClip(SoundGroup group, SoundID id)
        {
            var key = (group, id);
            clipCache.TryGetValue(key, out var clip);
            return clip;
        }

        /// <summary>
        /// そのサウンドがSEかBGMかを取得（ロード前でも判定可能にするなら別途キャッシュ必要）
        /// </summary>
        public SoundType GetSoundType(SoundGroup group, SoundID id)
        {
            var key = (group, id);
            return typeCache.TryGetValue(key, out var type) ? type : SoundType.SE;
        }

        // =============================================================
        // グループロード／アンロード
        // =============================================================
        public void LoadGroup(SoundGroup group, GroupCategory category, Action onCompleted = null)
            => LoadGroupAsync(group, category, onCompleted).Forget();

        public async UniTask LoadGroupAsync(SoundGroup group, GroupCategory category, Action onCompleted)
        {
            while (!IsLoadDatabase)
                await UniTask.Yield(combinedToken);

            var groupData = database.GroupedSoundsList.FirstOrDefault(x => x.Group == group);
            if (groupData == null) { onCompleted?.Invoke(); return; }

            var tasks = new List<UniTask>();

            foreach (var sound in groupData.Sounds)
            {
                var key = (group, sound.SoundID);
                if (clipCache.ContainsKey(key) || loadingKeys.Contains(key)) continue;

                loadingKeys.Add(key);

                var addressable = new AddressableData<AudioClip>(category, AssetCategory.Audio, sound.AddressablePath);

                tasks.Add(addressable.LoadAsync(clip =>
                {
                    if (addressable.IsLoadedAndSetup)
                    {
                        clipCache[key] = clip;
                        volumeCache[key] = sound.BaseVolume;
                        typeCache[key] = sound.Type;
                        soundAddressables[key] = addressable;
                    }
                    loadingKeys.Remove(key);
                }, ex =>
                {
                    Debug.LogError($"[SoundCore] Load failed {sound.SoundID}: {ex.Message}");
                    loadingKeys.Remove(key);
                }).AttachExternalCancellation(combinedToken));
            }

            await UniTask.WhenAll(tasks);
            onCompleted?.Invoke();
        }

        public void UnloadGroup(SoundGroup group, GroupCategory category, Action onCompleted = null)
            => UnloadGroupAsync(group, onCompleted).Forget();

        private async UniTask UnloadGroupAsync(SoundGroup group, Action onCompleted)
        {
            var keysToRemove = new List<(SoundGroup, SoundID)>();
            foreach (var kv in clipCache)
                if (kv.Key.group == group) keysToRemove.Add(kv.Key);

            foreach (var key in keysToRemove)
            {
                if (soundAddressables.TryGetValue(key, out var addressable))
                {
                    addressable.ReleaseAndUntrack();
                    soundAddressables.Remove(key);
                }
                clipCache.Remove(key);
                volumeCache.Remove(key);
                typeCache.Remove(key);
            }

            onCompleted?.Invoke();
            await UniTask.CompletedTask;
        }

        // =============================================================
        // 個別ID単位のロード／アンロード
        // グループロードと同じ soundAddressables / clipCache 等をそのまま使う。
        // =============================================================
        internal void LoadSingle(SoundGroup group, SoundID id, GroupCategory category, Action onCompleted = null)
            => LoadSingleAsync(group, id, category, onCompleted).Forget();

        internal async UniTask LoadSingleAsync(SoundGroup group, SoundID id, GroupCategory category, Action onCompleted = null)
        {
            while (!IsLoadDatabase)
                await UniTask.Yield(combinedToken);

            var key = (group, id);
            if (clipCache.ContainsKey(key) || loadingKeys.Contains(key))
            {
                onCompleted?.Invoke();
                return;
            }

            var groupData = database.GroupedSoundsList.FirstOrDefault(x => x.Group == group);
            var sound = groupData?.Sounds.FirstOrDefault(s => s.SoundID == id);
            if (sound == null) { onCompleted?.Invoke(); return; }

            loadingKeys.Add(key);
            var addressable = new AddressableData<AudioClip>(category, AssetCategory.Audio, sound.AddressablePath);
            await addressable.LoadAsync(clip =>
            {
                if (addressable.IsLoadedAndSetup)
                {
                    clipCache[key] = clip;
                    volumeCache[key] = sound.BaseVolume;
                    typeCache[key] = sound.Type;
                    soundAddressables[key] = addressable;
                }
                loadingKeys.Remove(key);
            }, ex =>
            {
                Debug.LogError($"[SoundCore] Load failed (single) {id}: {ex.Message}");
                loadingKeys.Remove(key);
            }).AttachExternalCancellation(combinedToken);

            onCompleted?.Invoke();
        }

        public void UnloadSingle(SoundGroup group, SoundID id, Action onCompleted = null)
            => UnloadSingleAsync(group, id, onCompleted).Forget();

        public async UniTask UnloadSingleAsync(SoundGroup group, SoundID id, Action onCompleted = null)
        {
            var key = (group, id);
            if (soundAddressables.TryGetValue(key, out var addressable))
            {
                addressable.ReleaseAndUntrack();
                soundAddressables.Remove(key);
                clipCache.Remove(key);
                volumeCache.Remove(key);
                typeCache.Remove(key);
            }
            onCompleted?.Invoke();
            await UniTask.CompletedTask;
        }

        // =============================================================
        // SubGroup単位のロード／アンロード（内部実装）
        // 公開APIは SoundCoreSubGroups.cs 側で、グループごとの
        // 専用enum（例: Sound_EnemyID）を受け取るオーバーロードとして生成される。
        // どのサウンドがどのSubGroupに属するかは SoundData.SubGroupId から都度判定する。
        // グループロードと同じ soundAddressables / clipCache 等をそのまま使い、
        // 専用の管理は持たない。
        // =============================================================
        internal void LoadSubGroupInternal(SoundGroup group, int subGroupId, GroupCategory category, Action onCompleted = null)
            => LoadSubGroupInternalAsync(group, subGroupId, category, onCompleted).Forget();

        internal async UniTask LoadSubGroupInternalAsync(SoundGroup group, int subGroupId, GroupCategory category, Action onCompleted = null)
        {
            while (!IsLoadDatabase)
                await UniTask.Yield(combinedToken);

            var groupData = database.GroupedSoundsList.FirstOrDefault(x => x.Group == group);
            if (groupData == null) { onCompleted?.Invoke(); return; }

            var tasks = new List<UniTask>();
            foreach (var sound in groupData.Sounds)
            {
                if (sound.SubGroupId != subGroupId) continue;
                var key = (group, sound.SoundID);
                if (clipCache.ContainsKey(key) || loadingKeys.Contains(key)) continue;

                loadingKeys.Add(key);
                var addressable = new AddressableData<AudioClip>(category, AssetCategory.Audio, sound.AddressablePath);

                tasks.Add(addressable.LoadAsync(clip =>
                {
                    if (addressable.IsLoadedAndSetup)
                    {
                        clipCache[key] = clip;
                        volumeCache[key] = sound.BaseVolume;
                        typeCache[key] = sound.Type;
                        soundAddressables[key] = addressable;
                    }
                    loadingKeys.Remove(key);
                }, ex =>
                {
                    Debug.LogError($"[SoundCore] Load failed (subgroup) {sound.SoundID}: {ex.Message}");
                    loadingKeys.Remove(key);
                }).AttachExternalCancellation(combinedToken));
            }

            await UniTask.WhenAll(tasks);
            onCompleted?.Invoke();
        }

        internal void UnloadSubGroupInternal(SoundGroup group, int subGroupId, Action onCompleted = null)
            => UnloadSubGroupInternalAsync(group, subGroupId, onCompleted).Forget();

        internal async UniTask UnloadSubGroupInternalAsync(SoundGroup group, int subGroupId, Action onCompleted = null)
        {
            if (database != null)
            {
                var groupData = database.GroupedSoundsList.FirstOrDefault(x => x.Group == group);
                if (groupData != null)
                {
                    foreach (var sound in groupData.Sounds)
                    {
                        if (sound.SubGroupId != subGroupId) continue;
                        var key = (group, sound.SoundID);
                        if (soundAddressables.TryGetValue(key, out var addressable))
                        {
                            addressable.ReleaseAndUntrack();
                            soundAddressables.Remove(key);
                        }
                        clipCache.Remove(key);
                        volumeCache.Remove(key);
                        typeCache.Remove(key);
                    }
                }
            }

            onCompleted?.Invoke();
            await UniTask.CompletedTask;
        }

        // =============================================================
        // SE再生（最速・安全）
        // =============================================================
        public void PlaySE(SoundGroup group, SoundID id, float volume = 1f, bool is3D = false, Vector3 position = default, float maxDistance = 500f)
            => PlaySEAsync(group, id, volume, is3D, position, maxDistance).Forget();

        private async UniTask PlaySEAsync(SoundGroup group, SoundID id, float volume, bool is3D, Vector3 position, float maxDistance)
        {
            var key = (group, id);

            if (!clipCache.TryGetValue(key, out var clip) ||
                !volumeCache.TryGetValue(key, out var baseVolume) ||
                !typeCache.TryGetValue(key, out var type) || type != SoundType.SE)
                return;

            var source = GetPooledSourceFast();
            if (source == null) return;

            source.clip = clip;
            source.volume = baseVolume * volume * SaveManagerCore.instance.SystemSettings.seVolume;
            source.loop = false;
            source.spatialBlend = is3D ? 1f : 0f;
            source.maxDistance = maxDistance;
            if (is3D) source.transform.position = position;

            source.Play();

            try
            {
                await UniTask.WaitUntil(() => !source.isPlaying, cancellationToken: combinedToken);
            }
            catch (OperationCanceledException) { }
            finally
            {
                ResetSource(source);
            }
        }

        private AudioSource GetPooledSourceFast()
        {
            int startIndex = poolIndex;
            do
            {
                var source = sePool[poolIndex];
                if (!source.isPlaying)
                {
                    ResetSource(source);
                    poolIndex = (poolIndex + 1) % PoolSize;
                    return source;
                }
                poolIndex = (poolIndex + 1) % PoolSize;
            } while (poolIndex != startIndex);

            var victim = sePool[0];
            ResetSource(victim);
            return victim;
        }

        // =============================================================
        // BGM再生・フェード・クロスフェード
        // =============================================================
        public void PlayBGM(SoundGroup group, SoundID id, float volume = 1f, float fadeTime = 0f)
            => PlayBGMAsync(group, id, volume, fadeTime).Forget();

        private async UniTask PlayBGMAsync(SoundGroup group, SoundID id, float volume, float fadeTime)
        {
            var key = (group, id);
            if (!clipCache.TryGetValue(key, out var clip) ||
                !volumeCache.TryGetValue(key, out var baseVolume) ||
                !typeCache.TryGetValue(key, out var type) || type != SoundType.BGM)
                return;

            if (bgmSource.isPlaying && fadeTime > 0f)
                await FadeOutAsync(fadeTime);

            bgmSource.clip = clip;
            bgmSource.volume = 0f;
            bgmSource.Play();

            float targetVolume = baseVolume * volume * SaveManagerCore.instance.SystemSettings.bgmVolume;
            if (fadeTime > 0f)
                await FadeInAsync(targetVolume, fadeTime);
            else
                bgmSource.volume = targetVolume;
        }

        public void CrossFadeBGM(SoundGroup group, SoundID id, float volume = 1f, float fadeTime = 1f)
            => CrossFadeBGMAsync(group, id, volume, fadeTime).Forget();

        private async UniTask CrossFadeBGMAsync(SoundGroup group, SoundID id, float volume, float fadeTime)
        {
            var key = (group, id);
            if (!clipCache.TryGetValue(key, out var clip) ||
                !volumeCache.TryGetValue(key, out var baseVolume) ||
                !typeCache.TryGetValue(key, out var type) || type != SoundType.BGM)
                return;

            isCrossFading = true;

            crossFadeTempSource = gameObject.AddComponent<AudioSource>();
            crossFadeTempSource.loop = true;
            crossFadeTempSource.clip = clip;
            crossFadeTempSource.volume = 0f;
            crossFadeTempSource.Play();

            float startVolume = bgmSource.volume;
            float targetVolume = baseVolume * volume * SaveManagerCore.instance.SystemSettings.bgmVolume;

            float timer = 0f;
            while (timer < fadeTime)
            {
                timer += Time.deltaTime;
                float t = Mathf.Clamp01(timer / fadeTime);
                bgmSource.volume = Mathf.Lerp(startVolume, 0f, t);
                crossFadeTempSource.volume = Mathf.Lerp(0f, targetVolume, t);
                await UniTask.Yield(combinedToken);
            }

            bgmSource.Stop();
            Destroy(bgmSource);
            bgmSource = crossFadeTempSource;
            bgmSource.volume = targetVolume;
            crossFadeTempSource = null;
            isCrossFading = false;
        }

        private async UniTask FadeOutAsync(float fadeTime, Action onCompleted = null)
        {
            if (!bgmSource.isPlaying) { onCompleted?.Invoke(); return; }

            float startVolume = bgmSource.volume;
            float timer = 0f;

            while (timer < fadeTime)
            {
                timer += Time.deltaTime;
                bgmSource.volume = Mathf.Lerp(startVolume, 0f, timer / fadeTime);
                if (timer >= fadeTime) break;
                await UniTask.Yield(combinedToken);
            }

            bgmSource.volume = 0f;
            bgmSource.Stop();
            bgmSource.clip = null;
            onCompleted?.Invoke();
        }

        private async UniTask FadeInAsync(float targetVolume, float fadeTime, Action onCompleted = null)
        {
            float timer = 0f;
            while (timer < fadeTime)
            {
                timer += Time.deltaTime;
                bgmSource.volume = Mathf.Lerp(0f, targetVolume, timer / fadeTime);
                if (timer >= fadeTime) break;
                await UniTask.Yield(combinedToken);
            }
            bgmSource.volume = targetVolume;
            onCompleted?.Invoke();
        }

        // =============================================================
        // ユーティリティ
        // =============================================================
        private void ResetSource(AudioSource source)
        {
            if (source == null) return;
            source.Stop();
            source.clip = null;
            source.volume = 0f;
            source.spatialBlend = 0f;
        }

        public void SetSystemBGMVolume()
        {
            if (bgmSource != null && bgmSource.isPlaying)
                bgmSource.volume = bgmSource.volume / SaveManagerCore.instance.SystemSettings.bgmVolume * SaveManagerCore.instance.SystemSettings.bgmVolume;
        }

        public void SetSystemSEVolume()
        {
            float vol = SaveManagerCore.instance.SystemSettings.seVolume;
            foreach (var s in sePool) s.volume = vol;
        }

        private void Update()
        {
            if (bgmSource == null && !isCrossFading)
                bgmSource = gameObject.AddComponent<AudioSource>();

            sePool.RemoveAll(s => s == null);
        }

        private void OnDestroy()
        {
            StopAllAndCancelAllTasks();

            foreach (var addr in soundAddressables.Values)
                addr.Release();

            clipCache.Clear();
            volumeCache.Clear();
            typeCache.Clear();
            soundAddressables.Clear();
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
using GameCore.Enums;
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
            private readonly int subGroupId;
            public SoundData(SoundID soundID, string idName, string addressablePath, float baseVolume, SoundType type, int subGroupId = 0)
            {
                this.idName = idName;
                this.addressablePath = addressablePath;
                this.baseVolume = baseVolume;
                this.type = type;
                this.soundID = soundID;
                this.subGroupId = subGroupId;
            }
            public string IdName => idName;
            public string AddressablePath => addressablePath;
            public float BaseVolume => baseVolume;
            public SoundID SoundID => soundID;
            public SoundType Type => type;
            // SubGroup ID（0 = SubGroupなし）。専用enum(例:Sound_EnemyID)にキャストして使う
            public int SubGroupId => subGroupId;
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
            
    if not os.path.exists(os.path.join(SOUND_DATA, 'SoundBinaryReader.cs')):
        code_str = """
        
using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;
using GameCore.Enums;
using UnityEngine.AddressableAssets;         
using UnityEngine.ResourceManagement.AsyncOperations;
using Cysharp.Threading.Tasks;

namespace GameCore.Sound
{
    public class SoundBinaryReader
    {

        public static async UniTask<SoundDatabase> LoadSoundDatabaseFromBinaryAsync(string filePath, bool addressable = false)
        {
            if (!addressable)
            {
                if (!File.Exists(filePath))
                {
                    UnityEngine.Debug.LogError($"Binary file not found: {filePath}");
                    return null;
                }

                return await UniTask.RunOnThreadPool(() =>
                {
                    using (BinaryReader reader = new BinaryReader(File.Open(filePath, FileMode.Open)))
                    {
                        return ReadDatabase(reader);
                    }
                });
            }
            else
            {
                // ====================== Addressableの場合 ======================

                AsyncOperationHandle<TextAsset> handle = Addressables.LoadAssetAsync<TextAsset>(filePath);

                await handle.ToUniTask();   // ここはメインスレッドで待機完了

                if (handle.Status != AsyncOperationStatus.Succeeded || handle.Result == null)
                {
                    UnityEngine.Debug.LogError($"Failed to load Addressable binary: {filePath}");
                    if (handle.IsValid()) Addressables.Release(handle);
                    return null;
                }

                TextAsset textAsset = handle.Result;

                // ★★★ ここでメインスレッド上で .bytes を取得 ★★★
                byte[] rawBytes = textAsset.bytes;        // ← これを先に取る！

                // 解析だけ別スレッドに逃がす
                SoundDatabase database;
                using (MemoryStream ms = new MemoryStream(rawBytes))
                using (BinaryReader reader = new BinaryReader(ms))
                {
                    database = ReadDatabase(reader);
                }

                Addressables.Release(handle);

                return database;
            }
        }
        public static SoundDatabase LoadSoundDatabaseFromBinary(string filePath, bool addressable = false)
        {
            if (!addressable)
            {
                if (!File.Exists(filePath))
                {
                    Debug.LogError($"Binary file not found: {filePath}");
                    return null;
                }

                using (BinaryReader reader = new BinaryReader(File.Open(filePath, FileMode.Open)))
                {
                    return ReadDatabase(reader);
                }
            }
            else
            {
                // ====================== Addressableの場合 ======================
                // sound_data.bytes
                AsyncOperationHandle<TextAsset> handle = Addressables.LoadAssetAsync<TextAsset>(filePath);


                handle.WaitForCompletion();


                if (handle.Status != AsyncOperationStatus.Succeeded || handle.Result == null)
                {
                    Debug.LogError($"Failed to load Addressable binary: {filePath}");
                    if (handle.IsValid()) Addressables.Release(handle);
                    return null;
                }

                TextAsset textAsset = handle.Result;

                using (MemoryStream ms = new MemoryStream(textAsset.bytes))
                using (BinaryReader reader = new BinaryReader(ms))
                {
                    SoundDatabase database = ReadDatabase(reader);
                    Addressables.Release(handle);
                    return database;
                }
            }
        }

        // 共通読み込みロジック
        private static SoundDatabase ReadDatabase(BinaryReader reader)
        {
            SoundDatabase database = new SoundDatabase();

            int groupCount = reader.ReadInt32();
            int[] offsets = new int[groupCount];

            for (int i = 0; i < groupCount; i++)
            {
                offsets[i] = reader.ReadInt32();
            }

            string[] groupNames = Enum.GetNames(typeof(SoundGroup));
            if (groupCount > groupNames.Length - 1)
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
                    int subGroupId = reader.ReadInt32();

                    string enumName = Enum.GetName(typeof(SoundID), id) ?? $"Unknown_{id}";

                    sounds.Add(new SoundDatabase.SoundData(
                        idName: enumName,
                        addressablePath: addressablePath,
                        baseVolume: volume,
                        type: type,
                        soundID: (SoundID)id,
                        subGroupId: subGroupId
                    ));
                }

                database.GroupedSoundsList.Add(new SoundDatabase.GroupedSounds(
                    group: (SoundGroup)(i + 1),
                    sounds: sounds
                ));
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

""" 
        with open(os.path.join(SOUND_DATA, 'SoundBinaryReader.cs'), 'w', encoding='utf-8') as f:
            f.write(code_str)
            
            
    if not os.path.exists(os.path.join(SOUND_DATA,"SoundObjectPool.cs")):
        code_str = """
//===================================================================
// SoundObjectPool.cs 
//==================================================================
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using UnityEngine;
using Cysharp.Threading.Tasks;
using GameCore.Enums;
using GameCore.Sound;
using GameCore.SaveSystem;

namespace GameCore.Sound
{
    // =============================================================
    // メインクラス：SoundObjectPool
    // =============================================================
    public sealed class SoundObjectPool : BaseSingleton<SoundObjectPool>
    {
        private readonly Dictionary<(SoundGroup group, SoundID id), SoundPool> sePools = new();
        private readonly ConcurrentDictionary<(SoundGroup group, SoundID id), UniTask<SoundPool>> creatingPools = new();
        private readonly BGMChannel[] bgmChannels = new BGMChannel[4];

        // キャンセルトークン（全UniTaskをシーン遷移時に即殺）
        private CancellationToken destroyToken;
        private CancellationTokenSource manualCancelSource = new();
        private CancellationToken combinedToken;

        public override void AwakeSingleton()
        {
            base.AwakeSingleton();
            DontDestroyOnLoad(gameObject);

            destroyToken = this.GetCancellationTokenOnDestroy();
            manualCancelSource = new CancellationTokenSource();
            combinedToken = CancellationTokenSource.CreateLinkedTokenSource(destroyToken, manualCancelSource.Token).Token;

            for (int i = 0; i < bgmChannels.Length; i++)
                bgmChannels[i] = new BGMChannel(i, combinedToken);
        }
        // =============================================================
        // 全停止＆全キャンセル（シーン遷移時に絶対呼ぶ！）
        // =============================================================
        public void StopAllAndCancelAllTasks()
        {
            manualCancelSource.Cancel();
            manualCancelSource.Dispose();
            manualCancelSource = new CancellationTokenSource();
            combinedToken = CancellationTokenSource.CreateLinkedTokenSource(destroyToken, manualCancelSource.Token).Token;

            foreach (var pool in sePools.Values)
                pool?.StopAllImmediately();

            foreach (var channel in bgmChannels)
                channel?.StopImmediately();

           
            creatingPools.Clear();

        }

        // =============================================================
        // 個別SE停止（特定Group+ID or 全SE）
        // =============================================================
        public void StopSE(SoundGroup group, SoundID id)
        {
            var key = (group, id);
            if (sePools.TryGetValue(key, out var pool))
                pool.StopAllImmediately();
        }

        public void StopAllSE()
        {
            foreach (var pool in sePools.Values)
                pool?.StopAllImmediately();
        }

        // =============================================================
        // SE再生
        // =============================================================
        public static async UniTask<SoundHandle> PlaySE(
            SoundGroup group,
            SoundID id,
            Vector3 position,
            float volume = 1f,
            float pitch = 1f,
            float forceDuration = -1f,
            float distance = 0f,
            Action<SoundHandle> onCompleted = null)
        {
            volume = (volume * SoundCore.Instance.GetSoundVolume(group, id)) * SaveManagerCore.instance.SystemSettings.seVolume;
            var pool = await Instance.GetOrCreateSEPool(group, id);
            if (pool == null) return default;

            await pool.WaitForAvailableAsync(Instance.combinedToken);
            return pool.PlayImmediately(position, volume, pitch, forceDuration, distance, onCompleted);
        }

        // =============================================================
        // BGM再生・停止
        // =============================================================
        public static async UniTask PlayBGM(int channel, SoundGroup group, SoundID id, float fadeIn = 1f, float volume = 1f)
        {
            if (channel < 0 || channel >= Instance.bgmChannels.Length) return;
            volume = (volume * SoundCore.Instance.GetSoundVolume(group, id)) * SaveManagerCore.instance.SystemSettings.bgmVolume;
            await Instance.bgmChannels[channel].Play(group, id, fadeIn, volume, Instance.combinedToken);
        }

        public static async UniTask StopBGM(int channel, float fadeOut = 1f, Action onComplete = null)
        {
            if (channel < 0 || channel >= Instance.bgmChannels.Length) return;
            await Instance.bgmChannels[channel].StopAsync(fadeOut, onComplete, Instance.combinedToken);
        }

        public static void StopBGMImmediately(int channel)
        {
            if (channel >= 0 && channel < Instance.bgmChannels.Length)
                Instance.bgmChannels[channel].StopImmediately();
        }

        private async UniTask<SoundPool> GetOrCreateSEPool(SoundGroup group, SoundID id)
        {
            var key = (group, id);
            if (sePools.TryGetValue(key, out var pool))
                return pool;

            var creationTask = creatingPools.GetOrAdd(key, k =>
            {
                var tcs = new UniTaskCompletionSource<SoundPool>();
                CreatePoolAsync(k, tcs).Forget();
                return tcs.Task;
            });

            return await creationTask;
        }

        private async UniTask CreatePoolAsync((SoundGroup group, SoundID id) key, UniTaskCompletionSource<SoundPool> tcs)
        {
            try
            {
                var pool = new SoundPool(key.group, key.id, combinedToken);
                await pool.InitializeAsync(combinedToken);
                sePools[key] = pool;
                creatingPools.TryRemove(key, out _);
                tcs.TrySetResult(pool);
            }
            catch (Exception e)
            {
                creatingPools.TryRemove(key, out _);
                tcs.TrySetException(e);
            }
        }

        private void OnDestroy()
        {
            StopAllAndCancelAllTasks();
            foreach (var pool in sePools.Values) pool?.Dispose();
            foreach (var channel in bgmChannels) channel?.Dispose();
            sePools.Clear();
            creatingPools.Clear();
            manualCancelSource?.Cancel();
            manualCancelSource?.Dispose();
        }
    }

    // =============================================================
    // BGMチャンネル
    // =============================================================
    internal sealed class BGMChannel : IDisposable
    {
        public int ChannelID { get; }
        private AudioSource current;
        private AudioSource next;
        private readonly CancellationToken channelToken;

        public BGMChannel(int id, CancellationToken token)
        {
            ChannelID = id;
            channelToken = token;
        }

        public async UniTask Play(SoundGroup group, SoundID id, float fadeIn, float volume, CancellationToken ct)
        {
            var clip = SoundCore.Instance.GetSoundClip(group, id);
            if (!clip) return;

            var go = new GameObject($"BGM_Channel{ChannelID}");
            go.transform.SetParent(SoundObjectPool.Instance.transform);
            var source = go.AddComponent<AudioSource>();
            source.clip = clip;
            source.loop = true;
            source.playOnAwake = false;
            source.volume = 0f;

            if (current != null && fadeIn > 0f)
            {
                next = source;
                await CrossFadeAsync(fadeIn, volume, ct);
            }
            else
            {
                if (current) GameObject.Destroy(current.gameObject);
                current = source;
                current.volume = volume;
                current.Play();
            }
        }

        public async UniTask StopAsync(float fadeOut, Action onComplete, CancellationToken ct)
        {
            if (current == null)
            {
                onComplete?.Invoke();
                return;
            }

            await FadeOutAsync(current, fadeOut, ct);
            if (current) GameObject.Destroy(current.gameObject);
            current = null;
            onComplete?.Invoke();
        }

        public void StopImmediately()
        {
            if (current != null)
            {
                current.Stop();
                GameObject.Destroy(current.gameObject);
                current = null;
            }
            if (next != null)
            {
                next.Stop();
                GameObject.Destroy(next.gameObject);
                next = null;
            }
        }

        private async UniTask CrossFadeAsync(float duration, float targetVolume, CancellationToken ct)
        {
            if (next == null) return;

            next.Play();
            float timer = 0f;
            float startVol = current != null ? current.volume : 0f;

            while (timer < duration)
            {
                timer += Time.unscaledDeltaTime;
                float t = Mathf.Clamp01(timer / duration);
                if (current) current.volume = Mathf.Lerp(startVol, 0f, t);
                next.volume = Mathf.Lerp(0f, targetVolume, t);
                await UniTask.Yield(ct);
            }

            if (current) GameObject.Destroy(current.gameObject);
            current = next;
            next = null;
        }

        private async UniTask FadeOutAsync(AudioSource source, float duration, CancellationToken ct)
        {
            if (source == null) return;

            float startVol = source.volume;
            float timer = 0f;

            while (timer < duration)
            {
                timer += Time.unscaledDeltaTime;
                source.volume = Mathf.Lerp(startVol, 0f, timer / duration);
                await UniTask.Yield(ct);
            }

            source.volume = 0f;
            source.Stop();
        }

        public void Dispose()
        {
            StopImmediately();
        }
    }

    // =============================================================
    // SEプール
    // =============================================================
    internal sealed class SoundPool : IDisposable
    {
        private readonly SoundGroup group;
        private readonly SoundID id;
        private AudioClip clip;
        private readonly List<PooledAudioObject> pool = new();
        private readonly Queue<PooledAudioObject> freeQueue = new();
        private readonly HashSet<PooledAudioObject> activeSet = new();
        private readonly SemaphoreSlim expandSemaphore = new(1, 1);
        private int peakUsage = 0;
        private float lastShrinkTime = 0f;
        private readonly CancellationToken poolToken;

        private const float ShrinkInterval = 30f;
        private const float ShrinkThreshold = 0.6f;
        private const int MinCapacity = 32;

        public SoundPool(SoundGroup group, SoundID id, CancellationToken token)
        {
            this.group = group;
            this.id = id;
            this.poolToken = token;
        }

        public async UniTask InitializeAsync(CancellationToken ct = default)
        {
            clip = SoundCore.Instance.GetSoundClip(group, id);
            if (!clip) throw new Exception($"[SoundPool] Clip not found: {group}/{id}");
            await ExpandAsync(32, ct);
        }

        public async UniTask WaitForAvailableAsync(CancellationToken ct)
        {
            using var linkedCts = CancellationTokenSource.CreateLinkedTokenSource(ct, poolToken);
            while (true)
            {
                linkedCts.Token.ThrowIfCancellationRequested();

                while (freeQueue.Count > 0 && freeQueue.Peek().isDestroyed)
                    freeQueue.Dequeue();

                if (freeQueue.Count > 0) break;

                await expandSemaphore.WaitAsync(linkedCts.Token);
                try
                {
                    if (freeQueue.Count > 0) break;
                    await ExpandAsync(Mathf.Max(8, activeSet.Count + 8), linkedCts.Token);
                }
                finally
                {
                    expandSemaphore.Release();
                }
            }
        }

        public SoundHandle PlayImmediately(Vector3 position, float volume, float pitch, float forceDuration, float distance, Action<SoundHandle> onCompleted)
        {
            while (freeQueue.Count > 0 && freeQueue.Peek().isDestroyed)
                freeQueue.Dequeue();

            var obj = freeQueue.Dequeue();
            activeSet.Add(obj);
            obj.isActive = true;
            obj.isDestroyed = false;

            var go = obj.gameObject;
            var source = obj.source;
            go.transform.position = position;
            source.volume = volume;
            source.pitch = pitch;
            source.spatialBlend = distance > 0f ? 1f : 0f;
            source.minDistance = 0.5f;
            source.maxDistance = distance;
            go.SetActive(true);
            source.Play();

            float lifetime = forceDuration > 0f ? forceDuration : clip.length / Mathf.Abs(pitch);
            var handle = new SoundHandle(this, obj, lifetime);
            onCompleted?.Invoke(handle);
            return handle;
        }

        internal void TryReturn(PooledAudioObject obj, int generation)
        {
            if (obj == null || obj.generation != generation || !activeSet.Remove(obj)) return;

            obj.source.Stop();
            obj.source.volume = 1f;
            obj.source.pitch = 1f;
            obj.gameObject.SetActive(false);
            obj.isActive = false;
            obj.gameObject.transform.SetParent(SoundObjectPool.Instance.transform);
            obj.generation++;
            freeQueue.Enqueue(obj);
            TryScheduleShrink();
        }

        public void StopAllImmediately()
        {
            foreach (var obj in activeSet)
            {
                if (obj.source != null && obj.source.isPlaying)
                {
                    obj.source.Stop();
                    obj.gameObject.SetActive(false);
                }
                obj.isActive = false;
            }

            while (activeSet.Count > 0)
            {
                var obj = activeSet.FirstOrDefault();
                if (obj != null)
                {
                    activeSet.Remove(obj);
                    if (!obj.isDestroyed) freeQueue.Enqueue(obj);
                }
            }
        }

        private async UniTask ExpandAsync(int count, CancellationToken ct)
        {
            var template = new GameObject($"PooledSE_Temp:{clip.name}");
            template.transform.SetParent(SoundObjectPool.Instance.transform);
            var op = UnityEngine.Object.InstantiateAsync(template, count);
            await op.WithCancellation(ct);
            GameObject.Destroy(template);

            foreach (var go in op.Result)
            {
                go.transform.SetParent(SoundObjectPool.Instance.transform);
                go.SetActive(false);
                var source = go.AddComponent<AudioSource>();
                source.playOnAwake = false;
                source.clip = clip;
                var pooled = new PooledAudioObject
                {
                    gameObject = go,
                    source = source,
                    generation = 0,
                    isActive = false,
                    isDestroyed = false
                };
                pool.Add(pooled);
                freeQueue.Enqueue(pooled);
            }
        }

        private void TryScheduleShrink()
        {
            if (Time.unscaledTime - lastShrinkTime < ShrinkInterval) return;
            lastShrinkTime = Time.unscaledTime;

            if (activeSet.Count <= (int)(peakUsage * ShrinkThreshold) && pool.Count > MinCapacity)
                ShrinkAsync().Forget();
        }

        private async UniTask ShrinkAsync()
        {
            await expandSemaphore.WaitAsync();
            try
            {
                int target = Mathf.Max(MinCapacity, activeSet.Count + 16);
                if (pool.Count <= target) return;

                int toDestroy = pool.Count - target;
                int destroyed = 0;

                for (int i = pool.Count - 1; i >= 0 && destroyed < toDestroy; i--)
                {
                    var obj = pool[i];
                    if (!obj.isActive && !obj.isDestroyed)
                    {
                        obj.isDestroyed = true;
                        if (obj.gameObject) GameObject.Destroy(obj.gameObject);
                        pool.RemoveAt(i);
                        destroyed++;
                    }
                }
            }
            finally
            {
                expandSemaphore.Release();
            }
        }

        public void Dispose()
        {
            StopAllImmediately();
            foreach (var obj in pool)
                if (obj.gameObject) GameObject.Destroy(obj.gameObject);
            pool.Clear();
            freeQueue.Clear();
            activeSet.Clear();
        }
    }

    // =============================================================
    // SoundHandle（ゾンビ化防止）
    // =============================================================
    public readonly struct SoundHandle : IDisposable
    {
        private readonly SoundPool pool;
        private readonly PooledAudioObject pooledObject;
        private readonly int generation;

        internal SoundHandle(SoundPool pool, PooledAudioObject pooledObject, float lifetime)
        {
            this.pool = pool;
            this.pooledObject = pooledObject;
            this.generation = pooledObject.generation;
            var localGeneration = this.generation;
            if (lifetime > 0f)
            {
                UniTask.Delay(TimeSpan.FromSeconds(lifetime))
                    .ContinueWith(() => pool?.TryReturn(pooledObject, localGeneration))
                    .Forget();
            }
        }

        public void Stop() => pool?.TryReturn(pooledObject, generation);
        public void Dispose() => Stop();

        public bool IsValid => pooledObject != null && pooledObject.generation == generation;
        public bool IsPlaying => pooledObject?.source != null && pooledObject.source.isPlaying;
        public float Volume { get => pooledObject?.source?.volume ?? 0f; set { if (pooledObject?.source) pooledObject.source.volume = value; } }
        public float Pitch { get => pooledObject?.source?.pitch ?? 1f; set { if (pooledObject?.source) pooledObject.source.pitch = value; } }
    }

    // =============================================================
    // プールオブジェクト
    // =============================================================
    internal sealed class PooledAudioObject
    {
        public GameObject gameObject;
        public AudioSource source;
        public int generation = 0;
        public bool isActive = false;
        public bool isDestroyed = false;
    }
}
"""
        with open(os.path.join(SOUND_DATA,"SoundObjectPool.cs"),"w",encoding="utf-8") as f:
            f.write(code_str)


        
    # ENUM_DIR/Sound ディレクトリを作成
    if not os.path.exists(os.path.join(ENUM_DIR, "Sound")):
        os.makedirs(os.path.join(ENUM_DIR, "Sound"))
    
    # Sound.json を生成
    with open(os.path.join(ENUM_DIR, "Sound", "Sound.json"), 'w', encoding='utf-8') as f:
        sound_id_list = []
        for group, group_value in data['groups'].items():
            for sound in group_value['items']:
                sound_id = f"{group}_{sound['name']}"
                sound_id_list.append({
                    'description': sound['desc'],
                    'id': sound_id_map[sound_id],
                    'property': sound_id,
                    'value': sound_id_map[sound_id]
                })
        json.dump(sound_id_list, f, ensure_ascii=False, indent=4)

    generate_enum_csharp(os.path.join(ENUM_DIR, "Sound", "Sound.json"), "Sound", ENUM_DIR)

    # SoundCoreSubGroups.cs（SubGroup単位のLoad/Unload専用メソッド。毎回再生成される）
    generate_sound_core_subgroups(data)


def generate_sound_core_subgroups(data):
    """
    グループごとのSubGroup専用enum（Sound_{Group}ID）を引数に取る
    LoadSubGroup / UnloadSubGroup のオーバーロードを、partial classとして
    SoundCoreSubGroups.cs に生成する（毎回上書き）。
    """
    lines = []
    lines.append("// 自動生成ファイルです。手動編集しても generate 実行時に上書きされます。")
    lines.append("using System;")
    lines.append("using GameCore.Enums;")
    lines.append("")
    lines.append("namespace GameCore.Sound")
    lines.append("{")
    lines.append("    public partial class SoundCore")
    lines.append("    {")

    for group_name, group_value in data['groups'].items():
        subgroups = group_value.get('subgroups', [])
        if not subgroups:
            continue
        enum_name = f"Sound_{group_name}ID"
        lines.append(f"        public void LoadSubGroup({enum_name} subGroupId, AddressableSystem.GroupCategory category, Action onCompleted = null)")
        lines.append(f"            => LoadSubGroupInternal(SoundGroup.{group_name}, (int)subGroupId, category, onCompleted);")
        lines.append("")
        lines.append(f"        public void UnloadSubGroup({enum_name} subGroupId, Action onCompleted = null)")
        lines.append(f"            => UnloadSubGroupInternal(SoundGroup.{group_name}, (int)subGroupId, onCompleted);")
        lines.append("")

    lines.append("    }")
    lines.append("}")

    with open(os.path.join(SOUND_DATA, "SoundCoreSubGroups.cs"), 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))


def generate_sound_bin():
    """
    サウンドデータのバイナリファイルを生成
    """
    data = load_sound_data()
    with open(os.path.join(SOUND_DATA, 'sound_data.bytes'), 'wb') as f:
        groups = list(data['groups'].keys())
        group_count = len(groups)
        f.write(struct.pack('i', group_count))
        offsets = [0] * group_count
        offset_pos = f.tell()
        f.write(struct.pack('i' * group_count, *offsets))
        current_offset = f.tell()

        sound_id_map = {'None': 0}
        sound_id_counter = 1
        for group, group_value in data['groups'].items():
            for sound in group_value['items']:
                sound_id = f"{group}_{sound['name']}"
                if sound_id not in sound_id_map:
                    sound_id_map[sound_id] = sound_id_counter
                    sound_id_counter += 1

        for i, group in enumerate(groups):
            offsets[i] = current_offset
            group_value = data['groups'][group]
            sounds = group_value['items']
            subgroup_map = _subgroup_index_map(group_value.get('subgroups', []))
            f.write(struct.pack('i', len(sounds)))
            for sound in sounds:
                sound_id = sound_id_map.get(f"{group}_{sound['name']}", 0)
                f.write(struct.pack('i', sound_id))
                path_bytes = sound['path'].encode('utf-8') + b'\0'
                f.write(path_bytes)
                f.write(struct.pack('f', sound['volume']))
                type_byte = 0 if sound['type'] == 'SE' else 1
                f.write(struct.pack('B', type_byte))
                sub_group_id = subgroup_map.get(sound.get('subgroup'), 0)
                f.write(struct.pack('i', sub_group_id))
            current_offset = f.tell()
        f.seek(offset_pos)
        f.write(struct.pack('i' * group_count, *offsets))

# Texture data management
def get_texture_data():
    """
    テクスチャデータを取得
    """
    return load_texture_data()

def add_texture_group(group_name):
    """
    テクスチャグループを追加
    """
    data = load_texture_data()
    if group_name and group_name not in data['groups']:
        data['groups'][group_name] = {'items': [], 'subgroups': []}
        save_texture_data(data)

def delete_texture_group(group_name):
    """
    テクスチャグループを削除
    """
    data = load_texture_data()
    data['groups'].pop(group_name, None)
    save_texture_data(data)

def add_texture_subgroup(group_name, subgroup_name):
    """
    テクスチャグループの中にSubGroupを追加する
    """
    data = load_texture_data()
    add_subgroup_to_group(data, group_name, subgroup_name)
    save_texture_data(data)

def delete_texture_subgroup(group_name, subgroup_name):
    """
    テクスチャグループからSubGroupを削除する
    """
    data = load_texture_data()
    delete_subgroup_from_group(data, group_name, subgroup_name)
    save_texture_data(data)

def add_texture(group_name, name, desc, isSpriteRender, subgroup_name=None):
    """
    テクスチャをグループ（必要であればSubGroup）に追加
    """
    data = load_texture_data()
    if subgroup_name and subgroup_name not in data['groups'][group_name]['subgroups']:
        raise Exception(f"SubGroup '{subgroup_name}' が見つかりません。先にSubGroupを作成してください。")
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
    data['groups'][group_name]['items'].append({
        'name': name, 
        'desc': desc, 
        'path': addr_path,
        'isSpriteRender' : isSpriteRender,
        'absolute_path': os.path.abspath(file_path),
        'sprites': sprite_info,
        'subgroup': subgroup_name or None
    })
    save_texture_data(data)

def delete_texture(group_name, index):
    """
    テクスチャをグループから削除
    """
    data = load_texture_data()
    del data['groups'][group_name]['items'][index]
    save_texture_data(data)

def edit_texture(group_name, index, name=None, desc=None, isSpriteRender=None, subgroup_name=None):
    """
    既存のテクスチャエントリを編集する（ファイルの再選択は行わない）
    """
    data = load_texture_data()
    if group_name not in data['groups']:
        raise Exception(f"グループ '{group_name}' が見つかりません。")
    items = data['groups'][group_name]['items']
    if index < 0 or index >= len(items):
        raise Exception("対象のデータが見つかりません。")
    if subgroup_name and subgroup_name not in data['groups'][group_name]['subgroups']:
        raise Exception(f"SubGroup '{subgroup_name}' が見つかりません。先にSubGroupを作成してください。")

    entry = items[index]
    if name is not None:
        entry['name'] = name
    if desc is not None:
        entry['desc'] = desc
    if isSpriteRender is not None:
        entry['isSpriteRender'] = isSpriteRender
    entry['subgroup'] = subgroup_name or None
    save_texture_data(data)

def reload_texture_file(group_name, index):
    """
    既存エントリのファイル参照だけを再選択・再取得する（スプライト情報も取り直す）。
    エクスプローラーは、そのエントリで前回選択済みのパスのフォルダから開く。
    """
    data = load_texture_data()
    if group_name not in data['groups']:
        raise Exception(f"グループ '{group_name}' が見つかりません。")
    items = data['groups'][group_name]['items']
    if index < 0 or index >= len(items):
        raise Exception("対象のデータが見つかりません。")

    entry = items[index]
    prev_path = entry.get('absolute_path')
    initial_dir = os.path.dirname(prev_path) if prev_path and os.path.isdir(os.path.dirname(prev_path)) else get_unity_project_path()
    if not initial_dir:
        raise Exception("Unityプロジェクトのパスを取得できませんでした。")

    file_path = select_file(initial_dir, [("画像ファイル", "*.png *.jpg *.jpeg")])
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

    entry['path'] = addr_path
    entry['absolute_path'] = os.path.abspath(file_path)
    entry['sprites'] = sprite_info
    save_texture_data(data)
    return entry

def generate_texture_csharp():
    """
    テクスチャ関連のC#コードとJSONを生成
    - TextureEnums.cs を生成
    - assets_texture.json を更新
    - ENUM_DIR/Texture/TextureSpriteID.json を生成
    """
    data = load_texture_data()
    # TextureEnums.cs
    with open(os.path.join(TEXTURE_DATA, 'TextureEnums.cs'), 'w', encoding='utf-8') as f:
        f.write('namespace GameCore.Texture {\n')
        f.write('    public enum TextureGroup { None')
        for group in data['groups']:
            f.write(f', {group}')
        f.write(' ,Max\n  };\n')
        texture_id_counter = 1
        texture_id_map = {'None': 0}
        for group, group_value in data['groups'].items():
            for texture in group_value['items']:
                texture_id = f"{group}_{texture['name']}"
                if texture_id not in texture_id_map:
                    texture_id_map[texture_id] = texture_id_counter
                    texture_id_counter += 1
        
        # SpriteID の生成
        sprite_id_counter = 1
        sprite_id_map = {'None': 0}
        for group, group_value in data['groups'].items():
            for texture in group_value['items']:
                texture_id = f"{group}_{texture['name']}"
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
        
        # スプライトシート用の専用列挙型
        for group, group_value in data['groups'].items():
            for texture in group_value['items']:
                if len(texture.get('sprites', [])) > 1:
                    sprite_enum_name = f"{group}_{texture['name']}"
                    sprite_id_counter = 0
                    for sprite in texture.get('sprites', []):
                        sprite_id_counter += 1
        
        f.write('}\n')

    # SubGroup用enum（Texture_{Group}ID）を各グループごとに生成／同期
    subgroup_enum_names = sync_subgroup_enum_files(
    ENUM_DIR, "Texture", data['groups'],
    data_dir=TEXTURE_DATA, namespace="GameCore.Texture", class_name="TextureCore",
    group_enum_name="TextureGroup", id_enum_name="TextureID"
    )
    register_enum_names(ENUM_DIR, subgroup_enum_names)

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
using GameCore.Enums;

namespace GameCore.Texture
{
    public partial class TextureCore : BaseSingleton<TextureCore>
    {
        private TextureDatabase database;
        private Dictionary<TextureGroup, Dictionary<TextureID, TextureAddressableData>> loadedAssets =
            new Dictionary<TextureGroup, Dictionary<TextureID, TextureAddressableData>>();
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
            database = await TextureBinaryReader.LoadTextureDatabaseFromBinaryAsync(SupportFiles.ALL_TEXTURE_BIN,SupportFiles.ADDRESSABLE_CHECK);
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
            if (loadedAssets.ContainsKey(group)) return;
            var textures = database.GroupedTexturesList.FirstOrDefault(data => data.Group == group);
            if (textures == null) return;

            loadedAssets[group] = new Dictionary<TextureID, TextureAddressableData>();
            var tasks = new List<UniTask>();

            foreach (var texture in textures.Textures)
            {
                if (texture.IsSpriteSheet)
                {
                    // スプライトシート自体のロード
                    var addressableSpriteSheet = new TextureAddressableData(groupCategory, AssetCategory.Sprite, texture.AddressablePath,true);
                    tasks.Add(addressableSpriteSheet.LoadAsync(texture.AddressablePath,texture.Sprites.Count, obj =>
                    {
                        if (addressableSpriteSheet.IsLoadedAndSetup)
                        {
                            loadedAssets[group][texture.TextureID] = addressableSpriteSheet;
                        }
                    }, ex =>
                    {
                        Debug.LogError($"Failed to load sprite sheet for {texture.TextureID} at {texture.AddressablePath}: {ex.ToString()}");
                    }).AttachExternalCancellation(destroyToken));




                }
                else
                {
                    // テクスチャのロード
                    var addressableTexture = new TextureAddressableData(groupCategory, AssetCategory.Texture, texture.AddressablePath, false);
                    tasks.Add(addressableTexture.LoadAsync(texture.AddressablePath, 0,obj =>
                    {
                        if (addressableTexture.IsLoadedAndSetup)
                        {
                            loadedAssets[group][texture.TextureID] = addressableTexture;
                        }
                    }, ex =>
                    {
                        Debug.LogError($"Failed to load texture for {texture.TextureID} at {texture.AddressablePath}: {ex.ToString()}");
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
            if (!loadedAssets.TryGetValue(group, out var assets)) return;

            foreach (var addressable in assets.Values)
            {
                addressable.Release();
            }
            loadedAssets.Remove(group);
            AddressableDataCore.Instance.ReleaseCategory(groupCategory, AssetCategory.Texture);
            AddressableDataCore.Instance.ReleaseCategory(groupCategory, AssetCategory.Sprite);
            action?.Invoke();
            await UniTask.CompletedTask.AttachExternalCancellation(destroyToken);
        }

        // =============================================================
        // 個別ID単位のロード／アンロード
        // 既存の loadedAssets（グループロードと同じキャッシュ）をそのまま使う。
        // =============================================================
        internal void LoadSingle(TextureGroup group, TextureID id, GroupCategory groupCategory, Action action = null)
            => LoadSingleAsync(group, id, groupCategory, action).Forget();

        internal async UniTask LoadSingleAsync(TextureGroup group, TextureID id, GroupCategory groupCategory, Action action = null)
        {
            while (database == null)
                await UniTask.Yield(cancellationToken: destroyToken);

            if (loadedAssets.TryGetValue(group, out var existing) && existing.ContainsKey(id))
            {
                action?.Invoke();
                return;
            }

            var groupData = database.GroupedTexturesList.FirstOrDefault(d => d.Group == group);
            var texture = groupData?.Textures.FirstOrDefault(t => t.TextureID == id);
            if (texture == null) { action?.Invoke(); return; }

            if (!loadedAssets.ContainsKey(group))
                loadedAssets[group] = new Dictionary<TextureID, TextureAddressableData>();

            var addressable = new TextureAddressableData(groupCategory, texture.IsSpriteSheet ? AssetCategory.Sprite : AssetCategory.Texture, texture.AddressablePath, texture.IsSpriteSheet);
            await addressable.LoadAsync(texture.AddressablePath, texture.IsSpriteSheet ? texture.Sprites.Count : 0, obj =>
            {
                if (addressable.IsLoadedAndSetup)
                {
                    loadedAssets[group][id] = addressable;
                }
            }, ex =>
            {
                Debug.LogError($"Failed to load single texture {id} at {texture.AddressablePath}: {ex.Message}");
            });

            action?.Invoke();
        }

        public void UnloadSingle(TextureGroup group, TextureID id, Action action = null)
            => UnloadSingleAsync(group, id, action).Forget();

        public async UniTask UnloadSingleAsync(TextureGroup group, TextureID id, Action action = null)
        {
            if (loadedAssets.TryGetValue(group, out var dict) && dict.TryGetValue(id, out var addressable))
            {
                addressable.ReleaseAndUntrack();
                dict.Remove(id);
            }
            action?.Invoke();
            await UniTask.CompletedTask.AttachExternalCancellation(destroyToken);
        }

        // =============================================================
        // SubGroup単位のロード／アンロード（内部実装）
        // 公開APIは TextureCoreSubGroups.cs 側で、グループごとの
        // 専用enum（例: Texture_EnemyID）を受け取るオーバーロードとして生成される。
        // どのテクスチャがどのSubGroupに属するかは TextureData.SubGroupId から都度判定する。
        // 既存の loadedAssets キャッシュをそのまま使い、専用の管理は持たない。
        // =============================================================
        internal void LoadSubGroupInternal(TextureGroup group, int subGroupId, GroupCategory groupCategory, Action action = null)
            => LoadSubGroupInternalAsync(group, subGroupId, groupCategory, action).Forget();

        internal async UniTask LoadSubGroupInternalAsync(TextureGroup group, int subGroupId, GroupCategory groupCategory, Action action = null)
        {
            while (database == null)
                await UniTask.Yield(cancellationToken: destroyToken);

            var groupData = database.GroupedTexturesList.FirstOrDefault(d => d.Group == group);
            if (groupData == null) { action?.Invoke(); return; }

            if (!loadedAssets.ContainsKey(group))
                loadedAssets[group] = new Dictionary<TextureID, TextureAddressableData>();

            var tasks = new List<UniTask>();
            foreach (var texture in groupData.Textures)
            {
                if (texture.SubGroupId != subGroupId) continue;
                if (loadedAssets[group].ContainsKey(texture.TextureID)) continue;

                var addressable = new TextureAddressableData(groupCategory, texture.IsSpriteSheet ? AssetCategory.Sprite : AssetCategory.Texture, texture.AddressablePath, texture.IsSpriteSheet);
                tasks.Add(addressable.LoadAsync(texture.AddressablePath, texture.IsSpriteSheet ? texture.Sprites.Count : 0, obj =>
                {
                    if (addressable.IsLoadedAndSetup)
                        loadedAssets[group][texture.TextureID] = addressable;
                }, ex =>
                {
                    Debug.LogError($"Failed to load texture for {texture.TextureID} at {texture.AddressablePath}: {ex.Message}");
                }));
            }

            await UniTask.WhenAll(tasks);
            action?.Invoke();
        }

        internal void UnloadSubGroupInternal(TextureGroup group, int subGroupId, Action action = null)
            => UnloadSubGroupInternalAsync(group, subGroupId, action).Forget();

        internal async UniTask UnloadSubGroupInternalAsync(TextureGroup group, int subGroupId, Action action = null)
        {
            if (loadedAssets.TryGetValue(group, out var dict) && database != null)
            {
                var groupData = database.GroupedTexturesList.FirstOrDefault(d => d.Group == group);
                if (groupData != null)
                {
                    foreach (var texture in groupData.Textures)
                    {
                        if (texture.SubGroupId != subGroupId) continue;
                        if (dict.TryGetValue(texture.TextureID, out var addressable))
                        {
                            addressable.ReleaseAndUntrack();
                            dict.Remove(texture.TextureID);
                        }
                    }
                }
            }

            action?.Invoke();
            await UniTask.CompletedTask.AttachExternalCancellation(destroyToken);
        }

        public Texture2D GetTexture(TextureGroup group, TextureID id)
        {
            if (loadedAssets.TryGetValue(group, out var groupAssets) && groupAssets.TryGetValue(id, out var addressable))
            {
                var result = addressable.GetAddressableObjectResult();
                if (result is Texture2D texture)
                {
                    return texture;
                }
                Debug.LogWarning($"Asset with ID {id} in group {group} is not a Texture2D.");
            }
            return null;
        }

        public Sprite GetSprite(TextureGroup group, TextureID id)
        {
            if (loadedAssets.TryGetValue(group, out var groupAssets) && groupAssets.TryGetValue(id, out var addressable))
            {
                var result = addressable.GetAddressableObjectResult();
                if (result is Sprite sprite)
                {
                    return sprite;
                }
                if (result is IList<Sprite> sprites && sprites.Count > 0)
                {
                    return sprites[0];
                }
                Debug.LogWarning($"Asset with ID {id} in group {group} is not a Sprite or Sprite array.");
            }
            return null;
        }

        public Sprite GetSprite<TEnum>(TextureGroup group, TextureID textureId, TEnum spriteIndex, int fallbackIndex = -1) where TEnum : Enum
        {
            if (loadedAssets.TryGetValue(group, out var groupAssets) &&
                groupAssets.TryGetValue(textureId, out var addressable))
            {
                // TEnum を数値（インデックス）として変換
                int index = (int)spriteIndex - 1;

                // fallbackIndex が指定されている場合はそちらを優先
                int targetIndex = fallbackIndex >= 0 ? fallbackIndex : index;

                var result = addressable.GetAddressableArrayResult();
                if (result is Sprite[] sprite && targetIndex == 0)
                {
                    return sprite[0]; // 単一スプライトの場合
                }
                if (result is IList<Sprite> sprites && sprites.Count > 0)
                {
                    if (targetIndex >= 0 && targetIndex < sprites.Count)
                    {
                        return sprites[targetIndex];
                    }
                    return sprites[0];
                }
                Debug.LogWarning($"Asset with ID {textureId} in group {group} is not a Sprite or Sprite array.");
            }
            Debug.LogWarning($"No asset found for TextureID {textureId} in group {group}.");
            return null;
        }

        private void OnDestroy()
        {
            foreach (var group in loadedAssets.Values)
            {
                foreach (var asset in group.Values)
                {
                    asset.Release();
                }
            }
            loadedAssets.Clear();
        }
    }
}

"""
        with open(os.path.join(TEXTURE_DATA, "TextureCore.cs"), 'w', encoding='utf-8') as f:
            f.write(code_str)
            
    if not os.path.exists(os.path.join(ENUM_DIR, "TextureAddressableData.cs")):
        code_str = """


using System;
using System.Collections.Generic;
using UnityEngine;
using AddressableSystem;
using Cysharp.Threading.Tasks;

namespace GameCore.Texture
{
    public class TextureAddressableData
    {
        private readonly AddressableData<Sprite> spriteData;
        private readonly AddressableData<Texture2D> textureData;
        private readonly bool isSprite;

        public TextureAddressableData(GroupCategory groupCategory, AssetCategory assetCategory, string path,bool isSprite)
        {
            this.isSprite = isSprite;
            if (isSprite)
            {
                spriteData = new AddressableData<Sprite>(groupCategory, assetCategory, path);
                textureData = null;
            }
            else
            {
                textureData = new AddressableData<Texture2D>(groupCategory, assetCategory, path);
                spriteData = null;
            }
        }

        public bool IsLoadedAndSetup => isSprite ? spriteData.IsLoadedAndSetup : textureData.IsLoadedAndSetup;

        public async UniTask LoadAsync(string path, int spriteCount, Action<object> onSuccess, Action<Exception> onError)
        {
            if (isSprite)
            {
                if (spriteCount > 1)
                {
                    await spriteData.LoadArrayAsync(onSuccess, onError);
                }
                else
                {
                    await spriteData.LoadAsync(onSuccess, onError);
                }
            }
            else
            {
                await textureData.LoadAsync(onSuccess, onError);
            }
        }

        public void Release()
        {
            if (isSprite)
            {
                spriteData?.Release();
            }
            else
            {
                textureData?.Release();
            }
        }

        public object GetAddressableObjectResult()
        {
            return isSprite ? spriteData.GetAddressableObjectResult() : textureData.GetAddressableObjectResult();
        }

        public Sprite[] GetAddressableArrayResult()
        {
            if (isSprite)
            {
                return spriteData.GetAddressableObjectArrayResult();
            }
            return null;
        }
    }
}
        
        
        """
        
        with open(os.path.join(ENUM_DIR, "TextureAddressableData.cs"), 'w', encoding='utf-8') as f:
            f.write(code_str)

    # TextureDatabase.cs
    if not os.path.exists(os.path.join(TEXTURE_DATA, 'TextureDatabase.cs')):
        code_str = """
using System.Collections.Generic;
using GameCore.Enums;
namespace GameCore.Texture
{
    public class TextureDatabase
    {
        [System.Serializable]
        public class SpriteData
        {
            private readonly string idName;
            private readonly string addressablePath;
            private readonly TextureID textureID;
            public SpriteData(TextureID textureID, string idName, string addressablePath)
            {
                this.idName = idName;
                this.addressablePath = addressablePath;
                this.textureID = textureID;
            }
            public string IdName => idName;
            public string AddressablePath => addressablePath;
            public TextureID TextureID => textureID;
        }

        [System.Serializable]
        public class TextureData
        {
            private readonly string idName;
            private readonly string addressablePath;
            private readonly TextureID textureID;
            private readonly List<SpriteData> sprites;
            private readonly bool isSpriteSheet;
            private readonly int subGroupId;
            public TextureData(TextureID textureID, string idName, string addressablePath, List<SpriteData> sprites, bool isSpriteSheet, int subGroupId = 0)
            {
                this.idName = idName;
                this.addressablePath = addressablePath;
                this.textureID = textureID;
                this.sprites = sprites ?? new List<SpriteData>();
                this.isSpriteSheet = isSpriteSheet;
                this.subGroupId = subGroupId;
            }
            public string IdName => idName;
            public string AddressablePath => addressablePath;
            public TextureID TextureID => textureID;
            public List<SpriteData> Sprites => sprites;
            public bool IsSpriteSheet => isSpriteSheet;
            // SubGroup ID（0 = SubGroupなし）。専用enum(例:Texture_EnemyID)にキャストして使う
            public int SubGroupId => subGroupId;
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
            
    if not os.path.exists(os.path.join(TEXTURE_DATA, 'TextureBinaryReader.cs')):
        code_str = """
using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;
using GameCore.Enums;
using UnityEngine.AddressableAssets;      
using UnityEngine.ResourceManagement.AsyncOperations;
using Cysharp.Threading.Tasks;

namespace GameCore.Texture
{
    public class TextureBinaryReader
    {
        public static TextureDatabase LoadTextureDatabaseFromBinary(string filePath, bool addressable = false)
        {
            if (!addressable)
            {
                if (!File.Exists(filePath))
                {
                    Debug.LogError($"Binary file not found: {filePath}");
                    return null;
                }

                using (BinaryReader reader = new BinaryReader(File.Open(filePath, FileMode.Open)))
                {
                    return ReadDatabase(reader);
                }
            }
            else
            {
                // ====================== Addressableの場合 ======================
                AsyncOperationHandle<TextAsset> handle = Addressables.LoadAssetAsync<TextAsset>(SupportFiles.ALL_TEXTURE_BIN_FILE);



                handle.WaitForCompletion();


                if (handle.Status != AsyncOperationStatus.Succeeded || handle.Result == null)
                {
                    Debug.LogError($"Failed to load Addressable binary: {SupportFiles.ALL_TEXTURE_BIN_FILE}");
                    if (handle.IsValid()) Addressables.Release(handle);
                    return null;
                }

                TextAsset textAsset = handle.Result;

                using (MemoryStream ms = new MemoryStream(textAsset.bytes))
                using (BinaryReader reader = new BinaryReader(ms))
                {
                    TextureDatabase database = ReadDatabase(reader);
                    Addressables.Release(handle);   // 必ず解放
                    return database;
                }
            }
        }

        public static async UniTask<TextureDatabase> LoadTextureDatabaseFromBinaryAsync(string filePath, bool addressable = false)
        {
            if (!addressable)
            {
                if (!File.Exists(filePath))
                {
                    Debug.LogError($"Binary file not found: {filePath}");
                    return null;
                }

                using (BinaryReader reader = new BinaryReader(File.Open(filePath, FileMode.Open)))
                {
                    return ReadDatabase(reader);
                }
            }
            else
            {
                // ====================== Addressableの場合 ======================
                AsyncOperationHandle<TextAsset> handle = Addressables.LoadAssetAsync<TextAsset>(SupportFiles.ALL_TEXTURE_BIN_FILE);



                await handle.ToUniTask();


                if (handle.Status != AsyncOperationStatus.Succeeded || handle.Result == null)
                {
                    Debug.LogError($"Failed to load Addressable binary: {SupportFiles.ALL_TEXTURE_BIN_FILE}");
                    if (handle.IsValid()) Addressables.Release(handle);
                    return null;
                }

                TextAsset textAsset = handle.Result;


                byte[] rawBytes = textAsset.bytes;

                using (MemoryStream ms = new MemoryStream(rawBytes))
                using (BinaryReader reader = new BinaryReader(ms))
                {
                    TextureDatabase database = ReadDatabase(reader);
                    Addressables.Release(handle);   // 必ず解放
                    return database;
                }
            }
        }

        // 共通読み込みロジック（コード重複を避けるため抽出）
        private static TextureDatabase ReadDatabase(BinaryReader reader)
        {
            TextureDatabase database = new TextureDatabase();

            int groupCount = reader.ReadInt32();
            int[] offsets = new int[groupCount];

            for (int i = 0; i < groupCount; i++)
            {
                offsets[i] = reader.ReadInt32();
            }

            string[] groupNames = Enum.GetNames(typeof(TextureGroup));
            if (groupCount > groupNames.Length - 1)
            {
                Debug.LogError("Binary contains more groups than defined in TextureGroup enum.");
                return null;
            }

            for (int i = 0; i < groupCount; i++)
            {
                reader.BaseStream.Seek(offsets[i], SeekOrigin.Begin);
                int textureCount = reader.ReadInt32();
                List<TextureDatabase.TextureData> textures = new List<TextureDatabase.TextureData>();

                for (int j = 0; j < textureCount; j++)
                {
                    int textureId = reader.ReadInt32();
                    string textureIdName = ReadNullTerminatedString(reader);
                    string addressablePath = ReadNullTerminatedString(reader);
                    bool isSpriteSheet = reader.ReadBoolean();
                    int spriteCount = reader.ReadInt32();
                    List<TextureDatabase.SpriteData> sprites = new List<TextureDatabase.SpriteData>();

                    for (int k = 0; k < spriteCount; k++)
                    {
                        int spriteTextureId = reader.ReadInt32();
                        string spriteIdName = ReadNullTerminatedString(reader);
                        string spriteAddressablePath = ReadNullTerminatedString(reader);

                        sprites.Add(new TextureDatabase.SpriteData(
                            textureID: (TextureID)spriteTextureId,
                            idName: spriteIdName,
                            addressablePath: spriteAddressablePath
                        ));
                    }

                    int subGroupId = reader.ReadInt32();

                    textures.Add(new TextureDatabase.TextureData(
                        textureID: (TextureID)textureId,
                        idName: textureIdName,
                        addressablePath: addressablePath,
                        sprites: sprites,
                        isSpriteSheet: isSpriteSheet,
                        subGroupId: subGroupId
                    ));
                }

                database.GroupedTexturesList.Add(new TextureDatabase.GroupedTextures(
                    group: (TextureGroup)(i + 1),
                    textures: textures
                ));
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
        """
        with open(os.path.join(TEXTURE_DATA, 'TextureBinaryReader.cs'), "w", encoding='utf-8') as f:
            f.write(code_str)
            

    # ENUM_DIR/Texture ディレクトリを作成
    if not os.path.exists(os.path.join(ENUM_DIR, "Texture")):
        os.makedirs(os.path.join(ENUM_DIR, "Texture"))
    
    # TextureSprite.json を生成（TextureとSpriteを統合）
    with open(os.path.join(ENUM_DIR, "Texture", "Texture.json"), 'w', encoding='utf-8') as f:
            texture_id_list = []
            for group, group_value in data['groups'].items():
                for texture in group_value['items']:
                    texture_id = f"{group}_{texture['name']}"
                    texture_id_list.append({
                        'description': texture['desc'],
                        'id': texture_id_map[texture_id],
                        'property': texture_id,
                        'value': texture_id_map[texture_id]
                    })
            json.dump(texture_id_list, f, ensure_ascii=False, indent=4)
    generate_enum_csharp(os.path.join(ENUM_DIR, "Texture", "Texture.json"), "Texture", ENUM_DIR)
            
    # TextureSprite.json を生成（Spriteのエントリ、複数スプライトの場合）
    added_names = []
    for group, group_value in data['groups'].items():
        for texture in group_value['items']:
            if len(texture.get('sprites', [])) > 1:
                name = f"{group}_{texture['name']}"
                if not os.path.exists(os.path.join(ENUM_DIR, f"{name}")):
                    os.makedirs(os.path.join(ENUM_DIR, f"{name}"))
                with open(os.path.join(ENUM_DIR, f"{name}", f"{name}.json"), 'w', encoding='utf-8') as f:
                    texture_sprite_id_list = []
                    count = 0
                    for sprite in texture.get('sprites', []):
                        sprite_id = f"{texture['name']}_{sprite}"
                        texture_sprite_id_list.append({
                            'description': f"{texture['desc']}(Sprite:{sprite})",
                            'id': count,
                            'property': sprite_id,
                            'isSpriteRender':True,
                            'value': count
                        })
                        count += 1
                    json.dump(texture_sprite_id_list, f, ensure_ascii=False, indent=4)
                if name not in added_names:
                    added_names.append(name)
                generate_enum_csharp(os.path.join(ENUM_DIR, f"{name}", f"{name}.json"), name, ENUM_DIR)

    # enum_list.json に追加した名前を一括で追加
    enum_list_path = os.path.join(ENUM_DIR, 'enum_list.json')
    if os.path.exists(enum_list_path) and added_names:
        with open(enum_list_path, 'r+', encoding='utf-8') as f:
            enum_list = json.load(f)
            existing_names = [e['name'] for e in enum_list]
            max_id = max([e['id'] for e in enum_list if 'id' in e], default=0)
            for name in added_names:
                if name not in existing_names:
                    max_id += 1
                    enum_list.append({'id': max_id, 'name': name, 'view': False})
            f.seek(0)
            json.dump(enum_list, f, ensure_ascii=False, indent=4)
            f.truncate()

    # TextureCoreSubGroups.cs（SubGroup単位のLoad/Unload専用メソッド。毎回再生成される）
    generate_texture_core_subgroups(data)


def generate_texture_core_subgroups(data):
    """
    グループごとのSubGroup専用enum（Texture_{Group}ID）を引数に取る
    LoadSubGroup / UnloadSubGroup のオーバーロードを、partial classとして
    TextureCoreSubGroups.cs に生成する（毎回上書き）。
    """
    lines = []
    lines.append("// 自動生成ファイルです。手動編集しても generate 実行時に上書きされます。")
    lines.append("using System;")
    lines.append("using GameCore.Enums;")
    lines.append("")
    lines.append("namespace GameCore.Texture")
    lines.append("{")
    lines.append("    public partial class TextureCore")
    lines.append("    {")

    for group_name, group_value in data['groups'].items():
        subgroups = group_value.get('subgroups', [])
        if not subgroups:
            continue
        enum_name = f"Texture_{group_name}ID"
        lines.append(f"        public void LoadSubGroup({enum_name} subGroupId, AddressableSystem.GroupCategory groupCategory, Action onCompleted = null)")
        lines.append(f"            => LoadSubGroupInternal(TextureGroup.{group_name}, (int)subGroupId, groupCategory, onCompleted);")
        lines.append("")
        lines.append(f"        public void UnloadSubGroup({enum_name} subGroupId, Action onCompleted = null)")
        lines.append(f"            => UnloadSubGroupInternal(TextureGroup.{group_name}, (int)subGroupId, onCompleted);")
        lines.append("")

    lines.append("    }")
    lines.append("}")

    with open(os.path.join(TEXTURE_DATA, "TextureCoreSubGroups.cs"), 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))


def generate_texture_bin():
    """
    テクスチャデータのバイナリファイルを生成
    """
    data = load_texture_data()
    with open(os.path.join(TEXTURE_DATA, 'texture_data.bytes'), 'wb') as f:
        groups = list(data['groups'].keys())
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
        for group, group_value in data['groups'].items():
            for texture in group_value['items']:
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
            group_value = data['groups'][group]
            textures = group_value['items']
            subgroup_map = _subgroup_index_map(group_value.get('subgroups', []))
            f.write(struct.pack('i', len(textures)))
            for texture in textures:
                texture_id = texture_id_map.get(f"{group}_{texture['name']}", 0)
                f.write(struct.pack('i', texture_id))
                id_name = texture['name'].encode('utf-8') + b'\0'
                f.write(id_name)
                path_bytes = texture['path'].encode('utf-8') + b'\0'
                f.write(path_bytes)
                sprites = texture.get('sprites', [])
                isSpriteRender = texture.get('isSpriteRender', False)
                f.write(struct.pack('B', 1 if isSpriteRender else 0))
                sprite_count = len(sprites)
                f.write(struct.pack('i', sprite_count))
                for sprite in sprites:
                    sprite_id = sprite_id_map.get(f"{group}_{texture['name']}_{sprite}", sprite_id_map.get(f"{group}_{texture['name']}", 0))
                    f.write(struct.pack('i', sprite_id))
                    sprite_name = sprite.encode('utf-8') + b'\0'
                    f.write(sprite_name)
                    sprite_path = f"{texture['path']}#{sprite}".encode('utf-8') + b'\0'
                    f.write(sprite_path)
                sub_group_id = subgroup_map.get(texture.get('subgroup'), 0)
                f.write(struct.pack('i', sub_group_id))
            current_offset = f.tell()
        f.seek(offset_pos)
        f.write(struct.pack('i' * group_count, *offsets))

# GameObject data management
def get_gameobject_data():
    """
    ゲームオブジェクトデータを取得
    """
    return load_gameobject_data()

def add_gameobject_group(group_name):
    """
    ゲームオブジェクトグループを追加
    """
    data = load_gameobject_data()
    if group_name and group_name not in data['groups']:
        data['groups'][group_name] = {'items': [], 'subgroups': []}
        save_gameobject_data(data)

def delete_gameobject_group(group_name):
    """
    ゲームオブジェクトグループを削除
    """
    data = load_gameobject_data()
    data['groups'].pop(group_name, None)
    save_gameobject_data(data)

def add_gameobject_subgroup(group_name, subgroup_name):
    """
    ゲームオブジェクトグループの中にSubGroupを追加する
    （登録順がそのままGameObject_{group}ID enumのID順になる）
    """
    data = load_gameobject_data()
    add_subgroup_to_group(data, group_name, subgroup_name)
    save_gameobject_data(data)

def delete_gameobject_subgroup(group_name, subgroup_name):
    """
    ゲームオブジェクトグループからSubGroupを削除する
    （所属していたアイテムはグループ直下に戻る）
    """
    data = load_gameobject_data()
    delete_subgroup_from_group(data, group_name, subgroup_name)
    save_gameobject_data(data)

def add_gameobject(group_name, name, desc, subgroup_name=None):
    """
    ゲームオブジェクトをグループ（必要であればSubGroup）に追加
    """
    data = load_gameobject_data()
    if subgroup_name and subgroup_name not in data['groups'][group_name]['subgroups']:
        raise Exception(f"SubGroup '{subgroup_name}' が見つかりません。先にSubGroupを作成してください。")
    project_path = get_unity_project_path()
    if not project_path:
        raise Exception("Unityプロジェクトのパスを取得できませんでした。")
    file_path = select_file(project_path, [("プレハブファイル", "*.prefab")])
    if not file_path:
        raise Exception("ファイルが選択されていません。")
    addr_path = get_addressable_path(file_path)
    if not addr_path:
        raise Exception("アドレス指定可能なパスを取得できませんでした。")
    data['groups'][group_name]['items'].append({
        'name': name, 
        'desc': desc, 
        'path': addr_path,
        'absolute_path': os.path.abspath(file_path),
        'subgroup': subgroup_name or None
    })
    save_gameobject_data(data)

def delete_gameobject(group_name, index):
    """
    ゲームオブジェクトをグループから削除
    """
    data = load_gameobject_data()
    del data['groups'][group_name]['items'][index]
    save_gameobject_data(data)

def edit_gameobject(group_name, index, name=None, desc=None, subgroup_name=None):
    """
    既存のゲームオブジェクトエントリを編集する（ファイルの再選択は行わない）
    """
    data = load_gameobject_data()
    if group_name not in data['groups']:
        raise Exception(f"グループ '{group_name}' が見つかりません。")
    items = data['groups'][group_name]['items']
    if index < 0 or index >= len(items):
        raise Exception("対象のデータが見つかりません。")
    if subgroup_name and subgroup_name not in data['groups'][group_name]['subgroups']:
        raise Exception(f"SubGroup '{subgroup_name}' が見つかりません。先にSubGroupを作成してください。")

    entry = items[index]
    if name is not None:
        entry['name'] = name
    if desc is not None:
        entry['desc'] = desc
    entry['subgroup'] = subgroup_name or None
    save_gameobject_data(data)

def reload_gameobject_file(group_name, index):
    """
    既存エントリのファイル参照だけを再選択・再取得する。
    エクスプローラーは、そのエントリで前回選択済みのパスのフォルダから開く。
    """
    data = load_gameobject_data()
    if group_name not in data['groups']:
        raise Exception(f"グループ '{group_name}' が見つかりません。")
    items = data['groups'][group_name]['items']
    if index < 0 or index >= len(items):
        raise Exception("対象のデータが見つかりません。")

    entry = items[index]
    prev_path = entry.get('absolute_path')
    initial_dir = os.path.dirname(prev_path) if prev_path and os.path.isdir(os.path.dirname(prev_path)) else get_unity_project_path()
    if not initial_dir:
        raise Exception("Unityプロジェクトのパスを取得できませんでした。")

    file_path = select_file(initial_dir, [("プレハブファイル", "*.prefab")])
    if not file_path:
        raise Exception("ファイルが選択されていません。")
    addr_path = get_addressable_path(file_path)
    if not addr_path:
        raise Exception("アドレス指定可能なパスを取得できませんでした。")

    entry['path'] = addr_path
    entry['absolute_path'] = os.path.abspath(file_path)
    save_gameobject_data(data)
    return entry

def generate_gameobject_csharp():
    """
    ゲームオブジェクト関連のC#コードとJSONを生成
    - GameObjectEnums.cs を生成
    - assets_gameobject.json を更新
    - ENUM_DIR/GameObject/GameObject.json を生成
    """
    data = load_gameobject_data()
    # GameObjectEnums.cs
    with open(os.path.join(GAMEOBJECT_DATA, 'GameObjectEnums.cs'), 'w', encoding='utf-8') as f:
        f.write('namespace GameCore.Gameobject {\n')
        f.write('    public enum GameObjectGroup { None')
        for group in data['groups']:
            f.write(f', {group}')
        if "Particle" not in data["groups"]:
            f.write(f', Particle')
        f.write(' ,Max\n  };\n')
        gameobject_id_counter = 1
        gameobject_id_map = {'None': 0}
        for group, group_value in data['groups'].items():
            for go in group_value['items']:
                go_id = f"{group}_{go['name']}"
                if go_id not in gameobject_id_map:
                    gameobject_id_map[go_id] = gameobject_id_counter
                    gameobject_id_counter += 1

        f.write('}\n')

    # SubGroup用enum（GameObject_{Group}ID）を各グループごとに生成／同期
    subgroup_enum_names = sync_subgroup_enum_files(
    ENUM_DIR, "GameObject", data['groups'],
    data_dir=GAMEOBJECT_DATA, namespace="GameCore.Gameobject", class_name="GameObjectCore",
    group_enum_name="GameObjectGroup", id_enum_name="GameObjectID"
    )
    register_enum_names(ENUM_DIR, subgroup_enum_names)

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
using GameCore.Enums;
namespace GameCore.Gameobject
{
    public partial class GameObjectCore : BaseSingleton<GameObjectCore>
    {
        private GameObjectDatabase database;
        private Dictionary<GameObjectGroup, Dictionary<GameObjectID, AddressableData<UnityEngine.GameObject>>> loadedGameObjects =
            new Dictionary<GameObjectGroup, Dictionary<GameObjectID, AddressableData<UnityEngine.GameObject>>>();
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
            string path = SupportFiles.ADDRESSABLE_CHECK ? SupportFiles.ALL_GAMEOBJECT_BIN_FILE : SupportFiles.ALL_GAMEOBJECT_BIN;
            database = await GameObjectBinaryReader.LoadGameObjectDatabaseFromBinaryAsync(path, SupportFiles.ADDRESSABLE_CHECK);
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

            loadedGameObjects[group] = new Dictionary<GameObjectID, AddressableData<UnityEngine.GameObject>>();
            var tasks = new List<UniTask>();

            foreach (var go in gameObjects.GameObjects)
            {
                var addressable = new AddressableData<UnityEngine.GameObject>(groupCategory, AssetCategory.Prefab, go.AddressablePath);
                tasks.Add(addressable.LoadAsync( obj =>
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
            AddressableDataCore.Instance.ReleaseCategory(groupCategory, AssetCategory.Prefab);
            action?.Invoke();
            await UniTask.CompletedTask.AttachExternalCancellation(destroyToken);
        }

        public void UnloadAll(Action action = null)
        {
            UnloadAllAsync(action).Forget();
        }

        public async UniTask UnloadAllAsync(Action action = null)
        {
            foreach(var group in loadedGameObjects.Values)
            {
                foreach(var data in group.Values)
                {
                    data.Release();
                }
                await UniTask.Yield(destroyToken);
                group.Clear();
            }
            loadedGameObjects.Clear();

            AddressableDataCore.Instance.ReleaseAssetsAll(AssetCategory.Prefab);
            await UniTask.Yield(destroyToken);
            action?.Invoke();
            await UniTask.CompletedTask.AttachExternalCancellation(destroyToken);

        }

        // =============================================================
        // 個別ID単位のロード／アンロード
        // 既存の loadedGameObjects（グループロードと同じキャッシュ）をそのまま使う。
        // 個別専用の管理は持たない。
        // =============================================================
        internal void LoadSingle(GameObjectGroup group, GameObjectID id, GroupCategory groupCategory, Action action = null)
            => LoadSingleAsync(group, id, groupCategory, action).Forget();

        internal async UniTask LoadSingleAsync(GameObjectGroup group, GameObjectID id, GroupCategory groupCategory, Action action = null)
        {
            while (database == null)
            {
                await UniTask.Yield(cancellationToken: destroyToken);
            }
            if (loadedGameObjects.TryGetValue(group, out var existing) && existing.ContainsKey(id))
            {
                action?.Invoke();
                return;
            }

            var groupData = database.GroupedGameObjectsList.FirstOrDefault(d => d.Group == group);
            var target = groupData?.GameObjects.FirstOrDefault(g => g.GameObjectID == id);
            if (target == null) { action?.Invoke(); return; }

            if (!loadedGameObjects.ContainsKey(group))
                loadedGameObjects[group] = new Dictionary<GameObjectID, AddressableData<UnityEngine.GameObject>>();

            var addressable = new AddressableData<UnityEngine.GameObject>(groupCategory, AssetCategory.Prefab, target.AddressablePath);
            await addressable.LoadAsync(obj =>
            {
                if (addressable.IsLoadedAndSetup)
                {
                    loadedGameObjects[group][id] = addressable;
                }
            }, ex =>
            {
                Debug.LogError($"Failed to load single gameobject {id} at {target.AddressablePath}: {ex.Message}");
            }).AttachExternalCancellation(destroyToken);

            action?.Invoke();
        }

        public void UnloadSingle(GameObjectGroup group, GameObjectID id, Action action = null)
            => UnloadSingleAsync(group, id, action).Forget();

        public async UniTask UnloadSingleAsync(GameObjectGroup group, GameObjectID id, Action action = null)
        {
            if (loadedGameObjects.TryGetValue(group, out var dict) && dict.TryGetValue(id, out var addressable))
            {
                addressable.ReleaseAndUntrack();
                dict.Remove(id);
            }
            action?.Invoke();
            await UniTask.CompletedTask.AttachExternalCancellation(destroyToken);
        }

        // =============================================================
        // SubGroup単位のロード／アンロード（内部実装）
        // 公開APIは {Category}CoreSubGroups.cs 側で、グループごとの
        // 専用enum（例: GameObject_EnemyID）を受け取るオーバーロードとして生成される。
        // どのアイテムがどのSubGroupに属するかは GameObjectData.SubGroupId
        // （バイナリ生成時に書き出し済み）から都度判定する。
        // 既存の loadedGameObjects キャッシュをそのまま使い、専用の管理は持たない。
        // =============================================================
        internal void LoadSubGroupInternal(GameObjectGroup group, int subGroupId, GroupCategory groupCategory, Action action = null)
            => LoadSubGroupInternalAsync(group, subGroupId, groupCategory, action).Forget();

        internal async UniTask LoadSubGroupInternalAsync(GameObjectGroup group, int subGroupId, GroupCategory groupCategory, Action action = null)
        {
            while (database == null)
            {
                await UniTask.Yield(cancellationToken: destroyToken);
            }
            var groupData = database.GroupedGameObjectsList.FirstOrDefault(d => d.Group == group);
            if (groupData == null) { action?.Invoke(); return; }

            if (!loadedGameObjects.ContainsKey(group))
                loadedGameObjects[group] = new Dictionary<GameObjectID, AddressableData<UnityEngine.GameObject>>();

            var tasks = new List<UniTask>();
            foreach (var go in groupData.GameObjects)
            {
                if (go.SubGroupId != subGroupId) continue;
                if (loadedGameObjects[group].ContainsKey(go.GameObjectID)) continue;

                var addressable = new AddressableData<UnityEngine.GameObject>(groupCategory, AssetCategory.Prefab, go.AddressablePath);
                tasks.Add(addressable.LoadAsync(obj =>
                {
                    if (addressable.IsLoadedAndSetup)
                        loadedGameObjects[group][go.GameObjectID] = addressable;
                }, ex =>
                {
                    Debug.LogError($"Failed to load gameobject for {go.GameObjectID} at {go.AddressablePath}: {ex.Message}");
                }).AttachExternalCancellation(destroyToken));
            }

            await UniTask.WhenAll(tasks);
            action?.Invoke();
        }

        internal void UnloadSubGroupInternal(GameObjectGroup group, int subGroupId, Action action = null)
            => UnloadSubGroupInternalAsync(group, subGroupId, action).Forget();

        internal async UniTask UnloadSubGroupInternalAsync(GameObjectGroup group, int subGroupId, Action action = null)
        {
            if (loadedGameObjects.TryGetValue(group, out var dict) && database != null)
            {
                var groupData = database.GroupedGameObjectsList.FirstOrDefault(d => d.Group == group);
                if (groupData != null)
                {
                    foreach (var go in groupData.GameObjects)
                    {
                        if (go.SubGroupId != subGroupId) continue;
                        if (dict.TryGetValue(go.GameObjectID, out var addressable))
                        {
                            addressable.ReleaseAndUntrack();
                            dict.Remove(go.GameObjectID);
                        }
                    }
                }
            }

            action?.Invoke();
            await UniTask.CompletedTask.AttachExternalCancellation(destroyToken);
        }

        public UnityEngine.GameObject GetGameObject(GameObjectGroup group, GameObjectID id)
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
using GameCore.Enums;
namespace GameCore.Gameobject
{
    public class GameObjectDatabase
    {
        [System.Serializable]
        public class GameObjectData
        {
            private readonly string idName;
            private readonly string addressablePath;
            private readonly GameObjectID gameObjectID;
            private readonly int subGroupId;
            public GameObjectData(GameObjectID gameObjectID, string idName, string addressablePath, int subGroupId = 0)
            {
                this.idName = idName;
                this.addressablePath = addressablePath;
                this.gameObjectID = gameObjectID;
                this.subGroupId = subGroupId;
            }
            public string IdName => idName;
            public string AddressablePath => addressablePath;
            public GameObjectID GameObjectID => gameObjectID;
            // SubGroup ID（0 = SubGroupなし）。専用enum(例:GameObject_EnemyID)にキャストして使う
            public int SubGroupId => subGroupId;
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
            
    if not os.path.exists(os.path.join(GAMEOBJECT_DATA, 'GameObjectBinaryReader.cs')):
        code_str = """
using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;
using GameCore.Enums;
using UnityEngine.AddressableAssets;         
using UnityEngine.ResourceManagement.AsyncOperations;
using Cysharp.Threading.Tasks;

namespace GameCore.Gameobject
{
    public class GameObjectBinaryReader
    {
        public static GameObjectDatabase LoadGameObjectDatabaseFromBinary(string filePath, bool addressable = false)
        {
            if (!addressable)
            {
                if (!File.Exists(filePath))
                {
                    Debug.LogError($"Binary file not found: {filePath}");
                    return null;
                }

                using (BinaryReader reader = new BinaryReader(File.Open(filePath, FileMode.Open)))
                {
                    return ReadDatabase(reader);
                }
            }
            else
            {
                // ====================== Addressableの場合 ======================
                AsyncOperationHandle<TextAsset> handle = Addressables.LoadAssetAsync<TextAsset>(filePath);

                handle.WaitForCompletion();


                if (handle.Status != AsyncOperationStatus.Succeeded || handle.Result == null)
                {
                    Debug.LogError($"Failed to load Addressable binary: {filePath}");
                    if (handle.IsValid()) Addressables.Release(handle);
                    return null;
                }

                TextAsset textAsset = handle.Result;

                using (MemoryStream ms = new MemoryStream(textAsset.bytes))
                using (BinaryReader reader = new BinaryReader(ms))
                {
                    GameObjectDatabase database = ReadDatabase(reader);
                    Addressables.Release(handle);
                    return database;
                }
            }
        }

        public static async UniTask<GameObjectDatabase> LoadGameObjectDatabaseFromBinaryAsync(string filePath, bool addressable = false)
        {
            if (!addressable)
            {
                if (!File.Exists(filePath))
                {
                    Debug.LogError($"Binary file not found: {filePath}");
                    return null;
                }

                using (BinaryReader reader = new BinaryReader(File.Open(filePath, FileMode.Open)))
                {
                    return ReadDatabase(reader);
                }
            }
            else
            {
                // ====================== Addressableの場合 ======================
                AsyncOperationHandle<TextAsset> handle = Addressables.LoadAssetAsync<TextAsset>(filePath);

                await handle.ToUniTask();


                if (handle.Status != AsyncOperationStatus.Succeeded || handle.Result == null)
                {
                    Debug.LogError($"Failed to load Addressable binary: {filePath}");
                    if (handle.IsValid()) Addressables.Release(handle);
                    return null;
                }

                TextAsset textAsset = handle.Result;

                byte[] rawBytes = textAsset.bytes;

                using (MemoryStream ms = new MemoryStream(rawBytes))
                using (BinaryReader reader = new BinaryReader(ms))
                {
                    GameObjectDatabase database = ReadDatabase(reader);
                    Addressables.Release(handle);
                    return database;
                }
            }
        }

        // 共通読み込みロジック
        private static GameObjectDatabase ReadDatabase(BinaryReader reader)
        {
            GameObjectDatabase database = new GameObjectDatabase();

            int groupCount = reader.ReadInt32();
            int[] offsets = new int[groupCount];

            for (int i = 0; i < groupCount; i++)
            {
                offsets[i] = reader.ReadInt32();
            }

            string[] groupNames = Enum.GetNames(typeof(GameObjectGroup));
            if (groupCount > groupNames.Length - 1)
            {
                Debug.LogError("Binary contains more groups than defined in GameObjectGroup enum.");
                return null;
            }

            for (int i = 0; i < groupCount; i++)
            {
                reader.BaseStream.Seek(offsets[i], SeekOrigin.Begin);
                int gameObjectCount = reader.ReadInt32();
                List<GameObjectDatabase.GameObjectData> gameObjects = new List<GameObjectDatabase.GameObjectData>();

                for (int j = 0; j < gameObjectCount; j++)
                {
                    int gameObjectId = reader.ReadInt32();
                    string idName = ReadNullTerminatedString(reader);
                    string addressablePath = ReadNullTerminatedString(reader);
                    int subGroupId = reader.ReadInt32();

                    gameObjects.Add(new GameObjectDatabase.GameObjectData(
                        gameObjectID: (GameObjectID)gameObjectId,
                        idName: idName,
                        addressablePath: addressablePath,
                        subGroupId: subGroupId
                    ));
                }

                database.GroupedGameObjectsList.Add(new GameObjectDatabase.GroupedGameObjects(
                    group: (GameObjectGroup)(i + 1),
                    gameObjects: gameObjects
                ));
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
        
        """

        with open(os.path.join(GAMEOBJECT_DATA, 'GameObjectBinaryReader.cs'), 'w', encoding='utf-8') as f:
            f.write(code_str)
            
    if not os.path.exists(os.path.join(GAMEOBJECT_DATA,"ParticleObjectPool.cs")):
        code_str = """
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using UnityEngine;
using Cysharp.Threading.Tasks;
using GameCore.Enums;
using GameCore.Gameobject;

namespace GameCore.Gameobject
{
    public sealed class ParticleObjectPool : BaseSingleton<ParticleObjectPool>
    {
        private readonly Dictionary<GameObjectID, ParticlePool> pools = new();
        private readonly ConcurrentDictionary<GameObjectID, UniTask<ParticlePool>> creatingPools = new();

        // キャンセルトークン（全タスクをシーン遷移時に即殺）
        private CancellationToken destroyToken;
        private CancellationTokenSource manualCancelSource = new();
        private CancellationToken combinedToken;

        public override void AwakeSingleton()
        {
            base.AwakeSingleton();
            DontDestroyOnLoad(gameObject);

            destroyToken = this.GetCancellationTokenOnDestroy();
            manualCancelSource = new CancellationTokenSource();
            combinedToken = CancellationTokenSource.CreateLinkedTokenSource(destroyToken, manualCancelSource.Token).Token;
        }

        // 全停止＆全キャンセル（シーン遷移時に必ず呼ぶ！）
        public void StopAllAndCancelAllTasks()
        {
            manualCancelSource.Cancel();
            manualCancelSource.Dispose();
            manualCancelSource = new CancellationTokenSource();
            combinedToken = CancellationTokenSource.CreateLinkedTokenSource(destroyToken, manualCancelSource.Token).Token;

            foreach (var pool in pools.Values)
                pool?.StopAllImmediately();

            creatingPools.Clear();
        }

        // 個別ID停止
        public void StopParticle(GameObjectID id)
        {
            if (pools.TryGetValue(id, out var pool))
                pool.StopAllImmediately();
            var a = new MaterialPropertyBlock();

        }

        // 全パーティクル停止
        public void StopAllParticles()
        {
            foreach (var pool in pools.Values)
                pool?.StopAllImmediately();
        }

        public static async UniTask<ParticleHandle> Play(
            GameObjectID id,
            Vector3 position,
            Quaternion rotation = default,
            Transform parent = null,
            float forceDuration = -1f,
            TimedAction[] timedActions = null,
            Action<ParticleHandle> onCompleted = null)
        {
            if (rotation == default) rotation = Quaternion.identity;

            var pool = await Instance.GetOrCreatePool(id);
            if (pool == null) return default;

            await pool.WaitForAvailableAsync(Instance.combinedToken);
            return pool.PlayImmediately(position, rotation, parent, forceDuration, timedActions, onCompleted);
        }

        private async UniTask<ParticlePool> GetOrCreatePool(GameObjectID id)
        {
            if (pools.TryGetValue(id, out var pool))
                return pool;

            var creationTask = creatingPools.GetOrAdd(id, k =>
            {
                var tcs = new UniTaskCompletionSource<ParticlePool>();
                CreatePoolAsync(k, tcs).Forget();
                return tcs.Task;
            });

            return await creationTask;
        }

        private async UniTask CreatePoolAsync(GameObjectID id, UniTaskCompletionSource<ParticlePool> tcs)
        {
            try
            {
                var pool = new ParticlePool(id, combinedToken);
                await pool.InitializeAsync(combinedToken);
                pools[id] = pool;
                creatingPools.TryRemove(id, out _);
                tcs.TrySetResult(pool);
            }
            catch (Exception e)
            {
                creatingPools.TryRemove(id, out _);
                tcs.TrySetException(e);
            }
        }

        private void OnDestroy()
        {
            StopAllAndCancelAllTasks();
            foreach (var pool in pools.Values) pool?.Dispose();
            pools.Clear();
            creatingPools.Clear();
            manualCancelSource?.Cancel();
            manualCancelSource?.Dispose();
        }
    }

    // =============================================================
    // ParticlePool
    // =============================================================
    internal sealed class ParticlePool : IDisposable
    {
        private readonly GameObjectID id;
        private GameObject template;
        private float duration;
        private bool isLoop;
        private readonly List<PooledParticleObject> pool = new();
        private readonly Queue<PooledParticleObject> freeQueue = new();
        private readonly HashSet<PooledParticleObject> activeSet = new();
        private readonly SemaphoreSlim expandSemaphore = new(1, 1);
        private int peakUsage = 0;
        private float lastShrinkTime = 0f;
        private readonly CancellationToken poolToken;

        private const float ShrinkInterval = 30f;
        private const float ShrinkThreshold = 0.6f;
        private const int MinCapacity = 32;

        public ParticlePool(GameObjectID id, CancellationToken token)
        {
            this.id = id;
            this.poolToken = token;
        }

        public async UniTask InitializeAsync(CancellationToken ct)
        {
            template = GameObjectCore.Instance.GetGameObject(GameObjectGroup.Particle, id);
            if (template == null) throw new Exception($"[ParticlePool] Template not found: {id}");

            var ps = template.GetComponentInChildren<ParticleSystem>(true);
            if (ps == null) throw new Exception($"[ParticlePool] No ParticleSystem on {id}");

            var main = ps.main;
            duration = main.duration + main.startLifetime.constantMax + 0.5f;
            isLoop = main.loop;

            await ExpandAsync(32, ct);
        }

        public async UniTask WaitForAvailableAsync(CancellationToken ct)
        {
            using var linkedCts = CancellationTokenSource.CreateLinkedTokenSource(ct, poolToken);

            while (true)
            {
                linkedCts.Token.ThrowIfCancellationRequested();

                while (freeQueue.Count > 0 && freeQueue.Peek().isDestroyed)
                    freeQueue.Dequeue();

                if (freeQueue.Count > 0) break;

                await expandSemaphore.WaitAsync(linkedCts.Token);
                try
                {
                    if (freeQueue.Count > 0) break;
                    await ExpandAsync(Mathf.Max(8, activeSet.Count + 8), linkedCts.Token);
                }
                finally
                {
                    expandSemaphore.Release();
                }
            }
        }

        public ParticleHandle PlayImmediately(
            Vector3 position,
            Quaternion rotation,
            Transform parent,
            float forceDuration,
            TimedAction[] timedActions,
            Action<ParticleHandle> onCompleted)
        {
            while (freeQueue.Count > 0 && freeQueue.Peek().isDestroyed)
                freeQueue.Dequeue();

            var obj = freeQueue.Dequeue();
            activeSet.Add(obj);
            obj.isActive = true;
            obj.isDestroyed = false;

            var go = obj.gameObject;
            var ps = obj.particleSystem;

            if (parent != null) go.transform.SetParent(parent, false);
            else go.transform.SetParent(ParticleObjectPool.Instance.transform, false);

            go.transform.SetPositionAndRotation(position, rotation);
            go.SetActive(true);

            ps.Clear(true);
            ps.Play(true);

            float lifetime = forceDuration > 0f ? forceDuration : (isLoop ? -1f : duration);
            var handle = new ParticleHandle(this, obj, lifetime, timedActions, poolToken);
            onCompleted?.Invoke(handle);

            if (activeSet.Count > peakUsage) peakUsage = activeSet.Count;

            return handle;
        }

        internal void TryReturn(PooledParticleObject obj, int generation)
        {
            if (obj == null || obj.generation != generation || !activeSet.Remove(obj)) return;

            obj.particleSystem.Stop(true, ParticleSystemStopBehavior.StopEmittingAndClear);
            obj.gameObject.SetActive(false);
            obj.isActive = false;
            obj.gameObject.transform.SetParent(ParticleObjectPool.Instance.transform, false);
            obj.generation++;
            freeQueue.Enqueue(obj);
            TryScheduleShrink();
        }

        public void StopAllImmediately()
        {
            foreach (var obj in activeSet.ToList())
            {
                if (obj.particleSystem != null)
                {
                    obj.particleSystem.Stop(true, ParticleSystemStopBehavior.StopEmittingAndClear);
                    obj.gameObject.SetActive(false);
                }
                obj.isActive = false;
                TryReturn(obj, obj.generation);
            }
        }

        private async UniTask ExpandAsync(int count, CancellationToken ct)
        {
            var op = UnityEngine.Object.InstantiateAsync(template, count);
            await op.WithCancellation(ct);

            foreach (var go in op.Result)
            {
                go.transform.SetParent(ParticleObjectPool.Instance.transform, false);
                go.SetActive(false);
                var ps = go.GetComponentInChildren<ParticleSystem>(true);
                var pooled = new PooledParticleObject
                {
                    gameObject = go,
                    particleSystem = ps,
                    generation = 0,
                    isActive = false,
                    isDestroyed = false
                };
                pool.Add(pooled);
                freeQueue.Enqueue(pooled);
            }
        }

        private void TryScheduleShrink()
        {
            if (Time.unscaledTime - lastShrinkTime < ShrinkInterval) return;
            lastShrinkTime = Time.unscaledTime;

            if (activeSet.Count <= (int)(peakUsage * ShrinkThreshold) && pool.Count > MinCapacity)
                ShrinkAsync().Forget();
        }

        private async UniTask ShrinkAsync()
        {
            await expandSemaphore.WaitAsync();
            try
            {
                int target = Mathf.Max(MinCapacity, activeSet.Count + 16);
                if (pool.Count <= target) return;

                int toDestroy = pool.Count - target;
                int destroyed = 0;

                for (int i = pool.Count - 1; i >= 0 && destroyed < toDestroy; i--)
                {
                    var obj = pool[i];
                    if (!obj.isActive && !obj.isDestroyed)
                    {
                        obj.isDestroyed = true;
                        if (obj.gameObject) GameObject.Destroy(obj.gameObject);
                        pool.RemoveAt(i);
                        destroyed++;
                    }
                }
            }
            finally
            {
                expandSemaphore.Release();
            }
        }

        public void Dispose()
        {
            StopAllImmediately();
            foreach (var obj in pool)
                if (obj.gameObject) GameObject.Destroy(obj.gameObject);
            pool.Clear();
            freeQueue.Clear();
            activeSet.Clear();
        }
    }

    // =============================================================
    // ParticleHandle（完全安全・TimedActionもキャンセル対応）
    // =============================================================
    public readonly struct ParticleHandle : IDisposable
    {
        private readonly ParticlePool pool;
        private readonly PooledParticleObject pooledObject;
        private readonly int generation;
        private readonly CancellationTokenSource lifetimeCts;

        internal ParticleHandle(ParticlePool pool, PooledParticleObject pooledObject, float lifetime, TimedAction[] timedActions, CancellationToken externalToken)
        {
            this.pool = pool;
            this.pooledObject = pooledObject;
            this.generation = pooledObject.generation;
            this.lifetimeCts = CancellationTokenSource.CreateLinkedTokenSource(externalToken);

            var localPool = pool;
            var localObj = pooledObject;
            var localGen = this.generation;
            var localHandle = this;

            // 自動返却
            if (lifetime > 0f)
            {
                UniTask.Delay(TimeSpan.FromSeconds(lifetime), cancellationToken: lifetimeCts.Token)
                    .ContinueWith(() => localPool?.TryReturn(localObj, localGen))
                    .Forget();
            }

            // TimedAction
            if (timedActions != null)
            {
                foreach (var action in timedActions)
                {
                    float delay = action.usePercentage && lifetime > 0f
                        ? lifetime * (action.timeOrPercent / 100f)
                        : action.timeOrPercent;

                    if (delay < 0f) continue;

                    var capturedAction = action.action;
                    UniTask.Delay(TimeSpan.FromSeconds(delay), cancellationToken: lifetimeCts.Token)
                        .ContinueWith(() => capturedAction?.Invoke(localHandle))
                        .Forget();
                }
            }
        }

        public void Stop()
        {
            lifetimeCts.Cancel();
            pool?.TryReturn(pooledObject, generation);
        }

        public void Dispose() => Stop();

        public bool IsValid => pooledObject != null && pooledObject.generation == generation;
        public bool IsPlaying => pooledObject?.particleSystem != null && pooledObject.particleSystem.isPlaying;
        public GameObject GameObject => pooledObject?.gameObject;
        public ParticleSystem ParticleSystem => pooledObject?.particleSystem;
    }

    // =============================================================
    // 内部クラス
    // =============================================================
    internal sealed class PooledParticleObject
    {
        public GameObject gameObject;
        public ParticleSystem particleSystem;
        public int generation = 0;
        public bool isActive = false;
        public bool isDestroyed = false;
    }

    public struct TimedAction
    {
        public float timeOrPercent;
        public bool usePercentage;
        public Action<ParticleHandle> action;

        public TimedAction(float value, bool isPercent, Action<ParticleHandle> action)
        {
            timeOrPercent = value;
            usePercentage = isPercent;
            this.action = action;
        }
    }
}
        """
        with open(os.path.join(GAMEOBJECT_DATA,"ParticleObjectPool.cs"),"w",encoding="utf-8") as f:
            f.write(code_str)

    # ENUM_DIR/GameObject ディレクトリを作成
    if not os.path.exists(os.path.join(ENUM_DIR, "GameObject")):
        os.makedirs(os.path.join(ENUM_DIR, "GameObject"))
    
    # GameObject.json を生成
    with open(os.path.join(ENUM_DIR, "GameObject", "GameObject.json"), 'w', encoding='utf-8') as f:
        gameobject_id_list = []
        for group, group_value in data['groups'].items():
            for go in group_value['items']:
                go_id = f"{group}_{go['name']}"
                gameobject_id_list.append({
                    'description': go['desc'],
                    'id': gameobject_id_map[go_id],
                    'property': go_id,
                    'value': gameobject_id_map[go_id]
                })
        json.dump(gameobject_id_list, f, ensure_ascii=False, indent=4)
    generate_enum_csharp(os.path.join(ENUM_DIR, "GameObject", "GameObject.json"), "GameObject", ENUM_DIR)

    # GameObjectCoreSubGroups.cs（SubGroup単位のLoad/Unload専用メソッド。毎回再生成される）
    generate_gameobject_core_subgroups(data)


def generate_gameobject_core_subgroups(data):
    """
    グループごとのSubGroup専用enum（GameObject_{Group}ID）を引数に取る
    LoadSubGroup / UnloadSubGroup のオーバーロードを、partial classとして
    GameObjectCoreSubGroups.cs に生成する。
    このファイルは（GameObjectCore.cs自体とは違い）呼び出すたびに毎回上書きされる。
    """
    lines = []
    lines.append("// 自動生成ファイルです。手動編集しても generate 実行時に上書きされます。")
    lines.append("using System;")
    lines.append("using GameCore.Enums;")
    lines.append("")
    lines.append("namespace GameCore.Gameobject")
    lines.append("{")
    lines.append("    public partial class GameObjectCore")
    lines.append("    {")

    for group_name, group_value in data['groups'].items():
        subgroups = group_value.get('subgroups', [])
        if not subgroups:
            continue
        enum_name = f"GameObject_{group_name}ID"
        lines.append(f"        public void LoadSubGroup({enum_name} subGroupId, AddressableSystem.GroupCategory groupCategory, Action onCompleted = null)")
        lines.append(f"            => LoadSubGroupInternal(GameObjectGroup.{group_name}, (int)subGroupId, groupCategory, onCompleted);")
        lines.append("")
        lines.append(f"        public void UnloadSubGroup({enum_name} subGroupId, Action onCompleted = null)")
        lines.append(f"            => UnloadSubGroupInternal(GameObjectGroup.{group_name}, (int)subGroupId, onCompleted);")
        lines.append("")

    lines.append("    }")
    lines.append("}")

    with open(os.path.join(GAMEOBJECT_DATA, "GameObjectCoreSubGroups.cs"), 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))


def generate_gameobject_bin():
    """
    ゲームオブジェクトデータのバイナリファイルを生成
    """
    data = load_gameobject_data()
    with open(os.path.join(GAMEOBJECT_DATA, 'gameobject_data.bytes'), 'wb') as f:
        groups = list(data['groups'].keys())
        group_count = len(groups)
        f.write(struct.pack('i', group_count))
        offsets = [0] * group_count
        offset_pos = f.tell()
        f.write(struct.pack('i' * group_count, *offsets))
        current_offset = f.tell()

        gameobject_id_map = {'None': 0}
        gameobject_id_counter = 1
        for group, group_value in data['groups'].items():
            for go in group_value['items']:
                go_id = f"{group}_{go['name']}"
                if go_id not in gameobject_id_map:
                    gameobject_id_map[go_id] = gameobject_id_counter
                    gameobject_id_counter += 1

        for i, group in enumerate(groups):
            offsets[i] = current_offset
            group_value = data['groups'][group]
            gameobjects = group_value['items']
            subgroup_map = _subgroup_index_map(group_value.get('subgroups', []))
            f.write(struct.pack('i', len(gameobjects)))
            for go in gameobjects:
                go_id = gameobject_id_map.get(f"{group}_{go['name']}", 0)
                f.write(struct.pack('i', go_id))
                id_name = go['name'].encode('utf-8') + b'\0'
                f.write(id_name)
                path_bytes = go['path'].encode('utf-8') + b'\0'
                f.write(path_bytes)
                sub_group_id = subgroup_map.get(go.get('subgroup'), 0)
                f.write(struct.pack('i', sub_group_id))
            current_offset = f.tell()
        f.seek(offset_pos)
        f.write(struct.pack('i' * group_count, *offsets))

# ============================================================
# Material CS生成機能
# ============================================================

# Shader.GetPropertyType（UnityEngine.Rendering.ShaderPropertyType）→ C#表現のマッピング
# 旧ShaderUtil.ShaderPropertyTypeでは "TexEnv" だったが、新APIでは "Texture" になるため両方保持
MATERIAL_PROPERTY_TYPE_MAP = {
    'Color':   {'cs_type': 'Color',   'setter': 'SetColor'},
    'Vector':  {'cs_type': 'Vector4', 'setter': 'SetVector'},
    'Float':   {'cs_type': 'float',   'setter': 'SetFloat'},
    'Range':   {'cs_type': 'float',   'setter': 'SetFloat'},
    'Int':     {'cs_type': 'int',     'setter': 'SetInt'},
    'Texture': {'cs_type': 'Texture', 'setter': 'SetTexture'},
    'TexEnv':  {'cs_type': 'Texture', 'setter': 'SetTexture'},  # 旧ShaderUtil由来データとの互換用
}

def _material_property_field_name(prop_name):
    """
    シェーダープロパティ名からC#の識別子名を作る
    例: "_Color" -> "Color", "_EmissionColor" -> "EmissionColor", "_MainTex" -> "MainTex"
    """
    name = prop_name.lstrip('_')
    if not name:
        name = prop_name
    return name[0].upper() + name[1:]

def get_material_data():
    """
    生成済みMaterialDataエントリの一覧を取得
    """
    return load_material_data()

def _request_material_properties_from_unity(file_path):
    """
    Unityエディタに対して指定パスのプロパティ一覧を問い合わせる
    （エクスプローラーは開かない・内部共通処理）

    Addressableパスは get_material_properties の戻り値には頼らず、
    Sound/GameObjectと同じ get_addressable_path で個別に取得する。
    （プロパティ列挙とAddressable登録有無は別々の関心事であり、
    　前者の戻り値からAddressableパスを取り出そうとしていたのが、
    　パスが取得できなくなっていた原因）
    """
    result = send_to_unity('get_material_properties', {'file_path': file_path})
    if result is None:
        raise Exception("プロパティ情報を取得できませんでした。EditorCommunicationが起動しているか確認してください。")

    try:
        parsed = json.loads(result)
        if not isinstance(parsed, dict):
            parsed = {}
    except (TypeError, ValueError):
        parsed = {}

    addressable_path = get_addressable_path(file_path) or ''

    return {
        'addressable_path': addressable_path,
        'properties': parsed.get('items', []) or []
    }

def get_material_properties():
    """
    エクスプローラーを開いて .shader / .mat ファイルを選択し、
    含まれるプロパティ名・型・Addressableパスを一度の通信で取得する
    """
    project_path = get_unity_project_path()
    if not project_path:
        raise Exception("Unityプロジェクトのパスを取得できませんでした。")

    file_path = select_file(project_path, [("Shader / Materialファイル", "*.shader *.shadergraph *.mat")])
    if not file_path:
        raise Exception("ファイルが選択されていません。")

    fetched = _request_material_properties_from_unity(file_path)

    return {
        'absolute_path': os.path.abspath(file_path),
        'addressable_path': fetched['addressable_path'],
        'properties': fetched['properties']
    }

def add_material_group(group_name):
    """
    Materialグループを追加
    """
    data = load_material_data()
    if group_name and group_name not in data['groups']:
        data['groups'][group_name] = {'items': [], 'subgroups': []}
        save_material_data(data)

def delete_material_group(group_name):
    """
    Materialグループを削除し、そのグループに属していたC#ファイルも削除した上で
    Enum・Core・バイナリを再生成する
    """
    data = load_material_data()
    group_value = data['groups'].pop(group_name, {'items': []})
    entries = group_value.get('items', []) if isinstance(group_value, dict) else group_value
    save_material_data(data)

    for entry in entries:
        cs_dir = os.path.join(MATERIAL_DATA, f"{entry['class_name']}")
        if os.path.isdir(cs_dir):
            shutil.rmtree(cs_dir)

    generate_material_enum_csharp()
    generate_material_bin()

def add_material_subgroup(group_name, subgroup_name):
    """
    Materialグループの中にSubGroupを追加する
    （Enum/バイナリへの反映は他カテゴリ同様、Generateボタン実行時に行われる）
    """
    data = load_material_data()
    add_subgroup_to_group(data, group_name, subgroup_name)
    save_material_data(data)

def delete_material_subgroup(group_name, subgroup_name):
    """
    Materialグループから SubGroup を削除する
    （Enum/バイナリへの反映は他カテゴリ同様、Generateボタン実行時に行われる）
    """
    data = load_material_data()
    delete_subgroup_from_group(data, group_name, subgroup_name)
    save_material_data(data)

def generate_material_entry(group_name, class_name, desc, absolute_path, selected_property_names, subgroup_name=None):
    """
    CS生成ボタンから呼ばれるメイン処理。
    jsonに保持しているabsolute_pathを使い、Unityと再度通信して
    最新のプロパティ（型含む）とAddressableパスを取得し直してからCSを再生成する。
    併せてMaterialGroup/MaterialID Enum・Core一式・バイナリも再生成する。
    """
    if not group_name:
        raise Exception("グループを選択してください。")
    if not class_name:
        raise Exception("クラス名を入力してください。")
    if not absolute_path:
        raise Exception("Shader / Materialのパスがありません。先にファイルを選択してください。")
    if not selected_property_names:
        raise Exception("プロパティを1つ以上選択してください。")

    data = load_material_data()
    if group_name not in data['groups']:
        raise Exception(f"グループ '{group_name}' が見つかりません。先にグループを作成してください。")
    if subgroup_name and subgroup_name not in data['groups'][group_name]['subgroups']:
        raise Exception(f"SubGroup '{subgroup_name}' が見つかりません。先にSubGroupを作成してください。")

    # 再通信して最新のプロパティ・Addressableパスを取得
    fetched = _request_material_properties_from_unity(absolute_path)
    addressable_path = fetched['addressable_path']

    selected_set = set(selected_property_names)
    properties = [p for p in fetched['properties'] if p.get('name') in selected_set]
    if not properties:
        raise Exception("選択したプロパティがシェーダーから見つかりませんでした。ファイルが変更された可能性があります。")

    # JSONエントリを更新（同グループ内で同名クラスは上書き。absolute_pathを保持し続ける）
    items = data['groups'][group_name]['items']
    data['groups'][group_name]['items'] = [e for e in items if e['class_name'] != class_name]
    data['groups'][group_name]['items'].append({
        'class_name': class_name,
        'desc': desc or '',
        'absolute_path': absolute_path,
        'addressable_path': addressable_path,
        'properties': properties,
        'subgroup': subgroup_name or None
    })
    save_material_data(data)

    # C#（クラス本体・Group/ID Enum・Core一式・バイナリ）を再生成
    generate_material_csharp(group_name, class_name)
    generate_material_enum_csharp()
    generate_material_bin()
    generate_material_core_files()

def regenerate_material_entry(group_name, class_name):
    """
    生成済みエントリの「再生成」用。jsonに保持しているabsolute_pathと
    これまで選択していたプロパティ名を使って、Unityに再問い合わせしてから再生成する。
    """
    data = load_material_data()
    items = data['groups'].get(group_name, {}).get('items', [])
    entry = next((e for e in items if e['class_name'] == class_name), None)
    if entry is None:
        raise Exception(f"{class_name} のデータが見つかりません。")

    selected_names = [p['name'] for p in entry.get('properties', []) if p.get('name')]
    generate_material_entry(
        group_name,
        entry['class_name'],
        entry.get('desc', ''),
        entry.get('absolute_path'),
        selected_names,
        entry.get('subgroup')
    )

def delete_material_entry(group_name, class_name):
    """
    Materialエントリと生成済みC#ファイルを削除し、Enum・バイナリも再生成する
    """
    data = load_material_data()
    if group_name in data['groups']:
        items = data['groups'][group_name]['items']
        data['groups'][group_name]['items'] = [e for e in items if e['class_name'] != class_name]
    save_material_data(data)

    cs_dir = os.path.join(MATERIAL_DATA, f"{class_name}")
    if os.path.isdir(cs_dir):
        shutil.rmtree(cs_dir)

    generate_material_enum_csharp()
    generate_material_bin()

def _build_material_cs_code(class_name, desc, properties):
    """
    選択されたプロパティに基づき、MaterialPropertyBlockを使った
    高効率なマテリアル操作用のC#クラスのソースコード文字列を組み立てる
    （グループ登録あり／CS-onlyのどちらからも呼ばれる共通ロジック）
    """
    id_field_lines = []
    setter_method_blocks = []
    used_field_names = set()

    for prop in properties:
        prop_name = prop.get('name')
        if not prop_name:
            continue
        prop_type = prop.get('type', 'Float')
        type_info = MATERIAL_PROPERTY_TYPE_MAP.get(prop_type, MATERIAL_PROPERTY_TYPE_MAP['Float'])

        field_name = _material_property_field_name(prop_name)
        # 重複するフィールド名を避ける
        base_field_name = field_name
        suffix = 1
        while field_name in used_field_names:
            suffix += 1
            field_name = f"{base_field_name}{suffix}"
        used_field_names.add(field_name)

        id_name = f"{field_name}PropertyId"

        id_field_lines.append(
            f'    private static readonly int {id_name} = Shader.PropertyToID("{prop_name}");'
        )

        setter_method_blocks.append(f'''
    /// <summary>
    /// {prop_name} ({prop_type}) をMaterialPropertyBlock経由で効率的に変更する
    /// メモリリークせず、バッチング（描画最適化）も維持されます
    /// </summary>
    public void Set{field_name}Efficiently({type_info['cs_type']} newValue)
    {{
        targetRenderer.GetPropertyBlock(propertyBlock);
        propertyBlock.{type_info['setter']}({id_name}, newValue);
        targetRenderer.SetPropertyBlock(propertyBlock);
    }}''')

    id_fields_str = "\n".join(id_field_lines) if id_field_lines else "    // プロパティが選択されていません"
    setters_str = "".join(setter_method_blocks)

    return f"""using UnityEngine;
using GameCore.MaterialData;

/// <summary>
/// {desc}
/// </summary>
[System.Serializable]
public class {class_name} : BaseMaterialData
{{

{id_fields_str}


{setters_str}

}}
"""

def generate_material_csharp(group_name, class_name):
    """
    選択されたプロパティに基づき、MaterialPropertyBlockを使った
    高効率なマテリアル操作用のC#クラスを1ファイル生成する（グループ登録あり・Enum/バイナリ対象）
    """
    _ensure_base_material_data()

    data = load_material_data()
    items = data['groups'].get(group_name, {}).get('items', [])
    entry = next((e for e in items if e['class_name'] == class_name), None)
    if entry is None:
        raise Exception(f"{class_name} のデータが見つかりません。")

    properties = entry.get('properties', [])
    desc = entry.get('desc', '')
    code_str = _build_material_cs_code(class_name, desc, properties)

    if not os.path.exists(os.path.join(MATERIAL_DATA,f"{class_name}")):        
        os.mkdir(os.path.join(MATERIAL_DATA,f"{class_name}"))
    cs_path = os.path.join(MATERIAL_DATA,f"{class_name}", f"{class_name}.cs")
    
    with open(cs_path, 'w', encoding='utf-8') as f:
        f.write(code_str)

def _material_id_map(data):
    """
    "{group}_{class_name}" -> MaterialID の対応表を作る（None=0固定、以降は登場順）
    GameObjectのgameobject_id_mapと同じ考え方（グループをまたいでユニークなID）。
    ※ CS-only（Enum非登録）のエントリはここには含まれない。
    """
    id_map = {'None': 0}
    counter = 1
    for group, group_value in data['groups'].items():
        for e in group_value['items']:
            key = f"{group}_{e['class_name']}"
            if key not in id_map:
                id_map[key] = counter
                counter += 1
    return id_map

def generate_material_enum_csharp():
    """
    GameObject/Sound/Textureと同様に、Material用のenum(MaterialGroup / MaterialID)を生成する
    - MaterialEnums.cs（MaterialGroup）を生成
    - ENUM_DIR/Material/Material.json を更新してMaterialID.csを生成（generate_enum_csharpを再利用）
    """
    data = load_material_data()

    # MaterialEnums.cs（MaterialGroup） - GameObjectEnums.csのGameObjectGroupと同じ考え方
    with open(os.path.join(MATERIAL_DATA, 'MaterialEnums.cs'), 'w', encoding='utf-8') as f:
        f.write('namespace GameCore.MaterialData {\n')
        f.write('    public enum MaterialGroup { None')
        for group in data['groups']:
            f.write(f', {group}')
        f.write(' ,Max\n  };\n')
        f.write('}\n')

    id_map = _material_id_map(data)

    material_dir = os.path.join(ENUM_DIR, "Material")
    if not os.path.exists(material_dir):
        os.makedirs(material_dir)

    material_json_path = os.path.join(material_dir, "Material.json")
    with open(material_json_path, 'w', encoding='utf-8') as f:
        material_id_list = []
        for group, group_value in data['groups'].items():
            for e in group_value['items']:
                key = f"{group}_{e['class_name']}"
                material_id_list.append({
                    'description': e.get('desc', ''),
                    'id': id_map[key],
                    'property': key,
                    'value': id_map[key]
                })
        json.dump(material_id_list, f, ensure_ascii=False, indent=4)

    generate_enum_csharp(material_json_path, "Material", ENUM_DIR)

    # SubGroup用enum（Material_{Group}ID）を各グループごとに生成／同期
    subgroup_enum_names = sync_subgroup_enum_files(
    ENUM_DIR, "Material", data['groups'],
    data_dir=MATERIAL_DATA, namespace="GameCore.MaterialData", class_name="MaterialCore",
    group_enum_name="MaterialGroup", id_enum_name="MaterialID",
    global_key_field="class_name"
    )
    register_enum_names(ENUM_DIR, subgroup_enum_names)

    # MaterialCoreSubGroups.cs（毎回再生成）
    generate_material_core_subgroups(data)


def generate_material_core_subgroups(data):
    """
    グループごとのSubGroup専用enum（Material_{Group}ID）を引数に取る
    LoadSubGroup / UnloadSubGroup のオーバーロードを、partial classとして
    MaterialCoreSubGroups.cs に生成する（毎回上書き）。
    """
    lines = []
    lines.append("// 自動生成ファイルです。手動編集しても generate 実行時に上書きされます。")
    lines.append("using System;")
    lines.append("using GameCore.Enums;")
    lines.append("")
    lines.append("namespace GameCore.MaterialData")
    lines.append("{")
    lines.append("    public partial class MaterialCore")
    lines.append("    {")

    for group_name, group_value in data['groups'].items():
        subgroups = group_value.get('subgroups', [])
        if not subgroups:
            continue
        enum_name = f"Material_{group_name}ID"
        lines.append(f"        public void LoadSubGroup({enum_name} subGroupId, AddressableSystem.GroupCategory groupCategory, Action onCompleted = null)")
        lines.append(f"            => LoadSubGroupInternal(MaterialGroup.{group_name}, (int)subGroupId, groupCategory, onCompleted);")
        lines.append("")
        lines.append(f"        public void UnloadSubGroup({enum_name} subGroupId, Action onCompleted = null)")
        lines.append(f"            => UnloadSubGroupInternal(MaterialGroup.{group_name}, (int)subGroupId, onCompleted);")
        lines.append("")

    lines.append("    }")
    lines.append("}")

    with open(os.path.join(MATERIAL_DATA, "MaterialCoreSubGroups.cs"), 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))

def generate_material_bin():
    """
    gameobject_data.bytes と同じ「グループごとのオフセットテーブル」形式で、
    MaterialGroup / MaterialID / クラス名 / Addressableパスをバイナリ出力する
    （material_data.bytes）
    """
    data = load_material_data()
    with open(os.path.join(MATERIAL_DATA, 'material_data.bytes'), 'wb') as f:
        groups = list(data['groups'].keys())
        group_count = len(groups)
        f.write(struct.pack('i', group_count))
        offsets = [0] * group_count
        offset_pos = f.tell()
        f.write(struct.pack('i' * group_count, *offsets))
        current_offset = f.tell()

        id_map = _material_id_map(data)

        for i, group in enumerate(groups):
            offsets[i] = current_offset
            group_value = data['groups'][group]
            entries = group_value['items']
            subgroup_map = _subgroup_index_map(group_value.get('subgroups', []))
            f.write(struct.pack('i', len(entries)))
            for e in entries:
                material_id = id_map.get(f"{group}_{e['class_name']}", 0)
                f.write(struct.pack('i', material_id))
                name_bytes = e['class_name'].encode('utf-8') + b'\0'
                f.write(name_bytes)
                addressable_path = e.get('addressable_path') or ''
                path_bytes = addressable_path.encode('utf-8') + b'\0'
                f.write(path_bytes)
                sub_group_id = subgroup_map.get(e.get('subgroup'), 0)
                f.write(struct.pack('i', sub_group_id))
            current_offset = f.tell()
        f.seek(offset_pos)
        f.write(struct.pack('i' * group_count, *offsets))

def _ensure_base_material_data():
    """
    Material用CS生成の共通基底クラス（BaseMaterialData.cs）が存在しなければ生成する。
    元々generate_gameobject_csharp内に紛れ込んでいた処理をMaterial側へ移設し、
    かつ f-string化していなかったため二重波括弧がそのまま出力される不具合
    （{{ }} が壊れたC#として書き出されていた）を修正。
    MonoBehaviourにコンストラクタを持たせるのは実行時に呼ばれないため、Awakeへ変更。
    """
    if not os.path.exists(MATERIAL_DATA):
        os.makedirs(MATERIAL_DATA)
    if not os.path.exists(os.path.join(MATERIAL_DATA, "BaseMaterialData.cs")):
        code_str = """using UnityEngine;

namespace GameCore.MaterialData
{
    /// <summary>
    /// Material CS生成機能によって生成される各クラスの共通基底クラス
    /// </summary>
    [System.Serializable]
    public abstract class BaseMaterialData 
    {
        [SerializeField] protected Renderer targetRenderer;
        // MaterialPropertyBlock用（メモリを汚さず、マテリアルを複製しない最高効率の方式）
        protected MaterialPropertyBlock propertyBlock;

        // マテリアル自体のパラメータを直接変える必要がある場合にキャッシュする変数
        protected Material cachedMaterial;

        public virtual void Awake()
        {
            if (targetRenderer == null) return;
            propertyBlock = new MaterialPropertyBlock();

            // 【注意】もしマテリアル自体のシェーダーキーワード切り替えなどが必要な場合のみ、
            // インスタンスをキャッシュして使い回します（毎フレームの .material 呼び出しは絶対NG）
            // cachedMaterial = targetRenderer.material;
        }
    }
}
"""
        with open(os.path.join(MATERIAL_DATA, "BaseMaterialData.cs"), "w", encoding="utf-8") as f:
            f.write(code_str)

def generate_material_core_files():
    """
    GameObjectCore/GameObjectDatabase/GameObjectBinaryReaderと同じ「グループ紐づけ」構成で、
    Addressable対応のMaterialCore一式を生成する（存在する場合はスキップ）。

    ※ グループ対応前の形式（Dictionary<MaterialID, ...>のみ）から作り直しているため、
    　既存プロジェクトに旧MaterialCore.cs / MaterialDatabase.cs / MaterialBinaryReader.cs /
    　MaterialEnums.cs がある場合は、一度削除してから再生成してください
    　（このスキャフォールドは既存ファイルを上書きしない方針のため）。
    """
    _ensure_base_material_data()

    # MaterialDatabase.cs
    if not os.path.exists(os.path.join(MATERIAL_DATA, 'MaterialDatabase.cs')):
        code_str = """
using System.Collections.Generic;
using GameCore.Enums;
namespace GameCore.MaterialData
{
    public class MaterialDatabase
    {
        [System.Serializable]
        public class MaterialAssetData
        {
            private readonly MaterialID materialID;
            private readonly string idName;
            private readonly string addressablePath;
            private readonly int subGroupId;
            public MaterialAssetData(MaterialID materialID, string idName, string addressablePath, int subGroupId = 0)
            {
                this.materialID = materialID;
                this.idName = idName;
                this.addressablePath = addressablePath;
                this.subGroupId = subGroupId;
            }
            public MaterialID MaterialID => materialID;
            public string IdName => idName;
            public string AddressablePath => addressablePath;
            // SubGroup ID（0 = SubGroupなし）。専用enum(例:Material_EnemyID)にキャストして使う
            public int SubGroupId => subGroupId;
        }

        [System.Serializable]
        public class GroupedMaterials
        {
            private readonly MaterialGroup group;
            private readonly List<MaterialAssetData> materials;
            public GroupedMaterials(MaterialGroup group, List<MaterialAssetData> materials)
            {
                this.group = group;
                this.materials = materials ?? new List<MaterialAssetData>();
            }
            public MaterialGroup Group => group;
            public List<MaterialAssetData> Materials => materials;
        }

        private readonly List<GroupedMaterials> groupedMaterials;
        public MaterialDatabase()
        {
            groupedMaterials = new List<GroupedMaterials>();
        }
        public List<GroupedMaterials> GroupedMaterialsList => groupedMaterials;
    }
}
"""
        with open(os.path.join(MATERIAL_DATA, 'MaterialDatabase.cs'), 'w', encoding='utf-8') as f:
            f.write(code_str)

    # MaterialBinaryReader.cs
    if not os.path.exists(os.path.join(MATERIAL_DATA, 'MaterialBinaryReader.cs')):
        code_str = """
using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;
using GameCore.Enums;
using UnityEngine.AddressableAssets;
using UnityEngine.ResourceManagement.AsyncOperations;
using Cysharp.Threading.Tasks;

namespace GameCore.MaterialData
{
    public class MaterialBinaryReader
    {
        public static MaterialDatabase LoadMaterialDatabaseFromBinary(string filePath, bool addressable = false)
        {
            if (!addressable)
            {
                if (!File.Exists(filePath))
                {
                    Debug.LogError($"Binary file not found: {filePath}");
                    return null;
                }

                using (BinaryReader reader = new BinaryReader(File.Open(filePath, FileMode.Open)))
                {
                    return ReadDatabase(reader);
                }
            }
            else
            {
                AsyncOperationHandle<TextAsset> handle = Addressables.LoadAssetAsync<TextAsset>(filePath);

                handle.WaitForCompletion();

                if (handle.Status != AsyncOperationStatus.Succeeded || handle.Result == null)
                {
                    Debug.LogError($"Failed to load Addressable binary: {filePath}");
                    if (handle.IsValid()) Addressables.Release(handle);
                    return null;
                }

                TextAsset textAsset = handle.Result;

                using (MemoryStream ms = new MemoryStream(textAsset.bytes))
                using (BinaryReader reader = new BinaryReader(ms))
                {
                    MaterialDatabase database = ReadDatabase(reader);
                    Addressables.Release(handle);
                    return database;
                }
            }
        }

        public static async UniTask<MaterialDatabase> LoadMaterialDatabaseFromBinaryAsync(string filePath, bool addressable = false)
        {
            if (!addressable)
            {
                if (!File.Exists(filePath))
                {
                    Debug.LogError($"Binary file not found: {filePath}");
                    return null;
                }

                using (BinaryReader reader = new BinaryReader(File.Open(filePath, FileMode.Open)))
                {
                    return ReadDatabase(reader);
                }
            }
            else
            {
                AsyncOperationHandle<TextAsset> handle = Addressables.LoadAssetAsync<TextAsset>(filePath);

                await handle.ToUniTask();

                if (handle.Status != AsyncOperationStatus.Succeeded || handle.Result == null)
                {
                    Debug.LogError($"Failed to load Addressable binary: {filePath}");
                    if (handle.IsValid()) Addressables.Release(handle);
                    return null;
                }

                TextAsset textAsset = handle.Result;
                byte[] rawBytes = textAsset.bytes;

                using (MemoryStream ms = new MemoryStream(rawBytes))
                using (BinaryReader reader = new BinaryReader(ms))
                {
                    MaterialDatabase database = ReadDatabase(reader);
                    Addressables.Release(handle);
                    return database;
                }
            }
        }

        // 共通読み込みロジック（GameObjectBinaryReaderと同じグループ・オフセット構成）
        private static MaterialDatabase ReadDatabase(BinaryReader reader)
        {
            MaterialDatabase database = new MaterialDatabase();

            int groupCount = reader.ReadInt32();
            int[] offsets = new int[groupCount];

            for (int i = 0; i < groupCount; i++)
            {
                offsets[i] = reader.ReadInt32();
            }

            string[] groupNames = Enum.GetNames(typeof(MaterialGroup));
            if (groupCount > groupNames.Length - 1)
            {
                Debug.LogError("Binary contains more groups than defined in MaterialGroup enum.");
                return null;
            }

            for (int i = 0; i < groupCount; i++)
            {
                reader.BaseStream.Seek(offsets[i], SeekOrigin.Begin);
                int materialCount = reader.ReadInt32();
                List<MaterialDatabase.MaterialAssetData> materials = new List<MaterialDatabase.MaterialAssetData>();

                for (int j = 0; j < materialCount; j++)
                {
                    int materialId = reader.ReadInt32();
                    string idName = ReadNullTerminatedString(reader);
                    string addressablePath = ReadNullTerminatedString(reader);
                    int subGroupId = reader.ReadInt32();

                    materials.Add(new MaterialDatabase.MaterialAssetData(
                        materialID: (MaterialID)materialId,
                        idName: idName,
                        addressablePath: addressablePath,
                        subGroupId: subGroupId
                    ));
                }

                database.GroupedMaterialsList.Add(new MaterialDatabase.GroupedMaterials(
                    group: (MaterialGroup)(i + 1),
                    materials: materials
                ));
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
"""
        with open(os.path.join(MATERIAL_DATA, 'MaterialBinaryReader.cs'), 'w', encoding='utf-8') as f:
            f.write(code_str)

    # MaterialCore.cs（GameObjectCoreと同じグループ紐づけのDictionaryで管理）
    if not os.path.exists(os.path.join(MATERIAL_DATA, 'MaterialCore.cs')):
        code_str = """
using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using UnityEngine;
using Cysharp.Threading.Tasks;
using AddressableSystem;
using GameCore.Enums;

namespace GameCore.MaterialData
{
    public partial class MaterialCore : BaseSingleton<MaterialCore>
    {
        private MaterialDatabase database;
        private Dictionary<MaterialGroup, Dictionary<MaterialID, AddressableData<Material>>> loadedMaterials =
            new Dictionary<MaterialGroup, Dictionary<MaterialID, AddressableData<Material>>>();
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
            string path = SupportFiles.ADDRESSABLE_CHECK ? SupportFiles.ALL_MATERIAL_BIN_FILE : SupportFiles.ALL_MATERIAL_BIN;
            database = await MaterialBinaryReader.LoadMaterialDatabaseFromBinaryAsync(path, SupportFiles.ADDRESSABLE_CHECK);
            if (database == null)
            {
                Debug.LogError("Failed to load MaterialDatabase from binary.");
            }
            await UniTask.CompletedTask.AttachExternalCancellation(destroyToken);
            isLoadDatabase = true;
        }

        public void LoadGroup(MaterialGroup group, GroupCategory groupCategory, Action action = null)
        {
            LoadGroupAsync(group, groupCategory, action).Forget();
        }

        public async UniTask LoadGroupAsync(MaterialGroup group, GroupCategory groupCategory, Action action = null)
        {
            while (database == null)
            {
                await UniTask.Yield(cancellationToken: destroyToken);
            }
            if (loadedMaterials.ContainsKey(group)) { action?.Invoke(); return; }
            var materials = database.GroupedMaterialsList.FirstOrDefault(data => data.Group == group);
            if (materials == null) return;

            loadedMaterials[group] = new Dictionary<MaterialID, AddressableData<Material>>();
            var tasks = new List<UniTask>();

            foreach (var mat in materials.Materials)
            {
                var addressable = new AddressableData<Material>(groupCategory, AssetCategory.Material, mat.AddressablePath);
                tasks.Add(addressable.LoadAsync(obj =>
                {
                    if (addressable.IsLoadedAndSetup)
                    {
                        loadedMaterials[group][mat.MaterialID] = addressable;
                    }
                }, ex =>
                {
                    Debug.LogError($"Failed to load material for {mat.MaterialID} at {mat.AddressablePath}: {ex.Message}");
                }).AttachExternalCancellation(destroyToken));
            }

            await UniTask.WhenAll(tasks);
            action?.Invoke();
        }

        public void UnloadGroup(MaterialGroup group, GroupCategory groupCategory, Action action = null)
        {
            UnloadGroupAsync(group, groupCategory, action).Forget();
        }

        public async UniTask UnloadGroupAsync(MaterialGroup group, GroupCategory groupCategory, Action action = null)
        {
            if (!loadedMaterials.TryGetValue(group, out var materials)) return;

            foreach (var addressable in materials.Values)
            {
                addressable.Release();
            }
            loadedMaterials.Remove(group);
            AddressableDataCore.Instance.ReleaseCategory(groupCategory, AssetCategory.Material);
            action?.Invoke();
            await UniTask.CompletedTask.AttachExternalCancellation(destroyToken);
        }

        // =============================================================
        // 個別ID単位のロード／アンロード
        // 既存の loadedMaterials（グループロードと同じキャッシュ）をそのまま使う。
        // =============================================================
        internal void LoadSingle(MaterialGroup group, MaterialID id, GroupCategory groupCategory, Action action = null)
            => LoadSingleAsync(group, id, groupCategory, action).Forget();

        internal async UniTask LoadSingleAsync(MaterialGroup group, MaterialID id, GroupCategory groupCategory, Action action = null)
        {
            while (database == null)
                await UniTask.Yield(cancellationToken: destroyToken);

            if (loadedMaterials.TryGetValue(group, out var existing) && existing.ContainsKey(id))
            {
                action?.Invoke();
                return;
            }

            var groupData = database.GroupedMaterialsList.FirstOrDefault(d => d.Group == group);
            var mat = groupData?.Materials.FirstOrDefault(m => m.MaterialID == id);
            if (mat == null) { action?.Invoke(); return; }

            if (!loadedMaterials.ContainsKey(group))
                loadedMaterials[group] = new Dictionary<MaterialID, AddressableData<Material>>();

            var addressable = new AddressableData<Material>(groupCategory, AssetCategory.Material, mat.AddressablePath);
            await addressable.LoadAsync(obj =>
            {
                if (addressable.IsLoadedAndSetup)
                {
                    loadedMaterials[group][id] = addressable;
                }
            }, ex =>
            {
                Debug.LogError($"Failed to load single material {id} at {mat.AddressablePath}: {ex.Message}");
            }).AttachExternalCancellation(destroyToken);

            action?.Invoke();
        }

        public void UnloadSingle(MaterialGroup group, MaterialID id, Action action = null)
            => UnloadSingleAsync(group, id, action).Forget();

        public async UniTask UnloadSingleAsync(MaterialGroup group, MaterialID id, Action action = null)
        {
            if (loadedMaterials.TryGetValue(group, out var dict) && dict.TryGetValue(id, out var addressable))
            {
                addressable.ReleaseAndUntrack();
                dict.Remove(id);
            }
            action?.Invoke();
            await UniTask.CompletedTask.AttachExternalCancellation(destroyToken);
        }

        // =============================================================
        // SubGroup単位のロード／アンロード（内部実装）
        // 公開APIは MaterialCoreSubGroups.cs 側で、グループごとの
        // 専用enum（例: Material_EnemyID）を受け取るオーバーロードとして生成される。
        // どのマテリアルがどのSubGroupに属するかは MaterialAssetData.SubGroupId から都度判定する。
        // 既存の loadedMaterials キャッシュをそのまま使い、専用の管理は持たない。
        // =============================================================
        internal void LoadSubGroupInternal(MaterialGroup group, int subGroupId, GroupCategory groupCategory, Action action = null)
            => LoadSubGroupInternalAsync(group, subGroupId, groupCategory, action).Forget();

        internal async UniTask LoadSubGroupInternalAsync(MaterialGroup group, int subGroupId, GroupCategory groupCategory, Action action = null)
        {
            while (database == null)
                await UniTask.Yield(cancellationToken: destroyToken);

            var groupData = database.GroupedMaterialsList.FirstOrDefault(d => d.Group == group);
            if (groupData == null) { action?.Invoke(); return; }

            if (!loadedMaterials.ContainsKey(group))
                loadedMaterials[group] = new Dictionary<MaterialID, AddressableData<Material>>();

            var tasks = new List<UniTask>();
            foreach (var mat in groupData.Materials)
            {
                if (mat.SubGroupId != subGroupId) continue;
                if (loadedMaterials[group].ContainsKey(mat.MaterialID)) continue;

                var addressable = new AddressableData<Material>(groupCategory, AssetCategory.Material, mat.AddressablePath);
                tasks.Add(addressable.LoadAsync(obj =>
                {
                    if (addressable.IsLoadedAndSetup)
                        loadedMaterials[group][mat.MaterialID] = addressable;
                }, ex =>
                {
                    Debug.LogError($"Failed to load material for {mat.MaterialID} at {mat.AddressablePath}: {ex.Message}");
                }).AttachExternalCancellation(destroyToken));
            }

            await UniTask.WhenAll(tasks);
            action?.Invoke();
        }

        internal void UnloadSubGroupInternal(MaterialGroup group, int subGroupId, Action action = null)
            => UnloadSubGroupInternalAsync(group, subGroupId, action).Forget();

        internal async UniTask UnloadSubGroupInternalAsync(MaterialGroup group, int subGroupId, Action action = null)
        {
            if (loadedMaterials.TryGetValue(group, out var dict) && database != null)
            {
                var groupData = database.GroupedMaterialsList.FirstOrDefault(d => d.Group == group);
                if (groupData != null)
                {
                    foreach (var mat in groupData.Materials)
                    {
                        if (mat.SubGroupId != subGroupId) continue;
                        if (dict.TryGetValue(mat.MaterialID, out var addressable))
                        {
                            addressable.ReleaseAndUntrack();
                            dict.Remove(mat.MaterialID);
                        }
                    }
                }
            }

            action?.Invoke();
            await UniTask.CompletedTask.AttachExternalCancellation(destroyToken);
        }

        public void UnloadAll(Action action = null)
        {
            UnloadAllAsync(action).Forget();
        }

        public async UniTask UnloadAllAsync(Action action = null)
        {
            foreach (var group in loadedMaterials.Values)
            {
                foreach (var data in group.Values)
                {
                    data.Release();
                }
                await UniTask.Yield(destroyToken);
                group.Clear();
            }
            loadedMaterials.Clear();

            AddressableDataCore.Instance.ReleaseAssetsAll(AssetCategory.Material);
            await UniTask.Yield(destroyToken);
            action?.Invoke();
            await UniTask.CompletedTask.AttachExternalCancellation(destroyToken);
        }

        public Material GetMaterial(MaterialGroup group, MaterialID id)
        {
            if (loadedMaterials.TryGetValue(group, out var groupMaterials) && groupMaterials.TryGetValue(id, out var addressable))
            {
                return addressable.GetAddressableObjectResult();
            }
            return null;
        }

        private void OnDestroy()
        {
            foreach (var group in loadedMaterials.Values)
            {
                foreach (var mat in group.Values)
                {
                    mat.Release();
                }
            }
            loadedMaterials.Clear();
        }
    }
}
"""
        with open(os.path.join(MATERIAL_DATA, 'MaterialCore.cs'), 'w', encoding='utf-8') as f:
            f.write(code_str)

def get_texture_file_path(group_name, index):
    """
    テクスチャの絶対パスを取得
    """
    data = load_texture_data()
    items = data['groups'].get(group_name, {}).get('items', [])
    if index < len(items):
        return items[index]['absolute_path']
    return None

def get_sound_file_path(group_name, index):
    """
    サウンドの絶対パスを取得
    """
    data = load_sound_data()
    items = data['groups'].get(group_name, {}).get('items', [])
    if index < len(items):
        return items[index]['absolute_path']
    return None

# =============================================================================
# Material「CS生成のみ」モード
# -----------------------------------------------------------------------------
# 通常のMaterialエントリ（generate_material_entry）とは完全に独立した保管場所
# （MATERIAL_CS_ONLY_JSON）で管理する。
#   - MaterialGroup / MaterialID のEnumには一切登録されない
#   - material_data.bytes（バイナリ）にも一切含まれない
#   - 生成されるのは MaterialPropertyBlock操作用の .cs クラス本体だけ
# 「とりあえずプロパティ操作用のクラスだけ欲しい」というケース向けの軽量モード。
# =============================================================================

def load_material_cs_only_data():
    """
    assets_material_cs_only.json を読み込む（存在しなければ空のentriesを返す）
    """
    if os.path.exists(MATERIAL_CS_ONLY_JSON):
        with open(MATERIAL_CS_ONLY_JSON, 'r', encoding='utf-8') as f:
            data = json.load(f)
        data.setdefault('entries', [])
        return data
    return {'entries': []}

def save_material_cs_only_data(data):
    """
    assets_material_cs_only.json を保存
    """
    os.makedirs(MATERIAL_CS_ONLY_DATA, exist_ok=True)
    with open(MATERIAL_CS_ONLY_JSON, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def get_material_cs_only_data():
    """
    CS-onlyモードで生成済みのエントリ一覧を取得
    """
    return load_material_cs_only_data()

def generate_material_cs_only(class_name, desc, absolute_path, selected_property_names):
    """
    「CS生成だけ」モードのメイン処理。
    通常のgenerate_material_entryと違い、
      - グループへの追加をしない
      - MaterialGroup / MaterialID Enumへの登録をしない
      - material_data.bytes（バイナリ）に含めない
    Unityと通信して最新のプロパティ・Addressableパスを取得し、
    MaterialPropertyBlock操作用の.csファイル1つだけを生成する。
    """
    if not class_name:
        raise Exception("クラス名を入力してください。")
    if not absolute_path:
        raise Exception("Shader / Materialのパスがありません。先にファイルを選択してください。")
    if not selected_property_names:
        raise Exception("プロパティを1つ以上選択してください。")

    _ensure_base_material_data()

    # 再通信して最新のプロパティ・Addressableパスを取得
    fetched = _request_material_properties_from_unity(absolute_path)
    addressable_path = fetched['addressable_path']

    selected_set = set(selected_property_names)
    properties = [p for p in fetched['properties'] if p.get('name') in selected_set]
    if not properties:
        raise Exception("選択したプロパティがシェーダーから見つかりませんでした。ファイルが変更された可能性があります。")

    data = load_material_cs_only_data()
    data['entries'] = [e for e in data['entries'] if e['class_name'] != class_name]
    data['entries'].append({
        'class_name': class_name,
        'desc': desc or '',
        'absolute_path': absolute_path,
        'addressable_path': addressable_path,
        'properties': properties
    })
    save_material_cs_only_data(data)

    code_str = _build_material_cs_code(class_name, desc or '', properties)

    class_dir = os.path.join(MATERIAL_CS_ONLY_DATA, class_name)
    os.makedirs(class_dir, exist_ok=True)
    cs_path = os.path.join(class_dir, f"{class_name}.cs")
    with open(cs_path, 'w', encoding='utf-8') as f:
        f.write(code_str)

    # 注意: generate_material_enum_csharp() / generate_material_bin() は
    #       意図的に呼び出さない（Enum・バイナリに含めないため）

def regenerate_material_cs_only(class_name):
    """
    CS-onlyエントリの再生成。保持しているabsolute_pathと選択済みプロパティ名を使って
    Unityへ再問い合わせしてからCSを再生成する。
    """
    data = load_material_cs_only_data()
    entry = next((e for e in data['entries'] if e['class_name'] == class_name), None)
    if entry is None:
        raise Exception(f"{class_name} のデータが見つかりません（CS-only）。")

    selected_names = [p['name'] for p in entry.get('properties', []) if p.get('name')]
    generate_material_cs_only(
        entry['class_name'],
        entry.get('desc', ''),
        entry.get('absolute_path'),
        selected_names
    )

def delete_material_cs_only(class_name):
    """
    CS-onlyエントリと生成済みC#ファイルを削除する（Enum・バイナリには元々含まれていない）
    """
    data = load_material_cs_only_data()
    data['entries'] = [e for e in data['entries'] if e['class_name'] != class_name]
    save_material_cs_only_data(data)

    class_dir = os.path.join(MATERIAL_CS_ONLY_DATA, class_name)
    if os.path.isdir(class_dir):
        shutil.rmtree(class_dir)
# -*- coding: utf-8 -*-
"""
pythonSrc/story_setting.py

シナリオイベントのサブイベント（sub）ごとに設定する「物語設定」を管理する。

物語設定は、シナリオ再生前に事前ロードしておきたい素材への参照
（Texture画像・SE・BGM・GameObjectエフェクト）と、可変性が高いため
ロードのタイミングが異なるVoice系列（voice_series_id）への参照を
まとめたデータ。

スロット命名規則:
  img_01 ~ img_99        : Texture（Spriteの場合は追加でSprite名も指定可）
  sound_se_01 ~ 99       : SE（Sound、type=SE）
  sound_bgm_01 ~ 99      : BGM（Sound、type=BGM）
  effect_01 ~ 99         : GameObject（エフェクト用）
  voice_series_id（単数） : Sound側の「大本」単位（Group+SubGroup）を1つ指定。
                            個別のVoiceそのものではなく、シリーズ全体を指す
                            （例: Sound_Scenario_TestScene）。

各スロットは「retain（保持）」フラグを持つ。trueの場合、シナリオ進行で
サブイベントが切り替わってGroup/SubGroupが変わっても、既にロード済みの
アセットを解放せず保持したままにする（次の物語設定での再ロードもしない）。
実際のロード/アンロード制御（各種~~Coreとの連携）は別途C#生成で対応する
（本モジュールはデータの保存・スロット定義・Enum生成のみを担当）。

実データは、対象サブイベントの既存JSON（scenario.SCENARIO_EVENT配下の
{eventId}/{eventId}.json の subgroups[subId]）に 'storySetting' キーとして
同居させる。既存の 'nodes'/'edges'（遷移グラフ）とは独立したキーであり、
本モジュールは遷移データの読み書きには一切関与しない
（app.py側の /transition 保存処理を、storySettingキーを保持するよう
 非破壊マージに修正している。詳細はapp.py側のコメント参照）。
"""
import json
import os
import struct
import pythonSrc.data_utils
import pythonSrc.constants

DATA_DIR = None

SLOT_DEFS = [
    {"prefix": "img", "enumName": "ImgSlot", "count": 99, "label": "画像(Texture)"},
    {"prefix": "sound_se", "enumName": "SoundSeSlot", "count": 99, "label": "SE"},
    {"prefix": "sound_bgm", "enumName": "SoundBgmSlot", "count": 99, "label": "BGM"},
    {"prefix": "effect", "enumName": "EffectSlot", "count": 99, "label": "エフェクト(GameObject)"},
]

_DEFAULT_STORY = {"slots": [], "voiceSeriesId": None}

VOICE_ROLE_NAME = "VoiceLine"


def init(data_dir):
    global DATA_DIR
    DATA_DIR = data_dir


def slot_names(prefix, count=99):
    return [f"{prefix}_{i:02d}" for i in range(1, count + 1)]


def _event_file_path(event_id):
    return os.path.join(DATA_DIR, "scenario_data", "scenario_event_data", event_id, f"{event_id}.json")



def read_story_setting(event_id, sub_id):
    path = _event_file_path(event_id)
    if not os.path.isfile(path):
        return dict(_DEFAULT_STORY)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    sub = data.get("subgroups", {}).get(sub_id, {})
    story = sub.get("storySetting")
    if not story:
        return dict(_DEFAULT_STORY)
    story.setdefault("slots", [])
    story.setdefault("voiceSeriesId", None)
    return story


def write_story_setting(event_id, sub_id, story_data):
    """既存のsubgroups[sub_id]内の 'nodes'/'edges'（遷移グラフ）には
    触れず、'storySetting' キーだけを差し替える（非破壊マージ）。"""
    path = _event_file_path(event_id)
    current = {}
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            current = json.load(f)
    current.setdefault("subgroups", {})
    existing_sub = current["subgroups"].setdefault(sub_id, {"nodes": [], "edges": []})
    existing_sub["storySetting"] = story_data
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(current, f, ensure_ascii=False, indent=2)


def generate_story_setting_enums():
    """img_01~99等の固定スロット名をC# enumとして書き出す。
    ユーザーが個々に管理する「Enum」ツール（class_data.py側）とは独立した、
    物語設定専用の固定スキャフォールディングなので、専用ファイルとして
    scenario_data直下に生成する。"""
    out_dir = os.path.join(DATA_DIR, "scenario_data")
    os.makedirs(out_dir, exist_ok=True)
    lines = ["namespace GameCore.Scenario.StorySetting", "{"]
    for slot_def in SLOT_DEFS:
        names = ", ".join(slot_names(slot_def["prefix"], slot_def["count"]))
        lines.append(f"    public enum {slot_def['enumName']} {{ None = 0, {names} }}")
    lines.append("}")
    lines.append("")
    out_path = os.path.join(out_dir, "StorySettingEnums.cs")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return out_path


_KIND_BYTE = {"img": 0, "se": 1, "bgm": 2, "effect": 3}


def _iter_story_settings():
    """DATA_DIR配下の全シナリオイベントを走査し、物語設定が設定されている
    (eventId, subId, story) の組を返す。"""
    scenario_event_dir = os.path.join(DATA_DIR, "scenario_data", "scenario_event_data")
    if not os.path.isdir(scenario_event_dir):
        return
    for event_id in sorted(os.listdir(scenario_event_dir)):
        event_json = os.path.join(scenario_event_dir, event_id, f"{event_id}.json")
        if not os.path.isfile(event_json):
            continue
        try:
            with open(event_json, "r", encoding="utf-8") as f:
                event_data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        for sub_id, sub in (event_data.get("subgroups") or {}).items():
            story = sub.get("storySetting")
            if story and (story.get("slots") or story.get("voiceSeriesId")):
                yield event_id, sub_id, story


def _write_cstr(buf, s):
    buf.extend((s or "").encode("utf-8"))
    buf.append(0)


def ensure_voice_role():
    """Voice専用の自動生成Role「VoiceLine」を用意する（無ければ作成、
    既にあれば何もしない）。

    通常のScenarioRoleと全く同じ保存形式
    （scenario_data/scenario_role/{name}/{name}.json）を使うため、
    ScenarioRoleGridの一覧にも通常のRoleと同様に表示され、通常の
    Transaction入力フローにそのまま組み込める。

    フィールドは1つだけ: voiceId（type='voice_ref'）。この型は通常の
    Roleエディタ画面では選択肢に出さない特殊型で、フロントエンド
    （BaseRoleInputForm.js）側だけがこの型を認識し、そのサブイベントの
    物語設定に設定されたvoice_series_id（Group+SubGroup）に属する
    SoundIDだけへ絞り込んだドロップダウンとして描画する。
    """
    role_dir = os.path.join(DATA_DIR, "scenario_data", "scenario_role", VOICE_ROLE_NAME)
    role_path = os.path.join(role_dir, f"{VOICE_ROLE_NAME}.json")
    if os.path.isfile(role_path):
        return role_path, False

    os.makedirs(role_dir, exist_ok=True)
    role_json = {
        "branchType": "General",
        "description": (
            "Voice専用の自動生成Role。voiceIdは、このRoleが使われているサブイベントの"
            "物語設定で指定されたvoice_series_id（Group+SubGroup）に属するSoundIDのみ"
            "選択可能（Transaction入力画面でカスケード絞り込みされる）。"
        ),
        "data": [
            {"name": "voiceId", "type": "voice_ref", "arraySize": 0, "description": "再生するVoiceのSoundID"},
        ],
    }
    with open(role_path, "w", encoding="utf-8") as f:
        json.dump(role_json, f, ensure_ascii=False, indent=2)

    # scenario_role_list.json にも登録し、通常のRole一覧(ScenarioRoleGrid)に表示されるようにする
    list_path = os.path.join(DATA_DIR, "scenario_data", "scenario_role", "scenario_role_list.json")
    roles = []
    if os.path.isfile(list_path):
        try:
            with open(list_path, "r", encoding="utf-8") as f:
                roles = json.load(f)
        except (json.JSONDecodeError, OSError):
            roles = []
    if not any(r.get("name") == VOICE_ROLE_NAME for r in roles):
        next_id = max([r.get("id", 0) for r in roles], default=0) + 1
        roles.append({
            "id": next_id, "name": VOICE_ROLE_NAME,
            "description": "Voice専用ロール（自動生成）", "branchType": "General",
        })
        os.makedirs(os.path.dirname(list_path), exist_ok=True)
        with open(list_path, "w", encoding="utf-8") as f:
            json.dump(roles, f, ensure_ascii=False, indent=2)

    return role_path, True


def find_item(data, group, subgroup, name):
    for item in data["groups"].get(group, {}).get("items", []):
        if item.get("subgroup") == subgroup and item.get("name", "").lower() == name.lower():
            return item
    return None

def find_index(data, group_name, subgroup, name):
    index = 0

    for current_group_name, group in data["groups"].items():
        # 指定したグループだけを見る
        if current_group_name != group_name:
            continue

        for item in group.get("items", []):
            if (
                item.get("subgroup") == subgroup
                and item.get("name", "").lower() == name.lower()
            ):
                return index + 1

            index += 1

    return None

def find_group_index(data, group_name):
    for index, name in enumerate(data["groups"], start=1):
        if name == group_name:
            return index

    return None


def _resolve_id(kind,id_group,id_subgroup, id_name):
    """kind ('img'|'se'|'bgm'|'effect') の素材ID名から
    TextureID/SoundID/GameObjectIDの整数値を返す。"""
    
    path = ""
    if kind == "img":
        path = os.path.join(
        DATA_DIR,
        pythonSrc.constants.ASSETS_DATA,
        pythonSrc.constants.TEXTURE_DATA,
        "assets_texture.json"
    )

    elif kind in ("se", "bgm"):
        path = os.path.join(
        DATA_DIR,
        pythonSrc.constants.ASSETS_DATA,
        pythonSrc.constants.SOUND_DATA,
        "assets_sound.json"
    )

    elif kind == "effect":
        path = os.path.join(
        DATA_DIR,
        pythonSrc.constants.ASSETS_DATA,
        pythonSrc.constants.GAMEOBJECT_DATA,
        "assets_gameobject.json"
    )
    else:
        raise NotImplementedError(
        "class_data.py側のEnum管理から、素材ID名→整数値を引く実装が必要です"
    )
        
    with open(path,"r",encoding="utf-8") as f:
        data = json.load(f)
        
    item_index = find_index(data,id_group,id_subgroup,id_name)
    return item_index
    
        
    
    
    



def _resolve_group(kind, group_name):
    """kindの素材Group名からTextureGroup/SoundGroup/GameObjectGroupの整数値を返す。"""
    
    path = ""
    if kind == "img":
        path = os.path.join(
        DATA_DIR,
        pythonSrc.constants.ASSETS_DATA,
        pythonSrc.constants.TEXTURE_DATA,
        "assets_texture.json"
    )

    elif kind in ("se", "bgm"):
        path = os.path.join(
        DATA_DIR,
        pythonSrc.constants.ASSETS_DATA,
        pythonSrc.constants.SOUND_DATA,
        "assets_sound.json"
    )

    elif kind == "effect":
        path = os.path.join(
        DATA_DIR,
        pythonSrc.constants.ASSETS_DATA,
        pythonSrc.constants.GAMEOBJECT_DATA,
        "assets_gameobject.json"
    )
    else:
        raise NotImplementedError(
        "class_data.py側のEnum管理から、Group名→整数値を引く実装が必要です"
    )
        
    with open(path,"r",encoding="utf-8") as f:
        data = json.load(f)
        
    item_index = find_group_index(data,group_name)
    return item_index


def get_value(data, property_name):
    for item in data:
        if item.get("property") == property_name:
            return item.get("value")

    return 0
def _resolve_sprite_id(sprite_group,sprite_subgroup,sprite_name,sprite_details_name):
    
    name = f"{sprite_group}_{sprite_subgroup}_{sprite_name}"
    path = os.path.join(DATA_DIR,pythonSrc.constants.ENUM,name,f"{name}.json")
    
    with open(path,"r",encoding="utf-8") as f:
        data = json.load(f)
        
    return get_value(data,sprite_details_name)


def _resolve_slot_key(kind, slot_name):
    """スロット名(例: 'img_01')から Story_ImgID/Story_SoundID/Story_GameobjectID の
    整数値を返す。generate_story_setting_enumsで出力する順序と一致させる必要がある。"""
    if kind == "img":
        names = slot_names("img", 99)
    elif kind in ("se", "bgm"):
        names = slot_names("sound_se", 99) + slot_names("sound_bgm", 99)
    elif kind == "effect":
        names = slot_names("effect", 99)
    else:
        raise ValueError(f"unknown kind: {kind}")
    # None=0始まりなので+1
    return names.index(slot_name) + 1


def generate_story_setting_bin():
    """全サブイベントの物語設定を、(eventId, subId)単位でオフセット
    インデックス化したバイナリへ書き出す。

    エントリ本体のレイアウトはStorySettingBinaryReader.ReadEntryChunkBodyと
    完全一致させる必要がある:
      img_dict:        count(int), [key_id(int), id(int), group_id(int), spriteID(int), retain(byte)] * count
      sound_se_dict:    count(int), [key_id(int), id(int), group_id(int), retain(byte)] * count
      sound_bgm_dict:   count(int), [key_id(int), id(int), group_id(int), retain(byte)] * count
      gameobject_dict:  count(int), [key_id(int), id(int), group_id(int), retain(byte)] * count
      hasVoice(byte), [SoundID(int)] if hasVoice
    ID/Group/キーはすべてenumの生の整数値（Unsafe.As再解釈のため、文字列ではなくint）。
    0は「未設定」として読み飛ばされる（ReadBinary側の`if (x == 0) continue`）ので、
    有効な素材IDには0を割り当てないこと。
    """
    entries = list(_iter_story_settings())

    body_chunks = []
    for _event_id, _sub_id, story in entries:
        chunk = bytearray()
        slots = story.get("slots", [])

        by_kind = {"img": [], "se": [], "bgm": [], "effect": []}
        for slot in slots:
            by_kind.setdefault(slot.get("kind"), []).append(slot)

        # img
        chunk += struct.pack("i", len(by_kind["img"]))
        for slot in by_kind["img"]:
            chunk += struct.pack("i", _resolve_slot_key("img", slot["slot"]))
            chunk += struct.pack("i", _resolve_id("img",slot["group"],slot["subGroup"],slot["id"]))
            chunk += struct.pack("i", _resolve_group("img", slot["group"]))
            chunk += struct.pack("i", _resolve_sprite_id(slot["group"],slot["subGroup"],slot["id"],slot.get("spriteName") or ""))
            chunk += struct.pack("B", 1 if slot.get("retain") else 0)

        # sound_se / sound_bgm
        for kind in ("se", "bgm"):
            chunk += struct.pack("i", len(by_kind[kind]))
            for slot in by_kind[kind]:
                chunk += struct.pack("i", _resolve_slot_key(kind, slot["slot"]))
                chunk += struct.pack("i", _resolve_id(kind, slot["group"],slot["subGroup"],slot["id"]))
                chunk += struct.pack("i", _resolve_group(kind, slot["group"]))
                chunk += struct.pack("B", 1 if slot.get("retain") else 0)

        # effect (gameobject)
        chunk += struct.pack("i", len(by_kind["effect"]))
        for slot in by_kind["effect"]:
            chunk += struct.pack("i", _resolve_slot_key("effect", slot["slot"]))
            chunk += struct.pack("i", _resolve_id("effect", slot["group"],slot["subGroup"],slot["id"]))
            chunk += struct.pack("i", _resolve_group("effect", slot["group"]))
            chunk += struct.pack("B", 1 if slot.get("retain") else 0)

        # voice: C#側は SoundID(int) のみ。groupやretainは持たない。
        voice = story.get("voiceSeriesId")
        if voice and voice.get("id"):
            chunk += struct.pack("B", 1)
            chunk += struct.pack("i", _resolve_id("se", voice["id"]))
        else:
            chunk += struct.pack("B", 0)

        body_chunks.append(bytes(chunk))

    header_entries_bytes = []
    header_size = 4
    for event_id, sub_id, _story in entries:
        eb = bytearray()
        _write_cstr(eb, event_id)
        _write_cstr(eb, sub_id)
        eb += struct.pack("i", 0)
        header_entries_bytes.append(eb)
        header_size += len(eb)

    final_header = bytearray()
    final_header += struct.pack("i", len(entries))
    running_offset = header_size
    for i, (event_id, sub_id, _story) in enumerate(entries):
        _write_cstr(final_header, event_id)
        _write_cstr(final_header, sub_id)
        final_header += struct.pack("i", running_offset)
        running_offset += len(body_chunks[i])

    out_path = os.path.join(DATA_DIR, "scenario_data", "story_settings.bytes")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(final_header)
        for chunk in body_chunks:
            f.write(chunk)

    return out_path, len(entries)


def generate_story_setting_csharp():
    """StorySettingDatabase.cs（データ構造＋バイナリリーダー、サウンドバンクと
    同じ遅延チャンク読み込み方式）と StorySettingCore.cs（各種~~Core経由での
    プリロード／解放オーケストレーター）を生成する。"""
    out_dir = os.path.join(DATA_DIR, "scenario_data")
    os.makedirs(out_dir, exist_ok=True)

    database_code = '''
using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.CompilerServices;
using System.Text;
using Cysharp.Threading.Tasks;
using GameCore.Enums;
using GameCore.Gameobject;
using GameCore.Sound;
using GameCore.Texture;
using UnityEngine;
using UnityEngine.AddressableAssets;
using UnityEngine.Rendering.Universal;
using UnityEngine.ResourceManagement.AsyncOperations;

namespace GameCore.Scenario.StorySetting
{
    public class StorySettingSlotDetailsData<T,TGroup> where T : struct, Enum where TGroup : struct,Enum
    {
        protected T id;
        public T ID => id;

        protected TGroup group_id;
        public TGroup GroupID => group_id;

        protected bool retain;
        public bool Retain => retain;

        public StorySettingSlotDetailsData(T value_id, TGroup value_group_id,bool value_retain)
        {
            id = value_id;
            group_id = value_group_id;
            retain = value_retain;
        }
    }
    public class StorySettingSlotTextureDetailsData : StorySettingSlotDetailsData<TextureID,TextureGroup>
    {
        protected int sptiteID;
        public int SpriteID => sptiteID;
        public StorySettingSlotTextureDetailsData(int value_sprite_id, TextureID value_id, TextureGroup value_group_id,bool value_retain) : base(value_id, value_group_id,value_retain)
        {
            sptiteID = value_sprite_id;
        }
    }

    public class StorySettingSlotData
    {
        Dictionary<Story_ImgID, StorySettingSlotTextureDetailsData> texture_setting_id;
        public Dictionary<Story_ImgID, StorySettingSlotTextureDetailsData> TextureSettingData => texture_setting_id;

        public StorySettingSlotTextureDetailsData TextureSetting(Story_ImgID id)
        {
            if(texture_setting_id.TryGetValue(id,out var result))
            {
                return result;
            }
            return null;
        }

        Dictionary<Story_SoundSE_ID, StorySettingSlotDetailsData<SoundID,SoundGroup>> sound_se_setting_id;
        public Dictionary<Story_SoundSE_ID, StorySettingSlotDetailsData<SoundID,SoundGroup>> SoundSESettingData => sound_se_setting_id;
        public Dictionary<Story_SoundSE_ID, StorySettingSlotDetailsData<SoundID,SoundGroup>> SoundSESetting(Story_SoundSE_ID id)
        {
            if(sound_se_setting_id.TryGetValue(id,out var result))
            {
                return result;
            }
            return null;
        }
        Dictionary<Story_SoundBGM_ID, StorySettingSlotDetailsData<SoundID,SoundGroup>> sound_bgm_setting_id;
        public Dictionary<Story_SoundBGM_ID, StorySettingSlotDetailsData<SoundID,SoundGroup>> SoundBGMSettingData => sound_bgm_setting_id;
        public Dictionary<Story_SoundBGM_ID, StorySettingSlotDetailsData<SoundID,SoundGroup>> SoundBGMSetting(Story_SoundBGM_ID id)
        {
            if(sound_bgm_setting_id.TryGetValue(id,out var result))
            {
                return result;
            }
            return null;
        }
        Dictionary<Story_GameobjectID, StorySettingSlotDetailsData<GameObjectID,GameObjectGroup>> gameobject_setting_id;
        public Dictionary<Story_GameobjectID, StorySettingSlotDetailsData<GameObjectID,GameObjectGroup>> GameobjectSettingData => gameobject_setting_id;
        public Dictionary<Story_GameobjectID, StorySettingSlotDetailsData<GameObjectID,GameObjectGroup>> GameobjectSetting(Story_SoundID id)
        {
            if(gameobject_setting_id.TryGetValue(id,out var result))
            {
                return result;
            }
            return null;
        }


        public StorySettingSlotData(
           Dictionary<Story_ImgID, StorySettingSlotTextureDetailsData> texture_setting_id,
           Dictionary<Story_SoundSE_ID, StorySettingSlotDetailsData<SoundID,SoundGroup>> sound_se_setting_id,
           Dictionary<Story_SoundBGM_ID, StorySettingSlotDetailsData<SoundID,SoundGroup>> sound_bgm_setting_id,
           Dictionary<Story_GameobjectID, StorySettingSlotDetailsData<GameObjectID,GameObjectGroup>> gameobject_setting_id)
        {
            this.texture_setting_id = texture_setting_id;
            this.sound_se_setting_id = sound_se_setting_id;
            this.sound_bgm_setting_id = sound_bgm_setting_id;
            this.gameobject_setting_id = gameobject_setting_id;
        }
    }

    public class VoiceSeriesRefData
    {
        public bool HasValue;
        public SoundID SeriseSoundID;
    }

    public class StorySettingEntry
    {
        public List<StorySettingSlotData> Slots = new List<StorySettingSlotData>();
        public VoiceSeriesRefData VoiceSeries;
    }

    /// <summary>
    /// サウンドバンクと同じ「インデックスだけ先に読み、実データ(チャンク)は
    /// 必要になったタイミングで個別に読み込む」方式の物語設定データベース。
    /// キーは (eventId, subId)。
    /// </summary>
    public class StorySettingDatabase
    {
        private readonly Dictionary<(string eventId, string subId), int> chunkOffsets = new();
        private readonly Dictionary<(string eventId, string subId), StorySettingEntry> loadedEntries = new();
        private byte[] sourceBytes;
        private string sourceFilePath;

        internal void SetSource(byte[] bytes, string filePath)
        {
            sourceBytes = bytes;
            sourceFilePath = filePath;
        }

        internal void SetChunkOffset(string eventId, string subId, int offset)
        {
            chunkOffsets[(eventId, subId)] = offset;
        }

        public bool HasEntry(string eventId, string subId) => chunkOffsets.ContainsKey((eventId, subId));

        public async UniTask<StorySettingEntry> EnsureEntryLoadedAsync(string eventId, string subId)
        {
            var key = (eventId, subId);
            if (loadedEntries.TryGetValue(key, out var cached)) return cached;
            if (!chunkOffsets.TryGetValue(key, out int offset)) return null;

            StorySettingEntry entry = await UniTask.RunOnThreadPool(
                () => StorySettingBinaryReader.ReadEntryChunk(sourceBytes, sourceFilePath, offset));
            loadedEntries[key] = entry;
            return entry;
        }

        public void UnloadEntry(string eventId, string subId)
        {
            loadedEntries.Remove((eventId, subId));
        }
    }

    public static class StorySettingBinaryReader
    {
        public static async UniTask<StorySettingDatabase> LoadStorySettingDatabaseFromBinaryAsync(string filePath, bool addressable = false)
        {
            if (!addressable)
            {
                if (!File.Exists(filePath))
                {
                    Debug.LogError($"Binary file not found: {filePath}");
                    return null;
                }
                return await UniTask.RunOnThreadPool(() =>
                {
                    using (BinaryReader reader = new BinaryReader(File.Open(filePath, FileMode.Open)))
                    {
                        var database = ReadIndex(reader);
                        database?.SetSource(null, filePath);
                        return database;
                    }
                });
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

                byte[] rawBytes = handle.Result.bytes;
                StorySettingDatabase database;
                using (MemoryStream ms = new MemoryStream(rawBytes))
                using (BinaryReader reader = new BinaryReader(ms))
                {
                    database = ReadIndex(reader);
                }
                database?.SetSource(rawBytes, null);
                Addressables.Release(handle);
                return database;
            }
        }

        private static StorySettingDatabase ReadIndex(BinaryReader reader)
        {
            var database = new StorySettingDatabase();
            int entryCount = reader.ReadInt32();
            for (int i = 0; i < entryCount; i++)
            {
                string eventId = ReadNullTerminatedString(reader);
                string subId = ReadNullTerminatedString(reader);
                int offset = reader.ReadInt32();
                database.SetChunkOffset(eventId, subId, offset);
            }
            return database;
        }

        internal static StorySettingEntry ReadEntryChunk(byte[] rawBytes, string filePath, int offset)
        {
            if (rawBytes != null)
            {
                using (MemoryStream ms = new MemoryStream(rawBytes))
                using (BinaryReader reader = new BinaryReader(ms))
                {
                    return ReadEntryChunkBody(reader, offset);
                }
            }
            using (BinaryReader reader = new BinaryReader(File.Open(filePath, FileMode.Open)))
            {
                return ReadEntryChunkBody(reader, offset);
            }
        }

        private static StorySettingEntry ReadEntryChunkBody(BinaryReader reader, int offset)
        {
            reader.BaseStream.Seek(offset, SeekOrigin.Begin);
            var entry = new StorySettingEntry();


            var img_dict = ReadBinary(reader);
            var sound_se_dict = ReadBinary<Story_SoundSE_ID, SoundID,SoundGroup>(reader);
            var sound_bgm_dict = ReadBinary<Story_SoundBGM_ID, SoundID,SoundGroup>(reader);
            var gameobject_dict = ReadBinary<Story_GameobjectID, GameObjectID,GameObjectGroup>(reader);
            entry.Slots.Add(new StorySettingSlotData(img_dict, sound_se_dict, sound_bgm_dict, gameobject_dict));


            bool hasVoice = reader.ReadByte() != 0;
            if (hasVoice)
            {
                SoundID id = Convert<SoundID>(reader.ReadInt32());
                entry.VoiceSeries = new VoiceSeriesRefData{ HasValue = hasVoice,SeriseSoundID = id };
            }

            return entry;
        }

        private static string ReadNullTerminatedString(BinaryReader reader)
        {
            List<byte> bytes = new List<byte>();
            byte b;
            while ((b = reader.ReadByte()) != 0)
            {
                bytes.Add(b);
            }
            return Encoding.UTF8.GetString(bytes.ToArray());
        }

        public static Dictionary<Story_ImgID, StorySettingSlotTextureDetailsData> ReadBinary(BinaryReader reader)
        {
            var result = new Dictionary<Story_ImgID, StorySettingSlotTextureDetailsData>();

            //サイズ
            int count = reader.ReadInt32();

            for (int i = 0; i < count; i++)
            {
                int key_id = reader.ReadInt32();
                int id = reader.ReadInt32();
                int group_id = reader.ReadInt32();

                
                int spriteID = reader.ReadInt32();


                TextureID t = Convert<TextureID>(id);
                TextureGroup group = Convert<TextureGroup>(group_id);

                Story_ImgID tid = Convert<Story_ImgID>(key_id);

                bool retain = reader.ReadByte() != 0;

                StorySettingSlotTextureDetailsData add_data = new StorySettingSlotTextureDetailsData(spriteID,t, group,retain);

                result.Add(tid, add_data);
            }

            return result;
        }

        public static Dictionary<TID, StorySettingSlotDetailsData<TReturn,TGroup>> ReadBinary<TID, TReturn,TGroup>(BinaryReader reader) where TID : struct, Enum where TReturn : struct, Enum where TGroup : struct,Enum
        {
            var result = new Dictionary<TID, StorySettingSlotDetailsData<TReturn,TGroup>>();

            //サイズ
            int count = reader.ReadInt32();

            for (int i = 0; i < count; i++)
            {
                int key_id = reader.ReadInt32();
                int id = reader.ReadInt32();
                int group_id = reader.ReadInt32();


                TReturn t = Convert<TReturn>(id);

                TID tid = Convert<TID>(key_id);
                TGroup group = Convert<TGroup>(group_id);

                bool retain = reader.ReadByte() != 0;

                StorySettingSlotDetailsData<TReturn,TGroup> add_data = new StorySettingSlotDetailsData<TReturn,TGroup>(t, group,retain);

                result.Add(tid, add_data);
            }

            return result;
        }
        public static TReturn Convert<TReturn>(int id)
            where TReturn : struct, Enum
        {
            return Unsafe.As<int, TReturn>(ref id);
        }

    }
}



'''
    with open(os.path.join(out_dir, "StorySettingDatabase.cs"), "w", encoding="utf-8") as f:
        f.write(database_code)

    core_code = '''
uusing System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using Cysharp.Threading.Tasks;
using UnityEngine;
using GameCore;
using GameCore.Sound;
using GameCore.Texture;
using GameCore.Gameobject;
using AddressableSystem;
using Cysharp.Threading.Tasks.Triggers;
using GameCore.Enums;

namespace GameCore.Scenario.StorySetting
{
    /// <summary>
    /// シナリオのサブイベントに紐づく「物語設定」を、対応する各種~~Core
    /// （TextureCore/SoundCore/GameObjectCore）経由で事前ロード・解放する。
    ///
    /// - LoadForSubEventAsync: サブイベントへ遷移する際に呼ぶ。前回ロードした
    ///   スロットのうち、今回引き継がれない（かつRetainされていない）ものは
    ///   解放し、新しいスロットをロードする。Retainされたスロットは、次の
    ///   物語設定に同じ内容が無くても解放せず、かつ再ロードもしない。
    /// - UnloadAll: シナリオそのものが終了したときに呼ぶ。Retainの有無に
    ///   関わらず、現在保持している全スロットを解放する（Retainはシナリオ内の
    ///   遷移をまたぐためだけの仕組みであり、シナリオ終了後まで保持し続ける
    ///   機能ではない）。
    ///
    /// Voiceは可変性が高く全件事前ロードの対象にしないため、ここでは
    /// 素材そのもののロードは行わない（voice_series_idの実際のロードは、
    /// 専用のRole/Transaction機構側で個別に行う想定）。
    /// </summary>
    [AddComponentMenu("GameCore/Story Setting Core")]
    public partial class StorySettingCore : BaseSingleton<StorySettingCore>
    {
        private StorySettingDatabase database;
        private bool isLoadDatabase;
        private CancellationTokenSource manualCancelSource;
        private CancellationToken combinedToken;

        // 現在ロード中のスロット（Retain中のものも含む）
        private readonly List<StorySettingSlotData> currentSlots = new();
        private VoiceSeriesRefData currentVoiceSeries;
        public VoiceSeriesRefData CurrentVoiceSeries => currentVoiceSeries;

        public override void AwakeSingleton()
        {
            base.AwakeSingleton();
            DontDestroyOnLoad(gameObject);
            manualCancelSource = new CancellationTokenSource();
            combinedToken = CancellationTokenSource.CreateLinkedTokenSource(this.GetCancellationTokenOnDestroy(), manualCancelSource.Token).Token;
            LoadDatabaseAsync().Forget();
        }

        private async UniTask LoadDatabaseAsync()
        {
            string path = SupportFiles.ADDRESSABLE_CHECK ? SupportFiles.ALL_STORY_SETTING_BIN_FILE : SupportFiles.ALL_STORY_SETTING_BIN;
            database = await StorySettingBinaryReader.LoadStorySettingDatabaseFromBinaryAsync(path, SupportFiles.ADDRESSABLE_CHECK);
            if (database == null)
                Debug.LogError("[StorySettingCore] Failed to load StorySettingDatabase.");
            isLoadDatabase = true;
        }

        /// <summary>
        /// 指定したサブイベントの物語設定を読み込み、必要な素材を各種~~Core
        /// 経由で事前ロードする。前回ロード分との差分だけをロード/アンロード
        /// する（Retainされたスロットは維持される）。
        /// </summary>
        public async UniTask LoadForSubEventAsync(string eventId, string subId, GroupCategory category = GroupCategory.Game)
        {
            while (!isLoadDatabase)
                await UniTask.Yield(combinedToken);

            var entry = await database.EnsureEntryLoadedAsync(eventId, subId);
            var nextSlots = entry?.Slots ?? new List<StorySettingSlotData>();
            var nextVoiceSeries = entry?.VoiceSeries ?? default;

            // Retain対象で、かつ次の物語設定に同一内容が無いスロットはそのまま維持する
            var slotsToKeep = currentSlots
                .Where(s => IsFullyRetained(s) && !nextSlots.Any(n => SameAsset(n, s)))
                .ToList();

            // Retain対象でなく、かつ次の物語設定に引き継がれないスロットは解放する
            var slotsToUnload = currentSlots
                .Where(s => !IsFullyRetained(s) && !nextSlots.Any(n => SameAsset(n, s)))
                .ToList();

            // 現在ロード済みの内容に存在しない、新規にロードすべきスロット
            var slotsToLoad = nextSlots
                .Where(n => !currentSlots.Any(s => SameAsset(n, s)))
                .ToList();

            foreach (var slot in slotsToUnload)
                UnloadSlot(slot);

            var loadTasks = new List<UniTask>();
            foreach (var slot in slotsToLoad)
                loadTasks.Add(LoadSlotAsync(slot, category));

            await UniTask.WhenAll(loadTasks);

            // slotsToKeep は定義上nextSlotsと内容が重複しないので、単純結合でOK
            currentSlots.Clear();
            currentSlots.AddRange(slotsToKeep);
            currentSlots.AddRange(nextSlots);

            // Voiceは事前ロード対象外（専用機構が個別にロードする）なので、参照の引き継ぎのみ行う
            currentVoiceSeries = nextVoiceSeries;

            database.UnloadEntry(eventId, subId);
        }

        /// <summary>
        /// スロット内の全アイテムがRetain対象かどうか。
        /// 一つでもRetain対象でないアイテムがあればfalse。
        /// </summary>
        private static bool IsFullyRetained(StorySettingSlotData slot)
        {
            if (slot.TextureSettingData != null && slot.TextureSettingData.Values.Any(v => !v.Retain)) return false;
            if (slot.SoundSESettingData != null && slot.SoundSESettingData.Values.Any(v => !v.Retain)) return false;
            if (slot.SoundBGMSettingData != null && slot.SoundBGMSettingData.Values.Any(v => !v.Retain)) return false;
            if (slot.GameobjectSettingData != null && slot.GameobjectSettingData.Values.Any(v => !v.Retain)) return false;
            return true;
        }

        /// <summary>
        /// 2つのスロットが参照するアセット内容が完全一致するかどうか。
        /// </summary>
        private static bool SameAsset(StorySettingSlotData a, StorySettingSlotData b)
        {
            if (a == null || b == null) return false;
            if (ReferenceEquals(a, b)) return true;

            return TextureDictEquals(a.TextureSettingData, b.TextureSettingData)
                && DetailsDictEquals(a.SoundSESettingData, b.SoundSESettingData)
                && DetailsDictEquals(a.SoundBGMSettingData, b.SoundBGMSettingData)
                && DetailsDictEquals(a.GameobjectSettingData, b.GameobjectSettingData);
        }

        private static bool TextureDictEquals(
            Dictionary<Story_ImgID, StorySettingSlotTextureDetailsData> a,
            Dictionary<Story_ImgID, StorySettingSlotTextureDetailsData> b)
        {
            int countA = a?.Count ?? 0;
            int countB = b?.Count ?? 0;
            if (countA != countB) return false;
            if (countA == 0) return true;

            foreach (var kv in a)
            {
                if (!b.TryGetValue(kv.Key, out var other)) return false;
                if (!kv.Value.ID.Equals(other.ID)) return false;
                if (!kv.Value.GroupID.Equals(other.GroupID)) return false;
                if (kv.Value.SpriteID != other.SpriteID) return false;
            }
            return true;
        }

        private static bool DetailsDictEquals<TKey, TID, TGroup>(
            Dictionary<TKey, StorySettingSlotDetailsData<TID, TGroup>> a,
            Dictionary<TKey, StorySettingSlotDetailsData<TID, TGroup>> b)
            where TID : struct, Enum
            where TGroup : struct, Enum
        {
            int countA = a?.Count ?? 0;
            int countB = b?.Count ?? 0;
            if (countA != countB) return false;
            if (countA == 0) return true;

            foreach (var kv in a)
            {
                if (!b.TryGetValue(kv.Key, out var other)) return false;
                if (!kv.Value.ID.Equals(other.ID)) return false;
                if (!kv.Value.GroupID.Equals(other.GroupID)) return false;
            }
            return true;
        }

        private async UniTask LoadSlotAsync(StorySettingSlotData slot, GroupCategory category)
        {
            try
            {
                foreach (var data in slot.TextureSettingData)
                {
                    await TextureCore.Instance.LoadSingleAsync(data.Value.GroupID,
                                                               data.Value.ID,
                                                               category);
                }
                foreach (var data in slot.SoundSESettingData)
                {
                    await SoundCore.Instance.LoadSingleAsync(data.Value.GroupID,
                                                             data.Value.ID,
                                                             category);
                }
                foreach (var data in slot.SoundBGMSettingData)
                {
                    await SoundCore.Instance.LoadSingleAsync(data.Value.GroupID,
                                                             data.Value.ID,
                                                              category);
                }
                foreach (var data in slot.GameobjectSettingData)
                {
                    await GameObjectCore.Instance.LoadSingleAsync(data.Value.GroupID,
                                                                 data.Value.ID,
                                                                category);
                }
            }
            catch (Exception ex)
            {
                Debug.LogError($"[StorySettingCore] Failed to load slot: {ex}");
            }
        }

        private void UnloadSlot(StorySettingSlotData slot)
        {
            try
            {
                foreach (var data in slot.TextureSettingData)
                {
                    TextureCore.Instance.UnloadSingle(data.Value.GroupID,
                                                               data.Value.ID
                                                               );
                }
                foreach (var data in slot.SoundSESettingData)
                {
                    SoundCore.Instance.UnloadSingle(data.Value.GroupID,
                                                             data.Value.ID
                                                             );
                }
                foreach (var data in slot.SoundBGMSettingData)
                {
                    SoundCore.Instance.UnloadSingle(data.Value.GroupID,
                                                             data.Value.ID
                                                              );
                }
                foreach (var data in slot.GameobjectSettingData)
                {
                    GameObjectCore.Instance.UnloadSingle(data.Value.GroupID,
                                                                 data.Value.ID
                                                                );
                }
            }
            catch (Exception ex)
            {
                Debug.LogError($"[StorySettingCore] Failed to unload slot: {ex}");
            }
        }

        /// <summary>
        /// シナリオそのものが終了したときに呼ぶ。Retainの有無に関わらず、
        /// 現在保持している全スロットを解放する。
        /// </summary>
        public void UnloadAll()
        {
            foreach (var slot in currentSlots)
                UnloadSlot(slot);
            currentSlots.Clear();
            currentVoiceSeries = default;
        }
    }
}
'''
    core_path = os.path.join(out_dir, "StorySettingCore.cs")
    if not os.path.exists(core_path):
        with open(core_path, "w", encoding="utf-8") as f:
            f.write(core_code)

    return os.path.join(out_dir, "StorySettingDatabase.cs"), core_path


def register(app, data_dir):
    from flask import jsonify, request
    init(data_dir)
    inti_class_data_id()

    @app.route("/api/story-setting/slot-defs", methods=["GET"])
    def story_setting_slot_defs():
        return jsonify([
            {
                "prefix": s["prefix"], "enumName": s["enumName"], "count": s["count"],
                "label": s["label"], "names": slot_names(s["prefix"], s["count"]),
            }
            for s in SLOT_DEFS
        ])

    @app.route("/api/story-setting/generate-enums", methods=["POST"])
    def story_setting_generate_enums():
        try:
            path = generate_story_setting_enums()
            return jsonify({"message": f"物語設定用Enumを生成しました: {path}"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/story-setting/generate", methods=["POST"])
    def story_setting_generate_all():
        """Enum・C#（Database/Core）・バイナリを一括生成する。"""
        try:
            enum_path = generate_story_setting_enums()
            db_path, core_path = generate_story_setting_csharp()
            bin_path, entry_count = generate_story_setting_bin()
            return jsonify({
                "message": f"物語設定を生成しました（対象サブイベント: {entry_count}件）",
                "files": [enum_path, db_path, core_path, bin_path],
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/story-setting/generate-voice-role", methods=["POST"])
    def story_setting_generate_voice_role():
        try:
            path, created = ensure_voice_role()
            if created:
                message = f"Voice専用Role「{VOICE_ROLE_NAME}」を作成しました: {path}"
            else:
                message = f"Voice専用Role「{VOICE_ROLE_NAME}」は既に存在します: {path}"
            return jsonify({"message": message, "created": created})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/scenario-event/<eventId>/sub/<subId>/story", methods=["GET", "POST"])
    def scenario_story_setting(eventId, subId):
        if not eventId or eventId == "undefined" or not subId or subId == "undefined":
            return jsonify({"error": "Invalid eventId or subId"}), 400
        if request.method == "GET":
            try:
                return jsonify(read_story_setting(eventId, subId))
            except Exception as e:
                return jsonify({"error": str(e)}), 500
        else:
            try:
                write_story_setting(eventId, subId, request.get_json() or {})
                return jsonify({"message": "物語設定を保存しました"})
            except Exception as e:
                return jsonify({"error": str(e)}), 500
            
            
def inti_class_data_id():
    init_class_data_id_name("Img")
    init_class_data_id_name("SoundSE")
    init_class_data_id_name("SoundBGM")
    init_class_data_id_name("Gameobject")


def init_class_data_id_name(name):
    class_id_name = f"Story_{name}ID"
    
    result = pythonSrc.data_utils.add_json_enum_parent(class_id_name)

    
    data = []

    for i in range(1, 100):
        data.append({
            "id": i,
            "property": f"{name}_{i:02d}",
            "value": i,
            "description": f"{name}_{i:02d}"
        })
        
    os.makedirs(
        os.path.join(DATA_DIR, pythonSrc.constants.ENUM, class_id_name),
        exist_ok=True
    )
    
    with open(os.path.join(DATA_DIR, pythonSrc.constants.ENUM,f"{class_id_name}", f"{class_id_name}.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
        
    lines = [
        "namespace GameCore.Enums",
        "{",
        f"    public enum {class_id_name}",
        "    {",
        "        None = 0, // デフォルト値",
    ]

    for item in data:
        lines.append(
            f'        {item["property"]} = {item["value"]}, // {item["description"]}'
        )

    max_value = max((item["value"] for item in data), default=0) + 1

    lines += [
        f"        Max = {max_value}",
        "    }",
        "}",
    ]
        
    with open(os.path.join(DATA_DIR, pythonSrc.constants.ENUM,f"{class_id_name}", f"{class_id_name}.cs"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        
    

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


def generate_story_setting_bin():
    """全サブイベントの物語設定を、(eventId, subId)単位でオフセット
    インデックス化したバイナリへ書き出す（story_settings.bytes）。

    Sound側のサウンドバンク/チャンクと同じ考え方: C#側は起動時に
    インデックス（(eventId, subId) → オフセット）だけを読み、各サブ
    イベントの物語設定本体は、実際にそのサブイベントへ遷移するタイミング
    （StorySettingCore.LoadForSubEventAsync）で初めて読み込む。
    """
    entries = list(_iter_story_settings())

    body_chunks = []
    for _event_id, _sub_id, story in entries:
        chunk = bytearray()
        slots = story.get("slots", [])
        chunk += struct.pack("i", len(slots))
        for slot in slots:
            kind_byte = _KIND_BYTE.get(slot.get("kind"), 0)
            chunk += struct.pack("B", kind_byte)
            _write_cstr(chunk, slot.get("slot"))
            _write_cstr(chunk, slot.get("group"))
            _write_cstr(chunk, slot.get("id"))
            _write_cstr(chunk, slot.get("spriteName") or "")
            chunk += struct.pack("B", 1 if slot.get("retain") else 0)

        voice = story.get("voiceSeriesId")
        if voice:
            chunk += struct.pack("B", 1)
            _write_cstr(chunk, voice.get("group"))
            _write_cstr(chunk, voice.get("subGroup"))
            chunk += struct.pack("B", 1 if voice.get("retain") else 0)
        else:
            chunk += struct.pack("B", 0)

        body_chunks.append(bytes(chunk))

    # ヘッダーサイズを先に確定させるため、まず(仮オフセット込みで)同じ長さの
    # ヘッダーエントリを組み立ててサイズを測り、それを起点に実オフセットを算出する
    # （文字列長は最終版と仮版で完全に一致するため、この2パスで正しく求まる）。
    header_entries_bytes = []
    header_size = 4  # entryCount分
    for event_id, sub_id, _story in entries:
        eb = bytearray()
        _write_cstr(eb, event_id)
        _write_cstr(eb, sub_id)
        eb += struct.pack("i", 0)  # placeholder
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

    database_code = '''using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using Cysharp.Threading.Tasks;
using UnityEngine;
using UnityEngine.AddressableAssets;
using UnityEngine.ResourceManagement.AsyncOperations;

namespace GameCore.Scenario.StorySetting
{
    public struct StorySettingSlotData
    {
        public byte Kind;         // 0=img, 1=se, 2=bgm, 3=effect
        public string SlotName;   // 例: "img_01"
        public string Group;
        public string Id;
        public string SpriteName; // imgのみ使用。それ以外は空文字
        public bool Retain;

        public StorySettingSlotData(byte kind, string slotName, string group, string id, string spriteName, bool retain)
        {
            Kind = kind; SlotName = slotName; Group = group; Id = id; SpriteName = spriteName; Retain = retain;
        }
    }

    public struct VoiceSeriesRefData
    {
        public bool HasValue;
        public string Group;
        public string SubGroup;
        public bool Retain;
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

            int slotCount = reader.ReadInt32();
            for (int i = 0; i < slotCount; i++)
            {
                byte kind = reader.ReadByte();
                string slotName = ReadNullTerminatedString(reader);
                string group = ReadNullTerminatedString(reader);
                string id = ReadNullTerminatedString(reader);
                string spriteName = ReadNullTerminatedString(reader);
                bool retain = reader.ReadByte() != 0;
                entry.Slots.Add(new StorySettingSlotData(kind, slotName, group, id, spriteName, retain));
            }

            bool hasVoice = reader.ReadByte() != 0;
            if (hasVoice)
            {
                string group = ReadNullTerminatedString(reader);
                string subGroup = ReadNullTerminatedString(reader);
                bool retain = reader.ReadByte() != 0;
                entry.VoiceSeries = new VoiceSeriesRefData { HasValue = true, Group = group, SubGroup = subGroup, Retain = retain };
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
    }
}
'''
    with open(os.path.join(out_dir, "StorySettingDatabase.cs"), "w", encoding="utf-8") as f:
        f.write(database_code)

    core_code = '''using System;
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
            combinedToken = CancellationTokenSource.CreateLinkedTokenSource(destroyToken, manualCancelSource.Token).Token;
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

            var slotsToKeep = currentSlots.Where(s => s.Retain).ToList();
            var slotsToUnload = currentSlots
                .Where(s => !s.Retain && !nextSlots.Any(n => SameAsset(n, s)))
                .ToList();
            var slotsToLoad = nextSlots
                .Where(n => !currentSlots.Any(s => SameAsset(n, s)))
                .ToList();

            foreach (var slot in slotsToUnload)
                UnloadSlot(slot);

            var loadTasks = new List<UniTask>();
            foreach (var slot in slotsToLoad)
                loadTasks.Add(LoadSlotAsync(slot, category));

            await UniTask.WhenAll(loadTasks);

            currentSlots.Clear();
            currentSlots.AddRange(slotsToKeep);
            currentSlots.AddRange(nextSlots.Where(n => !slotsToKeep.Any(s => SameAsset(n, s))));

            // Voice系列はデータ参照の引き継ぎのみ（実ロードは専用機構が担当）。
            if (!currentVoiceSeries.HasValue || !currentVoiceSeries.Retain)
                currentVoiceSeries = nextVoiceSeries;

            database.UnloadEntry(eventId, subId);
        }

        private static bool SameAsset(StorySettingSlotData a, StorySettingSlotData b)
            => a.Kind == b.Kind && a.Group == b.Group && a.Id == b.Id && a.SpriteName == b.SpriteName;

        private async UniTask LoadSlotAsync(StorySettingSlotData slot, GroupCategory category)
        {
            try
            {
                switch (slot.Kind)
                {
                    case 0: // img
                        {
                            var group = (TextureGroup)Enum.Parse(typeof(TextureGroup), slot.Group);
                            var id = (TextureID)Enum.Parse(typeof(TextureID), $"{slot.Group}_{slot.Id}");
                            await TextureCore.Instance.LoadSingleAsync(group, id, category);
                            break;
                        }
                    case 1: // se
                    case 2: // bgm
                        {
                            var group = (SoundGroup)Enum.Parse(typeof(SoundGroup), slot.Group);
                            var id = (SoundID)Enum.Parse(typeof(SoundID), $"{slot.Group}_{slot.Id}");
                            await SoundCore.Instance.LoadSingleAsync(group, id, category);
                            break;
                        }
                    case 3: // effect
                        {
                            var group = (GameObjectGroup)Enum.Parse(typeof(GameObjectGroup), slot.Group);
                            var id = (GameObjectID)Enum.Parse(typeof(GameObjectID), $"{slot.Group}_{slot.Id}");
                            await GameObjectCore.Instance.LoadSingleAsync(group, id, category);
                            break;
                        }
                }
            }
            catch (Exception ex)
            {
                Debug.LogError($"[StorySettingCore] Failed to load slot {slot.SlotName} ({slot.Group}/{slot.Id}): {ex.Message}");
            }
        }

        private void UnloadSlot(StorySettingSlotData slot)
        {
            try
            {
                switch (slot.Kind)
                {
                    case 0:
                        {
                            var group = (TextureGroup)Enum.Parse(typeof(TextureGroup), slot.Group);
                            var id = (TextureID)Enum.Parse(typeof(TextureID), $"{slot.Group}_{slot.Id}");
                            TextureCore.Instance.UnloadSingle(group, id);
                            break;
                        }
                    case 1:
                    case 2:
                        {
                            var group = (SoundGroup)Enum.Parse(typeof(SoundGroup), slot.Group);
                            var id = (SoundID)Enum.Parse(typeof(SoundID), $"{slot.Group}_{slot.Id}");
                            SoundCore.Instance.UnloadSingle(group, id);
                            break;
                        }
                    case 3:
                        {
                            var group = (GameObjectGroup)Enum.Parse(typeof(GameObjectGroup), slot.Group);
                            var id = (GameObjectID)Enum.Parse(typeof(GameObjectID), $"{slot.Group}_{slot.Id}");
                            GameObjectCore.Instance.UnloadSingle(group, id);
                            break;
                        }
                }
            }
            catch (Exception ex)
            {
                Debug.LogError($"[StorySettingCore] Failed to unload slot {slot.SlotName} ({slot.Group}/{slot.Id}): {ex.Message}");
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

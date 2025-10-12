from cmath import isfinite, isnan
import struct
import sys
import os
import json
from enum import Enum
# 追加 import
import glob
from venv import logger

# 実行可能ファイルのディレクトリを取得（PyInstaller対応）
if getattr(sys, 'frozen', False):
    # PyInstallerでビルドされた場合
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # デバッグ環境（VS Codeなど）
    # main-support/ の1つ上のディレクトリ（project/）を基準にする
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ディレクトリパスをプロジェクトルート基準に設定
STATIC_FOLDER = os.path.join(BASE_DIR, 'build')
DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "data"))

CLASS_DATA_ID = 'class-data-id'

SCENARIO_DATA = 'scenario-data'
SCENARIO_ROLE =  os.path.join(SCENARIO_DATA, 'scenario-role')
SCENARIO_CONDITIONS_DATA = os.path.join(SCENARIO_DATA, 'scenario-conditions-data')
SCENARIO_EVENT = os.path.join(SCENARIO_DATA, 'scenario-event-data')

def generate_scenario_folder(parent_path : str):
    if not os.path.exists(os.path.join(parent_path, SCENARIO_DATA)):
        os.makedirs(os.path.join(parent_path, SCENARIO_DATA))
    if not os.path.exists(os.path.join(parent_path, SCENARIO_ROLE)):
        os.makedirs(os.path.join(parent_path, SCENARIO_ROLE))
    if not os.path.exists(os.path.join(parent_path, SCENARIO_CONDITIONS_DATA)):
        os.makedirs(os.path.join(parent_path, SCENARIO_CONDITIONS_DATA))
    if not os.path.exists(os.path.join(parent_path, SCENARIO_EVENT)):
        os.makedirs(os.path.join(parent_path, SCENARIO_EVENT))

def generate_base_script_file(parent_path : str):
    if not os.path.exists(os.path.join(parent_path,SCENARIO_ROLE, "BaseScenearioRoleData.cs")):
        code_str = """
using System;
using System.Collections;
using UnityEngine;

namespace GameCore.Scenario
{
    public class BaseScenarioRoleData
    {
        public ScenarioRoleID RoleID { get; private set; }
        public int ScenarioGroupID { get; private set; }
        public int ScenarioSubGroupID { get; private set; }
        public int ScenarioSeekPos { get; set; } = -1;

        public virtual void ReadBinary(BinaryReader reader)
        {
            RoleID = (ScenarioRoleID)reader.ReadInt32();
            ScenarioGroupID = reader.ReadInt32();
            ScenarioSubGroupID = reader.ReadInt32();
        }
    }
}
"""
        with open(os.path.join(parent_path,SCENARIO_ROLE, "BaseScenearioRoleData.cs"), 'w', encoding='utf-8') as f:
            f.write(code_str)
    
    if not os.path.exists(os.path.join(parent_path,SCENARIO_ROLE, "BaseOrigintScenarioRoleAction.cs")):
        code_str = """
using System;
using System.Collections;
using UnityEngine;
using System.IO;
namespace GameCore.Scenario
{
    public  class BaseOrigintScenarioRoleAction
    {
        public bool IsCompleted { get; protected set; } = false;
        public bool IsStartUp { get; protected set; } = false;
        public bool IsRelease { get; protected set; } = false;
        public virtual void ReadBinary(BinaryReader reader)
        {
            
        }
        public virtual void OnInitialize()
        {
            IsCompleted = false;
        }
        public virtual void OnExecute()
        {
            // Implement action logic here
        }
        public virtual void OnFinalize()
        {
            // Implement cleanup logic here
        }
    }
}
"""
        with open(os.path.join(parent_path,SCENARIO_ROLE, "BaseOrigintScenarioRoleActionbstractScenarioRoleAction.cs"), 'w', encoding='utf-8') as f:
            f.write(code_str)
            
    if not os.path.exists(os.path.join(parent_path,SCENARIO_ROLE, "BaseGeneralScenarioRoleAction.cs")):
        code_str = """
using System;
using System.Collections;
using UnityEngine;
using System.IO;
namespace GameCore.Scenario
{
    public  class BaseGeneralScenarioRoleAction<T> : BaseOrigintScenarioRoleAction where T : BaseScenarioRoleData
    {
        public T RoleData { get; private set; }

        public BaseGeneralScenarioRoleAction(T roleData) : base()
        {
            RoleData = roleData;
        }


        public override void OnInitialize()
        {
            base.OnInitialize();
        }
    }
}
"""
        with open(os.path.join(parent_path,SCENARIO_ROLE, "BaseGeneralScenarioRoleAction.cs"), 'w', encoding='utf-8') as f:
            f.write(code_str)
            
    if not os.path.exists(os.path.join(parent_path,SCENARIO_ROLE, "BaseScenarioRoleAction.cs")):
        code_str = """
using System;
using System.Collections;
using UnityEngine;

namespace GameCore.Scenario
{
    public class BaseScenarioRoleAction<T> : BaseGeneralScenarioRoleAction<T> where T : BaseScenarioRoleData
    {

        public BaseScenarioRoleAction(T roleData) : base(roleData)
        {
            
        }

        public override void OnInitialize()
        {
            base.OnInitialize();
        }



    }
}
"""
        with open(os.path.join(parent_path,SCENARIO_ROLE, "BaseScenarioRoleAction.cs"), 'w', encoding='utf-8') as f:
            f.write(code_str)
            
    if not os.path.exists(os.path.join(parent_path,SCENARIO_ROLE, "BaseScenarioRoleBranchAction.cs")):
        code_str = """
using System;
using System.Collections;
using UnityEngine;

namespace GameCore.Scenario
{
    public class BaseScenarioRoleBranchAction<T> : BaseGeneralScenarioRoleAction<T> where T : BaseScenarioRoleData
    {


        public BaseScenarioRoleBranchAction(T roleData) : base(roleData)
        {
            
        }

        public override void OnInitialize()
        {
            base.OnInitialize();
        }


    }
}
"""
        with open(os.path.join(parent_path,SCENARIO_ROLE, "BaseScenarioRoleBranchAction.cs"), 'w', encoding='utf-8') as f:
            f.write(code_str)
            
            
    
    if not os.path.exists(os.path.join(parent_path,SCENARIO_ROLE, "ScenarioEventManager.cs")):        
        # Generate ScenarioRoleID enum
        enum_content = """using System;

namespace GameCore.Scenario {
    public enum ScenarioRoleID {
        None = 0,
        Max
        }
    }
"""
        with open(os.path.join(parent_path, SCENARIO_ROLE, "ScenarioRoleID.cs"), 'w', encoding='utf-8') as f:
            f.write(enum_content)
            
     
    if not os.path.exists(os.path.join(parent_path,SCENARIO_ROLE, "ScenarioRoleFactory.cs")):       
        # Generate ScenarioRoleFactory class
        factory_content = """
using System;
namespace GameCore.Scenario {
    public static class ScenarioRoleFactory {
        public static BaseScenarioRoleData CreateRoleData(ScenarioRoleID id) {
            switch (id) {

                default:
                    return null;
            }
        }

        public static BaseOrigintScenarioRoleAction CreateRoleAction(BaseScenarioRoleData data) {
            if (data == null) return null;
            switch (data.RoleID) {

                default:
                    return null;
            }
        }
    }
}
"""
        with open(os.path.join(parent_path, SCENARIO_ROLE, "ScenarioRoleFactory.cs"), 'w', encoding='utf-8') as f:
            f.write(factory_content)
            
            
# 1. ScenarioMasterExecuteAction.cs
    if not os.path.exists(os.path.join(parent_path, SCENARIO_DATA, "script", "ScenarioMasterExecuteAction.cs")):
        # Generate ScenarioMasterExecuteAction class
        factory_content = """
using Cysharp.Threading.Tasks;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEngine;

public class ScenarioMasterExecuteAction
{
    private List<ScenarioGroupExecuteAction> scenarioActionList = new List<ScenarioGroupExecuteAction>();
    public int executeGroupID { get; private set; } = 0;
    public int executeSubGroupID { get; private set; } = 0;
    public bool IsExecuteFinish {  get; private set; }

    private List<ScenarioGroupExecuteAction> FindGroupActionList(int groupID)
    {
        return scenarioActionList.FindAll(data => data.GroupID == groupID);
    }

    public bool IsMaxReached()
    {
        if (IsExecuteFinish) return true;
        if (scenarioActionList.Count == 0) return true; // No groups, consider max reached
        if (executeGroupID < scenarioActionList.Count - 1) return false; // Not at last group

        var currentGroup = scenarioActionList.Find(data => data.GroupID == executeGroupID);
        if (currentGroup == null) return true; // No group found, consider max reached

        var subGroupCount = currentGroup.FindSubGroupActionList(int.MaxValue).Count;
        return executeSubGroupID >= subGroupCount - 1; // At last subgroup of last group
    }

    public void SetUp(BinaryReader reader)
    {
        IsExecuteFinish = false;
        int count = reader.ReadInt32();
        for (int i = 0; i < count; i++)
        {
            var addAction = new ScenarioGroupExecuteAction();
            addAction.SetUp(reader);
            scenarioActionList.Add(addAction);
        }
    }

    public async UniTask OnInitializeAsync()
    {
        if (IsMaxReached()) return;

        var find = FindGroupActionList(executeGroupID);
        var tasks = find.Select(action => action.OnInitializeAsync(executeSubGroupID)).ToArray();
        await UniTask.WhenAll(tasks);
    }

    public async UniTask OnExecuteAsync()
    {
        if (IsMaxReached()) return;

        var find = FindGroupActionList(executeGroupID);
        var tasks = find.Select(action => action.OnExecuteAsync(executeSubGroupID)).ToArray();
        await UniTask.WhenAll(tasks);
    }

    public async UniTask OnFinalizeAsync()
    {
        if (IsMaxReached()) return;

        var find = FindGroupActionList(executeGroupID);
        var tasks = find.Select(action => action.OnFinalizeAsync(executeSubGroupID)).ToArray();
        await UniTask.WhenAll(tasks);

        // Increment executeSubGroupID
        executeSubGroupID++;

        var currentGroup = scenarioActionList.Find(data => data.GroupID == executeGroupID);
        if (currentGroup != null)
        {
            var subGroupCount = currentGroup.FindSubGroupActionList(int.MaxValue).Count;
            if (executeSubGroupID >= subGroupCount)
            {
                executeSubGroupID = 0; // Reset subGroupID
                executeGroupID++; // Move to next group

                if (executeGroupID >= scenarioActionList.Count)
                {
                    executeGroupID = 0; // Reset to first group
                    IsExecuteFinish = true;
                }
            }
        }
    }
}
"""
        with open(os.path.join(parent_path, SCENARIO_DATA, "script", "ScenarioMasterExecuteAction.cs"), 'w', encoding='utf-8') as f:
            f.write(factory_content)

    # 2. ScenarioGroupExecuteAction.cs
    if not os.path.exists(os.path.join(parent_path, SCENARIO_DATA, "script", "ScenarioGroupExecuteAction.cs")):
        # Generate ScenarioGroupExecuteAction class
        factory_content = """
using Cysharp.Threading.Tasks;
using GameCore.Scenario;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEngine;

public class ScenarioGroupExecuteAction
{
    private List<ScenarioSubGroupExecuteAction> scenarioActionList = new List<ScenarioSubGroupExecuteAction>();
    public int GroupID { get; private set; }

    public List<ScenarioSubGroupExecuteAction> FindSubGroupActionList(int subGroupID)
    {
        return scenarioActionList.FindAll(data => data.SubGroupID == subGroupID);
    }

    public void SetUp(BinaryReader reader)
    {
        GroupID = reader.ReadInt32(); // Added GroupID read, assuming it was missing
        int count = reader.ReadInt32();
        for (int i = 0; i < count; i++)
        {
            var addAction = new ScenarioSubGroupExecuteAction();
            addAction.SetUp(reader);
            scenarioActionList.Add(addAction);
        }
    }

    public async UniTask OnInitializeAsync(int subGroupID)
    {
        var find = FindSubGroupActionList(subGroupID);
        var tasks = find.Select(action => action.OnInitializeAsync()).ToArray();
        await UniTask.WhenAll(tasks);
    }

    public async UniTask OnExecuteAsync(int subGroupID)
    {
        var find = FindSubGroupActionList(subGroupID);
        var tasks = find.Select(action => action.OnExecuteAsync()).ToArray();
        await UniTask.WhenAll(tasks);
    }

    public async UniTask OnFinalizeAsync(int subGroupID)
    {
        var find = FindSubGroupActionList(subGroupID);
        var tasks = find.Select(action => action.OnFinalizeAsync()).ToArray();
        await UniTask.WhenAll(tasks);
    }
}
"""
        with open(os.path.join(parent_path, SCENARIO_DATA, "script", "ScenarioGroupExecuteAction.cs"), 'w', encoding='utf-8') as f:
            f.write(factory_content)

    # 3. ScenarioExecuteAction.cs
    if not os.path.exists(os.path.join(parent_path, SCENARIO_DATA, "script", "ScenarioExecuteAction.cs")):
        # Generate ScenarioExecuteAction class
        factory_content = """
using Cysharp.Threading.Tasks;
using GameCore.Scenario;
using System.IO;
using UnityEngine;

public class ScenarioExecuteAction
{
    private BaseScenarioRoleData roleData;
    private BaseOrigintScenarioRoleAction action;

    public int GroupID => roleData.ScenarioGroupID;
    public int SubGroupID => roleData.ScenarioSubGroupID;

    public bool IsStartUp => action != null && action.IsStartUp;
    public bool IsRelease => action != null && action.IsRelease;
    public bool IsCompleted => action != null && action.IsCompleted && action.IsStartUp;

    public void SetUp(ScenarioRoleID id, BinaryReader reader)
    {
        roleData = ScenarioRoleFactory.CreateRoleData(id);
        roleData.ReadBinary(reader);
        action = ScenarioRoleFactory.CreateRoleAction(roleData);
    }

    public UniTask OnInitializeAsync()
    {
        if (IsStartUp)
        {
            return UniTask.CompletedTask;
        }
        action.OnInitialize();
        return UniTask.CompletedTask;
    }

    public UniTask OnExecuteAsync()
    {
        if (IsCompleted)
        {
            return UniTask.CompletedTask;
        }
        action.OnExecute();
        return UniTask.CompletedTask;
    }

    public UniTask OnFinalizeAsync()
    {
        if (IsRelease)
        {
            return UniTask.CompletedTask;
        }
        action.OnFinalize();
        return UniTask.CompletedTask;
    }
}
"""
        with open(os.path.join(parent_path, SCENARIO_DATA, "script", "ScenarioExecuteAction.cs"), 'w', encoding='utf-8') as f:
            f.write(factory_content)

    # 4. ScenarioSubGroupExecuteAction.cs
    if not os.path.exists(os.path.join(parent_path, SCENARIO_DATA, "script", "ScenarioSubGroupExecuteAction.cs")):
        # Generate ScenarioSubGroupExecuteAction class
        factory_content = """
using Cysharp.Threading.Tasks;
using GameCore.Scenario;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEngine;

public class ScenarioSubGroupExecuteAction
{
    private List<ScenarioExecuteAction> scenarioActionList = new List<ScenarioExecuteAction>();
    public int SubGroupID { get; private set; }

    public void SetUp(BinaryReader reader)
    {
        SubGroupID = reader.ReadInt32();
        int count = reader.ReadInt32();
        for (int i = 0; i < count; i++)
        {
            var addAction = new ScenarioExecuteAction();
            var id = (ScenarioRoleID)reader.ReadInt32();
            addAction.SetUp(id, reader);
            scenarioActionList.Add(addAction);
        }
    }

    public async UniTask OnInitializeAsync()
    {
        var tasks = scenarioActionList.Select(action => action.OnInitializeAsync()).ToArray();
        await UniTask.WhenAll(tasks);
    }

    public async UniTask OnExecuteAsync()
    {
        while (scenarioActionList.Any(action => !action.IsCompleted))
        {
            var tasks = scenarioActionList
                .Where(action => !action.IsCompleted)
                .Select(action => action.OnExecuteAsync())
                .ToArray();
            await UniTask.WhenAll(tasks);
            await UniTask.Yield(); // Prevent tight loop, allow frame update
        }
    }

    public async UniTask OnFinalizeAsync()
    {
        var tasks = scenarioActionList.Select(action => action.OnFinalizeAsync()).ToArray();
        await UniTask.WhenAll(tasks);
    }
}
"""
        with open(os.path.join(parent_path, SCENARIO_DATA, "script", "ScenarioSubGroupExecuteAction.cs"), 'w', encoding='utf-8') as f:
            f.write(factory_content)

    # 5. ScenarioEventBinaryHeader.cs
    if not os.path.exists(os.path.join(parent_path, SCENARIO_DATA, "script", "ScenarioEventBinaryHeader.cs")):
        # Generate ScenarioEventBinaryHeader class
        factory_content = """
// EventBinaryHeader.cs
using Cysharp.Threading.Tasks;
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;

namespace GameCore.Scenario
{
    // ヘッダー全体を管理するクラス
    public class ScenarioEventBinaryHeader
    {
        // staticなフィールドでヘッダー情報を保持
        private static List<ScenarioEventInfo> _events = null;

        // 読み込んだイベントリストを返すプロパティ
        public static List<ScenarioEventInfo> Events
        {
            get
            {
                if (_events == null)
                {
                    _events = new List<ScenarioEventInfo>();
                }
                return _events;
            }
            private set
            {
                _events = value;
            }
        }

        // バイナリファイルからヘッダーを非同期で読み込むメソッド
        public static async UniTask ReadHeaderAsync(string filePath, Action onComplete = null)
        {
            try
            {
                using (var stream = new FileStream(filePath, FileMode.Open, FileAccess.Read))
                using (var reader = new BinaryReader(stream, Encoding.UTF8))
                {
                    int eventCount = reader.ReadInt32(); // イベント数
                    var events = new List<ScenarioEventInfo>();

                    // イベント情報の読み込み
                    for (int i = 0; i < eventCount; i++)
                    {
                        var eventInfo = ScenarioEventInfo.ReadFromBinary(reader);
                        events.Add(eventInfo);
                        await UniTask.Yield();
                    }
                    await UniTask.Yield();
                    // サブイベント情報の読み込み
                    foreach (var eventInfo in events)
                    {
                        stream.Seek(eventInfo.EventOffset, SeekOrigin.Begin);
                        int subEventCount = reader.ReadInt32(); // サブイベント数
                        for (int j = 0; j < subEventCount; j++)
                        {
                            var subEventInfo = ScenarioSubEventInfo.ReadFromBinary(reader);
                            eventInfo.SubEvents.Add(subEventInfo);
                        }
                        await UniTask.Yield();
                    }

                    // staticフィールドに保存（メモリ保持）
                    Events = events;
                }

                // 読み込み完了後にコールバックを呼び出し
                onComplete?.Invoke();
            }
            catch (IOException ex)
            {
                throw new IOException($"Failed to read binary file: {filePath}", ex);
            }
            catch (Exception ex)
            {
                throw new Exception($"Error reading binary header: {ex.Message}", ex);
            }

            await UniTask.CompletedTask;
        }

        // イベント名とサブイベントIDからサブイベントのシーク座標を取得するメソッド
        public static long GetSubEventOffset(string eventName, int subEventId)
        {
            if (_events == null)
            {
                throw new InvalidOperationException("Header has not been loaded. Call ReadHeaderAsync first.");
            }

            foreach (var eventInfo in _events)
            {
                if (eventInfo.EventName == eventName)
                {
                    foreach (var subEventInfo in eventInfo.SubEvents)
                    {
                        if (subEventInfo.SubEventId == subEventId)
                        {
                            return subEventInfo.SubEventOffset;
                        }
                    }
                }
            }

            throw new KeyNotFoundException($"SubEvent with ID {subEventId} in Event '{eventName}' not found.");
        }
    }
}
"""
        with open(os.path.join(parent_path, SCENARIO_DATA, "script", "ScenarioEventBinaryHeader.cs"), 'w', encoding='utf-8') as f:
            f.write(factory_content)

    # 6. ScenarioEventInfo.cs
    if not os.path.exists(os.path.join(parent_path, SCENARIO_DATA, "script", "ScenarioEventInfo.cs")):
        # Generate ScenarioEventInfo class
        factory_content = """
// EventInfo.cs
using System.Collections.Generic;
using System.IO;
using System.Text;

namespace GameCore.Scenario
{
    // イベントの情報を格納するクラス
    public class ScenarioEventInfo
    {
        public string EventId { get; set; } // イベントID
        public string EventName { get; set; } // イベント名
        public long EventOffset { get; set; } // イベントのシーク座標
        public List<ScenarioSubEventInfo> SubEvents { get; set; } // サブイベントのリスト

        public ScenarioEventInfo(string eventId, string eventName, long eventOffset)
        {
            EventId = eventId ?? string.Empty;
            EventName = eventName ?? string.Empty;
            EventOffset = eventOffset;
            SubEvents = new List<ScenarioSubEventInfo>();
        }

        // バイナリから読み込むメソッド
        public static ScenarioEventInfo ReadFromBinary(BinaryReader reader)
        {
            int idLength = reader.ReadInt32(); // イベントIDの長さ
            string eventId = Encoding.UTF8.GetString(reader.ReadBytes(idLength)); // イベントID
            int nameLength = reader.ReadInt32(); // イベント名の長さ
            string eventName = Encoding.UTF8.GetString(reader.ReadBytes(nameLength)); // イベント名
            long eventOffset = reader.ReadInt64(); // イベントのシーク座標
            return new ScenarioEventInfo(eventId, eventName, eventOffset);
        }
    }
}
"""
        with open(os.path.join(parent_path, SCENARIO_DATA, "script", "ScenarioEventInfo.cs"), 'w', encoding='utf-8') as f:
            f.write(factory_content)

    # 7. ScenarioSubEventInfo.cs
    if not os.path.exists(os.path.join(parent_path, SCENARIO_DATA, "script", "ScenarioSubEventInfo.cs")):
        # Generate ScenarioSubEventInfo class
        factory_content = """
// SubEventInfo.cs
using System.IO;
using System.Text;

namespace GameCore.Scenario
{
    // サブイベントの情報を格納するクラス
    public class ScenarioSubEventInfo
    {
        public int SubEventId { get; set; } // サブイベントID (4バイト)
        public string SubEventName { get; set; } // サブイベント名
        public long SubEventOffset { get; set; } // サブイベントのシーク座標 (8バイト)

        public ScenarioSubEventInfo(int subEventId, string subEventName, long subEventOffset)
        {
            SubEventId = subEventId;
            SubEventName = subEventName ?? string.Empty;
            SubEventOffset = subEventOffset;
        }

        // バイナリから読み込むメソッド
        public static ScenarioSubEventInfo ReadFromBinary(BinaryReader reader)
        {
            int subEventId = reader.ReadInt32(); // サブイベントID
            int nameLength = reader.ReadInt32(); // サブイベント名の長さ
            string subEventName = Encoding.UTF8.GetString(reader.ReadBytes(nameLength)); // サブイベント名
            long subEventOffset = reader.ReadInt64(); // サブイベントのシーク座標
            return new ScenarioSubEventInfo(subEventId, subEventName, subEventOffset);
        }
    }
}
"""
        with open(os.path.join(parent_path, SCENARIO_DATA, "script", "ScenarioSubEventInfo.cs"), 'w', encoding='utf-8') as f:
            f.write(factory_content)

# app.pyから借用/統合するための関数 (実際はapp.pyからインポート)
def get_enum_values():
    enum_dir = os.path.join(DATA_DIR, 'enum')  # app.pyのENUM
    enum_list_path = os.path.join(enum_dir, 'enum_list.json')
    if not os.path.exists(enum_list_path):
        return {}
    with open(enum_list_path, 'r', encoding='utf-8') as f:
        enum_list = json.load(f)
    enum_values = {}
    for e in enum_list:
        enum_path = os.path.join(enum_dir, e['name'], f"{e['name']}.json")
        if os.path.exists(enum_path):
            with open(enum_path, 'r', encoding='utf-8') as ef:
                enum_values[e['name']] = json.load(ef)
    # class-data-idのenum_propertyも追加 (app.pyのget_json_data_id使用)
    class_id_dir = os.path.join(DATA_DIR, 'class-data-id')
    class_id_list_path = os.path.join(class_id_dir, 'class_data_id_list.json')
    if os.path.exists(class_id_list_path):
        with open(class_id_list_path, 'r', encoding='utf-8') as f:
            class_id_list = json.load(f)
        for c in class_id_list:
            class_path = os.path.join(class_id_dir, c['name'], f"{c['name']}.json")
            if os.path.exists(class_path):
                with open(class_path, 'r', encoding='utf-8') as cf:
                    class_data = json.load(cf)
                    enum_values[c['name']] = [r['enum_property'] for r in class_data.get('rows', [])]
    return enum_values

def get_type_lists():
    basic_types = ['int', 'float', 'bool', 'string', 'double', 'byte', 'char', 'short', 'long', 'decimal', 'object']
    unity_types = ['GameObject', 'Transform', 'Vector2', 'Vector3', 'Vector4', 'Quaternion', 'Color', 'Rect', 'Bounds', 'Matrix4x4', 'AnimationCurve', 'Sprite', 'Texture', 'Material', 'Mesh', 'Rigidbody', 'Collider', 'AudioClip', 'ScriptableObject']
    enum_dir = os.path.join(DATA_DIR, 'enum')
    class_dir = os.path.join(DATA_DIR, 'class-data')
    class_id_dir = os.path.join(DATA_DIR, 'class-data-id')
    enum_list = json.load(open(os.path.join(enum_dir, 'enum_list.json'))) if os.path.exists(os.path.join(enum_dir, 'enum_list.json')) else []
    class_list = json.load(open(os.path.join(class_dir, 'class_list.json'))) if os.path.exists(os.path.join(class_dir, 'class_list.json')) else []
    class_id_list = json.load(open(os.path.join(class_id_dir, 'class_data_id_list.json'))) if os.path.exists(os.path.join(class_id_dir, 'class_data_id_list.json')) else []
    return (
        basic_types,
        unity_types,
        [e.get('name') for e in enum_list],
        [c.get('name') for c in class_list],
        [c.get('name') for c in class_id_list]
    )

# generate_role_form_schema (全考慮版)
def generate_role_form_schema(role_name, data_dir, depth=0, max_depth=3):
    if depth > max_depth:
        return {"fields": [], "error": "Max depth reached"}

    role_path = os.path.join(data_dir, SCENARIO_ROLE, f"{role_name}", f"{role_name}.json")
    if not os.path.exists(role_path):
        return None
    with open(role_path, 'r', encoding='utf-8') as f:
        role_json = json.load(f)
        role_data = role_json.get('data', [])
        branch_type = role_json.get('branchType', 'General')

    schema = {"fields": [], "branchType": branch_type}

    for var in role_data:
        field = {"name": var['name'], "label": var['name'], "description": var.get('description', '')}
        var_type = var['type'].lower()

        # 各数値型を個別に割り当て
        if var_type in ['int', 'float', 'double', 'short', 'long', 'decimal', 'byte', 'char']:
            field['type'] = var_type  # ← まとめず個別型名をそのまま使う

        # bool
        elif var_type == 'bool':
            field['type'] = 'bool'

        # 文字列
        elif var_type == 'string':
            field['type'] = 'string'

        # vector 系
        elif var_type == 'vector2':
            field['type'] = 'vector2'
        elif var_type == 'vector3':
            field['type'] = 'vector3'
        elif var_type == 'vector4':
            field['type'] = 'vector4'

        # Enum
        elif var_type in get_type_lists()[2]:
            field['type'] = var_type
            enum_values = get_enum_values()
            if var_type in enum_values:
                field['options'] = [item.get('name', '') for item in enum_values[var_type]]
            else:
                field['options'] = []
                field['warning'] = 'Enum options not found'

        # class-data/class-data-id
        elif var_type in get_type_lists()[3] or var_type in get_type_lists()[4]:
            field['type'] = var_type
            sub_schema = generate_role_form_schema(var_type, data_dir, depth + 1, max_depth)
            field['subFields'] = sub_schema['fields'] if sub_schema else []

        else:
            field['type'] = var_type  # 未知型でもそのまま

        if var.get('arraySize', 0) > 0:
            field['isArray'] = True
            field['arraySize'] = var['arraySize']

        schema['fields'].append(field)

    return schema


# ユーティリティ: イベントJSONの読み書き
def read_event_data(eventId):
    event_path = os.path.join(DATA_DIR, SCENARIO_EVENT,f"{eventId}", f"{eventId}.json")
    if os.path.exists(event_path):
        with open(event_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"subgroups": {}}

def write_event_data(eventId, data):
    event_path = os.path.join(DATA_DIR, SCENARIO_EVENT, f"{eventId}", f"{eventId}.json")
    with open(event_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        
# Role schema の初期値生成ヘルパー
def get_initial_value(type_):
    type_lower = type_.lower()
    if type_lower in ['int', 'short', 'long', 'byte', 'char']:
        return 0
    elif type_lower in ['float', 'double', 'decimal']:
        return 0.0
    elif type_lower == 'bool':
        return False
    elif type_lower == 'string':
        return ""
    elif type_lower == 'vector2':
        return [0.0, 0.0]
    elif type_lower == 'vector3':
        return [0.0, 0.0, 0.0]
    elif type_lower == 'vector4':
        return [0.0, 0.0, 0.0, 0.0]
    else:  # enum, class_id など
        return 0

# Fix 関数: 全 event を fix
def fix_all_events():
    # 全 role schema マップ（変更なし）
    role_schemas = {}
    role_dir = os.path.join(DATA_DIR, SCENARIO_ROLE)
    for role_file in glob.glob(os.path.join(role_dir, '*', '*.json')):
        role_name = os.path.basename(os.path.dirname(role_file))
        with open(role_file, 'r', encoding='utf-8') as f:
            schema_data = json.load(f)
            fields = schema_data.get('data', [])
            role_schemas[role_name] = {field['name']: field['type'] for field in fields}

    # 全 event JSON を走査
    event_dir = os.path.join(DATA_DIR, SCENARIO_EVENT)
    for event_file in glob.glob(os.path.join(event_dir, '*', '*.json')):
        with open(event_file, 'r', encoding='utf-8') as f:
            event_data = json.load(f)
        
        # subgroups を走査
        updated = False
        subgroups = event_data.get('subgroups', {})
        if not isinstance(subgroups, dict):
            logger.error(f"Invalid subgroups in event {event_data.get('id', 'unknown')}: {subgroups}")
            continue
        logger.debug(f"Processing subgroups for event {event_data.get('id', 'unknown')}: {subgroups.keys()}")
        for sub_id, sub_group in subgroups.items():
            if not isinstance(sub_group, dict) or 'nodes' not in sub_group:
                logger.error(f"Invalid sub_group for event {event_data.get('id', 'unknown')}, sub_id {sub_id}: {sub_group}")
                continue
            nodes = sub_group.get('nodes', [])
            logger.debug(f"Subgroup {sub_id}: {len(nodes)} nodes")
            for node in nodes:
                # メイン node の roles
                roles = node.get('data', {}).get('roles', [])
                updated = fix_roles(roles, role_schemas) or updated
                
                # subgroups 内 (nested)
                inner_subgroups = node.get('data', {}).get('subgroups', {})
                if not isinstance(inner_subgroups, dict):
                    logger.error(f"Invalid inner subgroups in event {event_data.get('id', 'unknown')}, node {node.get('id', 'unknown')}: {inner_subgroups}")
                    continue
                logger.debug(f"Inner subgroups for node {node.get('id', 'unknown')}: {inner_subgroups.keys()}")
                for inner_sub_id, inner_sub in inner_subgroups.items():
                    inner_nodes = inner_sub.get('nodes', [])
                    for inner_node in inner_nodes:
                        inner_roles = inner_node.get('data', {}).get('roles', [])
                        updated = fix_roles(inner_roles, role_schemas) or updated
        
        if updated:
            with open(event_file, 'w', encoding='utf-8') as f:
                json.dump(event_data, f, ensure_ascii=False, indent=2)

def fix_roles(roles, role_schemas):
    updated = False
    for role in roles:
        role_name = role['name']
        schema_fields = role_schemas.get(role_name, {})
        current_data = {d['name']: d['value'] for d in role.get('data', [])}
        
        # schema にない field を削除
        new_data = [d for d in role['data'] if d['name'] in schema_fields]
        if len(new_data) != len(role['data']):
            updated = True
        
        # schema に新しく追加された field を初期値で追加
        for field_name, field_type in schema_fields.items():
            if field_name not in current_data:
                updated = True
                new_data.append({"name": field_name, "value": get_initial_value(field_type)})
        
        role['data'] = new_data
    return updated

# Event bin 生成ヘルパー
def pack_value(value, type_):
    type_lower = type_.lower()
    if isinstance(value, (int, float)) and (isnan(value) or not isfinite(value)):
        return b''  # スキップ
    if type_lower in ['int', 'short', 'long', 'byte', 'char']:
        return struct.pack('i', int(value))
    elif type_lower == 'float':
        return struct.pack('f', float(value))
    elif type_lower == 'double':
        return struct.pack('d', float(value))
    elif type_lower == 'bool':
        return struct.pack('?', bool(value))
    elif type_lower == 'string':
        encoded = value.encode('utf-8')
        return struct.pack('i', len(encoded)) + encoded
    elif type_lower == 'vector2':
        return struct.pack('ff', *map(float, value))
    elif type_lower == 'vector3':
        return struct.pack('fff', *map(float, value))
    elif type_lower == 'vector4':
        return struct.pack('ffff', *map(float, value))
    else:  # enum/class_id
        return struct.pack('i', int(value))
    
def generate_all_event_bin():
    all_bin_path = os.path.join(DATA_DIR, SCENARIO_EVENT, 'all_events.bin')
    header = bytearray()
    data_sections = bytearray()
    
    # 全 event リスト
    event_dir = os.path.join(DATA_DIR, SCENARIO_EVENT)
    event_files = glob.glob(os.path.join(event_dir, '*', '*.json'))
    events = []
    for event_file in event_files:
        with open(event_file, 'r', encoding='utf-8') as f:
            event_data = json.load(f)
            events.append(event_data)
    
    header.extend(struct.pack('i', len(events)))
    
    offsets = {}
    current_offset = len(header)
    
    # Placeholder for each event's offset
    for event in events:
        id_encoded = event.get('id', '').encode('utf-8')
        name_encoded = event.get('name', '').encode('utf-8')
        header.extend(struct.pack('i', len(id_encoded)))
        header.extend(id_encoded)
        header.extend(struct.pack('i', len(name_encoded)))
        header.extend(name_encoded)
        header.extend(struct.pack('q', 0))
    
    # Role schemas for types（変更なし）
    role_schemas = {}
    role_dir = os.path.join(DATA_DIR, SCENARIO_ROLE)
    for role_file in glob.glob(os.path.join(role_dir, '*', '*.json')):
        role_name = os.path.basename(os.path.dirname(role_file))
        with open(role_file, 'r', encoding='utf-8') as f:
            schema_data = json.load(f)
            fields = schema_data.get('data', [])
            role_schemas[role_name] = [(field['name'], field['type']) for field in fields]
    
    # Generate data sections
    for event in events:
        event_offset = len(header) + len(data_sections)
        offsets[event.get('id', '')] = event_offset
        
        section = bytearray()
        subEvents = event.get('subEvents', {})
        logger.debug(f"Generating bin for event {event.get('id', 'unknown')}: {len(subEvents)} subEvents")
        section.extend(struct.pack('i', len(subEvents)))
        
        sub_offsets = {}
        sub_current_offset = len(section)
        
        # Placeholder for sub offsets
        for sub_id in subEvents:
            name_encoded = sub_id.get('name', '').encode('utf-8')
            section.extend(struct.pack('i', int(sub_id["subId"])))
            section.extend(struct.pack('i', len(name_encoded)))
            section.extend(name_encoded)
            section.extend(struct.pack('q', 0))

            # Sub sections
            for sub_id, sub_group in event["subgroups"].items():
                if not isinstance(sub_group, dict) or 'nodes' not in sub_group:
                    logger.error(f"Invalid sub_group for event {event.get('id', 'unknown')}, sub_id {sub_id}: {sub_group}")
                    continue
                sub_offset = len(section) + sub_current_offset
                sub_offsets[sub_id] = len(header) + len(data_sections) + sub_current_offset + sub_offset

                sub_section = bytearray()
                nodes = sub_group.get('nodes', [])
                sub_section.extend(struct.pack('i', len(nodes)))

                for node in nodes:
                    node_id = int(node.get('id', '0')) if node.get('id', '0').isdigit() else 0
                    sub_section.extend(struct.pack('i', node_id))

                    roles = node.get('data', {}).get('roles', [])
                    sub_section.extend(struct.pack('i', len(roles)))

                    for role in roles:
                        role_id = int(role.get('id', '0')) if isinstance(role.get('id', '0'), (int, str)) and str(role.get('id', '0')).isdigit() else 0
                        sub_section.extend(struct.pack('i', role_id))

                        fields = role.get('data', [])
                        sub_section.extend(struct.pack('i', len(fields)))

                        schema_fields = role_schemas.get(role.get('name', ''), [])
                        for idx, field in enumerate(fields):
                            if idx < len(schema_fields):
                                _, field_type = schema_fields[idx]
                                sub_section.extend(pack_value(field.get('value', ''), field_type))

                # Nested subgroups
                for node in nodes:
                    inner_subgroups = node.get('data', {}).get('subgroups', {})
                    if not isinstance(inner_subgroups, dict):
                        logger.error(f"Invalid inner subgroups in event {event.get('id', 'unknown')}, node {node.get('id', 'unknown')}: {inner_subgroups}")
                        continue
                    logger.debug(f"Inner subgroups for node {node.get('id', 'unknown')}: {inner_subgroups.keys()}")
                    for inner_sub_id, inner_sub in inner_subgroups.items():
                        inner_nodes = inner_sub.get('nodes', [])
                        sub_section.extend(struct.pack('i', len(inner_nodes)))
                        for inner_node in inner_nodes:
                            inner_node_id = int(inner_node.get('id', '0')) if inner_node.get('id', '0').isdigit() else 0
                            sub_section.extend(struct.pack('i', inner_node_id))
                            inner_roles = inner_node.get('data', {}).get('roles', [])
                            sub_section.extend(struct.pack('i', len(inner_roles)))
                            for inner_role in inner_roles:
                                inner_role_id = int(inner_role.get('id', '0')) if isinstance(inner_role.get('id', '0'), (int, str)) and str(inner_role.get('id', '0')).isdigit() else 0
                                sub_section.extend(struct.pack('i', inner_role_id))
                                inner_fields = inner_role.get('data', [])
                                sub_section.extend(struct.pack('i', len(inner_fields)))
                                inner_schema_fields = role_schemas.get(inner_role.get('name', ''), [])
                                for idx, field in enumerate(inner_fields):
                                    if idx < len(inner_schema_fields):
                                        _, field_type = inner_schema_fields[idx]
                                        sub_section.extend(pack_value(field.get('value', ''), field_type))

                section.extend(sub_section)

            data_sections.extend(section)
    
    # Update offsets in header
    pos = 4
    for event in events:
        id_len = len(event.get('id', '').encode('utf-8'))
        name_len = len(event.get('name', '').encode('utf-8'))
        pos += 4 + id_len + 4 + name_len
        header[pos:pos+8] = struct.pack('q', offsets[event.get('id', '')])
        pos += 8
    
    # Write file
    with open(all_bin_path, 'wb') as f:
        f.write(header + data_sections)
    class_id_generate()
    return {"message": "All event bin generated"}

def class_id_generate():
    try:
        # class_data_id_list.jsonを読み込み
        class_data_path = os.path.join(DATA_DIR, CLASS_DATA_ID, "class_data_id_list.json")
        try:
            with open(class_data_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            print(f"エラー: {class_data_path} が見つかりません。空のリストで開始します。")
            data = []
        except json.JSONDecodeError:
            print(f"エラー: {class_data_path} のJSON形式が不正です。")
            return

        # ScenarioEventが存在するかチェック
        if not any(item.get("name") == "ScenarioEvent" for item in data):
            new_entry = {
                "name": "ScenarioEvent",
                "id": max((item["id"] for item in data), default=0) + 1
            }
            data.append(new_entry)
            # JSONに保存（テキストモードで）
            with open(class_data_path, "w", encoding="utf-8") as fw:
                json.dump(data, fw, ensure_ascii=False, indent=2)
            print(f"ScenarioEventを追加しました。ID: {new_entry['id']}")

        # ScenarioEventディレクトリを作成
        scenario_event_dir = os.path.join(DATA_DIR, CLASS_DATA_ID, "ScenarioEvent")
        os.makedirs(scenario_event_dir, exist_ok=True)

        # scenario_event_list.jsonを読み込み
        scenario_list_path = os.path.join(DATA_DIR,SCENARIO_EVENT, "scenario_event_list.json")
        try:
            with open(scenario_list_path, "r", encoding="utf-8") as f:
                scenario_list = json.load(f)
        except FileNotFoundError:
            print(f"エラー: {scenario_list_path} が見つかりません。")
            return
        except json.JSONDecodeError:
            print(f"エラー: {scenario_list_path} のJSON形式が不正です。")
            return

        # ScenarioEvent.jsonのデータ構造を初期化
        add_data = {
            "columns": [
                {"name": "eventID", "type": "string"},
                {"name": "subID", "type": "int"}
            ],
            "rows": []
        }

        count = 1
        for item in scenario_list:
            # subEventsが存在するかチェック
            if "subEvents" not in item:
                print(f"警告: {item.get('name', '不明')} にsubEventsがありません。スキップします。")
                continue
            for details in item["subEvents"]:
                add_id_data = {
                    "id": count,
                    "enum_property": f"{item.get('name', '')}_{details.get('name', '')}",
                    "description": f"{item.get('description', '')}_{details.get('name', '')}",
                    "data": [
                        {"eventID": str(item.get("id", ""))},
                        {"subID": str(details.get("subId", ""))}
                    ]
                }
                add_data["rows"].append(add_id_data)
                count += 1

        # ScenarioEvent.jsonに保存
        scenario_event_path = os.path.join(scenario_event_dir, "ScenarioEvent.json")
        with open(scenario_event_path, "w", encoding="utf-8") as fw:
            json.dump(add_data, fw, ensure_ascii=False, indent=2)
        print(f"{scenario_event_path} にデータを保存しました。")

    except Exception as e:
        print(f"予期しないエラーが発生しました: {e}")
from cmath import isfinite, isnan
import io
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

CLASS_DATA_ID = 'class_data_id'

SCENARIO_DATA = 'scenario_data'
SCENARIO_ROLE =  os.path.join(SCENARIO_DATA, 'scenario_role')
SCENARIO_CONDITIONS_DATA = os.path.join(SCENARIO_DATA, 'scenario_conditions_data')
SCENARIO_EVENT = os.path.join(SCENARIO_DATA, 'scenario_event_data')

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
using System.IO;
using UnityEngine;

namespace GameCore.Scenario
{
    public abstract class BaseScenarioRoleData
    {
        public ScenarioRoleID RoleID { get; protected set; }

        public abstract void ReadBinary(BinaryReader reader);
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
using System.Threading;
using Cysharp.Threading.Tasks;
namespace GameCore.Scenario
{
    public  class BaseOrigintScenarioRoleAction
    {
        public bool IsCompleted { get; protected set; } = false;
        public bool IsOneExecute { get; protected set; } = false;
        public bool IsStartUp { get; protected set; } = false;
        public bool IsRelease { get; protected set; } = false;
        public virtual void ReadBinary(BinaryReader reader)
        {
            
        }
        public virtual void OnInitialize(ScenarioExecuteData executeData, CancellationTokenSource ct)
        {
            IsCompleted = false;
        }
        public virtual void OnOneExecute(ScenarioExecuteData executeData, CancellationTokenSource ct)
        {
            // Implement action logic here
        }
        public virtual void OnExecute(ScenarioExecuteData executeData, CancellationTokenSource ct)
        {
            // Implement action logic here
        }
        public virtual void OnFinalize(ScenarioExecuteData executeData, CancellationTokenSource ct)
        {
            // Implement cleanup logic here
        }
        
        public virtual async UniTask OnInitializeAsync(ScenarioExecuteData executeData, CancellationTokenSource ct)
        {
            IsCompleted = false;
            await UniTask.CompletedTask;
        }
        public virtual async UniTask OnOneExecuteAsync(ScenarioExecuteData executeData, CancellationTokenSource ct)
        {
            // Implement action logic here
            await UniTask.CompletedTask;
        }
        public virtual async UniTask OnExecuteAsync(ScenarioExecuteData executeData, CancellationTokenSource ct)
        {
            // Implement action logic here
            await UniTask.CompletedTask;
        }
        public virtual async UniTask OnFinalizeAsync(ScenarioExecuteData executeData, CancellationTokenSource ct)
        {
            await UniTask.CompletedTask;
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
using System.Threading;
using Cysharp.Threading.Tasks;
namespace GameCore.Scenario
{
    public  class BaseGeneralScenarioRoleAction<T> : BaseOrigintScenarioRoleAction where T : BaseScenarioRoleData
    {
        public T RoleData { get; private set; }

        public BaseGeneralScenarioRoleAction(T roleData) : base()
        {
            RoleData = roleData;
        }


        public override void OnInitialize(ScenarioExecuteData executeData,CancellationTokenSource ct)
        {
            base.OnInitialize(executeData,ct);
        }
        
        public override async UniTask OnInitializeAsync(ScenarioExecuteData executeData, CancellationTokenSource ct)
        {
            await base.OnInitializeAsync(executeData, ct);
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
using System.Threading;
using UnityEngine;
using Cysharp.Threading.Tasks;
namespace GameCore.Scenario
{
    public class BaseScenarioRoleAction<T> : BaseGeneralScenarioRoleAction<T> where T : BaseScenarioRoleData
    {

        public BaseScenarioRoleAction(T roleData) : base(roleData)
        {

        }

        public override  void OnInitialize(ScenarioExecuteData executeData, CancellationTokenSource ct)
        {
            base.OnInitialize(executeData,ct);
        }
        
        public override async UniTask OnInitializeAsync(ScenarioExecuteData executeData, CancellationTokenSource ct)
        {
            await base.OnInitializeAsync(executeData, ct);
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
using System.Threading;
using UnityEngine;
using Cysharp.Threading.Tasks;
namespace GameCore.Scenario
{
    public class BaseScenarioRoleBranchAction<T> : BaseGeneralScenarioRoleAction<T> where T : BaseScenarioRoleData
    {


        public BaseScenarioRoleBranchAction(T roleData) : base(roleData)
        {

        }

        public override void OnInitialize(ScenarioExecuteData executeData, CancellationTokenSource ct)
        {
            base.OnInitialize(executeData,ct);
        }
        
        public override async UniTask OnInitializeAsync(ScenarioExecuteData executeData, CancellationTokenSource ct)
        {
            await base.OnInitializeAsync(executeData, ct);
        }


    }
}


"""
        with open(os.path.join(parent_path,SCENARIO_ROLE, "BaseScenarioRoleBranchAction.cs"), 'w', encoding='utf-8') as f:
            f.write(code_str)
            
            
    
    if not os.path.exists(os.path.join(parent_path,SCENARIO_ROLE, "ScenarioRoleID.cs")):        
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
            
    if not os.path.exists(os.path.join(parent_path,SCENARIO_DATA,"script")):
        os.makedirs(os.path.join(parent_path,SCENARIO_DATA,"script"))
      
            
            
# 1. ScenarioMasterExecuteAction.cs
    if not os.path.exists(os.path.join(parent_path, SCENARIO_DATA, "script", "ScenarioMasterExecuteAction.cs")):
        # Generate ScenarioMasterExecuteAction class
        factory_content = """
using Cysharp.Threading.Tasks;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;

public class ScenarioMasterExecuteAction
{
    private List<ScenarioGroupExecuteAction> scenarioActionList = new List<ScenarioGroupExecuteAction>();
    public int executeGroupID { get; private set; } = 1;
    public int executeSubGroupID { get; private set; } = 1;
    public bool IsExecuteFinish { get; private set; }
    private ScenarioExecuteData executeData = new ScenarioExecuteData();
    public ScenarioExecuteData ExecuteData {  get { return executeData; } }
    public void SetExecuteGroupID(int value)
    {
        if (value <= 0 || value >= scenarioActionList.Count) return;
        executeGroupID = value;
    }
    public void SetExecuteSubGroupID(int value)
    {
        if(value <= 0 || value >= scenarioActionList.Find(id => id.GroupID == executeGroupID).ScenarioActionListCount()) return;
        executeSubGroupID = value;
    }
    
    private List<ScenarioGroupExecuteAction> FindGroupActionList(int groupID)
    {
        return scenarioActionList.FindAll(data => data.GroupID == groupID);
    }

    public bool IsMaxReached()
    {
        return IsExecuteFinish;
    }

    public void SetUp(BinaryReader reader)
    {
        IsExecuteFinish = false;
        int groupEventCount = reader.ReadInt32(); // グループイベント数
        for (int i = 0; i < groupEventCount; i++)
        {
            var addAction = new ScenarioGroupExecuteAction();
            addAction.SetUp(reader);
            scenarioActionList.Add(addAction);
        }
    }

    public async UniTask OnInitializeAsync(CancellationTokenSource ct)
    {
        if (IsMaxReached()) return;

        var find = FindGroupActionList(executeGroupID);
        var tasks = find.Select(action => action.OnInitializeAsync(executeSubGroupID, executeData,ct));
        await UniTask.WhenAll(tasks).AttachExternalCancellation(ct.Token);
    }

    public async UniTask OnExecuteAsync(CancellationTokenSource ct)
    {
        if (IsMaxReached()) return;

        var find = FindGroupActionList(executeGroupID).First();
        var subFind = find.FindSubGroupActionList(executeSubGroupID);
        var tasks = subFind.Select(action => action.OnExecuteAsync(executeData, ct)).ToArray();
        await UniTask.WhenAll(tasks).AttachExternalCancellation(ct.Token);
    }

    public async UniTask OnFinalizeAsync(CancellationTokenSource ct)
    {
        if (IsMaxReached()) return;

        var find = FindGroupActionList(executeGroupID).First();
        var subFind = find.FindSubGroupActionList(executeSubGroupID);
        var tasks = subFind.Select(action => action.OnFinalizeAsync(executeData, ct)).ToArray();
        await UniTask.WhenAll(tasks).AttachExternalCancellation(ct.Token);

        executeSubGroupID++;
        var currentGroup = scenarioActionList.Find(data => data.GroupID == executeGroupID);
        if (currentGroup != null)
        {
            var subGroupCount = currentGroup.FindSubGroupActionList(executeSubGroupID);
            if (subGroupCount == null || !subGroupCount.Any())
            {
                executeGroupID++;
                executeSubGroupID = 1;
                if(executeGroupID >= scenarioActionList.Count)
                {
                    IsExecuteFinish = true;
                }
            }
        }
        else
        {
            IsExecuteFinish = true;
        }
    }
    
    public void AllRelease()
    {
        executeGroupID = executeSubGroupID = 1;
        scenarioActionList.Clear();
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
using System.Collections.Generic;
using System.IO;
using System.Threading;

public class ScenarioGroupExecuteAction
{
    private List<ScenarioSubGroupExecuteAction> scenarioActionList = new List<ScenarioSubGroupExecuteAction>();
    public int ScenarioActionListCount() => scenarioActionList.Count;
    public int GroupID { get; private set; }

    public List<ScenarioSubGroupExecuteAction> FindSubGroupActionList(int subGroupID)
    {
        return scenarioActionList.FindAll(data => data.SubGroupID == subGroupID);
    }

    public void SetUp(BinaryReader reader)
    {
        GroupID = reader.ReadInt32(); // グループイベントID
        int subEventCount = reader.ReadInt32(); // サブイベント数
        for (int i = 0; i < subEventCount; i++)
        {
            var addAction = new ScenarioSubGroupExecuteAction();
            addAction.SetUp(reader);
            scenarioActionList.Add(addAction);
        }
    }

    public async UniTask OnInitializeAsync(int subGroupID, ScenarioExecuteData executeData, CancellationTokenSource ct)
    {
        var find = FindSubGroupActionList(subGroupID);
        var tasks = find.Select(action => action.OnInitializeAsync(executeData,ct));
        await UniTask.WhenAll(tasks).AttachExternalCancellation(ct.Token);
    }

    public async UniTask OnExecuteAsync(int subGroupID, ScenarioExecuteData executeData, CancellationTokenSource ct)
    {
        var find = FindSubGroupActionList(subGroupID);
        var tasks = find.Select(action => action.OnExecuteAsync(executeData,ct));
        await UniTask.WhenAll(tasks).AttachExternalCancellation(ct.Token);
    }

    public async UniTask OnFinalizeAsync(int subGroupID, ScenarioExecuteData executeData, CancellationTokenSource ct)
    {
        var find = FindSubGroupActionList(subGroupID);
        var tasks = find.Select(action => action.OnFinalizeAsync(executeData,ct));
        await UniTask.WhenAll(tasks).AttachExternalCancellation(ct.Token);
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
using System.Threading;
using UnityEngine;

public class ScenarioExecuteAction
{
    private BaseScenarioRoleData roleData;
    private BaseOrigintScenarioRoleAction action;


    public bool IsStartUp => action != null && action.IsStartUp;
    public bool IsRelease => action != null && action.IsRelease;
    public bool IsCompleted => action != null && action.IsCompleted && action.IsStartUp;
    public bool IsOneCompleted => action != null && action.IsOneExecute && action.IsStartUp;

    public void SetUp(ScenarioRoleID id, BinaryReader reader)
    {
        roleData = ScenarioRoleFactory.CreateRoleData(id);
        roleData.ReadBinary(reader);
        action = ScenarioRoleFactory.CreateRoleAction(roleData);
    }


    public async UniTask OnInitializeAsync(ScenarioExecuteData executeData,CancellationTokenSource ct)
    {
        if (IsStartUp)
        {
            await UniTask.Yield(ct.Token);
            return;
        }
        await action.OnInitializeAsync(executeData,ct);
        action.OnInitialize(executeData, ct);
        await UniTask.Yield(ct.Token);
    }


    public async UniTask OnOneExecuteAsync(ScenarioExecuteData executeData, CancellationTokenSource ct)
    {
        if (IsOneCompleted)
        {
            await UniTask.Yield(ct.Token);
            return;
        }
        await action.OnOneExecuteAsync(executeData,ct);
        action.OnOneExecute(executeData, ct);
        await UniTask.Yield(ct.Token);
    }


    public async UniTask OnExecuteAsync(ScenarioExecuteData executeData, CancellationTokenSource ct)
    {
        if (IsCompleted)
        {
            await UniTask.Yield(ct.Token);
            return;
        }
        await action.OnExecuteAsync(executeData,ct);
        action.OnExecute(executeData, ct);
        await UniTask.Yield(ct.Token);
    }

    public async UniTask OnFinalizeAsync(ScenarioExecuteData executeData,CancellationTokenSource ct)
    {
        if (IsRelease)
        {
            await UniTask.Yield(ct.Token);
            return;
        }
        await action.OnFinalizeAsync(executeData,ct);
        action.OnFinalize(executeData, ct);
        await UniTask.Yield(ct.Token);
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
using System.Threading;

public class ScenarioSubGroupExecuteAction
{
    private List<ScenarioExecuteAction> scenarioActionList = new List<ScenarioExecuteAction>();
    public int SubGroupID { get; private set; }

    public void SetUp(BinaryReader reader)
    {
        SubGroupID = reader.ReadInt32(); // サブイベントID
        int actionCount = reader.ReadInt32(); // アクション（ロール）数
        for (int i = 0; i < actionCount; i++)
        {
            var addAction = new ScenarioExecuteAction();
            var id = (ScenarioRoleID)reader.ReadInt32(); // ロールID
            addAction.SetUp(id, reader);
            scenarioActionList.Add(addAction);
        }
    }

    public async UniTask OnInitializeAsync(ScenarioExecuteData executeData, CancellationTokenSource ct)
    {
        var tasks = scenarioActionList.Select(action => action.OnInitializeAsync(executeData,ct));
       
        await UniTask.WhenAll(tasks).AttachExternalCancellation(ct.Token);
    }

    public async UniTask OnExecuteAsync(ScenarioExecuteData executeData, CancellationTokenSource ct)
    {
        var oneTasks = scenarioActionList
                    .Where(action => !action.IsOneCompleted)
                    .Select(action => action.OnOneExecuteAsync(executeData,ct))
                    .ToArray();
        await UniTask.WhenAll(oneTasks).AttachExternalCancellation(ct.Token).AttachExternalCancellation(ct.Token);
        while (scenarioActionList.Any(action => !action.IsCompleted))
        {
            var tasks = scenarioActionList
                .Where(action => !action.IsCompleted)
                .Select(action => action.OnExecuteAsync(executeData,ct))
                .ToArray();
            await UniTask.WhenAll(tasks).AttachExternalCancellation(ct.Token);
            await UniTask.Yield(ct.Token);
        }
    }

    public async UniTask OnFinalizeAsync(ScenarioExecuteData executeData, CancellationTokenSource ct)
    {
        var tasks = scenarioActionList.Select(action => action.OnFinalizeAsync(executeData,ct)).ToArray();
        await UniTask.WhenAll(tasks).AttachExternalCancellation(ct.Token);
    }
}
"""
        with open(os.path.join(parent_path, SCENARIO_DATA, "script", "ScenarioSubGroupExecuteAction.cs"), 'w', encoding='utf-8') as f:
            f.write(factory_content)

    # 5. ScenarioEventBinaryHeader.cs
    if not os.path.exists(os.path.join(parent_path, SCENARIO_DATA, "script", "ScenarioEventBinaryHeader.cs")):
        # Generate ScenarioEventBinaryHeader class
        factory_content = """

using Cysharp.Threading.Tasks;
using GameCore.Tables;
using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices.ComTypes;
using System.Text;
using UnityEngine;
using UnityEngine.AddressableAssets;
using UnityEngine.ResourceManagement.AsyncOperations;

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

        public static long GetEventSeekPos(string eventName,string subName)
        {
            var find = _events.Find(data => data.EventId == eventName);
            var findSub = find.SubEvents.Find(data => data.SubEventName == subName);
            return findSub.SubEventOffset;
        }
        public static long GetEventSeekPos(string eventName, int subID)
        {
            var find = _events.Find(data => data.EventId == eventName);
            var findSub = find.SubEvents.Find(data => data.SubEventId == subID);
            return findSub.SubEventOffset;
        }
        public static async UniTask ReadHeaderAsync(Action action = null, bool addressable = false)
        {
            Stream stream = null;
            AsyncOperationHandle<TextAsset> handle = default;

            try
            {
                (stream, handle) = await GetDataStreamAsync(addressable);

                using var reader = new BinaryReader(stream, Encoding.UTF8);

                int eventCount = reader.ReadInt32();
                if (eventCount <= 0)
                    throw new InvalidDataException($"Invalid event count: {eventCount}");

                Events.Clear();

                for (int i = 0; i < eventCount; i++)
                {
                    var eventInfo = await ReadScenarioEventInfoAsync(reader, stream);
                    Events.Add(eventInfo);

                    await UniTask.Yield(); // 1フレームに1イベント処理（重い場合のフリーズ防止）
                }

                action?.Invoke();
            }
            finally
            {
                stream?.Dispose();

                if (handle.IsValid())
                    Addressables.Release(handle);
            }
        }

        /// <summary>
        /// Addressable または FileStream から Stream と Handle を取得
        /// </summary>
        private static async UniTask<(Stream stream, AsyncOperationHandle<TextAsset> handle)> GetDataStreamAsync(bool addressable)
        {
            if (addressable)
            {
                var handle = Addressables.LoadAssetAsync<TextAsset>(SupportFiles.ALL_SCENARIO_EVENT_BIN_FILE);
                TextAsset textAsset = await handle.ToUniTask();

                if (textAsset == null)
                {
                    Debug.LogError($"Failed to load Addressable binary: {SupportFiles.ALL_SCENARIO_EVENT_BIN_FILE}");
                    if (handle.IsValid()) Addressables.Release(handle);
                    throw new InvalidOperationException("Failed to load scenario event binary from Addressables.");
                }

                return (new MemoryStream(textAsset.bytes), handle);
            }
            else
            {
                var stream = new FileStream(
                    SupportFiles.ALL_SCENARIO_EVENTS_BIN,
                    FileMode.Open,
                    FileAccess.Read,
                    FileShare.Read);

                return (stream, default);
            }
        }

        /// <summary>
        /// 1つのイベント（サブイベント含む）を読み込む
        /// </summary>
        private static async UniTask<ScenarioEventInfo> ReadScenarioEventInfoAsync(BinaryReader reader, Stream baseStream)
        {
            // Event ID
            string eventId = ReadLengthPrefixedString(reader, baseStream, "event ID");

            // Event Name
            string eventName = ReadLengthPrefixedString(reader, baseStream, "event name");

            // Event Offset
            long eventOffset = reader.ReadInt64();
            ValidateOffset(eventOffset, baseStream, "event offset");

            // Sub Events
            int subEventCount = reader.ReadInt32();
            ValidateCount(subEventCount, 1000, "subEvent count", baseStream);

            var subEvents = new List<ScenarioSubEventInfo>(subEventCount);

            for (int j = 0; j < subEventCount; j++)
            {
                int subEventId = reader.ReadInt32();
                string subEventName = ReadLengthPrefixedString(reader, baseStream, "subEvent name");

                long subEventOffset = reader.ReadInt64();
                ValidateOffset(subEventOffset, baseStream, "subEvent offset");

                subEvents.Add(new ScenarioSubEventInfo(subEventId, subEventName, subEventOffset));

                await UniTask.Yield(PlayerLoopTiming.Initialization);
            }

            return new ScenarioEventInfo(eventId, eventName, eventOffset, subEvents);
        }

        /// <summary>
        /// 長さプレフィックス付きの文字列を安全に読み込む
        /// </summary>
        private static string ReadLengthPrefixedString(BinaryReader reader, Stream baseStream, string fieldName)
        {
            int length = reader.ReadInt32();
            ValidateCount(length, 1000, $"{fieldName} length", baseStream);

            if (length == 0)
                return string.Empty;

            byte[] bytes = reader.ReadBytes(length);
            return Encoding.UTF8.GetString(bytes);
        }

        /// <summary>
        /// カウント値（長さや個数）のバリデーション
        /// </summary>
        private static void ValidateCount(int count, int max, string fieldName, Stream stream)
        {
            if (count < 0 || count > max)
            {
                throw new InvalidDataException(
                    $"Invalid {fieldName}: {count} at position {stream.Position - 4}");
            }
        }

        /// <summary>
        /// オフセット値のバリデーション
        /// </summary>
        private static void ValidateOffset(long offset, Stream stream, string fieldName)
        {
            if (offset < 0 || offset > stream.Length)
            {
                throw new InvalidDataException(
                    $"Invalid {fieldName}: {offset} at position {stream.Position - 8}");
            }
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

        public ScenarioEventInfo(string eventId, string eventName, long eventOffset,List<ScenarioSubEventInfo> value)
        {
            EventId = eventId ?? string.Empty;
            EventName = eventName ?? string.Empty;
            EventOffset = eventOffset;
            SubEvents = value;
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


    }
}
"""
        with open(os.path.join(parent_path, SCENARIO_DATA, "script", "ScenarioSubEventInfo.cs"), 'w', encoding='utf-8') as f:
            f.write(factory_content)
            
    if not os.path.exists(os.path.join(parent_path,SCENARIO_DATA,"script","ScenarioExecuteData.cs")):
        code_str = """
using UnityEngine;


/// <summary>
/// ExecuteData
/// </summary>
public class ScenarioExecuteData
{
    
}

        """
        
        with open(os.path.join(parent_path,SCENARIO_DATA,"script","ScenarioExecuteData.cs"), 'w', encoding='utf-8') as f:
            f.write(code_str)
    
    if not os.path.exists(os.path.join(parent_path,SCENARIO_DATA,"script","ScenarioManagerCore.cs")):
        code_str = """
using Cysharp.Threading.Tasks;
using GameCore;
using GameCore.Scenario;
using System;
using System.IO;
using System.Text;
using System.Threading;
using Unity.VisualScripting;
using UnityEngine;
using UnityEngine.AddressableAssets;
using UnityEngine.ResourceManagement.AsyncOperations;

public class ScenarioManagerCore : BaseSingleton<ScenarioManagerCore>
{
    public bool IsHeaderLoad { get; private set; } = false;

    private ScenarioMasterExecuteAction master = new ScenarioMasterExecuteAction();

    private string event_play_name = "";
    private string event_sub_name = "";
    private bool is_event_change = false;

    public override void AwakeSingleton()
    {
        base.AwakeSingleton();
        ScenarioEventBinaryHeader.ReadHeaderAsync(() =>
        {
            IsHeaderLoad = true;
        }, addressable: SupportFiles.ADDRESSABLE_CHECK).Forget();
    }

    public void SetExecuteGroupID(int value) => master?.SetExecuteGroupID(value);
    public void SetExecuteSubGroupID(int value) => master?.SetExecuteSubGroupID(value);

    public void SetEventName(string value_event_name, string value_event_sub_name)
    {
        event_play_name = value_event_name;
        event_sub_name = value_event_sub_name;
        is_event_change = true;
    }

    public void SetEventNameID(string value_event_name, string value_event_sub_name,
                               int value_group_id = 1, int value_sub_group_id = 1)
    {
        SetExecuteGroupID(value_group_id);
        SetExecuteSubGroupID(value_sub_group_id);
        SetEventName(value_event_name, value_event_sub_name);
    }

    /// <summary>
    /// シナリオを実行します。
    /// </summary>
    /// <param name="eventName">イベント名</param>
    /// <param name="eventSubName">サブイベント名</param>
    /// <param name="addressable">trueの場合 Addressable から読み込む（TextAsset）</param>
    /// <param name="action">完了時に実行するアクション</param>
    /// <param name="cts">外部キャンセルトークン</param>
    public async UniTask ScenarioExecuteUpdate(
        string eventName,
        string eventSubName,
        bool addressable = false,                    // ← 追加
        Action<ScenarioExecuteData> action = null,
        CancellationTokenSource cts = null)
    {
        using var localCts = new CancellationTokenSource();
        using var linkedCts = cts != null
            ? CancellationTokenSource.CreateLinkedTokenSource(localCts.Token, cts.Token, this.GetCancellationTokenOnDestroy())
            : CancellationTokenSource.CreateLinkedTokenSource(localCts.Token, this.GetCancellationTokenOnDestroy());


        event_play_name = eventName;
        event_sub_name = eventSubName;
        is_event_change = true;

        try
        {
            while (!master.IsExecuteFinish && !linkedCts.IsCancellationRequested && is_event_change)
            {
                master.AllRelease();
                is_event_change = false;

                var seekPos = ScenarioEventBinaryHeader.GetEventSeekPos(event_play_name, event_sub_name);

                if (addressable)
                {
                    await LoadAndExecuteWithAddressable(seekPos, linkedCts);
                }
                else
                {
                    await LoadAndExecuteWithFileStream(seekPos, linkedCts);
                }

                await UniTask.Yield(PlayerLoopTiming.Update, linkedCts.Token);
            }
        }
        catch (OperationCanceledException)
        {
            Debug.Log($"ScenarioExecuteUpdate canceled for {eventName}/{eventSubName}");
            throw;
        }
        finally
        {
            action?.Invoke(master.ExecuteData);
            master.AllRelease();
            is_event_change = false;
            await UniTask.Yield(PlayerLoopTiming.Update, linkedCts.Token);
        }
    }

    // ====================== 非Addressable（従来通り） ======================
    private async UniTask LoadAndExecuteWithFileStream(long seekPos, CancellationTokenSource token)
    {
        using (var stream = new FileStream(SupportFiles.ALL_SCENARIO_EVENTS_BIN, FileMode.Open, FileAccess.Read))
        using (var reader = new BinaryReader(stream, Encoding.UTF8))
        {
            stream.Seek(seekPos, SeekOrigin.Begin);
            master.SetUp(reader);

            await ExecuteScenarioLoop(token);
        }
    }

    // ====================== Addressable版 ======================
    private async UniTask LoadAndExecuteWithAddressable(long seekPos, CancellationTokenSource token)
    {
        AsyncOperationHandle<TextAsset> handle = Addressables.LoadAssetAsync<TextAsset>(SupportFiles.ALL_SCENARIO_EVENT_BIN_FILE);

        TextAsset textAsset = await handle.ToUniTask(cancellationToken: token.Token);

        if (textAsset == null)
        {
            Debug.LogError($"Failed to load Addressable scenario binary: {SupportFiles.ALL_SCENARIO_EVENT_BIN_FILE}");
            if (handle.IsValid()) Addressables.Release(handle);
            return;
        }

        try
        {
            using (var ms = new MemoryStream(textAsset.bytes))
            using (var reader = new BinaryReader(ms, Encoding.UTF8))
            {
                ms.Seek(seekPos, SeekOrigin.Begin);
                master.SetUp(reader);

                await ExecuteScenarioLoop(token);
            }
        }
        finally
        {
            if (handle.IsValid()) Addressables.Release(handle);
        }
    }

    // ====================== 共通の実行ループ ======================
    private async UniTask ExecuteScenarioLoop(CancellationTokenSource token)
    {
        while (!master.IsExecuteFinish && !token.IsCancellationRequested)
        {
            await master.OnInitializeAsync(token);   // CancellationToken対応を推奨
            await master.OnExecuteAsync(token);
            await master.OnFinalizeAsync(token);

            await UniTask.Yield(PlayerLoopTiming.Update, token.Token);
        }
    }
}


        """
        with open(os.path.join(parent_path,SCENARIO_DATA,"script","ScenarioManagerCore.cs"), 'w', encoding='utf-8') as f:
            f.write(code_str)

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
    # class_data_idのenum_propertyも追加 (app.pyのget_json_data_id使用)
    class_id_dir = os.path.join(DATA_DIR, 'class_data_id')
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
    class_id_dir = os.path.join(DATA_DIR, 'class_data_id')
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
        field = {"name": var['name'], "label": var['name'], "arraySize":var["arraySize"], "description": var.get('description', '')}
        var_type = var['type']

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

        # class-data/class_data_id
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

def write_7bit_encoded_int(value: int) -> bytes:
    """7ビットの可変長整数をバイト列として返す"""
    result = []
    while True:
        byte = value & 0x7F  # 下位7ビットを抽出
        value >>= 7
        if value > 0:  # まだデータが続く場合は最上位ビットを1に設定
            byte |= 0x80
        result.append(byte)
        if value == 0:
            break
    return bytes(result)

# Event bin 生成ヘルパー
def pack_value(value, type_,basic_types, unity_types, enum_list, class_list, class_data_id_list,enum_data,class_data_id,class_data):
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
        return write_7bit_encoded_int(len(encoded)) + encoded
    elif type_lower == 'vector2':
        return struct.pack('ff', *map(float, value))
    elif type_lower == 'vector3':
        return struct.pack('fff', *map(float, value))
    elif type_lower == 'vector4':
        return struct.pack('ffff', *map(float, value))
    elif type_ + "ID" in enum_data:
        # 文字列ならTextureID.以降を取得、辞書ならvalueを使用
        property_name = value
        actual_id = next((item['id'] for item in enum_data[type_ + "ID"] if item['property'] == property_name.split('.')[-1]), 0)
        return struct.pack('i', actual_id)
                    
    elif type_ + "ID" in class_data_id:
        property_name = value
        actual_id = next((row['id'] for row in class_data_id[type_+ "ID"]['rows'] if row['enum_property'] == property_name.split('.')[-1]), 0)
        return struct.pack('i', actual_id)
    elif type_ in class_list:
        property_name = value
        customData =  class_data[type_]
        section = bytearray()
        for detailsData in customData:
            typeDetails = detailsData["type"]
            arraySize = detailsData["arraySize"]
            valueDetails = None
            
            for key, valueData in value.items():
                if(key == detailsData["name"]):
                    valueDetails = valueData
                    break
            if valueDetails == None:
                 return struct.pack('i', int(0))
            
            if arraySize == 0:
                return (pack_value(valueDetails, typeDetails,basic_types, unity_types, enum_list, class_list, class_data_id_list,enum_data,class_data_id,class_data))
            elif arraySize > 0:
                for count in range(0,arraySize):
                    section.extend(pack_value(valueDetails[count], typeDetails,basic_types, unity_types, enum_list, class_list, class_data_id_list,enum_data,class_data_id,class_data))
            elif arraySize <= -1:
                section.extend(struct.pack('i', int(arraySize)))
                for count in range(0,arraySize):
                    section.extend(pack_value(valueDetails[count], typeDetails,basic_types, unity_types, enum_list, class_list, class_data_id_list,enum_data,class_data_id,class_data))
                    
        
        
        
        return section
    else:  # enuass_id
        return struct.pack('i', int(value))
    

def generate_all_event_bin(basic_types, unity_types, enum_list, class_list, class_data_id_list,enum_data,class_data_id,class_data ):
    all_bin_path = os.path.join(DATA_DIR, SCENARIO_EVENT, 'all_events.bytes')
    header = bytearray()
    data_sections = bytearray()
    
    
    
    
    # 1. Load event JSON files
    event_dir = os.path.join(DATA_DIR, SCENARIO_EVENT)
    event_files = glob.glob(os.path.join(event_dir, '*', '*.json'))  # Original path
    events = []
    for event_file in event_files:
        try:
            with open(event_file, 'r', encoding='utf-8') as f:
                event_data = json.load(f)
                # Handle list-wrapped JSON
                if isinstance(event_data, list) and event_data:
                    event_data = event_data[0]  # Take first dict
                if not isinstance(event_data, dict):
                    logger.error(f"Invalid event data format in {event_file}: expected dict, got {type(event_data)}")
                    continue
                if 'id' not in event_data:
                    logger.error(f"Missing 'id' in event data: {event_file}")
                    continue
                events.append(event_data)
                logger.debug(f"Loaded event file: {event_file}, ID: {event_data.get('id')}")
        except Exception as e:
            logger.error(f"Failed to load event file {event_file}: {e}")
    
    if not events:
        logger.error("No valid event files loaded")
        return {"error": "No valid event files loaded"}
    
    # Write event count
    header.extend(struct.pack('i', len(events)))
    logger.debug(f"Writing event count: {len(events)}")
    
    # Event offset management
    offsets = {}
    event_offset_positions = []
    
    # 2. Event headers
    for event in events:
        event_id = event.get('id', '')
        id_encoded = event_id.encode('utf-8')
        name_encoded = event.get('name', '').encode('utf-8')
        header.extend(struct.pack('i', len(id_encoded)))
        header.extend(id_encoded)
        header.extend(struct.pack('i', len(name_encoded)))
        header.extend(name_encoded)
        offset_pos = len(header)
        header.extend(struct.pack('q', 0))
        event_offset_positions.append((event_id, offset_pos))
        logger.debug(f"Event header: ID={event_id}, Name={event.get('name', '')}, OffsetPos={offset_pos}")
    
    # 3. Load role schemas
    role_schemas = {
        'TalkText': [('text', 'string'), ('name', 'string')]  # Temporary schema
    }
    role_dir = os.path.join(DATA_DIR, SCENARIO_ROLE)
    for role_file in glob.glob(os.path.join(role_dir, '*', '*.json')):
        role_name = os.path.basename(os.path.dirname(role_file))
        try:
            with open(role_file, 'r', encoding='utf-8') as f:
                schema_data = json.load(f)
                fields = schema_data.get('data', [])
                role_schemas[role_name] = [(field['name'], field['type']) for field in fields]
            logger.debug(f"Loaded role schema: {role_name}")
        except Exception as e:
            logger.error(f"Failed to load role file {role_file}: {e}")
    
    # 4. Data section generation
    for event in events:
        event_id = event.get('id', '')
        event_offset = len(header) + len(data_sections)
        offsets[event_id] = event_offset
        logger.debug(f"Event {event_id} data at offset: {event_offset}")

        section = bytearray()
        subEvents = event.get('subEvents', [])
        section.extend(struct.pack('i', len(subEvents)))  # SubEvent count
        logger.debug(f"Writing subEvent count for {event_id}: {len(subEvents)}")

        sub_offsets = {}
        sub_offset_positions = []

        # 4.1 SubEvent placeholders
        for sub_data in subEvents:
            sub_id = str(sub_data.get('subId', 0))
            name_encoded = sub_data.get('name', '').encode('utf-8')
            section.extend(struct.pack('i', int(sub_id)))
            section.extend(struct.pack('i', len(name_encoded)))
            section.extend(name_encoded)
            pos_in_section = len(section)
            section.extend(struct.pack('q', 0))
            sub_offset_positions.append((sub_id, pos_in_section))
            logger.debug(f"SubEvent header: ID={sub_id}, Name={sub_data.get('name', '')}, OffsetPos={pos_in_section}")

        # 4.2 SubEvent data
        for sub_data in subEvents:
            sub_id = str(sub_data.get('subId', 0))
            sub_offset = len(header) + len(data_sections) + len(section)
            sub_offsets[sub_id] = sub_offset
            logger.debug(f"SubEvent {sub_id} data at offset: {sub_offset}")

            sub_section = bytearray()
            subgroups = event.get('subgroups', {}).get(sub_id, {})
            groups = subgroups.get('nodes', []) if isinstance(subgroups, dict) else []
            sub_section.extend(struct.pack('i', len(groups)))  # Group count
            logger.debug(f"Writing group count for subEvent {sub_id}: {len(groups)}")

            for group in groups:
                group_id = int(group.get('id', '0')) if group.get('id', '0').isdigit() else 0
                sub_section.extend(struct.pack('i', group_id))  # Group ID
                logger.debug(f"Group ID: {group_id}")

                roles = group.get('data', {}).get('roles', [])
                inner_subgroups = group.get('data', {}).get('subgroups', {})
                inner_nodes = sum([inner_sub.get('nodes', []) for inner_sub in inner_subgroups.values()], [])
                num_subgroups = (1 if roles else 0) + len(inner_nodes)
                sub_section.extend(struct.pack('i', num_subgroups))  # SubGroup count
                logger.debug(f"SubGroup count for Group {group_id}: {num_subgroups}")

                if roles:
                    sub_section.extend(struct.pack('i', 0))  # SubGroup ID = 0
                    sub_section.extend(struct.pack('i', len(roles)))  # Action count
                    logger.debug(f"Roles for Group {group_id}: {len(roles)}")
                    for role in roles:
                        role_id = int(role.get('id', '0')) if isinstance(role.get('id', '0'), (int, str)) and str(role.get('id', '0')).isdigit() else 0
                        sub_section.extend(struct.pack('i', role_id))
                        logger.debug(f"Role ID: {role_id}")
                        schema_fields = role_schemas.get(role.get('name', ''), [])
                        fields = role.get('data', [])
                        for field_idx in range(min(len(fields), len(schema_fields))):
                            field = fields[field_idx]
                            _, field_type = schema_fields[field_idx]
                            sub_section.extend(pack_value(field.get('value', ''), field_type,basic_types, unity_types, enum_list, class_list, class_data_id_list,enum_data,class_data_id,class_data))

                for inner_sub_id, inner_sub in inner_subgroups.items():
                    inner_nodes = inner_sub.get('nodes', [])
                    for inner_node in inner_nodes:
                        inner_sub_group_id = int(inner_node.get('id', '0')) if inner_node.get('id', '0').isdigit() else 0
                        sub_section.extend(struct.pack('i', inner_sub_group_id))  # SubGroup ID
                        inner_roles = inner_node.get('data', {}).get('roles', [])
                        sub_section.extend(struct.pack('i', len(inner_roles)))  # Action count
                        logger.debug(f"SubGroup ID: {inner_sub_group_id}, Action count: {len(inner_roles)}")

                        for inner_role in inner_roles:
                            inner_role_id = int(inner_role.get('id', '0')) if isinstance(inner_role.get('id', '0'), (int, str)) and str(inner_role.get('id', '0')).isdigit() else 0
                            sub_section.extend(struct.pack('i', inner_role_id))
                            logger.debug(f"Inner Role ID: {inner_role_id}")
                            inner_schema_fields = role_schemas.get(inner_role.get('name', ''), [])
                            inner_fields = inner_role.get('data', [])
                            for field_idx in range(min(len(inner_fields), len(inner_schema_fields))):
                                field = inner_fields[field_idx]
                                _, field_type = inner_schema_fields[field_idx]
                                if(field_type == "Fade"):
                                    print("Fade type found, skipping value packing for this field.")
                                arraySize = field.get('arraySize',0)
                                if arraySize == 0:
                                    sub_section.extend(pack_value(field.get('value', ''), field_type,basic_types, unity_types, enum_list, class_list, class_data_id_list,enum_data,class_data_id,class_data))
                                elif arraySize > 0:
                                    for count in range(0,arraySize):
                                        sub_section.extend(pack_value(field.get('value', '')[count], field_type,basic_types, unity_types, enum_list, class_list, class_data_id_list,enum_data,class_data_id,class_data))
                                elif arraySize <= -1:
                                    sub_section.extend(struct.pack('i', int(arraySize)))
                                    for count in range(0,arraySize):
                                        sub_section.extend(pack_value(field.get('value', '')[count], field_type,basic_types, unity_types, enum_list, class_list, class_data_id_list,enum_data,class_data_id,class_data))

            section.extend(sub_section)

        for sub_id, pos_in_section in sub_offset_positions:
            logger.debug(f"Patching SubEvent {sub_id} offset: {sub_offsets[sub_id]} at position {pos_in_section}")
            section[pos_in_section:pos_in_section+8] = struct.pack('q', sub_offsets[sub_id])

        data_sections.extend(section)
    
    for event_id, pos in event_offset_positions:
        logger.debug(f"Patching Event {event_id} offset: {offsets[event_id]} at position {pos}")
        header[pos:pos+8] = struct.pack('q', offsets[event_id])
    
    try:
        with open(all_bin_path, 'wb') as f:
            f.write(header + data_sections)
        logger.info(f"Successfully wrote binary file: {all_bin_path} (Size: {len(header + data_sections)} bytes)")
    except Exception as e:
        logger.error(f"Failed to write binary file {all_bin_path}: {e}")
        return {"error": f"Failed to write binary file: {e}"}
    
    try:
        class_id_generate()
    except NameError:
        logger.error("class_id_generate is not defined")
        return {"error": "class_id_generate is not defined"}
    
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
                {"name": "subID", "type": "string"}
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
                    "data": {
                        "eventID": {"value": str(item.get("id", "")), "type": "string"},
                        "subID": {"value": str(details.get("name", "")), "type": "string"}
                    }
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
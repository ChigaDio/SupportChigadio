from cmath import isfinite, isnan
import io
import re
import struct
import sys
import os
import json
from enum import Enum
# 追加 import
import glob
from venv import logger

# CustomClassData / CustomClassDataID (bit・color・bezier対応済みの型解決とバイナリ書き込み)を
# シナリオ側でも再利用するために読み込む。app.py 側で customclassdata.register() が
# 呼ばれ済みであることを前提とする(_state['DATA_DIR'] が必要なAPI呼び出しは
# 実行時=Flaskアプリ起動後にしか行われないため問題ない)。
import pythonSrc.customclassdata as customclassdata
# ClassDataID側(Row.cs/Table.cs/TableID.cs/バイナリの自動生成、Scenario_{親}エントリの
# 追加・リネーム・削除追従、IDの並び替え)と連携するために読み込む。
import pythonSrc.class_data_id as class_data_id_api

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

def init(data_dir):
    """app.py から呼び出す初期化関数。"""
    global DATA_DIR
    DATA_DIR = os.path.abspath(data_dir)

def generate_scenario_folder(parent_path : str):
    if not os.path.exists(os.path.join(parent_path, SCENARIO_DATA)):
        os.makedirs(os.path.join(parent_path, SCENARIO_DATA))
    if not os.path.exists(os.path.join(parent_path, SCENARIO_ROLE)):
        os.makedirs(os.path.join(parent_path, SCENARIO_ROLE))
    if not os.path.exists(os.path.join(parent_path, SCENARIO_CONDITIONS_DATA)):
        os.makedirs(os.path.join(parent_path, SCENARIO_CONDITIONS_DATA))
    if not os.path.exists(os.path.join(parent_path, SCENARIO_EVENT)):
        os.makedirs(os.path.join(parent_path, SCENARIO_EVENT))

def compute_max_role_concurrency():
    """全シナリオイベントの遷移図データを走査し、役職(Role名)ごとに
    「1つのサブグループ内で同時に呼ばれる最大数」を求める。
    ScenarioRoleFactoryのプール事前ウォームアップ(項目3)に使う。
    戻り値: { role_name: max_concurrent_count, ... }
    """
    max_counts = {}
    event_list_path = os.path.join(DATA_DIR, SCENARIO_EVENT, "scenario_event_list.json")
    if not os.path.exists(event_list_path):
        return max_counts

    try:
        with open(event_list_path, 'r', encoding='utf-8') as f:
            events = json.load(f)
    except Exception:
        return max_counts

    for event in events:
        event_id = event.get('id')
        if not event_id:
            continue
        event_path = os.path.join(DATA_DIR, SCENARIO_EVENT, event_id, f"{event_id}.json")
        if not os.path.exists(event_path):
            continue
        try:
            with open(event_path, 'r', encoding='utf-8') as f:
                event_data = json.load(f)
        except Exception:
            continue

        # main(親イベント直下)＋サブグループのそれぞれを「1アクション単位」として集計
        groups_to_check = []
        if 'nodes' in event_data:
            groups_to_check.append(event_data.get('nodes', []))
        for sub_data in event_data.get('subgroups', {}).values():
            groups_to_check.append(sub_data.get('nodes', []))

        for nodes in groups_to_check:
            counts = {}
            for node in nodes:
                for role in (node.get('data', {}) or {}).get('roles', []) or []:
                    role_name = role.get('name')
                    if not role_name:
                        continue
                    counts[role_name] = counts.get(role_name, 0) + 1
            for role_name, count in counts.items():
                if count > max_counts.get(role_name, 0):
                    max_counts[role_name] = count

    return max_counts




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
        // ------------------------------------------------------------
        // 各関数(Enter/OneUpdate/Update/Finish、同期・非同期それぞれ)に
        // 紐づいたフラグ。デフォルトfalseで、本実装(具象クラス)側の
        // 最初の自動生成でoverrideされた際、その処理が終わったところで
        // trueにする(＝「この関数の処理が完了した」という意味)。
        // 以前あったIsCompleted/IsOneExecute/IsStartUp/IsReleaseは廃止し、
        // 制御はすべてこの8個のフラグに一本化した。
        // ------------------------------------------------------------
        public bool IsEnter { get; protected set; } = false;
        public bool IsEnterAsync { get; protected set; } = false;
        public bool IsOneUpdate { get; protected set; } = false;
        public bool IsOneUpdateAsync { get; protected set; } = false;
        public bool IsUpdate { get; protected set; } = false;
        public bool IsUpdateAsync { get; protected set; } = false;
        public bool IsFinish { get; protected set; } = false;
        public bool IsFinishAsync { get; protected set; } = false;
        public virtual void ReadBinary(BinaryReader reader)
        {
            
        }
        public virtual void OnInitialize(ScenarioExecuteData executeData, CancellationTokenSource ct)
        {
            IsEnter = true;
        }
        public virtual void OnOneExecute(ScenarioExecuteData executeData, CancellationTokenSource ct)
        {
            // Implement action logic here
            IsOneUpdate = true;
        }
        public virtual void OnExecute(ScenarioExecuteData executeData, CancellationTokenSource ct)
        {
            // Implement action logic here
            IsUpdate = true;
        }
        public virtual void OnFinalize(ScenarioExecuteData executeData, CancellationTokenSource ct)
        {
            // Implement cleanup logic here
            IsFinish = true;
        }
        
        public virtual async UniTask OnInitializeAsync(ScenarioExecuteData executeData, CancellationTokenSource ct)
        {
            IsEnterAsync = true;
            await UniTask.CompletedTask;
        }
        public virtual async UniTask OnOneExecuteAsync(ScenarioExecuteData executeData, CancellationTokenSource ct)
        {
            IsOneUpdateAsync = true;
            // Implement action logic here
            await UniTask.CompletedTask;
        }
        public virtual async UniTask OnExecuteAsync(ScenarioExecuteData executeData, CancellationTokenSource ct)
        {
            IsUpdateAsync = true;
            // Implement action logic here
            await UniTask.CompletedTask;
        }
        public virtual async UniTask OnFinalizeAsync(ScenarioExecuteData executeData, CancellationTokenSource ct)
        {
            IsFinishAsync = true;
            await UniTask.CompletedTask;
        }

        // ------------------------------------------------------------
        // RoleActionの再利用対応(項目3)。プールに戻す前に呼ばれ、
        // 使い回すインスタンスの状態を初期状態(全フェーズ未完了)に戻す。
        // 実装クラス側はoverrideし、base.Reset()を呼んだうえで
        // 自身の内部状態の初期化コードを追加する。
        // ------------------------------------------------------------
        public virtual void Reset()
        {
            IsEnter = false;
            IsEnterAsync = false;
            IsOneUpdate = false;
            IsOneUpdateAsync = false;
            IsUpdate = false;
            IsUpdateAsync = false;
            IsFinish = false;
            IsFinishAsync = false;
        }
        public virtual async UniTask ResetAsync()
        {
            IsEnter = false;
            IsEnterAsync = false;
            IsOneUpdate = false;
            IsOneUpdateAsync = false;
            IsUpdate = false;
            IsUpdateAsync = false;
            IsFinish = false;
            IsFinishAsync = false;
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
        # シナリオデータを解析し、役職ごとに「1アクション(1サブグループ)内で
        # 同時に呼ばれる最大数」を求めてプールを事前に用意しておく。
        role_max_concurrency = compute_max_role_concurrency()
        warmup_lines = []
        for role_name, max_count in sorted(role_max_concurrency.items()):
            if max_count <= 0:
                continue
            
            warmup_lines.append(f"                new {role_name}ID");
            warmup_lines.append(f"");

        # Generate ScenarioRoleFactory class
        factory_content = f"""
using System;
using System.Collections.Generic;
using System.Threading;
using Cysharp.Threading.Tasks;

namespace GameCore.Scenario {{
    public static class ScenarioRoleFactory {{
        public static BaseScenarioRoleData CreateRoleData(ScenarioRoleID id) {{
            switch (id) {{
                default:
                    return null;
            }}
        }}

        private static BaseOrigintScenarioRoleAction CreateNewRoleAction(BaseScenarioRoleData data) {{
            switch (data.RoleID) {{
                default:
                    return null;
            }}
        }}
        
        public static void SetData(BaseOrigintScenarioRoleAction action,BaseScenarioRoleData data) {{
            if (data == null) return;
            switch (data.RoleID) {{
                default:
                    return;
            }}
        }}

        // 役職ごとのプール構造：
        // freePool: 未使用インスタンスを O(1) で出し入れする Stack
        // activeSet: 解放時に正しいアクションか確認、あるいは線形探索を避けるための管理
        private class RolePool {{
            public readonly Stack<BaseOrigintScenarioRoleAction> FreeStack = new Stack<BaseOrigintScenarioRoleAction>();
            // どのアクションが使われているかをO(1)で判定・管理したい場合のセット
            public readonly HashSet<BaseOrigintScenarioRoleAction> ActiveSet = new HashSet<BaseOrigintScenarioRoleAction>();
        }}

        private static readonly Dictionary<ScenarioRoleID, RolePool> actionPool
            = new Dictionary<ScenarioRoleID, RolePool>();

        private static RolePool GetOrCreatePool(ScenarioRoleID id) {{
            if (!actionPool.TryGetValue(id, out var pool)) {{
                pool = new RolePool();
                actionPool[id] = pool;
            }}
            return pool;
        }}

        public static void WarmUpPool(BaseScenarioRoleData data,int count) {{
            var pool = GetOrCreatePool(data.RoleID);
            int currentTotal = pool.FreeStack.Count + pool.ActiveSet.Count;
            int needed = count - currentTotal;
            
            for (int i = 0; i < needed; i++) {{
                var newAction = CreateNewRoleAction(data);
                if (newAction != null) {{
                    pool.FreeStack.Push(newAction);
                }}
            }}
        }}

        public static async UniTask<BaseOrigintScenarioRoleAction> CreateRoleActionAsync(BaseScenarioRoleData data, CancellationToken ct = default) {{
            if (data == null) return null;
            var pool = GetOrCreatePool(data.RoleID);

            BaseOrigintScenarioRoleAction action;

            if (pool.FreeStack.Count > 0) {{
                action = pool.FreeStack.Pop();
                SetData(action,data);
            }} else {{
                action = CreateNewRoleAction(data);
                if (action == null) return null;
            }}

            action.Reset();

            try {{
                // キャンセルトークンを紐付けて非同期リセットを実行
                await action.ResetAsync().AttachExternalCancellation(ct);
            }} catch (System.OperationCanceledException) {{
                // 万が一キャンセルされた場合は、プールからポップしたアクションを再度スタックに戻すか、
                // もし新規生成したものであれば破棄・未使用に戻すなどの配慮が必要です
                pool.FreeStack.Push(action);
                throw;
            }}

            pool.ActiveSet.Add(action);
            return action;
        }}

        public static void ReleaseRoleAction(ScenarioRoleID id, BaseOrigintScenarioRoleAction action) {{
            if (action == null) return;
            if (!actionPool.TryGetValue(id, out var pool)) return;

            // O(1) でアクティブセットから外し、未使用スタックに戻す
            if (pool.ActiveSet.Remove(action)) {{
                pool.FreeStack.Push(action);
            }}
        }}

        public static void AllClear() {{
            actionPool.Clear();
        }}
    }}
}}

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
using GameCore.Scenario;
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
    
    public void SetUpExecuteData(ScenarioExecuteData value_data)
    {
        executeData = value_data;
    }
    
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

    public async UniTask OnFinalizeAsync(bool is_event_change,bool is_event_group_change,bool is_event_sub_group_change,CancellationTokenSource ct)
    {
        if (IsMaxReached()) return;

        var find = FindGroupActionList(executeGroupID).First();
        var subFind = find.FindSubGroupActionList(executeSubGroupID);
        var tasks = subFind.Select(action => action.OnFinalizeAsync(executeData, ct)).ToArray();
        await UniTask.WhenAll(tasks).AttachExternalCancellation(ct.Token);

        if(!is_event_change || !is_event_group_change || !is_event_sub_group_change)
        {
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
    }
    
    public void AllRelease()
    {
        executeGroupID = executeSubGroupID = 1;
        scenarioActionList.Clear();
        ScenarioRoleFactory.AllClear();
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
using System.Linq;
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


    // 旧IsStartUp/IsCompleted/IsOneExecute/IsReleaseは廃止。
    // 同期・非同期それぞれ専用のフラグ(両方trueで「そのフェーズ完了」)から算出する。
    public bool IsStartUp => action != null && action.IsEnter && action.IsEnterAsync;
    public bool IsRelease => action != null && action.IsFinish && action.IsFinishAsync;
    public bool IsCompleted => action != null && action.IsUpdate && action.IsUpdateAsync;
    public bool IsOneCompleted => action != null && action.IsOneUpdate && action.IsOneUpdateAsync;

    public void SetUp(ScenarioRoleID id, BinaryReader reader)
    {
        roleData = ScenarioRoleFactory.CreateRoleData(id);
        roleData.ReadBinary(reader);
    }

    // 使い終わったRoleActionをプールへ返却する(項目3: 再利用)。
    // 自動では呼ばれないため、シナリオ完了時など呼び出し側で明示的に呼ぶ。
    public void Release()
    {
        if (action == null || roleData == null) return;
        ScenarioRoleFactory.ReleaseRoleAction(roleData.RoleID, action);
        action = null;
    }


    


    public async UniTask OnInitializeAsync(ScenarioExecuteData executeData,CancellationTokenSource ct)
    {
        action = await ScenarioRoleFactory.CreateRoleActionAsync(roleData, ct.Token);
        if (IsStartUp)
        {
            await UniTask.Yield(ct.Token);
            return;
        }
        await action.OnInitializeAsync(executeData,ct);
        action.OnInitialize(executeData, ct);
        
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
        Release();
        
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
            await UniTask.Yield(PlayerLoopTiming.Update,ct.Token);
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
            var find = _events.Find(data => data.EventName == eventName);
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
    private bool is_event_group_change = false;
    private bool is_event_sub_group_change = false;

    public override void AwakeSingleton()
    {
        base.AwakeSingleton();
        ScenarioEventBinaryHeader.ReadHeaderAsync(() =>
        {
            IsHeaderLoad = true;
        }, addressable: SupportFiles.ADDRESSABLE_CHECK).Forget();
    }

    public void SetExecuteGroupID(int value)
    {
        master?.SetExecuteGroupID(value);
        master?.SetExecuteSubGroupID(1);
        is_event_group_change = true;
    }
    public void SetExecuteSubGroupID(int value)
    {
        master?.SetExecuteSubGroupID(value);
        is_event_sub_group_change = true;
    }
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
        ScenarioExecuteData value_execute_data = null,
        CancellationTokenSource cts = null)
    {
        using var localCts = new CancellationTokenSource();
        using var linkedCts = cts != null
            ? CancellationTokenSource.CreateLinkedTokenSource(localCts.Token, cts.Token, this.GetCancellationTokenOnDestroy())
            : CancellationTokenSource.CreateLinkedTokenSource(localCts.Token, this.GetCancellationTokenOnDestroy());


        event_play_name = eventName;
        event_sub_name = eventSubName;
        is_event_change = is_event_group_change = is_event_sub_group_change = false;
        
        if(value_execute_data != null)
        {
            master.SetUpExecuteData(value_execute_data);
        }


        while(IsHeaderLoad == false)
        {
            await UniTask.Yield(cts.Token);
        }

        try
        {
            while ((!master.IsExecuteFinish || (is_event_change || is_event_group_change)) && !linkedCts.IsCancellationRequested)
            {
                master.AllRelease();
                is_event_change = is_event_group_change = is_event_sub_group_change = false;

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
            is_event_change = is_event_group_change = is_event_sub_group_change = false;
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
            await master.OnFinalizeAsync(is_event_change,is_event_group_change,is_event_sub_group_change,token);

            if(is_event_change || is_event_group_change) break;

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
    class_dir = os.path.join(DATA_DIR, 'class_data')
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

# CustomClassData のフィールド一覧(name.customclass.json由来)を、role-form-schema と
# 同じ形の subFields に変換する(bit/color/bezier や入れ子のCustomClassDataにも対応する再帰)。
def _build_custom_class_subfields(fields, custom_info, depth, max_depth):
    if depth > max_depth:
        return []
    custom_class_list = custom_info['custom_class_list']
    custom_class_schemas = custom_info['custom_class_schemas']
    result = []
    for f in fields or []:
        sub = {
            "name": f['name'],
            "label": f.get('name'),
            "arraySize": f.get('arraySize', 0),
            "description": f.get('description', ''),
            "type": f['type'],
        }
        if f['type'] in ('bit', 'color', 'bezier', 'dictionary'):
            sub['options'] = f.get('options', {})
        elif f['type'] in custom_class_list:
            sub['subFields'] = _build_custom_class_subfields(
                custom_class_schemas.get(f['type'], []), custom_info, depth + 1, max_depth
            )
        result.append(sub)
    return result


# generate_role_form_schema (全考慮版)
# bit/color/bezier、CustomClassData・CustomClassDataID参照にも対応する。
def _get_class_data_id_options(table_name, data_dir=None):
    """class_data_id テーブル(table_name)の現在の行の識別子一覧(enum_property)を返す。
    Transaction DSL(Lua風テキスト)の予測変換・値検証(coerceValueTokens)で
    class_data_id型フィールドの候補として使うため、generate_role_form_schema から呼ばれる。
    _resolve_prefill_members() と同じパス規約(フォルダ名は末尾のIDを除いたもの)を用いる。"""
    data_dir = data_dir or DATA_DIR
    class_id_path = os.path.join(data_dir, CLASS_DATA_ID, table_name.replace("ID", ""), f"{table_name}.json")
    if not os.path.exists(class_id_path):
        return []
    try:
        with open(class_id_path, 'r', encoding='utf-8') as f:
            table_data = json.load(f)
        return [r.get('enum_property') for r in table_data.get('rows', []) if r.get('enum_property')]
    except Exception:
        return []


def generate_role_form_schema(role_name, data_dir, depth=0, max_depth=3, _custom_info=None):
    if depth > max_depth:
        return {"fields": [], "error": "Max depth reached"}

    role_path = os.path.join(data_dir, SCENARIO_ROLE, f"{role_name}", f"{role_name}.json")
    if not os.path.exists(role_path):
        return None
    with open(role_path, 'r', encoding='utf-8') as f:
        role_json = json.load(f)
        role_data = role_json.get('data', [])
        branch_type = role_json.get('branchType', 'General')

    # CustomClassData/CustomClassDataID の一覧・スキーマは1回だけ取得して再帰呼び出しに使い回す
    custom_info = _custom_info or customclassdata.get_extended_type_lists()
    custom_class_list = custom_info['custom_class_list']
    custom_class_id_list = custom_info['custom_class_id_list']
    custom_class_schemas = custom_info['custom_class_schemas']

    _, _, enum_names, class_names, class_id_names = get_type_lists()

    schema = {"fields": [], "branchType": branch_type}

    for var in role_data:
        field = {"name": var['name'], "label": var['name'], "arraySize": var.get("arraySize", 0), "description": var.get('description', '')}
        # フィールドに保存済みのデフォルト値があれば渡す(無ければキー自体を付けない)。
        # フロント(BaseRoleInputForm.js)はこれをinitialDataより優先度低く、
        # 型ごとの汎用初期値(getDefaultValue)より優先度高く使う。
        if 'default' in var and var['default'] is not None:
            field['default'] = var['default']
        var_type = var['type']

        # bit / color / bezier / dictionary: 値編集に必要な options をそのままフロントへ渡す
        # voice_ref: Voice専用Role(VoiceLine)専用の特殊型。通常のRoleフィールド
        # エディタでは選ばせず、story_setting.ensure_voice_role() が自動生成する
        # VoiceLineロールでのみ使う。フロント(BaseRoleInputForm.js)側で、
        # そのサブイベントの物語設定のvoice_series_idから絞り込んだSoundID一覧を
        # 選ぶドロップダウンとして特別描画する。
        if var_type in ('bit', 'color', 'bezier', 'dictionary', 'voice_ref'):
            field['type'] = var_type
            field['options'] = var.get('options', {})

        # 各数値型を個別に割り当て
        elif var_type in ['int', 'float', 'double', 'short', 'long', 'decimal', 'byte', 'char']:
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
        elif var_type in enum_names:
            field['type'] = var_type
            enum_values = get_enum_values()
            if var_type in enum_values:
                # enum項目のJSON構造は {"property": "...", "value": N, "description": "..."} であり、
                # "name"というキーは存在しない(class_data.py の generate_enum_files 参照)。
                # 以前はitem.get('name', '')としていたため候補が常に空文字列になり、
                # Transaction DSL(Lua風テキスト)の予測変換に一切出てこなかった。
                field['options'] = [item.get('property', '') for item in enum_values[var_type] if item.get('property')]
            else:
                field['options'] = []
                field['warning'] = 'Enum options not found'

        # CustomClassDataID: class_data_id と同じくID参照。値候補はフロント側が
        # /api/custom-class-data-id から取得するので、typeだけ渡せば十分。
        # ※Transaction DSL(Lua風テキスト)の予測変換では、GUI側のような専用フェッチが
        # できないため、この型の予測変換は現状未対応(customclassdata.py側の行データ
        # 構造にここから安全にアクセスする手段が無いため)。
        elif var_type in custom_class_id_list:
            field['type'] = var_type

        # CustomClassData: ネストしたオブジェクト。フロントは通常
        # /api/custom-class-data-type-options から取得した custom_class_schemas を使って
        # 描画するが、バックエンド側のスキーマにも参考として subFields を載せておく。
        elif var_type in custom_class_list:
            field['type'] = var_type
            field['subFields'] = _build_custom_class_subfields(
                custom_class_schemas.get(var_type, []), custom_info, depth + 1, max_depth
            )

        # class_data_id: IDテーブル参照(値候補はフロントが/api/class-data-idから取得)
        elif var_type in class_id_names:
            field['type'] = var_type
            # Transaction DSL(Lua風テキスト)側の予測変換・値検証用に、現在の行の
            # 識別子一覧(enum_property)をoptionsとして渡す(GUI側は従来通り
            # /api/class-data-idから取得するため、ここを追加してもGUI側の挙動は変わらない)。
            field['options'] = _get_class_data_id_options(var_type, data_dir)

        # class_data: ネストしたClassData
        elif var_type in class_names:
            field['type'] = var_type
            sub_schema = generate_role_form_schema(var_type, data_dir, depth + 1, max_depth, custom_info)
            field['subFields'] = sub_schema['fields'] if sub_schema else []

        else:
            field['type'] = var_type  # 未知型でもそのまま

        if var.get('arraySize', 0) > 0:
            field['isArray'] = True
            field['arraySize'] = var['arraySize']

        schema['fields'].append(field)

    return schema


# ============================================================
# Roleフィールドの「デフォルト値」保存
# ------------------------------------------------------------
# Transactionのデータ入力フォーム上で「このフィールドの値をデフォルトとして
# 保存」した際に呼ばれる。scenario_role/<RoleName>/<RoleName>.jsonの該当
# フィールド定義に default キーとして書き込む。以後、このRoleを新規に
# シナリオへ追加した際の初期値として使われる(generate_role_form_schema →
# BaseRoleInputForm.getDefaultValueの代わりにfield.defaultが使われる)。
# 既存のシナリオイベントに既に置かれているRoleのデータには影響しない
# (initialItemが優先されるため)。
# ============================================================
def save_role_field_default(role_name, field_name, value, data_dir=None):
    data_dir = data_dir or DATA_DIR
    role_path = os.path.join(data_dir, SCENARIO_ROLE, f"{role_name}", f"{role_name}.json")
    if not os.path.exists(role_path):
        return {"error": f"Role not found: {role_name}"}
    with open(role_path, 'r', encoding='utf-8') as f:
        role_json = json.load(f)

    found = False
    for var in role_json.get('data', []):
        if var.get('name') == field_name:
            var['default'] = value
            found = True
            break
    if not found:
        return {"error": f"Field not found: {role_name}.{field_name}"}

    with open(role_path, 'w', encoding='utf-8') as f:
        json.dump(role_json, f, ensure_ascii=False, indent=2)

    # 既に生成済みのスキーマキャッシュ(フロント側 schemaCache/backend側があれば)は
    # 呼び出し元(Flaskルート)でinvalidate_role_schema_cache的な処理があるなら
    # ここではなくルート側で対応する想定。
    return {"message": f"{role_name}.{field_name} のデフォルト値を保存しました", "default": value}


def clear_role_field_default(role_name, field_name, data_dir=None):
    """保存済みデフォルト値を削除し、型ごとの汎用初期値に戻す。"""
    data_dir = data_dir or DATA_DIR
    role_path = os.path.join(data_dir, SCENARIO_ROLE, f"{role_name}", f"{role_name}.json")
    if not os.path.exists(role_path):
        return {"error": f"Role not found: {role_name}"}
    with open(role_path, 'r', encoding='utf-8') as f:
        role_json = json.load(f)

    found = False
    for var in role_json.get('data', []):
        if var.get('name') == field_name:
            var.pop('default', None)
            found = True
            break
    if not found:
        return {"error": f"Field not found: {role_name}.{field_name}"}

    with open(role_path, 'w', encoding='utf-8') as f:
        json.dump(role_json, f, ensure_ascii=False, indent=2)
    return {"message": f"{role_name}.{field_name} のデフォルト値をクリアしました"}


# ============================================================
# 仕様書項目5(追記分): scenario_role / scenario_transaction 側のプリフィル同期。
# class_data_id.py・matrix.pyと同じ規約(options.prefillSourceName / keyType+prefillKeys)を
# ロールのフィールドデータ(イベントJSON内 node.data.roles[].data)に対して適用する。
# ============================================================
def _default_value_for_prefill_sync_scenario(field_type):
    t = (field_type or '').replace('[]', '')
    if t in ('int', 'uint'):
        return 0
    if t in ('float', 'double'):
        return 0.0
    if t == 'bool':
        return False
    if t == 'string':
        return ''
    return None


def _resolve_prefill_members(source_name):
    """source_name(Enum名 or ClassDataIDテーブル名)の現在のメンバー名一覧を、対応するJSONから直接解決する。
    fix_all_events()からの安全網呼び出し用(呼び出し元がcurrent_membersを持っていない場合に使う)。"""
    # Enumとして探す
    enum_path = os.path.join(DATA_DIR, 'enum', source_name, f"{source_name}.json")
    if os.path.exists(enum_path):
        try:
            with open(enum_path, 'r', encoding='utf-8') as f:
                items = json.load(f)
            return [item.get('property') for item in items if isinstance(item, dict) and item.get('property')]
        except Exception:
            pass
    # ClassDataIDテーブルとして探す
    class_id_path = os.path.join(DATA_DIR, CLASS_DATA_ID, source_name.replace("ID", ""), f"{source_name}.json")
    if os.path.exists(class_id_path):
        try:
            with open(class_id_path, 'r', encoding='utf-8') as f:
                table_data = json.load(f)
            return [r.get('enum_property') for r in table_data.get('rows', []) if r.get('enum_property')]
        except Exception:
            pass
    return None  # 解決できない場合は同期しない(誤って空扱いで消さないため)


def _load_role_field_meta():
    """role名 -> {field_name: {'type':..., 'options':...}} のマップを構築する"""
    role_field_meta = {}
    role_dir = os.path.join(DATA_DIR, SCENARIO_ROLE)
    for role_file in glob.glob(os.path.join(role_dir, '*', '*.json')):
        role_name = os.path.basename(os.path.dirname(role_file))
        try:
            with open(role_file, 'r', encoding='utf-8') as f:
                schema_data = json.load(f)
            fields = schema_data.get('data', [])
            role_field_meta[role_name] = {
                field['name']: {'type': field.get('type', ''), 'options': field.get('options') or {}}
                for field in fields if isinstance(field, dict) and field.get('name')
            }
        except Exception:
            continue
    return role_field_meta


def _sync_prefill_role_list(roles, role_field_meta, class_schemas, source_name, current_members):
    """rolesリスト内のprefill対象フィールドをsource_name+current_membersに同期する。
    class_data_id.pyの共有再帰ロジックを使うため、ネストしたClassData型フィールドの中まで
    自動的に辿ってprefillを同期できる。戻り値: 変更有無。"""
    changed = False
    for role in roles:
        role_name = role.get('name')
        field_meta = role_field_meta.get(role_name, {})
        for field in role.get('data', []):
            meta = field_meta.get(field.get('name'))
            if not meta:
                continue
            field_changed, new_val = class_data_id_api.fix_prefill_in_raw_value(
                field.get('value'), meta.get('type') or '', meta.get('options') or {},
                class_schemas, source_name, current_members
            )
            if field_changed:
                field['value'] = new_val
                changed = True
    return changed


def _collect_prefill_sources(role_field_meta, class_schemas):
    """role_field_meta(トップレベル)から使われているprefillソース名の集合を集める。
    ネストしたClassData型フィールドの中まで再帰して収集する(安全網同期で、どのソースを
    解決すればよいかを事前に洗い出すために使う)。"""
    sources = set()
    visited_types = set()

    def walk_type(field_type, options):
        ft = field_type or ''
        opts = options or {}
        if ft.endswith('[]'):
            base_type = ft[:-2]
            if opts.get('prefillSourceName'):
                sources.add(opts['prefillSourceName'])
            walk_type(base_type, None)
        elif ft == 'dictionary':
            if opts.get('keyType') and opts.get('prefillKeys'):
                sources.add(opts['keyType'])
            value_type = opts.get('valueType')
            if value_type:
                value_array_size = opts.get('valueArraySize', 0)
                walk_type(f"{value_type}[]" if value_array_size else value_type, opts.get('valueOptions'))
        elif ft in class_schemas and ft not in visited_types:
            visited_types.add(ft)
            for f in class_schemas[ft]:
                sub_arraysize = f.get('arraySize', 0) or 0
                sub_type = f.get('type', '')
                full = f"{sub_type}[]" if sub_arraysize != 0 else sub_type
                walk_type(full, f.get('options'))

    for role_name, fields in role_field_meta.items():
        for fname, meta in fields.items():
            walk_type(meta.get('type'), meta.get('options'))

    return sources


def _walk_event_roles(event_data, visit_fn):
    """イベントJSON内の全roles(ネストしたsubgroups含む)を辿ってvisit_fn(roles)を呼び、
    1つでもTrueを返せばchangedとする。fix_all_eventsと同じtraversal。"""
    changed = False
    subgroups = event_data.get('subgroups', {})
    if not isinstance(subgroups, dict):
        return changed
    for sub_group in subgroups.values():
        if not isinstance(sub_group, dict):
            continue
        for node in sub_group.get('nodes', []):
            roles = node.get('data', {}).get('roles', [])
            changed = visit_fn(roles) or changed

            inner_subgroups = node.get('data', {}).get('subgroups', {})
            if not isinstance(inner_subgroups, dict):
                continue
            for inner_sub in inner_subgroups.values():
                inner_nodes = inner_sub.get('nodes', []) if isinstance(inner_sub, dict) else []
                for inner_node in inner_nodes:
                    inner_roles = inner_node.get('data', {}).get('roles', [])
                    changed = visit_fn(inner_roles) or changed
    return changed


def sync_prefill_dependents_scenario(source_name, current_members):
    """class_data_id.py / class_data.py からカスケード呼び出しされる即時同期。
    source_name(Enum名 or ClassDataIDテーブル名)のメンバー構成(current_members)が変わった際、
    それをprefillSourceName / (keyType+prefillKeys)として参照している全イベントJSON内の
    ロールフィールドデータを同期する。ネストしたClassData型フィールドの中まで再帰対応。"""
    try:
        role_field_meta = _load_role_field_meta()
        class_schemas = class_data_id_api.load_class_schemas()
        event_dir = os.path.join(DATA_DIR, SCENARIO_EVENT)
        for event_file in glob.glob(os.path.join(event_dir, '*', '*.json')):
            try:
                with open(event_file, 'r', encoding='utf-8') as f:
                    event_data = json.load(f)
            except Exception:
                continue

            changed = _walk_event_roles(
                event_data,
                lambda roles: _sync_prefill_role_list(roles, role_field_meta, class_schemas, source_name, current_members)
            )

            if changed:
                with open(event_file, 'w', encoding='utf-8') as f:
                    json.dump(event_data, f, ensure_ascii=False, indent=2)
                logger.info(f"prefill同期(scenario): {os.path.basename(event_file)} を {source_name} のメンバー変更に追従させました")
    except Exception as e:
        logger.error(f"prefill同期処理エラー(scenario, source={source_name}): {str(e)}")


def sync_all_prefill_scenario_safety_net():
    """安全網: 個別のカスケード通知に頼らず、既存のfix_all_events()と同じタイミング
    (バイナリ生成前)で全イベント×全roleフィールドのprefill設定を都度その場で解決して同期する。
    ネストしたClassData型フィールドも含め、実際に使われている参照元(Enum/ClassDataID)を
    事前に洗い出し、参照元ごとに全イベントを1パスずつ同期する(参照元が複数あっても正しく解決するため)。
    これにより、何らかの理由でカスケード通知が漏れた場合でも、バイナリ生成前には必ず
    最新のメンバー構成に揃った状態になる。"""
    try:
        role_field_meta = _load_role_field_meta()
        class_schemas = class_data_id_api.load_class_schemas()
        sources = _collect_prefill_sources(role_field_meta, class_schemas)
        if not sources:
            return
        event_dir = os.path.join(DATA_DIR, SCENARIO_EVENT)
        event_files = glob.glob(os.path.join(event_dir, '*', '*.json'))

        for source_name in sources:
            members = _resolve_prefill_members(source_name)
            if members is None:
                continue
            for event_file in event_files:
                try:
                    with open(event_file, 'r', encoding='utf-8') as f:
                        event_data = json.load(f)
                except Exception:
                    continue

                changed = _walk_event_roles(
                    event_data,
                    lambda roles: _sync_prefill_role_list(roles, role_field_meta, class_schemas, source_name, members)
                )

                if changed:
                    with open(event_file, 'w', encoding='utf-8') as f:
                        json.dump(event_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"prefill安全網同期処理エラー: {str(e)}")


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
    elif type_lower == 'dictionary':
        return {"entries": []}
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
            if len(schema_data) == 0:
                continue
            fields = schema_data.get('data', [])
            if fields is None:
                continue
            role_schemas[role_name] = {
                field['name']: {'type': field['type'], 'default': field.get('default')}
                for field in fields
            }

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

    # 仕様書項目5(追記分)の安全網: prefill設定を持つ全フィールドを、その場で参照元の
    # 最新メンバー構成に合わせて同期する。fix_all_events()は既にバイナリ生成前に必ず
    # 呼ばれているため、個別のカスケード通知に漏れがあってもここで最終的に整合する。
    sync_all_prefill_scenario_safety_net()

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
        # (保存済みのデフォルト値があればそれを優先し、無ければ型ごとの汎用初期値)
        for field_name, field_meta in schema_fields.items():
            if field_name not in current_data:
                updated = True
                default_value = field_meta.get('default')
                initial_value = default_value if default_value is not None else get_initial_value(field_meta.get('type'))
                new_data.append({"name": field_name, "value": initial_value})
        
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
#
# 実際のバイナリ書き込みは pythonSrc/customclassdata.py 側の実装(_write_custom_single_value /
# _write_custom_field_value)に委譲する。理由:
#   - あちら側はすでに bit/color/bezier、CustomClassData・CustomClassDataID、通常の
#     enum/classData/classDataID を正しくバイナリ化できており、C#側の生成コード
#     (generate_csharp_field / generate_custom_field の ReadBinary)ともバイト単位で
#     整合が取れている。
#   - 旧実装には (a) NaN/Infの値でバイト自体を書かずスキップしてしまい後続フィールドの
#     オフセットがずれる、(b) byte/short/longを全部4バイトint扱いで書いてしまいC#側の
#     ReadByte/ReadInt16/ReadInt64と桁数が合わない、(c) ClassData型のフィールドが複数ある
#     とき最初の1個を書いた時点で return してしまい残りのフィールドが書き込まれない、
#     という3つの実害あるバグがあったため、書き直すよりも「動作確認済みの実装を再利用する」
#     方が安全。
# Vector4 のみ customclassdata 側に無い型のため、ここで個別対応する。
def build_scenario_type_info(enum_list, class_list, class_data_id_list):
    """pack_value/write_field_value で使う type_info を組み立てる。
    CustomClassData・CustomClassDataIDの一覧/スキーマは customclassdata 側から取得する。"""
    ext = customclassdata.get_extended_type_lists()
    return {
        'enum_list': enum_list,
        'class_list': class_list,
        'class_data_id_list': class_data_id_list,
        'custom_class_list': ext['custom_class_list'],
        'custom_class_id_list': ext['custom_class_id_list'],
        'custom_class_schemas': ext['custom_class_schemas'],
    }


def pack_value(value, type_, basic_types, unity_types, enum_list, class_list, class_data_id_list,
               enum_data, class_data_id, class_data, options=None, type_info=None):
    """1つの値をバイナリへ変換して返す(後方互換のための薄いラッパー)。
    type_info を渡さない場合は enum_list/class_list/class_data_id_list のみから組み立てる
    (この場合 CustomClassData/CustomClassDataID・bit/color/bezier は非対応になる)。"""
    info = type_info or {
        'enum_list': enum_list,
        'class_list': class_list,
        'class_data_id_list': class_data_id_list,
        'custom_class_list': [],
        'custom_class_id_list': [],
        'custom_class_schemas': {},
    }
    type_str = (type_ or '').replace('[]', '')
    buf = io.BytesIO()
    if type_str == 'Vector4':
        x, y, z, w = value if isinstance(value, (list, tuple)) and len(value) >= 4 else [0.0, 0.0, 0.0, 0.0]
        buf.write(struct.pack('ffff', float(x or 0), float(y or 0), float(z or 0), float(w or 0)))
    elif type_str == 'dictionary':
        # ★ dictionary型はここで自己完結して処理する(customclassdata側への委譲なし)。
        #   options.valueArraySize (0=単一 / -1=可変長List / N=固定長配列) を見て
        #   pack_value を再帰呼び出しするため、Dictionary<T,List<~>> や
        #   Dictionary<T,Dictionary<TE,~>> のような入れ子にも対応できる。
        opts = options or {}
        key_type = opts.get('keyType', 'int')
        value_type = opts.get('valueType', 'int')
        value_array_size = opts.get('valueArraySize', 0) or 0
        value_options = opts.get('valueOptions') or {}
        entries = value.get('entries', []) if isinstance(value, dict) else []

        buf.write(struct.pack('i', len(entries)))
        for entry in entries:
            k = entry.get('key') if isinstance(entry, dict) else None
            v = entry.get('value') if isinstance(entry, dict) else None

            buf.write(pack_value(k, key_type, basic_types, unity_types, enum_list, class_list, class_data_id_list,
                                  enum_data, class_data_id, class_data, options=None, type_info=info))

            if value_array_size == -1:
                values = v if isinstance(v, list) else []
                buf.write(struct.pack('i', len(values)))
                for vv in values:
                    buf.write(pack_value(vv, value_type, basic_types, unity_types, enum_list, class_list, class_data_id_list,
                                          enum_data, class_data_id, class_data, options=value_options, type_info=info))
            elif value_array_size > 0:
                values = v if isinstance(v, list) else []
                for i in range(value_array_size):
                    vv = values[i] if i < len(values) else None
                    buf.write(pack_value(vv, value_type, basic_types, unity_types, enum_list, class_list, class_data_id_list,
                                          enum_data, class_data_id, class_data, options=value_options, type_info=info))
            else:
                buf.write(pack_value(v, value_type, basic_types, unity_types, enum_list, class_list, class_data_id_list,
                                      enum_data, class_data_id, class_data, options=value_options, type_info=info))
    else:
        customclassdata._write_custom_single_value(buf, value, type_str, options or {}, info)
    return buf.getvalue()


def write_field_value(buf, value, type_str, array_size, options, type_info):
    """schema 1フィールド分(配列/固定長配列/単一値)をバイナリとして buf(bytearray)に追記する。
    generate_all_event_bin 側の roles / inner_roles 双方から共通で呼び出す。"""
    type_str = (type_str or '').replace('[]', '')
    array_size = array_size or 0

    def pack_single(v):
        return pack_value(v, type_str, None, None, None, None, None, None, None, None,
                           options=options, type_info=type_info)

    if array_size == -1:
        values = value if isinstance(value, list) else []
        buf.extend(struct.pack('i', len(values)))
        for v in values:
            buf.extend(pack_single(v))
    elif array_size > 0:
        values = value if isinstance(value, list) else []
        for i in range(array_size):
            buf.extend(pack_single(values[i] if i < len(values) else None))
    else:
        buf.extend(pack_single(value))

def generate_all_event_bin(basic_types, unity_types, enum_list, class_list, class_data_id_list,enum_data,class_data_id,class_data ):
    all_bin_path = os.path.join(DATA_DIR, SCENARIO_EVENT, 'all_events.bytes')
    header = bytearray()
    data_sections = bytearray()

    # bit/color/bezier・CustomClassData・CustomClassDataID を含めたバイナリ書き込みに使う type_info
    type_info = build_scenario_type_info(enum_list, class_list, class_data_id_list)

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
    
 # 2. Event + SubEvent headers（C#側がSeekせず直列に読むため、subEvent情報もheaderにインラインで書く）
    sub_offset_positions_by_event = {}  # event_id -> [(sub_id, pos_in_header), ...]

    for event in events:
        event_id = event.get('id', '')
        id_encoded = event_id.encode('utf-8')
        name_encoded = event.get('name', '').encode('utf-8')
        header.extend(struct.pack('i', len(id_encoded)))
        header.extend(id_encoded)
        header.extend(struct.pack('i', len(name_encoded)))
        header.extend(name_encoded)
        offset_pos = len(header)
        header.extend(struct.pack('q', 0))  # event offset placeholder
        event_offset_positions.append((event_id, offset_pos))
        logger.debug(f"Event header: ID={event_id}, Name={event.get('name', '')}, OffsetPos={offset_pos}")

        subEvents = event.get('subEvents', [])
        header.extend(struct.pack('i', len(subEvents)))  # SubEvent count
        logger.debug(f"Writing subEvent count for {event_id}: {len(subEvents)}")

        sub_positions = []
        for sub_data in subEvents:
            sub_id = str(sub_data.get('subId', 0))
            sub_name_encoded = sub_data.get('name', '').encode('utf-8')
            header.extend(struct.pack('i', int(sub_id)))
            header.extend(struct.pack('i', len(sub_name_encoded)))
            header.extend(sub_name_encoded)
            sub_offset_pos = len(header)
            header.extend(struct.pack('q', 0))  # subEvent offset placeholder
            sub_positions.append((sub_id, sub_offset_pos))
            logger.debug(f"SubEvent header: ID={sub_id}, Name={sub_data.get('name', '')}, OffsetPos={sub_offset_pos}")

        sub_offset_positions_by_event[event_id] = sub_positions

    # 3. Load role schemas（変更なし。以下は元のコードのまま）
    role_schemas = {
        'TalkText': [
            {'name': 'text', 'type': 'string', 'arraySize': 0, 'options': {}},
            {'name': 'name', 'type': 'string', 'arraySize': 0, 'options': {}},
        ]  # Temporary schema
    }
    role_dir = os.path.join(DATA_DIR, SCENARIO_ROLE)
    for role_file in glob.glob(os.path.join(role_dir, '*', '*.json')):
        role_name = os.path.basename(os.path.dirname(role_file))
        try:
            with open(role_file, 'r', encoding='utf-8') as f:
                schema_data = json.load(f)
                fields = schema_data.get('data', [])
                role_schemas[role_name] = [
                    {
                        'name': field['name'],
                        'type': field['type'],
                        'arraySize': field.get('arraySize', 0),
                        'options': field.get('options', {}),
                    }
                    for field in fields
                ]
            logger.debug(f"Loaded role schema: {role_name}")
        except Exception as e:
            logger.error(f"Failed to load role file {role_file}: {e}")

    def write_role_fields(sub_section, role, schema_fields):
        """1つのRoleが持つフィールド値をすべてバイナリへ書き込む(roles/inner_roles共通)。"""
        fields = role.get('data', [])
        for field_idx in range(min(len(fields), len(schema_fields))):
            field = fields[field_idx]
            schema_field = schema_fields[field_idx]
            field_type = schema_field['type']
            array_size = field.get('arraySize', schema_field.get('arraySize', 0))
            options = field.get('options', schema_field.get('options', {}))
            write_field_value(sub_section, field.get('value', ''), field_type, array_size, options, type_info)

    # 4. Data section generation（役割/グループ実データのみ。ランタイムのSeek対象。headerには含めない）
    sub_offsets = {}  # (event_id, sub_id) -> absolute offset

    for event in events:
        event_id = event.get('id', '')
        event_offset = len(header) + len(data_sections)
        offsets[event_id] = event_offset
        logger.debug(f"Event {event_id} data at offset: {event_offset}")

        subEvents = event.get('subEvents', [])
        for sub_data in subEvents:
            sub_id = str(sub_data.get('subId', 0))
            sub_offset = len(header) + len(data_sections)
            sub_offsets[(event_id, sub_id)] = sub_offset
            logger.debug(f"SubEvent {event_id}/{sub_id} data at offset: {sub_offset}")

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
                        write_role_fields(sub_section, role, schema_fields)

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
                            write_role_fields(sub_section, inner_role, inner_schema_fields)

            data_sections.extend(sub_section)

    # Event offset のパッチ
    for event_id, pos in event_offset_positions:
        logger.debug(f"Patching Event {event_id} offset: {offsets[event_id]} at position {pos}")
        header[pos:pos+8] = struct.pack('q', offsets[event_id])

    # SubEvent offset のパッチ（headerに直接パッチする点に注意）
    for event in events:
        event_id = event.get('id', '')
        for sub_id, pos_in_header in sub_offset_positions_by_event[event_id]:
            offset_value = sub_offsets[(event_id, sub_id)]
            logger.debug(f"Patching SubEvent {event_id}/{sub_id} offset: {offset_value} at position {pos_in_header}")
            header[pos_in_header:pos_in_header+8] = struct.pack('q', offset_value)
    
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
        scenario_list_path = os.path.join(DATA_DIR, SCENARIO_EVENT, "scenario_event_list.json")
        try:
            with open(scenario_list_path, "r", encoding="utf-8") as f:
                scenario_list = json.load(f)
        except FileNotFoundError:
            print(f"エラー: {scenario_list_path} が見つかりません。")
            return
        except json.JSONDecodeError:
            print(f"エラー: {scenario_list_path} のJSON形式が不正です。")
            return

        # --- 手動追加カラムの退避 ---
        # ScenarioEvent.jsonは毎回作り直すが、event_id/sub_event_id以外のカラム(手動で
        # 追加された想定)は既存ファイルから引き継ぐ。行の紐付けは「親イベントid」＋
        # 「サブイベントid(無ければ名前にフォールバック)」の安定キー(_scenario_key)で
        # 行うことで、イベント名/サブイベント名がリネームされてもデータが消えないようにする。
        # 初回移行時(まだ_scenario_keyを持たない旧データ)は event_id/sub_event_id の
        # 値一致でフォールバック照合する。
        scenario_event_path = os.path.join(scenario_event_dir, "ScenarioEvent.json")
        manual_columns = []
        old_data_by_key = {}
        old_data_by_name = {}
        try:
            with open(scenario_event_path, "r", encoding="utf-8") as f:
                old_add_data = json.load(f)
            manual_columns = [
                col for col in old_add_data.get("columns", [])
                if col.get("name") not in ("event_id", "sub_event_id")
            ]
            manual_col_names = {col["name"] for col in manual_columns}
            for old_row in old_add_data.get("rows", []):
                old_row_data = old_row.get("data", {})
                manual_values = {k: v for k, v in old_row_data.items() if k in manual_col_names}
                if not manual_values:
                    continue
                scenario_key = old_row.get("_scenario_key")
                if scenario_key is not None:
                    old_data_by_key[tuple(scenario_key)] = manual_values
                # 旧データ(_scenario_key無し)の救済用に、名前ベースのキーでも控えておく
                name_key = (
                    old_row_data.get("event_id", {}).get("value"),
                    old_row_data.get("sub_event_id", {}).get("value"),
                )
                old_data_by_name[name_key] = manual_values
        except (FileNotFoundError, json.JSONDecodeError):
            pass

        # ScenarioEvent.jsonのデータ構造を初期化
        # 以前はeventID/subIDにそれぞれ生の名前を入れていたが、
        # Scenario_{親}_{サブ}(class_data_id側のScenarioタグ配下エントリ)と
        # 紐付く形の単一カラムに変更した(項目6)。
        add_data = {
            "columns": [
                {"name": "event_id", "type": "string", "description" : "イベントID"},
                {"name": "sub_event_id", "type": "string","description" : "サブイベントID"},
            ] + manual_columns,
            "rows": []
        }

        count = 1
        for item in scenario_list:
            # subEventsが存在するかチェック
            if "subEvents" not in item:
                print(f"警告: {item.get('name', '不明')} にsubEventsがありません。スキップします。")
                continue
            for details in item["subEvents"]:
                scenario_value = f"Scenario_{item.get('name', '')}_{details.get('name', '')}"

                # 安定キー: 親イベントid + サブイベントid(無ければ名前にフォールバック)
                scenario_key = [item.get("id"), details.get("id", details.get("name", ""))]
                name_key = (item.get("name", ""), details.get("name", ""))
                matched_manual_values = old_data_by_key.get(tuple(scenario_key))
                if matched_manual_values is None:
                    matched_manual_values = old_data_by_name.get(name_key, {})

                row_data = {
                    "event_id": {"value": item.get('name', ''), "type": "string"},
                    "sub_event_id": {"value": details.get('name', ''), "type": "string"},
                }
                # 手動カラムの値を引き継ぐ(見つからなければ型に応じた初期値で埋める)
                for col in manual_columns:
                    if col["name"] in matched_manual_values:
                        row_data[col["name"]] = matched_manual_values[col["name"]]
                    else:
                        row_data[col["name"]] = {"value": get_initial_value(col.get("type", "string")), "type": col.get("type", "string")}

                add_id_data = {
                    "id": count,
                    "enum_property": f"{item.get('name', '')}_{details.get('name', '')}",
                    "description": f"{item.get('description', '')}_{details.get('name', '')}",
                    "data": row_data,
                    "_scenario_key": scenario_key,
                }
                add_data["rows"].append(add_id_data)
                count += 1

        # ScenarioEvent.jsonに保存
        with open(scenario_event_path, "w", encoding="utf-8") as fw:
            json.dump(add_data, fw, ensure_ascii=False, indent=2)
        print(f"{scenario_event_path} にデータを保存しました。")

        # ScenarioEventのRow.cs/Table.cs/TableID.cs(+py/js)とバイナリも、
        # JSON更新のたびにその場で自動再生成する(手動でC#生成ボタンを押さなくても最新に保つ)。
        class_data_id_api.generate_class_data_id_cs_core("ScenarioEvent", add_data["columns"], add_data["rows"])
        class_data_id_api.generate_binary_core("ScenarioEvent", add_data["columns"], add_data["rows"])

        # 項目7・11: Scenario_{親}() 開始関数・ScenarioExecuteUpdateオーバーロードは
        # class_data_id.py 側の sync_scenario_parent_enum_files() で
        # Scenario_{親}ID enum(assets.py方式)を使って正式に生成される
        # (app.pyのイベント追加・削除・リネーム時に自動で呼ばれる)。

    except Exception as e:
        print(f"予期しないエラーが発生しました: {e}")


def sync_all_scenario_class_data(scenario_events):
    """シナリオイベント(親/サブ)の追加・編集・削除・コピーの度に app.py から呼ばれる
    統合エントリポイント。以下を一括で行う:

      1. ScenarioEvent(全シナリオの索引テーブル)のJSON/Row.cs/Table.cs/TableID.cs/
         バイナリを最新の scenario_event_list.json の内容で再生成する
      2. 各Scenario_{親}(class_data_id側のScenarioタグ配下エントリ)のJSON/Row.cs/
         Table.cs/TableID.cs/バイナリを、追加・リネーム・削除に追従して再生成する
         (もう存在しない親のエントリはファイルごと削除、リネームされた親は
         旧エントリを退避してから新名義へ移行する)
      3. class_data_id_list.json のID採番を
         「Scenario関連以外(既存の並び順維持) → ScenarioEvent → 各Scenarioグループ
         (イベント登録順)」の順に並び替える

    scenario_events: scenario_event_list.json そのままの形
      ([{ "id":..., "name":..., "subEvents":[{"name":...}, ...] }, ...])
    """
    # 1. ScenarioEvent側を最新化(JSON生成 → ScenarioEvent.json → Row/Table/TableID/バイナリ再生成)
    class_id_generate()

    # 2. 各Scenario_{親}を最新化(追加・リネーム・削除への追従 + Row/Table/TableID/バイナリ再生成)
    events = [
        {
            "name": ev["name"],
            "parent": ev["id"],
            "subs": [sub["name"] for sub in ev.get("subEvents", [])],
        }
        for ev in scenario_events
    ]
    result = class_data_id_api.sync_scenario_class_data_ids_core(events)

    # 3. IDの並び替え(Scenario以外は既存順維持 → ScenarioEvent → 各Scenarioグループを登録順で)
    class_data_id_api.reorder_scenario_class_data_ids(events)

    return result
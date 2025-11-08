import json
import os
import socket
import struct
import tkinter as tk
from tkinter import filedialog
import sys
import re
# 既存の定数に追加
# 実行可能ファイルのディレクトリを取得（PyInstaller対応）
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ディレクトリパスをプロジェクトルート基準に設定
DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "data"))
ASSETS_DATA = os.path.join(DATA_DIR, "assets-data")
ANIM_DATA = os.path.join(ASSETS_DATA, 'anim-data')
ANIM_JSON = os.path.join(ANIM_DATA, 'assets_animator.json')

def generate_base():
    if not os.path.exists(ASSETS_DATA):
        os.mkdir(ASSETS_DATA)
    if not os.path.exists(ANIM_DATA):
        os.mkdir(ANIM_DATA)
        
    if not os.path.exists(ANIM_JSON):
        with open(ANIM_JSON,"w",encoding="utf-8") as f:
            json.dump({}, f,ensure_ascii=False, indent=4)
            
    if not os.path.exists(os.path.join(ANIM_DATA,"OriginAnimatorManager.cs")):
        code_str = """
using UnityEngine;

namespace GameCore.GameAnimator
{
    public class OriginAnimatorManager
    {

    }
}

        """
        with open(os.path.join(ANIM_DATA,"OriginAnimatorManager.cs"),"w",encoding="utf-8") as f:
            f.write(code_str)
            
    if not os.path.exists(os.path.join(ANIM_DATA,"BaseAnimatorManager.cs")):
        code_str = """


// ========================================
// GameCore/Animator/AnimatorManager.cs
// ========================================
using System;
using System.Collections.Generic;
using System.Threading;
using Cysharp.Threading.Tasks;
using UnityEngine;
using static GameCore.GameAnimator.HoloListenerAnimatorManager;

namespace GameCore.GameAnimator
{
    public abstract class BaseAnimatorManager<TLayerEnum, TStateEnum,TParam> : OriginAnimatorManager
        where TLayerEnum : Enum
        where TStateEnum : Enum 
        where TParam : class,new()
    {
        // ─────────────────────────────────────
        // 内部クラス：レイヤーごとのステート管理
        // ─────────────────────────────────────
        public class BaseTLayer
        {
            protected int index = -1;
            public Dictionary<TStateEnum, string> stateDict = new();

            public int Index => index;
            public IReadOnlyDictionary<TStateEnum, string> States => stateDict;

            internal void SetIndex(int idx) => index = idx;
        }

        // ─────────────────────────────────────
        // フィールド
        // ─────────────────────────────────────
        protected static Dictionary<TLayerEnum, BaseTLayer> animationKey;
        protected Animator animator;
        public readonly TParam param = new();
        private struct PlayRecord
        {
            public TLayerEnum Layer;
            public TStateEnum State;
            public bool Reverse;
            public float StartNormalizedTime;
            public CancellationTokenSource Cts;
            public Action OnFinish;
        }

        private PlayRecord? current;
        public void CancelUnitasl()
        {
            current?.Cts?.Cancel();
            current?.Cts.Dispose();
        }
        // ─────────────────────────────────────
        // SetUp
        // ─────────────────────────────────────
        public void SetUp(GameObject gameObject)
        {
            if (animator != null)
            {
                return;
            }
            animator = gameObject.GetComponent<Animator>();
            if (animator == null)
            {
                animator = gameObject.GetComponentInChildren<Animator>();
            }
            if (animator == null)
                throw new Exception($"Animator not found on {gameObject.name}");

            KeySetUp();

            int idx = 0;
            foreach (var kvp in animationKey)
                kvp.Value.SetIndex(idx++);
        }

        public void SetUp(Animator value)
        {
            if (animator != null)
            {
                return;
            }
            animator = value;
            KeySetUp();

            int idx = 0;
            foreach (var kvp in animationKey)
                kvp.Value.SetIndex(idx++);
        }

        public abstract void KeySetUp();

        // ─────────────────────────────────────
        // Play
        // ─────────────────────────────────────
        public void PlayAnimation(TStateEnum state, float crossFade = 0.2f, Action onFinish = null, bool reverse = false)
            => PlayAnimationAsync(state, crossFade, onFinish, reverse).Forget();

        public async UniTask PlayAnimationAsync(TStateEnum state, float crossFade = 0.2f,
            Action onFinish = null, bool reverse = false, CancellationTokenSource customCts = null)
        {
            if (!TryGetLayerAndClip(state, out TLayerEnum layer, out string clipName, out int layerIndex))
            {
                Debug.LogError($"[BaseAnimatorManager] AnimationID not registered: {state}");
                onFinish?.Invoke();
                return;
            }

            current?.Cts?.Cancel();
            current?.Cts?.Dispose();

            var cts = customCts != null
                ? CancellationTokenSource.CreateLinkedTokenSource(customCts.Token, animator.gameObject.GetCancellationTokenOnDestroy())
                : CancellationTokenSource.CreateLinkedTokenSource(animator.gameObject.GetCancellationTokenOnDestroy());

            current = new PlayRecord
            {
                Layer = layer,
                State = state,
                Reverse = reverse,
                StartNormalizedTime = reverse ? 1f : 0f,
                Cts = cts,
                OnFinish = onFinish
            };

            if (crossFade > 0f)
                animator.CrossFade(clipName, crossFade, layerIndex, reverse ? 1f : 0f);
            else
                animator.Play(clipName, layerIndex, reverse ? 1f : 0f);

            await WaitAnimationComplete(layerIndex, clipName, reverse, cts.Token);
        }

        private async UniTask WaitAnimationComplete(int layerIndex, string clipName, bool reverse, CancellationToken ct)
        {
            try
            {
                while (!ct.IsCancellationRequested)
                {
                    var info = animator.GetCurrentAnimatorStateInfo(layerIndex);
                    if (info.shortNameHash != Animator.StringToHash(clipName)) break;

                    animator.speed = reverse ? -1f : 1f;

                    float norm = info.normalizedTime % 1f;
                    if (reverse) norm = 1f - norm;
                    if ((reverse && norm <= 0f) || (!reverse && norm >= 1f)) break;

                    await UniTask.Yield(PlayerLoopTiming.Update, ct);
                }
            }
            catch (OperationCanceledException) { }
            finally
            {
                animator.speed = 1f;
                current = null;
                current?.OnFinish?.Invoke();
            }
        }

        // ─────────────────────────────────────
        // 状態取得
        // ─────────────────────────────────────
        public TStateEnum GetCurrentState(TLayerEnum layer)
        {
            if (!animationKey.TryGetValue(layer, out var layerData)) return default;
            if (layerData.Index < 0) return default;

            var info = animator.GetCurrentAnimatorStateInfo(layerData.Index);
            foreach (var kvp in layerData.States)
                if (Animator.StringToHash(kvp.Value) == info.shortNameHash)
                    return kvp.Key;
            return default;
        }

        public bool IsPlaying(TLayerEnum layer)
        {
            if (!animationKey.TryGetValue(layer, out var layerData)) return false;
            if (layerData.Index < 0) return false;

            var info = animator.GetCurrentAnimatorStateInfo(layerData.Index);
            float norm = info.normalizedTime % 1f;
            if (current?.Reverse == true) norm = 1f - norm;
            return norm < 1f;
        }

        public void Stop()
        {
            current?.Cts?.Cancel();
            current?.Cts?.Dispose();
            animator.speed = 1f;
        }

        // ─────────────────────────────────────
        // 内部検索
        // ─────────────────────────────────────
        private bool TryGetLayerAndClip(TStateEnum state, out TLayerEnum layer, out string clipName, out int layerIndex)
        {
            layer = default; clipName = null; layerIndex = -1;

            foreach (var kvp in animationKey)
            {
                if (kvp.Value.States.TryGetValue(state, out clipName))
                {
                    layer = kvp.Key;
                    layerIndex = kvp.Value.Index;
                    return true;
                }
            }
            return false;
        }
    }
}


        

        """
        with open(os.path.join(ANIM_DATA,"BaseAnimatorManager.cs"),"w",encoding="utf-8") as f:
            f.write(code_str)
            
    
    if not os.path.exists(os.path.join(ANIM_DATA,"AnimationParam.cs")):
        code_str = """
using System;
using UnityEngine;
namespace GameCore.GameAnimator
{
    public abstract class AnimationParam<TType, TParamEnum>
        where TType : struct
        where TParamEnum : Enum
    {
        protected Animator animator;
        public void SetAnimator(Animator anim) => animator = anim;
    }


    public sealed class FloatParam<TParamEnum> : AnimationParam<float, TParamEnum>
        where TParamEnum : Enum
    {
        public void Set(TParamEnum param, float value) => animator.SetFloat(param.ToString(), value);
        public float Get(TParamEnum param) => animator.GetFloat(param.ToString());
    }

    public sealed class IntParam<TParamEnum> : AnimationParam<int, TParamEnum>
        where TParamEnum : Enum
    {
        public void Set(TParamEnum param, int value) => animator.SetInteger(param.ToString(), value);
        public int Get(TParamEnum param) => animator.GetInteger(param.ToString());
    }

    public sealed class BoolParam<TParamEnum> : AnimationParam<bool, TParamEnum>
        where TParamEnum : Enum
    {
        public void Set(TParamEnum param, bool value) => animator.SetBool(param.ToString(), value);
        public bool Get(TParamEnum param) => animator.GetBool(param.ToString());
    }

    public sealed class TriggerParam<TParamEnum> : AnimationParam<bool, TParamEnum>
        where TParamEnum : Enum
    {
        public void Trigger(TParamEnum param) => animator.SetTrigger(param.ToString());
    }
}
        """
        with open(os.path.join(ANIM_DATA,"AnimationParam.cs"),"w",encoding="utf-8") as f:
            f.write(code_str)
            
    if not os.path.exists(os.path.join(ANIM_DATA,"OriginAnimatorHub.cs")):
        code_str = """
using UnityEngine;
namespace GameCore.GameAnimator
{
    public class OriginAnimatorHub : MonoBehaviour
    {
        public virtual void SetUp() { }

        public virtual void ReleaseHub() { }
    }
}

        """
        with open(os.path.join(ANIM_DATA,"OriginAnimatorHub.cs"),"w",encoding="utf-8") as f:
            f.write(code_str)
            
    if not os.path.exists(os.path.join(ANIM_DATA,"BaseAnimatorHub.cs")):
        code_str = """
using Cysharp.Threading.Tasks;
using System;
using System.Threading;
using UnityEngine;

namespace GameCore.GameAnimator
{
    public class BaseAnimatorHub<TAnimatorManager, TLayerEnum, TStateEnum,TParam> : OriginAnimatorHub
        where TAnimatorManager : BaseAnimatorManager<TLayerEnum, TStateEnum,TParam>, new()
        where TLayerEnum : struct, Enum
        where TStateEnum : struct, Enum
        where TParam : class,new()
    {
        protected Animator animator;
        protected TAnimatorManager animationManager;

        public override void SetUp()
        {
            animator = GetComponent<Animator>();
            if (animator.Equals(null))
            {
                animator = GetComponentInChildren<Animator>();
            }

            animationManager = new TAnimatorManager();
            animationManager.SetUp(animator);
        }

        public override void ReleaseHub()
        {
            animationManager?.Stop();
        }

        public TParam Param()
        {
            return animationManager.param;
        }

        public void PlayAnimation(TStateEnum state, float crossFade = 0.2f, Action onFinish = null, bool reverse = false)
         => animationManager.PlayAnimation(state, crossFade, onFinish, reverse);

        public async UniTask PlayAnimationAsync(TStateEnum state, float crossFade = 0.2f,
            Action onFinish = null, bool reverse = false, CancellationTokenSource customCts = null)
            => await animationManager.PlayAnimationAsync(state, crossFade, onFinish, reverse);

        public TStateEnum GetCurrentState(TLayerEnum layer) => animationManager.GetCurrentState(layer);

        public bool IsPlaying(TLayerEnum layer) => animationManager.IsPlaying(layer);

        public void Stop() => animationManager.Stop();
    }


}

        
        

        """
        with open(os.path.join(ANIM_DATA,"BaseAnimatorHub.cs"),"w",encoding="utf-8") as f:
            f.write(code_str)
        
# -------------------------------------------------
# インデックス（登録名だけのリスト）管理
# -------------------------------------------------
def load_index() -> list[str]:
    if not os.path.exists(ANIM_JSON):
        return []
    with open(ANIM_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
        return data.get("registered", []) if isinstance(data, dict) else data

def save_index(names: list[str]):
    os.makedirs(ANIM_DATA, exist_ok=True)
    with open(ANIM_JSON, "w", encoding="utf-8") as f:
        json.dump({"registered": sorted(names)}, f, ensure_ascii=False, indent=4)
# -------------------------------------------------
# 個別JSONの保存・読み込み
# -------------------------------------------------
def get_individual_path(name: str) -> str:
    """ ANIM_DATA/{name}/{name}.json """
    safe_name = to_valid_identifier(name)  # ファイルシステム的に安全にする
    dir_path  = os.path.join(ANIM_DATA, safe_name)
    return os.path.join(dir_path, f"{safe_name}.json")

def load_individual(name: str) -> dict:
    path = get_individual_path(name)
    if not os.path.exists(path):
        raise FileNotFoundError(f"{name} の個別JSONが見つかりません")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_individual(name: str, data: dict):
    path = get_individual_path(name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    
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

def select_file(initial_dir, filetypes):
    """
    ファイル選択ダイアログを表示
    """
    root = tk.Tk()
    root.withdraw()
    file_path = filedialog.askopenfilename(initialdir=initial_dir, filetypes=filetypes)
    root.destroy()
    return file_path if file_path else None

# ========================================
# Unity通信でAnimatorController情報取得
# ========================================
def get_animator_controller_info(file_path):
    result = send_to_unity('get_animator_controller_info', {'file_path': file_path})
    if not result or result == "[]":
        return None
    return json.loads(result)

# ========================================
# 新規追加（Gridから呼び出し）
# ========================================
def add_animator(group_name, name, desc=""):
    # ---- 1. Unityからコントローラー選択＆情報取得（従来と同じ） ----
    project_path = get_unity_project_path()
    file_path = select_file(project_path, [("Animator Controller", "*.controller")])
    if not file_path:
        raise Exception("キャンセル")

    info = get_animator_controller_info(file_path)
    if not info:
        raise Exception("AnimatorController解析失敗")

    # ---- 2. 個別JSONに保存するデータ ----
    entry = {
        "name": name,
        "group": group_name,
        "desc": desc,
        "absolute_path": os.path.abspath(file_path),
        "parameters": info['parameters'],
        "layers": info['layers'],
        "events" : []
    }
    save_individual(name, entry)

    # ---- 3. インデックスに登録 ----
    index = load_index()
    if name not in index:
        index.append(name)
        save_index(index)

    # ---- 4. 自動生成（全件走査に変更になるので後述）----
    generate_all_animator_csharp()
    print(f"[{name}] 追加＆自動生成完了！")
    

# ========================================
# Pythonだけで全自動生成（BaseAnimatorManager + Param継承クラス対応）
# ========================================
def to_valid_identifier(name: str) -> str:
    """C#で有効な識別子に変換（スペース・ドット・ハイフンなどを除去）"""
    if not name or name == "None":
        return "None"
    # スペース・ドット・ハイフンなどをアンダースコアに置換
    s = re.sub(r'[ .\-\(\)\[\]]+', '_', name)
    # 先頭が数字なら頭に_をつける
    if s[0].isdigit():
        s = '_' + s
    # C#キーワード回避
    keywords = {'class', 'namespace', 'public', 'void', 'int', 'float', 'bool', 'true', 'false', 'null'}
    if s in keywords:
        s += '_'
    return s

# ========================================
# 1. 個別生成（DetailGrid用）
# ========================================
def generate_single_animator_csharp(ctrl,basic_types, unity_types, enum_list, class_list, class_data_id_list,enum_data,class_data_id,class_data):
    """DetailGridの「このAnimatorだけC#生成」用"""
    _generate_animator_hub_csharp_core(ctrl,basic_types, unity_types, enum_list, class_list, class_data_id_list,enum_data,class_data_id,class_data)
    return _generate_animator_csharp_core(ctrl)

# ========================================
# 2. 全件生成（Gridの「全Animator自動生成」用） ← 完全に共通化！
# ========================================
def generate_all_animator_csharp(basic_types, unity_types, enum_list, class_list, class_data_id_list,enum_data,class_data_id,class_data):
    registered = load_index()
    if not registered:
        print("登録Animatorなし")
        return

    generated = []
    for name in registered:
        try:
            ctrl = load_individual(name)
            _generate_animator_hub_csharp_core(ctrl,basic_types, unity_types, enum_list, class_list, class_data_id_list,enum_data,class_data_id,class_data)
            path = _generate_animator_csharp_core(ctrl)
            generated.append(path)
        except Exception as e:
            print(f"[{name}] 生成失敗: {e}")

    print(f"全Animator自動生成完了！（{len(generated)}件）")
    print("Unityでリフレッシュしてね")
    
# ========================================
# 共通：1件分のC#生成ロジック（all / single 両方で使用）
# ========================================
def _generate_animator_csharp_core(ctrl):
    """
    内部関数：実際にコード生成してファイル書き出し
    ctrl = load_individual(name) の戻り値
    """
    name = ctrl['name']
    class_name = f"{name}AnimatorManager"
    layer_map = {}

    code = f"""// <auto-generated by Python - Full Generic + Param Support>
using System;
using System.Collections.Generic;
using Cysharp.Threading.Tasks;
using UnityEngine;
using GameCore.GameAnimator;

namespace GameCore.GameAnimator
{{
    public class {class_name} : BaseAnimatorManager<{class_name}.Layer, {class_name}.State,{class_name}.Param>
    {{
        public enum Layer
        {{
"""

    # === Layer enum ===
    for layer in ctrl['layers']:
        orig_name = layer['name'] if layer['name'] else "Base Layer"
        safe_name = to_valid_identifier(orig_name)
        layer_map[orig_name] = safe_name
        code += f"            {safe_name},\n"
    code += "        }\n\n"

    # === State enum ===
    code += "        public enum State\n        {\n"
    for layer in ctrl['layers']:
        layer_orig = layer['name'] if layer['name'] else "Base Layer"
        layer_safe = layer_map[layer_orig]
        for state in layer['states']:
            state_orig = state['name']
            state_safe = to_valid_identifier(state_orig)
            full_safe = f"{layer_safe}_{state_safe}"
            code += f"            {full_safe},\n"
            
            if state.get('isBlendTree') and state.get('blendTree'):
                for child in state['blendTree']['children']:
                    child_name = child['motionName']
                    if child_name == "None": continue
                    child_safe = to_valid_identifier(child_name)
                    child_full = f"{layer_safe}_{state_safe}_{child_safe}"
                    code += f"            {child_full},\n"
    code += "        }\n\n"

    # === KeySetUp ===
    code += "        public override void KeySetUp()\n        {\n"
    code += "            if (animationKey != null){param.Init(animator); return;}\n"
    code += "            animationKey = new();\n\n"
    
    for layer in ctrl['layers']:
        layer_orig = layer['name'] if layer['name'] else "Base Layer"
        layer_safe = layer_map[layer_orig]
        layer_index = layer.get('index', 0)
        
        code += f"            animationKey[Layer.{layer_safe}] = new BaseTLayer\n"
        code += "            {\n"
        code += "                stateDict = new()\n"
        code += "                {\n"
        
        for state in layer['states']:
            state_orig = state['name']
            state_safe = to_valid_identifier(state_orig)
            full_safe = f"{layer_safe}_{state_safe}"
            code += f"                    [State.{full_safe}] = \"{state_safe}\",\n"
            
            if state.get('isBlendTree') and state.get('blendTree'):
                for child in state['blendTree']['children']:
                    child_name = child['motionName']
                    if child_name == "None": continue
                    child_safe = to_valid_identifier(child_name)
                    child_full = f"{layer_safe}_{state_safe}_{child_safe}"
                    code += f"                    [State.{child_full}] = \"{state_safe}\",\n"
        
        code += "                }\n"
        code += "            };\n"
        code += f"            animationKey[Layer.{layer_safe}].SetIndex({layer_index});\n\n"
        code += f"            param.Init(animator);\n\n"
    
    code += "        }\n\n"

    # === Paramクラス ===
    float_params = [p['name'] for p in ctrl['parameters'] if p['type'] == "Float"]
    int_params   = [p['name'] for p in ctrl['parameters'] if p['type'] == "Int"]
    bool_params  = [p['name'] for p in ctrl['parameters'] if p['type'] == "Bool"]
    trigger_params = [p['name'] for p in ctrl['parameters'] if p['type'] == "Trigger"]

    code += "        public sealed class Param\n        {\n"
    if float_params:
        safe_floats = [to_valid_identifier(p) for p in float_params]
        code += f"            public enum FloatParams {{ {', '.join(safe_floats)} }}\n"
        code += "            public readonly FloatParam<FloatParams> Float = new();\n"
    if int_params:
        safe_ints = [to_valid_identifier(p) for p in int_params]
        code += f"            public enum IntParams {{ {', '.join(safe_ints)} }}\n"
        code += "            public readonly IntParam<IntParams> Int = new();\n"
    if bool_params:
        safe_bools = [to_valid_identifier(p) for p in bool_params]
        code += f"            public enum BoolParams {{ {', '.join(safe_bools)} }}\n"
        code += "            public readonly BoolParam<BoolParams> Bool = new();\n"
    if trigger_params:
        safe_triggers = [to_valid_identifier(p) for p in trigger_params]
        code += f"            public enum TriggerParams {{ {', '.join(safe_triggers)} }}\n"
        code += "            public readonly TriggerParam<TriggerParams> Trigger = new();\n"

    code += "\n            public void Init(Animator anim)\n            {\n"
    if float_params:   code += "                Float.SetAnimator(anim);\n"
    if int_params:     code += "                Int.SetAnimator(anim);\n"
    if bool_params:    code += "                Bool.SetAnimator(anim);\n"
    if trigger_params: code += "                Trigger.SetAnimator(anim);\n"
    code += "            }\n        }\n\n"

    code += "        public readonly Param param = new();\n\n"
    code += "        public new void SetUp(GameObject go)\n        {\n"
    code += "            base.SetUp(go);\n"
    code += "        }\n\n"
    code += f"        public {class_name}(GameObject go) : base()\n        {{\n"
    code += "            base.SetUp(go);\n"
    code += "        }\n\n"
    code += f"        public {class_name}() : base()\n        {{\n"
    code += "        }\n\n"

    # === BlendTree専用Play ===
    code += "        // === BlendTree子ステート専用Play ===\n"
    for layer in ctrl['layers']:
        layer_orig = layer['name'] if layer['name'] else "Base Layer"
        layer_safe = layer_map[layer_orig]
        for state in layer['states']:
            if not (state.get('isBlendTree') and state.get('blendTree')): 
                continue
            state_safe = to_valid_identifier(state['name'])
            param_name = to_valid_identifier(state['blendTree']['blendParameter'])
            for child in state['blendTree']['children']:
                child_name = child['motionName']
                if child_name == "None": continue
                child_safe = to_valid_identifier(child_name)
                method_name = f"Play_{layer_safe}_{state_safe}_{child_safe}"
                threshold = child['threshold']
                state_full = f"{layer_safe}_{state_safe}_{child_safe}"
                code += f"        public UniTask {method_name}(float crossFade = 0.2f, Action onFinish = null)\n"
                code += f"        {{\n"
                code += f"            Param.Float.Set(Param.FloatParams.{param_name}, {threshold}f);\n"
                code += f"            return PlayAnimation(State.{state_full}, crossFade, onFinish);\n"
                code += f"        }}\n\n"

    code += "    }\n}\n// </auto-generated>\n"

    # === ファイル保存 ===
    dir_path = os.path.join(ANIM_DATA, f"{name}")
    os.makedirs(dir_path, exist_ok=True)
    file_path = os.path.join(dir_path, f"{class_name}.cs")
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(code)

    print(f"Generated: {file_path}")
    return file_path

def _generate_animator_hub_csharp_core(ctrl,basic_types, unity_types, enum_list, class_list, class_data_id_list,enum_data,class_data_id,class_data):
    
    name = ctrl['name']
    events = ctrl.get("events",[])
    
    method_str = ""
    release_str = ""
    for event in events:

        type_str = event['type']
        if type_str in enum_list:
            type_str = f"GameCore.Enums.{type_str}ID"

        elif type_str in class_list:
            type_str = f"GameCore.Classes.{type_str}"

        elif type_str in class_data_id_list:
            type_str = f"GameCore.Tables.ID.{type_str}TableID"
            
        s_cap = event['name'].capitalize()
        s_lower = lower_first(event['name'])
        method_str += f"        //{event['description']}\n"
        if type_str == "void" or type_str == "Void":
            method_str += f"        private Action<{name}AnimatorManager> {s_lower};\n"
            method_str += f"        private void Add{s_cap}(Action<{name}AnimatorManager> add) => {s_lower} += add;\n"
            method_str += f"        private void Remove{s_cap}(Action<{name}AnimatorManager> remove) => {s_lower} -= remove;\n"    
            method_str += f"        private void Clear{s_cap}() => {s_lower} = null;\n"
            method_str += f"        public On{s_cap}() => {s_lower}?.Invoke(animationManager);\n\n"
        else:
            method_str += f"        private Action<{type_str},{name}AnimatorManager> {s_lower};\n"
            method_str += f"        private void Add{s_cap}(Action<{type_str},{name}AnimatorManager> add) => {s_lower} += add;\n"
            method_str += f"        private void Remove{s_cap}(Action<{type_str},{name}AnimatorManager> remove) => {s_lower} -= remove;\n"    
            method_str += f"        private void Clear{s_cap}() => {s_lower} = null;\n"
            method_str += f"        public On{s_cap}({type_str} parameter) => {s_lower}?.Invoke(parameter,animationManager);\n\n"
        release_str += f"            {s_lower} = null;\n"
        
    code_str = f"""
using System;
using System.Collections.Generic;
using Cysharp.Threading.Tasks;
using UnityEngine;


namespace GameCore.GameAnimator
{{
    public class {name}AnimatorHub : BaseAnimatorHub<{name}AnimatorManager,{name}AnimatorManager.Layer,{name}AnimatorManager.Stat, {name}AnimatorManager.Param>
    {{
{method_str}
        public void Awake()
        {{
            SetUp();
        }}
        
        public void OnDestroy()
        {{
            ReleaseHub();
{release_str}
        }}
    }}
}}
"""
    dir_path = os.path.join(ANIM_DATA, f"{name}")
    os.makedirs(dir_path, exist_ok=True)
    file_path = os.path.join(dir_path, f"{name}AnimatorHub.cs")
    with open(file_path,"w",encoding="utf-8") as f:
        f.write(code_str)
        
def lower_first(s):
    return s[0].lower() + s[1:] if s else s
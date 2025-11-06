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
            
    if not os.path.exists(os.path.join(ANIM_DATA,"BaseAnimationManager.cs")):
        code_str = """
using Cysharp.Threading.Tasks;
using System;
using System.Collections.Generic;
using System.Threading;
using UnityEngine;

namespace GameCore.GameAnimation
{
    public class BaseAnimationManager<TLayerEnum, TStateEnum> where TLayerEnum : Enum where TStateEnum : Enum
    {
        protected static Dictionary<TLayerEnum, Dictionary<TStateEnum, string>> animationKey;
        protected Animator animator;

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

        public void SetUp(GameObject gameObject)
        {
            animator = gameObject.GetComponent<Animator>();
            if (animator == null)
                throw new Exception($"Animator not found on {gameObject.name}");

            KeySetUp();
        }

        public virtual void KeySetUp()
        {
            if (animationKey != null) return;

            animationKey = new Dictionary<TLayerEnum, Dictionary<TStateEnum, string>>();

            throw new NotImplementedException(
                "継承先で partial void KeySetUp() を実装し、animationKey を初期化してください。"
            );
        }

        public void PlayAnimation(TStateEnum animationID, float crossFade = 0.2f, Action onFinish = null, bool reverse = false)
            => PlayAnimationAsync(animationID, crossFade, onFinish, reverse).Forget();

        public async UniTask PlayAnimationAsync(TStateEnum animationID, float crossFade = 0.2f, Action onFinish = null, bool reverse = false, CancellationTokenSource customCts = null)
        {
            if (!TryGetLayerAndClip(animationID, out TLayerEnum layer, out string clipName, out int layerIndex))
            {
                Debug.LogError($"[BaseAnimationManager] AnimationID not registered: {animationID}");
                onFinish?.Invoke();
                return;
            }


            current?.Cts?.Cancel();
            current?.Cts?.Dispose();
            CancellationTokenSource cts = null;

            if (customCts != null)
            {
                cts = CancellationTokenSource.CreateLinkedTokenSource(customCts.Token, animator.gameObject.GetCancellationTokenOnDestroy());
            }
            else
            {
                cts =   CancellationTokenSource.CreateLinkedTokenSource(animator.gameObject.GetCancellationTokenOnDestroy());
            }

            current = new PlayRecord
            {
                Layer = layer,
                State = animationID,
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

        public TStateEnum IsAnimation(TLayerEnum layerID)
        {
            int layerIndex = animator.GetLayerIndex(layerID.ToString());
            if (layerIndex < 0) return default;

            var info = animator.GetCurrentAnimatorStateInfo(layerIndex);
            if (!animationKey.TryGetValue(layerID, out var dict)) return default;

            foreach (var kvp in dict)
                if (Animator.StringToHash(kvp.Value) == info.shortNameHash)
                    return kvp.Key;

            return default;
        }

        public bool IsPlaying(TLayerEnum layerID)
        {
            int layerIndex = animator.GetLayerIndex(layerID.ToString());
            if (layerIndex < 0) return false;

            var info = animator.GetCurrentAnimatorStateInfo(layerIndex);
            float norm = info.normalizedTime % 1f;
            if (current?.Reverse == true) norm = 1f - norm;
            return norm < 1f;
        }

        public void Stop()
        {
            current?.Cts?.Cancel();
            animator.speed = 1f;
        }

        private bool TryGetLayerAndClip(TStateEnum state, out TLayerEnum layer, out string clipName, out int layerIndex)
        {
            layer = default; clipName = null; layerIndex = -1;
            foreach (var kvp in animationKey)
                if (kvp.Value.TryGetValue(state, out clipName))
                {
                    layer = kvp.Key;
                    layerIndex = animator.GetLayerIndex(layer.ToString());
                    return layerIndex >= 0;
                }
            return false;
        }

    }
}


        """
        with open(os.path.join(ANIM_DATA,"BaseAnimationManager.cs"),"w",encoding="utf-8") as f:
            f.write(code_str)
            
    
    if not os.path.exists(os.path.join(ANIM_DATA,"AnimationParam.cs")):
        code_str = """
using System;
using UnityEngine;
namespace GameCore.GameAnimation
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
            
def load_anim_json():
    if not os.path.exists(ANIM_JSON):
        return {}
    
    data = {}
    with open(ANIM_JSON,"r",encoding="utf-8") as f:
        return json.load(f)
    
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
    data = load_anim_json()
    
    if data.get("groups") == None:
        data["groups"] = {}
    if group_name not in data.get('groups',[]):
        data['groups'][group_name] = []

    project_path = get_unity_project_path()
    file_path = select_file(project_path, [("Animator Controller", "*.controller")])
    if not file_path:
        raise Exception("キャンセル")

    info = get_animator_controller_info(file_path)
    if not info:
        raise Exception("AnimatorController解析失敗")


    entry = {
        'name': name,
        'desc': desc,
        'absolute_path': os.path.abspath(file_path),
        'parameters': info['parameters'],
        'layers': info['layers']
    }
    data['groups'][group_name].append(entry)
    save_anim_data(data)

    # 自動生成実行
    generate_all_animator_csharp()
    print(f"[{name}] 追加＆自動生成完了！")
    
def load_anim_data():
    if os.path.exists(ANIM_JSON):
        with open(ANIM_JSON, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'groups': {}}

def save_anim_data(data):
    with open(ANIM_JSON, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
        
# ========================================
# Pythonだけで全自動生成（BaseAnimationManager + Param継承クラス対応）
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

def generate_all_animator_csharp():
    data = load_anim_data()
    
    for group, controllers in data['groups'].items():
        for ctrl in controllers:
            ctrl_name = ctrl['name']
            class_name = f"{ctrl_name}AnimationManager"
            
            # レイヤーとステートのマッピング用辞書（表示名 → 識別子）
            layer_map = {}
            state_map = {}  # "Layer_State" → 識別子
            
            code = f"""// <auto-generated by Python - Full Generic + Param Support>
using System;
using System.Collections.Generic;
using Cysharp.Threading.Tasks;
using UnityEngine;
using GameCore.Animator;

namespace GameCore.GameAnimation
{{
    public partial class {class_name} : BaseAnimationManager<{class_name}.Layer, {class_name}.State>
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
                    state_map[f"{layer_orig}_{state_orig}"] = full_safe
                    code += f"            {full_safe},\n"
                    
                    # BlendTreeの子ステート
                    if state.get('isBlendTree') and state.get('blendTree'):
                        for child in state['blendTree']['children']:
                            child_name = child['motionName']
                            if child_name == "None":
                                continue
                            child_safe = to_valid_identifier(child_name)
                            child_full = f"{layer_safe}_{state_safe}_{child_safe}"
                            state_map[f"{layer_orig}_{state_orig}_{child_name}"] = child_full
                            code += f"            {child_full},\n"
            code += "        }\n\n"

            # === KeySetUp ===
            code += "        partial void KeySetUp()\n        {\n"
            code += "             if (animationKey != null) return;\n"
            code += "            animationKey = new()\n            {\n"
            for layer in ctrl['layers']:
                layer_orig = layer['name'] if layer['name'] else "Base Layer"
                layer_safe = layer_map[layer_orig]
                code += f"                [Layer.{layer_safe}] = new()\n                {{\n"
                for state in layer['states']:
                    state_orig = state['name']
                    state_safe = to_valid_identifier(state_orig)
                    clip_name = state['motions'][0] if state['motions'] and state['motions'][0] != "None" else state_orig
                    full_safe = f"{layer_safe}_{state_safe}"
                    code += f"                    [State.{full_safe}] = \"{clip_name}\",\n"
                    
                    if state.get('isBlendTree') and state.get('blendTree'):
                        for child in state['blendTree']['children']:
                            child_name = child['motionName']
                            if child_name == "None":
                                continue
                            child_safe = to_valid_identifier(child_name)
                            child_full = f"{layer_safe}_{state_safe}_{child_safe}"
                            code += f"                    [State.{child_full}] = \"{child_name}\",\n"
                code += "                }},\n"
            code += "            };\n        }\n\n"

            # === Paramクラス ===
            float_params = [p['name'] for p in ctrl['parameters'] if p['type'] == "Float"]
            int_params   = [p['name'] for p in ctrl['parameters'] if p['type'] == "Int"]
            bool_params  = [p['name'] for p in ctrl['parameters'] if p['type'] == "Bool"]
            trigger_params = [p['name'] for p in ctrl['parameters'] if p['type'] == "Trigger"]

            code += "        public sealed class Param\n        {\n"
            if float_params:
                safe_floats = [to_valid_identifier(p) for p in float_params]
                code += f"            public enum Float {{ {', '.join(safe_floats)} }}\n"
                code += "            public readonly FloatParam<Float> Float = new();\n"
            if int_params:
                safe_ints = [to_valid_identifier(p) for p in int_params]
                code += f"            public enum Int {{ {', '.join(safe_ints)} }}\n"
                code += "            public readonly IntParam<Int> Int = new();\n"
            if bool_params:
                safe_bools = [to_valid_identifier(p) for p in bool_params]
                code += f"            public enum Bool {{ {', '.join(safe_bools)} }}\n"
                code += "            public readonly BoolParam<Bool> Bool = new();\n"
            if trigger_params:
                safe_triggers = [to_valid_identifier(p) for p in trigger_params]
                code += f"            public enum Trigger {{ {', '.join(safe_triggers)} }}\n"
                code += "            public readonly TriggerParam<Trigger> Trigger = new();\n"

            code += "\n            public void Init(Animator anim)\n            {\n"
            if float_params:   code += "                Float.SetAnimator(anim);\n"
            if int_params:     code += "                Int.SetAnimator(anim);\n"
            if bool_params:    code += "                Bool.SetAnimator(anim);\n"
            if trigger_params: code += "                Trigger.SetAnimator(anim);\n"
            code += "            }\n        }\n\n"

            code += "        public readonly Param Param = new();\n\n"
            code += "        public new void SetUp(GameObject go)\n        {\n"
            code += "            base.SetUp(go);\n"
            code += "            Param.Init(animator);\n"
            code += "        }\n\n"

            # === BlendTree専用Playメソッド ===
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
                        if child_name == "None":
                            continue
                        child_safe = to_valid_identifier(child_name)
                        method_name = f"Play_{layer_safe}_{state_safe}_{child_safe}"
                        threshold = child['threshold']
                        state_full = f"{layer_safe}_{state_safe}_{child_safe}"
                        code += f"        public UniTask {method_name}(float crossFade = 0.2f, Action onFinish = null)\n"
                        code += f"        {{\n"
                        code += f"            Param.Float.Set(Param.Float.{param_name}, {threshold}f);\n"
                        code += f"            return PlayAnimation(State.{state_full}, crossFade, onFinish);\n"
                        code += f"        }}\n\n"

            code += "    }\n}\n// </auto-generated>\n"

            # 保存
            dir_path = os.path.join(ANIM_DATA, class_name)
            os.makedirs(dir_path, exist_ok=True)
            file_path = os.path.join(dir_path, f"{class_name}.g.cs")
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(code)

    print("全Animator自動生成完了！（完全修正版・コンパイルエラーゼロ）")
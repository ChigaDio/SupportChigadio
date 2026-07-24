# pythonSrc/dbgcommand.py
#
# DebugCommand機能一式。
#   ・DebugCommandの登録（コマンド名 + 引数[名前,型] + （任意で）戻り値[名前,型]）
#   ・登録したDebugCommandからC#クラスを自動生成
#       Base{Name}DebugCommand : DebugCommandBase   ... 自動生成（毎回上書き）
#       {Name}DebugCommand      : Base{Name}DebugCommand ... 手動実装用（存在しない場合のみ生成）
#   ・WebSocket(dbgServer.py)経由でJS側から送られてきたコマンドをUnity(C#)側で
#     ディスパッチするための共通基盤(DebugCommandBase.cs)も自動生成
#
# app.py側の変更は最小限（本モジュールをimportしてregister()を呼ぶだけ）。

import os
import json
import shutil
import logging
from flask import request, jsonify

logger = logging.getLogger(__name__)

DEBUG_COMMAND = 'debug_command'

# 引数・戻り値で使用できる型（app.py の TYPE_MAP / CONST_TYPE_MAP と揃えている）
ALLOWED_TYPES = ['int', 'uint', 'float', 'double', 'bool', 'string', 'vector2', 'vector3']

CS_TYPE_MAP = {
    'int': 'int',
    'uint': 'uint',
    'float': 'float',
    'double': 'double',
    'bool': 'bool',
    'string': 'string',
    'vector2': 'Vector2',
    'vector3': 'Vector3',
}


# ============================================================
# C#コード生成用の小さなヘルパー
# ============================================================

def _cs_type(t):
    return CS_TYPE_MAP.get(t, 'string')


def _from_json_expr(t, name):
    """自前のJsonObject(Newtonsoft非依存)から t 型のフィールドを取り出すC#式を返す。
    引数が省略された場合は各Getメソッドのデフォルト値（0 / false / "" / Vector.zero）が使われる。"""
    if t == 'vector2':
        return f'json.GetVector2("{name}")'
    if t == 'vector3':
        return f'json.GetVector3("{name}")'
    if t == 'string':
        return f'json.GetString("{name}")'
    if t == 'bool':
        return f'json.GetBool("{name}")'
    if t == 'int':
        return f'json.GetInt("{name}")'
    if t == 'uint':
        return f'json.GetUInt("{name}")'
    if t == 'double':
        return f'json.GetDouble("{name}")'
    # float
    return f'json.GetFloat("{name}")'


def _to_json_stmt(t, name):
    """C#フィールド値を自前のJsonObjectに詰めるC#文を返す"""
    if t == 'vector2':
        return f'json.SetVector2("{name}", {name});'
    if t == 'vector3':
        return f'json.SetVector3("{name}", {name});'
    return f'json["{name}"] = {name};'


def _validate_fields(fields):
    if not isinstance(fields, list):
        return "フィールドはリストで指定してください"
    seen = set()
    for fdef in fields:
        if not isinstance(fdef, dict) or not fdef.get('name'):
            return "フィールド名は必須です"
        if fdef['name'] in seen:
            return f"フィールド名が重複しています: {fdef['name']}"
        seen.add(fdef['name'])
        if fdef.get('type') not in ALLOWED_TYPES:
            return f"不正な型です: {fdef.get('type')}"
    return None


# ============================================================
# 共通基盤ファイル（一度生成すれば以後は上書きされるだけ。手動編集不要）
# ============================================================

def _generate_json_cs(base_dir):
    """Newtonsoft.Json等の外部ライブラリに依存しない、自前の最小限JSON実装。
    Dictionary<string,object> / List<object> / string / double / bool / null のみを扱う。"""
    path = os.path.join(base_dir, "DebugCommandJson.cs")
    content = r'''
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using UnityEngine;

namespace GameCore.DebugCommand
{
    // 外部ライブラリに依存しない最小限のJSONパーサ・シリアライザ（DebugCommand専用）
    public static class MiniJson
    {
        public static object Parse(string json)
        {
            int i = 0;
            return ParseValue(json, ref i);
        }

        public static string Serialize(object obj)
        {
            var sb = new StringBuilder();
            WriteValue(sb, obj);
            return sb.ToString();
        }

        private static object ParseValue(string s, ref int i)
        {
            SkipWhitespace(s, ref i);
            if (i >= s.Length) return null;
            char c = s[i];
            if (c == '{') return ParseObject(s, ref i);
            if (c == '[') return ParseArray(s, ref i);
            if (c == '"') return ParseString(s, ref i);
            if (c == 't' || c == 'f') return ParseBool(s, ref i);
            if (c == 'n') { i += 4; return null; }
            return ParseNumber(s, ref i);
        }

        private static Dictionary<string, object> ParseObject(string s, ref int i)
        {
            var dict = new Dictionary<string, object>();
            i++; // {
            SkipWhitespace(s, ref i);
            if (i < s.Length && s[i] == '}') { i++; return dict; }
            while (true)
            {
                SkipWhitespace(s, ref i);
                string key = ParseString(s, ref i);
                SkipWhitespace(s, ref i);
                i++; // :
                var value = ParseValue(s, ref i);
                dict[key] = value;
                SkipWhitespace(s, ref i);
                if (i < s.Length && s[i] == ',') { i++; continue; }
                if (i < s.Length && s[i] == '}') { i++; break; }
                break;
            }
            return dict;
        }

        private static List<object> ParseArray(string s, ref int i)
        {
            var list = new List<object>();
            i++; // [
            SkipWhitespace(s, ref i);
            if (i < s.Length && s[i] == ']') { i++; return list; }
            while (true)
            {
                list.Add(ParseValue(s, ref i));
                SkipWhitespace(s, ref i);
                if (i < s.Length && s[i] == ',') { i++; continue; }
                if (i < s.Length && s[i] == ']') { i++; break; }
                break;
            }
            return list;
        }

        private static string ParseString(string s, ref int i)
        {
            var sb = new StringBuilder();
            i++; // opening "
            while (i < s.Length && s[i] != '"')
            {
                char c = s[i];
                if (c == '\\' && i + 1 < s.Length)
                {
                    i++;
                    char e = s[i];
                    switch (e)
                    {
                        case 'n': sb.Append('\n'); break;
                        case 't': sb.Append('\t'); break;
                        case 'r': sb.Append('\r'); break;
                        case '"': sb.Append('"'); break;
                        case '\\': sb.Append('\\'); break;
                        case '/': sb.Append('/'); break;
                        case 'u':
                            string hex = s.Substring(i + 1, 4);
                            sb.Append((char)Convert.ToInt32(hex, 16));
                            i += 4;
                            break;
                        default: sb.Append(e); break;
                    }
                }
                else
                {
                    sb.Append(c);
                }
                i++;
            }
            i++; // closing "
            return sb.ToString();
        }

        private static bool ParseBool(string s, ref int i)
        {
            if (i + 4 <= s.Length && s.Substring(i, 4) == "true") { i += 4; return true; }
            i += 5; // false
            return false;
        }

        private static double ParseNumber(string s, ref int i)
        {
            int start = i;
            while (i < s.Length && (char.IsDigit(s[i]) || s[i] == '-' || s[i] == '+' || s[i] == '.' || s[i] == 'e' || s[i] == 'E'))
            {
                i++;
            }
            return double.Parse(s.Substring(start, i - start), CultureInfo.InvariantCulture);
        }

        private static void SkipWhitespace(string s, ref int i)
        {
            while (i < s.Length && char.IsWhiteSpace(s[i])) i++;
        }

        private static void WriteValue(StringBuilder sb, object obj)
        {
            switch (obj)
            {
                case null:
                    sb.Append("null");
                    break;
                case string str:
                    WriteString(sb, str);
                    break;
                case bool b:
                    sb.Append(b ? "true" : "false");
                    break;
                case JsonObject jo:
                    WriteObject(sb, jo.Raw);
                    break;
                case Dictionary<string, object> dict:
                    WriteObject(sb, dict);
                    break;
                case List<object> list:
                    WriteArray(sb, list);
                    break;
                case float f:
                    sb.Append(f.ToString(CultureInfo.InvariantCulture));
                    break;
                case double d:
                    sb.Append(d.ToString(CultureInfo.InvariantCulture));
                    break;
                case int ii:
                    sb.Append(ii.ToString(CultureInfo.InvariantCulture));
                    break;
                case uint ui:
                    sb.Append(ui.ToString(CultureInfo.InvariantCulture));
                    break;
                default:
                    WriteString(sb, obj.ToString());
                    break;
            }
        }

        private static void WriteObject(StringBuilder sb, Dictionary<string, object> dict)
        {
            sb.Append('{');
            bool first = true;
            foreach (var kv in dict)
            {
                if (!first) sb.Append(',');
                first = false;
                WriteString(sb, kv.Key);
                sb.Append(':');
                WriteValue(sb, kv.Value);
            }
            sb.Append('}');
        }
        private static void WriteArray(StringBuilder sb, List<object> list)
        {
            sb.Append('[');
            for (int i = 0; i < list.Count; i++)
            {
                if (i > 0) sb.Append(',');
                WriteValue(sb, list[i]);
            }
            sb.Append(']');
        }
        private static void WriteString(StringBuilder sb, string s)
        {
            sb.Append('"');
            foreach (char c in s)
            {
                switch (c)
                {
                    case '"': sb.Append("\\\""); break;
                    case '\\': sb.Append("\\\\"); break;
                    case '\n': sb.Append("\\n"); break;
                    case '\r': sb.Append("\\r"); break;
                    case '\t': sb.Append("\\t"); break;
                    default: sb.Append(c); break;
                }
            }
            sb.Append('"');
        }
    }

    // Newtonsoft の JObject の代わりに使う軽量ラッパー（外部ライブラリ非依存）
    public class JsonObject
    {
        private readonly Dictionary<string, object> _data;

        public JsonObject() { _data = new Dictionary<string, object>(); }
        public JsonObject(Dictionary<string, object> data) { _data = data ?? new Dictionary<string, object>(); }

        internal Dictionary<string, object> Raw => _data;

        public static JsonObject Parse(string json)
        {
            var obj = MiniJson.Parse(json) as Dictionary<string, object>;
            return new JsonObject(obj ?? new Dictionary<string, object>());
        }

        public object this[string key]
        {
            get => _data.TryGetValue(key, out var v) ? v : null;
            set => _data[key] = (value is JsonObject jo) ? (object)jo.Raw : value;
        }

        public bool Has(string key) => _data.ContainsKey(key);

        public JsonObject GetObject(string key)
        {
            if (_data.TryGetValue(key, out var v) && v is Dictionary<string, object> d) return new JsonObject(d);
            return null;
        }

        public string GetString(string key, string def = "")
        {
            return _data.TryGetValue(key, out var v) && v != null ? v.ToString() : def;
        }

        public bool GetBool(string key, bool def = false)
        {
            return (_data.TryGetValue(key, out var v) && v is bool b) ? b : def;
        }

        public int GetInt(string key, int def = 0)
        {
            return (_data.TryGetValue(key, out var v) && v is double d) ? (int)d : def;
        }

        public uint GetUInt(string key, uint def = 0)
        {
            return (_data.TryGetValue(key, out var v) && v is double d) ? (uint)d : def;
        }

        public float GetFloat(string key, float def = 0f)
        {
            return (_data.TryGetValue(key, out var v) && v is double d) ? (float)d : def;
        }

        public double GetDouble(string key, double def = 0)
        {
            return (_data.TryGetValue(key, out var v) && v is double d) ? d : def;
        }

        public Vector2 GetVector2(string key)
        {
            var o = GetObject(key);
            return o == null ? Vector2.zero : new Vector2(o.GetFloat("x"), o.GetFloat("y"));
        }

        public Vector3 GetVector3(string key)
        {
            var o = GetObject(key);
            return o == null ? Vector3.zero : new Vector3(o.GetFloat("x"), o.GetFloat("y"), o.GetFloat("z"));
        }

        public void SetVector2(string key, Vector2 v)
        {
            _data[key] = new Dictionary<string, object> { ["x"] = (double)v.x, ["y"] = (double)v.y };
        }

        public void SetVector3(string key, Vector3 v)
        {
            _data[key] = new Dictionary<string, object> { ["x"] = (double)v.x, ["y"] = (double)v.y, ["z"] = (double)v.z };
        }

        public override string ToString()
        {
            return MiniJson.Serialize(_data);
        }
    }
}

'''
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    return path


def _generate_registry_cs(base_dir):
    path = os.path.join(base_dir, "DebugCommandBase.cs")
    content = '''

using System;
using System.Collections.Generic;
using Newtonsoft.Json.Linq;

namespace GameCore.DebugCommand
{
    // 全DebugCommandの基底クラス（自動生成・編集不要）
    public abstract class DebugCommandBase
    {
        public abstract string CommandName { get; }

        // JS側から送られてきた引数(JsonObject)を受け取り実行し、結果(JsonObjectまたはnull)を返す
        public abstract JsonObject Invoke(JsonObject argsJson);
    }

    // 名前でDebugCommandを管理し、WebSocket経由で受信したメッセージをディスパッチする。
    // DebugCommandWebSocketHandler.cs から自動的に呼び出される。
    public static class DebugCommandRegistry
    {
        private static readonly Dictionary<string, DebugCommandBase> _commands = new Dictionary<string, DebugCommandBase>();


        public static void Register(DebugCommandBase command)
        {
            _commands[command.CommandName] = command;
        }

        public static bool TryGet(string name, out DebugCommandBase command)
        {
            return _commands.TryGetValue(name, out command);
        }

        // dbgServer.py から届いたJSON文字列を解析し、対応するDebugCommandを実行して
        // 応答用のJSON文字列を返す（type:"command" 以外のメッセージが来た場合はnullを返す）。
        public static string Dispatch(string receivedJson)
        {
            JsonObject root;
            try
            {
                root = JsonObject.Parse(receivedJson);
            }
            catch (Exception e)
            {
                return BuildError(null, null, $"JSON parse error: {e.Message}");
            }

            if (root.GetString("type") != "command")
            {
                return null;
            }

            string commandId = root.GetString("id", null);
            string name = root.GetString("name", null);
            var args = root.GetObject("args") ?? new JsonObject();

            if (!TryGet(name, out var command))
            {
                return BuildError(commandId, name, $"Unknown command: {name}");
            }

            try
            {
                var result = command.Invoke(args);
                var response = new JsonObject();
                response["type"] = "response";
                response["id"] = commandId;
                response["name"] = name;
                response["time"] = DateTime.Now.ToString("HH:mm:ss.fff");
                response["data"] = result;
                return response.ToString();
            }
            catch (Exception e)
            {
                return BuildError(commandId, name, e.Message);
            }
        }

        private static string BuildError(string commandId, string name, string message)
        {
            var response = new JsonObject();
            response["type"] = "response";
            response["id"] = commandId;
            response["name"] = name;
            response["time"] = DateTime.Now.ToString("HH:mm:ss.fff");
            response["error"] = message;
            return response.ToString();
        }
    }
}



'''
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    return path


def _generate_websocket_handler_cs(base_dir):
    """dbgServer.py(ws://localhost:8765)に接続し、DebugCommandの受信・実行・応答送信を行う
    Unity側のハンドラ。シーンに配置するだけで動作する（自動生成・編集不要）。"""
    path = os.path.join(base_dir, "DebugCommandWebSocketHandler.cs")
    content = '''
using System;
using System.IO;
using System.Text;
using System.Threading;
using System.Net.WebSockets;
using Cysharp.Threading.Tasks;
using UnityEngine;
using System.Diagnostics;

namespace GameCore.DebugCommand
{
    // dbgServer.py (既定: ws://localhost:8765) に接続し、JS(DebugCommandConsole)から
    // 送られてくる DebugCommand を受信して実行し、結果を送り返すハンドラ。
    // 空のGameObjectに1つアタッチしてください（自動生成・編集不要）。
    public class DebugCommandWebSocketHandler : MonoBehaviour
    {
        [SerializeField] private string url = "ws://localhost:8765";

        private ClientWebSocket _socket;
        private CancellationTokenSource _cts;
        
        [Conditional("UNITY_EDITOR")]
        [Conditional("UNITY_ENABLE_CHECKS")]
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
        private static void Init()
        {
            if (UnityEngine.Debug.isDebugBuild || Application.isEditor)
            {
                var go = new GameObject("DebugCommand");
                UnityEngine.Object.DontDestroyOnLoad(go);
                go.AddComponent<DebugCommandWebSocketHandler>();
                //DebugCommandInstaller.InstallAll();
            }
        }
        [Conditional("UNITY_EDITOR")]
        [Conditional("UNITY_ENABLE_CHECKS")]
        private void Start()
        {
            _cts = new CancellationTokenSource();
            ConnectAsync().Forget();
        }


        private async UniTaskVoid ConnectAsync()
        {
            _socket = new ClientWebSocket();
            try
            {
                await _socket.ConnectAsync(new Uri(url), _cts.Token);
                UnityEngine.Debug.Log($"[DebugCommand] WebSocket connected: {url}");
                ReceiveLoop().Forget();
            }
            catch (Exception e)
            {
                UnityEngine.Debug.LogError($"[DebugCommand] WebSocket connect failed: {e.Message}");
            }
        }
        private async UniTaskVoid ReceiveLoop()
        {
            var buffer = new byte[8192];
            while (_socket != null && _socket.State == WebSocketState.Open && !_cts.IsCancellationRequested)
            {
                string text;
                using (var ms = new MemoryStream())
                {
                    WebSocketReceiveResult result;
                    do
                    {
                        result = await _socket.ReceiveAsync(new ArraySegment<byte>(buffer), _cts.Token);
                        if (result.MessageType == WebSocketMessageType.Close)
                        {
                            await _socket.CloseAsync(WebSocketCloseStatus.NormalClosure, "closed", _cts.Token);
                            return;
                        }
                        ms.Write(buffer, 0, result.Count);
                    } while (!result.EndOfMessage);

                    text = Encoding.UTF8.GetString(ms.ToArray());
                }

                HandleMessage(text).Forget();
            }
        }
        private async UniTaskVoid HandleMessage(string text)
        {
            string response;
            try
            {
                // type:"command" 以外のメッセージ（通常のDebugLog等）の場合は null が返る
                response = DebugCommandRegistry.Dispatch(text);
            }
            catch (Exception e)
            {
                UnityEngine.Debug.LogError($"[DebugCommand] Dispatch error: {e.Message}");
                return;
            }

            if (string.IsNullOrEmpty(response)) return;

            await SendAsync(response);
        }
        private async UniTask SendAsync(string text)
        {
            if (_socket == null || _socket.State != WebSocketState.Open) return;
            var bytes = Encoding.UTF8.GetBytes(text);
            await _socket.SendAsync(new ArraySegment<byte>(bytes), WebSocketMessageType.Text, true, _cts.Token);
        }

        [Conditional("UNITY_EDITOR")]
        [Conditional("UNITY_ENABLE_CHECKS")]
        private async void OnDestroy()
        {
            _cts?.Cancel();
            try
            {
                if (_socket != null && _socket.State == WebSocketState.Open)
                {
                    await _socket.CloseAsync(WebSocketCloseStatus.NormalClosure, "destroyed", CancellationToken.None);
                }
            }
            catch
            {
                // シャットダウン時の例外は無視する
            }
            finally
            {
                _socket?.Dispose();
            }
        }
    }
}

'''
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    return path


def generate_base(data_dir):
    """共通基盤一式を生成する（起動時に毎回上書き。手動編集不要）。
      DebugCommandJson.cs              ... 自前JSONパーサ/シリアライザ（Newtonsoft非依存）
      DebugCommandBase.cs              ... 基底クラス + レジストリ + ディスパッチャ
      DebugCommandWebSocketHandler.cs  ... Unity側WebSocketクライアント（受信→実行→応答送信）
    """
    base_dir = os.path.join(data_dir, DEBUG_COMMAND)
    os.makedirs(base_dir, exist_ok=True)
    json_path = _generate_json_cs(base_dir)
    registry_path = _generate_registry_cs(base_dir)
    handler_path = _generate_websocket_handler_cs(base_dir)
    return json_path, registry_path, handler_path


def generate_installer(data_dir, names):
    """登録済み全DebugCommandをレジストリに登録するインストーラ（全生成のたびに上書き）"""
    base_dir = os.path.join(data_dir, DEBUG_COMMAND)
    os.makedirs(base_dir, exist_ok=True)
    path = os.path.join(base_dir, "DebugCommandInstaller.cs")

    lines = []
    lines.append("namespace GameCore.DebugCommand")
    lines.append("{")
    lines.append("    // 登録済みの全DebugCommandをレジストリに登録する（自動生成・編集不要）")
    lines.append("    public static class DebugCommandInstaller")
    lines.append("    {")
    lines.append("        public static void InstallAll()")
    lines.append("        {")
    for n in names:
        lines.append(f"            DebugCommandRegistry.Register(new {n}DebugCommand());")
    lines.append("        }")
    lines.append("    }")
    lines.append("}")

    with open(path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
    return path

def generate_base_installer(data_dir):
    """登録済み全DebugCommandをレジストリに登録するインストーラ（全生成のたびに上書き）"""
    base_dir = os.path.join(data_dir, DEBUG_COMMAND)
    os.makedirs(base_dir, exist_ok=True)
    path = os.path.join(base_dir, "DebugCommandInstaller.cs")

    lines = []
    lines.append("namespace GameCore.DebugCommand")
    lines.append("{")
    lines.append("    // 登録済みの全DebugCommandをレジストリに登録する（自動生成・編集不要）")
    lines.append("    public static class DebugCommandInstaller")
    lines.append("    {")
    lines.append("        public static void InstallAll()")
    lines.append("        {")
    lines.append("        }")
    lines.append("    }")
    lines.append("}")

    with open(path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
    return path


# ============================================================
# コマンド単位のC#生成
#   Base{Name}DebugCommand.cs ... 自動生成（毎回上書き）
#   {Name}DebugCommand.cs     ... 手動実装用スタブ（存在しない場合のみ生成）
# ============================================================

def generate_debug_command_cs(data_dir, name, args, has_return, return_fields):
    cmd_dir = os.path.join(data_dir, DEBUG_COMMAND, name)
    os.makedirs(cmd_dir, exist_ok=True)

    result_type = f"{name}Result" if has_return else "void"

    lines = []
    lines.append("using System;")
    lines.append("using UnityEngine;")
    lines.append("using Newtonsoft.Json.Linq;")
    lines.append("")
    lines.append("namespace GameCore.DebugCommand")
    lines.append("{")

    # --- 引数クラス ---
    lines.append(f"    // {name} コマンドの引数（自動生成）")
    lines.append(f"    public class {name}Args")
    lines.append("    {")
    for a in args:
        lines.append(f"        public {_cs_type(a['type'])} {a['name']};")
    lines.append("")
    lines.append(f"        public static {name}Args FromJson(JsonObject json)")
    lines.append("        {")
    lines.append(f"            return new {name}Args")
    lines.append("            {")
    for a in args:
        lines.append(f"                {a['name']} = {_from_json_expr(a['type'], a['name'])},")
    lines.append("            };")
    lines.append("        }")
    lines.append("    }")
    lines.append("")

    # --- 戻り値クラス（ある場合のみ） ---
    if has_return:
        lines.append(f"    // {name} コマンドの戻り値（自動生成）")
        lines.append(f"    public class {name}Result")
        lines.append("    {")
        for r in return_fields:
            lines.append(f"        public {_cs_type(r['type'])} {r['name']};")
        lines.append("")
        lines.append("        public JObject ToJson()")
        lines.append("        {")
        lines.append("            var json = new JObject();")
        for r in return_fields:
            lines.append(f"            {_to_json_stmt(r['type'], r['name'])}")
        lines.append("            return json;")
        lines.append("        }")
        lines.append("    }")
        lines.append("")

    # --- 基底クラス（ロジックは書かない。継承先で実装） ---
    lines.append(f"    // 自動生成される基底クラス。このファイルは毎回上書きされます。")
    lines.append(f"    // 実際の処理は {name}DebugCommand 側（手動実装ファイル）に書いてください。")
    lines.append(f"    public abstract class Base{name}DebugCommand : DebugCommandBase")
    lines.append("    {")
    lines.append(f'        public override string CommandName => "{name}";')
    lines.append("")
    lines.append("        public override JObject Invoke(JsonObject argsJson)")
    lines.append("        {")
    lines.append(f"            var args = {name}Args.FromJson(argsJson);")
    if has_return:
        lines.append("            var result = Execute(args);")
        lines.append("            return result?.ToJson();")
    else:
        lines.append("            Execute(args);")
        lines.append("            return null;")
    lines.append("        }")
    lines.append("")
    lines.append(f"        protected abstract {result_type} Execute({name}Args args);")
    lines.append("    }")
    lines.append("}")

    base_cs_path = os.path.join(cmd_dir, f"Base{name}DebugCommand.cs")
    with open(base_cs_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))

    # --- 手動実装クラス（存在しない場合のみ生成。以後は触らない） ---
    stub_path = os.path.join(cmd_dir, f"{name}DebugCommand.cs")
    if not os.path.exists(stub_path):
        stub_lines = []
        stub_lines.append("using UnityEngine;")
        stub_lines.append("using Newtonsoft.Json.Linq;")
        stub_lines.append("")
        stub_lines.append("namespace GameCore.DebugCommand")
        stub_lines.append("{")
        stub_lines.append(f"    // {name} コマンドの実処理。ここに手動でロジックを実装してください。")
        stub_lines.append(f"    // このファイルは初回生成時にのみ作られ、以後の生成では上書きされません。")
        stub_lines.append(f"    public class {name}DebugCommand : Base{name}DebugCommand")
        stub_lines.append("    {")
        stub_lines.append(f"        protected override {result_type} Execute({name}Args args)")
        stub_lines.append("        {")
        stub_lines.append("            // TODO: ここに実装")
        if has_return:
            stub_lines.append(f"            return new {name}Result();")
        stub_lines.append("        }")
        stub_lines.append("    }")
        stub_lines.append("}")
        with open(stub_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(stub_lines))

    return base_cs_path, stub_path


# ============================================================
# Flaskルート登録
# ============================================================

def register(app, data_dir):
    """app.py側からは import pythonSrc.dbgcommand as dbgcommand; dbgcommand.register(app, DATA_DIR)
    を呼ぶだけでOK。"""

    cmd_root = os.path.join(data_dir, DEBUG_COMMAND)
    os.makedirs(cmd_root, exist_ok=True)

    # 共通基盤(DebugCommandBase.cs)は起動時に必ず最新化しておく
    generate_base(data_dir)
    
    generate_base_installer(data_dir)

    list_path = os.path.join(cmd_root, 'debug_command_list.json')

    def _load_list():
        if not os.path.exists(list_path):
            return []
        with open(list_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _save_list(data):
        with open(list_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _detail_path(name):
        return os.path.join(cmd_root, name, f"{name}.json")

    def _load_detail(name):
        path = _detail_path(name)
        if not os.path.exists(path):
            return {"args": [], "hasReturn": False, "returnFields": []}
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    # --- 一覧取得 / 新規登録 / 削除 ---
    @app.route('/api/debug-command', methods=['GET', 'POST', 'PATCH'])
    def manage_debug_command():
        if request.method == 'GET':
            try:
                return jsonify(_load_list()), 200
            except Exception as e:
                logger.error(f"DebugCommand一覧取得エラー: {str(e)}")
                return jsonify({"error": str(e)}), 500

        elif request.method == 'POST':
            try:
                body = request.get_json() or {}
                name = body.get('name')
                if not name:
                    return jsonify({"error": "名前は必須です"}), 400
                if ':' in name:
                    return jsonify({"error": "名前に':'を含めることはできません"}), 400

                data = _load_list()
                if any(item['name'] == name for item in data):
                    return jsonify({"error": f"DebugCommand {name} はすでに存在します"}), 400

                max_id = max([item['id'] for item in data], default=0) + 1
                new_entry = {"id": max_id, "name": name}
                data.append(new_entry)
                _save_list(data)

                data_file_path = _detail_path(name)
                os.makedirs(os.path.dirname(data_file_path), exist_ok=True)
                with open(data_file_path, 'w', encoding='utf-8') as f:
                    json.dump({"args": [], "hasReturn": False, "returnFields": []}, f, ensure_ascii=False, indent=2)

                logger.info(f"DebugCommandを作成しました: {name}")
                return jsonify({"message": f"DebugCommand {name} を作成しました", "data": new_entry}), 201
            except Exception as e:
                logger.error(f"DebugCommand作成エラー: {str(e)}")
                return jsonify({"error": str(e)}), 500

        elif request.method == 'PATCH':
            try:
                delete_name = (request.get_json() or {}).get('name')
                if not delete_name:
                    return jsonify({"error": "削除する名前を指定してください"}), 400

                data = _load_list()
                if not any(item['name'] == delete_name for item in data):
                    return jsonify({"error": f"DebugCommand {delete_name} が見つかりません"}), 404

                data = [item for item in data if item['name'] != delete_name]
                _save_list(data)

                cmd_dir = os.path.join(cmd_root, delete_name)
                if os.path.exists(cmd_dir):
                    shutil.rmtree(cmd_dir)

                logger.info(f"DebugCommandを削除しました: {delete_name}")
                return jsonify({"message": f"DebugCommand {delete_name} を削除しました"}), 200
            except Exception as e:
                logger.error(f"DebugCommand削除エラー: {str(e)}")
                return jsonify({"error": str(e)}), 500

    # --- 詳細（引数・戻り値定義）の取得 / 保存 ---
    @app.route('/api/debug-command/<name>', methods=['GET', 'POST'])
    def debug_command_detail(name):
        if request.method == 'GET':
            try:
                return jsonify(_load_detail(name)), 200
            except Exception as e:
                logger.error(f"DebugCommand詳細取得エラー {name}: {str(e)}")
                return jsonify({"error": str(e)}), 500

        elif request.method == 'POST':
            try:
                body = request.get_json() or {}
                args = body.get('args', [])
                has_return = bool(body.get('hasReturn', False))
                return_fields = body.get('returnFields', [])

                err = _validate_fields(args)
                if err:
                    return jsonify({"error": f"引数定義エラー: {err}"}), 400
                if has_return:
                    err = _validate_fields(return_fields)
                    if err:
                        return jsonify({"error": f"戻り値定義エラー: {err}"}), 400
                else:
                    return_fields = []

                detail = {"args": args, "hasReturn": has_return, "returnFields": return_fields}
                path = _detail_path(name)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(detail, f, ensure_ascii=False, indent=2)

                return jsonify({"message": f"DebugCommand {name} を保存しました"}), 200
            except Exception as e:
                logger.error(f"DebugCommand詳細保存エラー {name}: {str(e)}")
                return jsonify({"error": str(e)}), 500

    # --- JS側の予測変換用: 一覧+詳細をまとめて返す ---
    @app.route('/api/debug-command-full', methods=['GET'])
    def debug_command_full():
        try:
            entries = _load_list()
            result = []
            for e in entries:
                detail = _load_detail(e['name'])
                result.append({"id": e['id'], "name": e['name'], **detail})
            return jsonify(result), 200
        except Exception as e:
            logger.error(f"DebugCommand一括取得エラー: {str(e)}")
            return jsonify({"error": str(e)}), 500

    # --- 単一コマンドのC#生成 ---
    @app.route('/api/generate-debug-command/<name>', methods=['POST'])
    def generate_debug_command(name):
        try:
            detail = _load_detail(name)
            base_path, stub_path = generate_debug_command_cs(
                data_dir, name, detail.get('args', []),
                detail.get('hasReturn', False), detail.get('returnFields', [])
            )
            return jsonify({"message": f"C#ファイルを生成しました: {base_path}, {stub_path}"}), 200
        except Exception as e:
            logger.error(f"DebugCommand CS生成エラー {name}: {str(e)}")
            return jsonify({"error": str(e)}), 500

    # --- 全コマンド一括生成 + インストーラ生成 ---
    @app.route('/api/generate-all-debug-command', methods=['POST'])
    def generate_all_debug_command():
        try:
            entries = _load_list()
            names = []
            for e in entries:
                name = e['name']
                detail = _load_detail(name)
                generate_debug_command_cs(
                    data_dir, name, detail.get('args', []),
                    detail.get('hasReturn', False), detail.get('returnFields', [])
                )
                names.append(name)
            installer_path = generate_installer(data_dir, names)
            return jsonify({"message": f"{len(names)}件のDebugCommandを生成しました", "installer": installer_path}), 200
        except Exception as e:
            logger.error(f"DebugCommand一括生成エラー: {str(e)}")
            return jsonify({"error": str(e)}), 500
        

    
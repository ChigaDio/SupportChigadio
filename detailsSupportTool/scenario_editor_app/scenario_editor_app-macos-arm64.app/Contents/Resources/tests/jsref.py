"""元のJS(js_ref/src)をNodeで実行して結果を得る、差分テスト用ヘルパー。

    from jsref import run_js
    run_js('scenarioTransactionDsl', 'tokenizeLine', 'PlayBGM a=1')        # -> list[dict]
    run_js('scenarioTransactionDsl', 'compileDocument', text, role_schemas)

- module: js_ref/src/<module>.js (拡張子なし)
- fn: export されている関数名
- 引数は JSON でそのまま渡す。戻り値も JSON。undefined は null、Set は list、Map は dict、Error は例外で返る。
- 複数呼び出しをまとめたいときは run_js_batch(module, [(fn, args), ...])。
- 関数が JSON にできない値(関数・クラス)を返す場合は、js_expr で自分で変換する式を渡す:
    run_js_expr("import {x} from '...'; return x(...)")
"""
import json
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), 'js_ref', 'src')

_RUNNER = r"""
import { pathToFileURL } from 'node:url';
import fs from 'node:fs';
const req = JSON.parse(fs.readFileSync(0, 'utf8'));
const replacer = (k, v) => {
  if (v instanceof Set) return Array.from(v);
  if (v instanceof Map) return Object.fromEntries(v);
  if (v === undefined) return null;
  if (typeof v === 'number' && !Number.isFinite(v)) return { __num__: String(v) };
  return v;
};
const out = [];
for (const call of req.calls) {
  try {
    const mod = await import(pathToFileURL(req.src + '/' + call.module + '.js').href);
    const r = await mod[call.fn](...call.args);
    out.push({ ok: true, value: r });
  } catch (e) {
    out.push({ ok: false, error: String(e && e.message || e) });
  }
}
process.stdout.write(JSON.stringify(out, replacer));
"""


class JsError(Exception):
    pass


def run_js_batch(module, calls):
    """calls: [(fn, [args...]), ...] -> [value, ...] (JS が例外なら JsError)"""
    payload = json.dumps({'src': SRC, 'calls': [{'module': module, 'fn': fn, 'args': list(args)} for fn, args in calls]})
    p = subprocess.run(['node', '--input-type=module', '-e', _RUNNER], input=payload.encode('utf-8'),
                       capture_output=True, cwd=os.path.dirname(HERE), timeout=120)
    if p.returncode != 0:
        raise JsError(p.stderr.decode('utf-8', 'replace'))
    res = json.loads(p.stdout.decode('utf-8'))
    out = []
    for r in res:
        if not r['ok']:
            raise JsError(r['error'])
        out.append(r['value'])
    return out


def run_js(module, fn, *args):
    return run_js_batch(module, [(fn, args)])[0]

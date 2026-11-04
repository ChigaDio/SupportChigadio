"""差分テスト用の補助 (F2)。jsref.run_js では渡せない値(Set 等)を JS 側で組み立てて呼ぶ。

    run_js_adapter('scenarioValidation',
                   "(m, a) => m.validateGraph(a.nodes, a.edges, {...a.ctx, roleNames: a.ctx.roleNames && new Set(a.ctx.roleNames)})",
                   [case1, case2, ...])      # -> [値, ...]  (JS が例外なら JsError)

- adapter は JS の関数式 `(module, arg) => ...` (async 可)。module は import * したモジュール。
- 戻り値の undefined は null、Set は list、Map は dict (jsref と同じ)。
"""
import json
import os
import subprocess

from jsref import SRC, JsError

HERE = os.path.dirname(os.path.abspath(__file__))

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
const mod = await import(pathToFileURL(req.src + '/' + req.module + '.js').href);
const fn = eval(req.adapter);
const out = [];
for (const c of req.cases) {
  try { out.push({ ok: true, value: await fn(mod, c) }); }
  catch (e) { out.push({ ok: false, error: String(e && e.message || e) }); }
}
process.stdout.write(JSON.stringify(out, replacer));
"""


def run_js_adapter(module, adapter, cases, raise_errors=True):
    payload = json.dumps({'src': SRC, 'module': module, 'adapter': adapter, 'cases': list(cases)})
    p = subprocess.run(['node', '--input-type=module', '-e', _RUNNER], input=payload.encode('utf-8'),
                       capture_output=True, cwd=os.path.dirname(HERE), timeout=180)
    if p.returncode != 0:
        raise JsError(p.stderr.decode('utf-8', 'replace'))
    res = json.loads(p.stdout.decode('utf-8'))
    out = []
    for r in res:
        if not r['ok']:
            if raise_errors:
                raise JsError(r['error'])
            out.append({'__error__': r['error']})
        else:
            out.append(r['value'])
    return out


def norm(x):
    """JS(JSON 経由)と Python の戻り値を比較しやすい形に揃える: None のキーは落とす / 整数値の float は int / set は sorted list。"""
    from scenario_editor.core.diff import UNDEFINED
    if x is UNDEFINED:
        return None
    if isinstance(x, dict):
        return {k: norm(v) for k, v in x.items() if v is not None and v is not UNDEFINED}
    if isinstance(x, (list, tuple)):
        return [norm(v) for v in x]
    if isinstance(x, (set, frozenset)):
        return sorted(norm(v) for v in x)
    if isinstance(x, float) and x == x and abs(x) < 1e15 and x == int(x):
        return int(x)
    return x

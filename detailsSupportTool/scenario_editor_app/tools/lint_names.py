"""PySide6 が入れられない環境でも Qt 層のコードの凡ミスを見つけるための静的チェック (pyflakes 相当 + α)。

  python tools/lint_names.py            # scenario_editor/ 全体
  python tools/lint_names.py path ...   # 指定ファイル/フォルダ

検査: ① 構文  ② 未定義の名前  ③ 未使用 import  ④ モジュール別名の属性 (C.xxx / T.xxx がそのモジュールに有るか)
      ⑤ プロジェクト内の関数・クラス・self メソッド呼び出しの引数の数/キーワード名
      ⑥ self.xxx (snake_case) がクラス階層のどこにも代入/定義されていない
終了コード: 問題があれば 1。誤検出しうる箇所は行末に  # lint: ignore  を付ける。
"""
from __future__ import annotations

import ast
import builtins
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = "scenario_editor"
BUILTINS = set(dir(builtins)) | {"__file__", "__name__", "__doc__"}
# Qt の小文字1語メソッド (self.xxx の検査から除外)
QT_WORDS = set("""show hide close update repaint size pos move resize rect geometry parent window layout font palette style
 raise_ lower lower_ setParent focus clear count text value data item items width height x y cursor event key accept ignore
 children sender isVisible objectName type delete deleteLater setFocus insert add remove take index row column
 reject accept done grab rehighlight document viewport completer activated toggled clicked changed selected current
 """.split())


def module_name(path):
    rel = os.path.relpath(path, ROOT)[:-3].replace(os.sep, ".")
    return rel[:-9] if rel.endswith(".__init__") else rel


def resolve_from(cur_mod, is_pkg, node):
    if node.level == 0:
        return node.module or ""
    parts = cur_mod.split(".")
    base = parts if is_pkg else parts[:-1]
    base = base[: len(base) - (node.level - 1)] if node.level > 1 else base
    return ".".join(base + ([node.module] if node.module else []))


class ModInfo:
    def __init__(self, path):
        self.path = path
        self.name = module_name(path)
        self.is_pkg = path.endswith("__init__.py")
        self.src = open(path, encoding="utf-8").read()
        self.lines = self.src.splitlines()
        self.tree = ast.parse(self.src, path)
        self.top = {}        # 名前 -> node (def/class/assign/import)
        self.imports = {}    # 名前 -> (module, attr|None)
        self.all_names = set()
        for n in self.tree.body:
            self._collect(n)

    def _collect(self, n):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            self.top[n.name] = n
        elif isinstance(n, ast.Import):
            for a in n.names:
                nm = (a.asname or a.name).split(".")[0]
                self.top[nm] = n
                self.imports[nm] = (a.name if a.asname else a.name.split(".")[0], None)
        elif isinstance(n, ast.ImportFrom):
            mod = resolve_from(self.name, self.is_pkg, n)
            for a in n.names:
                if a.name == "*":
                    continue
                self.top[a.asname or a.name] = n
                self.imports[a.asname or a.name] = (mod, a.name)
        elif isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            for t in (n.targets if isinstance(n, ast.Assign) else [n.target]):
                for x in ast.walk(t):
                    if isinstance(x, ast.Name):
                        self.top[x.id] = n
        elif isinstance(n, (ast.If, ast.Try, ast.With, ast.For, ast.While)):
            for sub in ast.iter_child_nodes(n):
                if isinstance(sub, list):
                    continue
                if isinstance(sub, ast.stmt):
                    self._collect(sub)
            for blk in ("body", "orelse", "finalbody", "handlers"):
                for sub in getattr(n, blk, []) or []:
                    if isinstance(sub, ast.ExceptHandler):
                        for s2 in sub.body:
                            self._collect(s2)
                    elif isinstance(sub, ast.stmt):
                        self._collect(sub)


class Linter:
    def __init__(self, files):
        self.mods = {}
        self.problems = []
        for f in files:
            try:
                m = ModInfo(f)
            except SyntaxError as e:
                self.problems.append((f, e.lineno or 0, f"構文エラー: {e.msg}"))
                continue
            self.mods[m.name] = m
        self.extra = {}   # 解析対象外の project モジュール (パス解決用)

    # ------------------------------------------------------------------ util
    def report(self, mod, node, msg):
        line = getattr(node, "lineno", 0)
        if 0 < line <= len(mod.lines) and "lint: ignore" in mod.lines[line - 1]:
            return
        self.problems.append((mod.path, line, msg))

    def get_mod(self, name):
        if name in self.mods:
            return self.mods[name]
        if name in self.extra:
            return self.extra[name]
        p = os.path.join(ROOT, *name.split("."))
        for cand in (p + ".py", os.path.join(p, "__init__.py")):
            if os.path.exists(cand):
                try:
                    self.extra[name] = ModInfo(cand)
                    return self.extra[name]
                except SyntaxError:
                    return None
        return None

    def is_project(self, modname):
        return modname == PKG or modname.startswith(PKG + ".")

    # ------------------------------------------------------------------ 実行
    def run(self):
        for m in list(self.mods.values()):
            self.check_module(m)
        return self.problems

    def check_module(self, m):
        self.check_names(m)
        self.check_unused_imports(m)
        self.check_attrs_and_calls(m)

    # ------------------------------------------------------------------ ② 未定義名
    def check_names(self, m):
        mod_names = set(m.top) | BUILTINS

        def bound_in(node):
            """この関数/モジュール直下で束縛される名前。"""
            names = set()
            args = getattr(node, "args", None)
            if args:
                for a in args.posonlyargs + args.args + args.kwonlyargs:
                    names.add(a.arg)
                if args.vararg:
                    names.add(args.vararg.arg)
                if args.kwarg:
                    names.add(args.kwarg.arg)
            stack = list(ast.iter_child_nodes(node)) if not isinstance(node, ast.Lambda) else [node.body]
            while stack:
                x = stack.pop()
                if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    names.add(x.name)
                    continue          # 中身は別スコープ
                if isinstance(x, ast.Lambda):
                    continue
                if isinstance(x, ast.Name) and isinstance(x.ctx, (ast.Store, ast.Del)):
                    names.add(x.id)
                elif isinstance(x, (ast.Import, ast.ImportFrom)):
                    for a in x.names:
                        names.add((a.asname or a.name).split(".")[0])
                elif isinstance(x, ast.ExceptHandler) and x.name:
                    names.add(x.name)
                elif isinstance(x, (ast.Global, ast.Nonlocal)):
                    names.update(x.names)
                elif isinstance(x, ast.NamedExpr):
                    names.add(x.target.id)
                elif isinstance(x, ast.MatchAs) and x.name:
                    names.add(x.name)
                stack.extend(ast.iter_child_nodes(x))
            return names

        def visit(node, scopes):
            """scopes: 外側から順の束縛集合のリスト (クラススコープは入れない)。"""
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                    for d in (child.args.defaults + [d for d in child.args.kw_defaults if d]):
                        visit_expr(d, scopes)
                    for dec in getattr(child, "decorator_list", []):
                        visit_expr(dec, scopes)
                    inner = scopes + [bound_in(child)]
                    if isinstance(child, ast.Lambda):
                        visit_expr(child.body, inner)
                    else:
                        visit(child, inner)
                elif isinstance(child, ast.ClassDef):
                    for b in child.bases + [k.value for k in child.keywords]:
                        visit_expr(b, scopes)
                    for dec in child.decorator_list:
                        visit_expr(dec, scopes)
                    visit_class(child, scopes)
                else:
                    visit_stmt_or_expr(child, scopes)

        def visit_class(cls, scopes):
            cls_names = bound_in(cls)
            for child in cls.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for d in child.args.defaults + [d for d in child.args.kw_defaults if d]:
                        visit_expr(d, scopes + [cls_names])
                    for dec in child.decorator_list:
                        visit_expr(dec, scopes + [cls_names])
                    visit(child, scopes + [bound_in(child)])      # メソッドからクラス変数は直接見えない
                elif isinstance(child, ast.ClassDef):
                    visit_class(child, scopes + [cls_names])
                else:
                    visit_stmt_or_expr(child, scopes + [cls_names])

        def visit_expr(e, scopes):
            visit_stmt_or_expr(e, scopes)

        def visit_stmt_or_expr(node, scopes):
            # 内包表記は独自スコープ
            if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
                comp = set()
                for g in node.generators:
                    for x in ast.walk(g.target):
                        if isinstance(x, ast.Name):
                            comp.add(x.id)
                inner = scopes + [comp]
                for g in node.generators:
                    visit_stmt_or_expr(g.iter, scopes if g is node.generators[0] else inner)
                    for c in g.ifs:
                        visit_stmt_or_expr(c, inner)
                if isinstance(node, ast.DictComp):
                    visit_stmt_or_expr(node.key, inner)
                    visit_stmt_or_expr(node.value, inner)
                else:
                    visit_stmt_or_expr(node.elt, inner)
                return
            if isinstance(node, ast.Name):
                if isinstance(node.ctx, ast.Load):
                    if not (any(node.id in s for s in scopes) or node.id in mod_names):
                        self.report(m, node, f"未定義の名前: {node.id}")
                return
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                visit(ast.Module(body=[node], type_ignores=[]), scopes)
                return
            for c in ast.iter_child_nodes(node):
                visit_stmt_or_expr(c, scopes)

        visit(m.tree, [bound_in(m.tree)])

    # ------------------------------------------------------------------ ③ 未使用 import
    def check_unused_imports(self, m):
        if m.path.endswith("__init__.py"):
            return
        used = set()
        for n in ast.walk(m.tree):
            if isinstance(n, ast.Name):
                used.add(n.id)
            elif isinstance(n, ast.Attribute):
                pass
        # 文字列注釈 (from __future__ import annotations) 内の使用
        for n in ast.walk(m.tree):
            if isinstance(n, ast.Constant) and isinstance(n.value, str):
                for tok in n.value.replace("|", " ").replace("[", " ").replace("]", " ").replace(",", " ").split():
                    used.add(tok.split(".")[0])
        for n in m.tree.body:
            if isinstance(n, (ast.Import, ast.ImportFrom)):
                if isinstance(n, ast.ImportFrom) and n.module == "__future__":
                    continue
                for a in n.names:
                    nm = (a.asname or a.name).split(".")[0]
                    if nm not in used:
                        self.report(m, n, f"未使用の import: {nm}")

    # ------------------------------------------------------------------ ④⑤⑥ 属性と呼び出し
    def sig_of(self, fn, drop_first):
        a = fn.args
        pos = [x.arg for x in a.posonlyargs + a.args]
        if drop_first and pos:
            pos = pos[1:]
        n_def = len(a.defaults)
        required = pos[: len(pos) - n_def] if n_def else pos
        kwonly = [x.arg for x in a.kwonlyargs]
        kw_required = [x.arg for x, d in zip(a.kwonlyargs, a.kw_defaults) if d is None]
        return {"pos": pos, "required": required, "kwonly": kwonly, "kw_required": kw_required,
                "vararg": a.vararg is not None, "kwarg": a.kwarg is not None}

    def check_call(self, m, call, sig, what):
        if any(isinstance(x, ast.Starred) for x in call.args) or any(k.arg is None for k in call.keywords):
            return
        npos = len(call.args)
        kws = [k.arg for k in call.keywords]
        if npos > len(sig["pos"]) and not sig["vararg"]:
            self.report(m, call, f"{what}: 位置引数が多すぎます ({npos} > {len(sig['pos'])})")
            return
        for k in kws:
            if k not in sig["pos"] and k not in sig["kwonly"] and not sig["kwarg"]:
                self.report(m, call, f"{what}: 不明なキーワード引数 {k}=")
        filled = set(sig["pos"][:npos]) | set(kws)
        miss = [r for r in sig["required"] if r not in filled] + [r for r in sig["kw_required"] if r not in kws]
        if miss:
            self.report(m, call, f"{what}: 必須引数が足りません {miss}")

    def resolve_name(self, m, name):
        """モジュール内の名前 -> ('mod', ModInfo) | ('func'|'class', ModInfo, node) | None"""
        if name in m.top and isinstance(m.top[name], (ast.FunctionDef, ast.ClassDef)):
            n = m.top[name]
            return ("class" if isinstance(n, ast.ClassDef) else "func", m, n)
        imp = m.imports.get(name)
        if imp and self.is_project(imp[0]):
            mod, attr = imp
            if attr is None:
                tm = self.get_mod(mod)
                return ("mod", tm) if tm else None
            sub = self.get_mod(f"{mod}.{attr}")
            if sub is not None and not (self.get_mod(mod) and attr in self.get_mod(mod).top and not isinstance(self.get_mod(mod).top[attr], ast.ImportFrom)):
                return ("mod", sub)
            pm = self.get_mod(mod)
            if pm and attr in pm.top:
                n = pm.top[attr]
                if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
                    return ("class" if isinstance(n, ast.ClassDef) else "func", pm, n)
                if isinstance(n, ast.ImportFrom):       # 再エクスポート
                    return self.resolve_name(pm, attr)
        return None

    def class_methods(self, m, cls, seen=None):
        """(メソッド dict, 属性集合, 全基底が解決できたか)"""
        seen = seen or set()
        methods, attrs, complete = {}, set(), True
        if id(cls) in seen:
            return methods, attrs, complete
        seen.add(id(cls))
        for b in cls.bases:
            r = None
            if isinstance(b, ast.Name):
                r = self.resolve_name(m, b.id)
            elif isinstance(b, ast.Attribute) and isinstance(b.value, ast.Name):
                base_mod = self.resolve_name(m, b.value.id)
                if base_mod and base_mod[0] == "mod" and b.attr in base_mod[1].top:
                    n = base_mod[1].top[b.attr]
                    if isinstance(n, ast.ClassDef):
                        r = ("class", base_mod[1], n)
            if r and r[0] == "class":
                mm, aa, cc = self.class_methods(r[1], r[2], seen)
                methods.update(mm)
                attrs |= aa
                complete = complete and cc
            else:
                complete = False          # Qt など解析対象外の基底
        for n in cls.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods[n.name] = (n, m)
                for x in ast.walk(n):
                    if isinstance(x, ast.Attribute) and isinstance(x.value, ast.Name) and x.value.id == "self" and isinstance(x.ctx, ast.Store):
                        attrs.add(x.attr)
                    if isinstance(x, ast.Call) and isinstance(x.func, ast.Name) and x.func.id in ("setattr",) and len(x.args) >= 2 \
                            and isinstance(x.args[1], ast.Constant):
                        attrs.add(x.args[1].value)
            elif isinstance(n, (ast.Assign, ast.AnnAssign)):
                for t in (n.targets if isinstance(n, ast.Assign) else [n.target]):
                    if isinstance(t, ast.Name):
                        attrs.add(t.id)
        return methods, attrs, complete

    def check_attrs_and_calls(self, m):
        for cls in [n for n in ast.walk(m.tree) if isinstance(n, ast.ClassDef)]:
            methods, attrs, _complete = self.class_methods(m, cls)
            known = set(methods) | attrs
            for fn in [n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
                is_static = any(isinstance(d, ast.Name) and d.id == "staticmethod" for d in fn.decorator_list)
                selfname = fn.args.args[0].arg if fn.args.args and not is_static else None
                if selfname is None:
                    continue
                for x in ast.walk(fn):
                    if isinstance(x, ast.Attribute) and isinstance(x.value, ast.Name) and x.value.id == selfname and isinstance(x.ctx, ast.Load):
                        a = x.attr
                        if a in known or a.startswith("__"):
                            continue
                        snake = "_" in a.strip("_") or a.startswith("_")
                        if snake or (a.islower() and a not in QT_WORDS and not _complete_qt(a)):
                            self.report(m, x, f"self.{a} はこのクラス階層のどこにも定義/代入されていません")
                    if isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute) and isinstance(x.func.value, ast.Name) \
                            and x.func.value.id == selfname and x.func.attr in methods:
                        f, fm = methods[x.func.attr]
                        deco = [d.id for d in f.decorator_list if isinstance(d, ast.Name)]
                        if "property" in deco:
                            continue
                        self.check_call(m, x, self.sig_of(f, "staticmethod" not in deco), f"{cls.name}.{x.func.attr}()")
        # モジュール別名の属性 / 関数・クラスの呼び出し
        for x in ast.walk(m.tree):
            if isinstance(x, ast.Attribute) and isinstance(x.value, ast.Name) and isinstance(x.ctx, ast.Load):
                r = self.resolve_name(m, x.value.id) if x.value.id in m.imports else None
                if r and r[0] == "mod" and x.attr not in r[1].top and not x.attr.startswith("__"):
                    sub = self.get_mod(f"{r[1].name}.{x.attr}")
                    if sub is None:
                        self.report(m, x, f"{x.value.id}.{x.attr}: モジュール {r[1].name} にそんな名前はありません")
            if isinstance(x, ast.Call):
                f = x.func
                r = None
                if isinstance(f, ast.Name):
                    r = self.resolve_name(m, f.id)
                elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id in m.imports:
                    base = self.resolve_name(m, f.value.id)
                    if base and base[0] == "mod" and f.attr in base[1].top and isinstance(base[1].top[f.attr], (ast.FunctionDef, ast.ClassDef)):
                        n = base[1].top[f.attr]
                        r = ("class" if isinstance(n, ast.ClassDef) else "func", base[1], n)
                if not r:
                    continue
                if r[0] == "func":
                    self.check_call(m, x, self.sig_of(r[2], False), f"{r[2].name}()")
                elif r[0] == "class":
                    methods, _a, complete = self.class_methods(r[1], r[2])
                    init = methods.get("__init__")
                    if init:
                        self.check_call(m, x, self.sig_of(init[0], True), f"{r[2].name}()")


def _complete_qt(_a):
    return False


def collect(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            for d, _dirs, files in os.walk(p):
                if "__pycache__" in d:
                    continue
                out += [os.path.join(d, f) for f in files if f.endswith(".py")]
        elif p.endswith(".py"):
            out.append(p)
    return sorted(os.path.abspath(x) for x in out)


def main(argv):
    sys.path.insert(0, ROOT)
    paths = argv or [os.path.join(ROOT, PKG), os.path.join(ROOT, "main.py")]
    files = collect(paths)
    problems = Linter(files).run()
    problems.sort()
    for path, line, msg in problems:
        print(f"{os.path.relpath(path, ROOT)}:{line}: {msg}")
    print(f"\n{len(files)} files, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_docs.py  ―  スクリプター向けドキュメントサイト生成ツール

Role定義(JSON)・enum・ClassDataID・RoleAction.cs を読み取り、
検索できる辞書つきの「1ファイル完結のHTML」を生成する。

使い方:
    python build_docs.py --data-dir <dataフォルダ> --out dist/index.html

    (サンプルで試す)
    python build_docs.py --data-dir sample_data

オプション:
    --data-dir   エディタの data フォルダ。以下を読み取る(無いものは自動でスキップ)
                   scenario_data/scenario_role/scenario_role_list.json
                   scenario_data/scenario_role/<Role>/<Role>.json
                   scenario_data/scenario_role/<Role>/<Role>RoleAction.cs   (任意: 動作状況の自動判定)
                   enum/enum_list.json , enum/<Name>/<Name>.json            (任意: 選べる値の一覧)
                   class_data_id/class_data_id_list.json , class_data_id/<Name>/<Name>.json (任意)
    --content    手書き原稿フォルダ (既定: ./content)
    --out        出力HTML (既定: ./dist/index.html)
    --title      サイトの題名
    --strict     警告をエラー扱いにして失敗させる(CI向け)
"""
import argparse
import glob
import json
import os
import re
import sys
import datetime

try:
    import markdown
except ImportError:
    sys.exit("markdown ライブラリが必要です:  pip install markdown")

HERE = os.path.dirname(os.path.abspath(__file__))
WARNINGS = []


def warn(msg):
    WARNINGS.append(msg)
    print("  [警告] " + msg)


def read_json(path, default=None):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception as e:  # noqa
        warn(f"JSONを読めませんでした: {path} ({e})")
        return default


def read_text(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return f.read()


# ---------------------------------------------------------------- 型の分類
BUILTIN_NUM = {"int", "uint", "short", "long", "byte", "float", "double", "decimal"}
VECTORS = {"vector2": ["x", "y"], "vector3": ["x", "y", "z"], "vector4": ["x", "y", "z", "w"]}


def base_type(t):
    t = t or ""
    return t[:-2] if t.endswith("[]") else t


def classify(t, enum_names, class_id_names):
    """型名 → 表示用の種類(kind)。サイト上の色分けと説明文に使う。"""
    b = base_type(t)
    low = b.lower()
    if low in BUILTIN_NUM:
        return "number"
    if low == "bool":
        return "bool"
    if low == "string":
        return "string"
    if low in VECTORS:
        return "vector"
    if low in ("color", "bit", "bezier", "dictionary"):
        return low
    if low in ("text_list_index", "voice_ref"):
        return "index"
    if b in enum_names:
        return "enum"
    if b in class_id_names:
        return "id"
    return "ref"  # enum / ClassDataID / class_data のいずれか(データ未指定時は区別できない)


# ---------------------------------------------------------------- 例の自動生成
def fmt_num(v):
    if isinstance(v, float) and v == int(v):
        return str(int(v)) if abs(v) >= 1 else str(v)
    return str(v)


def dsl_value_from_default(v, t=""):
    """JSONの default 値を DSL の書き方に直す。"""
    low = base_type(t).lower()
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return fmt_num(v)
    if isinstance(v, str):
        if low == "string":
            return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
        return v
    if isinstance(v, list):
        if low in VECTORS and len(v) == len(VECTORS[low]):
            return "{ " + ", ".join(f"{n}: {fmt_num(x)}" for n, x in zip(VECTORS[low], v)) + " }"
        if low not in VECTORS and 2 <= len(v) <= 4 and all(isinstance(x, (int, float)) for x in v):
            names = VECTORS[f"vector{len(v)}"]
            return "{ " + ", ".join(f"{n}: {fmt_num(x)}" for n, x in zip(names, v)) + " }"
        return "[" + ", ".join(dsl_value_from_default(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{k}: {dsl_value_from_default(x)}" for k, x in v.items()) + " }"
    return str(v)


def placeholder_for(field, enum_values):
    t = field["type"]
    b = base_type(t)
    low = b.lower()
    if field.get("arraySize", 0) or t.endswith("[]"):
        inner = placeholder_for({**field, "type": b, "arraySize": 0}, enum_values)
        return f"[{inner}, {inner}]"
    if low in ("int", "uint", "short", "long", "byte"):
        return "0"
    if low in ("float", "double", "decimal"):
        return "1"
    if low == "bool":
        return "true"
    if low == "string":
        return '"テキスト"'
    if low in VECTORS:
        return "{ " + ", ".join(f"{n}: 0" for n in VECTORS[low]) + " }"
    if low == "color":
        return "{ r: 1, g: 1, b: 1, a: 1 }"
    if low == "bit":
        return "{ size: 8, bits: [0, 2] }"
    if low == "bezier":
        return "{ points: [{ time: 0, value: 0, inTangent: 0, outTangent: 0 }, { time: 1, value: 1, inTangent: 0, outTangent: 0 }] }"
    if low == "dictionary":
        return '{"key":"value"}'
    if low in ("text_list_index", "voice_ref"):
        return "0"
    vals = enum_values.get(b) or []
    vals = [v for v in vals if not v.endswith(".None") and v != "None"]
    if vals:
        return short_enum(vals[0])
    return f"<{b}>"


def short_enum(v):
    return v.split(".", 1)[1] if "." in v else v


def example_value(field, enum_values):
    if "default" in field and field["default"] is not None:
        return dsl_value_from_default(field["default"], field["type"])
    return placeholder_for(field, enum_values)


# ---------------------------------------------------------------- C# の解析
BOILER = re.compile(
    r"^\s*(using\b|namespace\b|[{}]\s*;?\s*$|//|public\s+override|public\s+\w+Action\(|Is\w+\s*=\s*true;|"
    r"base\.\w+\(|Debug\.Log|await\s+UniTask\.CompletedTask;|return;|\}\s*$|public class|private\s+\w+\s+\w+\s*;)"
)


def analyze_action(cs_text):
    """RoleAction.cs の中身から『動くのか/スキップ対応か』を推定する(あくまで目安)。"""
    if not cs_text:
        return {"known": False}
    code = re.sub(r"/\*.*?\*/", "", cs_text, flags=re.S)
    meaningful = [ln for ln in code.splitlines() if ln.strip() and not BOILER.match(ln)]
    return {
        "known": True,
        "implemented": len(meaningful) >= 3,
        "skip": "skip_scenario" in code,
        "click_skip": "ScenarioKeyNextClick" in code,
        "waits": bool(re.search(r"IsUpdateAsync\s*=\s*true", code)) and "ScenarioKeyNextClick" in code,
        "meaningful_lines": len(meaningful),
    }


# ---------------------------------------------------------------- 読み込み
def load_enums(data_dir):
    """enum / ClassDataID の値を {型名: [{name, desc}]} で返す。"""
    out, kinds = {}, {}
    enum_dir = os.path.join(data_dir, "enum")
    lst = read_json(os.path.join(enum_dir, "enum_list.json"), []) or []
    for e in lst:
        name = e.get("name")
        items = read_json(os.path.join(enum_dir, name, f"{name}.json"), []) or []
        vals = []
        for it in items:
            if isinstance(it, dict) and it.get("property"):
                desc = next((str(it[k]) for k in ("description", "comment", "label", "display_name", "name") if it.get(k) and it.get(k) != it["property"]), "")
                vals.append({"name": it["property"], "desc": desc})
        out[name] = vals
        kinds[name] = "enum"
    cid_dir = os.path.join(data_dir, "class_data_id")
    lst = read_json(os.path.join(cid_dir, "class_data_id_list.json"), []) or []
    for c in lst:
        name = c.get("name")
        tbl = read_json(os.path.join(cid_dir, name, f"{name}.json"), {}) or {}
        vals = []
        for r in tbl.get("rows", []):
            if isinstance(r, dict) and r.get("enum_property"):
                desc = next((str(r[k]) for k in ("description", "comment", "label", "display_name", "name") if r.get(k) and r.get(k) != r["enum_property"]), "")
                vals.append({"name": r["enum_property"], "desc": desc})
        out[name] = vals
        kinds[name] = "id"
    return out, kinds


def load_roles(data_dir):
    role_root = os.path.join(data_dir, "scenario_data", "scenario_role")
    lst = read_json(os.path.join(role_root, "scenario_role_list.json"), None)
    if lst is None:
        sys.exit(f"scenario_role_list.json が見つかりません: {role_root}\n--data-dir を確認してください。")
    roles = []
    for r in lst:
        name = r["name"]
        rj = read_json(os.path.join(role_root, name, f"{name}.json"), None)
        if rj is None:
            warn(f"Role定義 {name}.json が見つかりません(一覧にはあるのでスキップ)")
            continue
        cs_path = os.path.join(role_root, name, f"{name}RoleAction.cs")
        cs = read_text(cs_path) if os.path.exists(cs_path) else None
        roles.append({
            "id": r.get("id"), "name": name, "description": r.get("description", ""),
            "branchType": r.get("branchType", rj.get("branchType", "General")),
            "fields_raw": rj.get("data", []),
            # タグ: エディタのRole一覧(scenario_role_list.json)が正。無ければRole JSON、最後に content/role_notes.json
            "tags": r.get("tags") or rj.get("tags") or None,
            "action": analyze_action(cs),
        })
    return roles


# ---------------------------------------------------------------- 原稿(Markdown)
def md_to_html(text):
    md = markdown.Markdown(extensions=["fenced_code", "tables", "admonition", "attr_list", "sane_lists"],
                           output_format="html")
    html = md.convert(text)
    return html


def split_h2(html):
    """<h2> ごとの見出し一覧(右側の目次用)。idを付ける。"""
    heads = []

    def repl(m):
        title = re.sub(r"<[^>]+>", "", m.group(2))
        hid = "h-" + re.sub(r"[^0-9A-Za-zぁ-んァ-ヶ一-龠ー]+", "-", title).strip("-")
        heads.append({"id": hid, "title": title})
        return f'<h2 id="{hid}">{m.group(2)}</h2>'
    html = re.sub(r"<h2([^>]*)>(.*?)</h2>", repl, html, flags=re.S)
    return html, heads


def load_guides(content_dir, project):
    guides = []
    gdir = os.path.join(content_dir, "guides")
    for path in sorted(glob.glob(os.path.join(gdir, "*.md"))):
        raw = read_text(path)
        meta = {}
        m = re.match(r"^---\n(.*?)\n---\n", raw, flags=re.S)
        if m:
            for ln in m.group(1).splitlines():
                if ":" in ln:
                    k, v = ln.split(":", 1)
                    meta[k.strip()] = v.strip()
            raw = raw[m.end():]
        # {{project.key}} を project.json の値に差し替える
        raw = re.sub(r"\{\{\s*project\.([\w.]+)\s*\}\}", lambda mm: str(project.get(mm.group(1), f"〈{mm.group(1)}を project.json に設定〉")), raw)
        html, heads = split_h2(md_to_html(raw))
        gid = os.path.splitext(os.path.basename(path))[0]
        gid = re.sub(r"^\d+-", "", gid)
        guides.append({
            "id": gid, "title": meta.get("title", gid), "summary": meta.get("summary", ""),
            "group": meta.get("group", "guide"), "html": html, "headings": heads,
            "text": re.sub(r"<[^>]+>", " ", html),
        })
    return guides


# ---------------------------------------------------------------- 組み立て
def build_data(args):
    data_dir = args.data_dir
    content_dir = args.content
    project = read_json(os.path.join(content_dir, "project.json"), {}) or {}
    notes = read_json(os.path.join(content_dir, "role_notes.json"), {}) or {}
    glossary = read_json(os.path.join(content_dir, "glossary.json"), []) or []
    type_notes = read_json(os.path.join(content_dir, "type_notes.json"), {}) or {}

    enum_data, enum_kind = load_enums(data_dir)
    enum_names = {k for k, v in enum_kind.items() if v == "enum"}
    cid_names = {k for k, v in enum_kind.items() if v == "id"}
    # データフォルダに無い型でも、type_notes.json に values があれば「確認済みの値」として使う
    for tname, tn in type_notes.items():
        if tname not in enum_data and tn.get("values"):
            enum_data[tname] = [{"name": v["name"], "desc": v.get("desc", "")} if isinstance(v, dict) else {"name": v, "desc": ""} for v in tn["values"]]
    enum_short = {k: [v["name"] for v in vs] for k, vs in enum_data.items()}

    roles = load_roles(data_dir)
    types = {}  # name -> dict

    def type_entry(name):
        if name not in types:
            types[name] = {"name": name, "kind": classify(name, enum_names, cid_names), "usedBy": [], "values": [], "known": []}
        return types[name]

    out_roles = []
    for r in roles:
        fields = []
        for f in sorted(r["fields_raw"], key=lambda x: x.get("id", 0)):
            t = f.get("type", "")
            b = base_type(t)
            kind = classify(t, enum_names, cid_names)
            dep = f.get("dependency")
            fld = {
                "id": f.get("id"), "name": f.get("name"), "type": t, "baseType": b, "kind": kind,
                "description": f.get("description", ""), "required": bool(f.get("required", False)),
                "isArray": bool(f.get("arraySize", 0)) or t.endswith("[]"),
                "arraySize": f.get("arraySize", 0), "options": f.get("options"),
            }
            if "default" in f and f["default"] is not None:
                fld["default"] = f["default"]
                fld["defaultDsl"] = dsl_value_from_default(f["default"], t)
            if dep:
                fld["dependency"] = {"field": dep.get("parentFieldName"), "values": dep.get("enableValues", []),
                                     "hide": bool(dep.get("hideWhenDisabled"))}
            fld["exampleDsl"] = example_value(fld, enum_short)
            fields.append(fld)
            te = type_entry(b)
            te["usedBy"].append({"role": r["name"], "field": fld["name"]})
            # データ未指定でも、定義の中に出てくる値(default / dependency)は「確認済みの値」として覚える
            if kind in ("ref", "enum", "id"):
                cand = []
                if isinstance(fld.get("default"), str):
                    cand.append(fld["default"])
                if dep:
                    cand += [str(x) for x in dep.get("enableValues", [])]
                for c in cand:
                    if c not in te["known"]:
                        te["known"].append(c)

        # DSL 1行(必須だけ / 全部)
        def line(fs):
            return r["name"] + "".join(f" {x['name']}={x['exampleDsl']}" for x in fs)

        a = r["action"]
        rn = notes.get(r["name"], {})
        tags = r.get("tags") or ([rn["category"]] if rn.get("category") else [])
        tags = [str(t).strip() for t in tags if str(t).strip()]
        if not tags:
            warn(f"Role {r['name']} にタグがありません(エディタのRole一覧でタグを設定してください。いまは「その他」に入ります)")
        out_roles.append({
            "id": r["id"], "name": r["name"], "description": r["description"], "branchType": r["branchType"],
            "tags": tags,
            "fields": fields,
            "lineRequired": line([x for x in fields if x["required"]]),
            "lineAll": line(fields),
            "action": a,
            "notes": rn,
        })

    # 型辞書
    out_types = []
    for name, te in sorted(types.items(), key=lambda kv: kv[0].lower()):
        vals = enum_data.get(name, [])
        tn = type_notes.get(name, {})
        te["values"] = vals
        te["complete"] = name in enum_kind
        te["summary"] = tn.get("summary", "")
        te["howto"] = tn.get("howto", "")
        te["dsl"] = tn.get("dsl", "")
        if name in enum_kind:
            te["kind"] = enum_kind[name]
        out_types.append(te)

    guides = load_guides(content_dir, project)

    meta = {
        "title": args.title,
        "generatedAt": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "roleCount": len(out_roles),
        "enumLoaded": bool(enum_data),
        "project": project,
    }
    return {"meta": meta, "roles": out_roles, "types": out_types, "guides": guides, "glossary": glossary}


def safe_name(n):
    return re.sub(r"[^0-9A-Za-z_.-]", "_", str(n))


def page_list(data):
    """複数ファイル出力のページ一覧: (ファイル名, DOC_PAGE値, <title>)"""
    t = data["meta"]["title"]
    pages = [("index.html", "home", t),
             ("roles.html", "roles", f"Role辞典 ｜ {t}"),
             ("types.html", "types", f"型・選択肢辞典 ｜ {t}"),
             ("glossary.html", "glossary", f"用語集 ｜ {t}")]
    for r in data["roles"]:
        pages.append((f"role-{safe_name(r['name'])}.html", f"role:{r['name']}", f"{r['description']}（{r['name']}） ｜ {t}"))
    for ty in data["types"]:
        pages.append((f"type-{safe_name(ty['name'])}.html", f"type:{ty['name']}", f"{ty['name']} ｜ {t}"))
    for g in data["guides"]:
        pages.append((f"guide-{safe_name(g['id'])}.html", f"guide:{g['id']}", f"{g['title']} ｜ {t}"))
    return pages


def build_multi(args, data, tpl, css, js):
    out = args.out_dir
    assets = os.path.join(out, "assets")
    os.makedirs(assets, exist_ok=True)
    # 古い出力を消す(前回あったRoleのページが残らないように)。自分が作った種類のファイルだけ
    for f in glob.glob(os.path.join(out, "*.html")):
        os.remove(f)
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    with open(os.path.join(assets, "style.css"), "w", encoding="utf-8") as f:
        f.write(css)
    with open(os.path.join(assets, "app.js"), "w", encoding="utf-8") as f:
        f.write(js)
    with open(os.path.join(assets, "data.js"), "w", encoding="utf-8") as f:
        f.write("window.DOC_DATA=" + payload + ";\n")
    shell = re.sub(r"<style>\s*/\*__CSS__\*/\s*</style>", '<link rel="stylesheet" href="assets/style.css">', tpl)
    shell = re.sub(r'<script id="data" type="application/json">__DATA__</script>', "<!--DATA-->", shell)
    shell = re.sub(r"<script>\s*/\*__JS__\*/\s*</script>", '<script src="assets/app.js"></script>', shell)
    pages = page_list(data)
    for fname, key, title in pages:
        h = shell.replace("<!--DATA-->", '<script src="assets/data.js"></script>\n<script>window.DOC_PAGE=' + json.dumps(key, ensure_ascii=False) + ';</script>')
        h = h.replace("__HOME__", "index.html")
        h = re.sub(r"<title>.*?</title>", "<title>" + title.replace("\\", "") .replace("&", "&amp;").replace("<", "&lt;") + "</title>", h, count=1)
        h = h.replace("__TITLE__", args.title)
        with open(os.path.join(out, fname), "w", encoding="utf-8") as f:
            f.write(h)
    return len(pages)


def main():
    ap = argparse.ArgumentParser(description="スクリプター向けドキュメントサイト生成")
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--content", default=os.path.join(HERE, "content"))
    ap.add_argument("--template", default=os.path.join(HERE, "template"))
    ap.add_argument("--out-dir", default=os.path.join(HERE, "dist"), help="複数ファイル出力の先(既定)")
    ap.add_argument("--single", metavar="FILE", help="1つのHTMLにまとめて出力する(配布用)。例: --single dist/all.html")
    ap.add_argument("--title", default="シナリオ辞典")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    print(f"[1/3] データ読み込み: {args.data_dir}")
    data = build_data(args)
    print(f"      Role {len(data['roles'])}件 / 型 {len(data['types'])}件 / ガイド {len(data['guides'])}件 / 用語 {len(data['glossary'])}件")
    if not data["meta"]["enumLoaded"]:
        print("      (enum / class_data_id が見つからないため、選べる値の一覧は定義に出てきたものだけを表示します)")

    print("[2/3] テンプレート読み込み")
    tpl = read_text(os.path.join(args.template, "index.html"))
    css = read_text(os.path.join(args.template, "style.css"))
    js = read_text(os.path.join(args.template, "app.js"))

    print("[3/3] 出力")
    if args.single:
        payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
        html = (tpl.replace("/*__CSS__*/", css).replace("/*__JS__*/", js)
                   .replace("__DATA__", payload).replace("__HOME__", "#/").replace("__TITLE__", args.title))
        os.makedirs(os.path.dirname(os.path.abspath(args.single)), exist_ok=True)
        with open(args.single, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"      1ファイル: {args.single} ({len(html)//1024} KB)")
    else:
        n = build_multi(args, data, tpl, css, js)
        print(f"      {n} ページ + assets/ -> {args.out_dir}")
    if WARNINGS:
        print(f"警告 {len(WARNINGS)}件")
        if args.strict:
            sys.exit(1)


if __name__ == "__main__":
    main()

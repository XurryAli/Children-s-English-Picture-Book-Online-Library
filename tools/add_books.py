#!/usr/bin/env python3
"""批量新增书目工具（工程常驻脚本，纯标准库实现，无第三方依赖）

从 JSON 清单读取新书目，校验后一次性完成两件事：
  1) 按 lv 把新条目插入 BOOKS 数据的对应分级区段末尾（不再一律追加到整份数据末尾）；
  2) 插入后整份数据按新顺序重新编号：每条数据的 i 重新等于其数组下标（0,1,2,...）；
  3) 复用 encrypt_books.py 的加解密实现，把合并后的 BOOKS 数据写回数据文件
     （工程内单独文件夹 data/books.js，由页面引用加载）。

页面侧无需同步改动：index.html 的 #grid 不再写死卡片，卡片与详情页均由页面运行时
按数据渲染（buildGrid / cardHTML / coverSVG）；某条数据的 c 为空时，页面在列表与详情页
统一显示分级色占位封面。因此本工具只维护数据文件，不再插入或改写任何静态卡片。

用法：
    python tools/add_books.py --input new_books.json             # 校验并写入
    python tools/add_books.py --input new_books.json --dry-run    # 只校验与预览，不写文件
    python tools/add_books.py --input new_books.json --file 页面.html --data data/books.js
    python tools/add_books.py --selftest                          # 校验数据编号、分级区段与页面渲染前提

清单格式（JSON 数组，每个对象一本书；也接受 {"books": [...]} 包裹）：
[
  {
    "lv": "桥梁书",                        # 必填，必须是页面 LEVELS 中的分级 key
    "zh": "苍蝇小子",                       # zh / en 至少填一个（同时用于卡片标题与可访问名）
    "en": "Fly Guy",
    "t": "1.Fly Guy 苍蝇小子 15本PDF+音频",   # 必填，原始目录名（去重键之一）
    "u": "https://pan.quark.cn/s/xxxx",     # 选填，网盘链接；含 https://pan 的条目计入“有效源”并分级高亮
    "c": "assets/covers/桥梁书_406.jpg",     # 选填，封面；填了就必须是 assets/covers/ 下已存在的文件，
                                           # 留空则页面用分级色占位封面显示（列表与详情页一致）
    "n": "15本",                           # 选填，册数；缺省卡片显示“册数见目录”
    "f": "PDF、MP3音频",                    # 选填，资源格式；缺省“见目录内资源”
    "d": "2026-11-04",                     # 选填，收录日期 YYYY-MM-DD；缺省当天
    "dir": "/【...】/1. Bridging Books/...",  # 选填，网盘路径
    "lx": "270–500L", "lxm": 410,          # 选填，蓝思值文本 / 中位数值；缺省“未收录”(lxm 为空)
    "db": ["Hi! Fly Guy", "Arnold, Tedd", "", "https://book.douban.com/subject/4532743/"]
  }                                        # db 选填，豆瓣匹配书目；缺省为 null
]

要点：
    - 落位规则：新条目插入其 lv 分级的区段末尾。例：新增一本“桥梁书”会插到现有桥梁书区段的最后一条
      （初章书区段之前），而不是整份数据的最后；同一批清单里的多条同分级条目按清单顺序依次追加。
    - 编号规则：写入前整份数据按新顺序重新编号，i 始终等于数组下标；清单里即便写了 i 也会被忽略。
    - 要求数据文件当前即满足 i == 数组下标（本工具的历次输出都满足）；若不满足会直接报错并提示修正。
    - 页面按 i 取书（BOOK_BY_ID），与数组下标一致，因此“插到中间”不影响列表筛选与详情弹窗。
    - 因插入后位置整体后移，其后既有书目的封面文件名不再等于 {lv}_{i+1}（封面文件不改名，各条目的
      c 字段始终指向实际文件）；新建封面时建议按 {lv}_{i+1}.jpg 命名，具体建议名见运行摘要。
    - 重复条目（t 或 u 与已有书目、或与同批清单中其他条目相同）会被跳过，因此同一份清单重复执行
      不会产生重复数据；清单条目全部被跳过时不会改动任何文件。
    - 写入前提：页面必须是“数据驱动”形态——#grid 内不含写死的 book-card 卡片，且页面按 i 取书
      （BOOK_BY_ID）、包含 buildGrid 渲染入口；否则会直接报错，避免数据与页面脱节。
    - 数据文件保持原有形态：原本是密文就写回密文，原本是明文就写回明文；页面两种形态都能读。
    - 写入流程：内存中生成并回读校验（数据逐条一致、i 与数组下标逐条对应且唯一）→ 原子替换落盘 →
      落盘后再回读校验；任一步不通过都不会写入文件。
"""
import argparse
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import encrypt_books as eb  # noqa: E402  复用加解密与原子写入实现

ROOT = eb.ROOT
DEFAULT_FILE = os.path.join(ROOT, "index.html")
DEFAULT_DATA = eb.DEFAULT_DATA

GRID_RE = re.compile(r'<section[^>]*id="grid"[^>]*>(.*?)</section>', re.S)
STATIC_CARD_RE = re.compile(r'<article[^>]*class="book-card"')
LEVELS_RE = re.compile(r"const LEVELS\s*=\s*\[(.*?)\n\s*\];", re.S)
LEVEL_RE = re.compile(r"key:'([^']+)'\s*,\s*en:'[^']*'\s*,\s*color:'([^']+)'")
LOOKUP_RE = re.compile(r"BOOK_BY_ID\s*\.\s*get\s*\(")
BUILDGRID_RE = re.compile(r"function\s+buildGrid\s*\(")

FIELDS = ["i", "lv", "lx", "lxm", "en", "zh", "t", "n", "f", "d", "dir", "u", "c", "db"]
REQUIRED = ["lv", "t"]
IMG_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".avif", ".svg")


def err(msg):
    raise SystemExit("[x] " + msg)


def read_text(path):
    if not os.path.isfile(path):
        err("目标文件不存在: %s" % path)
    with open(path, encoding="utf-8") as f:
        return f.read()


def parse_levels(text):
    """从页面 LEVELS 表解析分级 -> 颜色，保证清单校验与页面渲染始终一致。"""
    m = LEVELS_RE.search(text)
    if not m:
        err("未能从页面解析 LEVELS 分级表，请检查 const LEVELS = [ ... ]; 是否完整")
    pairs = LEVEL_RE.findall(m.group(1))
    if not pairs:
        err("LEVELS 分级表解析结果为空，请检查其格式（key/en/color）")
    return {k: {"key": k, "color": c} for k, c in pairs}


def check_page_lookup(text):
    """页面必须按 i 取书：新增条目并入中间分级后，其后书目的数组下标会整体后移。"""
    if LOOKUP_RE.search(text):
        return
    err("页面仍按下标取书（BOOKS[id]）：新增条目并入中间分级后，其后书目的数组下标会整体后移，"
        "列表筛选与详情弹窗会取成别的书。请把页面取数改为按 i 查找："
        "const BOOK_BY_ID = new Map(BOOKS.map(b=>[b.i,b]));")


def check_page_ready(text):
    """页面必须是数据驱动形态：#grid 内不得留有写死的 book-card 卡片，且具备 buildGrid 渲染入口。"""
    m = GRID_RE.search(text)
    if not m:
        err('未找到书架网格容器 <section ... id="grid"> ... </section>')
    if STATIC_CARD_RE.search(m.group(1)):
        err("页面 #grid 内仍存在写死的 book-card 卡片：页面已改为按数据渲染，静态卡片会与数据重复。"
            "请先移除 #grid 内的静态卡片（改由 buildGrid() 渲染），再执行新增")
    if not BUILDGRID_RE.search(text):
        err("页面未找到 function buildGrid(...)：无法按数据渲染书架，请先恢复数据驱动渲染")


def check_data_ids(data):
    """数据自身的编号基线：i 必须等于数组下标且唯一。"""
    ids = [b.get("i") for b in data]
    for k, i in enumerate(ids):
        if i != k:
            err("数据第 %d 条的 i=%r 与数组下标不符（本工具要求 i 等于数组下标）；"
                "请先在数据文件中修正编号，再执行新增" % (k + 1, i))
    dups = sorted({x for x in ids if ids.count(x) > 1}, key=lambda x: str(x))
    if dups:
        err("数据中存在重复的 i：%s（每本书的 i 必须唯一）" % dups)
    return data


def load_data(data_path):
    """从数据文件读取 BOOKS 数据，返回 (数据, 形态)。"""
    if not os.path.isfile(data_path):
        err("数据文件不存在: %s" % data_path)
    obj, mode = eb.parse_data_file(eb.read_text(data_path))
    return eb.books_of(obj, mode), mode


def lv_runs(data):
    """按数据顺序切出分级区段，返回 [(lv, 起始下标, 结束下标, 条数)]。"""
    runs = []
    for k, b in enumerate(data):
        lv = b.get("lv")
        if not runs or runs[-1][0] != lv:
            runs.append([lv, k, k, 1])
        else:
            runs[-1][2] = k
            runs[-1][3] += 1
    return [(lv, a, z, n) for lv, a, z, n in runs]


def format_runs(runs):
    return "｜".join("%s 第%d–%d条(%d)" % (lv, a + 1, z + 1, n) for lv, a, z, n in runs)


def grouping_note(runs):
    lvs = [lv for lv, *_ in runs]
    if len(lvs) == len(set(lvs)):
        return None
    return ("数据目前未按分级连续成段（%s）：新增条目将插入其分级最后一个区段的末尾；"
            "如需恢复成段，可先把同分级条目整理到一起" % "→".join(lvs))


def block_insert_index(data, lv):
    """新条目在数据中的插入下标：其 lv 分级最后一个区段的末尾（数据里没有该分级则追加到末尾）。"""
    at = [k for k, b in enumerate(data) if b.get("lv") == lv]
    return at[-1] + 1 if at else len(data)


def normalize_key(value):
    return re.sub(r"\s+", "", str(value or "")).lower().rstrip("/")


def validate(items, data, levels):
    """逐条校验清单，返回 (待写入条目, 被跳过的重复项, 警告列表)。"""
    seen_t = {normalize_key(b.get("t")): "数据第 %d 条" % (k + 1) for k, b in enumerate(data) if b.get("t")}
    seen_u = {normalize_key(b.get("u")): "数据第 %d 条" % (k + 1) for k, b in enumerate(data) if b.get("u")}
    accepted, skipped, warns = [], [], []
    today = datetime.date.today().isoformat()
    batch_t, batch_u = {}, {}

    for idx, it in enumerate(items):
        tag = "清单第 %d 条" % (idx + 1)
        if not isinstance(it, dict):
            err("%s 不是对象（JSON 里每本书应为一个 {}）" % tag)

        unknown = [k for k in it if k not in FIELDS]
        if unknown:
            err("%s 含有未知字段 %s；可用字段为 %s" % (tag, unknown, FIELDS))

        for f in REQUIRED:
            if not str(it.get(f) or "").strip():
                err("%s 缺少必填字段 %s" % (tag, f))

        lv = str(it["lv"]).strip()
        if lv not in levels:
            err("%s 的 lv=%r 不是页面 LEVELS 的取值，应为 %s" % (tag, lv, list(levels)))

        zh = str(it.get("zh") or "").strip()
        en = str(it.get("en") or "").strip()
        if not (zh or en):
            err("%s 的 zh 与 en 都为空，卡片将没有书名" % tag)

        cvr = str(it.get("c") or "").strip().replace("\\", "/")
        if cvr:
            if not cvr.startswith("assets/covers/"):
                err("%s 的 c=%r 必须指向 assets/covers/ 下的封面" % (tag, cvr))
            if not os.path.isfile(os.path.join(ROOT, cvr)):
                err("%s 的封面文件不存在：%s" % (tag, os.path.join(ROOT, cvr)))
            if not cvr.lower().endswith(IMG_EXT):
                warns.append("%s 的封面扩展名不常见：%s" % (tag, cvr))
        else:
            warns.append("%s 的 c 为空：页面将以分级色占位封面显示（列表与详情页一致）" % tag)

        u = str(it.get("u") or "").strip()
        if u and not re.match(r"^https?://", u):
            err("%s 的 u=%r 不是 http(s) 链接" % (tag, u))
        if u and "https://pan" not in u:
            warns.append("%s 的 u 不含 https://pan ，不计入“有效源”，卡片底部也不会高亮" % tag)
        if not u:
            warns.append("%s 未填 u（网盘链接），详情页“打开网盘目录”按钮将为空" % tag)

        lxm = it.get("lxm", None)
        if lxm is not None:
            try:
                lxm = int(lxm)
            except (TypeError, ValueError):
                err("%s 的 lxm=%r 不是整数" % (tag, it.get("lxm")))
        lx = str(it.get("lx") or "").strip()
        if lxm is None:
            if lx and lx != "未收录":
                err("%s 的 lx=%r 与 lxm=空 不一致（未收录时 lx 应为“未收录”或省略）" % (tag, lx))
            lx = "未收录"
        elif not lx:
            err("%s 填了 lxm=%d 就必须同时给出 lx 文本（如 “500L” 或 “300–480L”）" % (tag, lxm))

        d = str(it.get("d") or "").strip() or today
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", d):
            err("%s 的 d=%r 不是 YYYY-MM-DD 格式" % (tag, d))

        db = it.get("db", None)
        if db is not None:
            if not isinstance(db, list) or not 1 <= len(db) <= 4:
                err("%s 的 db 应为 1–4 个字符串的数组（书名 / 作者译者 / 其他 / 豆瓣链接）" % tag)
            db = [str(x) for x in (list(db) + ["", "", "", ""])[:4]]

        dir_ = str(it.get("dir") or "").strip()
        if not dir_:
            warns.append("%s 未填 dir（网盘路径），详情页“网盘路径”一行为空" % tag)

        t = str(it["t"]).strip()
        key_t, key_u = normalize_key(t), normalize_key(u)
        # 先判同批清单内部重复（提示更精确），再判与已有书目重复
        if key_t in batch_t:
            skipped.append("%s 与同批清单第 %s 条重复（t 相同），已跳过" % (tag, batch_t[key_t]))
            continue
        if key_u and key_u in batch_u:
            skipped.append("%s 与同批清单第 %s 条重复（u 相同），已跳过" % (tag, batch_u[key_u]))
            continue
        if key_t in seen_t:
            skipped.append("%s 与 %s 重复（t 相同），已跳过" % (tag, seen_t[key_t]))
            continue
        if key_u and key_u in seen_u:
            skipped.append("%s 与 %s 重复（u 相同），已跳过" % (tag, seen_u[key_u]))
            continue

        entry = {
            "i": None,          # 最终编号由 build_data() 在插入后统一重排为数组下标
            "lv": lv,
            "lx": lx,
            "lxm": lxm,
            "en": en,
            "zh": zh,
            "t": t,
            "n": str(it.get("n") or "").strip(),
            "f": str(it.get("f") or "").strip() or "见目录内资源",
            "d": d,
            "dir": dir_,
            "u": u,
            "c": cvr,
            "db": db,
        }
        accepted.append(entry)
        seen_t[key_t] = tag
        batch_t[key_t] = idx + 1
        if key_u:
            seen_u[key_u] = tag
            batch_u[key_u] = idx + 1

    return accepted, skipped, warns


# ---------------------------------------------------------------- 生成

def build_data(data, entries):
    """把新条目按 lv 并入数据并重排编号，返回 (合并后的数据, 各新增条目的数据下标)。"""
    check_data_ids(data)
    merged, slots = list(data), []
    for e in entries:
        at = block_insert_index(merged, e["lv"])
        merged.insert(at, e)
        slots.append(at)
    for k, b in enumerate(merged):            # 重排编号：插入后 i 恒等于数组下标
        b["i"] = k
    return merged, slots


def data_text_of(merged, mode):
    """按原形态生成数据文件内容：plain 保持明文，其余按密文写入。"""
    if mode == "plain":
        return eb.plain_text(merged)
    compact = json.dumps(merged, ensure_ascii=False, separators=(",", ":"))
    key = eb.secrets.token_urlsafe(24)
    ct = eb.rc4(key.encode("utf-8"), compact.encode("utf-8"))
    if eb.rc4(key.encode("utf-8"), ct).decode("utf-8") != compact:
        err("RC4 自检失败")
    return eb.cipher_text(key, eb.base64.b64encode(ct).decode("ascii"))


def stats_of(data):
    empty = sum(1 for b in data if not b.get("c"))
    pan = sum(1 for b in data if "https://pan" in str(b.get("u") or ""))
    return {"count": len(data), "empty_cover": empty, "pan": pan}


def verify(data_text, merged, mode, levels, phase):
    """回读校验：数据逐条一致、形态不变、编号自洽、分级合法。"""
    obj, got_mode = eb.parse_data_file(data_text)
    if eb.books_of(obj, got_mode) != merged:
        err("%s校验失败：BOOKS 数据与预期不一致，未写入文件" % phase)
    if got_mode != mode:
        err("%s校验失败：数据文件形态不正确（%s），未写入文件" % (phase, got_mode))
    ids = [b.get("i") for b in merged]
    if ids != list(range(len(merged))):
        err("%s校验失败：数据 i 与数组下标不一致，未写入文件" % phase)
    for b in merged:
        if b.get("lv") not in levels:
            err("%s校验失败：存在非法分级 %r" % (phase, b.get("lv")))
    return stats_of(merged)


# ---------------------------------------------------------------- 子命令

def cmd_selftest(path, data_path):
    text = read_text(path)
    levels = parse_levels(text)
    check_page_lookup(text)
    check_page_ready(text)
    data, mode = load_data(data_path)
    check_data_ids(data)

    merged, slots = build_data(data, [])
    if merged != data or slots:
        err("零新增重建校验失败：并入空清单后数据发生变化")

    runs = lv_runs(data)
    note = grouping_note(runs)
    st = stats_of(data)
    missing_u = sum(1 for b in data if not b.get("u"))

    print("[selftest] 页面 %s（数据驱动渲染：无写死卡片、按 i 取书），数据 %s（%s）"
          % (os.path.basename(path), os.path.basename(data_path), mode))
    print("[selftest] 数据 %d 条，i 与数组下标逐条对应且唯一；分级表 %s" % (len(data), list(levels)))
    print("[selftest] 分级区段：%s" % format_runs(runs))
    print("[selftest] 封面：真实封面 %d，空 c（页面占位封面）%d；有效源（u 含 https://pan）%d，u 为空 %d"
          % (st["count"] - st["empty_cover"], st["empty_cover"], st["pan"], missing_u))
    if note:
        print("[selftest] 提示：%s" % note)
    print("[selftest] 通过：数据编号自洽、页面为数据驱动渲染、零新增可无损重建")
    return 0


def describe_ids(entries):
    ids = [e["i"] for e in entries]
    if len(ids) == 1:
        return str(ids[0])
    if ids == list(range(ids[0], ids[0] + len(ids))):
        return "%d–%d" % (ids[0], ids[-1])
    return "、".join(str(x) for x in ids)


def entry_preview(e):
    return json.dumps({k: e[k] for k in FIELDS}, ensure_ascii=False)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="批量新增书目（按 lv 归入对应分级，只写数据文件 data/books.js；页面按数据渲染）")
    ap.add_argument("--input", help="新书目 JSON 清单")
    ap.add_argument("--file", default=DEFAULT_FILE,
                    help="页面 HTML（用于读取 LEVELS 与校验渲染前提），默认工程根目录 index.html")
    ap.add_argument("--data", default=DEFAULT_DATA, help="数据文件，默认工程根目录 data/books.js")
    ap.add_argument("--dry-run", action="store_true", help="只校验并预览，不写入文件")
    ap.add_argument("--selftest", action="store_true", help="校验数据编号、分级区段与页面渲染前提")
    args = ap.parse_args(argv)

    path = os.path.abspath(args.file)
    data_path = os.path.abspath(args.data)
    if args.selftest:
        return cmd_selftest(path, data_path)
    if not args.input:
        err("缺少 --input（新书目 JSON 清单）")

    with open(args.input, encoding="utf-8") as f:
        try:
            raw = json.load(f)
        except json.JSONDecodeError as e:
            err("清单不是合法 JSON：%s" % e)
    items = raw.get("books") if isinstance(raw, dict) else raw
    if not isinstance(items, list) or not items:
        err("清单应为非空数组，或形如 {\"books\": [...]}")

    text = read_text(path)
    levels = parse_levels(text)
    check_page_lookup(text)
    check_page_ready(text)
    data, mode = load_data(data_path)
    check_data_ids(data)
    note = grouping_note(lv_runs(data))
    if note:
        print("[!] " + note)

    entries, skipped, warns = validate(items, data, levels)
    for w in warns:
        print("[!] " + w)
    for s in skipped:
        print("[-] " + s)
    if not entries:
        print("[i] 无新增条目（清单中 %d 条全部为重复项），文件未做改动" % len(items))
        return 0

    merged, slots = build_data(data, entries)
    for e, at in zip(entries, slots):
        e["i"] = merged[at]["i"]      # 插入重排后的最终编号（= 数组下标）
    new_data_text = data_text_of(merged, mode)
    st = verify(new_data_text, merged, mode, levels, "写入前")

    have_lv = {b.get("lv") for b in data}
    print("[+] 新增 %d 条：i %s，总条目 %d -> %d" % (len(entries), describe_ids(entries), len(data), len(merged)))
    for e, at in zip(entries, slots):
        where = "数据第 %d 条（%s 区段末尾）" % (at + 1, e["lv"]) \
            if e["lv"] in have_lv else "数据第 %d 条（原无该分级，追加到末尾）" % (at + 1)
        cover = e["c"] if e["c"] else "空 → 页面显示分级色占位封面"
        pan = "计入有效源" if "https://pan" in e["u"] else "不计入有效源"
        print("[+] i=%-4d %s 归入 %s；封面 %s；%s" % (e["i"], e["lv"], where, cover, pan))
    print("[i] 入库后分级区段：%s" % format_runs(lv_runs(merged)))
    print("[i] 入库后封面统计：真实封面 %d，空 c（占位封面）%d；有效源 %d"
          % (st["count"] - st["empty_cover"], st["empty_cover"], st["pan"]))
    diff = []
    for e in entries:
        if not e["c"]:
            continue
        sug = "assets/covers/%s_%d%s" % (e["lv"], e["i"] + 1, os.path.splitext(e["c"])[1] or ".jpg")
        if sug != e["c"]:
            diff.append((e["i"], sug, e["c"]))
    if diff:
        print("[i] 封面命名不一致（现有封面沿用 {lv}_{i+1}.jpg）：%s"
              % "；".join("i=%d 建议 %s，清单为 %s" % d for d in diff))

    if args.dry_run:
        print("[i] --dry-run：以上落位与编号均已校验通过，未写入文件；新增条目预览：")
        for e in entries:
            print("    " + entry_preview(e))
        return 0

    eb.write_atomic(data_path, new_data_text)
    verify(eb.read_text(data_path), merged, mode, levels, "落盘后")
    print("[ok] 已写入 %s（%d 条，%s）；页面无需改动（#grid 由数据渲染）"
          % (os.path.relpath(data_path, ROOT).replace(os.sep, "/"), len(merged), mode))
    return 0


if __name__ == "__main__":
    sys.exit(main())
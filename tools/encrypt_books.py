#!/usr/bin/env python3
"""BOOKS 数据加解密工具（工程常驻脚本，纯标准库实现，无第三方依赖）

数据存放位置：工程内单独文件夹 data/books.js，由 index.html 通过
    <script src="data/books.js"></script>
引用加载；页面运行时用同款内联 decryptBooks() 解密读取。

数据文件两种形态（同一个文件在两种状态间切换，均可安全重复执行）：
    密文形态：window.BOOKS_DATA = {"key":"...","cipher":"..."};
    明文形态：window.BOOKS_DATA = {"key":null,"books":[ ... ]};   （便于编辑）

用法：
    python tools/encrypt_books.py                    # 加密：把 data/books.js 中的 BOOKS 数据加密存储
    python tools/encrypt_books.py decrypt            # 解密：把 BOOKS 数据还原为明文数组（便于编辑）
    python tools/encrypt_books.py --data data/books.js   # 指定数据文件，默认工程根目录 data/books.js
    python tools/encrypt_books.py --expect 405       # 附加校验书籍条目数（0 表示不校验）

日常维护流程：
    1) python tools/encrypt_books.py decrypt   # 把 BOOKS 还原成明文数组（写入 data/books.js）
    2) 编辑 data/books.js 中的 books 数组（新增 / 修改书目、封面、网盘链接等）
    3) python tools/encrypt_books.py           # 重新加密，每次生成新的随机密钥

实现说明：
    - 数据流：JSON 数组 -> 紧凑 JSON -> RC4（密钥 secrets.token_urlsafe(24)）-> base64，
      写入 data/books.js 的 BOOKS_DATA.cipher；页面内联同款 decryptBooks() 运行时代码。
    - 数据文件已是密文时，加密前会先从密文解密读回数据，因此两种状态都能安全重复执行。
    - 脚本就地重写数据文件（先写临时文件再原子替换），写入前后都会回读解密并与原数据逐条比对，
      校验不通过则不会写入，避免留下半成品。
"""
import argparse
import base64
import json
import os
import secrets
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
DEFAULT_DATA = os.path.join(DATA_DIR, "books.js")

ASSIGN = "window.BOOKS_DATA = "
HEADER_CIPHER = "/* 加密书目数据 · 由 tools/encrypt_books.py 自动生成，请勿手工编辑 */\n"
HEADER_PLAIN = "/* 书目数据明文（编辑用）· 改完请运行 python tools/encrypt_books.py 重新加密 */\n"


def rc4(key_bytes, data_bytes):
    """RC4 流密码，与页面内 decryptBooks() 的算法完全一致。"""
    S = list(range(256))
    j = 0
    for i in range(256):
        j = (j + S[i] + key_bytes[i % len(key_bytes)]) & 255
        S[i], S[j] = S[j], S[i]
    out = bytearray(len(data_bytes))
    i = j = 0
    for n, b in enumerate(data_bytes):
        i = (i + 1) & 255
        j = (j + S[i]) & 255
        S[i], S[j] = S[j], S[i]
        out[n] = b ^ S[(S[i] + S[j]) & 255]
    return bytes(out)


def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def parse_data_file(text):
    """解析数据文件，返回 (对象, 形态)，形态为 cipher / plain。"""
    if ASSIGN not in text:
        raise SystemExit("[x] 数据文件缺少 %r 赋值，已损坏：请用版本管理或备份恢复" % ASSIGN.strip())
    i = text.index(ASSIGN) + len(ASSIGN)
    try:
        obj, _ = json.JSONDecoder().raw_decode(text, i)
    except ValueError:
        raise SystemExit("[x] 数据文件中的 BOOKS_DATA 不是合法 JSON，请用版本管理或备份恢复")
    if not isinstance(obj, dict):
        raise SystemExit("[x] 数据文件中的 BOOKS_DATA 不是对象")
    mode = "cipher" if obj.get("cipher") else "plain"
    return obj, mode


def books_of(obj, mode):
    """从数据对象取出 BOOKS 数组（密文形态先解密）。"""
    if mode == "cipher":
        key = obj.get("key") or ""
        if not key:
            raise SystemExit("[x] 密文形态缺少 BOOKS_DATA.key")
        plain = rc4(key.encode("utf-8"), base64.b64decode(obj["cipher"])).decode("utf-8")
        return json.loads(plain)
    books = obj.get("books")
    if books is None:
        raise SystemExit("[x] 明文形态缺少 BOOKS_DATA.books")
    return books


def cipher_text(key, b64):
    """生成密文形态的数据文件内容。"""
    obj = {"key": key, "cipher": b64}
    return HEADER_CIPHER + ASSIGN + json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + ";\n"


def plain_text(books):
    """生成明文形态的数据文件内容。"""
    obj = {"key": None, "books": books}
    return HEADER_PLAIN + ASSIGN + json.dumps(obj, ensure_ascii=False, indent=4) + ";\n"


def write_atomic(path, text):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".enc-tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    os.replace(tmp, path)


def main(argv=None):
    ap = argparse.ArgumentParser(description="BOOKS 数据加解密工具（数据文件 data/books.js）")
    ap.add_argument("mode", nargs="?", default="encrypt", choices=["encrypt", "decrypt"],
                    help="encrypt=加密存储（默认），decrypt=还原明文数组")
    ap.add_argument("--data", "--file", dest="data", default=DEFAULT_DATA,
                    help="数据文件，默认工程根目录 data/books.js")
    ap.add_argument("--expect", type=int, default=0, help="校验书籍条目数，0 表示不校验")
    args = ap.parse_args(argv)

    path = os.path.abspath(args.data)
    if not os.path.isfile(path):
        raise SystemExit("[x] 数据文件不存在: %s" % path)

    text = read_text(path)
    obj, mode = parse_data_file(text)
    data = books_of(obj, mode)
    if not isinstance(data, list) or not data:
        raise SystemExit("[x] BOOKS 数据解析结果不是非空数组")
    if args.expect and len(data) != args.expect:
        raise SystemExit("[x] 条目数不符：期望 %d，实际 %d" % (args.expect, len(data)))

    if args.mode == "decrypt":
        out = plain_text(data)
        want = "plain"
    else:
        compact = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        key = secrets.token_urlsafe(24)
        ct = rc4(key.encode("utf-8"), compact.encode("utf-8"))
        if rc4(key.encode("utf-8"), ct).decode("utf-8") != compact:
            raise SystemExit("[x] RC4 自检失败")
        out = cipher_text(key, base64.b64encode(ct).decode("ascii"))
        want = "cipher"

    # 写入前先在内存中回读校验，避免留下半成品文件
    obj_v, mode_v = parse_data_file(out)
    if books_of(obj_v, mode_v) != data:
        raise SystemExit("[x] 校验失败：%s 结果与原始数据不一致，未写入文件" % args.mode)
    if mode_v != want:
        raise SystemExit("[x] 校验失败：写入后形态不正确（%s），未写入文件" % mode_v)

    write_atomic(path, out)

    # 落盘后再次回读校验
    saved = read_text(path)
    obj_s, mode_s = parse_data_file(saved)
    if books_of(obj_s, mode_s) != data or mode_s != want:
        raise SystemExit("[x] 落盘校验失败：请用版本管理或备份恢复 %s" % path)

    print("[ok] %s %s entries=%d file %d -> %d bytes" % (
        args.mode, os.path.relpath(path, ROOT).replace(os.sep, "/"), len(data),
        len(text), len(saved)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
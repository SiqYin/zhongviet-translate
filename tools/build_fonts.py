#!/usr/bin/env python3
"""依本詞典實際用字，把兩款字體子集化成 app/fonts/*.woff2。

霞鶩文楷：簡繁漢字、越南語、拉丁、注音、常用符號
Nom Na Tong：字喃（只放字喃字形，字喃一律用它，不與霞鶩文楷混排）

用法：
    python tools/build_fonts.py \
        --wenkai "/path/to/LXGWWenKai-Regular.ttf" \
        --nom "/path/to/NomNaTong-Regular.ttf"

兩個字體都以 woff2 輸出，並把授權檔一併放在 app/fonts/。
"""
import argparse
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
APP = ROOT / "app"
OUT = APP / "fonts"

VI_LOWER = ("àáảãạăằắẳẵặâầấẩẫậđèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵ")
VI_UPPER = VI_LOWER.upper()
BOPOMOFO = "ㄅㄆㄇㄈㄉㄊㄋㄌㄍㄎㄏㄐㄑㄒㄓㄔㄕㄖㄗㄘㄙㄚㄛㄜㄝㄞㄟㄠㄡㄢㄣㄤㄥㄦㄧㄨㄩˊˇˋ˙"
SYMBOLS = "·×→↔⿰⿱⿲⿳⿴⿵⿶⿷⿸⿹⿺⿻（）「」《》〈〉、。，；：？！…—–＂＇"


def load_json_var(path):
    txt = path.read_text(encoding="utf-8")
    body = txt[txt.index("=") + 1:]
    body = body.rstrip().rstrip(";")
    return json.loads(body[body.index("["):body.rindex("]") + 1])


def wenkai_charset():
    chars = set()
    for row in load_json_var(APP / "zhvi.js"):
        for field in (row[0], row[1], row[3]):      # 繁體、簡體、越南語義項
            chars.update(field)
        for field in (row[2], row[4]):              # 拼音、漢越音（拉丁）
            chars.update(field)
    for f in ("index.html", "app.js", "translate.js", "style.css"):
        chars.update((APP / f).read_text(encoding="utf-8"))
    chars.update(chr(c) for c in range(0x20, 0x7F))
    chars.update(VI_LOWER + VI_UPPER + BOPOMOFO + SYMBOLS)
    return {c for c in chars if ord(c) >= 0x20}


def nom_charset():
    chars = set()
    for vi, nom in load_json_var(APP / "nom.js"):
        chars.update(c for c in nom if ord(c) > 0x3000)
    for row in load_json_var(APP / "zhvi.js"):
        if len(row) > 5 and row[5]:
            chars.update(c for c in row[5] if ord(c) > 0x3000)
    return chars


def subset(src, chars, dest):
    text = "".join(sorted(chars))
    tmp = ROOT / "data" / "_font_charset.txt"
    tmp.parent.mkdir(exist_ok=True)
    tmp.write_text(text, encoding="utf-8")
    cmd = [sys.executable, "-m", "fontTools.subset", str(src),
           f"--text-file={tmp}", "--flavor=woff2", "--no-hinting",
           f"--output-file={dest}"]
    subprocess.run(cmd, check=True)
    tmp.unlink()
    size = dest.stat().st_size
    print(f"  {dest.name}: {len(chars)} 字形 -> {size/1024/1024:.2f} MB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wenkai", required=True, help="LXGWWenKai-Regular.ttf 路徑")
    ap.add_argument("--nom", required=True, help="NomNaTong-Regular.ttf 路徑")
    ap.add_argument("--license-wenkai", default="", help="OFL.txt 路徑")
    ap.add_argument("--license-nom", default="", help="NomNaTong LICENSE 路徑")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    print("霞鶩文楷：")
    subset(args.wenkai, wenkai_charset(), OUT / "wenkai.woff2")
    print("Nom Na Tong：")
    subset(args.nom, nom_charset(), OUT / "nom.woff2")

    for src, name in ((args.license_wenkai, "OFL-LXGWWenKai.txt"),
                      (args.license_nom, "LICENSE-NomNaTong.txt")):
        if src and pathlib.Path(src).exists():
            (OUT / name).write_bytes(pathlib.Path(src).read_bytes())
            print(f"  授權 {name}")


if __name__ == "__main__":
    main()

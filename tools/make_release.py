# -*- coding: utf-8 -*-
"""创建 GitHub Release 并上传 exe/apk。

    python tools/make_release.py
"""
import json
import pathlib
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
ARCH = ROOT.parent.parent
TOKEN_FILE = pathlib.Path(r"C:\Users\29736\AppData\Local\Temp\gh_token_ok.txt")
OWNER, REPO = "SiqYin", "zhongviet-translate"
TAG = "v1.5.7"
API = "https://api.github.com/repos/%s/%s" % (OWNER, REPO)

TOKEN = TOKEN_FILE.read_text(encoding="utf-8").strip()
H = {"Authorization": "Bearer " + TOKEN, "User-Agent": "curl/8", "Accept": "application/vnd.github+json"}


def api(url, data=None, method=None):
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=dict(H, **{"Content-Type": "application/json"}), method=method)
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def upload(rel_id, path, name):
    url = "https://uploads.github.com/repos/%s/%s/releases/%d/assets?name=%s" % (OWNER, REPO, rel_id, name)
    data = pathlib.Path(path).read_bytes()
    h = {"Authorization": "Bearer " + TOKEN, "User-Agent": "curl/8",
         "Content-Type": "application/octet-stream", "Content-Length": str(len(data))}
    req = urllib.request.Request(url, data=data, headers=h, method="POST")
    with urllib.request.urlopen(req, timeout=3600) as r:
        return json.load(r)


def main():
    # 1. APK：从 Actions 产物下载（urllib 跨域会带 Authorization 导致 401，改用 curl）
    apk = ROOT / "release-out" / "zhongviet-translate.apk"
    if not apk.exists():
        import subprocess
        zpath = ROOT / "release-out" / "apk_artifact.zip"
        subprocess.run(["curl", "-sL", "-H", "Authorization: Bearer " + TOKEN,
                        "-o", str(zpath),
                        API + "/actions/artifacts/13683603647/zip"], check=True)
        import zipfile
        z = zipfile.ZipFile(zpath)
        for n in z.namelist():
            if n.lower().endswith(".apk"):
                apk.write_bytes(z.read(n))
        print("apk", apk.stat().st_size)

    # 2. 建 Release
    body = (ROOT / "release_notes_v1.5.7.md").read_text(encoding="utf-8")
    try:
        rel = api(API + "/releases/tags/" + TAG)
        print("release exists", rel["id"], rel["html_url"])
    except Exception:
        rel = api(API + "/releases", {"tag_name": TAG, "name": "漢南辭典 v1.5.7",
                                      "body": body, "draft": False, "prerelease": False}, method="POST")
        print("release created", rel["id"], rel["html_url"])

    # 3. 上传资产
    have = {a["name"] for a in rel.get("assets", [])}
    exe = ROOT / "release-out" / "HanVietDict-setup.exe"
    for path, name in ((exe, "HanVietDict-setup.exe"), (apk, "zhongviet-translate.apk")):
        if name in have:
            print("skip existing", name)
            continue
        print("uploading", name, "%.1f MB" % (path.stat().st_size / 1048576), flush=True)
        a = upload(rel["id"], path, name)
        print("  uploaded", a["name"], a["size"], flush=True)

    rel = api(API + "/releases/tags/" + TAG)
    print("final assets:", [(a["name"], a["size"]) for a in rel.get("assets", [])])
    print("url", rel["html_url"])


if __name__ == "__main__":
    main()

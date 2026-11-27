#!/usr/bin/env python3
"""Publish index.html + archive.json to GitHub Pages via the Contents API.

Reads GH_TOKEN from the environment (never prints it), skips unchanged files,
then waits for the public page to serve the current meta.generated value.
"""
import base64
import json
import os
import pathlib
import time
import urllib.error
import urllib.request

OWNER = os.environ.get("GH_OWNER", "hkings2010")
REPO = os.environ.get("GH_REPO", "one-person-daily")
BRANCH = os.environ.get("GH_BRANCH", "main")
SITE = f"https://{OWNER}.github.io/{REPO}/"
FILES = ["archive.json", "index.html"]
ROOT = pathlib.Path(__file__).resolve().parent


def api(path, method="GET", data=None):
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        raise SystemExit("GH_TOKEN is missing")
    req = urllib.request.Request(
        "https://api.github.com" + path,
        method=method,
        data=json.dumps(data).encode() if data is not None else None,
    )
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "qoder-opc-deploy")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode()
            return resp.status, json.loads(body) if body else None
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        try:
            parsed = json.loads(body)
        except Exception:  # noqa: BLE001
            parsed = body
        return exc.code, parsed


def remote_file(path):
    status, data = api(f"/repos/{OWNER}/{REPO}/contents/{path}?ref={BRANCH}")
    if status == 404:
        return None, None
    if status != 200 or not isinstance(data, dict):
        raise SystemExit(f"cannot read {path}: HTTP {status} {data}")
    content = base64.b64decode(data.get("content", "")).decode("utf-8")
    return data.get("sha"), content


def main() -> None:
    archive = json.loads((ROOT / "archive.json").read_text(encoding="utf-8"))
    marker = str((archive.get("meta") or {}).get("generated") or "")
    if not marker:
        raise SystemExit("archive.json meta.generated is missing")

    for name in FILES:
        local = (ROOT / name).read_bytes()
        sha, remote = remote_file(name)
        if remote is not None and remote.encode("utf-8") == local:
            print(f"skip {name} (unchanged)")
            continue
        payload = {
            "message": f"Update daily digest {marker} ({name})",
            "content": base64.b64encode(local).decode(),
            "branch": BRANCH,
        }
        if sha:
            payload["sha"] = sha
        status, data = api(f"/repos/{OWNER}/{REPO}/contents/{name}", "PUT", payload)
        if status not in (200, 201):
            raise SystemExit(f"upload {name} failed: HTTP {status} {data}")
        print(f"uploaded {name}")

    # GitHub Pages usually rebuilds in ~30-90s. Verify the new marker is live.
    for attempt in range(24):
        try:
            req = urllib.request.Request(
                SITE + "?v=" + str(int(time.time())),
                headers={"User-Agent": "Mozilla/5.0", "Cache-Control": "no-cache"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8", "replace")
            if marker in body:
                print(f"live: {SITE}")
                return
            print(f"waiting for Pages ({attempt + 1}/24)")
        except Exception as exc:  # noqa: BLE001
            print(f"waiting for Pages ({attempt + 1}/24): {type(exc).__name__}")
        time.sleep(10)
    raise SystemExit("page uploaded but the new marker did not appear in time")


if __name__ == "__main__":
    main()
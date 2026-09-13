# -*- coding: utf-8 -*-
"""VAL//AIM auto-updater (stdlib only, no git needed).

Play-Aim-Trainer.bat runs this before every launch:
  1. reads local VERSION
  2. fetches VERSION from GitHub (raw) — if it differs, downloads the branch zip
     and overlays every file EXCEPT data/ (your training history) and .git/
  3. the launcher .bat is never overwritten while it is running — a new one is
     written as Play-Aim-Trainer.bat.new and swapped in by the .bat itself

Exit codes: 0 = nothing to do / offline / skipped, 3 = updated (the .bat re-launches itself)

If a .git folder exists next to it (you cloned with git) it runs `git pull --ff-only`
instead and returns 3 when HEAD moved. With no VERSION file (the developer's working
copy) it does nothing.

Note: the zip overlay never deletes files, so a module removed upstream stays on disk
(harmless - nothing imports it). A fresh clone/zip is always clean.
"""
import io
import os
import sys
import shutil
import subprocess
import zipfile
import urllib.request

REPO = "intelisgod/val-aim"
BRANCH = "main"
RAW_BASE = os.environ.get("VALAIM_RAW_BASE") or f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/"
ZIP_URL = os.environ.get("VALAIM_ZIP_URL") or f"https://codeload.github.com/{REPO}/zip/refs/heads/{BRANCH}"

HERE = os.path.dirname(os.path.abspath(__file__))
VERSION_FILE = os.path.join(HERE, "VERSION")
LAUNCHER = "Play-Aim-Trainer.bat"
NEVER_TOUCH = ("data", ".git", "__pycache__")   # top-level names that are never written

def _say(msg):
    try:
        print(f"[update] {msg}")
    except Exception:
        pass

def _fetch(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": "VAL-AIM-updater", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

def _read_version():
    try:
        with open(VERSION_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""

def _same_file(path, blob):
    try:
        with open(path, "rb") as f:
            return f.read() == blob
    except OSError:
        return False

def apply_zip(zip_bytes):
    """Overlay the zip's files onto HERE. Returns number of files written."""
    written = 0
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            parts = info.filename.split("/")[1:]          # drop "val-aim-main/"
            if not parts or not parts[0]:
                continue
            if parts[0] in NEVER_TOUCH:
                continue
            rel = os.path.join(*parts)
            dest = os.path.join(HERE, rel)
            blob = z.read(info)
            if rel == LAUNCHER:
                # cmd.exe reads a running .bat by byte offset — overwriting it mid-run
                # corrupts the launch. Stage as .new; the .bat swaps it in on start.
                if _same_file(dest, blob):
                    continue
                dest = dest + ".new"
            elif _same_file(dest, blob):
                continue
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            tmp = dest + ".tmp"
            with open(tmp, "wb") as f:
                f.write(blob)
            os.replace(tmp, dest)
            written += 1
    return written

def _git(*args):
    r = subprocess.run(["git", "-C", HERE, *args], capture_output=True, text=True, timeout=90)
    return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()

def git_update():
    """git clone: pull fast-forward only (never overwrites local edits). 3 if HEAD moved."""
    if shutil.which("git") is None:
        _say("git clone but git.exe not found - install git or download the ZIP instead")
        return 0
    _, old, _ = _git("rev-parse", "HEAD")
    try:
        rc, _, err = _git("pull", "--ff-only", "--quiet")
    except subprocess.TimeoutExpired:
        _say("git pull timed out - playing the current version")
        return 0
    if rc != 0:
        _say("git pull skipped (offline, or local changes) - playing the current version")
        return 0
    _, new, _ = _git("rev-parse", "HEAD")
    if old and new and old != new:
        _say(f"updated {old[:7]} -> {new[:7]}")
        return 3
    _say(f"up to date ({new[:7]})")
    return 0

def main():
    if os.path.isdir(os.path.join(HERE, ".git")):
        return git_update()
    local = _read_version()
    if not local:
        _say("no VERSION file - developer copy, skipping")
        return 0
    try:
        remote = _fetch(RAW_BASE + "VERSION", timeout=6).decode("utf-8").strip()
    except Exception as e:
        _say(f"cannot reach GitHub ({type(e).__name__}) - playing the current version")
        return 0
    if not remote or remote == local:
        _say(f"up to date ({local})")
        return 0
    _say(f"new version {remote} (you have {local}) - downloading...")
    try:
        blob = _fetch(ZIP_URL, timeout=60)
    except Exception as e:
        _say(f"download failed ({type(e).__name__}) - playing the current version")
        return 0
    try:
        n = apply_zip(blob)
    except Exception as e:
        _say(f"update failed while writing files ({e}) - playing the current version")
        return 0
    with open(VERSION_FILE + ".tmp", "w", encoding="utf-8") as f:
        f.write(remote + "\n")
    os.replace(VERSION_FILE + ".tmp", VERSION_FILE)
    _say(f"updated to {remote} ({n} files)")
    return 3

if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:   # never block the game because of the updater
        _say(f"unexpected error: {e}")
        sys.exit(0)

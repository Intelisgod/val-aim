# -*- coding: utf-8 -*-
"""VAL//AIM auto-updater + rollback (stdlib only, no git needed).

Play-Aim-Trainer.bat runs `update.py` before every launch and `update.py --crashed`
when the game exits with an error.

Update sources (only builds that passed the GitHub Actions selftest reach `release`):
  git clone  -> fetch origin/release, fast-forward only (never overwrites local edits)
  zip copy   -> compare VERSION with raw.githubusercontent .../release/VERSION,
                download the release zip, overlay everything except data/ .prev/ .git/,
                then delete files under src/ assets/ .github/ that are not in MANIFEST
  no VERSION -> developer's working copy, do nothing

Safety:
  * the running .bat is never overwritten - a changed launcher is staged as
    Play-Aim-Trainer.bat.new and swapped in by the .bat itself on the next start
  * every file the update replaces/deletes is first copied to .prev/ ; if the game
    crashes within ROLLBACK_WINDOW of an update, --crashed offers to restore .prev/
    and writes .hold so that broken version is not installed again
  * after an update the CHANGELOG section for the new version is shown (What's new)
  * any error -> exit 0 and the game launches with what is on disk

Exit codes: 0 nothing to do / skipped, 3 updated (launcher restarts itself)
"""
import io
import os
import re
import sys
import time
import shutil
import subprocess
import zipfile
import urllib.request

for _s in (sys.stdout, sys.stderr):          # never die on a non-UTF-8 console because of Thai text
    try:
        _s.reconfigure(errors="replace")
    except Exception:
        pass

REPO = "Intelisgod/val-aim"                # owner is case-sensitive: wrong case = an extra redirect per request
BRANCH = "release"                     # promoted by .github/workflows/test-and-release.yml
RAW_BASE = os.environ.get("VALAIM_RAW_BASE") or f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/"
ZIP_URL = os.environ.get("VALAIM_ZIP_URL") or f"https://codeload.github.com/{REPO}/zip/refs/heads/{BRANCH}"

HERE = os.path.dirname(os.path.abspath(__file__))
VERSION_FILE = os.path.join(HERE, "VERSION")
HOLD_FILE = os.path.join(HERE, ".hold")          # version that crashed and was rolled back
PREV_DIR = os.path.join(HERE, ".prev")           # backup of the files the last update touched
LAUNCHER = "Play-Aim-Trainer.bat"
NEVER_TOUCH = ("data", ".git", ".prev", "__pycache__")   # top-level names the overlay never writes
MANAGED_DIRS = ("src", "assets", ".github")       # stale files here are removed per MANIFEST
ROLLBACK_WINDOW = 15 * 60                         # seconds after an update in which a crash offers rollback

# ---------------------------------------------------------------- helpers
def _say(msg):
    try:
        print(f"[update] {msg}")
    except Exception:
        pass

def _fetch(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": "VAL-AIM-updater", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

def _read(path, default=""):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return default

def _write(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text.rstrip("\n") + "\n")
    os.replace(tmp, path)

def _same_file(path, blob):
    try:
        with open(path, "rb") as f:
            return f.read() == blob
    except OSError:
        return False

def _msgbox(title, text, flags=0x40040):
    """Windows MessageBoxW (OK|INFO|TOPMOST by default). Returns the button id, 0 elsewhere."""
    if os.name == "nt":
        try:
            import ctypes
            return ctypes.windll.user32.MessageBoxW(None, text, title, flags)
        except Exception:
            pass
    print(f"--- {title} ---\n{text}\n")
    return 0

def changelog_section(version):
    """Bullets under `## <version>` in CHANGELOG.md (max ~12 lines), or ''."""
    text = _read(os.path.join(HERE, "CHANGELOG.md"))
    if not text:
        return ""
    m = re.search(rf"^## +v?{re.escape(version)}\b[^\n]*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not m:
        return ""
    lines = [l.rstrip() for l in m.group(1).strip().splitlines() if l.strip()]
    if len(lines) > 12:
        lines = lines[:12] + ["..."]
    return "\n".join(lines)

def whats_new(new_version):
    body = changelog_section(new_version)
    _msgbox(f"VAL//AIM updated to v{new_version}", body or "Update installed.")

# ---------------------------------------------------------------- backups / rollback
def _prev_reset():
    shutil.rmtree(PREV_DIR, ignore_errors=True)
    os.makedirs(PREV_DIR, exist_ok=True)

def _prev_backup(rel):
    """Copy HERE/rel into .prev/rel (if it exists)."""
    src = os.path.join(HERE, rel)
    if not os.path.isfile(src):
        return
    dst = os.path.join(PREV_DIR, "files", rel)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)

def _prev_stamp(old_version, new_version, git_prev=""):
    _write(os.path.join(PREV_DIR, "old_version"), old_version)
    _write(os.path.join(PREV_DIR, "applied_version"), new_version)
    _write(os.path.join(PREV_DIR, "applied_at"), str(int(time.time())))
    if git_prev:
        _write(os.path.join(PREV_DIR, "git_prev"), git_prev)

def _put_file(rel, blob):
    """Write a file into HERE, staging the launcher as .new. Returns True if written."""
    dest = os.path.join(HERE, rel)
    if _same_file(dest, blob):
        return False
    if rel == LAUNCHER:
        # cmd.exe reads a running .bat by byte offset - never overwrite it mid-run
        dest = dest + ".new"
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".tmp"
    with open(tmp, "wb") as f:
        f.write(blob)
    os.replace(tmp, dest)
    return True

def crashed():
    """Called by the launcher when the game exits non-zero. Offer rollback if we just updated."""
    applied = _read(os.path.join(PREV_DIR, "applied_version"))
    old = _read(os.path.join(PREV_DIR, "old_version"))
    at = int(_read(os.path.join(PREV_DIR, "applied_at"), "0") or 0)
    cur = _read(VERSION_FILE)
    if not applied or applied != cur or time.time() - at > ROLLBACK_WINDOW:
        return 0
    ans = _msgbox(
        "VAL//AIM - crash after update",
        f"The game exited with an error right after updating to v{applied}.\n\n"
        f"Restore the previous version (v{old}) and skip v{applied} until a newer one is released?",
        0x4 | 0x30 | 0x40000,   # YESNO | WARNING | TOPMOST
    )
    if ans != 6:                # IDYES
        return 0
    git_prev = _read(os.path.join(PREV_DIR, "git_prev"))
    if os.path.isdir(os.path.join(HERE, ".git")) and git_prev:
        rc, _, err = _git("reset", "--hard", git_prev)
        if rc != 0:
            _msgbox("VAL//AIM", f"rollback failed:\n{err}", 0x10 | 0x40000)
            return 0
    else:
        base = os.path.join(PREV_DIR, "files")
        n = 0
        for root, _dirs, files in os.walk(base):
            for fn in files:
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, base)
                with open(full, "rb") as f:
                    _put_file(rel, f.read())
                n += 1
        # files the update ADDED are left in place (harmless, and MANIFEST of the old version
        # would be needed to know them) - a fresh zip is always clean
        _write(VERSION_FILE, old or "0")
        _say(f"restored {n} files")
    _write(HOLD_FILE, applied)
    _write(os.path.join(PREV_DIR, "applied_version"), "")   # do not offer twice
    _msgbox("VAL//AIM", f"Restored v{old}. v{applied} will be skipped.\nStart the game again.")
    return 0

# ---------------------------------------------------------------- git mode
def _git(*args, timeout=90):
    r = subprocess.run(["git", "-C", HERE, *args], capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()

def git_update():
    if shutil.which("git") is None:
        _say("git clone but git.exe not found - install git or download the ZIP instead")
        return 0
    _, old, _ = _git("rev-parse", "HEAD")
    old_version = _read(VERSION_FILE)
    try:
        rc, _, err = _git("fetch", "--quiet", "origin", BRANCH)
    except subprocess.TimeoutExpired:
        _say("git fetch timed out - playing the current version")
        return 0
    if rc != 0:
        _say("git fetch failed (offline?) - playing the current version")
        return 0
    _, remote_version, _ = _git("show", "FETCH_HEAD:VERSION")
    hold = _read(HOLD_FILE)
    if hold and remote_version == hold:
        _say(f"v{hold} was rolled back on this PC - waiting for a newer release")
        return 0
    _, target, _ = _git("rev-parse", "FETCH_HEAD")
    if old != target:
        rc, _, err = _git("merge", "--ff-only", "--quiet", "FETCH_HEAD")
        _, new, _ = _git("rev-parse", "HEAD")
        if rc != 0 or new != target:
            # diverged, or HEAD is AHEAD of release (cloned `main` = untested commits):
            # with a clean tree, move onto the tested release build
            _, dirty, _ = _git("status", "--porcelain", "--untracked-files=no")   # a stray screenshot must not block updates
            if dirty:
                _say("git: local changes present - not updating (git stash to resume updates)")
                return 0
            rc, _, err = _git("checkout", "-B", BRANCH, "FETCH_HEAD")
            if rc != 0:
                _say(f"git update skipped: {err.splitlines()[-1] if err else rc}")
                return 0
    _, new, _ = _git("rev-parse", "HEAD")
    if old and new and old != new:
        _prev_reset()
        _prev_stamp(old_version, _read(VERSION_FILE), git_prev=old)
        _say(f"updated {old[:7]} -> {new[:7]} (v{_read(VERSION_FILE)})")
        whats_new(_read(VERSION_FILE))
        return 3
    _say(f"up to date (v{old_version})")
    return 0

# ---------------------------------------------------------------- zip mode
def apply_zip(zip_bytes):
    """Overlay the zip onto HERE (backing up replaced files), then prune per MANIFEST."""
    written = 0
    manifest = None
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            parts = info.filename.split("/")[1:]          # drop "val-aim-release/"
            if not parts or not parts[0] or parts[0] in NEVER_TOUCH:
                continue
            rel = os.path.join(*parts)
            blob = z.read(info)
            if rel == "MANIFEST":
                manifest = set(l.strip().replace("/", os.sep) for l in blob.decode("utf-8").splitlines() if l.strip())
            if not _same_file(os.path.join(HERE, rel), blob):
                _prev_backup(rel)
            if _put_file(rel, blob):
                written += 1
    removed = 0
    if manifest:
        for d in MANAGED_DIRS:
            base = os.path.join(HERE, d)
            for root, dirs, files in os.walk(base):
                dirs[:] = [x for x in dirs if x != "__pycache__"]
                for fn in files:
                    rel = os.path.relpath(os.path.join(root, fn), HERE)
                    if rel not in manifest and not fn.endswith((".tmp", ".new")):
                        _prev_backup(rel)
                        os.remove(os.path.join(root, fn))
                        removed += 1
    return written, removed

def zip_update():
    local = _read(VERSION_FILE)
    if not local:
        _say("no VERSION file - developer copy, skipping")
        return 0
    try:
        remote = _fetch(RAW_BASE + "VERSION", timeout=6).decode("utf-8").strip()
    except Exception as e:
        _say(f"cannot reach GitHub ({type(e).__name__}) - playing the current version")
        return 0
    if not remote or remote == local:
        _say(f"up to date (v{local})")
        return 0
    if remote == _read(HOLD_FILE):
        _say(f"v{remote} was rolled back on this PC - waiting for a newer release")
        return 0
    _say(f"new version v{remote} (you have v{local}) - downloading...")
    try:
        blob = _fetch(ZIP_URL, timeout=60)
    except Exception as e:
        _say(f"download failed ({type(e).__name__}) - playing the current version")
        return 0
    _prev_reset()
    try:
        n, removed = apply_zip(blob)
    except Exception as e:
        _say(f"update failed while writing files ({e}) - playing the current version")
        return 0
    _write(VERSION_FILE, remote)
    _prev_stamp(local, remote)
    _say(f"updated to v{remote} ({n} files written, {removed} stale removed)")
    whats_new(remote)
    return 3

def main():
    if "--crashed" in sys.argv:
        return crashed()
    if os.path.isdir(os.path.join(HERE, ".git")):
        return git_update()
    return zip_update()

if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:   # never block the game because of the updater
        _say(f"unexpected error: {e}")
        sys.exit(0)

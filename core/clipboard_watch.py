from __future__ import annotations

import re
import math
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication

from core.util import hash_text


@dataclass
class ClipboardEvent:
    text: str
    text_hash: str
    source_process: Optional[str] = None
    source_title: Optional[str] = None
    blocked_reason: Optional[str] = None


# -----------------------------
# Windows foreground app helpers
# -----------------------------
def _is_windows() -> bool:
    try:
        import os
        return os.name == "nt"
    except Exception:
        return False


def get_foreground_process_and_title() -> Tuple[Optional[str], Optional[str]]:
    """
    Returns (process_name, window_title) if available.
    Windows-only. Returns (None, None) on failure.
    """
    if not _is_windows():
        return None, None

    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)

        GetForegroundWindow = user32.GetForegroundWindow
        GetForegroundWindow.restype = wintypes.HWND

        GetWindowTextW = user32.GetWindowTextW
        GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        GetWindowTextW.restype = ctypes.c_int

        GetWindowThreadProcessId = user32.GetWindowThreadProcessId
        GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        GetWindowThreadProcessId.restype = wintypes.DWORD

        OpenProcess = kernel32.OpenProcess
        OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        OpenProcess.restype = wintypes.HANDLE

        CloseHandle = kernel32.CloseHandle
        CloseHandle.argtypes = [wintypes.HANDLE]
        CloseHandle.restype = wintypes.BOOL

        GetModuleBaseNameW = psapi.GetModuleBaseNameW
        GetModuleBaseNameW.argtypes = [wintypes.HANDLE, wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
        GetModuleBaseNameW.restype = wintypes.DWORD

        hwnd = GetForegroundWindow()
        if not hwnd:
            return None, None

        title_buf = ctypes.create_unicode_buffer(512)
        GetWindowTextW(hwnd, title_buf, 512)
        title = (title_buf.value or "").strip() or None

        pid = wintypes.DWORD(0)
        GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return None, title

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        PROCESS_VM_READ = 0x0010
        hproc = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ, False, pid.value)
        if not hproc:
            return None, title

        try:
            name_buf = ctypes.create_unicode_buffer(260)
            if GetModuleBaseNameW(hproc, None, name_buf, 260) == 0:
                return None, title
            proc = (name_buf.value or "").strip()
            return (proc.lower() if proc else None), title
        finally:
            CloseHandle(hproc)

    except Exception:
        return None, None


# -----------------------------
# Secret heuristics
# -----------------------------
_RE_PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
_RE_JWT = re.compile(r"^[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+$")
_RE_GITHUB = re.compile(r"^(ghp_|github_pat_)[A-Za-z0-9_]+")
_RE_SLACK = re.compile(r"^xox[baprs]-[A-Za-z0-9-]+")
_RE_AWS = re.compile(r"^AKIA[0-9A-Z]{16}$")


def _shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    freq = {}
    for ch in s:
        freq[ch] = freq.get(ch, 0) + 1
    ent = 0.0
    n = len(s)
    for c in freq.values():
        p = c / n
        ent -= p * math.log2(p)
    return ent


def is_suspected_secret(text: str, min_len: int = 16) -> Tuple[bool, str]:
    t = (text or "").strip()
    if len(t) < min_len:
        return False, ""

    tl = t.lower()

    if _RE_PRIVATE_KEY.search(t):
        return True, "private key block"
    if tl.startswith("bearer ") or "authorization:" in tl:
        return True, "auth header / bearer token"
    if _RE_GITHUB.match(t):
        return True, "github token"
    if _RE_SLACK.match(t):
        return True, "slack token"
    if _RE_AWS.match(t):
        return True, "aws access key id"
    if _RE_JWT.match(t) and len(t) >= 40:
        return True, "jwt-like token"

    keywords = ("password", "passcode", "otp", "2fa", "token", "apikey", "api key", "secret", "private key")
    if any(k in tl for k in keywords):
        return True, "secret keyword present"

    if " " not in t and "\n" not in t:
        has_upper = any("A" <= c <= "Z" for c in t)
        has_digit = any(c.isdigit() for c in t)
        has_sym = any(not c.isalnum() for c in t)
        ent = _shannon_entropy(t)
        if len(t) >= 24 and ent >= 3.6 and (has_digit and (has_upper or has_sym)):
            return True, f"high-entropy token (entropy {ent:.2f})"

    return False, ""


# -----------------------------
# Watcher
# -----------------------------
class ClipboardWatcher(QObject):
    def __init__(self, app: QApplication, poll_interval_ms: int = 350):
        super().__init__()
        self._app = app

        self._timer = QTimer(self)
        self._timer.setInterval(max(100, int(poll_interval_ms)))
        self._timer.timeout.connect(self._poll)

        self._on_new_text: Optional[Callable[[ClipboardEvent], None]] = None

        self.capture_paused: bool = False
        self.capture_mode: str = "blocklist"
        self.blocked_processes: list[str] = []
        self.allowed_processes: list[str] = []
        self.blocked_title_keywords: list[str] = []
        self.secret_heuristics_enabled: bool = True
        self.secret_min_len: int = 16

        self._last_seen_hash: Optional[str] = None

        # debug fields (optional)
        self.last_decision: str = "idle"
        self.last_foreground: str = ""
        self.last_title: str = ""

    def configure(
        self,
        *,
        capture_paused: bool,
        capture_mode: str,
        blocked_processes: list[str],
        allowed_processes: list[str],
        blocked_title_keywords: list[str],
        secret_heuristics_enabled: bool,
        secret_min_len: int,
        settle_delay_ms: int,  # accepted for compatibility; ignored in this simplified version
    ) -> None:
        self.capture_paused = bool(capture_paused)
        self.capture_mode = (capture_mode or "blocklist").lower().strip()
        self.capture_mode = "whitelist" if self.capture_mode == "whitelist" else "blocklist"

        self.blocked_processes = [str(x).lower() for x in (blocked_processes or [])]
        self.allowed_processes = [str(x).lower() for x in (allowed_processes or [])]
        self.blocked_title_keywords = [str(x).lower() for x in (blocked_title_keywords or [])]

        self.secret_heuristics_enabled = bool(secret_heuristics_enabled)
        self.secret_min_len = max(8, int(secret_min_len))

    def set_interval(self, poll_interval_ms: int) -> None:
        self._timer.setInterval(max(100, int(poll_interval_ms)))

    def on_new_text(self, cb: Callable[[ClipboardEvent], None]) -> None:
        self._on_new_text = cb

    def start(self) -> None:
        self._timer.start()
        QTimer.singleShot(200, self._poll)

    def stop(self) -> None:
        self._timer.stop()

    def poke(self) -> None:
        self._poll()

    def _poll(self) -> None:
        if self.capture_paused:
            self.last_decision = "paused"
            return

        cb = self._app.clipboard()
        text = (cb.text() or "").strip()
        if not text:
            self.last_decision = "empty"
            return

        h = hash_text(text)
        if self._last_seen_hash == h:
            self.last_decision = "duplicate"
            return

        proc, title = get_foreground_process_and_title()
        self.last_foreground = proc or ""
        self.last_title = title or ""

        blocked, reason = self._should_block(text, proc, title)
        if blocked:
            self._last_seen_hash = h
            self.last_decision = f"blocked: {reason}"
            return

        self._last_seen_hash = h
        self.last_decision = "captured"

        if self._on_new_text:
            self._on_new_text(
                ClipboardEvent(
                    text=text,
                    text_hash=h,
                    source_process=proc,
                    source_title=title,
                    blocked_reason=None,
                )
            )

    def _should_block(self, text: str, proc: Optional[str], title: Optional[str]) -> Tuple[bool, str]:
        p = (proc or "").lower().strip()
        t = (title or "").lower().strip()

        if self.capture_mode == "whitelist":
            if self.allowed_processes and p and p not in self.allowed_processes:
                return True, f"not in whitelist: {p}"
        else:
            if p and p in self.blocked_processes:
                return True, f"blocked process: {p}"

        if t and self.blocked_title_keywords:
            for kw in self.blocked_title_keywords:
                if kw and kw in t:
                    return True, f"blocked title keyword: {kw}"

        if self.secret_heuristics_enabled:
            suspected, why = is_suspected_secret(text, min_len=self.secret_min_len)
            if suspected:
                return True, f"suspected secret: {why}"

        return False, ""

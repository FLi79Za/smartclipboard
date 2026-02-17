import json
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class AppSettings:
    ollama_base: str = "http://127.0.0.1:11434"
    default_model: str = ""
    default_persona: str = "uk_editor"
    poll_interval_ms: int = 350
    output_target: str = "replace_composer"  # replace_composer | append_composer | new_versioned_clip | copy_clipboard
    quick_export_dir: str = ""  # if empty -> data/exports

    # Capture safety
    capture_paused: bool = False

    # "blocklist" = capture all except blocked apps
    # "whitelist" = capture only from allowed apps (safest)
    capture_mode: str = "blocklist"  # blocklist | whitelist

    # Process names (lowercase, with .exe) recommended
    blocked_processes: List[str] = field(
        default_factory=lambda: [
            "1password.exe",
            "keepass.exe",
            "keepassxc.exe",
            "lastpass.exe",
            "lastpass",
        ]
    )
    allowed_processes: List[str] = field(default_factory=list)  # used when capture_mode="whitelist"

    # Window-title keyword block (lowercase)
    blocked_title_keywords: List[str] = field(
        default_factory=lambda: [
            "1password",
            "keepass",
            "keepassxc",
            "lastpass",
            "password",
            "sign in",
            "login",
            "otp",
        ]
    )

    # Content-based secret detection
    secret_heuristics_enabled: bool = True
    secret_settle_delay_ms: int = 650  # wait before persisting to allow auto-clear
    secret_min_len: int = 16  # ignore short strings for entropy-based checks


class SettingsStore:
    def __init__(self, path: Path):
        self.path = path
        self._settings = AppSettings()
        self.load()

    @property
    def value(self) -> AppSettings:
        return self._settings

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            merged = asdict(self._settings)
            # only accept known keys
            for k, v in data.items():
                if k in merged:
                    merged[k] = v
            # normalise lists
            merged["blocked_processes"] = [str(x).lower() for x in (merged.get("blocked_processes") or [])]
            merged["allowed_processes"] = [str(x).lower() for x in (merged.get("allowed_processes") or [])]
            merged["blocked_title_keywords"] = [str(x).lower() for x in (merged.get("blocked_title_keywords") or [])]

            # normalise capture_mode
            cm = str(merged.get("capture_mode") or "blocklist").lower().strip()
            merged["capture_mode"] = "whitelist" if cm == "whitelist" else "blocklist"

            self._settings = AppSettings(**merged)
        except Exception:
            self._settings = AppSettings()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data: Dict[str, Any] = asdict(self._settings)
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def update(self, **kwargs: Any) -> None:
        d = asdict(self._settings)
        for k, v in kwargs.items():
            if k in d:
                d[k] = v

        # normalise lists and mode
        d["blocked_processes"] = [str(x).lower() for x in (d.get("blocked_processes") or [])]
        d["allowed_processes"] = [str(x).lower() for x in (d.get("allowed_processes") or [])]
        d["blocked_title_keywords"] = [str(x).lower() for x in (d.get("blocked_title_keywords") or [])]
        cm = str(d.get("capture_mode") or "blocklist").lower().strip()
        d["capture_mode"] = "whitelist" if cm == "whitelist" else "blocklist"

        self._settings = AppSettings(**d)
        self.save()

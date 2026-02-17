from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List, Optional

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSplitter,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.db import ClipDB, Clip
from core.settings import SettingsStore
from core.clipboard_watch import ClipboardWatcher, ClipboardEvent
from ai.ollama_client import OllamaClient
from ai.prompt_builder import build_system_prompt, build_user_prompt


class ModelRefreshWorker(QThread):
    models_ready = Signal(list)
    error = Signal(str)

    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url

    def run(self) -> None:
        try:
            client = OllamaClient(self.base_url)
            models = client.list_models()
            self.models_ready.emit(models)
        except Exception as e:
            self.error.emit(str(e))


class AiRunWorker(QThread):
    done = Signal(str)
    error = Signal(str)

    def __init__(self, base_url: str, model: str, system: str, user: str):
        super().__init__()
        self.base_url = base_url
        self.model = model
        self.system = system
        self.user = user

    def run(self) -> None:
        try:
            client = OllamaClient(self.base_url)
            out = client.chat(model=self.model, system=self.system, user=self.user)
            self.done.emit(out)
        except Exception as e:
            self.error.emit(str(e))


class PromptPreviewDialog(QDialog):
    def __init__(self, parent: QWidget, model: str, system: str, user: str):
        super().__init__(parent)
        self.setWindowTitle("Prompt preview")
        self.resize(900, 700)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Model: {model}"))

        layout.addWidget(QLabel("System prompt"))
        self.system_box = QTextEdit()
        self.system_box.setReadOnly(True)
        self.system_box.setPlainText(system)
        layout.addWidget(self.system_box, 1)

        layout.addWidget(QLabel("User prompt"))
        self.user_box = QTextEdit()
        self.user_box.setReadOnly(True)
        self.user_box.setPlainText(user)
        layout.addWidget(self.user_box, 2)

        btn_row = QHBoxLayout()
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        btn_row.addStretch(1)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)


class MainWindow(QMainWindow):
    def __init__(self, app_root: Path, data_dir: Path, settings: SettingsStore, db: ClipDB):
        super().__init__()
        self.app_root = app_root
        self.data_dir = data_dir
        self.settings = settings
        self.db = db

        self.setWindowTitle("Smart Clipboard (MVP)")
        self.resize(1320, 850)

        # Load config
        self.personas = self._load_json(app_root / "config" / "personas.json")
        self.actions = self._load_json(app_root / "config" / "actions.json")

        self._persona_map = {
            p["id"]: p
            for p in self.personas.get("personas", [])
            if isinstance(p, dict) and "id" in p
        }
        self._action_list = self.actions if isinstance(self.actions, list) else []
        self._action_map = {a.get("id"): a for a in self._action_list if isinstance(a, dict)}

        # UI
        self._build_ui()

        # Watcher
        self.watcher = ClipboardWatcher(QApplication.instance(), poll_interval_ms=self.settings.value.poll_interval_ms)
        self.watcher.on_new_text(self._on_clipboard_text)
        self._apply_capture_settings_to_watcher()
        self.watcher.start()

        # In-app hotkey (global hotkeys later)
        self._pause_shortcut = QShortcut(QKeySequence("Ctrl+Shift+P"), self)
        self._pause_shortcut.activated.connect(self.toggle_capture_pause)

        # Debug updater
        self._dbg_timer = QTimer(self)
        self._dbg_timer.setInterval(300)
        self._dbg_timer.timeout.connect(self._update_capture_debug)
        self._dbg_timer.start()

        # Initial load
        self.refresh_history()
        self.refresh_models()
        self._refresh_persona_info()
        self._refresh_action_info()
        self._update_capture_status_label()
        self._update_capture_debug()

        # Nudge once after UI stabilises
        QTimer.singleShot(350, self.watcher.poke)

    # ---------------- UI ----------------

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)

        splitter = QSplitter(Qt.Horizontal)

        # Left: History
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Clipboard History"))

        self.history_list = QListWidget()
        self.history_list.itemSelectionChanged.connect(self._on_history_select)
        self.history_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.history_list.customContextMenuRequested.connect(self._show_history_menu)
        left_layout.addWidget(self.history_list)

        hist_btn_row = QHBoxLayout()
        self.btn_pin = QPushButton("Pin/Unpin")
        self.btn_pin.clicked.connect(self.toggle_pin_selected)
        self.btn_delete = QPushButton("Delete")
        self.btn_delete.clicked.connect(self.delete_selected)
        self.btn_copyback = QPushButton("Copy back")
        self.btn_copyback.clicked.connect(self.copy_selected_to_clipboard)
        hist_btn_row.addWidget(self.btn_pin)
        hist_btn_row.addWidget(self.btn_delete)
        hist_btn_row.addWidget(self.btn_copyback)
        left_layout.addLayout(hist_btn_row)

        hist_btn_row2 = QHBoxLayout()
        self.btn_send_append = QPushButton("Append → Composer")
        self.btn_send_append.clicked.connect(lambda: self.send_selected_to_composer(mode="append"))
        self.btn_send_replace = QPushButton("Replace Composer")
        self.btn_send_replace.clicked.connect(lambda: self.send_selected_to_composer(mode="replace"))
        hist_btn_row2.addWidget(self.btn_send_append)
        hist_btn_row2.addWidget(self.btn_send_replace)
        left_layout.addLayout(hist_btn_row2)

        self.btn_save_clip = QPushButton("Save clip to file…")
        self.btn_save_clip.clicked.connect(self.save_selected_clip_to_file)
        left_layout.addWidget(self.btn_save_clip)

        # Centre: Composer
        centre = QWidget()
        centre_layout = QVBoxLayout(centre)
        centre_layout.addWidget(QLabel("Composer"))

        self.composer = QTextEdit()
        centre_layout.addWidget(self.composer)

        comp_btn_row = QHBoxLayout()
        self.separator_combo = QComboBox()
        self.separator_combo.addItems(["Blank line", "---", "Markdown heading", "Numbered label"])
        comp_btn_row.addWidget(QLabel("Separator:"))
        comp_btn_row.addWidget(self.separator_combo)

        self.btn_clear = QPushButton("Clear")
        self.btn_clear.clicked.connect(self.composer.clear)
        self.btn_copy_comp = QPushButton("Copy composer")
        self.btn_copy_comp.clicked.connect(self.copy_composer_to_clipboard)
        comp_btn_row.addWidget(self.btn_clear)
        comp_btn_row.addWidget(self.btn_copy_comp)
        centre_layout.addLayout(comp_btn_row)

        comp_btn_row2 = QHBoxLayout()
        self.btn_save_comp = QPushButton("Save composer to file…")
        self.btn_save_comp.clicked.connect(self.save_composer_to_file)
        self.btn_quick_save = QPushButton("Quick save")
        self.btn_quick_save.clicked.connect(self.quick_save_composer)
        comp_btn_row2.addWidget(self.btn_save_comp)
        comp_btn_row2.addWidget(self.btn_quick_save)
        centre_layout.addLayout(comp_btn_row2)

        # Right: AI + Capture
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(QLabel("AI Actions"))

        # Capture controls
        cap_row = QHBoxLayout()
        self.capture_status = QLabel("")
        self.capture_status.setStyleSheet("font-weight: 600;")
        self.btn_toggle_capture = QPushButton("Pause capture")
        self.btn_toggle_capture.clicked.connect(self.toggle_capture_pause)
        cap_row.addWidget(self.capture_status, 1)
        cap_row.addWidget(self.btn_toggle_capture)
        right_layout.addLayout(cap_row)

        self.capture_debug = QLabel("")
        self.capture_debug.setWordWrap(True)
        self.capture_debug.setStyleSheet("color: #bbbbbb;")
        right_layout.addWidget(self.capture_debug)

        cap_hint = QLabel("Tip: Ctrl+Shift+P toggles capture (in-app).")
        cap_hint.setStyleSheet("color: #bbbbbb;")
        cap_hint.setWordWrap(True)
        right_layout.addWidget(cap_hint)

        # Persona
        self.persona_combo = QComboBox()
        for p in self.personas.get("personas", []):
            if isinstance(p, dict) and "id" in p and "name" in p:
                self.persona_combo.addItem(p["name"], p["id"])
        self._select_combo_by_data(self.persona_combo, self.settings.value.default_persona)
        self.persona_combo.currentIndexChanged.connect(self._on_persona_changed)
        right_layout.addWidget(QLabel("Persona"))
        right_layout.addWidget(self.persona_combo)

        self.persona_info = QLabel("")
        self.persona_info.setWordWrap(True)
        self.persona_info.setStyleSheet("color: #bbbbbb;")
        right_layout.addWidget(self.persona_info)

        # Model
        model_row = QHBoxLayout()
        self.model_combo = QComboBox()
        self.model_combo.setEnabled(False)
        self.model_combo.currentIndexChanged.connect(self._on_model_changed)
        self.btn_refresh_models = QPushButton("Refresh")
        self.btn_refresh_models.clicked.connect(self.refresh_models)
        model_row.addWidget(self.model_combo, 1)
        model_row.addWidget(self.btn_refresh_models)
        right_layout.addWidget(QLabel("Model"))
        right_layout.addLayout(model_row)

        # Poll interval
        poll_row = QHBoxLayout()
        poll_row.addWidget(QLabel("Clipboard poll (ms)"))
        self.poll_spin = QSpinBox()
        self.poll_spin.setRange(100, 2000)
        self.poll_spin.setValue(int(self.settings.value.poll_interval_ms))
        self.poll_spin.valueChanged.connect(self._on_poll_changed)
        poll_row.addWidget(self.poll_spin)
        right_layout.addLayout(poll_row)

        # Action
        self.action_combo = QComboBox()
        for a in self._action_list:
            if isinstance(a, dict):
                self.action_combo.addItem(a.get("name", a.get("id", "action")), a.get("id"))
        self.action_combo.currentIndexChanged.connect(self._on_action_changed)
        right_layout.addWidget(QLabel("Action"))
        right_layout.addWidget(self.action_combo)

        self.action_info = QLabel("")
        self.action_info.setWordWrap(True)
        self.action_info.setStyleSheet("color: #bbbbbb;")
        right_layout.addWidget(self.action_info)

        # Extra instruction
        right_layout.addWidget(QLabel("Extra instruction (optional, highest priority)"))
        self.extra_instruction = QTextEdit()
        self.extra_instruction.setPlaceholderText(
            "e.g. Keep under 120 words, preserve technical terms, write as an internal email, etc."
        )
        self.extra_instruction.setFixedHeight(90)
        right_layout.addWidget(self.extra_instruction)

        # Apply source
        right_layout.addWidget(QLabel("Apply to"))
        self.apply_source = QComboBox()
        self.apply_source.addItems(["Composer", "Selected clip"])
        right_layout.addWidget(self.apply_source)

        # Output target
        right_layout.addWidget(QLabel("Output target"))
        self.out_group = QButtonGroup(self)
        self.rb_replace = QRadioButton("Replace composer")
        self.rb_append = QRadioButton("Append to composer")
        self.rb_newclip = QRadioButton("New versioned clip")
        self.rb_copy = QRadioButton("Copy to clipboard")
        self.out_group.addButton(self.rb_replace)
        self.out_group.addButton(self.rb_append)
        self.out_group.addButton(self.rb_newclip)
        self.out_group.addButton(self.rb_copy)

        right_layout.addWidget(self.rb_replace)
        right_layout.addWidget(self.rb_append)
        right_layout.addWidget(self.rb_newclip)
        right_layout.addWidget(self.rb_copy)

        self._select_output_radio(self.settings.value.output_target)
        self.out_group.buttonClicked.connect(self._on_output_target_changed)

        # Run + Preview
        btn_row = QHBoxLayout()
        self.btn_run = QPushButton("Run action")
        self.btn_run.clicked.connect(self.run_action)
        self.btn_preview = QPushButton("Preview prompt")
        self.btn_preview.clicked.connect(self.preview_prompt)
        btn_row.addWidget(self.btn_run, 2)
        btn_row.addWidget(self.btn_preview, 1)
        right_layout.addLayout(btn_row)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        right_layout.addWidget(self.status_label)
        right_layout.addStretch(1)

        splitter.addWidget(left)
        splitter.addWidget(centre)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setStretchFactor(2, 1)

        layout = QHBoxLayout(root)
        layout.addWidget(splitter)

        # Menu
        file_menu = self.menuBar().addMenu("File")
        act_open_data = QAction("Open data folder", self)
        act_open_data.triggered.connect(self.open_data_folder)
        file_menu.addAction(act_open_data)

        capture_menu = self.menuBar().addMenu("Capture")
        self.act_toggle_capture = QAction("Pause capture", self)
        self.act_toggle_capture.triggered.connect(self.toggle_capture_pause)
        capture_menu.addAction(self.act_toggle_capture)

        act_open_settings = QAction("Open settings.json", self)
        act_open_settings.triggered.connect(self.open_settings_file)
        capture_menu.addAction(act_open_settings)

    # ---------------- Capture ----------------

    def _apply_capture_settings_to_watcher(self) -> None:
        s = self.settings.value
        # The simplified watcher accepts settle_delay_ms for compatibility but ignores it.
        self.watcher.configure(
            capture_paused=getattr(s, "capture_paused", False),
            capture_mode=getattr(s, "capture_mode", "blocklist"),
            blocked_processes=getattr(s, "blocked_processes", []),
            allowed_processes=getattr(s, "allowed_processes", []),
            blocked_title_keywords=getattr(s, "blocked_title_keywords", []),
            secret_heuristics_enabled=getattr(s, "secret_heuristics_enabled", True),
            secret_min_len=getattr(s, "secret_min_len", 16),
            settle_delay_ms=getattr(s, "secret_settle_delay_ms", 0),
        )

    def _update_capture_status_label(self) -> None:
        paused = bool(getattr(self.settings.value, "capture_paused", False))
        if paused:
            self.capture_status.setText("CAPTURE: OFF")
            self.capture_status.setStyleSheet("font-weight: 700; color: #ff9a9a;")
            self.btn_toggle_capture.setText("Resume capture")
            self.act_toggle_capture.setText("Resume capture")
        else:
            self.capture_status.setText("CAPTURE: ON")
            self.capture_status.setStyleSheet("font-weight: 700; color: #9affb0;")
            self.btn_toggle_capture.setText("Pause capture")
            self.act_toggle_capture.setText("Pause capture")

    def _update_capture_debug(self) -> None:
        w = self.watcher
        fg = getattr(w, "last_foreground", "") or "(unknown)"
        title = getattr(w, "last_title", "") or ""
        decision = getattr(w, "last_decision", "") or "idle"
        if title:
            self.capture_debug.setText(f"Last: {decision}\nForeground: {fg}\nTitle: {title}")
        else:
            self.capture_debug.setText(f"Last: {decision}\nForeground: {fg}")

    def toggle_capture_pause(self) -> None:
        current = bool(getattr(self.settings.value, "capture_paused", False))
        self.settings.update(capture_paused=not current)
        self._apply_capture_settings_to_watcher()
        self._update_capture_status_label()
        self.watcher.poke()

    def open_settings_file(self) -> None:
        try:
            import os
            import subprocess

            p = str(self.data_dir / "settings.json")
            if os.name == "nt":
                subprocess.Popen(["notepad", p])
            else:
                subprocess.Popen(["xdg-open", p])
        except Exception as e:
            QMessageBox.information(self, "Info", str(e))

    # ---------------- Clipboard + DB ----------------

    def _on_clipboard_text(self, ev: ClipboardEvent) -> None:
        self.db.add_text_clip(ev.text, ev.text_hash)
        self.refresh_history()

    def refresh_history(self) -> None:
        self.history_list.blockSignals(True)
        self.history_list.clear()
        clips = self.db.list_clips(limit=300)

        for c in clips:
            preview = c.content.replace("\n", " ").strip()
            if len(preview) > 90:
                preview = preview[:90] + "…"
            label = f"{'📌 ' if c.pinned else ''}#{c.id}  {c.created_at}  {preview}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, c.id)
            self.history_list.addItem(item)

        self.history_list.blockSignals(False)

    def selected_clip_id(self) -> Optional[int]:
        items = self.history_list.selectedItems()
        if not items:
            return None
        return items[0].data(Qt.UserRole)

    def selected_clip(self) -> Optional[Clip]:
        cid = self.selected_clip_id()
        return self.db.get_clip(cid) if cid else None

    def _on_history_select(self) -> None:
        return

    def toggle_pin_selected(self) -> None:
        c = self.selected_clip()
        if not c:
            return
        self.db.set_pinned(c.id, 0 if c.pinned else 1)
        self.refresh_history()

    def delete_selected(self) -> None:
        c = self.selected_clip()
        if not c:
            return
        self.db.delete_clip(c.id)
        self.refresh_history()

    def copy_selected_to_clipboard(self) -> None:
        c = self.selected_clip()
        if not c:
            return
        QApplication.instance().clipboard().setText(c.content)

    def copy_composer_to_clipboard(self) -> None:
        txt = self.composer.toPlainText()
        if not txt.strip():
            return
        QApplication.instance().clipboard().setText(txt)

    def send_selected_to_composer(self, mode: str = "append") -> None:
        c = self.selected_clip()
        if not c:
            return

        if mode == "replace":
            self.composer.setPlainText(c.content)
            return

        sep = self._separator_text()
        existing = self.composer.toPlainText()
        if existing.strip():
            self.composer.setPlainText(existing + sep + c.content)
        else:
            self.composer.setPlainText(c.content)

    def _separator_text(self) -> str:
        choice = self.separator_combo.currentText()
        if choice == "Blank line":
            return "\n\n"
        if choice == "---":
            return "\n\n---\n\n"
        if choice == "Markdown heading":
            return "\n\n## Clip\n\n"
        if choice == "Numbered label":
            return "\n\n1) \n"
        return "\n\n"

    # ---------------- Export ----------------

    def exports_dir(self) -> Path:
        s = (self.settings.value.quick_export_dir or "").strip()
        if s:
            p = Path(s)
        else:
            p = self.data_dir / "exports"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def save_selected_clip_to_file(self) -> None:
        c = self.selected_clip()
        if not c:
            return
        self._save_text_as_dialog(c.content, suggested=f"clip_{c.id}.txt")

    def save_composer_to_file(self) -> None:
        txt = self.composer.toPlainText()
        if not txt.strip():
            return
        self._save_text_as_dialog(txt, suggested="composer.txt")

    def quick_save_composer(self) -> None:
        txt = self.composer.toPlainText()
        if not txt.strip():
            return
        out = self.exports_dir() / self._default_export_name(prefix="composer")
        try:
            out.write_text(txt, encoding="utf-8")
            self.status_label.setText(f"Saved: {out}")
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))

    def _default_export_name(self, prefix: str = "SmartClipboard") -> str:
        from datetime import datetime

        ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        return f"{prefix}_{ts}.txt"

    def _save_text_as_dialog(self, text: str, suggested: str = "output.txt") -> None:
        start_dir = str(self.exports_dir())
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save to file",
            str(Path(start_dir) / suggested),
            "Text (*.txt);;Markdown (*.md);;JSON (*.json);;All files (*.*)",
        )
        if not path:
            return

        p = Path(path)
        suffix = p.suffix.lower()
        try:
            if suffix == ".json":
                payload = {
                    "content": text,
                    "saved_at": self._local_iso(),
                    "model": self.model_combo.currentText(),
                    "persona": self.persona_combo.currentData(),
                    "action": self.action_combo.currentData(),
                }
                p.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            else:
                p.write_text(text, encoding="utf-8")

            self.status_label.setText(f"Saved: {p}")
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))

    def _local_iso(self) -> str:
        from datetime import datetime

        return datetime.now().isoformat(timespec="seconds")

    # ---------------- Ollama models ----------------

    def refresh_models(self) -> None:
        self.status_label.setText("Refreshing models…")
        self.btn_refresh_models.setEnabled(False)

        base = self.settings.value.ollama_base
        self._model_worker = ModelRefreshWorker(base)
        self._model_worker.models_ready.connect(self._on_models_ready)
        self._model_worker.error.connect(self._on_models_error)
        self._model_worker.finished.connect(lambda: self.btn_refresh_models.setEnabled(True))
        self._model_worker.start()

    def _on_models_ready(self, models: List[str]) -> None:
        self.model_combo.blockSignals(True)
        self.model_combo.clear()

        if not models:
            self.status_label.setText("No Ollama models found (or Ollama is empty).")
            self.model_combo.setEnabled(False)
            self.model_combo.blockSignals(False)
            return

        for m in models:
            self.model_combo.addItem(m)

        self.model_combo.setEnabled(True)

        desired = (self.settings.value.default_model or "").strip()
        if desired:
            ok = self._select_combo_by_text(self.model_combo, desired)
            if not ok:
                self.settings.update(default_model=self.model_combo.currentText())
        else:
            self.settings.update(default_model=self.model_combo.currentText())

        self.model_combo.blockSignals(False)
        self.status_label.setText(f"Models loaded: {len(models)}")

    def _on_models_error(self, msg: str) -> None:
        self.model_combo.setEnabled(False)
        self.status_label.setText(f"Ollama not available: {msg}")

    def _on_model_changed(self) -> None:
        current = (self.model_combo.currentText() or "").strip()
        if current:
            self.settings.update(default_model=current)

    # ---------------- Personas / actions info ----------------

    def _on_persona_changed(self) -> None:
        pid = self.persona_combo.currentData()
        if isinstance(pid, str) and pid.strip():
            self.settings.update(default_persona=pid)
        self._refresh_persona_info()

    def _on_action_changed(self) -> None:
        self._refresh_action_info()

    def _refresh_persona_info(self) -> None:
        pid = self.persona_combo.currentData()
        p = self._persona_map.get(pid, {})
        desc = (p.get("description") or "").strip()
        if not desc:
            sys_txt = (p.get("system") or "").strip()
            desc = sys_txt[:160] + ("…" if len(sys_txt) > 160 else "") if sys_txt else ""
        self.persona_info.setText(desc)

    def _refresh_action_info(self) -> None:
        aid = self.action_combo.currentData()
        a = self._action_map.get(aid, {})
        desc = (a.get("description") or "").strip()
        if not desc:
            instr = (a.get("instruction") or "").strip()
            desc = instr[:160] + ("…" if len(instr) > 160 else "") if instr else ""
        self.action_info.setText(desc)

    def _on_poll_changed(self, v: int) -> None:
        self.settings.update(poll_interval_ms=int(v))
        self.watcher.set_interval(int(v))

    def _on_output_target_changed(self) -> None:
        target = self._current_output_target()
        self.settings.update(output_target=target)

    def _current_output_target(self) -> str:
        if self.rb_replace.isChecked():
            return "replace_composer"
        if self.rb_append.isChecked():
            return "append_composer"
        if self.rb_newclip.isChecked():
            return "new_versioned_clip"
        return "copy_clipboard"

    def _select_output_radio(self, target: str) -> None:
        t = (target or "").strip()
        if t == "append_composer":
            self.rb_append.setChecked(True)
        elif t == "new_versioned_clip":
            self.rb_newclip.setChecked(True)
        elif t == "copy_clipboard":
            self.rb_copy.setChecked(True)
        else:
            self.rb_replace.setChecked(True)

    # ---------------- Prompt assembly / preview ----------------

    def _build_prompts_for_current_state(self) -> Optional[tuple[str, str, str, Optional[int], str]]:
        model = (self.model_combo.currentText() or "").strip()
        if not model:
            QMessageBox.warning(self, "No model", "No Ollama model selected.")
            return None

        action_id = self.action_combo.currentData()
        action = self._action_map.get(action_id)
        if not action:
            QMessageBox.warning(self, "No action", "No action selected.")
            return None

        persona_id = self.persona_combo.currentData()
        persona = self._persona_map.get(persona_id)
        if not persona:
            QMessageBox.warning(self, "No persona", "No persona selected.")
            return None

        apply_to = self.apply_source.currentText()
        text_in = ""
        parent_id: Optional[int] = None

        if apply_to == "Selected clip":
            c = self.selected_clip()
            if not c:
                QMessageBox.warning(self, "No clip selected", "Select a clip in history first.")
                return None
            text_in = c.content
            parent_id = c.id
        else:
            text_in = self.composer.toPlainText()

        if not text_in.strip():
            QMessageBox.warning(self, "No text", "Nothing to process.")
            return None

        extra = (self.extra_instruction.toPlainText() or "").strip()

        system = build_system_prompt(persona.get("system", ""))
        user = build_user_prompt(
            action_instruction=action.get("instruction", ""),
            output_format=action.get("output_format", "Return only the output."),
            text=text_in,
            extra_instruction=extra,
        )
        action_name = action.get("name", str(action_id))
        return model, system, user, parent_id, action_name

    def preview_prompt(self) -> None:
        built = self._build_prompts_for_current_state()
        if not built:
            return
        model, system, user, _parent_id, _action_name = built
        dlg = PromptPreviewDialog(self, model=model, system=system, user=user)
        dlg.exec()

    # ---------------- AI action ----------------

    def run_action(self) -> None:
        built = self._build_prompts_for_current_state()
        if not built:
            return

        model, system, user, parent_id, action_name = built

        self.btn_run.setEnabled(False)
        self.status_label.setText("Running…")

        base = self.settings.value.ollama_base
        self._ai_worker = AiRunWorker(base, model, system, user)
        self._ai_worker.done.connect(lambda out: self._on_ai_done(out, parent_id, action_name))
        self._ai_worker.error.connect(self._on_ai_error)
        self._ai_worker.finished.connect(lambda: self.btn_run.setEnabled(True))
        self._ai_worker.start()

    def _on_ai_done(self, out: str, parent_id: Optional[int], action_name: str) -> None:
        out = (out or "").strip()
        if not out:
            self.status_label.setText("No output returned.")
            return

        target = self._current_output_target()
        if target == "replace_composer":
            self.composer.setPlainText(out)
        elif target == "append_composer":
            existing = self.composer.toPlainText()
            sep = "\n\n"
            self.composer.setPlainText((existing + sep + out) if existing.strip() else out)
        elif target == "new_versioned_clip":
            from core.util import hash_text

            self.db.add_text_clip(out, hash_text(out), parent_id=parent_id, version_note=action_name)
            self.refresh_history()
        else:
            QApplication.instance().clipboard().setText(out)

        self.status_label.setText("Done.")

    def _on_ai_error(self, msg: str) -> None:
        self.status_label.setText(f"AI error: {msg}")

    # ---------------- Context menu ----------------

    def _show_history_menu(self, pos) -> None:
        c = self.selected_clip()
        if not c:
            return

        menu = QMenu(self)
        a_copy = menu.addAction("Copy back to clipboard")
        a_append = menu.addAction("Append to composer")
        a_replace = menu.addAction("Replace composer")
        menu.addSeparator()
        a_pin = menu.addAction("Pin/Unpin")
        a_save = menu.addAction("Save clip to file…")
        a_del = menu.addAction("Delete")

        chosen = menu.exec(self.history_list.mapToGlobal(pos))
        if chosen == a_copy:
            self.copy_selected_to_clipboard()
        elif chosen == a_append:
            self.send_selected_to_composer("append")
        elif chosen == a_replace:
            self.send_selected_to_composer("replace")
        elif chosen == a_pin:
            self.toggle_pin_selected()
        elif chosen == a_save:
            self.save_selected_clip_to_file()
        elif chosen == a_del:
            self.delete_selected()

    # ---------------- Helpers ----------------

    def _load_json(self, path: Path) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _select_combo_by_data(self, combo: QComboBox, data: Any) -> bool:
        for i in range(combo.count()):
            if combo.itemData(i) == data:
                combo.setCurrentIndex(i)
                return True
        return False

    def _select_combo_by_text(self, combo: QComboBox, text: str) -> bool:
        text = (text or "").strip()
        for i in range(combo.count()):
            if combo.itemText(i) == text:
                combo.setCurrentIndex(i)
                return True
        return False

    def open_data_folder(self) -> None:
        try:
            import os
            import subprocess

            p = str(self.data_dir)
            if os.name == "nt":
                subprocess.Popen(["explorer", p])
            elif os.name == "posix":
                subprocess.Popen(["xdg-open", p])
        except Exception as e:
            QMessageBox.information(self, "Info", str(e))

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


# ---------------------------
# Helpers / IO
# ---------------------------

def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))

def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

def backup_file(path: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_suffix(path.suffix + f".bak_{ts}")
    shutil.copy2(path, backup)
    return backup

def is_valid_id(s: str) -> bool:
    s = (s or "").strip()
    if not s:
        return False
    # keep it simple: allow a-z0-9_-
    for ch in s:
        if not (ch.isalnum() or ch in "_-"):
            return False
    return True


# ---------------------------
# Schemas (light validation)
# ---------------------------

PERSONA_REQUIRED = ["id", "name", "description", "system"]
ACTION_REQUIRED = ["id", "name", "description", "instruction", "output_format"]

@dataclass
class PersonaItem:
    id: str
    name: str
    description: str
    system: str

@dataclass
class ActionItem:
    id: str
    name: str
    description: str
    instruction: str
    output_format: str


# ---------------------------
# Edit Dialogs
# ---------------------------

class PersonaEditDialog(QDialog):
    def __init__(self, parent: QWidget, title: str, existing_ids: List[str], item: Optional[PersonaItem] = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(720, 520)

        self.existing_ids = set(existing_ids)
        self.original_id = item.id if item else ""

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.id_edit = QLineEdit(item.id if item else "")
        self.name_edit = QLineEdit(item.name if item else "")
        self.desc_edit = QLineEdit(item.description if item else "")
        self.system_edit = QTextEdit()
        self.system_edit.setPlainText(item.system if item else "")
        self.system_edit.setMinimumHeight(220)

        form.addRow("id", self.id_edit)
        form.addRow("name", self.name_edit)
        form.addRow("description", self.desc_edit)
        form.addRow("system prompt", self.system_edit)

        layout.addLayout(form)

        btn_row = QHBoxLayout()
        self.btn_ok = QPushButton("Save")
        self.btn_cancel = QPushButton("Cancel")
        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(self.btn_ok)
        layout.addLayout(btn_row)

    def get_value(self) -> Optional[PersonaItem]:
        pid = self.id_edit.text().strip()
        name = self.name_edit.text().strip()
        desc = self.desc_edit.text().strip()
        system = self.system_edit.toPlainText().strip()

        if not is_valid_id(pid):
            QMessageBox.warning(self, "Invalid id", "ID must be non-empty and contain only letters, numbers, _ or -.")
            return None
        if pid != self.original_id and pid in self.existing_ids:
            QMessageBox.warning(self, "Duplicate id", f"ID '{pid}' already exists.")
            return None
        if not name:
            QMessageBox.warning(self, "Missing name", "Name is required.")
            return None
        if not desc:
            QMessageBox.warning(self, "Missing description", "Description is required.")
            return None
        if not system:
            QMessageBox.warning(self, "Missing system prompt", "System prompt is required.")
            return None

        return PersonaItem(id=pid, name=name, description=desc, system=system)


class ActionEditDialog(QDialog):
    def __init__(self, parent: QWidget, title: str, existing_ids: List[str], item: Optional[ActionItem] = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(760, 620)

        self.existing_ids = set(existing_ids)
        self.original_id = item.id if item else ""

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.id_edit = QLineEdit(item.id if item else "")
        self.name_edit = QLineEdit(item.name if item else "")
        self.desc_edit = QLineEdit(item.description if item else "")

        self.instruction_edit = QTextEdit()
        self.instruction_edit.setPlainText(item.instruction if item else "")
        self.instruction_edit.setMinimumHeight(180)

        self.output_edit = QTextEdit()
        self.output_edit.setPlainText(item.output_format if item else "")
        self.output_edit.setMinimumHeight(120)

        form.addRow("id", self.id_edit)
        form.addRow("name", self.name_edit)
        form.addRow("description", self.desc_edit)
        form.addRow("instruction", self.instruction_edit)
        form.addRow("output_format", self.output_edit)

        layout.addLayout(form)

        btn_row = QHBoxLayout()
        self.btn_ok = QPushButton("Save")
        self.btn_cancel = QPushButton("Cancel")
        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(self.btn_ok)
        layout.addLayout(btn_row)

    def get_value(self) -> Optional[ActionItem]:
        aid = self.id_edit.text().strip()
        name = self.name_edit.text().strip()
        desc = self.desc_edit.text().strip()
        instruction = self.instruction_edit.toPlainText().strip()
        outfmt = self.output_edit.toPlainText().strip()

        if not is_valid_id(aid):
            QMessageBox.warning(self, "Invalid id", "ID must be non-empty and contain only letters, numbers, _ or -.")
            return None
        if aid != self.original_id and aid in self.existing_ids:
            QMessageBox.warning(self, "Duplicate id", f"ID '{aid}' already exists.")
            return None
        if not name:
            QMessageBox.warning(self, "Missing name", "Name is required.")
            return None
        if not desc:
            QMessageBox.warning(self, "Missing description", "Description is required.")
            return None
        if not instruction:
            QMessageBox.warning(self, "Missing instruction", "Instruction is required.")
            return None
        if not outfmt:
            QMessageBox.warning(self, "Missing output_format", "Output format is required.")
            return None

        return ActionItem(id=aid, name=name, description=desc, instruction=instruction, output_format=outfmt)


# ---------------------------
# Main Window
# ---------------------------

class JsonEditorWindow(QMainWindow):
    def __init__(self, personas_path: Path, actions_path: Path):
        super().__init__()
        self.setWindowTitle("SmartClipboard JSON Editor (Personas + Actions)")
        self.resize(1200, 720)

        self.personas_path = personas_path
        self.actions_path = actions_path

        self.personas_data: Dict[str, Any] = {}
        self.actions_data: List[Dict[str, Any]] = []

        self._build_ui()
        self.load_all()

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)

        # Left column: lists
        left = QWidget()
        left_layout = QVBoxLayout(left)

        # Personas
        left_layout.addWidget(QLabel("Personas"))
        self.persona_list = QListWidget()
        self.persona_list.currentItemChanged.connect(self._on_persona_selected)
        left_layout.addWidget(self.persona_list, 2)

        persona_btns = QHBoxLayout()
        self.btn_add_persona = QPushButton("Add")
        self.btn_edit_persona = QPushButton("Edit")
        self.btn_del_persona = QPushButton("Delete")
        self.btn_add_persona.clicked.connect(self.add_persona)
        self.btn_edit_persona.clicked.connect(self.edit_persona)
        self.btn_del_persona.clicked.connect(self.delete_persona)
        persona_btns.addWidget(self.btn_add_persona)
        persona_btns.addWidget(self.btn_edit_persona)
        persona_btns.addWidget(self.btn_del_persona)
        left_layout.addLayout(persona_btns)

        default_row = QHBoxLayout()
        default_row.addWidget(QLabel("Default persona"))
        self.default_persona_combo = QComboBox()
        self.default_persona_combo.currentIndexChanged.connect(self._on_default_persona_changed)
        default_row.addWidget(self.default_persona_combo, 1)
        left_layout.addLayout(default_row)

        # Actions
        left_layout.addWidget(QLabel("Actions"))
        self.action_list = QListWidget()
        self.action_list.currentItemChanged.connect(self._on_action_selected)
        left_layout.addWidget(self.action_list, 2)

        action_btns = QHBoxLayout()
        self.btn_add_action = QPushButton("Add")
        self.btn_edit_action = QPushButton("Edit")
        self.btn_del_action = QPushButton("Delete")
        self.btn_add_action.clicked.connect(self.add_action)
        self.btn_edit_action.clicked.connect(self.edit_action)
        self.btn_del_action.clicked.connect(self.delete_action)
        action_btns.addWidget(self.btn_add_action)
        action_btns.addWidget(self.btn_edit_action)
        action_btns.addWidget(self.btn_del_action)
        left_layout.addLayout(action_btns)

        layout.addWidget(left, 1)

        # Right column: preview + save
        right = QWidget()
        right_layout = QVBoxLayout(right)

        paths_row = QVBoxLayout()
        self.lbl_personas_path = QLabel(f"personas.json: {self.personas_path}")
        self.lbl_actions_path = QLabel(f"actions.json: {self.actions_path}")
        self.lbl_personas_path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lbl_actions_path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        paths_row.addWidget(self.lbl_personas_path)
        paths_row.addWidget(self.lbl_actions_path)
        right_layout.addLayout(paths_row)

        right_layout.addWidget(QLabel("Selected item preview (read-only JSON)"))
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        right_layout.addWidget(self.preview, 1)

        btn_row = QHBoxLayout()
        self.btn_reload = QPushButton("Reload from disk")
        self.btn_save = QPushButton("Save to disk (with backup)")
        self.btn_pick_files = QPushButton("Choose JSON files…")

        self.btn_reload.clicked.connect(self.load_all)
        self.btn_save.clicked.connect(self.save_all)
        self.btn_pick_files.clicked.connect(self.choose_files)

        btn_row.addWidget(self.btn_pick_files)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_reload)
        btn_row.addWidget(self.btn_save)
        right_layout.addLayout(btn_row)

        self.status = QLabel("")
        self.status.setStyleSheet("color: #bbbbbb;")
        right_layout.addWidget(self.status)

        layout.addWidget(right, 2)

    # ---------------------------
    # Load / Save
    # ---------------------------

    def load_all(self) -> None:
        try:
            self.personas_data = read_json(self.personas_path)
            self.actions_data = read_json(self.actions_path)
            if not isinstance(self.personas_data, dict) or "personas" not in self.personas_data:
                raise ValueError("personas.json must be an object with a 'personas' array.")
            if not isinstance(self.personas_data.get("personas"), list):
                raise ValueError("'personas' must be a list.")
            if not isinstance(self.actions_data, list):
                raise ValueError("actions.json must be a JSON array (list).")

            self._refresh_lists()
            self.status.setText("Loaded.")
        except Exception as e:
            QMessageBox.critical(self, "Load failed", str(e))

    def save_all(self) -> None:
        try:
            self._validate_all()

            p_bak = backup_file(self.personas_path)
            a_bak = backup_file(self.actions_path)

            write_json(self.personas_path, self.personas_data)
            write_json(self.actions_path, self.actions_data)

            self.status.setText(f"Saved. Backups: {p_bak.name}, {a_bak.name}")
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))

    def choose_files(self) -> None:
        p1, _ = QFileDialog.getOpenFileName(self, "Select personas.json", str(self.personas_path), "JSON (*.json)")
        if p1:
            self.personas_path = Path(p1)
        p2, _ = QFileDialog.getOpenFileName(self, "Select actions.json", str(self.actions_path), "JSON (*.json)")
        if p2:
            self.actions_path = Path(p2)

        self.lbl_personas_path.setText(f"personas.json: {self.personas_path}")
        self.lbl_actions_path.setText(f"actions.json: {self.actions_path}")
        self.load_all()

    # ---------------------------
    # Validation
    # ---------------------------

    def _validate_all(self) -> None:
        # Personas
        personas = self.personas_data.get("personas", [])
        if not isinstance(personas, list):
            raise ValueError("personas.json: 'personas' must be a list.")

        seen = set()
        for i, p in enumerate(personas):
            if not isinstance(p, dict):
                raise ValueError(f"personas.json: personas[{i}] must be an object.")
            for k in PERSONA_REQUIRED:
                if k not in p or not str(p.get(k, "")).strip():
                    raise ValueError(f"personas.json: personas[{i}] missing '{k}'.")
            pid = str(p["id"]).strip()
            if not is_valid_id(pid):
                raise ValueError(f"personas.json: invalid id '{pid}'.")
            if pid in seen:
                raise ValueError(f"personas.json: duplicate persona id '{pid}'.")
            seen.add(pid)

        # Default persona
        defaults = self.personas_data.get("defaults", {})
        if defaults and not isinstance(defaults, dict):
            raise ValueError("personas.json: 'defaults' must be an object.")
        default_id = (defaults.get("persona") if isinstance(defaults, dict) else None) or ""
        if default_id and default_id not in seen:
            raise ValueError(f"personas.json: defaults.persona '{default_id}' not found in personas.")

        # Actions
        actions = self.actions_data
        seen_a = set()
        for i, a in enumerate(actions):
            if not isinstance(a, dict):
                raise ValueError(f"actions.json: actions[{i}] must be an object.")
            for k in ACTION_REQUIRED:
                if k not in a or not str(a.get(k, "")).strip():
                    raise ValueError(f"actions.json: actions[{i}] missing '{k}'.")
            aid = str(a["id"]).strip()
            if not is_valid_id(aid):
                raise ValueError(f"actions.json: invalid id '{aid}'.")
            if aid in seen_a:
                raise ValueError(f"actions.json: duplicate action id '{aid}'.")
            seen_a.add(aid)

    # ---------------------------
    # List refresh + selection
    # ---------------------------

    def _refresh_lists(self) -> None:
        self.persona_list.blockSignals(True)
        self.action_list.blockSignals(True)
        self.default_persona_combo.blockSignals(True)

        self.persona_list.clear()
        self.action_list.clear()
        self.default_persona_combo.clear()

        personas = self.personas_data.get("personas", [])
        for p in personas:
            label = f"{p.get('name','')}  ({p.get('id','')})"
            it = QListWidgetItem(label)
            it.setData(Qt.UserRole, p.get("id", ""))
            self.persona_list.addItem(it)
            self.default_persona_combo.addItem(label, p.get("id", ""))

        actions = self.actions_data
        for a in actions:
            label = f"{a.get('name','')}  ({a.get('id','')})"
            it = QListWidgetItem(label)
            it.setData(Qt.UserRole, a.get("id", ""))
            self.action_list.addItem(it)

        # Default persona selection
        default_id = ""
        defaults = self.personas_data.get("defaults", {})
        if isinstance(defaults, dict):
            default_id = str(defaults.get("persona", "") or "")
        if default_id:
            for i in range(self.default_persona_combo.count()):
                if self.default_persona_combo.itemData(i) == default_id:
                    self.default_persona_combo.setCurrentIndex(i)
                    break

        self.persona_list.blockSignals(False)
        self.action_list.blockSignals(False)
        self.default_persona_combo.blockSignals(False)

        self.preview.setPlainText("")

    def _on_persona_selected(self) -> None:
        it = self.persona_list.currentItem()
        if not it:
            self.preview.setPlainText("")
            return
        pid = it.data(Qt.UserRole)
        p = self._find_persona(pid)
        self.preview.setPlainText(json.dumps(p, indent=2, ensure_ascii=False))

    def _on_action_selected(self) -> None:
        it = self.action_list.currentItem()
        if not it:
            self.preview.setPlainText("")
            return
        aid = it.data(Qt.UserRole)
        a = self._find_action(aid)
        self.preview.setPlainText(json.dumps(a, indent=2, ensure_ascii=False))

    def _on_default_persona_changed(self) -> None:
        pid = self.default_persona_combo.currentData()
        if not pid:
            return
        defaults = self.personas_data.get("defaults")
        if not isinstance(defaults, dict):
            self.personas_data["defaults"] = {}
        self.personas_data["defaults"]["persona"] = pid
        self.status.setText(f"Default persona set to: {pid}")

    # ---------------------------
    # Finders
    # ---------------------------

    def _find_persona(self, pid: str) -> Dict[str, Any]:
        for p in self.personas_data.get("personas", []):
            if p.get("id") == pid:
                return p
        return {}

    def _find_action(self, aid: str) -> Dict[str, Any]:
        for a in self.actions_data:
            if a.get("id") == aid:
                return a
        return {}

    def _persona_ids(self) -> List[str]:
        return [str(p.get("id", "")).strip() for p in self.personas_data.get("personas", []) if isinstance(p, dict)]

    def _action_ids(self) -> List[str]:
        return [str(a.get("id", "")).strip() for a in self.actions_data if isinstance(a, dict)]

    # ---------------------------
    # Persona operations
    # ---------------------------

    def add_persona(self) -> None:
        dlg = PersonaEditDialog(self, "Add persona", existing_ids=self._persona_ids(), item=None)
        while dlg.exec() == QDialog.Accepted:
            item = dlg.get_value()
            if item is None:
                continue
            self.personas_data["personas"].append({
                "id": item.id,
                "name": item.name,
                "description": item.description,
                "system": item.system,
            })
            self._refresh_lists()
            self.status.setText(f"Added persona: {item.id}")
            return

    def edit_persona(self) -> None:
        it = self.persona_list.currentItem()
        if not it:
            return
        pid = it.data(Qt.UserRole)
        p = self._find_persona(pid)
        if not p:
            return

        item = PersonaItem(
            id=str(p.get("id","")),
            name=str(p.get("name","")),
            description=str(p.get("description","")),
            system=str(p.get("system","")),
        )
        dlg = PersonaEditDialog(self, "Edit persona", existing_ids=self._persona_ids(), item=item)
        while dlg.exec() == QDialog.Accepted:
            new_item = dlg.get_value()
            if new_item is None:
                continue

            # Update in list
            for idx, obj in enumerate(self.personas_data.get("personas", [])):
                if obj.get("id") == pid:
                    obj["id"] = new_item.id
                    obj["name"] = new_item.name
                    obj["description"] = new_item.description
                    obj["system"] = new_item.system
                    break

            # If default persona referenced old id, update it
            defaults = self.personas_data.get("defaults", {})
            if isinstance(defaults, dict) and defaults.get("persona") == pid:
                defaults["persona"] = new_item.id

            self._refresh_lists()
            self.status.setText(f"Updated persona: {new_item.id}")
            return

    def delete_persona(self) -> None:
        it = self.persona_list.currentItem()
        if not it:
            return
        pid = it.data(Qt.UserRole)

        defaults = self.personas_data.get("defaults", {})
        default_id = defaults.get("persona") if isinstance(defaults, dict) else ""
        if pid == default_id:
            QMessageBox.warning(self, "Cannot delete", "This persona is currently set as the default. Change default first.")
            return

        if QMessageBox.question(self, "Delete persona", f"Delete persona '{pid}'?") != QMessageBox.Yes:
            return

        personas = self.personas_data.get("personas", [])
        self.personas_data["personas"] = [p for p in personas if p.get("id") != pid]
        self._refresh_lists()
        self.status.setText(f"Deleted persona: {pid}")

    # ---------------------------
    # Action operations
    # ---------------------------

    def add_action(self) -> None:
        dlg = ActionEditDialog(self, "Add action", existing_ids=self._action_ids(), item=None)
        while dlg.exec() == QDialog.Accepted:
            item = dlg.get_value()
            if item is None:
                continue
            self.actions_data.append({
                "id": item.id,
                "name": item.name,
                "description": item.description,
                "instruction": item.instruction,
                "output_format": item.output_format,
            })
            self._refresh_lists()
            self.status.setText(f"Added action: {item.id}")
            return

    def edit_action(self) -> None:
        it = self.action_list.currentItem()
        if not it:
            return
        aid = it.data(Qt.UserRole)
        a = self._find_action(aid)
        if not a:
            return

        item = ActionItem(
            id=str(a.get("id","")),
            name=str(a.get("name","")),
            description=str(a.get("description","")),
            instruction=str(a.get("instruction","")),
            output_format=str(a.get("output_format","")),
        )
        dlg = ActionEditDialog(self, "Edit action", existing_ids=self._action_ids(), item=item)
        while dlg.exec() == QDialog.Accepted:
            new_item = dlg.get_value()
            if new_item is None:
                continue

            for obj in self.actions_data:
                if obj.get("id") == aid:
                    obj["id"] = new_item.id
                    obj["name"] = new_item.name
                    obj["description"] = new_item.description
                    obj["instruction"] = new_item.instruction
                    obj["output_format"] = new_item.output_format
                    break

            self._refresh_lists()
            self.status.setText(f"Updated action: {new_item.id}")
            return

    def delete_action(self) -> None:
        it = self.action_list.currentItem()
        if not it:
            return
        aid = it.data(Qt.UserRole)

        if QMessageBox.question(self, "Delete action", f"Delete action '{aid}'?") != QMessageBox.Yes:
            return

        self.actions_data = [a for a in self.actions_data if a.get("id") != aid]
        self._refresh_lists()
        self.status.setText(f"Deleted action: {aid}")


def resolve_default_paths() -> Tuple[Path, Path]:
    """
    Looks for ../config/personas.json and ../config/actions.json relative to this file.
    Falls back to current working directory's config/.
    """
    here = Path(__file__).resolve()
    # tools/json_editor.py -> project_root/tools/json_editor.py
    project_root = here.parent.parent
    p1 = project_root / "config" / "personas.json"
    p2 = project_root / "config" / "actions.json"
    if p1.exists() and p2.exists():
        return p1, p2

    cwd = Path.cwd()
    p1 = cwd / "config" / "personas.json"
    p2 = cwd / "config" / "actions.json"
    return p1, p2


def main() -> int:
    personas_path, actions_path = resolve_default_paths()
    app = QApplication([])
    win = JsonEditorWindow(personas_path=personas_path, actions_path=actions_path)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

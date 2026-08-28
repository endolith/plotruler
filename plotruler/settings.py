"""Settings dialog for capturing a new global hotkey.

A small modal dialog that lets the user press a key combination and
records it. The overlay is a frameless custom window, but this dialog is
a conventional temporary window — it only exists to capture input, then
closes, so a native widget is appropriate here.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout

from .hotkey import KeyCombo, qkey_to_vk, qmodifiers_to_names

# Keys that should not be treated as the shortcut by themselves.
_MODIFIER_KEYS = {
    Qt.Key.Key_Control,
    Qt.Key.Key_Shift,
    Qt.Key.Key_Alt,
    Qt.Key.Key_Meta,
    Qt.Key.Key_Super_L,
    Qt.Key.Key_Super_R,
    Qt.Key.Key_unknown,
}


class HotkeyDialog(QDialog):
    """A dialog that captures the next key combination the user presses."""

    def __init__(self, current=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set Global Hotkey")
        self.setModal(False)
        self._combo = None

        layout = QVBoxLayout(self)
        self._prompt = QLabel(
            "Press a key combination (e.g. Win+Alt+P)\n\n"
            "include a modifier key plus a letter. "
            "Esc to cancel."
        )
        self._prompt.setWordWrap(True)
        layout.addWidget(self._prompt)

        self._combo_label = QLabel(self._describe(current))
        self._combo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._combo_label.setStyleSheet(
            "font-size: 16px; font-weight: bold; padding: 12px;"
        )
        layout.addWidget(self._combo_label)

        if current is not None:
            self._combo = current

        buttons = QVBoxLayout()
        use_btn = QPushButton("Use This Key")
        use_btn.clicked.connect(self._use_current)
        buttons.addWidget(use_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(cancel_btn)
        layout.addLayout(buttons)

    def _describe(self, combo):
        return combo.text() if combo is not None else "— none —"

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key.Key_Escape, Qt.Key.Key_Cancel):
            self.reject()
            return
        if key in _MODIFIER_KEYS:
            # A bare modifier isn't a shortcut; keep waiting.
            return
        vk = qkey_to_vk(key)
        if vk == 0:
            self._show_hint("That key isn't supported")
            return
        modifiers = qmodifiers_to_names(event.modifiers())
        if not modifiers:
            self._show_hint("Include a modifier key (Ctrl, Alt, or Win)")
            return
        self._combo = KeyCombo(modifiers, self._key_name(key), vk)
        self._combo_label.setText(self._describe(self._combo))

    def _show_hint(self, text):
        self._prompt.setText(text)
        self._prompt.setStyleSheet("color: #c0392b;")

    def _key_name(self, key):
        """Return a readable name for a Qt key."""
        # Qt.Key.Key_A .. Key_Z have the same value as their ASCII letter.
        if 0x41 <= key <= 0x5A:
            return chr(key)
        if 0x30 <= key <= 0x39:
            return chr(key)
        names = {
            Qt.Key.Key_Space: "Space",
            Qt.Key.Key_Tab: "Tab",
            Qt.Key.Key_Left: "Left",
            Qt.Key.Key_Right: "Right",
            Qt.Key.Key_Up: "Up",
            Qt.Key.Key_Down: "Down",
            Qt.Key.Key_Home: "Home",
            Qt.Key.Key_End: "End",
            Qt.Key.Key_PageUp: "Page Up",
            Qt.Key.Key_PageDown: "Page Down",
            Qt.Key.Key_Insert: "Insert",
            Qt.Key.Key_Delete: "Delete",
            Qt.Key.Key_F1: "F1",
            Qt.Key.Key_F2: "F2",
            Qt.Key.Key_F3: "F3",
            Qt.Key.Key_F4: "F4",
            Qt.Key.Key_F5: "F5",
            Qt.Key.Key_F6: "F6",
            Qt.Key.Key_F7: "F7",
            Qt.Key.Key_F8: "F8",
            Qt.Key.Key_F9: "F9",
            Qt.Key.Key_F10: "F10",
            Qt.Key.Key_F11: "F11",
            Qt.Key.Key_F12: "F12",
        }
        return names.get(key, "Key")

    def _use_current(self):
        if self._combo is not None:
            self.accept()

    def combo(self):
        """Return the recorded KeyCombo, or None."""
        return self._combo

"""Resize handling for the frameless overlay window.

A frameless window has no native resize border, so we implement it
ourselves: a thin invisible hit zone along each edge and corner, a
matching resize cursor, and manual geometry updates while dragging.
"""

from PySide6.QtCore import QRect, Qt

# How thick the invisible edge hit zones are, in pixels.
_EDGE = 8
# Minimum window size, in pixels.
_MIN_W = 320
_MIN_H = 200


def _cursor_for(edge):
    """Return the resize cursor appropriate for a hit-zone edge."""
    if edge in ("n", "s"):
        return Qt.CursorShape.SizeVerCursor
    if edge in ("e", "w"):
        return Qt.CursorShape.SizeHorCursor
    if edge in ("nw", "se"):
        return Qt.CursorShape.SizeFDiagCursor
    if edge in ("ne", "sw"):
        return Qt.CursorShape.SizeBDiagCursor
    return Qt.CursorShape.ArrowCursor


def _edge_at(pos, size):
    """Classify a local point as an edge name, corner name, or None.

    Corners take precedence so the diagonal cursor shows in them.
    """
    x, y = pos.x(), pos.y()
    w, h = size.width(), size.height()
    left = x < _EDGE
    right = x >= w - _EDGE
    top = y < _EDGE
    bottom = y >= h - _EDGE
    if left and top:
        return "nw"
    if right and top:
        return "ne"
    if left and bottom:
        return "sw"
    if right and bottom:
        return "se"
    if left:
        return "w"
    if right:
        return "e"
    if top:
        return "n"
    if bottom:
        return "s"
    return None


class Resizer:
    """Attaches edge/corner resize behavior to a frameless window."""

    def __init__(self, window):
        self.window = window
        self._edge = None
        self._start_geometry = None
        self._start_global = None

    def on_mouse_move(self, event):
        pos = event.position().toPoint()
        if self._edge is None:
            edge = _edge_at(pos, self.window.size())
            if edge is not None and not self.window.titlebar_under(pos):
                self.window.setCursor(_cursor_for(edge))
            else:
                self.window.unsetCursor()
            return
        # Dragging.
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._apply_drag(event.globalPosition().toPoint())

    def on_mouse_press(self, event):
        pos = event.position().toPoint()
        if self.window.titlebar_under(pos):
            return
        edge = _edge_at(pos, self.window.size())
        if edge is not None:
            self._edge = edge
            self._start_geometry = self.window.geometry()
            self._start_global = event.globalPosition().toPoint()

    def on_mouse_release(self, event):
        self._edge = None
        self.window.unsetCursor()

    def _apply_drag(self, global_pos):
        delta = global_pos - self._start_global
        geo = QRect(self._start_geometry)
        x, y, w, h = geo.x(), geo.y(), geo.width(), geo.height()
        edge = self._edge
        if "n" in edge:
            h = max(_MIN_H, h - delta.y())
            y = geo.y() + (geo.height() - h)
        if "s" in edge:
            h = max(_MIN_H, h + delta.y())
        if "w" in edge:
            w = max(_MIN_W, w - delta.x())
            x = geo.x() + (geo.width() - w)
        if "e" in edge:
            w = max(_MIN_W, w + delta.x())
        self.window.setGeometry(x, y, w, h)

"""Selectable QPdfView for Debian 13 / Qt PDF 6.8.

Qt's QWidget QPdfView does not implement drag-to-select text, so this class
adds *temporary* blue selection overlays over actual selectable PDF text.
No PDF annotations or document changes are written.

Page layout follows Qt 6.8's public QPdfView geometry algorithm. Geometry is
cached and only recomputed when view/document/zoom state changes.
"""
from bisect import bisect_right

from PySide6.QtCore import QPointF, QRect, QRectF, QSizeF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QKeySequence
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import QApplication, QMenu


class SelectablePdfView(QPdfView):
    selection_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selection = None
        self._selection_page = -1
        self._dragging = False
        self._start_point = None
        self._page_layout_key = None
        self._geometries = {}  # page -> (QRect in document pixels, pixels/point)
        self._page_starts = []
        self.setFocusPolicy(Qt.StrongFocus)

    def clear_selection(self):
        self._dragging = False
        self._selection = None
        self._selection_page = -1
        self._start_point = None
        self.selection_changed.emit(False)
        self.viewport().update()

    def reset_document_state(self):
        self.clear_selection()
        self._page_layout_key = None
        self._geometries.clear()
        self._page_starts.clear()

    def selected_text(self):
        if self._selection is not None and self._selection.isValid():
            return self._selection.text()
        return ''

    def copy_selected_text(self):
        text = self.selected_text()
        if text:
            QApplication.clipboard().setText(text)
            return True
        return False

    def _update_page_layout(self):
        doc = self.document()
        if not doc or doc.status() != QPdfDocument.Status.Ready:
            self._geometries.clear()
            self._page_starts.clear()
            self._page_layout_key = None
            return

        margins = self.documentMargins()
        mode = self.zoomMode()
        width = self.viewport().width()
        height = self.viewport().height()
        pages = doc.pageCount()
        current = self.pageNavigator().currentPage()
        key = (id(doc), pages, width, height, margins.left(), margins.right(),
               margins.top(), margins.bottom(), self.pageSpacing(), mode,
               round(self.zoomFactor(), 6), self.pageMode(),
               current if self.pageMode() == QPdfView.PageMode.SinglePage else -1)
        if self._page_layout_key == key:
            return
        self._page_layout_key = key

        resolution = QApplication.primaryScreen().logicalDotsPerInch() / 72.0
        first = current if self.pageMode() == QPdfView.PageMode.SinglePage else 0
        last = first + 1 if self.pageMode() == QPdfView.PageMode.SinglePage else pages
        sizes = []
        total_width = 0
        for page in range(first, last):
            point_size = doc.pagePointSize(page)
            original_width = max(1, round(point_size.width() * resolution))
            original_height = max(1, round(point_size.height() * resolution))
            if mode == QPdfView.ZoomMode.FitToWidth:
                factor = max(0.01, (width - margins.left() - margins.right()) / original_width)
                pixel_width = round(original_width * factor)
                pixel_height = round(original_height * factor)
                scale = resolution * factor
            elif mode == QPdfView.ZoomMode.FitInView:
                available_width = max(1, width - margins.left() - margins.right())
                available_height = max(1, height - margins.top() - self.pageSpacing())
                factor = min(available_width / original_width, available_height / original_height)
                pixel_width = round(original_width * factor)
                pixel_height = round(original_height * factor)
                scale = resolution * factor
            else:
                scale = resolution * self.zoomFactor()
                pixel_width = round(point_size.width() * scale)
                pixel_height = round(point_size.height() * scale)
            pixel_width = max(1, pixel_width)
            pixel_height = max(1, pixel_height)
            sizes.append((page, pixel_width, pixel_height, scale))
            total_width = max(total_width, pixel_width)

        total_width += margins.left() + margins.right()
        page_y = margins.top()
        self._geometries.clear()
        self._page_starts.clear()
        for page, page_width, page_height, scale in sizes:
            x = (max(total_width, width) - page_width) // 2
            self._geometries[page] = (QRect(x, page_y, page_width, page_height), scale)
            self._page_starts.append((page_y, page))
            page_y += page_height + self.pageSpacing()

    def _page_at(self, viewport_pos, preferred=None):
        """Convert a viewport mouse position into (page, PDF-point position)."""
        self._update_page_layout()
        pos = QPointF(viewport_pos) + QPointF(
            self.horizontalScrollBar().value(), self.verticalScrollBar().value())
        if preferred is not None:
            entry = self._geometries.get(preferred)
            if not entry:
                return None
            rect, scale = entry
            # Clamp a drag beyond the page edge instead of jumping pages.
            x = max(0.0, min(pos.x() - rect.left(), float(rect.width())))
            y = max(0.0, min(pos.y() - rect.top(), float(rect.height())))
            return preferred, QPointF(x / scale, y / scale)
        if not self._page_starts:
            return None
        index = bisect_right(self._page_starts, (pos.y(), float('inf'))) - 1
        if index < 0:
            return None
        page = self._page_starts[index][1]
        rect, scale = self._geometries[page]
        if not rect.contains(pos.toPoint()):
            return None
        return page, QPointF((pos.x() - rect.left()) / scale,
                             (pos.y() - rect.top()) / scale)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clear_selection()
            page_point = self._page_at(event.position())
            if page_point is not None:
                self._selection_page, self._start_point = page_point
                self._dragging = True
                self.setFocus()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging and self._selection_page >= 0:
            at = self._page_at(event.position(), preferred=self._selection_page)
            if at is not None:
                _, end = at
                self._selection = self.document().getSelection(
                    self._selection_page, self._start_point, end)
                self.selection_changed.emit(bool(self.selected_text()))
                self.viewport().update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._dragging:
            self.mouseMoveEvent(event)
            self._dragging = False
            if not self.selected_text():
                # Keep Qt PDF link-click handling when no text was selected.
                super().mouseReleaseEvent(event)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Copy) or (
                event.key() == Qt.Key_C and event.modifiers() & Qt.ControlModifier):
            if self.copy_selected_text():
                event.accept()
                return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        action = menu.addAction('Copy selected text')
        action.setEnabled(bool(self.selected_text()))
        chosen = menu.exec(event.globalPos())
        if chosen == action:
            self.copy_selected_text()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.selected_text():
            return
        self._update_page_layout()
        entry = self._geometries.get(self._selection_page)
        if entry is None:
            return
        rect, scale = entry
        offset_x = rect.x() - self.horizontalScrollBar().value()
        offset_y = rect.y() - self.verticalScrollBar().value()
        painter = QPainter(self.viewport())
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(52, 128, 238, 104))  # temporary blue selection
        for polygon in self._selection.bounds():
            bounds = polygon.boundingRect()
            painter.drawRect(QRectF(offset_x + bounds.x() * scale,
                                    offset_y + bounds.y() * scale,
                                    bounds.width() * scale,
                                    bounds.height() * scale))
        painter.end()

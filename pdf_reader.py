"""In-app PDF reader using Qt PDF, without a browser or external viewer.

Imported only when a PDF is opened; it reads source files at their original
location and doesn't create a persistent or temporary copy.
"""
from pathlib import Path

from pdf_selection import SelectablePdfView

from PySide6.QtCore import QEvent, QPointF, QTimer, Qt, Signal, Slot
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import (
    QAbstractSpinBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox,
    QPushButton, QSlider, QSpinBox, QToolButton, QVBoxLayout, QWidget,
)


class PageNumberSpin(QSpinBox):
    """Editable page field with explicit, reversed page-navigation arrows.

    The upper arrow navigates toward page 1; the lower arrow toward the last
    page. The arrow keys and wheel use the same directions. This deliberately
    differs from QSpinBox's normal numeric stepping.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('pdfPageSpin')
        self.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.setKeyboardTracking(False)  # Allow replacing 1 with e.g. 150 before jumping.
        self.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.setMinimumWidth(96)
        self.setFixedHeight(38)
        self.lineEdit().setTextMargins(0, 0, 26, 0)
        self.setStyleSheet("""
            QSpinBox#pdfPageSpin {
                background: #312824; color: #fff2df;
                border: 1px solid #806347; border-radius: 6px;
                padding: 3px 4px 3px 10px; font-size: 13px;
            }
            QToolButton#pdfPageUp, QToolButton#pdfPageDown {
                background: #534035; color: #f3ddc0;
                border: 0; border-radius: 2px;
                font-size: 10px; font-weight: 700; padding: 0;
            }
            QToolButton#pdfPageUp:hover, QToolButton#pdfPageDown:hover {
                background: #795a40;
            }
            QToolButton#pdfPageUp:disabled, QToolButton#pdfPageDown:disabled {
                background: #3b322d; color: #756558;
            }
        """)

        self.decrease_button = QToolButton(self)
        self.decrease_button.setObjectName('pdfPageUp')
        self.decrease_button.setText('▲')
        self.decrease_button.setToolTip('Previous page (decrease page number)')
        self.decrease_button.setAccessibleName('Decrease page number')
        self.decrease_button.clicked.connect(lambda: self.setValue(self.value() - 1))

        self.increase_button = QToolButton(self)
        self.increase_button.setObjectName('pdfPageDown')
        self.increase_button.setText('▼')
        self.increase_button.setToolTip('Next page (increase page number)')
        self.increase_button.setAccessibleName('Increase page number')
        self.increase_button.clicked.connect(lambda: self.setValue(self.value() + 1))

        self.valueChanged.connect(self.refresh_arrows)
        self.refresh_arrows()

    def stepBy(self, steps):
        # Reverse keyboard Up/Down and mouse wheel, too.
        super().stepBy(-steps)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        button_width = 21
        x = self.width() - button_width - 4
        half = (self.height() - 6) // 2
        self.decrease_button.setGeometry(x, 3, button_width, half)
        self.increase_button.setGeometry(x, 3 + half, button_width, half)

    def refresh_arrows(self, *_args):
        self.decrease_button.setEnabled(self.isEnabled() and self.value() > self.minimum())
        self.increase_button.setEnabled(self.isEnabled() and self.value() < self.maximum())


class PdfReader(QWidget):
    back_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.source_path = None
        self._source_note = None
        self._last_error_shown = False
        self._password_prompt_open = False
        self._password_attempts = 0
        self._zoom = 1.0

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(10)

        top = QHBoxLayout()
        self.back_button = QPushButton('← Back to bookshelf')
        self.back_button.clicked.connect(self.back_requested.emit)
        top.addWidget(self.back_button)
        self.filename = QLabel('')
        self.filename.setObjectName('readerFilename')
        self.filename.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.filename.setToolTip('')
        top.addWidget(self.filename, 1)
        root.addLayout(top)

        controls = QHBoxLayout()
        self.page_spin = PageNumberSpin()
        self.page_spin.setMinimum(1)
        self.page_spin.setMaximum(1)
        self.page_spin.setToolTip('Go to page')
        controls.addWidget(self.page_spin)
        self.page_total = QLabel('of 0')
        controls.addWidget(self.page_total)
        controls.addStretch()
        self.zoom_out = QPushButton('−')
        self.zoom_out.setToolTip('Zoom out')
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(25, 400)
        self.zoom_slider.setSingleStep(5)
        self.zoom_slider.setPageStep(25)
        self.zoom_slider.setValue(100)
        self.zoom_slider.setFixedWidth(150)
        self.zoom_slider.setToolTip('Zoom: 25% to 400%')
        self.zoom_label = QLabel('100%')
        self.zoom_label.setMinimumWidth(48)
        self.zoom_in = QPushButton('+')
        self.zoom_in.setToolTip('Zoom in')
        self.fit_width = QPushButton('Fit width')
        self.copy_button = QPushButton('Copy text')
        self.copy_button.setToolTip('Select PDF text with the mouse and copy it (Ctrl+C)')
        controls.addWidget(self.zoom_out)
        controls.addWidget(self.zoom_slider)
        controls.addWidget(self.zoom_label)
        controls.addWidget(self.zoom_in)
        controls.addWidget(self.fit_width)
        controls.addWidget(self.copy_button)
        root.addLayout(controls)

        self.view = SelectablePdfView(self)
        self.view.setPageMode(QPdfView.PageMode.MultiPage)
        self.view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        self.document = QPdfDocument(self)
        self.view.setDocument(self.document)
        self.view.viewport().installEventFilter(self)
        root.addWidget(self.view, 1)

        self.info = QLabel('')
        self.info.setObjectName('readerInfo')
        root.addWidget(self.info)

        self.navigator = self.view.pageNavigator()
        self.navigator.currentPageChanged.connect(self._current_page_changed)
        self.document.pageCountChanged.connect(self._page_count_changed)
        self.document.statusChanged.connect(self._status_changed)
        self.document.passwordRequired.connect(self._request_password)

        self.page_spin.valueChanged.connect(self._go_to_page)
        self.zoom_in.clicked.connect(lambda: self._change_zoom(1.25))
        self.zoom_out.clicked.connect(lambda: self._change_zoom(0.8))
        self.fit_width.clicked.connect(self._fit_to_width)
        self.zoom_slider.valueChanged.connect(self._slider_zoom_changed)
        self.view.selection_changed.connect(self.copy_button.setEnabled)
        self.copy_button.clicked.connect(self.view.copy_selected_text)
        self.view.zoomFactorChanged.connect(lambda _value: self._sync_zoom_slider())
        self.view.zoomModeChanged.connect(lambda _value: self._sync_zoom_slider())
        self._update_controls()

    def open_file(self, path: str, display_name: str | None = None,
                  source_note: str | None = None) -> bool:
        """Return False if the source is unavailable before attempting load."""
        self.close_file()
        if not Path(path).is_file():
            return False
        self.source_path = path
        self._source_note = source_note
        self.filename.setText(display_name or Path(path).name)
        self.filename.setToolTip(display_name or path)
        self.info.setText('Opening preview from RAM…' if source_note else 'Opening PDF directly from disc…')
        self._last_error_shown = False
        self._password_attempts = 0
        self.document.setPassword('')
        self.navigator.clear()
        self.view.reset_document_state()
        self._fit_to_width()
        self.document.load(path)
        # Status can already be Ready for a small, locally available PDF.
        self._status_changed(self.document.status())
        return True

    def close_file(self):
        """Release the optical file when returning to the shelf / ejecting."""
        self.source_path = None
        self._source_note = None
        self.view.reset_document_state()
        self.document.close()
        self.document.setPassword('')
        self.navigator.clear()
        self.filename.setText('')
        self.info.setText('')
        self._last_error_shown = False
        self._password_attempts = 0
        self._update_controls()

    @Slot(object)
    def _status_changed(self, status):
        if not self.source_path:
            return
        if status == QPdfDocument.Status.Ready:
            pages = self.document.pageCount()
            self.info.setText(f'{pages:,} page' + ('s' if pages != 1 else '') +
                              ' • ' + (self._source_note or 'reading directly from disc'))
            self._update_controls()
            QTimer.singleShot(0, self._sync_zoom_slider)
        elif status == QPdfDocument.Status.Loading:
            self.info.setText('Loading PDF…')
        elif status == QPdfDocument.Status.Error:
            # A passwordRequired signal can immediately follow the Error state.
            QTimer.singleShot(0, self._show_load_error)

    def _show_load_error(self):
        if self.source_path is None or self.document.status() != QPdfDocument.Status.Error:
            return
        if self._password_prompt_open or self._last_error_shown:
            return
        if self.document.error() == QPdfDocument.Error.IncorrectPassword and self._password_attempts == 0:
            # Give passwordRequired the opportunity to open its dialog first.
            return
        self._last_error_shown = True
        errors = {
            QPdfDocument.Error.FileNotFound: 'The document is no longer accessible. Is the disc still inserted?',
            QPdfDocument.Error.InvalidFileFormat: 'This file is not a valid or supported PDF.',
            QPdfDocument.Error.IncorrectPassword: 'The PDF password was not accepted.',
            QPdfDocument.Error.UnsupportedSecurityScheme: 'This PDF uses encryption that Qt PDF cannot open.',
        }
        message = errors.get(self.document.error(), 'The PDF could not be opened.')
        self.info.setText(message)
        QMessageBox.warning(self, 'Unable to read PDF', message)

    @Slot()
    def _request_password(self):
        if not self.source_path or self._password_prompt_open:
            return
        self._password_prompt_open = True
        try:
            if self._password_attempts >= 3:
                QMessageBox.warning(self, 'Unable to read PDF', 'Too many incorrect password attempts.')
                self._last_error_shown = True
                return
            pwd, ok = QInputDialog.getText(
                self, 'Protected PDF', 'Enter the document password:', QLineEdit.EchoMode.Password
            )
            if not ok:
                self.info.setText('Password entry cancelled.')
                self._last_error_shown = True
                return
            self._password_attempts += 1
            self.document.setPassword(pwd)
            self._last_error_shown = False
            self.document.load(self.source_path)
        finally:
            self._password_prompt_open = False

    @Slot(int)
    def _page_count_changed(self, _count):
        self._update_controls()

    @Slot(int)
    def _current_page_changed(self, page):
        self.page_spin.blockSignals(True)
        self.page_spin.setValue(max(1, page + 1))
        self.page_spin.blockSignals(False)
        self._update_controls()

    def _update_controls(self):
        pages = self.document.pageCount()
        ready = self.source_path is not None and self.document.status() == QPdfDocument.Status.Ready and pages > 0
        current = self.navigator.currentPage() if ready else 0
        self.page_spin.blockSignals(True)
        self.page_spin.setRange(1, max(1, pages))
        self.page_spin.setValue(min(max(1, current + 1), max(1, pages)))
        self.page_spin.blockSignals(False)
        self.page_total.setText(f'of {pages:,}')
        self.page_spin.setEnabled(ready)
        self.page_spin.refresh_arrows()
        self.zoom_in.setEnabled(ready)
        self.zoom_out.setEnabled(ready)
        self.fit_width.setEnabled(ready)
        self.zoom_slider.setEnabled(ready)
        self.copy_button.setEnabled(ready and bool(self.view.selected_text()))

    def _go_to_page(self, one_based_page):
        if self.document.status() != QPdfDocument.Status.Ready:
            return
        zero_based_page = one_based_page - 1
        if 0 <= zero_based_page < self.document.pageCount():
            self.navigator.jump(zero_based_page, QPointF(0, 0))

    def _effective_fit_zoom(self) -> float:
        if self.document.status() != QPdfDocument.Status.Ready or not self.document.pageCount():
            return 1.0
        page = max(0, self.navigator.currentPage())
        point_width = self.document.pagePointSize(page).width()
        screen = self.view.screen()
        dpi_scale = (screen.logicalDotsPerInch() if screen else 96.0) / 72.0
        margins = self.view.documentMargins()
        usable = max(1, self.view.viewport().width() - margins.left() - margins.right())
        return usable / max(1, point_width * dpi_scale)

    def _sync_zoom_slider(self):
        if self.view.zoomMode() == QPdfView.ZoomMode.FitToWidth:
            factor = self._effective_fit_zoom()
        else:
            factor = self.view.zoomFactor()
        percent = max(25, min(400, round(factor * 100)))
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(percent)
        self.zoom_slider.blockSignals(False)
        if self.view.zoomMode() == QPdfView.ZoomMode.FitToWidth:
            self.zoom_label.setText(f'{round(factor * 100)}%')
            self.zoom_label.setToolTip('Automatic fit-to-width zoom')
        else:
            self.zoom_label.setText(f'{percent}%')
            self.zoom_label.setToolTip('Custom zoom')

    def _fit_to_width(self):
        self.view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        QTimer.singleShot(0, self._sync_zoom_slider)

    def _slider_zoom_changed(self, percent):
        self._zoom = percent / 100.0
        self.view.setZoomMode(QPdfView.ZoomMode.Custom)
        self.view.setZoomFactor(self._zoom)
        self.zoom_label.setText(f'{percent}%')

    def _change_zoom(self, multiplier):
        if self.document.status() != QPdfDocument.Status.Ready:
            return
        if self.view.zoomMode() == QPdfView.ZoomMode.FitToWidth:
            current = self._effective_fit_zoom()
        else:
            current = self.view.zoomFactor()
        self.zoom_slider.setValue(max(25, min(400, round(current * multiplier * 100))))

    def eventFilter(self, watched, event):
        if watched == self.view.viewport() and event.type() == QEvent.Resize:
            if self.view.zoomMode() == QPdfView.ZoomMode.FitToWidth:
                QTimer.singleShot(0, self._sync_zoom_slider)
        return super().eventFilter(watched, event)

"""Independent, rearrangeable host for QGIS dock panels and attribute windows."""
from qgis.PyQt.QtCore import Qt, QTimer, QByteArray, QSettings
import re
import json
import base64
from qgis.PyQt.QtWidgets import (
    QMainWindow, QDockWidget, QDialog, QVBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QDialogButtonBox, QWidget,
    QPushButton, QMessageBox, QComboBox, QToolBar, QTabWidget,
    QApplication, QCheckBox, QHBoxLayout, QInputDialog,
)


def dock_area(name):
    return getattr(Qt.DockWidgetArea, name)


def orientation(name):
    return getattr(Qt.Orientation, name)


def is_attribute_dock(dock):
    """Recognize QGIS table/form docks, independent of dock/floating status."""
    title = dock.windowTitle()
    # Localized titles: 'layer — Objekter Totalt antal: ...' or English 'Features Total: ...'
    if re.search(r'(?:Objekter\s+Totalt\s+antal|Features?\s+Total|Features?\s+count)',
                 title, re.IGNORECASE):
        return True
    # Not all QGIS builds expose the same dock subclass; inspect embedded widgets.
    for child in dock.findChildren(QWidget):
        try:
            classname = child.metaObject().className()
        except RuntimeError:
            continue
        if classname in ('QgsAttributeTableDialog', 'QgsAttributeDialog',
                         'QgsAttributeTableView', 'QgsAttributeForm'):
            return True
    return False


def belongs_to_main_window(dock, main):
    """Include detached floating QDockWidgets even when not direct children."""
    if dock is main or not isinstance(dock, QDockWidget):
        return False
    node = dock.parentWidget()
    while node is not None:
        if node is main:
            return True
        node = node.parentWidget()
    return False


class SelectPanels(QDialog):
    def __init__(self, parent, panels, table_docks=(), windows=(), targets=(), selected_target=None):
        super().__init__(parent)
        self.setWindowTitle('External Panel Dock — select dock panels')
        self.resize(590, 620)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('Send selected panels to:'))
        self.destination = QComboBox(self)
        for target in targets:
            self.destination.addItem(target.windowTitle(), target)
        if selected_target in targets:
            self.destination.setCurrentIndex(targets.index(selected_target))
        layout.addWidget(self.destination)
        layout.addWidget(QLabel('QGIS panels and plugins'))
        self.list = QListWidget(self)
        for dock in panels:
            self._add_checkable(self.list, dock, dock.isFloating())
        layout.addWidget(self.list, 1)
        self._selection_buttons(layout, self.list, 'panels')

        layout.addWidget(QLabel('Attribute tables and feature forms'))
        self.window_list = QListWidget(self)
        for dock in table_docks:
            self._add_checkable(self.window_list, dock, dock.isFloating())
        # Standalone QGIS attribute dialogs are deliberately not offered here.
        # QGIS owns their Qt lifecycle, and reparenting can crash on shutdown.
        layout.addWidget(self.window_list, 1)
        self._selection_buttons(layout, self.window_list, 'tables/forms')
        layout.addWidget(QLabel('Only native dock widgets are movable. Standalone tables/forms must first be docked in QGIS.'))
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _selection_buttons(self, layout, target, label):
        row = QHBoxLayout()
        select_all = QPushButton('Select all ' + label, self)
        select_none = QPushButton('Deselect all ' + label, self)
        select_all.clicked.connect(lambda: self._set_checks(target, True))
        select_none.clicked.connect(lambda: self._set_checks(target, False))
        row.addWidget(select_all)
        row.addWidget(select_none)
        row.addStretch(1)
        layout.addLayout(row)

    @staticmethod
    def _set_checks(list_widget, checked):
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for i in range(list_widget.count()):
            list_widget.item(i).setCheckState(state)

    def _add_checkable(self, list_widget, widget, checked):
        name = widget.windowTitle().replace('&', '').strip() or widget.objectName()
        item = QListWidgetItem(name)
        item.setData(Qt.ItemDataRole.UserRole, widget)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        list_widget.addItem(item)

    def _selected_items(self, list_widget):
        return [list_widget.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(list_widget.count())
                if list_widget.item(i).checkState() == Qt.CheckState.Checked]

    def target_window(self):
        return self.destination.currentData()

    def selected(self):
        return self._selected_items(self.list) + [
            widget for widget in self._selected_items(self.window_list)
            if isinstance(widget, QDockWidget)]

    def selected_windows(self):
        return [widget for widget in self._selected_items(self.window_list)
                if not isinstance(widget, QDockWidget)]


class HerdWindow(QMainWindow):
    def __init__(self, original, manager=None):
        super().__init__(None)
        self.original = original
        self.manager = manager
        self.preset_name = None
        self.pending_preset = None
        self.restoring = False
        self._closing = False
        self.saved_state_loaded = False
        self.entries = []  # dock, original area, floating, original geometry, visible
        self.setWindowFlags(Qt.WindowType.Window |
                            Qt.WindowType.WindowMinMaxButtonsHint |
                            Qt.WindowType.WindowCloseButtonHint)
        self.setWindowTitle('External Panel Dock')
        self.resize(950, 770)
        self.setDockOptions(QMainWindow.DockOption.AllowTabbedDocks |
                            QMainWindow.DockOption.AllowNestedDocks |
                            QMainWindow.DockOption.AnimatedDocks)
        self.setTabPosition(Qt.DockWidgetArea.AllDockWidgetAreas,
                            QTabWidget.TabPosition.North)
        central = QWidget(self)
        central.setMaximumSize(0, 0)
        self.setCentralWidget(central)
        toolbar = QToolBar('Panel arrangement', self)
        toolbar.setObjectName('ExternalPanelDockToolbar')
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        self._button(toolbar, 'New dock', self.new_window)
        self._button(toolbar, 'Add panels…', self.add_prompt)
        toolbar.addSeparator()
        self._button(toolbar, 'Save setup…', self.save_setup)
        self._button(toolbar, 'Load setup…', self.load_setup)
        toolbar.addSeparator()
        self.auto_add = QCheckBox('Auto-add new tables', self)
        self.auto_add.setToolTip('Automatically move new native QGIS attribute-table docks into this window. Enable Open attribute table as docked window in QGIS Data Sources options.')
        # The first dock is the default auto-add destination. Additional docks
        # start disabled so opening a new window never steals auto-add silently.
        self.auto_add.setChecked(not (manager and manager.windows))
        self.auto_add.toggled.connect(self._auto_target_changed)
        toolbar.addWidget(self.auto_add)
        toolbar.addSeparator()
        self._button(toolbar, 'Tabs', lambda: self.arrange('tabs'))
        self._button(toolbar, 'Side by side', lambda: self.arrange('horizontal'))
        self._button(toolbar, 'Stack vertically', lambda: self.arrange('vertical'))
        toolbar.addSeparator()
        toolbar.addWidget(QLabel(' Panel: ', self))
        self.picker = QComboBox(self)
        self.picker.setMinimumWidth(130)
        toolbar.addWidget(self.picker)
        self._button(toolbar, 'Move left / up', lambda: self.move_selected(-1))
        self._button(toolbar, 'Move right / down', lambda: self.move_selected(1))
        toolbar.addSeparator()
        self._button(toolbar, 'Return all', self.release_all)
        self.statusBar().showMessage('For automatic tables, enable Open attribute table as docked window in QGIS Settings > Options > Data Sources.')
        self.auto_timer = QTimer(self)
        self.auto_timer.setInterval(1200)
        self.auto_timer.timeout.connect(self._auto_tick)
        self.auto_timer.start()

    def _button(self, toolbar, title, callback):
        action = toolbar.addAction(title)
        action.triggered.connect(callback)

    def _docks(self):
        result = []
        for entry in self.entries:
            dock = entry[0]
            try:
                dock.objectName()
                result.append(dock)
            except RuntimeError:
                pass
        return result

    def _refresh_picker(self):
        # Never query a Qt control while its native window is closing. Doing so
        # after removeDockWidget() caused a native access violation in Qt 6.
        if self._closing:
            return
        selected = self.picker.currentData()
        self.picker.clear()
        for dock in self._docks():
            self.picker.addItem(dock.windowTitle().replace('&', '') or dock.objectName(), dock)
        idx = self.picker.findData(selected)
        if idx >= 0:
            self.picker.setCurrentIndex(idx)

    def available(self):
        existing = self._docks()
        candidates = []
        seen = set()
        # QApplication.allWidgets() finds floating QDockWidgets even if Qt has
        # changed their parent or removed them from mainWindow's child tree.
        for dock in QApplication.allWidgets():
            if not isinstance(dock, QDockWidget) or dock in existing:
                continue
            if id(dock) in seen or dock.parentWidget() is self:
                continue
            if self.isAncestorOf(dock):
                continue
            if self.manager and any(w is not self and dock in w._docks() for w in self.manager.windows):
                continue
            # Only take widgets owned by QGIS or floating attribute docks.
            if not belongs_to_main_window(dock, self.original):
                if not (dock.isFloating() and is_attribute_dock(dock)):
                    continue
            seen.add(id(dock))
            candidates.append(dock)
        return sorted(candidates, key=lambda d: d.windowTitle().casefold())

    def new_window(self):
        if self.manager:
            self.manager.new_window(prompt=True)

    def _auto_target_changed(self, checked):
        if self._closing:
            return
        # Exactly one window is the automatic destination. Manual Add panels
        # can still target any dock using the destination dropdown.
        if checked and self.manager:
            for other in list(self.manager.windows):
                if other is not self and other.auto_add.isChecked():
                    other.auto_add.blockSignals(True)
                    other.auto_add.setChecked(False)
                    other.auto_add.blockSignals(False)

    def _auto_tick(self):
        if self.pending_preset:
            self._try_pending()
        self._auto_collect_tables()

    def save_setup(self):
        if self.manager:
            self.manager.save_workspace(self)

    def load_setup(self):
        if self.manager:
            self.manager.choose_setup()

    def _auto_collect_tables(self):
        """Only transfer QGIS-created native docks, never standalone dialogs.

        Defer until the QGIS UI has returned to the event loop, avoiding
        modifications inside QGIS's attribute-table creation callbacks.
        """
        if not self.auto_add.isChecked() or not self.isVisible() or self.isMinimized():
            return
        if self.manager and (self.manager.auto_target() is not self or
                             any(w.pending_preset for w in self.manager.windows)):
            return
        try:
            for dock in self.available():
                if not is_attribute_dock(dock) or not dock.isVisible():
                    continue
                self.attach(dock)
        except (RuntimeError, ReferenceError):
            # A table may have closed between enumeration and transfer.
            return

    def showEvent(self, event):
        super().showEvent(event)
        if not self.auto_timer.isActive():
            self.auto_timer.start()

    def add_prompt(self):
        choices = self.available()
        panels = [dock for dock in choices if not is_attribute_dock(dock)]
        table_docks = [dock for dock in choices if is_attribute_dock(dock)]
        windows = []  # Safety: never reparent QGIS-owned standalone dialogs.
        if not choices:
            QMessageBox.information(self, 'External Panel Dock', 'No available QGIS dock panels were found. Dock standalone attribute tables within QGIS first.')
            return
        targets = list(self.manager.windows) if self.manager else [self]
        dialog = SelectPanels(self, panels, table_docks, windows, targets, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        destination = dialog.target_window() or self
        for dock in dialog.selected():
            destination.attach(dock)
        destination.showNormal() if destination.isMinimized() else destination.show()
        destination.raise_()
        destination.activateWindow()

    def attach(self, dock, restore_item=None):
        if dock in self._docks():
            return
        area = self.original.dockWidgetArea(dock)
        floating = dock.isFloating()
        geometry = dock.geometry()
        visible = dock.isVisible()
        self.original.removeDockWidget(dock)
        dock.setFloating(False)
        current = self._docks()
        restored = False
        if restore_item is not None and self.saved_state_loaded:
            # Use the exact objectName saved in QMainWindow's layout stream.
            # Native QGIS table docks can receive new autogenerated names
            # each time they are opened.
            old_name = dock.objectName()
            saved_name = restore_item.get('name') or old_name
            if saved_name and saved_name != old_name:
                dock.setObjectName(saved_name)
            restored = self.restoreDockWidget(dock)
        if not restored:
            self.addDockWidget(dock_area('LeftDockWidgetArea'), dock)
            if current:
                self.tabifyDockWidget(current[0], dock)
        self.entries.append((dock, area, floating, geometry, visible))
        dock.show()
        dock.raise_()
        self._refresh_picker()

    def arrange(self, mode):
        docks = self._docks()
        if not docks:
            return
        # QMainWindow.splitDockWidget() does not split a tab group reliably.
        # Remove all first, then construct an entirely fresh dock layout.
        for dock in docks:
            self.removeDockWidget(dock)
            dock.setFloating(False)
        first = docks[0]
        self.addDockWidget(dock_area('LeftDockWidgetArea'), first)
        previous = first
        for dock in docks[1:]:
            if mode == 'tabs':
                self.tabifyDockWidget(first, dock)
            else:
                self.splitDockWidget(previous, dock,
                                     orientation('Horizontal' if mode == 'horizontal' else 'Vertical'))
                previous = dock
        for dock in docks:
            dock.show()
        if mode == 'tabs':
            first.raise_()
        self.statusBar().showMessage('Layout changed to ' + mode + '. Drag splitters to resize panels.', 6000)

    def move_selected(self, direction):
        docks = self._docks()
        selected = self.picker.currentData()
        if selected not in docks:
            return
        index = docks.index(selected)
        target = index + direction
        if target < 0 or target >= len(docks):
            return
        docks[index], docks[target] = docks[target], docks[index]
        metadata = {id(e[0]): e for e in self.entries}
        self.entries = [metadata[id(d)] for d in docks]
        # Keep current arrangement whenever possible by identifying tab membership.
        mode = 'tabs' if len(docks) <= 1 or self.tabifiedDockWidgets(docks[0]) else 'horizontal'
        self.arrange(mode)
        self._refresh_picker()
        self.picker.setCurrentIndex(target)

    def release_all(self, refresh=True):
        # Restore QGIS-owned docks, but do not access our toolbar controls
        # during QMainWindow close/destruction.
        entries, self.entries = self.entries, []
        for dock, area, floating, geometry, visible in entries:
            try:
                self.removeDockWidget(dock)
                if area == dock_area('NoDockWidgetArea'):
                    area = dock_area('LeftDockWidgetArea')
                self.original.addDockWidget(area, dock)
                if floating:
                    dock.setFloating(True)
                    dock.setGeometry(geometry)
                dock.setVisible(visible)
            except RuntimeError:
                continue
        if refresh and not self._closing:
            self._refresh_picker()
        self.original.update()

    def _dock_descriptor(self, dock):
        title = dock.windowTitle().replace('&', '').strip()
        layer = re.split(r'\s+[—–-]\s+', title, maxsplit=1)[0].strip()
        return {'name': dock.objectName(), 'title': title,
                'kind': 'table' if is_attribute_dock(dock) else 'panel',
                'layer': layer}

    def export_setup(self):
        # Qt's layout serializer requires stable, distinct object names.
        # Some native attribute-table docks are created with an empty name.
        existing_names = set()
        for idx, dock in enumerate(self._docks()):
            name = dock.objectName()
            if not name or name in existing_names:
                name = 'ExternalPanelDockStored_{}'.format(idx)
                while name in existing_names:
                    name += '_x'
                dock.setObjectName(name)
            existing_names.add(name)
        return {
            'geometry': base64.b64encode(bytes(self.saveGeometry())).decode('ascii'),
            'state': base64.b64encode(bytes(self.saveState())).decode('ascii'),
            'docks': [self._dock_descriptor(d) for d in self._docks()],
            'auto_add': self.auto_add.isChecked(),
        }

    def begin_restore(self, spec):
        self.pending_preset = dict(spec)
        self.saved_state_loaded = False
        self.pending_preset['waiting'] = list(spec.get('docks', []))
        self.auto_add.setChecked(bool(spec.get('auto_add', True)))
        try:
            self.restoreGeometry(QByteArray.fromBase64(spec['geometry'].encode('ascii')))
        except (KeyError, ValueError, TypeError):
            pass
        # Restore the *empty* QMainWindow first. Qt retains missing dock slots,
        # and restoreDockWidget fills them later as QGIS creates the tables.
        try:
            data = QByteArray.fromBase64(spec['state'].encode('ascii'))
            self.saved_state_loaded = bool(self.restoreState(data))
        except (KeyError, ValueError, TypeError):
            self.saved_state_loaded = False
        self.show()
        self._try_pending()

    def _candidate(self, item):
        candidates = self.available()
        # Use identity first, then localized title, then unique layer name.
        for d in candidates:
            if item.get('name') and d.objectName() == item['name']:
                return d
        for d in candidates:
            if d.windowTitle().replace('&', '').strip() == item.get('title'):
                return d
        if item.get('kind') == 'table':
            match = [d for d in candidates if is_attribute_dock(d) and
                     self._dock_descriptor(d)['layer'] == item.get('layer')]
            if len(match) == 1:
                return match[0]
        return None

    def _try_pending(self):
        if not self.pending_preset or self.restoring:
            return
        self.restoring = True
        try:
            remaining = []
            for item in self.pending_preset['waiting']:
                dock = self._candidate(item)
                if dock is None:
                    remaining.append(item)
                    continue
                self.attach(dock, restore_item=item)
            self.pending_preset['waiting'] = remaining
            if not remaining:
                self.pending_preset = None
        finally:
            self.restoring = False

    def closeEvent(self, event):
        # Mark closed *before* docking changes, as QGIS/Qt may synchronously
        # emit widget signals while panels are transferred back.
        if self._closing:
            event.accept()
            return
        self._closing = True
        self.auto_timer.stop()
        self.pending_preset = None
        self.release_all(refresh=False)
        if self.manager:
            self.manager.window_closed(self)
        event.accept()

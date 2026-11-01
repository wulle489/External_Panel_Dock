"""QGIS integration and named workspaces for External Panel Dock."""
import os
import json
from qgis.PyQt.QtCore import QSettings, QTimer
from qgis.PyQt.QtWidgets import QInputDialog, QMessageBox
from qgis.PyQt.QtGui import QAction, QIcon
from qgis.core import QgsProject, QgsVectorLayer

SETTINGS = 'ExternalPanelDock/workspaces_v1'
AUTO = 'ExternalPanelDock/restore_on_start'


class ExternalPanelDockPlugin:
    MENU = '&External Panel Dock'

    def __init__(self, iface):
        self.iface = iface
        self.windows = []
        self.action = None
        self.restore_timer = None
        self.opened_tables = set()
        self.startup_requested = False

    def initGui(self):
        icon = QIcon(os.path.join(os.path.dirname(__file__), 'icon.svg'))
        self.action = QAction(icon, 'External Panel Dock', self.iface.mainWindow())
        self.action.setToolTip('Manage multiple floating QGIS panel workspaces')
        self.action.triggered.connect(self.open_dock)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu(self.MENU, self.action)
        # Delay until QGIS has finished constructing its main interface.
        QTimer.singleShot(2500, self._startup)

    def _settings(self):
        return QSettings()

    def _presets(self):
        try:
            obj = json.loads(self._settings().value(SETTINGS, '{}'))
            return obj if isinstance(obj, dict) else {}
        except (ValueError, TypeError):
            return {}

    def new_window(self, prompt=False):
        from .panel_herd import HerdWindow
        w = HerdWindow(self.iface.mainWindow(), self)
        self.windows.append(w)
        w.setWindowTitle('External Panel Dock — Dock {}'.format(len(self.windows)))
        w.show()
        if prompt:
            w.add_prompt()
        return w

    def open_dock(self):
        if self.windows:
            w = self.windows[-1]
            w.showNormal()
            w.raise_()
            w.activateWindow()
            w.add_prompt()
        else:
            self.new_window(prompt=True)

    def window_closed(self, window):
        if window in self.windows:
            self.windows.remove(window)

    def auto_target(self):
        # A single designated window collects unsolicited new tables.
        return next((w for w in reversed(self.windows)
                     if w.auto_add.isChecked() and w.isVisible()), None)

    def save_workspace(self, caller):
        name, ok = QInputDialog.getText(caller, 'Save panel setup', 'Setup name:',
                                        text=caller.preset_name or '')
        name = name.strip()
        if not ok or not name:
            return
        presets = self._presets()
        if name in presets:
            ans = QMessageBox.question(caller, 'Overwrite setup',
                                      'Replace existing setup "{}"?'.format(name))
            if ans != QMessageBox.StandardButton.Yes:
                return
        # Save all currently open dock containers as one named multi-window workspace.
        presets[name] = [w.export_setup() for w in self.windows]
        self._settings().setValue(SETTINGS, json.dumps(presets))
        caller.preset_name = name
        answer = QMessageBox.question(caller, 'Restore on QGIS startup',
                                      'Automatically restore "{}" when QGIS starts?'.format(name))
        if answer == QMessageBox.StandardButton.Yes:
            self._settings().setValue(AUTO, name)
        caller.statusBar().showMessage('Saved setup: ' + name, 6000)

    def choose_setup(self):
        presets = self._presets()
        if not presets:
            QMessageBox.information(self.iface.mainWindow(), 'Panel setups',
                                    'No setups saved yet. Use Save setup in External Panel Dock.')
            return
        items = sorted(presets)
        name, ok = QInputDialog.getItem(self.iface.mainWindow(), 'Load panel setup',
                                         'Saved setup:', items, 0, False)
        if ok and name:
            self.load_workspace(name)

    def load_workspace(self, name):
        specs = self._presets().get(name)
        if not isinstance(specs, list):
            return
        # Return native docks before removing existing containers. Avoid closing
        # QGIS-owned standalone dialogs (they are never embedded).
        for w in list(self.windows):
            w.close()
        self.opened_tables.clear()
        for spec in specs:
            w = self.new_window(prompt=False)
            w.preset_name = name
            w.begin_restore(spec)
        # Old saved setups may contain auto_add=True in several windows.
        # Normalize after loading, leaving only the last requested target on.
        targets = [w for w in self.windows if w.auto_add.isChecked()]
        if len(targets) > 1:
            chosen = targets[-1]
            for w in targets:
                if w is not chosen:
                    w.auto_add.blockSignals(True)
                    w.auto_add.setChecked(False)
                    w.auto_add.blockSignals(False)
        self._start_restore_timer()

    def _startup(self):
        name = self._settings().value(AUTO, '', type=str)
        if name and name in self._presets() and not self.startup_requested:
            self.startup_requested = True
            self.load_workspace(name)

    def _start_restore_timer(self):
        if self.restore_timer is None:
            self.restore_timer = QTimer(self.iface.mainWindow())
            self.restore_timer.setInterval(1500)
            self.restore_timer.timeout.connect(self._pending_tables)
        self.restore_timer.start()

    def _pending_tables(self):
        pending = [item for w in self.windows if w.pending_preset
                   for item in w.pending_preset.get('waiting', [])]
        if not pending:
            self.restore_timer.stop()
            return
        for item in pending:
            if item.get('kind') != 'table':
                continue
            layer_name = item.get('layer', '')
            if not layer_name or layer_name in self.opened_tables:
                continue
            matches = [layer for layer in QgsProject.instance().mapLayersByName(layer_name)
                       if isinstance(layer, QgsVectorLayer) and layer.isValid()]
            if len(matches) != 1:
                continue  # project still loading, ambiguous, or no such layer
            self.opened_tables.add(layer_name)
            try:
                self.iface.showAttributeTable(matches[0])
            except (RuntimeError, AttributeError):
                self.opened_tables.discard(layer_name)
        for w in list(self.windows):
            if w.pending_preset:
                w._try_pending()

    def unload(self):
        if self.restore_timer:
            self.restore_timer.stop()
            self.restore_timer = None
        for w in list(self.windows):
            w.close()
        self.windows.clear()
        if self.action:
            self.iface.removePluginMenu(self.MENU, self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action.deleteLater()
            self.action = None

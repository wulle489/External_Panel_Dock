"""QGIS integration for External Panel Dock."""
import os
from qgis.PyQt.QtGui import QAction, QIcon


class ExternalPanelDockPlugin:
    MENU = '&External Panel Dock'

    def __init__(self, iface):
        self.iface = iface
        self.dock_window = None
        self.action = None

    def initGui(self):
        icon = QIcon(os.path.join(os.path.dirname(__file__), 'icon.svg'))
        self.action = QAction(icon, 'External Panel Dock', self.iface.mainWindow())
        self.action.setToolTip('Group QGIS panels and attribute windows in a separate, rearrangeable window')
        self.action.triggered.connect(self.open_dock)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu(self.MENU, self.action)

    def open_dock(self):
        from .panel_herd import HerdWindow
        if self.dock_window is None:
            self.dock_window = HerdWindow(self.iface.mainWindow())
        self.dock_window.show()
        self.dock_window.add_prompt()

    def unload(self):
        if self.dock_window is not None:
            self.dock_window.close()
            self.dock_window = None
        if self.action is not None:
            self.iface.removePluginMenu(self.MENU, self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action.deleteLater()
            self.action = None

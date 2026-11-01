"""External Panel Dock QGIS plugin."""

def classFactory(iface):
    from .plugin import ExternalPanelDockPlugin
    return ExternalPanelDockPlugin(iface)

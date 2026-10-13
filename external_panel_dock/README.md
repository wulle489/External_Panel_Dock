# External Panel Dock

Group QGIS dock panels, plugin panels, attribute tables and supported feature forms in a single independent window. Useful when the QGIS map canvas should stay on one monitor and tools or tables on another.

## Auto-add attribute tables (v0.8)

In QGIS, enable **Settings > Options > Data Sources > Open attribute table as docked window**. Then activate **Auto-add new tables** on the External Panel Dock toolbar. Tables opened while the external workspace is visible will be picked up automatically (typically within about 1 second). Only QGIS native dock widgets are moved, never standalone dialogs. Uncheck the option to stop automatic collection. This release does not change your global QGIS preferences.

## Features

- Separate, movable, resizable host window with minimize/maximize controls.
- Tabbed, horizontal and vertical layouts; manual reordering and resizable splitters.
- Selection dialog separating QGIS/plugin panels from attribute tables and forms.
- Select all / Deselect all buttons for each group.
- Restore the original windows with **Return all** or by closing the host.

## Use

1. Choose **Plugins → External Panel Dock → External Panel Dock** (or use the toolbar icon).
2. Select windows, then click **OK**.
3. Move the host to a second monitor and choose **Tabs**, **Side by side**, or **Stack vertically**.
4. Use **Return all** before unloading the plugin.

## Notes

- Save edits before moving standalone attribute forms or tables. Qt window reparenting is not officially supported for every QGIS dialog.
- Windows are only listed when detected by the QGIS/Qt window discovery logic.
- If the older **Dude, where's my window?** plugin is installed, uninstall or disable it separately: this plugin uses a new folder and ID.
- This release has passed static checks, not live GUI testing on QGIS.

## Attribution

Based on **Dude, Where's My Window?** by **Ian Hay**. Original license retained in `LICENSE`. The old window-rescue functionality has been removed.


## Safety change (0.7.1)

Standalone attribute-table dialogs are no longer transferable because Qt reparenting can cause an access violation when QGIS destroys its dockable-widget helper. Use the native QGIS Dock control to turn an attribute table into a dock widget before selecting it in External Panel Dock. Please save edits before changing the window layout.

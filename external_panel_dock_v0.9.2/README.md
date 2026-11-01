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


## Version 0.9.0 preview: multiple windows and named setups

Use **New dock** to create another independent external panel window. **Save setup…**
saves all currently open external panel windows under one name (including tab groups,
split arrangements, window positions, and selected dock panels). **Load setup…**
restores a previously saved workspace. When saving, you may opt into restoring that
setup at QGIS startup. Saved layouts are stored in user-local QSettings.

For reliable attribute table restoration enable **Open attribute table as docked
window** in QGIS Settings > Options > Data Sources. The plugin will attempt to open
missing saved attribute tables whose uniquely named layers are present in the
current project. Tables/forms that are standalone dialogs are not reparented.
Missing layers or plugin dock widgets remain unresolved until they are available.
The layout state uses Qt's dock object names; panels whose internal names change
across QGIS restarts may not return to their precise former position.

**Preview:** Not verified in a live QGIS 4.2 session. Test without unsaved edits.

## Version 0.9.1 preview fixes

The **Add panels...** dialog has a **Send selected panels to** dropdown to choose
which external dock receives the selected panels. Exactly one dock can have
**Auto-add new tables** enabled; use the checkbox on the desired dock to set
the automatic destination.

Setup loading now restores Qt's saved state before moving native dock widgets,
then uses `restoreDockWidget()` as tables become available. This is intended
to preserve nested horizontal/vertical splits and tabs instead of rebuilding
them as a single row. Existing v0.9.0 named setups remain readable, but for
more reliable table identities, save them again after loading the new version.

Still requires live testing in QGIS 4.2.1; test without unsaved edits.


### v0.9.2 preview safety fixes

- Close/Return All no longer touches the panel picker while the window is closing.
- New additional dock windows start with Auto-add off; only one dock can own automatic table collection.
- Multiple Auto-add values in older presets are normalized on load.

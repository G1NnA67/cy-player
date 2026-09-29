"""Keep Qt's normal GUI plugins except unused PDF and on-screen keyboard plugins."""
from pathlib import Path
from PyInstaller.utils.hooks.qt import add_qt6_dependencies

# Retain the upstream dependency collection, including Cocoa/native input support.
hiddenimports, binaries, datas = add_qt6_dependencies(__file__)
_unused_plugins = {"libqpdf.dylib", "libqtvirtualkeyboardplugin.dylib"}
binaries = [entry for entry in binaries if Path(entry[0]).name not in _unused_plugins]

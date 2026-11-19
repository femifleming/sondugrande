# -*- mode: python ; coding: utf-8 -*-
# PyInstaller recipe for Songrande and SoundGrain, on macOS, Windows and Linux.
#
#   pyinstaller --noconfirm --distpath dist --workpath build packaging/apps.spec
#
# macOS:   dist/Songrande.app and dist/SoundGrain.app
# others:  dist/Songrande/ with the two programs side by side (they share their libraries)
import glob
import os
import sys

from PyInstaller.utils.hooks import collect_dynamic_libs

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
sys.path.insert(0, ROOT)
MAC = sys.platform == "darwin"
WIN = sys.platform == "win32"


def version_of(path, name):
    import ast
    for node in ast.parse(open(path, encoding="utf-8").read()).body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == name for t in node.targets):
            return node.value.value
    raise ValueError(name)


SONGRANDE_VERSION = version_of(os.path.join(ROOT, "songrande", "constants.py"), "SG_VERSION")
SOUNDGRAIN_VERSION = version_of(os.path.join(ROOT, "Resources", "constants.py"), "SG_VERSION")


def resources(package):
    """The pictures, documentation and empty project a package looks for next to its modules."""
    out = []
    for pattern, target in (("*.png", ""), ("*.ico", ""), ("*.icns", ""), ("*.sg", ""), ("*.sgr", ""),
                            ("images/*.png", "images"), ("doc/*.md", "doc")):
        for path in glob.glob(os.path.join(ROOT, package, pattern)):
            out.append((path, os.path.join(package, target) if target else package))
    return out


binaries = collect_dynamic_libs("pyo")
excludes = ["tkinter", "matplotlib", "scipy", "PIL", "IPython", "pytest", "setuptools", "pip", "wheel",
            "soundgrain_resources", "numpy.f2py", "numpy.distutils", "pydoc_data", "lib2to3"]
hidden = ["pyo", "pyo64", "pyo.lib.hrtf", "markdown", "markdown.extensions.extra"]

songrande = Analysis([os.path.join(ROOT, "Songrande.py")], pathex=[ROOT], binaries=binaries,
                     datas=resources("songrande") + [(os.path.join(ROOT, "scripts", "COPYING.txt"), ".")],
                     hiddenimports=hidden + ["songrande.selftest", "songrande.render", "songrande.app"],
                     excludes=excludes, noarchive=False)
soundgrain = Analysis([os.path.join(ROOT, "packaging", "soundgrain_main.py")], pathex=[ROOT], binaries=binaries,
                      datas=resources("Resources") + [(os.path.join(ROOT, "scripts", "COPYING.txt"), ".")],
                      hiddenimports=hidden + ["SoundGrain"], excludes=excludes, noarchive=False)

songrande_pyz = PYZ(songrande.pure)
soundgrain_pyz = PYZ(soundgrain.pure)

songrande_icon = os.path.join(ROOT, "packaging", "Songrande.icns" if MAC else "Songrande.ico")
soundgrain_icon = os.path.join(ROOT, "Resources", "SoundGrain.icns" if MAC else "SoundGrain.ico")
# on Windows a console window would open beside the application; the programs
# still write their reports to a console they are started from
songrande_exe = EXE(songrande_pyz, songrande.scripts, [], exclude_binaries=True, name="Songrande",
                    console=not (MAC or WIN), icon=songrande_icon if (MAC or WIN) else None, upx=False)
soundgrain_exe = EXE(soundgrain_pyz, soundgrain.scripts, [], exclude_binaries=True, name="SoundGrain",
                     console=not (MAC or WIN), icon=soundgrain_icon if (MAC or WIN) else None, upx=False)

MICROPHONE = "The microphone is used to record into the sound table (the Mic button)."

if MAC:
    songrande_dir = COLLECT(songrande_exe, songrande.binaries, songrande.datas, name="Songrande", upx=False)
    soundgrain_dir = COLLECT(soundgrain_exe, soundgrain.binaries, soundgrain.datas, name="SoundGrain", upx=False)
    BUNDLE(songrande_dir, name="Songrande.app", icon=songrande_icon, bundle_identifier="org.songrande.Songrande",
           version=SONGRANDE_VERSION,
           info_plist={
               "CFBundleDisplayName": "Songrande",
               "CFBundleShortVersionString": SONGRANDE_VERSION,
               "NSHighResolutionCapable": True,
               "NSMicrophoneUsageDescription": MICROPHONE,
               "NSHumanReadableCopyright": "SoundGrain (C) 2009-2018 Olivier Belanger. Songrande (C) 2026 femifleming. GPLv3.",
               "LSMinimumSystemVersion": "13.0",
               "CFBundleDocumentTypes": [
                   {"CFBundleTypeName": "Songrande project", "CFBundleTypeExtensions": ["sgr"],
                    "CFBundleTypeRole": "Editor", "LSHandlerRank": "Owner"},
                   {"CFBundleTypeName": "SoundGrain project", "CFBundleTypeExtensions": ["sg"],
                    "CFBundleTypeRole": "Viewer", "LSHandlerRank": "Alternate"}],
           })
    BUNDLE(soundgrain_dir, name="SoundGrain.app", icon=soundgrain_icon, bundle_identifier="org.soundgrain.SoundGrain",
           version=SOUNDGRAIN_VERSION,
           info_plist={
               "CFBundleDisplayName": "SoundGrain",
               "CFBundleShortVersionString": SOUNDGRAIN_VERSION,
               "NSHighResolutionCapable": True,
               "NSMicrophoneUsageDescription": MICROPHONE,
               "NSHumanReadableCopyright": "(C) 2009-2018 Olivier Belanger. GPLv3.",
               "LSMinimumSystemVersion": "13.0",
               "CFBundleDocumentTypes": [
                   {"CFBundleTypeName": "SoundGrain project", "CFBundleTypeExtensions": ["sg"],
                    "CFBundleTypeRole": "Editor", "LSHandlerRank": "Owner",
                    "CFBundleTypeIconFile": "SoundGrainDocIcon.icns"}],
           })
else:
    COLLECT(songrande_exe, songrande.binaries, songrande.datas,
            soundgrain_exe, soundgrain.binaries, soundgrain.datas, name="Songrande", upx=False)

# -*- mode: python ; coding: utf-8 -*-
# PyInstaller recipe for Sondugrande and SoundGrain, on macOS, Windows and Linux.
#
#   pyinstaller --noconfirm --distpath dist --workpath build packaging/apps.spec
#
# macOS:   dist/Sondugrande.app and dist/SoundGrain.app
# others:  dist/Sondugrande/ with the two programs side by side (they share their libraries)
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


SONDUGRANDE_VERSION = version_of(os.path.join(ROOT, "sondugrande", "constants.py"), "SG_VERSION")
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

sondugrande = Analysis([os.path.join(ROOT, "Sondugrande.py")], pathex=[ROOT], binaries=binaries,
                     datas=resources("sondugrande") + [(os.path.join(ROOT, "scripts", "COPYING.txt"), ".")],
                     hiddenimports=hidden + ["sondugrande.selftest", "sondugrande.render", "sondugrande.app"],
                     excludes=excludes, noarchive=False)
soundgrain = Analysis([os.path.join(ROOT, "packaging", "soundgrain_main.py")], pathex=[ROOT], binaries=binaries,
                      datas=resources("Resources") + [(os.path.join(ROOT, "scripts", "COPYING.txt"), ".")],
                      hiddenimports=hidden + ["SoundGrain"], excludes=excludes, noarchive=False)

sondugrande_pyz = PYZ(sondugrande.pure)
soundgrain_pyz = PYZ(soundgrain.pure)

sondugrande_icon = os.path.join(ROOT, "packaging", "Sondugrande.icns" if MAC else "Sondugrande.ico")
soundgrain_icon = os.path.join(ROOT, "Resources", "SoundGrain.icns" if MAC else "SoundGrain.ico")
# on Windows a console window would open beside the application; the programs
# still write their reports to a console they are started from
sondugrande_exe = EXE(sondugrande_pyz, sondugrande.scripts, [], exclude_binaries=True, name="Sondugrande",
                    console=not (MAC or WIN), icon=sondugrande_icon if (MAC or WIN) else None, upx=False)
soundgrain_exe = EXE(soundgrain_pyz, soundgrain.scripts, [], exclude_binaries=True, name="SoundGrain",
                     console=not (MAC or WIN), icon=soundgrain_icon if (MAC or WIN) else None, upx=False)

MICROPHONE = "The microphone is used to record into the sound table (the Mic button)."

if MAC:
    sondugrande_dir = COLLECT(sondugrande_exe, sondugrande.binaries, sondugrande.datas, name="Sondugrande", upx=False)
    soundgrain_dir = COLLECT(soundgrain_exe, soundgrain.binaries, soundgrain.datas, name="SoundGrain", upx=False)
    BUNDLE(sondugrande_dir, name="Sondugrande.app", icon=sondugrande_icon, bundle_identifier="org.sondugrande.Sondugrande",
           version=SONDUGRANDE_VERSION,
           info_plist={
               "CFBundleDisplayName": "Sondugrande",
               "CFBundleShortVersionString": SONDUGRANDE_VERSION,
               "NSHighResolutionCapable": True,
               "NSMicrophoneUsageDescription": MICROPHONE,
               "NSHumanReadableCopyright": "SoundGrain (C) 2009-2018 Olivier Belanger. Sondugrande (C) 2026 femifleming. GPLv3.",
               "LSMinimumSystemVersion": "13.0",
               "CFBundleDocumentTypes": [
                   {"CFBundleTypeName": "Sondugrande project", "CFBundleTypeExtensions": ["sgr"],
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
    COLLECT(sondugrande_exe, sondugrande.binaries, sondugrande.datas,
            soundgrain_exe, soundgrain.binaries, soundgrain.datas, name="Sondugrande", upx=False)

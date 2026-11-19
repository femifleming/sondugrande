"""Put the built applications into one archive per system, with the manual,
the licence and a note on installing.

    python packaging/package.py            ->  dist/sondugrande-<system>.zip (or .tar.gz on Linux)
"""
import os
import shutil
import subprocess
import sys
import tarfile
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")

NOTES = {
    "darwin": """Sondugrande and SoundGrain for macOS (Apple silicon)

Drag Sondugrande.app and SoundGrain.app to /Applications (or anywhere).
The applications are not notarised: the first time, right-click one and
choose Open, or run once in Terminal

    xattr -dr com.apple.quarantine /Applications/Sondugrande.app /Applications/SoundGrain.app

macOS asks once for the microphone (the Mic button records into the sound table).
""",
    "win32": """Sondugrande and SoundGrain for Windows (64-bit)

Unzip the Sondugrande folder anywhere and start Sondugrande.exe or SoundGrain.exe
(the two share the files in _internal, so keep the folder together).
Windows SmartScreen may ask before the first start: choose More info, Run anyway.
""",
    "linux": """Sondugrande and SoundGrain for Linux (x86-64, built on Ubuntu 22.04)

Unpack the Sondugrande folder anywhere and run ./Sondugrande or ./SoundGrain
(the two share the files in _internal, so keep the folder together).
They need GTK 3 and ALSA (or JACK), which a desktop system has.
""",
}

COMMON = """
Sondugrande is a development of SoundGrain by Olivier Belanger
(https://github.com/belangeo/soundgrain). Both are free software under the
GNU General Public License version 3 (COPYING.txt). The source of both is at
https://github.com/femifleming/sondugrande

The manual is Sondugrande Manual.pdf. SoundGrain's own documentation is in its
Help menu.
"""


def main():
    system = "darwin" if sys.platform == "darwin" else "win32" if sys.platform == "win32" else "linux"
    label = {"darwin": "macOS-arm64", "win32": "Windows-x64", "linux": "Linux-x86_64"}[system]
    stage = os.path.join(DIST, "sondugrande-" + label)
    if os.path.isdir(stage):
        shutil.rmtree(stage)
    os.makedirs(stage)
    if system == "darwin":
        for app in ("Sondugrande.app", "SoundGrain.app"):
            # ditto keeps the bundle's symbolic links and signature
            subprocess.check_call(["ditto", os.path.join(DIST, app), os.path.join(stage, app)])
    else:
        shutil.copytree(os.path.join(DIST, "Sondugrande"), os.path.join(stage, "Sondugrande"), symlinks=True)
    with open(os.path.join(stage, "README.txt"), "w", encoding="utf-8") as f:
        f.write(NOTES[system] + COMMON)
    shutil.copy(os.path.join(ROOT, "scripts", "COPYING.txt"), os.path.join(stage, "COPYING.txt"))
    manual = os.path.join(ROOT, "docs", "manual", "Sondugrande Manual.pdf")
    if os.path.isfile(manual):
        shutil.copy(manual, stage)
    examples = os.path.join(ROOT, "examples")
    if os.path.isdir(examples):
        shutil.copytree(examples, os.path.join(stage, "examples"))
    if system == "darwin":
        archive = stage + ".zip"
        if os.path.exists(archive):
            os.remove(archive)
        subprocess.check_call(["ditto", "-c", "-k", "--keepParent", stage, archive])
    elif system == "win32":
        archive = stage + ".zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            for folder, dirs, files in os.walk(stage):
                for name in files:
                    path = os.path.join(folder, name)
                    z.write(path, os.path.relpath(path, DIST))
    else:
        archive = stage + ".tar.gz"
        with tarfile.open(archive, "w:gz") as t:
            t.add(stage, arcname=os.path.basename(stage))
    print("%s (%.1f MB)" % (archive, os.path.getsize(archive) / 1e6))


if __name__ == "__main__":
    main()

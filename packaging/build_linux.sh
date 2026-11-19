#!/usr/bin/env bash
# Build and check Sondugrande and SoundGrain on Ubuntu 22.04 (the continuous
# integration runs this; so does `docker run ubuntu:22.04` on another system).
#   packaging/build_linux.sh [python]        python defaults to python3
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${1:-python3}"

if [ "${SONDUGRANDE_APT:-1}" = "1" ]; then
  SUDO=""; [ "$(id -u)" != "0" ] && SUDO="sudo"
  export DEBIAN_FRONTEND=noninteractive
  $SUDO apt-get update -qq
  # what wxPython's wheel and pyo link to, and a display for the tests
  $SUDO apt-get install -y -qq --no-install-recommends \
      libgtk-3-0 libnotify4 libsdl2-2.0-0 libsm6 libxtst6 libxxf86vm1 libpng16-16 libjpeg-turbo8 libtiff5 \
      libpcre2-32-0 libsecret-1-0 libegl1 libgl1 libglu1-mesa libasound2 libjack-jackd2-0 \
      xvfb xauth binutils file >/dev/null
fi

"$PY" -m pip install -q --upgrade pip
"$PY" -m pip install -q -r packaging/requirements.txt pyinstaller
# wxPython has no Linux wheels on PyPI: the project's own builds for Ubuntu 22.04
"$PY" -m pip install -q -f https://extras.wxpython.org/wxPython4/extras/linux/gtk3/ubuntu-22.04 "wxPython==4.2.2"

# anything wxPython or pyo still cannot find is named here, before the tests trip over it
missing=$("$PY" - <<'PYCHECK'
import glob, os, subprocess, sysconfig
site = sysconfig.get_paths()["purelib"]
found = set()
for pattern in ("wx/_core.*.so", "wx/_adv.*.so", "wx/_html.*.so", "pyo/_pyo.*.so"):
    for path in glob.glob(os.path.join(site, pattern)):
        out = subprocess.run(["ldd", path], capture_output=True, text=True).stdout
        found.update(line.split()[0] for line in out.splitlines() if "not found" in line)
print(" ".join(sorted(found)))
PYCHECK
)
if [ -n "$missing" ]; then echo "missing system libraries: $missing"; exit 1; fi

"$PY" packaging/probe_pyo.py 2>&1 | grep -v -i "portmidi\|wxpython\|toolkit\|maintained\|gui\|^$\|Pyo message" || true

echo "== tests"
xvfb-run -a "$PY" -m unittest discover -s tests -p "test_sondugrande*.py"
# SoundGrain's own tests (two of them assume Linux paths, so they run here)
xvfb-run -a "$PY" -m unittest discover -s tests -p "test_[!s]*.py" || [ "${SOUNDGRAIN_TESTS_REQUIRED:-1}" != "1" ]

echo "== build"
"$PY" -m PyInstaller --noconfirm --distpath dist --workpath build packaging/apps.spec >build_pyinstaller.log 2>&1 || { tail -40 build_pyinstaller.log; exit 1; }

echo "== packaged programs"
xvfb-run -a "$PY" packaging/check_packaged.py out/selftest
"$PY" packaging/package.py

"""Run the self-checks of the built applications and say what happened.

    python packaging/check_packaged.py [folder for the self-test's files]

Works the same on macOS (dist/*.app), Windows and Linux (dist/Sondugrande/):
starts the packaged Sondugrande's self-test (it draws in the room, renders,
checks that the sound moves, saves and reloads) and the packaged SoundGrain's
smoke check, waits for them, prints the self-test's report and returns 0 only
if both passed. No audio device is needed.
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")


def program(name):
    if sys.platform == "darwin":
        return os.path.join(DIST, name + ".app", "Contents", "MacOS", name)
    if sys.platform == "win32":
        return os.path.join(DIST, "Sondugrande", name + ".exe")
    return os.path.join(DIST, "Sondugrande", name)


def run(command, timeout=600):
    print("$ " + " ".join(command))
    sys.stdout.flush()
    try:
        done = subprocess.run(command, timeout=timeout, capture_output=True, text=True, errors="replace")
    except subprocess.TimeoutExpired as error:
        print("TIMED OUT after %d s" % timeout)
        print((error.stdout or b"")[-3000:] if isinstance(error.stdout, bytes) else (error.stdout or "")[-3000:])
        return 124
    for stream in (done.stdout, done.stderr):
        text = "\n".join(line for line in (stream or "").splitlines() if "portmidi" not in line.lower())
        if text.strip():
            print(text[-6000:])
    return done.returncode


def main():
    folder = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "out", "selftest"))
    failed = []

    code = run([program("Sondugrande"), "--version"])
    if code != 0:
        failed.append("Sondugrande --version (%d)" % code)

    code = run([program("Sondugrande"), "--selftest", folder, "--offline", "--seconds", "4"])
    report_path = os.path.join(folder, "report.json")
    if os.path.isfile(report_path):
        with open(report_path) as f:
            report = json.load(f)
        for name, check in report["checks"].items():
            print("%s  %s  %s" % ("PASS" if check["ok"] else "FAIL", name, check["detail"] or ""))
        for error in report["errors"]:
            print(error)
        if not report.get("ok"):
            failed.append("Sondugrande self-test: checks failed")
    else:
        failed.append("Sondugrande self-test: no report")
    if code != 0:
        failed.append("Sondugrande self-test (%d)" % code)

    code = run([program("SoundGrain"), "--smoke"])
    if code != 0:
        failed.append("SoundGrain smoke check (%d)" % code)

    # the offline renderer of the packaged program, on the example project
    out = os.path.join(folder, "demo_ambix.wav")
    code = run([program("Sondugrande"), "--render", os.path.join(ROOT, "examples", "demo.sgr"), out,
                "--dur", "3", "--output", "Ambisonics", "--order", "3"])
    if code != 0 or not os.path.isfile(out) or os.path.getsize(out) < 16 * 3 * 44100 * 2:
        failed.append("Sondugrande --render (%d)" % code)
    else:
        print("rendered %s (%.1f MB)" % (out, os.path.getsize(out) / 1e6))

    if failed:
        print("PACKAGED PROGRAMS FAILED: " + "; ".join(failed))
        return 1
    print("PACKAGED PROGRAMS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())

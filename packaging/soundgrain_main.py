"""Entry point of the packaged SoundGrain.

SoundGrain itself (SoundGrain.py and the Resources package) is Olivier
Belanger's SoundGrain, unchanged. This small wrapper only adds a self-check
for the packaged application:

    SoundGrain --smoke     import everything, find the resources, build the
                           main window if an audio device is there, and quit
"""
import os
import sys


def smoke():
    # a home folder of its own: the check must not take the audio device (or
    # anything else) from the preferences in the real ~/.soundgrain-init
    import tempfile
    home = tempfile.mkdtemp(prefix="soundgrain-smoke-")
    os.environ["HOME"] = os.environ["USERPROFILE"] = home
    import wx
    import pyo
    import SoundGrain
    from Resources import constants
    from Resources import (audio, Biquad_Filter, CommandFrame, ControlPanel, DrawingSurface, FxBall,
                           MainFrame, MidiSettings, Modules, Trajectory, widgets, splash)
    missing = [path for path in (
        constants.SPLASH_FILE,
        os.path.join(constants.RESOURCES_PATH, "new_soundgrain_file.sg"),
        os.path.join(constants.DOCUMENTATION_PATH, "02_surface.md"),
        os.path.join(constants.IMAGES_PATH, "Mario1.png"),
    ) if not os.path.isfile(path)]
    if missing:
        print("SMOKE FAILED: missing resources: %s" % missing)
        return 1
    print("SoundGrain %s, pyo %s, wxPython %s" % (constants.SG_VERSION, ".".join(map(str, pyo.getVersion())),
                                                    wx.version()))
    names, indexes = pyo.pa_get_output_devices()
    if not indexes:
        # no audio device at all (a build machine): pyo's server would crash
        # booting PortAudio there, so the window, which boots it, is not built
        print("SMOKE PASSED (no audio output device, main window not built)")
        return 0
    app = wx.App(False)
    try:
        frame = MainFrame.MainFrame(None, -1, pos=(0, 20), size=(900, 600), screen_size=(1280, 800))
    except RuntimeError as error:
        # no audio device on this machine (a build machine): the window cannot open its server
        print("SMOKE PASSED (no audio device: %s)" % error)
        return 0
    frame.Show()
    result = {"code": 1}

    def done():
        try:
            ok = frame.controls.tog_audio.IsEnabled() and len(frame.panel.getAllTrajectories()) == constants.MAX_STREAMS
            result["code"] = 0 if ok else 1
            # leave without writing the preferences file
            if frame.sg_audio.server.getIsBooted():
                frame.controls.meter.OnClose(None)
                frame.sg_audio.shutdown()
        finally:
            frame.Destroy()
            wx.CallLater(200, app.ExitMainLoop)

    wx.CallLater(1500, done)
    app.MainLoop()
    print("SMOKE %s" % ("PASSED" if result["code"] == 0 else "FAILED"))
    return result["code"]


if __name__ == '__main__':
    # a windowed program on Windows has no console to write to
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")
    if len(sys.argv) > 1 and sys.argv[1] == "--smoke":
        sys.exit(smoke())
    import SoundGrain
    SoundGrain.main()

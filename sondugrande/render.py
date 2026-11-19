"""
Sondugrande - running a project without a window: offline rendering.

    python Sondugrande.py --render project.sgr out.wav --dur 20 --output Ambisonics --order 3

renders a saved project (or a scene built in code) to a sound file faster
than real time, through exactly the same engine as the application. The tests
and the continuous-integration smoke test use it, and it is the way to bounce
a long Ambisonic file.

This file is part of Sondugrande, a derivative of SoundGrain (Olivier Belanger),
released under the GNU General Public License version 3 or later.
"""
import os
import xmlrpc.client as xmlrpclib

from .constants import *
from . import ambi, space
from .scene import Scene, legacyFactors

Y_PARAMS = ["dns", "pit", "len", "dev", "amp", "fif", "fiq", "trs", "dur", "pos", "ffr", "fqr", "pan"]


def loadProject(path):
    with open(path, "r") as f:
        msg = f.read()
    result, method = xmlrpclib.loads(msg)
    return result[0]


def saveProject(state, path):
    with open(path, "w") as f:
        f.write(xmlrpclib.dumps((state,), allow_none=True))


def applyGranulatorState(audio, d):
    """What the Granulator Controls window does when a project loads, without the window."""
    audio.setDensity(d.get('density', 32))
    audio.setBasePitch(d.get('pitch', 1.0))
    audio.setGrainDur(d.get('graindur', 200))
    audio.setGrainDev(d.get('graindev', 0))
    audio.setFilterFreq(d.get('filtfreq', 15000.0))
    audio.setFilterQ(d.get('filtq', 0.7))
    audio.setFilterType(d.get('filtt', 0.0))
    audio.setRandDens(d.get('rnddens', 0))
    audio.setRandDur(d.get('rnddur', 0))
    audio.setRandPos(d.get('rndpos', 0))
    audio.setRandPit(d.get('rndpit', 0))
    audio.setRandPan(d.get('rndpan', 0))
    audio.setRandFilterFreq(d.get('rndffr', 0.0))
    audio.setRandFilterQ(d.get('rndfqr', 0.0))
    audio.setDiscreteTrans(d.get('trans', [1.0]) or [1.0])
    audio.setDiscreteFilterTrans(d.get('ftrans', [1.0]) or [1.0])
    for name in Y_PARAMS:
        check = "y_%s_check" % name
        if name + "Check" in d:
            audio.setCheck(check, int(bool(d[name + "Check"])))
        key = "y_%s_map" % name
        if name + "Ymin" in d:
            audio.setMapMin(key, float(d[name + "Ymin"]))
        if name + "Ymax" in d:
            audio.setMapMax(key, float(d[name + "Ymax"]))
        mid = d.get(name + "Ymid", "")
        try:
            audio.setMapMid(key, float(mid))
        except (TypeError, ValueError):
            audio.setMapMid(key, None)


def applyControlState(audio, d):
    """Equaliser, compressor and level of the control panel."""
    for i, freq in enumerate(d.get('eqfreqs', [100, 500, 2000])):
        audio.setEqFreq(i, freq)
    for i, db in enumerate(d.get('eqamps', [0, 0, 0, 0])):
        audio.setEqGain(i, pow(10.0, db * 0.05))
    comp = d.get('compress', [-3, 2, 0.05, 0.2])
    for name, value in zip(("thresh", "ratio", "risetime", "falltime"), comp):
        audio.setCompParam(name, value)
    audio.setGlobalAmp(d.get('globalamp', 1.0))


def buildEngine(state, sound=None, overrides=None, sr=None, backend="offline"):
    """A scene and a booted engine from a project state. The caller sets the
    record options, starts and shuts down."""
    from .audio import SG_Audio
    scene = Scene()
    audio = SG_Audio(scene.clock, None, audio=backend)
    scene.audio = audio
    audio.space.update(state.get("Space", {}))
    if overrides:
        audio.space.update(overrides)
    scene.xSource = int(audio.space.get("xSource", 0))
    scene.ySource = int(audio.space.get("ySource", 0))
    scene.flock = float(audio.space.get("flock", 0.0))
    panel = state.get("ControlPanel", {})
    audio.boot(None, 0, int(sr or panel.get("sr", 44100)))
    envelope = state.get("Envelope", {}).get("envelope")
    if envelope:
        audio.env.replace([(int(x * 8191), y) for x, y in envelope])
    sound = sound or panel.get("sound", "")
    if not sound or not os.path.isfile(sound):
        raise FileNotFoundError("Sound file not found: %r" % sound)
    audio.loadSnd(sound)
    applyGranulatorState(audio, state.get("ControlFrame", {}))
    applyControlState(audio, panel)
    main = state.get("MainFrame", {})
    scene.lowpass = main.get("lowpass", True)
    scene.fillPoints = main.get("fillPoints", True)
    scene.editionLevel = main.get("editionLevel", 2)
    xfac, yfac = legacyFactors(state)
    if "Trajectories" in state:
        scene.setTrajectories(state, xfac, yfac)
    if "fxballs" in state:
        scene.setFxBalls(state["fxballs"], xfac, yfac)
    for t in scene.getAllTrajectories():
        t.initCounter()
        if t.getActive():
            audio.setTrajAmplitude(t.getId(), t.getAmplitude())
    return scene, audio


def render(state, out, dur=10.0, sound=None, overrides=None, sr=None, sampletype=3, recordBus=False):
    """Render 'dur' seconds of a project state to the sound file 'out'.

    overrides: values for the space (output, order, layout...) replacing the
    project's. With recordBus the file holds the Ambisonic bus (AmbiX) even if
    the output is something else. Returns (path, channels).
    """
    if isinstance(state, str):
        folder = os.path.dirname(os.path.abspath(state))
        state = loadProject(state)
        # as in the application: a sound that is not where the project says is looked for beside the project
        named = state.get("ControlPanel", {}).get("sound", "")
        if sound is None and named and not os.path.isfile(named):
            beside = os.path.join(folder, os.path.basename(named.replace("\\", "/")))
            if os.path.isfile(beside):
                sound = beside
    overrides = dict(overrides or {})
    if recordBus:
        overrides.update({"output": "Ambisonics"})
    scene, audio = buildEngine(state, sound, overrides, sr)
    try:
        audio.server.recordOptions(dur=dur, filename=out, fileformat=0, sampletype=sampletype)
        audio.start()
        channels = audio.chnls
    finally:
        audio.shutdown()
    return out, channels


def emptyState():
    """The state of a new project (what new_sondugrande_file.sgr holds)."""
    from .audio import SPACE_DEFAULTS
    from .Trajectory import Trajectory
    blank = Trajectory(None, 1).getAttributes()
    return {
        "version": SG_VERSION, "platform": PLATFORM,
        "MainFrame": {"draw": True, "lowpass": True, "fillPoints": True, "editionLevel": 2,
                      "size": (1200, 780)},
        "ControlFrame": {'density': 32, 'graindur': 200, 'graindev': 0, 'pitch': 1.0,
                         'filtfreq': 15000.0, 'filtq': 0.7, 'filtt': 0.0, 'rnddens': 0, 'rnddur': 0,
                         'rndpos': 0, 'rndpit': 0, 'rndpan': 0, 'rndffr': 0, 'rndfqr': 0,
                         'trans': [1.0], 'ftrans': [1.0], 'pitCheck': 1},
        "MidiSettings": None,
        "ControlPanel": {"type": 0, "closed": 0, "cutoff": 5000, "q": 0.5, "period": 2, "scaling": 1,
                         "eqfreqs": [100, 500, 2000], "eqamps": [0, 0, 0, 0],
                         "compress": [-3, 2, 0.05, 0.2], "globalamp": 1.0, "nchnls": 2, "sr": 44100,
                         "fileformat": 0, "sampletype": 0, "sound": "", "recfolder": "~/Desktop",
                         "filename": "snd", "drawOn": 0, "penHeight": 0.0, "sphereRadius": 1.0},
        "Space": dict(SPACE_DEFAULTS),
        "View": {"view": "3D"},
        "Trajectories": {str(i): dict(blank) for i in range(MAX_STREAMS)},
        "MemorizedTrajectory": dict(blank),
        "Envelope": {"envelope": [(0.0, 0), (0.3, 1), (0.7, 1), (1.0, 0)]},
        "fxballs": {},
    }


def main(argv):
    """Command line: --render project out.wav [--dur s] [--output mode] [--order n]
    [--layout name] [--sound file] [--sr rate] [--bus]"""
    import argparse
    parser = argparse.ArgumentParser(prog="Sondugrande --render",
                                     description="Render a Sondugrande (or SoundGrain) project offline.")
    parser.add_argument("project")
    parser.add_argument("out")
    parser.add_argument("--dur", type=float, default=10.0)
    parser.add_argument("--output", choices=["Binaural", "Stereo", "Ambisonics", "Speakers"])
    parser.add_argument("--order", type=int)
    parser.add_argument("--layout")
    parser.add_argument("--sound")
    parser.add_argument("--sr", type=int)
    parser.add_argument("--bus", action="store_true", help="write the Ambisonic bus (AmbiX)")
    args = parser.parse_args(argv)
    overrides = {}
    if args.output:
        overrides["output"] = args.output
    if args.order:
        overrides["order"] = args.order
    if args.layout:
        overrides["layout"] = args.layout
        overrides["customLayout"] = None
    path, channels = render(args.project, args.out, args.dur, args.sound, overrides, args.sr,
                            recordBus=args.bus)
    print("Rendered %s (%d channels, %.1f s)" % (path, channels, args.dur))
    return 0

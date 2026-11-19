"""Says whether pyo's own Harmonizer object works on this system.

SoundGrain's Harmonizer FX ball uses it. In the Linux x86-64 build of pyo 1.1.0
it was seen to give out nothing but NaN (under emulation); Sondugrande builds its
harmonizer from delay lines instead. This probe only reports: it never fails.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from pyo import Server, Sine, Harmonizer, getVersion

from sondugrande import wavio

path = os.path.join(tempfile.mkdtemp(prefix="pyo_probe_"), "harmonizer.wav")
server = Server(sr=44100, nchnls=1, buffersize=512, duplex=0, audio="offline").boot()
server.recordOptions(dur=0.5, filename=path, fileformat=0, sampletype=3)
source = Sine(440, mul=0.3)
out = Harmonizer(source, transpo=-7, feedback=0.25).out()
server.start()
samples, rate = wavio.read(path)
bad = int(np.sum(~np.isfinite(samples)))
print("pyo %s on %s: Harmonizer gives %s" % (".".join(map(str, getVersion())), sys.platform,
      "%d non-finite samples of %d (BROKEN here)" % (bad, samples.size) if bad else
      "sound, peak %.3f (works here)" % float(np.abs(samples).max())))

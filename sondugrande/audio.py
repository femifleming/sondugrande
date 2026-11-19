"""
Copyright 2009-2017 Olivier Belanger (SoundGrain)
Sondugrande additions: every grain stream is a source in space.

This file is part of Sondugrande, a derivative of SoundGrain.

Sondugrande is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Sondugrande is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Sondugrande.  If not, see <http://www.gnu.org/licenses/>.

The signal path
---------------
SoundGrain's sixteen granulators are kept as they are, except that each one
gives out a small cloud of CLOUD mono signals instead of a stereo pair: pyo's
Particle2 pans every grain between its outputs as the grain is born, so
SoundGrain's "Grains Panning" controls now place single grains round the
trajectory's point. Each cloud signal then goes through

    Delay (propagation time: Doppler)  ->  Tone (air absorption)  ->
    Ambisonic encoder (ACN / SN3D, 1st to 7th order, gains gliding from one
    clock tick to the next, level by distance)

into one Ambisonic bus. The FX balls are regions of the room: they take the
streams that pass through them and give their sound out from where they are.
A room reverb fed before the distance gain (so far sounds are wetter) comes
back from four directions. SoundGrain's equaliser and compressor run on the
bus (the compressor is keyed by the omni channel and moves every channel
alike, so it can't bend the image), and the output stage sends the bus out as
it is, or decodes it for headphones (magnitude least squares, KEMAR), for a
stereo pair, or for a loudspeaker layout (AllRAD).
"""

import math, time, random, os

import numpy as np

from .constants import *
from . import ambi, space

if SAMPLE_PRECISION == "64-bit":
    try:
        from pyo64 import *
    except:
        from pyo import *
else:
    from pyo import *

CLOUD = 4                      # mono signals per stream: the points grains are panned between
OUTPUT_MODES = ["Binaural", "Stereo", "Ambisonics", "Speakers"]
BINAURAL_ORDER = 3             # the headphone decoder reads the first 16 channels
REVERB_DIRS = np.array([[1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1]], dtype=float) / math.sqrt(3.0)

SPACE_DEFAULTS = {
    "output": "Binaural",      # one of OUTPUT_MODES
    "order": 3,                # Ambisonic order of the bus, 1..7
    "layout": "Octagon",       # loudspeaker layout name (ambi.LAYOUTS) for the "Speakers" output
    "customLayout": None,      # [(azimuth, elevation) or "LFE", ...] loaded from a file, with its name
    "customLayoutName": "",
    "recordBus": False,        # record the Ambisonic bus instead of the output
    "roomSize": 5.0,           # metres from the listener to the loudspeaker sphere
    "rolloff": 1.0,            # level falls as 1 / distance ^ rolloff outside the sphere
    "air": 0.5,                # air absorption with distance
    "doppler": 1.0,            # 0 = off, 1 = true to the room size
    "spread": 0.0,             # width of every source, 0 = a point, 1 = all round
    "scatter": 0.0,            # degrees: how far single grains land from the trajectory
    "reverb": 0.0,             # level of the room
    "reverbTime": 0.6,         # 0..1, how long the room rings
    "turn": 0.0,               # degrees: the whole scene turned about the listener
    "turnSpeed": 0.0,          # degrees per second
    "flock": 0.0,              # 0 = every stream on its trajectory, 1 = they fly as a flock (boids)
    "glide": 1.0,              # 0 = positions step with the timer, 1 = glide from tick to tick
    "xSource": 0,              # what picks the place in the sound (space.X_SOURCES)
    "ySource": 0,              # what drives the Y-axis parameters (space.Y_SOURCES)
}

_binauralCache = {}


def binauralFilters(order, sr):
    key = (order, int(sr))
    if key not in _binauralCache:
        from pyo.lib.hrtf import ImpulseResponseTables
        tables = ImpulseResponseTables().getTables()
        taps = 128 if sr < 60000 else 96
        _binauralCache[key] = ambi.binaural_filters(order, tables, sr=float(sr), taps=taps)
    return _binauralCache[key]


def soundInfo(sndfile):
    num_frames, dur, samprate, chans, fformat, stype = sndinfo(sndfile)
    return (chans, samprate, dur)

def checkForDrivers():
    driverList, driverIndexes = pa_get_output_devices()
    selectedDriver = pa_get_default_output()
    return driverList, driverIndexes, selectedDriver

def checkForInputDrivers():
    driverList, driverIndexes = pa_get_input_devices()
    return driverList, driverIndexes, pa_get_default_input()

def checkForMidiDrivers():
    driverList, driverIndexes = pm_get_input_devices()
    selectedDriver = pm_get_default_input()
    return driverList, driverIndexes, selectedDriver

def outputChannelCounts():
    """{device index: how many output channels it has}."""
    counts = {}
    try:
        driverList, driverIndexes = pa_get_output_devices()
        maxima = pa_get_output_max_channels
        for index in driverIndexes:
            try:
                count = int(maxima(index))
            except Exception:
                continue
            # some PortAudio builds answer 0 for every device: then it is not known
            if count > 0:
                counts[index] = count
    except Exception:
        pass
    return counts


class Fx:
    """One FX ball's effect: mono in, mono out, encoded where the ball is."""
    def __init__(self, input, fx=0, nch=16):
        self.input = Denorm(DCBlock(input))
        self.fx = fx
        if fx == 0:
            self.process = WGVerb(self.input, feedback=.95, cutoff=5000, bal=1, mul=.7)
        elif fx == 1:
            self.process = Delay(self.input, delay=.1, feedback=.75)
        elif fx == 2:
            self.process = Disto(self.input, drive=.9, slope=.75, mul=.2)
        elif fx == 3:
            self.process = Waveguide(self.input, freq=100, dur=30, mul=.3)
        elif fx == 4:
            self.process = ComplexRes(self.input, freq=500, decay=1)
        elif fx == 5:
            self.process = Degrade(self.input, bitdepth=8, srscale=0.25)
        elif fx == 6:
            # A harmonizer made of its parts: two delay lines swept by a ramp, half
            # a window apart, cross-faded. (pyo's own Harmonizer object, which
            # SoundGrain uses and which works the same way, gives out no numbers at
            # all on some systems, and one NaN in the bus silences everything.)
            self.winsize = 0.1
            self.fbk = SigTo(value=0.25, time=0.05, init=0.25)
            self.loop = Sig(0)                               # what comes back, one block late
            self.hsrc = self.input + self.loop
            self.hrate = SigTo(value=self.harmonizerRate(-7), time=0.05, init=self.harmonizerRate(-7))
            self.hpos = Phasor(freq=self.hrate, phase=[0, 0.5])
            self.htable = HannTable()
            self.hwin = Pointer(table=self.htable, index=self.hpos)
            self.hdel = Delay(self.hsrc, delay=self.hpos * self.winsize, maxdelay=self.winsize + 0.05, mul=self.hwin)
            self.process = Mix(self.hdel, voices=1)
            self.loop.value = self.process * self.fbk
        elif fx == 7:
            self.clip = Clip(self.input, min=-0.1, max=0.1, mul=3.3)
            self.process = ButLP(self.clip, freq=5000)
        elif fx == 8:
            self.lfo = Sine(freq=.2, mul=.0045, add=.005)
            self.flange = Delay(self.input, delay=self.lfo, feedback=.5)
            self.process = self.input + self.flange
        elif fx == 9:
            self.process = AllpassWG(self.input, freq=100, feed=0.999, detune=0.5, mul=.3)
        elif fx >= 10:
            self._makeMore(fx)
        self.level = SigTo(value=1, time=0.05, init=1)
        self.out = Sig(self.process, mul=self.level)
        self.spread = 0.25
        self.position = (space.HALF, space.HALF * 0.5, 0.0)   # canvas
        self.enc = SigTo(value=[0.0] * nch, time=0.05, init=0.0, mul=self.out)
        # kept for SoundGrain's name: what goes to the bus
        self.pan = self.enc

    # ------------------------------------------------------------------
    # the balls after Pinkie Pie's Balloon Palace (10-15) and Airwindows (16-19). Each keeps
    # its two controls in set1 / set2; their ranges are in constants.FX_BALL_SLIDER_*_INIT.
    # ------------------------------------------------------------------
    def _makeMore(self, fx):
        if fx == 10:
            # Snow: the spectrum held ringing, the way the Balloon Palace's snow freezes it. A
            # spectral reverb near infinite holds every partial; Frost is how bright the ice is.
            self.pva = PVAnal(self.input, size=4096, overlaps=8)
            self.pvv = PVVerb(self.pva, revtime=self.snowTime(0.8), damp=0.995)
            self.frost = SigTo(value=8000, time=0.05, init=8000)
            self.process = Tone(PVSynth(self.pvv, mul=0.6), freq=self.frost)
        elif fx == 11:
            # Heat: the sound melts into a slow wash that keeps drifting (the palace's heatwave):
            # every partial is smeared over seconds and its frequency wanders a little.
            self.pva = PVAnal(self.input, size=4096, overlaps=8)
            self.pvm = PVFreqMod(self.pva, basefreq=0.07, spread=0.6, depth=0.03)
            self.pvv = PVVerb(self.pvm, revtime=self.heatTime(0.7), damp=0.85)
            self.process = PVSynth(self.pvv, mul=0.6)
        elif fx == 12:
            # Rpeg: a ring modulator whose carrier climbs with the input's loudness (the palace's
            # ring modulator, after the ring-modulated hats on Autechre's Rpeg)
            self.rbase = SigTo(value=300, time=0.05, init=300)
            self.rfollow = SigTo(value=0.5, time=0.05, init=0.5)
            self.env = Follower(self.input, freq=12)
            self.carrier = Sine(freq=self.rbase * (1 + self.env * self.rfollow * 8))
            self.process = self.input * self.carrier
        elif fx == 13:
            # Spectral gate: only the partials above the threshold come through (the palace's
            # spectral gate); Damp lets the quiet ones through softened instead of cut
            self.pva = PVAnal(self.input, size=2048, overlaps=4)
            self.pvg = PVGate(self.pva, thresh=-30, damp=0.0)
            self.process = PVSynth(self.pvg)
        elif fx == 14:
            # Wind: gusts bend the pitch (the palace's wind) -- a short delay pushed about by a
            # slow random gust and a quicker flutter
            self.wrate = SigTo(value=0.5, time=0.05, init=0.5)
            self.wdepth = SigTo(value=0.5, time=0.05, init=0.5)
            self.gust = Randi(min=0, max=1, freq=self.wrate)
            self.flutter = Randi(min=-1, max=1, freq=self.wrate * 7)
            self.process = Delay(self.input, delay=0.002 + (self.gust + self.flutter * 0.15) * self.wdepth * 0.012, maxdelay=0.05)
        elif fx == 15:
            # Fog: every attack blurred (the palace's fog) -- a mist of five allpasses, then darker
            self.ffb = SigTo(value=0.6, time=0.05, init=0.6)
            self.fcut = SigTo(value=3000, time=0.05, init=3000)
            a = self.input
            self.fogs = []
            for d in (0.0131, 0.0179, 0.0233, 0.0311, 0.0419):
                a = Allpass(a, delay=d, feedback=self.ffb, maxdelay=0.05)
                self.fogs.append(a)
            self.process = Tone(a, freq=self.fcut)
        elif fx == 16:
            # Galactic (after Airwindows' Galactic): a huge, dark-edged reverb whose tail drifts
            self.gtime = SigTo(value=12, time=0.1, init=12)
            self.gdrift = SigTo(value=2.0, time=0.05, init=2.0)
            self.rev = STRev(self.input, inpos=0.5, revtime=self.gtime, cutoff=7000, bal=1, roomSize=2.5, firstRefGain=-20)
            self.process = Chorus(Mix(self.rev, voices=1), depth=self.gdrift, feedback=0.3, bal=0.6, mul=0.6)
        elif fx == 17:
            # ToTape (after Airwindows' ToTape): a tape echo -- wow and flutter on the head, the
            # tape's soft saturation and lost top in the loop. Changing the time glides, as tape does.
            self.ttime = SigTo(value=0.33, time=0.3, init=0.33)
            self.tfb = SigTo(value=0.45, time=0.05, init=0.45)
            self.tloop = Sig(0)                                  # what comes back, one block late
            self.wow = Sine(freq=0.55, mul=0.0018) + Randi(min=-0.0006, max=0.0006, freq=9)
            self.tdel = Delay(self.input + self.tloop, delay=self.ttime + self.wow, maxdelay=2.0)
            self.process = Tanh(ButLP(self.tdel, freq=4800) * 1.6, mul=0.6)
            self.tloop.value = self.process * self.tfb
        elif fx == 18:
            # Distance (after Airwindows' Distance): the sound far off -- later, quieter, the air
            # taking its top. Air is how much more the air takes.
            self.dpre = SigTo(value=0.04, time=0.1, init=0.04)
            self.dcut = SigTo(value=4800, time=0.1, init=4800)
            self.dair = SigTo(value=11800, time=0.1, init=11800)
            self.dlev = SigTo(value=0.5, time=0.1, init=0.5)
            self.process = Tone(Tone(Delay(self.input, delay=self.dpre, maxdelay=0.2), freq=self.dcut), freq=self.dair, mul=self.dlev)
            self.set1(0.5); self.set2(0.3)
        elif fx == 19:
            # Ensemble (after Airwindows' Ensemble): six voices, each its own slow drift
            self.edepth = SigTo(value=0.5, time=0.05, init=0.5)
            self.espeed = SigTo(value=1.0, time=0.05, init=1.0)
            rates = (0.31, 0.47, 0.61, 0.83, 1.07, 1.29)
            self.elfo = Sine(freq=[self.espeed * r for r in rates], phase=[i / 6.0 for i in range(6)], mul=self.edepth * 0.006, add=0.012)
            self.edel = Delay(self.input, delay=self.elfo, maxdelay=0.05)
            self.process = Mix(self.edel, voices=1, mul=0.35)

    @staticmethod
    def snowTime(v):
        return 0.85 + 0.149 * min(max(float(v), 0.0), 1.0)          # Freeze 0..1: long .. held

    @staticmethod
    def heatTime(v):
        return 0.6 + 0.38 * min(max(float(v), 0.0), 1.0)

    def set1(self, val):
        fx, val = self.fx, float(val)
        if fx == 10: self.pvv.revtime = self.snowTime(val)
        elif fx == 11: self.pvv.revtime = self.heatTime(val)
        elif fx == 12: self.rbase.value = val
        elif fx == 13: self.pvg.thresh = val
        elif fx == 14: self.wrate.value = val
        elif fx == 15: self.ffb.value = min(val, 0.9)
        elif fx == 16: self.gtime.value = val
        elif fx == 17: self.ttime.value = val
        elif fx == 18:
            d = min(max(val, 0.0), 1.0)
            self.dpre.value = 0.001 + 0.08 * d
            self.dcut.value = 18000.0 * (1.0 - d) ** 2 + 400.0
            self.dlev.value = 1.0 / (1.0 + 2.0 * d)
        elif fx == 19: self.edepth.value = val

    def set2(self, val):
        fx, val = self.fx, float(val)
        if fx == 10: self.frost.value = val
        elif fx == 11: self.pvm.depth = 0.1 * min(max(val, 0.0), 1.0)
        elif fx == 12: self.rfollow.value = val
        elif fx == 13: self.pvg.damp = min(max(val, 0.0), 1.0)
        elif fx == 14: self.wdepth.value = val
        elif fx == 15: self.fcut.value = val
        elif fx == 16: self.gdrift.value = val
        elif fx == 17: self.tfb.value = min(val, 0.95)
        elif fx == 18: self.dair.value = 16000.0 - 14000.0 * min(max(val, 0.0), 1.0)
        elif fx == 19: self.espeed.value = val

    def harmonizerRate(self, semitones):
        """How fast the delays must sweep to transpose by that many semitones."""
        return -(pow(2.0, float(semitones) / 12.0) - 1.0) / self.winsize

    def setGains(self, gains):
        for obj, value in zip(self.enc._base_objs, gains):
            obj.setValue(value)


class Granulator_Stream:
    def __init__(self, order, env, dens_noise, trans_noise, dur_noise, pit_noise, dev_noise,
                 pan_noise, ff_noise, fq_noise, ftype, clock_func, nch, sg_audio):
        self.sg_audio = sg_audio
        self.order = order
        self.env = env
        self.dens_noise = dens_noise
        self.pit_noise = pit_noise
        self.trans_noise = trans_noise
        self.dur_noise = dur_noise
        self.dev_noise = dev_noise
        self.pan_noise = pan_noise
        self.ff_noise = ff_noise
        self.fq_noise = fq_noise
        self.ftype = ftype
        self.clock_func = clock_func
        self.nch = nch
        self.granulator = None
        self.pointChain = []
        self.cloudChain = []
        self.scattered = False
        self.playing = False
        self.placed = False
        self.glide = 0.025
        self.transpoValue = 1.0
        self.yValues = {}
        self.ringTurn = random.uniform(0, 2 * math.pi)
        self.ringRate = random.uniform(0.15, 0.45) * random.choice([-1, 1])
        self.wobblePhase = [random.uniform(0, 2 * math.pi) for i in range(CLOUD)]
        self.wobbleRate = [random.uniform(0.5, 1.7) for i in range(CLOUD)]
        self.lastGains = None

        self.metro = Metro(time=0.025)
        self.base_pitch = SigTo(value=1, time=0.01)
        self.transpo = SigTo(value=1, time=0.001)
        self.traj_amp = SigTo(value=1, time=0.01, init=1)
        self.y_dns = SigTo(value=1, time=0.01)
        self.y_pit = SigTo(value=1, time=0.01)
        self.y_len = SigTo(value=1, time=0.01)
        self.y_dev = SigTo(value=1, time=0.01)
        self.y_amp = SigTo(value=1, time=0.01)
        self.y_pan = SigTo(value=0.5, time=0.01, mul=2, add=-1)
        self.y_fif = SigTo(value=1, time=0.01)
        self.y_fiq = SigTo(value=1, time=0.01)
        # one global noise for every voices ?
        self.y_trs = Randh(min=-1, max=1, freq=231, mul=0, add=1).stop()
        self.y_dur = Randh(min=-1, max=1, freq=201, mul=0, add=1).stop()
        self.y_pos = Randh(min=-1, max=1, freq=202, mul=0).stop()
        self.y_ffr = Randh(min=-1, max=1, freq=677, mul=0, add=1).stop()
        self.y_fqr = Randh(min=-1, max=1, freq=547, mul=0, add=1).stop()
        self.fader = SigTo(value=0, mul=0.05)
        # where in the cloud each new grain lands (sampled as the grain is born)
        self.cloud_pick = Randh(min=0, max=1, freq=random.uniform(900, 1300)).stop()
        # distance: propagation delay (Doppler when it moves) and air absorption
        self.dly = SigTo(value=0.0, time=0.025, init=0.0)
        self.airfreq = SigTo(value=20000.0, time=0.025, init=20000.0)
        self.trigger = TrigFunc(self.metro, self.clock_func, self.order)

    def create_granulator(self, table, pos_rnd):
        self.table = table
        self.pos_rnd = pos_rnd
        self.position = SigTo(value=0, time=0.01, mul=self.table.getSize(False))
        self.y_pos_rnd = Sig(self.y_pos, mul=self.table.getSize(False))
        nchnls = len(self.table)
        # the channels of the sound file sit evenly round the cloud
        if nchnls == 1:
            self.v_pan = 0.0
        else:
            self.v_pan = [i / float(nchnls) for i in range(nchnls)]
        self.granulator = Particle2( table=self.table,
                                    env=self.env,
                                    dens=self.dens_noise*self.y_dns,
                                    pitch=self.base_pitch*self.transpo*self.pit_noise*self.trans_noise*self.y_pit*self.y_trs,
                                    pos=self.position+self.pos_rnd+self.y_pos_rnd,
                                    dur=self.dur_noise*self.y_len*self.y_dur,
                                    dev=self.dev_noise+self.y_dev,
                                    pan=Wrap(self.y_pan+self.pan_noise+self.cloud_pick+self.v_pan, 0, 1),
                                    filterfreq=self.ff_noise*self.y_fif*self.y_ffr,
                                    filterq=self.fq_noise*self.y_fiq*self.y_fqr,
                                    filtertype=self.ftype,
                                    chnls=CLOUD,
                                    mul=self.fader*self.y_amp*self.traj_amp,
                                    ).stop()
        # the whole stream as one signal: what the FX balls and the room hear
        self.mono = Mix(self.granulator, voices=1).stop()
        # Two ways into the bus, of which one runs at a time.
        # The point: without scatter every grain is at the trajectory's point, so
        # the stream is one signal, delayed and filtered for its distance, with
        # one set of gains.
        self.delay1 = Delay(self.mono, delay=self.dly, maxdelay=1.0).stop()
        self.air1 = Tone(self.delay1, freq=self.airfreq).stop()
        self.enc1 = SigTo(value=[0.0] * self.nch, time=self.glide, init=0.0, mul=self.air1).stop()
        self.pointChain = [self.delay1, self.air1, self.enc1]
        # The cloud: with scatter the CLOUD outputs of the granulator are CLOUD
        # places round that point, each with its own gains (four times the work).
        self.cloud = Mix(self.granulator, voices=CLOUD).stop()
        self.delay = Delay(self.cloud, delay=self.dly, maxdelay=1.0).stop()
        self.air = Tone(self.delay, freq=self.airfreq).stop()
        self.enc = [SigTo(value=[0.0] * self.nch, time=self.glide, init=0.0, mul=self.air[k]).stop()
                    for k in range(CLOUD)]
        self.encoded = Mix(self.enc, voices=self.nch).stop()
        self.cloudChain = [self.cloud, self.delay, self.air] + self.enc + [self.encoded]
        self.scattered = False
        self.playing = False
        self.placed = False
        self.lastGains = None

    def ajustLength(self):
        self.position.mul = self.table.getSize(False)
        self.y_pos_rnd.mul = self.table.getSize(False)

    def setGain(self, x):
        self.fader.mul = x

    def setBasePitch(self, x):
        self.base_pitch.value = x

    def setGlide(self, seconds):
        seconds = max(0.003, float(seconds))
        if abs(seconds - self.glide) < 1e-6:
            return
        self.glide = seconds
        self.dly.time = seconds
        self.airfreq.time = seconds
        for enc in self.encoders():
            enc.time = seconds

    def encoders(self):
        if not hasattr(self, "enc1"):
            return []
        return [self.enc1] + self.enc

    def setSpatial(self, gains, delay, cutoff):
        """gains: array (1, channels) for a point, (CLOUD, channels) for a scattered stream."""
        scattered = len(gains) > 1
        if scattered != self.scattered:
            # the scatter was turned on or off: change over to the other way into the bus
            self.scattered = scattered
            if self.playing:
                for obj in (self.pointChain if scattered else self.cloudChain):
                    obj.stop()
                for obj in (self.cloudChain if scattered else self.pointChain):
                    obj.play()
            self.placed = False
        targets = self.enc if scattered else [self.enc1]
        if not self.placed:
            # first position: be there at once, don't fly in from nowhere
            self.dly.time = 0.001
            for enc in targets:
                enc.time = 0.001
        for k, enc in enumerate(targets):
            row = gains[k].tolist()
            for obj, value in zip(enc._base_objs, row):
                obj.setValue(value)
        self.dly.value = delay
        self.airfreq.value = cutoff
        if not self.placed:
            self.placed = True
            glide = self.glide
            self.glide = -1
            self.later = CallAfter(self.setGlide, 0.02, glide)
        self.lastGains = gains

    def setActive(self, val):
        if val == 1:
            self.metro.play()
            self.y_trs.play()
            self.y_dur.play()
            self.y_pos.play()
            self.y_ffr.play()
            self.y_fqr.play()
            self.cloud_pick.play()
            self.granulator.play()
            self.mono.play()
            for obj in (self.cloudChain if self.scattered else self.pointChain):
                obj.play()
            self.playing = True
            self.fader.value = 1
        else:
            self.fader.value = 0
            if self.sg_audio.started:
                self.latecall = CallAfter(self.real_stop, 0.075)
            else:
                self.real_stop()

    def real_stop(self):
        self.metro.stop()
        self.y_trs.stop()
        self.y_dur.stop()
        self.y_pos.stop()
        self.y_ffr.stop()
        self.y_fqr.stop()
        self.cloud_pick.stop()
        self.granulator.stop()
        self.mono.stop()
        for obj in self.pointChain + self.cloudChain:
            obj.stop()
        self.playing = False
        self.placed = False


class SG_Audio:
    def __init__(self, clock, refresh, controls=None, createTraj=None, deleteTraj=None, envFrame=None,
                 audio="portaudio"):
        self.started = False
        self.clock = clock
        self.refresh = refresh
        self.controls = controls
        self.createTraj = createTraj
        self.deleteTraj = deleteTraj
        self.envFrame = envFrame
        self.audioBackend = audio
        self.chnls = 2
        self.activeStreams = []
        self.fxs = {}
        self.samplingRate = 44100
        self.globalAmplitude = 1.0
        self.midiTriggerMethod = 0
        self.midiPitches = []
        self.midiVoices = {}
        self.ctlscan_callback = None
        self.bindings = {}
        self.space = dict(SPACE_DEFAULTS)
        self.basePitchValue = 1.0
        self.randPosValue = 0.0
        self.grainDurValue = 0.2
        self.tableDur = 1.0
        self.order = 3
        self.nch = 16
        self.booted = False
        self.busRecorder = None
        self.sceneAngle = 0.0
        self.sceneTime = None
        if audio == "portaudio":
            self.server = Server(sr=self.samplingRate, buffersize=512, duplex=1, ichnls=1)
        else:
            self.server = Server(sr=self.samplingRate, buffersize=512, duplex=0, audio=audio)
        self.server.deactivateMidi()
        self.micRecording = False
        self.inputAvailable = False
        self.check_dict = {"y_dns_check": 0, "y_pit_check": 1, "y_len_check": 0,
                           "y_dev_check": 0, "y_amp_check": 0, "y_trs_check": 0,
                           "y_dur_check": 0, "y_pos_check": 0, "y_pan_check": 0,
                           "y_fif_check": 0, "y_fiq_check": 0, "y_ffr_check": 0,
                           "y_fqr_check": 0}
        # map_dict: [min, max, exp, mid(optional)]
        self.map_dict = {"y_dns_map": [0, 1, 2, None], "y_pit_map": [0, 1, 1, None], "y_len_map": [0, 1, 1, None],
                         "y_dev_map": [0, 1, 1, None], "y_amp_map": [0, 1, 1, None], "y_trs_map": [0, 1, 3, None],
                         "y_dur_map": [0, 1, 4, None], "y_pos_map": [0, 1, 4, None], "y_pan_map": [0, 1, 1, None],
                         "y_fif_map": [0, 1, 2, None], "y_fiq_map": [0, 1, 2, None], "y_ffr_map": [0, 1, 1, None],
                         "y_fqr_map": [0, 1, 1, None]}

    # ------------------------------------------------------------------
    # the space: output format and the parameters of the room
    # ------------------------------------------------------------------
    def getLayout(self):
        """The loudspeaker layout of the "Speakers" output: [(az, el) or "LFE", ...]."""
        if self.space.get("customLayout"):
            return [tuple(e) if isinstance(e, (list, tuple)) else e for e in self.space["customLayout"]]
        return ambi.LAYOUTS.get(self.space["layout"], ambi.LAYOUTS["Octagon"])

    def outputChannels(self, settings=None):
        """How many channels the output device has to offer for the chosen output."""
        s = self.space if settings is None else settings
        mode = s["output"]
        if mode == "Ambisonics":
            return ambi.nch(int(s["order"]))
        if mode == "Speakers":
            if settings is None:
                return len(self.getLayout())
            layout = s.get("customLayout") or ambi.LAYOUTS.get(s["layout"], ambi.LAYOUTS["Octagon"])
            return len(layout)
        return 2

    def speakerDirections(self):
        """What the bus is decoded to, for the 3D view: [(output channel, room-frame unit vector), ...]."""
        mode = self.space["output"]
        if mode == "Speakers":
            return [(index + 1, tuple(space.ambi_to_room(d)))
                    for index, d in enumerate(ambi.layout_dirs(self.getLayout())) if d is not None]
        if mode == "Stereo":
            return [(1, (-1.0, 0.0, 0.0)), (2, (1.0, 0.0, 0.0))]
        return []

    def setSpace(self, name, value):
        """Change one parameter of the space. Output, order and layout only take
        effect at the next boot (the caller restarts the server)."""
        self.space[name] = value
        if not self.booted:
            return
        if name == "reverb":
            self.rev_level.value = float(value)
            self._runReverb(float(value) > 0.0)
        elif name == "reverbTime":
            self._setReverbTime(float(value))
        elif name == "glide":
            for st in self.streams.values():
                st.setGlide(self._glideFor(st))
        elif name == "scatter":
            pass
        if name in ("spread", "rolloff", "roomSize", "turn", "turnSpeed"):
            self.placeAllFx()

    def getSpace(self):
        return dict(self.space)

    def _glideFor(self, stream):
        period = float(stream.metro.time)
        glide = float(self.space["glide"])
        return max(0.003, min(period, 0.4) * glide)

    def _runReverb(self, on):
        """The room only works when it is heard."""
        if on == self.reverbRunning:
            return
        self.reverbRunning = on
        for obj in [self.rev_pre] + self.rev_taps + self.revs + self.rev_enc + [self.rev_out]:
            if on:
                obj.play()
            else:
                obj.stop()

    def _setReverbTime(self, x):
        x = max(0.0, min(1.0, x))
        for i, rev in enumerate(self.revs):
            rev.feedback = min(0.985, 0.55 + 0.43 * x - 0.01 * i)

    def sceneYaw(self):
        """The scene's turn about the listener right now, radians (to the left)."""
        now = self.server.getCurrentTimeInSamples() / float(self.samplingRate) if self.booted else 0.0
        if self.sceneTime is None:
            self.sceneTime = now
        self.sceneAngle += float(self.space["turnSpeed"]) * (now - self.sceneTime)
        self.sceneAngle %= 360.0
        self.sceneTime = now
        return math.radians(float(self.space["turn"]) + self.sceneAngle)

    def encodePoint(self, canvas_point, spread=None, yaw=None):
        """Bus gains and distance cues of a point of the room."""
        p = space.canvas_to_ambi(canvas_point)
        p = ambi.rotate_z(p, self.sceneYaw() if yaw is None else yaw)
        dist = float(np.linalg.norm(p))
        gain, delay, cutoff = space.distance_cues(dist, self.space["roomSize"], self.space["rolloff"],
                                                  self.space["air"], self.space["doppler"])
        s = self.space["spread"] if spread is None else spread
        return ambi.encode(p, self.order, s) * gain, delay, cutoff

    def setSpatial(self, which, canvas_point):
        """Move stream 'which' to a point of the room (called at every clock tick)."""
        if not getattr(self, "streams", None):
            return
        st = self.streams[which]
        if st.granulator is None:
            return
        p = space.canvas_to_ambi(canvas_point)
        p = ambi.rotate_z(p, self.sceneYaw())
        dist = float(np.linalg.norm(p))
        gain, delay, cutoff = space.distance_cues(dist, self.space["roomSize"], self.space["rolloff"],
                                                  self.space["air"], self.space["doppler"])
        angle = math.radians(float(self.space["scatter"]))
        if angle > 1e-4:
            period = float(st.metro.time)
            st.ringTurn += st.ringRate * period
            wobble = []
            for k in range(CLOUD):
                st.wobblePhase[k] += st.wobbleRate[k] * period
                wobble.append(0.5 + 0.5 * math.sin(st.wobblePhase[k]))
            pts = space.scatter_ring(p, angle, CLOUD, st.ringTurn, wobble)
        else:
            pts = p[None, :]
        gains = ambi.encode(pts, self.order, self.space["spread"]) * gain
        st.setSpatial(gains, delay, cutoff)

    def placeFx(self, key, canvas_point=None, spread=None):
        """Put an FX ball's sound at a point of the room."""
        if key not in self.fxs:
            return
        fx = self.fxs[key]
        if canvas_point is not None:
            fx.position = tuple(canvas_point)
        if spread is not None:
            fx.spread = float(spread)
        if not self.booted:
            return
        wide = 1.0 - (1.0 - fx.spread) * (1.0 - float(self.space["spread"]))
        gains, delay, cutoff = self.encodePoint(fx.position, spread=wide)
        fx.setGains(gains.tolist())

    def placeAllFx(self):
        for key in list(self.fxs.keys()):
            self.placeFx(key)

    # ------------------------------------------------------------------
    def setMidiListener(self, device):
        if hasattr(self, "listen"):
            self.listen.stop()
        self.listen = MidiListener(self.midirecv, device)
        self.listen.start()

    def boot(self, driver, chnls, samplingRate, inputDriver=None):
        """Start the audio server. chnls is ignored: the output format decides."""
        self.order = max(1, min(ambi.MAX_ORDER, int(self.space["order"])))
        self.nch = nch = ambi.nch(self.order)
        chnls = self.outputChannels()
        if self.audioBackend == "portaudio":
            self.server.setOutputDevice(driver)
            self.server.setDuplex(1 if inputDriver is not None else 0)
            if inputDriver is not None:
                self.server.setInputDevice(inputDriver)
        self.chnls = chnls
        self.server.setNchnls(chnls)
        self.samplingRate = samplingRate
        self.server.setSamplingRate(samplingRate)
        if self.controls is not None:
            self.server._server.setAmpCallable(getattr(self.controls, "meterFeed", self.controls.meter))
        try:
            self.server.boot()
        except Exception:
            if inputDriver is None:
                raise
        self.inputAvailable = inputDriver is not None and bool(self.server.getIsBooted())
        if not self.server.getIsBooted() and inputDriver is not None:
            self.server.setDuplex(0)
            self.server.boot()
        if not self.server.getIsBooted():
            raise RuntimeError("Could not start the audio server with the selected devices.")
        actual = int(self.server.getNchnls())
        if actual < chnls:
            # PortAudio opened the device with the channels it has
            self.server.shutdown()
            raise RuntimeError("the output device has %d channels and %s needs %d"
                               % (actual, self.space["output"], chnls))
        self.mixer = Mixer(outs=10, chnls=1)
        self.env = CosTable([(0,0),(2440,1),(5751,1),(8191,0)])
        if self.envFrame is not None:
            self.envFrame.setEnv(self.env)
        self.refresh_met = Metro(0.066666666666666666)
        self.refresh_func = TrigFunc(self.refresh_met, self.refresh_screen)
        self.latecalls = [None for i in range(MAX_STREAMS)]

        self.dens_noise = Randh(min=0, max=0, freq=25, mul=32, add=32)
        self.pit_noise = Randh(min=-1, max=1, freq=397, mul=0, add=1)
        self.pos_noise = Randh(min=-1, max=1, freq=199, mul=0)
        self.dur_noise = Randh(min=0, max=0, freq=198, mul=0.2, add=0.2)
        self.dev_noise = Sig(0)
        self.pan_noise = Randh(min=-1, max=1, freq=303, mul=0)
        self.trans_noise = Choice([1], freq=777)
        self.ffr_noise = Noise(mul=0, add=1)
        self.ffr_noise.setType(1)
        self.ff_noise = Choice(choice=[1.0], freq=999, mul=15000)
        self.fqr_noise = Noise(0.0, add=1.0)
        self.fqr_noise.setType(1)
        self.filterq = SigTo(0.7, time=0.05, init=0.7, mul=self.fqr_noise)
        self.filtert = SigTo(0.0, time=0.05, init=0.0)

        self.streams = {}
        for i in range(MAX_STREAMS):
            self.streams[i] = Granulator_Stream(i, self.env, self.dens_noise, self.trans_noise, self.dur_noise,
                                                self.pit_noise, self.dev_noise, self.pan_noise, self.ff_noise*self.ffr_noise,
                                                self.filterq, self.filtert, self.clock, nch, self)

        # the room: one send from every stream, back from four directions
        self.rev_level = SigTo(float(self.space["reverb"]), time=0.05, init=float(self.space["reverb"]))
        self.rev_in = Sig(0)
        self.rev_pre = Denorm(DCBlock(self.rev_in * self.rev_level))
        self.rev_taps = [Delay(self.rev_pre, delay=0.011 + 0.0077 * i, maxdelay=0.1) for i in range(4)]
        self.revs = [WGVerb(self.rev_taps[i], feedback=0.8, cutoff=4500 - 350 * i, bal=1, mul=0.35)
                     for i in range(4)]
        self._setReverbTime(float(self.space["reverbTime"]))
        rev_gains = ambi.sh(REVERB_DIRS, 1)
        self.rev_enc = [Sig(self.revs[i], mul=rev_gains[i].tolist()) for i in range(4)]
        # four streams (W, Y, Z, X): it must stay the last thing patched into the bus
        self.rev_out = Mix(self.rev_enc, voices=4)
        self.reverbRunning = True
        self._runReverb(float(self.space["reverb"]) > 0.0)

        # the Ambisonic bus
        self.stream_sum = Sig([0] * nch)
        self.eqFreq = [100, 500, 2000]
        self.eqGain = [1, 1, 1, 1]

        self.fbEqAmps = SigTo(self.eqGain, time=.1, init=self.eqGain)
        self.fbEq = FourBand(self.stream_sum, freq1=self.eqFreq[0],
                            freq2=self.eqFreq[1], freq3=self.eqFreq[2], mul=self.fbEqAmps)
        self.outEq = Mix(self.fbEq, voices=nch)

        # keyed by the omni channel, the same gain on every channel
        self.compLevel = Compress(self.outEq[0], thresh=-3, ratio=2, risetime=.05,
                                    falltime=.2, lookahead=5.0, knee=0.5, outputAmp=True)
        self.compDelay = Delay(self.outEq, delay=0.005)
        self.outComp = self.compDelay * self.compLevel
        self.bus = self.outComp
        self.makeOutput()
        self.booted = True
        self.sceneTime = None

    def makeOutput(self):
        """The output stage: the bus as it is, or decoded."""
        mode = self.space["output"]
        nch = self.nch
        self.decoder = []
        if mode == "Ambisonics":
            self.output = self.bus
            self.output.out()
            return
        if mode == "Binaural":
            order = min(self.order, BINAURAL_ORDER)
            filters, signs = binauralFilters(order, self.samplingRate)
            count = ambi.nch(order)
            taps = filters.shape[1]
            # The lows, which need the whole length, are all in the omni channel's
            # filter; the others have under a five-hundredth of their energy past
            # five eighths of it and are cut there (a third less work).
            short = max(16, int(taps * 0.625))
            fade = 0.5 * (1.0 + np.cos(np.linspace(0, math.pi, 8)))
            self.hrirTables = []
            self.convs = []
            for k in range(count):
                size = taps if k == 0 else short
                taps_k = np.array(filters[k, :size])
                if size < taps:
                    taps_k[-8:] *= fade
                self.hrirTables.append(DataTable(size=size, init=taps_k.tolist()))
                self.convs.append(Convolve(self.bus[k], self.hrirTables[k], size=size))
            self.left = Mix(self.convs, voices=1)
            self.right = Mix([Sig(self.convs[k], mul=float(signs[k])) for k in range(count)], voices=1)
            self.output = Mix([self.left, self.right], voices=2)
            self.output.out()
            return
        if mode == "Speakers":
            matrix = ambi.allrad(self.getLayout(), self.order)
        else:
            matrix = ambi.stereo_decoder(self.order)
        outs = matrix.shape[0]
        for k in range(nch):
            column = matrix[:, k]
            if np.all(np.abs(column) < 1e-9):
                continue
            self.decoder.append(Sig(self.bus[k], mul=column.tolist()))
        self.output = Mix(self.decoder, voices=outs)
        self.output.out()

    def shutdown(self):
        if self.micRecording:
            self.stopMic()
        self.booted = False
        if hasattr(self, "table"):
            del self.table
        if hasattr(self, "pos_rnd"):
            del self.pos_rnd
        self.streams = {}
        self.fxs = {}
        for name in ("env", "refresh_met", "refresh_func", "dens_noise", "pit_noise", "pos_noise",
                     "dur_noise", "dev_noise", "pan_noise", "trans_noise", "ffr_noise", "ff_noise",
                     "filterq", "filtert", "mixer", "fbEqAmps", "fbEq", "outEq", "compLevel",
                     "compDelay", "outComp", "bus", "output", "decoder", "convs", "hrirTables",
                     "left", "right", "rev_level", "rev_in", "rev_pre", "rev_taps", "revs",
                     "rev_enc", "rev_out", "stream_sum", "busRecorder"):
            if hasattr(self, name):
                delattr(self, name)
        self.busRecorder = None
        self.server.shutdown()

    def recStart(self, filename, fileformat=0, sampletype=0):
        filename, ext = os.path.splitext(filename)
        if fileformat >= 0 and fileformat < 8:
            ext = RECORD_EXTENSIONS[fileformat]
        else:
            ext = ".wav"
        date = time.strftime('_%d_%b_%Y_%Hh%M')
        if self.space.get("recordBus") and self.space["output"] != "Ambisonics":
            # the Ambisonic bus (AmbiX), whatever is being listened to
            complete_filename = filename + "_ambix%d" % self.order + date + ext
            self.busRecorder = Record(self.bus, complete_filename, chnls=self.nch,
                                      fileformat=fileformat, sampletype=sampletype)
        else:
            self.server.recordOptions(fileformat=fileformat, sampletype=sampletype)
            complete_filename = filename + date + ext
            self.server.recstart(complete_filename)
        self.lastRecording = complete_filename
        return complete_filename

    def recStop(self):
        if self.busRecorder is not None:
            self.busRecorder.stop()
            self.busRecorder = None
        else:
            self.server.recstop()

    def setEqFreq(self, which, freq):
        self.eqFreq[which] = freq
        if which == 0:
            self.fbEq.freq1 = freq
        elif which == 1:
            self.fbEq.freq2 = freq
        elif which == 2:
            self.fbEq.freq3 = freq

    def setEqGain(self, which, gain):
        self.eqGain[which] = gain
        self.fbEqAmps.value = self.eqGain

    def setCompParam(self, param, value):
        if param == "thresh":
            self.compLevel.thresh = value
        elif param == "ratio":
            self.compLevel.ratio = value
        elif param == "risetime":
            self.compLevel.risetime = value
        elif param == "falltime":
            self.compLevel.falltime = value

    def getTableDuration(self):
        return self.table.getDur(False)

    def loadSnd(self, sndPath):
        table = SndTable(sndPath)
        table.normalize()
        self.useTable(table)

    def patchBus(self):
        """(Re)connect everything that feeds the bus and the room."""
        ready = [st for st in self.streams.values() if st.granulator is not None]
        sources = [st.enc1 for st in ready] + [st.encoded for st in ready] \
            + [f.enc for f in self.fxs.values()] + [self.rev_out]
        self.stream_sum.value = Mix(sources, voices=self.nch)
        if ready:
            self.rev_in.value = Mix([st.mono for st in ready], voices=1)

    def useTable(self, table):
        self.table = table
        self.tableDur = float(table.getDur(False))
        self.pos_rnd = Sig(self.pos_noise, self.table.getSize(False))
        for gr in self.streams.values():
            gr.create_granulator(self.table, self.pos_rnd)
            gr.ajustLength()
            gr.setGlide(self._glideFor(gr))
        self.patchBus()
        for which in self.activeStreams:
            if which in self.mixer.getKeys():
                self.mixer.delInput(which)
            self.mixer.addInput(which, self.streams[which].mono)
            if self.started:
                self.streams[which].setActive(1)

    def startMic(self, length, finished):
        import wx
        if not self.inputAvailable:
            raise RuntimeError("No usable audio input is available. Check the input device in Settings.")
        if self.micRecording:
            raise RuntimeError("A microphone recording is already in progress.")
        table = NewTable(length=length, chnls=1)
        self.micInput = Input(chnl=0)
        self.micRecorder = TableRec(self.micInput, table=table)
        self.micTrigger = TrigFunc(self.micRecorder['trig'], lambda: wx.CallAfter(finished))
        if not self.server.getIsStarted():
            self.server.start()
        if not self.server.getIsStarted():
            raise RuntimeError("Could not start the audio server for microphone recording.")
        self.useTable(table)
        self.micRecording = True
        self.micRecorder.play()

    def stopMic(self):
        if not self.micRecording:
            return
        self.micRecording = False
        self.micRecorder.stop()
        self.micTrigger.stop()
        self.micInput.stop()
        del self.micRecorder, self.micTrigger, self.micInput
        if not self.started and self.server.getIsStarted():
            self.server.stop()

    def insertSnd(self, sndPath, start, end, point, cross):
        self.table.insert(sndPath, point, cross, start, end)
        self.pos_rnd.mul = self.table.getSize(False)
        self.tableDur = float(self.table.getDur(False))
        for gr in self.streams.values():
            gr.ajustLength()
        if self.server.getIsStarted():
            for which in self.activeStreams:
                self.streams[which].setActive(1)

    def setGlobalAmp(self, val):
        self.globalAmplitude = val
        self.server.amp = self.globalAmplitude

    def getViewTable(self, size, begin=0, end=0):
        if not hasattr(self, "table"):
            return []
        return self.table.getViewTable(size, begin, end)

    def setMidiMethod(self, value):
        self.midiTriggerMethod = value

    def getMidiMethod(self):
        return self.midiTriggerMethod

    def setDensity(self, x):
        self.dens_noise.add = x
        self.dens_noise.mul = x
        if x < 1:
            x = 1
        amp = 0.707/(math.log(x)+1)
        for gr in self.streams.values():
            gr.setGain(amp)

    def setRandDens(self, x):
        x = floatmap(x, exp=2)
        self.dens_noise.min = -x
        self.dens_noise.max = x

    def setBasePitch(self, x):
        self.basePitchValue = x
        for gr in self.streams.values():
            gr.setBasePitch(x)

    def setGrainDur(self, x):
        x *= 0.001
        self.grainDurValue = x
        self.dur_noise.add = x
        self.dur_noise.mul = x

    def setRandDur(self, x):
        x = floatmap(x, exp=2)
        self.dur_noise.min = -x
        self.dur_noise.max = x

    def setGrainDev(self, x):
        self.dev_noise.value = x

    def setFilterFreq(self, x):
        self.ff_noise.mul = x

    def setFilterQ(self, x):
        self.filterq.value = x

    def setFilterType(self, x):
        self.filtert.value = x

    def setRandPos(self, x):
        x = floatmap(x, min=0, max=0.5, exp=2)
        self.randPosValue = x
        self.pos_noise.mul = x

    def setRandPit(self, x):
        x = floatmap(x, exp=3)
        self.pit_noise.mul = x * 0.99

    def setRandPan(self, x):
        self.pan_noise.mul = x

    def setRandFilterFreq(self, x):
        self.ffr_noise.mul = x

    def setRandFilterQ(self, x):
        self.fqr_noise.mul = x

    def setDiscreteTrans(self, lst):
        self.trans_noise.choice = lst

    def setDiscreteFilterTrans(self, lst):
        self.ff_noise.choice = lst

    def setMetroTime(self, which, x):
        if not getattr(self, "streams", None):
            return
        self.streams[which].metro.time = x
        self.streams[which].setGlide(self._glideFor(self.streams[which]))

    def setTranspo(self, which, x):
        if not getattr(self, "streams", None):
            return
        self.streams[which].transpo.value = x
        self.streams[which].transpoValue = x

    def setTrajAmplitude(self, which, x):
        if not getattr(self, "streams", None):
            return
        self.streams[which].traj_amp.value = x

    def setCheck(self, which, state):
        self.check_dict[which] = state

    def setMapMin(self, which, value):
        self.map_dict[which][0] = value

    def setMapMax(self, which, value):
        self.map_dict[which][1] = value

    def setMapMid(self, which, value):
        self.map_dict[which][3] = value

    def setXposition(self, which, x):
        if not getattr(self, "streams", None):
            return
        if self.streams[which].granulator is None:
            return
        # A grain that would start before the sound or run past its end is not
        # played at all, so in SoundGrain a trajectory drops out at the edges
        # of the surface.
        # Here those edges are walls of the room: hold the place in the sound
        # where a whole grain still fits, the random part of its place included.
        st = self.streams[which]
        pitch = abs(self.basePitchValue * st.transpoValue * st.yValues.get("y_pit", 1.0))
        need = self.grainDurValue * st.yValues.get("y_len", 1.0) * pitch * 1.15 / max(self.tableDur, 1e-6)
        jitter = (abs(self.randPosValue) + abs(st.yValues.get("y_pos", 0.0))) * 1.02
        low = jitter
        high = 0.997 - need - jitter
        if high < low:
            low = high = max(0.0, min(0.997 - need, 0.5 * (low + high)))
        st.position.value = min(max(x, low), high)

    def setYposition(self, which, x):
        if not getattr(self, "streams", None):
            return
        params = [("y_dns", 1.0), ("y_pit", 1.0), ("y_len", 1.0), ("y_dev", 0.0),
                  ("y_pos", 0.0), ("y_trs", 0.0), ("y_dur", 0.0), ("y_amp", 1.0),
                  ("y_pan", 0.5), ("y_fif", 1.0), ("y_fiq", 1.0), ("y_ffr", 0.0),
                  ("y_fqr", 0.0)]
        for param, defval in params:
            if self.check_dict["%s_check" % param]:
                rng = self.map_dict["%s_map" % param]
                if rng[3] is None:
                    val = floatmap(x, rng[0], rng[1], rng[2])
                else:
                    if x < 0.5:
                        val = floatmap(x*2.0, rng[0], rng[3], rng[2])
                    else:
                        val = floatmap((x-0.5)*2.0, rng[3], rng[1], rng[2])
                getattr(self.streams[which], param).value = val
            else:
                val = defval
                getattr(self.streams[which], param).value = defval
            self.streams[which].yValues[param] = val
        return

    def setActive(self, which, val):
        if not getattr(self, "streams", None):
            return
        try:
            self.streams[which].setActive(val)
        except:
            pass
        if val == 1:
            if which not in self.activeStreams:
                self.activeStreams.append(which)
            if self.streams[which].granulator != None:
                if which in self.mixer.getKeys():
                    self.mixer.delInput(which)
                self.mixer.addInput(which, self.streams[which].mono)
        else:
            if which in self.activeStreams:
                self.latecalls[which] = CallAfter(self.stopStream, 0.075, which)

    def stopStream(self, which):
        if which in self.activeStreams:
            self.activeStreams.remove(which)
        if which in self.mixer.getKeys():
            self.mixer.delInput(which)

    def addFx(self, fx, key):
        self.fxs[key] = Fx(self.mixer[key], fx, self.nch)
        if self.server.getIsBooted():
            self.patchBus()
            self.placeFx(key)

    def removeFx(self, key):
        del self.fxs[key]
        if self.server.getIsBooted():
            self.patchBus()

    def setMixerChannelAmp(self, vin, vout, val):
        mixer = getattr(self, "mixer", None)
        if mixer is None:
            return
        if vin in mixer.getKeys():
            mixer.setAmp(vin, vout, val)

    def setMixerChannelAmps(self, trajs, fxballs):
        # Canvas repaints can arrive after the audio graph has been torn down.
        mixer = getattr(self, "mixer", None)
        if mixer is None:
            return
        keys = mixer.getKeys()
        for t in trajs:
            if t.getId() not in keys:
                continue
            for fx in fxballs:
                mixer.setAmp(t.getId(), fx.getId(), fx.getAmpValue(t.circlePos))

    def handleFxSlider1(self, fx, key, val):
        if fx == 0:
            self.fxs[key].process.feedback = val
        elif fx == 1:
            self.fxs[key].process.delay = val
        elif fx == 2:
            self.fxs[key].process.drive = val
        elif fx == 3:
            self.fxs[key].process.freq = val
        elif fx == 4:
            self.fxs[key].process.freq = val
        elif fx == 5:
            self.fxs[key].process.bitdepth = val
        elif fx == 6:
            self.fxs[key].hrate.value = self.fxs[key].harmonizerRate(val)
        elif fx == 7:
            self.fxs[key].clip.min = -val
            self.fxs[key].clip.max = val
            self.fxs[key].clip.mul = 1.0 / val * 0.33
        elif fx == 8:
            self.fxs[key].lfo.freq = val
        elif fx == 9:
            self.fxs[key].process.freq = val
        elif fx >= 10:
            self.fxs[key].set1(val)

    def handleFxSlider2(self, fx, key, val):
        if fx == 0:
            self.fxs[key].process.cutoff = val
        elif fx == 1:
            self.fxs[key].process.feedback = val
        elif fx == 2:
            self.fxs[key].process.slope = val
        elif fx == 3:
            self.fxs[key].process.dur = val
        elif fx == 4:
            self.fxs[key].process.decay = val
        elif fx == 5:
            self.fxs[key].process.srscale = val
        elif fx == 6:
            self.fxs[key].fbk.value = min(float(val), 0.98)
        elif fx == 7:
            self.fxs[key].process.freq = val
        elif fx == 8:
            self.fxs[key].flange.feedback = val
        elif fx == 9:
            self.fxs[key].process.detune = val
        elif fx >= 10:
            self.fxs[key].set2(val)

    def handleFxMul(self, key, val):
        self.fxs[key].level.value = val

    def handleFxPan(self, key, val):
        # SoundGrain's pan slider is the ball's spread here: where it is comes from the room
        self.placeFx(key, spread=val)

    def start(self):
        for which in self.activeStreams:
            self.setActive(which, 1)
        self.refresh_met.play()
        if not self.server.getIsStarted():
            self.server.start()
        self.server.amp = self.globalAmplitude
        self.started = True

    def stop(self):
        self.refresh_met.stop()
        self.started = False
        if self.micRecording:
            for which in self.activeStreams:
                self.streams[which].setActive(0)
        else:
            import wx
            wx.CallAfter(self.stopServerIfIdle)

    def stopServerIfIdle(self):
        if not self.started and not self.micRecording and self.server.getIsStarted():
            self.server.stop()

    def refresh_screen(self):
        if float(self.space["turnSpeed"]) != 0.0:
            self.placeAllFx()
        if self.refresh is not None:
            import wx
            wx.CallAfter(self.refresh)

    # Midi events handling
    def midirecv(self, status, data1, data2):
        # noteon
        if status & 0xF0 == 0x90 and data2 != 0:
            if self.midiVoices == {}:
                self.midiVoices[data1] = 0
                self.noteon(0, data1, data2)
            else:
                voices = self.midiVoices.values()
                voice = -1
                for i in range(16):
                    if i not in voices:
                        voice = i
                        break
                if voice != -1:
                    self.midiVoices[data1] = voice
                    self.noteon(voice, data1, data2)
        # noteoff
        elif status & 0xF0 == 0x90 and data2 == 0 or status & 0xF0 == 0x80:
            voice = None
            if data1 in self.midiVoices:
                voice = self.midiVoices[data1]
                del self.midiVoices[data1]
            if voice is not None:
                self.noteoff(voice)
        # control change
        if status & 0xF0 == 0xB0:
            midichnl = status - 0xB0 + 1
            if self.ctlscan_callback is not None:
                self.ctlscan_callback(data1, midichnl)
                self.ctlscan_callback = None
            if data1 in self.bindings:
                for callback in self.bindings[data1]:
                    callback(data2)

    def ctlscan(self, callback):
        self.ctlscan_callback = callback

    def bind(self, x, callback):
        if x in self.bindings:
            self.bindings[x].append(callback)
        else:
            self.bindings[x] = [callback]

    def unbind(self, x, callback):
        if x in self.bindings:
            if callback in self.bindings[x]:
                self.bindings[x].remove(callback)
                if not self.bindings[x]:
                    del self.bindings[x]

    def noteon(self, voice, pit, vel):
        if self.midiTriggerMethod == 0:
            hz, vel = midiToTranspo(pit), vel / 127.0
            self.createTraj(voice, hz, vel, pit)
        elif self.midiTriggerMethod == 1:
            vel = vel / 127.0
            if pit not in self.midiPitches:
                self.midiPitches.append(pit)
                self.createTraj(pit, midiToTranspo(pit), vel, pit)
            else:
                self.midiPitches.remove(pit)
                self.deleteTraj(pit)

    def noteoff(self, voice):
        if self.midiTriggerMethod == 0:
            self.deleteTraj(voice)

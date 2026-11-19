Introduction
============

Welcome to the Songrande 1.0.0 documentation.
----------------------------------------------

Songrande is SoundGrain in a room. In SoundGrain you draw trajectories over a
sound and every trajectory plays a stream of grains from the places it passes
over. In Songrande the sound lies on the floor of a room, the pen can leave the
floor, and where a trajectory goes is also where its sound is heard: around
you, above you, near and far.

Songrande is a development of SoundGrain 6.1.0 by Olivier Belanger, a graphical
interface where users can draw and edit trajectories to control granular sound
synthesis. Everything SoundGrain does is still here and works the same way.
Like SoundGrain it is written with Python and WxPython and uses Pyo as its
audio engine.

GNU GPL v3. SoundGrain (c) Olivier Belanger 2009-2018, Songrande (c) femifleming 2026.

### On the web: ###

Songrande source code: __https://github.com/femifleming/songrande__

SoundGrain source code: __https://github.com/belangeo/soundgrain__

Pyo source code: __https://github.com/belangeo/pyo__


Getting Started
---------------

Getting sound with Songrande is as easy as:

- Loading a soundfile (Menu -> File -> Open Soundfile...). Its waveform appears
  on the floor of the room.
- Drawing a trajectory in the room with the mouse.
- Activating the audio by clicking on the "Start" button.

Here you should get some output sound, on headphones to begin with: the sound
is where the little ball is, and moves with it.

After that:

- hold __Cmd__ (__Ctrl__ on Windows and Linux) while you draw, or turn the wheel,
  to pull the pen up off the floor;
- drag with the right button (or hold __Alt__) to walk round the room, and use
  the __Top__, __Front__ and __Side__ views to place things exactly
  (see [The Room](02_surface.md));
- draw on the __Sphere__ in place of the floor to keep a sound at one distance;
- choose where the sound goes in File -> Open Settings: headphones, two
  loudspeakers, a loudspeaker layout, or Ambisonics for a decoder
  (see [Space](07_space.md));
- open the Space Controls (Menu -> File -> Open Space Controls) for distance,
  Doppler, grain scatter and the room's reverb;
- play with the granulator controls (Menu -> File -> Open Granulator Controls)
  and with the effects balls (Menu -> FxBall), which are regions of the room.

You can record the generated sound to disk with the "Rec Start" button at the
bottom of the control panel. Choose the recording format, destination and
filename in File -> Open Settings (Ctrl+;).

A SoundGrain project (.sg) opens in Songrande: its surface becomes the floor.

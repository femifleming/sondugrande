Space
=====

Every trajectory is a stream of grains and a source of sound in the room. All
of them are encoded into one Ambisonic scene, which is sent out as it is or
decoded for what you listen on.

______________________________________________________________________________

Output (File -> Open Settings)
------------------------------

##### Binaural (headphones) #####

Two channels for headphones. The scene is decoded with head-related filters
(magnitude least squares, from the MIT KEMAR measurements), the way the IEM
BinauralDecoder does it. This is the default.

##### Stereo (two loudspeakers) #####

Two channels: left and right. Height and front - back are not heard.

##### Ambisonics (to a decoder) #####

The scene itself, in the AmbiX format (ACN channel order, SN3D normalisation):
4 channels at 1st order, 9 at 2nd, 16 at 3rd, 25 at 4th, 36 at 5th, 49 at 6th
and 64 at 7th. Send it to a decoder of the same order, such as the IEM
AllRADecoder (loudspeakers) or BinauralDecoder (headphones), or a SPARTA
decoder; choose SN3D there. The output device needs that many channels: with a
virtual device of 16 or 64 channels Songrande can play straight into a track
of REAPER.

##### Loudspeakers #####

One channel per loudspeaker of the chosen __Layout__, decoded with the AllRAD
method. The loudspeakers are drawn in the room, numbered by channel. Besides
the built-in layouts, __Load layout...__ reads a layout saved by the IEM
AllRADecoder or SPARTA (a JSON file). An LFE channel gets no signal.

##### Order #####

The Ambisonic order of the scene, 1 to 7: the higher, the sharper the sources
(and the more channels and work). The headphone decoder reads the first 16
channels (3rd order).

##### Record the Ambisonic bus (AmbiX) instead of what is heard #####

With this ticked, __Rec Start__ writes the Ambisonic scene (all its channels)
while you listen on headphones or loudspeakers.

If the output device has too few channels for the format, Songrande says so in
the status bar and plays on headphones (Binaural) instead.

______________________________________________________________________________

Space Controls (File -> Open Space Controls, Ctrl+L)
----------------------------------------------------

Right-click a slider to assign a MIDI controller to it, as in the Granulator
Controls.

- __Room Size__: how many metres it is from you to the loudspeaker sphere. It
  sets the time sound takes to reach you (so the Doppler shift of a moving
  sound) and how much the air takes off.
- __Distance Rolloff__: how fast a sound gets softer outside the sphere and
  louder inside it. At 1 the level follows 1 / distance; at 0 distance does
  not change the level.
- __Air Absorption__: far sounds lose their highs.
- __Doppler__: a sound coming towards you rises in pitch, one going away falls.
  0 turns it off.
- __Source Spread__: 0 is a point, 1 a sound that comes from all round you.
- __Grain Scatter__: single grains land this many degrees away from the
  trajectory, all round it: a cloud in place of a point. SoundGrain's
  _Grains Panning_ controls move grains round this cloud. A scattered stream
  is four times the work of a plain one.
- __Room Reverb Level__ and __Time__: a room round the whole scene. Far sounds
  are wetter than near ones.
- __Scene Turn__ and __Turning Speed__: turn everything about you, by an angle
  or steadily. The head in the room turns the other way to show it.
- __Flock__: the balls leave their lines and fly together, each on a leash to
  its own trajectory: drawn towards the others, along with them, and not too
  close. At 0 every ball is on its line.
- __Motion__: at the right the sound glides from one clock tick of a trajectory
  to the next; at the left it steps with the timer (hear it with a slow
  __Timer speed__).

The __Mapping__ tab chooses what SoundGrain's X (the place in the sound) and Y
(the Y-axis parameters) follow:

- X: __Left - right__ (SoundGrain's own), __Azimuth__ (the sound is laid round
  you, clockwise from the front, and drawn that way), __Along the path__ (from
  the start of a trajectory to its end), or __Height__.
- Y: __Front - back__ (SoundGrain's own), __Height__, __Distance__ or
  __Elevation__.

______________________________________________________________________________

Rendering offline
-----------------

A saved project can be rendered to a file without the application's window,
faster than real time:

    Songrande --render project.sgr out.wav --dur 60 --output Ambisonics --order 5

Options: __--output__ Binaural, Stereo, Ambisonics or Speakers; __--order__ 1 to 7;
__--layout__ name; __--bus__ (write the Ambisonic scene whatever the output);
__--sound__ file; __--sr__ rate.

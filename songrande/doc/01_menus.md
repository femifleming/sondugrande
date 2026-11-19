Menu Bar
========

This section provides documentation for the menu items located in the
menu bar of the application. OSX users should replace the shortcut _Ctrl_ 
key with the _Cmd_ key.

______________________________________________________________________________

File Menu
---------

##### New... (*Ctrl+N*) #####
    
Closes the current project (ask to save if modified) and starts a new one.

##### Open... (*Ctrl+O*) #####

Open a previously created .sgr file, or a SoundGrain .sg file (its surface
becomes the floor of the room; it is then saved as a new .sgr file).

##### Open Recent... #####

Reopen one of the last 10 opened or saved projects. The most recent project is
listed first. This list is remembered between sessions. If a project has been
moved or deleted, selecting it displays a message and removes it from the list.

##### Open Soundfile... (*Shift+Ctrl+O*) #####

Import a new sound into the drawing area.

##### Insert Soundfile... (*Shift+Ctrl+I*) #####

Insert a new sound (with crossfade) into the current drawing area.

##### Save (*Ctrl+S*) #####

Save the current state of the project.

##### Save As... (*Shift+Ctrl+S*) #####

Save the current state of the project in a new .sgr file.

##### Open Settings (*Ctrl+;*) #####

Opens the Settings window, which contains __Audio Settings__, __Project Settings__
and __Record Settings__.

In __Audio Settings__, choose the input and output audio devices and sample
precision. The device lists are updated at startup, and devices cannot be
changed during playback or microphone recording. Changing sample precision
requires restarting Songrande.

In __Project Settings__, choose the __Sample rate__ and the __Output__: headphones
(Binaural), two loudspeakers (Stereo), Ambisonics for a decoder, or a
loudspeaker __Layout__, and the Ambisonic __Order__. __Channels__ shows how many
channels that is; the audio device must have as many. See [Space](07_space.md).
These controls are disabled while audio playback is running.

In __Record Settings__, choose the audio file __Format__ and __Sample type__.
Enter the output folder path in __Destination__, or click __Choose__ to select
it with a folder dialog.

Enter a base name in __Filename__, without an extension. Songrande automatically
appends the date, time and the extension for the selected format to avoid
overwriting an existing file.

Settings take effect immediately. Click __Close__ or press __Escape__ to close
the window. Start and stop recording with the __Rec Start__ / __Rec Stop__ button
at the bottom of the main window's control panel.

##### Open Granulator Controls (*Ctrl+P*) #####

Open the [granulator's parameters window](04_granulator.md). This window, 
in the tab called 'Granulator', allows the user to change the density of 
grains per second, the global transposition, the grain duration, the grain 
start time deviation (synchronous vs asynchronous) and various randoms 
applied to the granulator. In the second tab, called 'Y axis', one can 
decide on which parameters, and its range, the Y axis of the drawing area 
will be mapped. Available parameters are: Density of grains, transposition, 
grain duration, start time deviation, amplitude, grain panning and various 
per grain randoms applied to the granulator.

##### Open Space Controls (*Ctrl+L*) #####

Open the [Space controls window](07_space.md): the size of the room, distance,
Doppler, spread, grain scatter, reverb, the turning of the scene, and what the
X and Y of the granulator follow.

##### Open Envelope Window (*Ctrl+E*) #####

Open a grapher window to modify the shape of the grain's envelope.

##### Run (*Ctrl+R*) #####

Start/stop audio processing.

______________________________________________________________________________

Drawing Menu
------------

##### Undo, Redo (*Ctrl+Z, Shift+Ctrl+Z*) #####

Unlimited undo and redo stages for the drawing area (only trajectories).

##### Draw Waveform  #####

If checked, the loaded soundfile's waveform will be drawn behind the trajectories.

##### Activate Lowpass filter  #####

If checked, all points of a new trajectory will be filtered using a lowpass 
filter. Controls of the filter are located in the Drawing section of the control 
panel. This can be used to smooth out the trajectory or to insert resonance in 
the curve when the Q is very high.

##### Fill points  #####

If checked, spaces between points in a trajectory (especially when stretching 
the curve) will be filled with additional points. If unchecked, the number of 
points in the trajectory won't change, allowing synchronization between similar 
trajectories.

##### Edition levels  #####

Set the modification spread of a trajectory when edited with the mouse (higher 
values mean narrower transformations).

##### Arrow Moves Speed levels  #####

This value controls how many pixels the trajectory(ies) will move when an arrow 
key is pressed with the focus is on the drawing surface.

##### Reinit counters  (*Ctrl+T*) #####

Re-sync the trajectories's counters (automatically done when audio is started).

______________________________________________________________________________

View Menu
---------

##### 3D, Top, Front, Side view (*P, T, F, S*) #####

Where the room is seen from. See [The Room](02_surface.md).

##### Reset view (*Esc*) #####

Put the view back where it started.

##### Draw on the floor / sphere / view (*G*) #####

The surface under the pen.

______________________________________________________________________________

Space Menu
----------

What can be done to the selected trajectory in the room: duplicate, mirrored
twin, flips, turn, tilts, raise and lower, larger and smaller, wrap onto the
sphere, flatten. The letter after each item is its key, with the focus on the
room. All of them can be undone.

##### Load a loudspeaker layout (IEM / SPARTA JSON)... #####

Use a loudspeaker layout saved by the IEM AllRADecoder or SPARTA for the
__Loudspeakers__ output.

______________________________________________________________________________

Midi Menu
---------

##### Memorize Trajectory (*Shift+Ctrl+M*) ######

Memorize the state of the selected trajectory The ensuing snapshot will be the 
initial state for trajectories triggered by MIDI notes.

##### Midi Settings... ######

Open the MIDI configuration and controls window.

See the [Midi Controls page](06_midi.md) for the detail about how to use MIDI 
with Soundgrain.

______________________________________________________________________________

FxBall Menu
-----------

FxBalls allow the user to add effect regions on the drawing surface. Only the
trajectories that cross a ball (and only for the time that the trajectory is
inside the ball) will send their audio output through the chosen effect.

See the [FX Balls page](05_fxballs.md) for the detail about available effects.

##### Add Reverb ball (*Ctrl+1*) #####

Create a reverb region on the drawing surface.

##### Add Delay ball (*Ctrl+2*) #####

Create a recursive delay region on the drawing surface.

##### Add Disto ball (*Ctrl+3*) #####

Create a distortion region on the drawing surface.

##### Add Waveguide ball (*Ctrl+4*) #####

Create a resonator region on the drawing surface.

##### Add Complex Resonator ball (*Ctrl+5*) #####

Create a very selective resonating region on the drawing surface.

##### Add Degrade ball (*Ctrl+6*) #####

Create a degradation region on the drawing surface.

##### Add Harmonizer ball (*Ctrl+7*) #####

Create a harmonization region on the drawing surface.

##### Add Clipper ball (*Ctrl+8*) #####

Create a hard clipping region on the drawing surface.

##### Add Flanger ball (*Ctrl+9*) #####

Create a flanging region on the drawing surface.

##### Add Detuned Resonator ball (*Ctrl+0*) #####

Create an allpass-detuned resonator region on the drawing surface.


The Room
========

The room takes the place of SoundGrain's drawing surface. The loaded soundfile
is shown on its floor, exactly as SoundGrain showed it: left to right is the
sound from its start to its end, back to front is SoundGrain's Y axis. The
floor is at the height of your ears, you are the small head in the middle
(the nose points to the front), and the circle round you is the loudspeaker
sphere: a sound on it is at its normal level, a sound inside it is nearer and
louder, a sound outside it further and softer.

A trajectory is a line through this room. Its place over the floor chooses the
grains, as in SoundGrain; its place in the room is where they are heard.
Thin lines drop from a trajectory to the floor, and its shadow lies there, so
that you can see how high it is.

______________________________________________________________________________

Looking at the room
-------------------

The buttons at the top left (and the __View__ menu, and the keys below) choose
where the room is seen from:

- __3D__: from where you like. Drag with the right button, or hold Alt and
  drag, to walk round it.
- __Top__: from above. This is SoundGrain's own surface.
- __Front__: from behind you, looking forward: left - right and height.
- __Side__: from your left: front - back and height.

##### Vertical scroll #####

Come closer or step back.

##### Horizontal scroll or Shift+scroll #####

Turn the room (3D view).

##### Right-click (or Alt+click) and drag in an empty space #####

Walk round the room. From one of the flat views this goes back to the 3D view.

##### Escape key #####

Put the view back where it started.

______________________________________________________________________________

What the pen draws on
---------------------

The second row of buttons (and the __Draw on__ popup of the control panel)
chooses the surface under the pen:

- __Floor__: a level plane. It starts at ear level; the __Pen height__ slider of
  the __3D__ tab moves it up or down (a blue square shows where it is).
- __Sphere__: the loudspeaker sphere, on the side that faces you. The
  __Sphere radius__ slider of the __3D__ tab makes it smaller or larger.
  Circles, oscillations and spirals drawn on it are wrapped round it.
- __View__: the plane that faces you, through the middle of the room. In the
  Front and Side views the pen always draws on this plane.

##### Cmd (Ctrl on Windows and Linux) while drawing or dragging #####

Pull the pen off its surface: straight up or down from the floor, in or out on
the sphere, towards you or away on the view plane. Move the mouse up and down.
Let go of the key and the pen goes on drawing at its new height, so a line can
climb in steps or in a slope, in one gesture.

##### Vertical scroll while drawing or dragging #####

The same, with the wheel.

At the bottom right the room shows where the pen is: X (seconds in the sound),
Y, Z (height), then the azimuth, elevation and distance from you.

______________________________________________________________________________

Mouse Bindings
--------------

##### Left-click and drag in an empty space #####

Create a new trajectory.

##### Left-click and drag on red rectangle #####

Move the trajectory, level (or in the plane facing you in the Front and Side
views). With Cmd/Ctrl: up and down.

##### Left-click and drag on red rectangle while holding Shift key #####

Move all trajectories.

##### Right-click on red rectangle #####

Delete the trajectory.

##### Alt+click (or double-click) on red rectangle #####

Duplicate the trajectory.

##### Left-click on blue diamond #####

Scale the size of a circle, oscil or spiral trajectory.

##### Left-click and drag on a trajectory line #####

Modify the shape of the trajectory (see "Edition levels"). With Cmd/Ctrl the
line is pulled up or down: this is the way to raise a part of a trajectory that
was drawn flat. In the Front and Side views a plain drag does it.

##### Left-click on the middle part of an FxBall #####

Move the ball (with Cmd/Ctrl: up and down).

##### Left-click on the border part of an FxBall #####

Resize the ball.

##### Right-click on the middle part of an FxBall #####

Open the effect's parameters window.

##### Alt+click (or double-click) on an FxBall #####

Delete the ball.

##### Shift+click on the middle part of an FxBall, up and down motion #####

Change the effects's fadein/fadeout ramp time.

______________________________________________________________________________

Keyboard Bindings
-----------------

With the focus on the room (click in it first):

##### P / T / F / S #####

3D (perspective), Top, Front and Side view.

##### G #####

Draw on the floor, the sphere, the view plane, and round again.

##### Delete key #####

Delete the selected trajectory.

##### Arrow keys #####

Move all trajectories over the floor.

##### Shift + arrow keys #####

Move the selected trajectory.

##### Cmd/Ctrl + up and down arrows (with Shift: the selected one) #####

Raise and lower.

##### D #####

Duplicate the selected trajectory.

##### M #####

Make a twin of the selected trajectory, mirrored left to right.

##### H / V / U #####

Flip the selected trajectory left - right / front - back / up - down around
its center.

##### R / Shift+R / Ctrl+Shift+R #####

Turn the selected trajectory by 15 / 5 / 1 degrees about the vertical.

##### X and Y (with Shift and Ctrl+Shift as for R) #####

Tilt the selected trajectory: X lifts its front, Y its side.

##### [ and ] #####

Lower and raise the selected trajectory.

##### - and = #####

Make the selected trajectory smaller and larger.

##### Z #####

Wrap the selected trajectory onto the sphere (of the radius of the __3D__ tab):
every point keeps its direction and goes to that distance.

##### B #####

Flatten the selected trajectory to its mean height.

All these can be undone, and are also in the __Space__ menu.

##### 1 to 8 (not on numeric keypad) #####

Freeze/unfreeze the selected trajectory.

##### 0 (not on numeric keypad) #####

Freeze/unfreeze all trajectories.

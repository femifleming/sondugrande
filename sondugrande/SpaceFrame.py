"""
Sondugrande - the Space Controls window: how the room sounds.

Built like SoundGrain's Granulator Controls window, with the same sliders
(right-click one to learn a MIDI controller).

This file is part of Sondugrande, a derivative of SoundGrain (Olivier Belanger).

Sondugrande is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""
import wx
from .constants import *
from .Modules import SGControlSlider
from . import space

# name, label, min, max, default, integer, log
SLIDERS = [
    ("roomSize", "Room Size: metres from you to the loudspeaker sphere", 1.0, 50.0, 5.0, False, True),
    ("rolloff", "Distance Rolloff (0 = no change of level, 1 = natural)", 0.0, 2.0, 1.0, False, False),
    ("air", "Air Absorption with Distance", 0.0, 2.0, 0.5, False, False),
    ("doppler", "Doppler (0 = off, 1 = true to the room size)", 0.0, 1.0, 1.0, False, False),
    ("spread", "Source Spread (0 = a point, 1 = all round you)", 0.0, 1.0, 0.0, False, False),
    ("scatter", "Grain Scatter round the Trajectory (degrees)", 0.0, 90.0, 0.0, False, False),
    ("reverb", "Room Reverb Level", 0.0, 1.0, 0.0, False, False),
    ("reverbTime", "Room Reverb Time", 0.0, 1.0, 0.6, False, False),
    ("turn", "Scene Turn (degrees to the left)", -180.0, 180.0, 0.0, False, False),
    ("turnSpeed", "Scene Turning Speed (degrees per second)", -90.0, 90.0, 0.0, False, False),
    ("flock", "Flock: the balls leave their lines and fly together", 0.0, 1.0, 0.0, False, False),
    ("glide", "Motion: steps with the timer <--> glides", 0.0, 1.0, 1.0, False, False),
]


class SpaceFrame(wx.Frame):
    def __init__(self, parent, sg_audio):
        wx.Frame.__init__(self, parent, -1, "Space controls")
        menuBar = wx.MenuBar()
        self.menu = wx.Menu()
        self.menu.Append(200, 'Close\tCtrl+W', "")
        self.menu.AppendSeparator()
        self.menu.Append(201, "Run\tCtrl+R", "", wx.ITEM_CHECK)
        menuBar.Append(self.menu, "&File")
        self.SetMenuBar(menuBar)

        self.Bind(wx.EVT_CLOSE, self.handleClose)
        self.Bind(wx.EVT_MENU, self.handleClose, id=200)
        self.Bind(wx.EVT_MENU, self.onRun, id=201)

        self.parent = parent
        self.sg_audio = sg_audio
        self.sliders = {}
        self.values = {}

        self.panel = wx.Panel(self, -1)
        self.notebook = wx.Notebook(self.panel, -1, style=wx.BK_DEFAULT | wx.EXPAND)
        self.panel1 = wx.Panel(self.notebook, wx.ID_ANY)
        self.panel2 = wx.Panel(self.notebook, wx.ID_ANY)
        self.box1 = wx.BoxSizer(wx.VERTICAL)
        self.box2 = wx.BoxSizer(wx.VERTICAL)

        self.box1.AddSpacer(10)
        for name, label, low, high, init, integer, log in SLIDERS:
            self.values[name] = init
            self.sliders[name] = self.makeSliderBox(self.box1, label, low, high, init, integer, log,
                                                    self.makeHandler(name))
        self.panel1.SetSizerAndFit(self.box1)
        self.notebook.AddPage(self.panel1, "Room")

        # what the place of a point in the room does to the granulator
        font = None
        for label, choices, attr in [
                ("Place in the sound (SoundGrain's X) follows", space.X_SOURCES, "xSource"),
                ("Y-axis parameters (SoundGrain's Y) follow", space.Y_SOURCES, "ySource")]:
            text = wx.StaticText(self.panel2, -1, label)
            font = text.GetFont()
            font.SetPointSize(font.GetPointSize() - (1 if PLATFORM == "win32" else 2))
            text.SetFont(font)
            self.box2.Add(text, 0, wx.LEFT | wx.TOP, 10)
            choice = wx.Choice(self.panel2, -1, choices=choices)
            choice.SetSelection(0)
            choice.Bind(wx.EVT_CHOICE, lambda evt, a=attr: self.handleSource(a, evt.GetInt()))
            self.box2.Add(choice, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
            setattr(self, attr + "Choice", choice)
        note = wx.StaticText(self.panel2, -1,
            "With the first choices the floor of the room is\n"
            "SoundGrain's surface: left to right runs through\n"
            "the sound, back to front is the Y axis.\n\n"
            "Azimuth lays the sound round you, clockwise\n"
            "from the front. Along the path plays it from the\n"
            "start of a trajectory to its end.\n\n"
            "The output format (headphones, loudspeakers,\n"
            "Ambisonics) is in Settings.")
        note.SetFont(font)
        self.box2.Add(note, 0, wx.ALL, 10)
        self.panel2.SetSizerAndFit(self.box2)
        self.notebook.AddPage(self.panel2, "Mapping")

        box = wx.BoxSizer(wx.VERTICAL)
        box.Add(self.notebook, 1, wx.ALL, 5)
        self.panel.SetSizerAndFit(box)

        self.Fit()
        X, Y = self.GetSize()
        self.SetMinSize((X, Y))
        self.SetMaxSize((X, Y))
        self.SetPosition((self.parent.GetPosition()[0] + 60, self.parent.GetPosition()[1] + 60))
        self.Show(False)

    def onRun(self, event):
        self.parent.onRun(event)

    def handleClose(self, event):
        self.Show(False)

    def makeSliderBox(self, box, label, minval, maxval, val, integer, log, callback):
        staticLabel = wx.StaticText(self.panel1, -1, label)
        font, psize = staticLabel.GetFont(), staticLabel.GetFont().GetPointSize()
        if PLATFORM == "win32":
            font.SetPointSize(psize-1)
        else:
            font.SetPointSize(psize-2)
        box.AddSpacer(5)
        staticLabel.SetFont(font)
        box.Add(staticLabel, 0, wx.LEFT, 10)
        sliderBox = wx.BoxSizer(wx.HORIZONTAL)
        slider = SGControlSlider(self.panel1, minval, maxval, val, size=(300, 16),
                                 log=log, integer=integer, outFunction=callback)
        sliderBox.Add(slider, 1, wx.LEFT | wx.RIGHT, 5)
        box.Add(sliderBox, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)
        box.AddStretchSpacer(1)
        return slider

    def makeHandler(self, name):
        def handler(x, fromSlider=True):
            # pyo sliders also call their function when they repaint
            if fromSlider and abs(x - self.values.get(name, x)) < 1e-9:
                return
            self.values[name] = x
            self.sg_audio.setSpace(name, x)
            if name == "flock":
                self.parent.panel.scene.flock = float(x)
            if fromSlider:
                self.parent.is_unsaved = True
            if name in ("turn", "turnSpeed"):
                self.parent.panel.Refresh()
        return handler

    def handleSource(self, attr, index):
        self.sg_audio.setSpace(attr, int(index))
        setattr(self.parent.panel.scene, attr, int(index))
        self.parent.panel.Refresh()
        self.parent.is_unsaved = True

    def setCustomLayout(self, layout, name):
        self.parent.controls.setCustomLayout(layout, name)

    def save(self):
        state = self.sg_audio.getSpace()
        for name, slider in self.sliders.items():
            state[name + "_m"] = slider.getMidiBinding()
        return state

    def load(self, d):
        for name, label, low, high, init, integer, log in SLIDERS:
            value = float(d.get(name, init))
            value = max(low, min(high, value))
            self.values[name] = value
            self.sliders[name].SetValue(value, False)
            self.sg_audio.setSpace(name, value)
            if name == "flock":
                self.parent.panel.scene.flock = value
            self.sliders[name].setMidiBinding(d.get(name + "_m", None))
        for attr in ("xSource", "ySource"):
            index = int(d.get(attr, 0))
            getattr(self, attr + "Choice").SetSelection(index)
            self.sg_audio.setSpace(attr, index)
            setattr(self.parent.panel.scene, attr, index)
        self.parent.panel.Refresh()

"""
Copyright 2009-2017 Olivier Belanger (SoundGrain)

This file is part of Songrande, a derivative of SoundGrain: the window of an
FX ball and its picture. The ball itself (a sphere in the room) is scene.Ball.

Songrande is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

SoundGrain is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with SoundGrain.  If not, see <http://www.gnu.org/licenses/>.
"""
import wx, math
from .constants import *
from pyo.lib._wxwidgets import ControlSlider

class FxBallControls(wx.Frame):
    def __init__(self, parent, fxball, sg_audio, size=(270, 200)):
        title = "%s Controls" % FX_BALL_TITLES[fxball.getFx()]
        wx.Frame.__init__(self, parent, -1, title, size=size)
        self.parent = parent
        self.fxball = fxball
        self.sg_audio = sg_audio
        menuBar = wx.MenuBar()
        self.menu = wx.Menu()
        self.menu.Append(200, 'Close\tCtrl+W', "")
        menuBar.Append(self.menu, "&File")
        self.SetMenuBar(menuBar)

        self.Bind(wx.EVT_CLOSE, self.handleClose)
        self.Bind(wx.EVT_MENU, self.handleClose, id=200)

        self.panel = wx.Panel(self, -1)
        self.box = wx.BoxSizer(wx.VERTICAL)

        sl1values = FX_BALL_SLIDER_1_INIT[fxball.getFx()]
        sl2values = FX_BALL_SLIDER_2_INIT[fxball.getFx()]

        text = wx.StaticText(self.panel, -1, sl1values[0])
        font, psize = text.GetFont(), text.GetFont().GetPointSize()
        font.SetPointSize(psize-1)
        text.SetFont(font)
        self.box.Add(text, 0, wx.LEFT|wx.RIGHT|wx.TOP, 10)
        self.box.AddSpacer(2)
        self.slider1 = ControlSlider(self.panel, sl1values[1], sl1values[2], sl1values[3], log=sl1values[4], size=(250,16), outFunction=self.handleSlider1)
        self.box.Add(self.slider1, 0, wx.LEFT|wx.RIGHT, 10)

        text = wx.StaticText(self.panel, -1, sl2values[0])
        text.SetFont(font)
        self.box.Add(text, 0, wx.LEFT|wx.RIGHT|wx.TOP, 10)
        self.box.AddSpacer(2)
        self.slider2 = ControlSlider(self.panel, sl2values[1], sl2values[2], sl2values[3], log=sl2values[4], size=(250,16), outFunction=self.handleSlider2)
        self.box.Add(self.slider2, 0, wx.LEFT|wx.RIGHT, 10)

        text = wx.StaticText(self.panel, -1, "Amplitude")
        text.SetFont(font)
        self.box.Add(text, 0, wx.LEFT|wx.RIGHT|wx.TOP, 10)
        self.box.AddSpacer(2)
        self.slider3 = ControlSlider(self.panel, 0, 2, 1, size=(250,16), outFunction=self.handleMul)
        self.box.Add(self.slider3, 0, wx.LEFT|wx.RIGHT, 10)

        # SoundGrain's pan: the ball sounds from where it is in the room, so
        # this is how wide its sound is (0 a point, 1 all round the listener)
        text = wx.StaticText(self.panel, -1, "Spread")
        text.SetFont(font)
        self.box.Add(text, 0, wx.LEFT|wx.RIGHT|wx.TOP, 10)
        self.box.AddSpacer(2)
        self.slider4 = ControlSlider(self.panel, 0, 1, 0.25, size=(250,16), outFunction=self.handlePan)
        self.box.Add(self.slider4, 0, wx.LEFT|wx.RIGHT|wx.BOTTOM, 10)

        self.panel.SetSizerAndFit(self.box)

        if PLATFORM == "win32":
            X, Y = self.GetSize()[0], self.GetSize()[1] + 50
        elif PLATFORM.startswith("linux"):
            X, Y = self.GetSize()[0], self.GetSize()[1] + 40
        else:
            X, Y = self.GetSize()[0], self.GetSize()[1] + 20
        self.SetMinSize((X, Y))
        self.SetMaxSize((X, Y))
        wx.CallAfter(self.SetSize, (X, Y))

    def handleClose(self, event):
        self.Show(False)

    def _ready(self):
        return self.fxball.getId() in getattr(self.sg_audio, "fxs", {})

    def handleSlider1(self, val):
        self.fxball.sliders["slider1"] = val
        if self._ready():
            self.sg_audio.handleFxSlider1(self.fxball.getFx(), self.fxball.getId(), val)

    def handleSlider2(self, val):
        self.fxball.sliders["slider2"] = val
        if self._ready():
            self.sg_audio.handleFxSlider2(self.fxball.getFx(), self.fxball.getId(), val)

    def handleMul(self, val):
        self.fxball.sliders["slider3"] = val
        if self._ready():
            self.sg_audio.handleFxMul(self.fxball.getId(), val)

    def handlePan(self, val):
        self.fxball.sliders["slider4"] = val
        if self._ready():
            self.sg_audio.handleFxPan(self.fxball.getId(), val)

    def save(self):
        return {"slider1": self.slider1.GetValue(),
                "slider2": self.slider2.GetValue(),
                "slider3": self.slider3.GetValue(),
                "slider4": self.slider4.GetValue()}

    def load(self, dict):
        dict = {"slider1": self.slider1.GetValue(), "slider2": self.slider2.GetValue(),
                "slider3": 1.0, "slider4": 0.25, **{k: v for k, v in dict.items() if v is not None}}
        self.slider1.SetValue(dict["slider1"])
        self.handleSlider1(self.slider1.GetValue())
        self.slider2.SetValue(dict["slider2"])
        self.handleSlider2(self.slider2.GetValue())
        self.slider3.SetValue(dict["slider3"])
        self.handleMul(self.slider3.GetValue())
        self.slider4.SetValue(dict["slider4"])
        self.handlePan(self.slider4.GetValue())

def getColors(col, gradient):
    gradient = int(gradient)
    if col == 0:
        firstColor = wx.Colour(255,30,255)
        secondColor = wx.Colour(gradient,30,gradient)
    elif col == 1:
        firstColor = wx.Colour(30,255,255)
        secondColor = wx.Colour(30,gradient,gradient)
    elif col == 2:
        firstColor = wx.Colour(255,255,30)
        secondColor = wx.Colour(gradient,gradient,30)
    elif col == 3:
        firstColor = wx.Colour(30,255,30)
        secondColor = wx.Colour(30,gradient,30)
    elif col == 4:
        firstColor = wx.Colour(30,30,255)
        secondColor = wx.Colour(30,30,gradient)
    elif col == 5:
        firstColor = wx.Colour(255,30,30)
        secondColor = wx.Colour(gradient,30,30)
    elif col == 6:
        firstColor = wx.Colour(255,255,255)
        secondColor = wx.Colour(gradient,gradient,gradient)
    elif col == 7:
        firstColor = wx.Colour(255,127,30)
        secondColor = wx.Colour(gradient,gradient//2,30)
    elif col == 8:
        firstColor = wx.Colour(255,30,127)
        secondColor = wx.Colour(gradient,30,gradient//2)
    elif col == 9:
        firstColor = wx.Colour(127,30,255)
        secondColor = wx.Colour(gradient//2,30,gradient)
    return firstColor, secondColor

def GetRoundMaskBitmap(w, h, radius):
    w, h = max(1, int(round(w))), max(1, int(round(h)))
    # Downsample a larger coverage mask so edge pixels have partial opacity.
    # Cache it with the ball; changing the gradient can reuse the same mask.
    scale = 4
    bitmap = wx.Bitmap(w * scale, h * scale)
    dc = wx.MemoryDC(bitmap)
    dc.SetBackground(wx.Brush(wx.BLACK))
    dc.Clear()
    dc.SetPen(wx.TRANSPARENT_PEN)
    dc.SetBrush(wx.Brush(wx.WHITE))
    dc.DrawRoundedRectangle(0, 0, w * scale, h * scale, radius * scale)
    dc.SelectObject(wx.NullBitmap)
    image = bitmap.ConvertToImage()
    image = image.Scale(w, h, wx.IMAGE_QUALITY_HIGH)
    return wx.Bitmap(image)

def GetRoundBitmap(w, h, mask, col, gradient):
    w, h = max(1, int(round(w))), max(1, int(round(h)))
    firstColor, secondColor = getColors(col, gradient)
    bitmap = wx.Bitmap(w, h)
    dc = wx.MemoryDC(bitmap)
    dc.GradientFillConcentric(wx.Rect(0, 0, w, h), firstColor, secondColor, (w//2, h//2))
    dc.SelectObject(wx.NullBitmap)
    image = bitmap.ConvertToImage()
    # Express the gradient as opacity instead of shading toward black, so
    # the waveform remains visible through the ball's outer region. Raising
    # the gradient still makes the ball more opaque, matching its audio fader.
    colors = image.GetData()
    coverage = mask.ConvertToImage().GetData()[::3]
    alpha = bytearray(w * h)
    for index, edge_alpha in enumerate(coverage):
        offset = index * 3
        brightness = max(colors[offset:offset + 3])
        opacity = max(0, min(255, (brightness - 30) * 255 // 225))
        alpha[index] = edge_alpha * opacity // 255
    image.SetData(bytes((firstColor.Red(), firstColor.Green(), firstColor.Blue())) * (w * h))
    image.SetAlpha(bytes(alpha))
    return wx.Bitmap(image)


class BallPicture:
    """The picture of an FX ball: SoundGrain's round gradient, made once at a
    fixed size and drawn scaled wherever the ball is in the view."""
    SIZE = 96

    def __init__(self, ball):
        self.ball = ball
        self.mask = GetRoundMaskBitmap(self.SIZE, self.SIZE, self.SIZE / 2)
        self.gradient = None
        self.bit = None
        self.update()

    def update(self):
        gradient = int(self.ball._gradient)
        if gradient != self.gradient:
            self.gradient = gradient
            self.bit = GetRoundBitmap(self.SIZE, self.SIZE, self.mask, self.ball.getFx(), gradient)
        return self.bit

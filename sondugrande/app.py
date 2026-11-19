"""
Sondugrande - the application object (SoundGrain's, with the room in place of
the drawing surface).

Copyright 2009-2017 Olivier Belanger (SoundGrain). This file is part of
Sondugrande, a derivative of SoundGrain, released under the GNU General Public
License version 3 or later.
"""
import sys
import wx

from .constants import *
from .splash import SoundGrainSplashScreen
from .MainFrame import MainFrame


class SondugrandeApp(wx.App):
    def __init__(self, *args, **kwargs):
        wx.App.__init__(self, *args, **kwargs)
        self.SetAppName(NAME)
        sysx = wx.SystemSettings.GetMetric(wx.SYS_SCREEN_X)
        sysy = wx.SystemSettings.GetMetric(wx.SYS_SCREEN_Y)
        if sysx < 1200:
            sizex = sysx - 40
        else:
            sizex = 1200
        self.frame = MainFrame(None, -1, pos=(0, 20), size=(sizex, -1),
                               screen_size=(sysx, sysy))
        # Size the content area directly: frame size conversions do not account
        # for the space occupied by menus and the status bar on every platform.
        controls = self.frame.controls
        panel_height = controls.GetSizer().GetMinSize().height
        panel_height += controls.GetSize().height - controls.GetClientSize().height
        client_width = self.frame.GetClientSize().width
        self.frame.SetClientSize((client_width, panel_height))
        sizey = self.frame.GetSize().height
        self.frame.SetSize((sizex, min(sizey, sysy - 40)))
        self.frame.Layout()

    def MacOpenFiles(self, filenames):
        if type(filenames) is not list:
            filenames = [filenames]
        if hasattr(self, "frame"):
            self.frame.loadFile(ensureNFD(filenames[0]))

    def MacReopenApp(self):
        try:
            self.frame.Raise()
        except:
            pass


def run(project=None, splash=True):
    app = SondugrandeApp(redirect=False)
    if splash:
        SoundGrainSplashScreen(None, SPLASH_FILE, app.frame)
    else:
        app.frame.Show()
    if project:
        wx.CallAfter(app.frame.loadFile, ensureNFD(project))
    app.MainLoop()
    return 0

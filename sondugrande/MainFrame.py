# encoding: utf-8
"""
Copyright 2009-2017 Olivier Belanger (SoundGrain)

This file is part of Sondugrande, a derivative of SoundGrain.

Sondugrande is free software: you can redistribute it and/or modify
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
import os, wx, time, json
from .constants import *
from .audio import *
from .Modules import *
from pyo.lib._wxwidgets import ControlSlider, Grapher
from .MidiSettings import MidiSettings
from .CommandFrame import CommandFrame
from .Surface3D import Surface3D
from .ControlPanel import ControlPanel
from .SpaceFrame import SpaceFrame
from .scene import legacyFactors
from .audio import SPACE_DEFAULTS
from . import space, ambi

# the part of the space that says where the sound goes
FORMAT_KEYS = ("output", "order", "layout", "customLayout", "customLayoutName", "recordBus")

if sys.version_info[0] < 3:
    import xmlrpclib
else:
    import xmlrpc.client as xmlrpclib

if "phoenix" in wx.version():
    from wx.adv import AboutDialogInfo, AboutBox
else:
    from wx import AboutDialogInfo, AboutBox


def silenceSliderCallbacks(window):
    """Prevent queued slider repaints from calling the torn-down audio graph."""
    if isinstance(window, ControlSlider):
        window.outFunction = None
    for child in window.GetChildren():
        silenceSliderCallbacks(child)

class EnvelopeFrame(wx.Frame):
    def __init__(self, parent, size=(600, 300)):
        wx.Frame.__init__(self, parent, -1, "Envelope Shape", size=size)
        self.parent = parent
        self.env = None
        menuBar = wx.MenuBar()
        self.menu = wx.Menu()
        self.menu.Append(200, 'Close\tCtrl+W', "")
        menuBar.Append(self.menu, "&File")
        self.SetMenuBar(menuBar)

        self.Bind(wx.EVT_CLOSE, self.handleClose)
        self.Bind(wx.EVT_MENU, self.handleClose, id=200)

        self.graph = Grapher(self, init=[(0.0,0),(0.3,1),(0.7,1),(1.0,0)], mode=1)

        self.Show(False)

    def setEnv(self, env):
        self.env = env
        self.env.replace(self.graph.getValues())
        self.graph.outFunction = self.env.replace

    def handleClose(self, event):
        self.Hide()

    def save(self):
        return {'envelope': self.graph.getPoints()}

    def load(self, dict):
        self.graph.setInitPoints(dict.get('envelope', [(0.0,0),(0.3,1),(0.7,1),(1.0,0)]))
        if self.env != None:
            self.env.replace(self.graph.getValues())

class MainFrame(wx.Frame):
    def __init__(self, parent, id, pos, size, screen_size):
        wx.Frame.__init__(self, parent, id, "", pos, size)
        self.SetMinSize((600,300))
        self.screen_size = screen_size
        self.is_unsaved = False
        self.currentFile = None
        self.currentPath = None
        self.temps = []
        self.draw = True
        self.lowpass = True
        self.fillPoints = True
        self.editionLevels = [2, 4, 8, 12, 16, 24, 32, 50]
        self.editionLevel = 2
        self.arrowSpeedLevels = [1, 2, 4, 8, 16, 32]
        self.arrowSpeedLevel = 1
        self.audioDriver = None
        self.inputDriver = None
        self.recall = self.undos = 0
        self.sample_precision = SAMPLE_PRECISION

        self.status = wx.StatusBar(self, -1)
        self.SetStatusBar(self.status)

        self.menuBar = wx.MenuBar()
        self.menu = wx.Menu()
        self.menu.Append(11, "New...\tCtrl+N")
        self.Bind(wx.EVT_MENU, self.handleNew, id=11)
        self.menu.Append(1, "Open...\tCtrl+O")
        self.Bind(wx.EVT_MENU, self.handleOpen, id=1)
        self.recentProjects = []
        self.recentProjectsMenu = wx.Menu()
        self.menu.AppendSubMenu(self.recentProjectsMenu, "Open Recent...")
        self.recentProjectIds = [wx.NewIdRef() for _ in range(10)]
        for menu_id in self.recentProjectIds:
            self.Bind(wx.EVT_MENU, self.handleOpenRecent, id=int(menu_id))
        self.menu.Append(2, "Open Soundfile...\tShift+Ctrl+O")
        self.Bind(wx.EVT_MENU, self.handleLoad, id=2)
        self.menu.Append(12, "Insert Soundfile...\tShift+Ctrl+I")
        self.Bind(wx.EVT_MENU, self.handleInsert, id=12)
        self.menu.Append(3, "Save\tCtrl+S")
        self.Bind(wx.EVT_MENU, self.handleSave, id=3)
        self.menu.Append(4, "Save as...\tShift+Ctrl+S")
        self.Bind(wx.EVT_MENU, self.handleSaveAs, id=4)
        self.menu.AppendSeparator()
        settings_item = self.menu.Append(wx.ID_ANY, "Open Settings\tCtrl+;")
        self.Bind(wx.EVT_MENU, lambda event: self.controls.openSettings(event), settings_item)
        self.menu.Append(6, "Open Granulator Controls\tCtrl+P")
        self.Bind(wx.EVT_MENU, self.openFxWindow, id=6)
        self.menu.Append(8, "Open Space Controls\tCtrl+L")
        self.Bind(wx.EVT_MENU, self.openSpaceWindow, id=8)
        self.menu.Append(5, "Open Envelope Window\tCtrl+E")
        self.Bind(wx.EVT_MENU, self.openEnvelopeWindow, id=5)
        self.menu.AppendSeparator()
        self.menu.Append(7, "Run\tCtrl+R", "", wx.ITEM_CHECK)
        self.Bind(wx.EVT_MENU, self.onRun, id=7)
        self.menu.AppendSeparator()
        quit_item = self.menu.Append(wx.ID_EXIT, "Quit\tCtrl+Q")
        self.Bind(wx.EVT_MENU, self.OnClose, id=wx.ID_EXIT)
        self.menuBar.Append(self.menu, "&File")

        self.menu1 = wx.Menu()
        self.menu1.Append(110, "Undo\tCtrl+Z", "")
        self.menu1.Enable(110, False)
        self.Bind(wx.EVT_MENU, self.handleUndo, id=110)
        self.menu1.Append(111, "Redo\tShift+Ctrl+Z", "")
        self.menu1.Enable(111, False)
        self.Bind(wx.EVT_MENU, self.handleUndo, id=111)
        self.menu1.InsertSeparator(2)
        self.menu1.Append(100, "Draw Waveform", "", wx.ITEM_CHECK)
        self.menu1.Check(100, True)
        self.Bind(wx.EVT_MENU, self.handleDrawWave, id=100)
        self.menu1.Append(101, "Activate Lowpass filter", "", wx.ITEM_CHECK)
        self.menu1.Check(101, True)
        self.Bind(wx.EVT_MENU, self.handleActivateLp, id=101)
        self.menu1.Append(102, "Fill points", "", wx.ITEM_CHECK)
        self.menu1.Check(102, True)
        self.Bind(wx.EVT_MENU, self.handleActivateFill, id=102)
        self.submenu1 = wx.Menu()
        for i, level in enumerate(self.editionLevels):
            menuId = 1000 + i
            self.submenu1.Append(menuId, str(level), "", wx.ITEM_RADIO)
            self.Bind(wx.EVT_MENU, self.handlesEditionLevels, id=menuId)
        self.menu1.AppendSubMenu(self.submenu1, "Edition levels")
        self.submenu2 = wx.Menu()
        for i, level in enumerate(self.arrowSpeedLevels):
            menuId = 12000 + i
            self.submenu2.Append(menuId, str(level), "", wx.ITEM_RADIO)
            self.Bind(wx.EVT_MENU, self.handlesArrowSpeedLevels, id=menuId)
        self.menu1.AppendSubMenu(self.submenu2, "Arrow Moves Speed levels")
        self.menu1.InsertSeparator(8)
        self.menu1.Append(103, "Reinit counters\tCtrl+T", "")
        self.Bind(wx.EVT_MENU, self.handleReinit, id=103)
        self.menuBar.Append(self.menu1, "&Drawing")

        self.menu3 = wx.Menu()
        self.menu3.Append(2004, "Memorize Trajectory\tShift+Ctrl+M", "")
        self.Bind(wx.EVT_MENU, self.handleMemorize, id=2004)
        self.menu3.Append(2005, "Midi Settings...\tShift+Alt+Ctrl+M", "")
        self.Bind(wx.EVT_MENU, self.showMidiSettings, id=2005)
        self.menuBar.Append(self.menu3, "&Midi")

        # the room: where you look from and what the pen draws on
        self.menuView = wx.Menu()
        # single letters are read by the room itself (so that typing a file name
        # does not change the view): they are shown here, not made accelerators
        for i, name in enumerate(space.VIEWS):
            self.menuView.Append(3000 + i, "%s view   (%s)" % (name, "PTFS"[i]), "", wx.ITEM_RADIO)
            self.Bind(wx.EVT_MENU, self.handleView, id=3000 + i)
        self.menuView.Append(3010, "Reset view   (Esc)", "")
        self.Bind(wx.EVT_MENU, self.handleView, id=3010)
        self.menuView.AppendSeparator()
        for i, name in enumerate(DRAW_SURFACES):
            self.menuView.Append(3020 + i, "Draw on the %s   (G)" % name.lower(), "", wx.ITEM_RADIO)
            self.Bind(wx.EVT_MENU, self.handleDrawOn, id=3020 + i)
        self.menuBar.Append(self.menuView, "&View")

        # what can be done to the selected trajectory in the room
        self.menuSpace = wx.Menu()
        self.spaceCommands = [
            ("Duplicate\tD", lambda: self.panel.duplicateSelected()),
            ("Mirrored twin (left - right)\tM", lambda: self.panel.mirrorSelected()),
            (None, None),
            ("Flip left - right\tH", lambda: self.panel.transformSelected('horizontal')),
            ("Flip front - back\tV", lambda: self.panel.transformSelected('vertical')),
            ("Flip up - down\tU", lambda: self.panel.transformSelected('updown')),
            (None, None),
            ("Turn 15 degrees\tR", lambda: self.panel.transformSelected('rotate', 15)),
            ("Tilt 15 degrees, front up\tX", lambda: self.panel.transformSelected('tiltx', 15)),
            ("Tilt 15 degrees, sideways\tY", lambda: self.panel.transformSelected('tilty', 15)),
            (None, None),
            ("Raise\t]", lambda: self.panel.transformSelected('lift', 10 * self.arrowSpeedLevel)),
            ("Lower\t[", lambda: self.panel.transformSelected('lift', -10 * self.arrowSpeedLevel)),
            ("Larger\t=", lambda: self.panel.transformSelected('scale', 1.05)),
            ("Smaller\t-", lambda: self.panel.transformSelected('scale', 1 / 1.05)),
            (None, None),
            ("Wrap onto the sphere\tZ", lambda: self.panel.transformSelected('sphere', self.panel.sphereRadius)),
            ("Flatten to its mean height\tB", lambda: self.panel.transformSelected('flatten')),
        ]
        for index, (label, action) in enumerate(self.spaceCommands):
            if label is None:
                self.menuSpace.AppendSeparator()
                continue
            # the letters are read by the room itself, so that typing in a text
            # field does not trigger them: show them, do not make accelerators
            name, key = label.split("\t")
            self.menuSpace.Append(3100 + index, "%s   (%s)" % (name, key))
            self.Bind(wx.EVT_MENU, self.handleSpaceCommand, id=3100 + index)
        self.menuSpace.AppendSeparator()
        self.menuSpace.Append(3200, "Load a loudspeaker layout (IEM / SPARTA JSON)...")
        self.Bind(wx.EVT_MENU, self.handleLoadLayout, id=3200)
        self.menuBar.Append(self.menuSpace, "&Space")

        self.menu4 = wx.Menu()
        self.menu4.Append(400, "Add Reverb ball\tCtrl+1", "")
        self.menu4.Append(401, "Add Delay ball\tCtrl+2", "")
        self.menu4.Append(402, "Add Disto ball\tCtrl+3", "")
        self.menu4.Append(403, "Add Waveguide ball\tCtrl+4", "")
        self.menu4.Append(404, "Add Complex Resonator ball\tCtrl+5", "")
        self.menu4.Append(405, "Add Degrade ball\tCtrl+6", "")
        self.menu4.Append(406, "Add Harmonizer ball\tCtrl+7", "")
        self.menu4.Append(407, "Add Clipper ball\tCtrl+8", "")
        self.menu4.Append(408, "Add Flanger ball\tCtrl+9", "")
        self.menu4.Append(409, "Add Detuned Resonator ball\tCtrl+0", "")
        for i in range(10):
            self.Bind(wx.EVT_MENU, self.addFxBall, id=400+i)
        self.menuBar.Append(self.menu4, "&FxBall")

        menu5 = wx.Menu()
        helpItem = menu5.Append(wx.ID_ABOUT, '&About %s %s' % (NAME, SG_VERSION))
        self.Bind(wx.EVT_MENU, self.showAbout, helpItem)
        commands = menu5.Append(501, "Open Sondugrande Documentation\tCtrl+H")
        self.Bind(wx.EVT_MENU, self.openCommandsPage, commands)
        self.menuBar.Append(menu5, '&Help')

        self.SetMenuBar(self.menuBar)

        lines = []
        if os.path.isfile(READ_PREFFILE):
            with open(READ_PREFFILE, "r", encoding=FILE_ENCODING) as f:
                lines = f.readlines()
                try:
                    auDriver = ensureNFD(lines[0].split("=")[1].replace("\n", ""))
                except:
                    auDriver = None
                try:
                    miDriver = ensureNFD(lines[1].split("=")[1].replace("\n", ""))
                except:
                    miDriver = None
                try:
                    self.lastFilePath = lines[3].split("=")[1].replace("\n", "")
                except:
                    self.lastFilePath = os.path.expanduser("~")
                try:
                    self.lastAudioPath = lines[4].split("=")[1].replace("\n", "")
                except:
                    self.lastAudioPath = os.path.expanduser("~")
        else:
            auDriver = None
            miDriver = None
            self.lastFilePath = os.path.expanduser("~")
            self.lastAudioPath = os.path.expanduser("~")

        inputPreference = None
        for line in lines:
            if line.startswith("inputDriver="):
                inputPreference = ensureNFD(line.split("=", 1)[1].strip())
            if line.startswith("recentProjects="):
                try:
                    paths = json.loads(line.split("=", 1)[1])
                    if isinstance(paths, list):
                        for path in paths:
                            if isinstance(path, str) and path and path not in self.recentProjects:
                                self.recentProjects.append(path)
                        self.recentProjects = self.recentProjects[:10]
                except (ValueError, TypeError):
                    pass
        self.updateRecentProjectsMenu()

        mainBox = wx.BoxSizer(wx.HORIZONTAL)
        self.panel = Surface3D(self)
        self.controls = ControlPanel(self, self.panel)
        mainBox.Add(self.panel, 20, wx.EXPAND, 5)
        mainBox.Add(self.controls, 0, wx.EXPAND, 5)
        self.SetSizer(mainBox)

        self.Bind(wx.EVT_CLOSE, self.OnClose)

        self.SetTitle('%s %s - ' % (NAME, SG_VERSION))
        self.envelopeFrame = EnvelopeFrame(self)
        self.sg_audio = SG_Audio(self.panel.clock, self.panel.Refresh, 
                                 self.controls, self.panel.addTrajFromMemory,
                                 self.panel.deleteMemorizedTraj, self.envelopeFrame,
                                 audio=AUDIO_BACKEND)
        self.panel.setAudio(self.sg_audio)
        self.granulatorControls = GranulatorFrame(self, self.sg_audio)
        self.spaceControls = SpaceFrame(self, self.sg_audio)
        for line in lines:
            if line.startswith("space="):
                try:
                    saved = json.loads(line.split("=", 1)[1])
                    # the output format is a property of this computer's set-up
                    for key in FORMAT_KEYS:
                        if key in saved:
                            self.sg_audio.space[key] = saved[key]
                except (ValueError, TypeError):
                    pass
        self.spaceControls.load(self.sg_audio.getSpace())
        self.midiSettings = MidiSettings(self, self.panel, self.sg_audio, miDriver)
        self.createInitTempFile()

        self.check(auDriver, inputPreference)

    def onRun(self, event):
        self.controls.handleAudio(event)

    def check(self, pref=None, inputPreference=None):
        self.status.SetStatusText('Scanning audio drivers...')
        self.driversList, self.driverIndexes, selected = checkForDrivers()
        self.driversList = [ensureNFD(driver) for driver in self.driversList]
        if pref == None:
            self.audioDriver = selected
        else:
            if pref in self.driversList:
                self.audioDriver = self.driverIndexes[self.driversList.index(pref)]
            else:
                self.audioDriver = selected
        self.controls.pop_audio_driver.Set(self.driversList)
        if self.audioDriver in self.driverIndexes:
            self.controls.pop_audio_driver.SetSelection(self.driverIndexes.index(self.audioDriver))
        else:
            self.controls.pop_audio_driver.Disable()
        self.inputDriversList, self.inputDriverIndexes, inputDefault = checkForInputDrivers()
        self.inputDriversList = [ensureNFD(driver) for driver in self.inputDriversList]
        if inputPreference in self.inputDriversList:
            self.inputDriver = self.inputDriverIndexes[self.inputDriversList.index(inputPreference)]
        elif inputDefault in self.inputDriverIndexes:
            self.inputDriver = inputDefault
        self.controls.pop_input_driver.Set(self.inputDriversList)
        if self.inputDriver in self.inputDriverIndexes:
            self.controls.pop_input_driver.SetSelection(self.inputDriverIndexes.index(self.inputDriver))
        else:
            self.controls.pop_input_driver.Disable()
        self.status.SetStatusText('Audio drivers loaded')
        self.controls.bootServer()

    def showMidiSettings(self, evt):
        self.midiSettings.show()

    def enableDrivers(self, state):
        self.controls.pop_audio_driver.Enable(state and bool(self.driverIndexes))
        if hasattr(self.controls, "pop_input_driver"):
            self.controls.pop_input_driver.Enable(state and bool(self.inputDriverIndexes))

    def handleView(self, evt):
        if evt.GetId() == 3010:
            self.panel.camera.reset()
            self.panel.Refresh()
        else:
            self.panel.setView(evt.GetId() - 3000)

    def handleDrawOn(self, evt):
        self.panel.setDrawOn(evt.GetId() - 3020)

    def syncViewMenu(self):
        """Tick the View menu for what the room shows."""
        if space.VIEWS.index(self.panel.camera.view) < 4:
            self.menuView.Check(3000 + space.VIEWS.index(self.panel.camera.view), True)
        self.menuView.Check(3020 + self.panel.drawOn, True)

    def handleSpaceCommand(self, evt):
        label, action = self.spaceCommands[evt.GetId() - 3100]
        if action is not None:
            action()

    def handleLoadLayout(self, evt):
        dlg = wx.FileDialog(self, message="Choose a loudspeaker layout (IEM AllRADecoder or SPARTA JSON)",
                            defaultDir=self.lastFilePath, wildcard="JSON file (*.json)|*.json|All files|*.*",
                            style=wx.FD_OPEN)
        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPath()
            try:
                layout = ambi.load_iem_layout(path)
            except Exception as error:
                wx.MessageBox("That file could not be read as a loudspeaker layout:\n%s" % error,
                              "Loudspeaker layout", wx.OK | wx.ICON_ERROR, self)
            else:
                self.spaceControls.setCustomLayout(layout, os.path.splitext(os.path.basename(path))[0])
        dlg.Destroy()

    def openSpaceWindow(self, evt):
        if self.spaceControls.IsShown():
            self.spaceControls.Hide()
        else:
            self.spaceControls.Show()
            self.spaceControls.Raise()

    def handleReinit(self, evt):
        for t in self.panel.getAllTrajectories():
            t.initCounter()

    def addFxBall(self, evt):
        self.panel.addFxBall(evt.GetId() - 400)

    def handleMemorize(self, evt):
        self.panel.Memorize()

    def handleDrawWave(self, evt):
        self.draw = self.menu1.IsChecked(100)
        self.drawing()

    def setDraw(self, state):
        self.menu1.Check(100, state)
        self.draw = state

    def drawing(self):
        if not self.draw:
            self.panel.sndBitmap = None
            self.panel.needBitmap = True
            self.panel.Refresh()
        else:
            if self.controls.sndPath != "":
                if self.controls.sndPath in self.panel.bitmapDict:
                    self.panel.list = self.panel.bitmapDict[self.controls.sndPath]
                    self.panel.create_bitmap()
                else:
                    self.panel.analyse(self.controls.sndPath)

    def handleActivateLp(self, evt):
        self.lowpass = self.menu1.IsChecked(101)
        self.checkLowpass()

    def setLowpass(self, state):
        self.menu1.Check(101, state)
        self.lowpass = state
        self.checkLowpass()

    def checkLowpass(self):
        for t in self.panel.getAllTrajectories():
            t.activateLp(self.lowpass)
        if self.lowpass:
            self.controls.drawing.sl_cutoff.Enable()
            self.controls.drawing.sl_q.Enable()
        else:
            self.controls.drawing.sl_cutoff.Disable()
            self.controls.drawing.sl_q.Disable()

    def handleActivateFill(self, evt):
        self.fillPoints = self.menu1.IsChecked(102)

    def setFillPoints(self, state):
        self.menu1.Check(102, state)
        self.fillPoints = state

    def handlesEditionLevels(self, evt):
        menuId = evt.GetId()
        self.editionLevel = self.editionLevels[menuId - 1000]
        self.pushEditionLevel()

    def handlesArrowSpeedLevels(self, evt):
        menuId = evt.GetId()
        self.arrowSpeedLevel = self.arrowSpeedLevels[menuId - 12000]

    def setEditionLevel(self, level):
        self.submenu1.Check(self.editionLevels.index(level)+1000, True)
        self.editionLevel = level
        self.pushEditionLevel()

    def pushEditionLevel(self):
        for t in self.panel.getAllTrajectories():
            t.setEditionLevel(self.editionLevel)

    def handleDriver(self, evt):
        index = evt.GetSelection()
        if index < 0 or index >= len(self.driverIndexes):
            return
        if self.driverIndexes[index] == self.audioDriver:
            return
        status, path = self.checkForMixedSound()
        if not status:
            if self.audioDriver in self.driverIndexes:
                self.controls.pop_audio_driver.SetSelection(self.driverIndexes.index(self.audioDriver))
            return
        if "Mixed sound" in self.controls.sndPath:
            self.controls.sndPath = path
            if path == "":
                self.panel.sndBitmap = None
                self.panel.needBitmap = True
                wx.CallAfter(self.panel.Refresh)
        self.audioDriver = self.driverIndexes[index]
        self.controls.shutdownServer()
        self.controls.bootServer()

    def handlePrecision(self, evt):
        self.sample_precision = self.controls.pop_precision.GetStringSelection()

    def handleInputDriver(self, evt):
        index = evt.GetSelection()
        if index < 0 or index >= len(self.inputDriverIndexes):
            return
        if self.inputDriverIndexes[index] == self.inputDriver:
            return
        status, path = self.checkForMixedSound()
        if not status:
            if self.inputDriver in self.inputDriverIndexes:
                self.controls.pop_input_driver.SetSelection(self.inputDriverIndexes.index(self.inputDriver))
            return
        if "Mixed sound" in self.controls.sndPath:
            self.controls.sndPath = path
            if path == "":
                self.panel.sndBitmap = None
                self.panel.needBitmap = True
                wx.CallAfter(self.panel.Refresh)
        self.inputDriver = self.inputDriverIndexes[index]
        self.controls.shutdownServer()
        self.controls.bootServer()

    def openFxWindow(self, evt):
        if self.granulatorControls.IsShown():
            self.granulatorControls.Hide()
        else:
            self.granulatorControls.SetTitle('Granulator controls')
            self.granulatorControls.Show()

    def openEnvelopeWindow(self, evt):
        if self.envelopeFrame.IsShown():
            self.envelopeFrame.Hide()
        else:
            self.envelopeFrame.Show()

    def handleUndo(self, evt):
        self.recallTempFile(evt.GetId())

    def handleNew(self, evt):
        cancel = False
        newpath = False
        if self.controls.sndPath != "":
            status, path = self.checkForMixedSound()
            if not status:
                return
            if "Mixed sound" in self.controls.sndPath and path:
                self.controls.sndPath = path
                newpath = True
        if self.is_unsaved or newpath:
            if self.currentFile == None:
                curfile = "Granulator.%s" % PROJECT_EXT
            else:
                curfile = self.currentFile
            dlg = wx.MessageDialog(self, 
                    "Do you want to save the changes you made in the document %s ?" % curfile,
                    'File Unsaved...', wx.YES_NO | wx.YES_DEFAULT | wx.CANCEL | wx.ICON_INFORMATION)
            ret = dlg.ShowModal()
            if ret == wx.ID_YES:
                self.handleSave(None)
            elif ret == wx.ID_CANCEL:
                cancel = True
            dlg.Destroy()
        if cancel:
            return
        self.panel.sndBitmap = None
        self.controls.sndPath = ""
        self.loadFile(os.path.join(RESOURCES_PATH, NEW_FILE))

    def handleOpen(self, evt):
        dlg = wx.FileDialog(self, message="Open a Sondugrande or SoundGrain file...",
                            defaultDir=self.lastFilePath,
                            defaultFile="",
                            wildcard="Sondugrande and SoundGrain files (*.sgr;*.sg)|*.sgr;*.sg|"
                                     "Sondugrande file (*.sgr)|*.sgr|SoundGrain file (*.sg)|*.sg",
                            style=wx.FD_OPEN)
        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPath()
            self.loadFile(ensureNFD(path))
            self.lastFilePath = os.path.split(path)[0]
        dlg.Destroy()

    def updateRecentProjectsMenu(self):
        for item in list(self.recentProjectsMenu.GetMenuItems()):
            self.recentProjectsMenu.DestroyItem(item)
        if not self.recentProjects:
            item = self.recentProjectsMenu.Append(wx.ID_ANY, "No recent projects")
            item.Enable(False)
        for index, path in enumerate(self.recentProjects):
            label = path.replace("&", "&&").replace("\t", " ").replace("\n", " ")
            self.recentProjectsMenu.Append(int(self.recentProjectIds[index]), label)

    def rememberRecentProject(self, path):
        path = os.path.abspath(path)
        self.recentProjects = [path] + [entry for entry in self.recentProjects if entry != path]
        self.recentProjects = self.recentProjects[:10]
        self.updateRecentProjectsMenu()

    def handleOpenRecent(self, evt):
        index = next((i for i, menu_id in enumerate(self.recentProjectIds)
                      if int(menu_id) == evt.GetId()), None)
        if index is None or index >= len(self.recentProjects):
            return
        path = self.recentProjects[index]
        if not os.path.isfile(path):
            wx.MessageBox("The project file could not be found:\n%s" % path,
                          "Open Recent", wx.OK | wx.ICON_ERROR, self)
            self.recentProjects.remove(path)
            self.updateRecentProjectsMenu()
            return
        self.loadFile(path)
        self.lastFilePath = os.path.dirname(path)

    def handleLoad(self, evt):
        self.controls.handleLoad()

    def handleInsert(self, evt):
        self.controls.handleInsert()

    def handleSave(self, evt):
        # a SoundGrain project that was opened is saved as a new Sondugrande file
        if self.currentFile and self.currentFile.lower().endswith("." + PROJECT_EXT):
            self.saveFile(self.currentFile)
        else:
            self.handleSaveAs(None)

    def handleSaveAs(self, evt):
        dlg = wx.FileDialog(self, message="Save file as ...",
                            defaultDir=self.lastFilePath,
                            defaultFile="Granulator.%s" % PROJECT_EXT,
                            wildcard="Sondugrande file (*.sgr)|*.sgr",
                            style=wx.FD_SAVE)
        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPath()
            if not path.lower().endswith("." + PROJECT_EXT):
                path = os.path.splitext(path)[0] + "." + PROJECT_EXT
            if os.path.isfile(path):
                dlg2 = wx.MessageDialog(self,
                      '"%s" already exists. Do you want to replace it?' % os.path.split(path)[1],
                      'Warning!', wx.OK | wx.ICON_INFORMATION | wx.CANCEL)
                if dlg2.ShowModal() == wx.ID_OK:
                    dlg2.Destroy()
                    self.saveFile(path)
                    self.lastFilePath = os.path.split(path)[0]
                    dlg.Destroy()
                else:
                    dlg2.Destroy()
                    dlg.Destroy()
                    self.handleSaveAs(None)
            else:
                self.saveFile(path)
                self.lastFilePath = os.path.split(path)[0]
                dlg.Destroy()

    def getState(self):
        saveDict = {}
        ### Main Frame ###
        saveDict['version'] = SG_VERSION
        saveDict['soundgrain'] = SOUNDGRAIN_VERSION
        saveDict['platform'] = PLATFORM
        saveDict['MainFrame'] = {}
        saveDict['MainFrame']['draw'] = self.draw
        saveDict['MainFrame']['lowpass'] = self.lowpass
        saveDict['MainFrame']['fillPoints'] = self.fillPoints
        saveDict['MainFrame']['editionLevel'] = self.editionLevel
        saveDict['MainFrame']['size'] = tuple(self.GetSize())
        ### The room: how it sounds and how it is looked at ###
        saveDict["Space"] = self.spaceControls.save()
        saveDict["View"] = self.panel.getViewState()
        ### Controls Frame ###
        saveDict['ControlFrame'] = self.granulatorControls.save()
        ### Midi Frame ###
        saveDict['MidiSettings'] = self.midiSettings.save()
        ### Control Panel ###
        saveDict['ControlPanel'] = {}
        saveDict['ControlPanel']['type'] = self.controls.getType()
        saveDict['ControlPanel']['closed'] = self.controls.getClosed()
        saveDict['ControlPanel']['cutoff'] = self.controls.getCutoff()
        saveDict['ControlPanel']['q'] = self.controls.getQ()
        saveDict['ControlPanel']['period'] = self.controls.getPeriod()
        saveDict['ControlPanel']['scaling'] = self.controls.getScaling()
        saveDict['ControlPanel']['eqfreqs'] = self.controls.getEqFreqs()
        saveDict['ControlPanel']['eqamps'] = self.controls.getEqAmps()
        saveDict['ControlPanel']['compress'] = self.controls.getCompValues()
        saveDict['ControlPanel']['globalamp'] = self.controls.getAmp()
        saveDict['ControlPanel']['nchnls'] = self.controls.getNchnls()
        saveDict['ControlPanel']['sr'] = self.controls.getSamplingRate()
        saveDict['ControlPanel']['fileformat'] = self.controls.getFileFormat()
        saveDict['ControlPanel']['sampletype'] = self.controls.getSampleType()
        saveDict['ControlPanel']['sound'] = self.controls.sndPath
        saveDict['ControlPanel']['recfolder'] = self.controls.tx_rec_folder.GetValue()
        saveDict['ControlPanel']['filename'] = self.controls.tx_output.GetValue()
        ### Trajectories ###
        saveDict['Trajectories'] = {}
        for i, t in enumerate(self.panel.getAllTrajectories()):
            saveDict['Trajectories'][str(i)] = t.getAttributes()
        saveDict['MemorizedTrajectory'] = self.panel.memorizedTrajectory.getAttributes()
        ### Grain Envelope ###
        saveDict['Envelope'] = self.envelopeFrame.save()
        ### Fx Balls ###
        saveDict['fxballs'] = {}
        for key, value in self.panel.fxballs.items():
            saveDict['fxballs'][str(key)] = value.save()
        return saveDict

    def saveFile(self, path):
        if self.controls.sndPath != "":
            status, sndpath = self.checkForMixedSound()
            if not status:
                return
            if "Mixed sound" in self.controls.sndPath:
                self.controls.sndPath = sndpath
        self.currentFile = path
        self.currentPath = os.path.split(path)[0]
        saveDict = self.getState()
        msg = xmlrpclib.dumps((saveDict, ), allow_none=True)
        f = open(path, 'w')
        f.write(msg)
        f.close()
        self.rememberRecentProject(path)
        self.SetTitle('%s %s - %s' % (NAME, SG_VERSION, os.path.split(self.currentFile)[1]))
        self.is_unsaved = False

    def setState(self, dict):
        version = dict.get('version', '3.0')
        platform = dict.get('platform', 'darwin')
        # a SoundGrain project has no room: its surface becomes the floor
        legacy = "Space" not in dict
        ### The room ###
        if not legacy:
            # the output format first: changing it restarts the audio server
            self.controls.applyOutputFormat(dict["Space"], dict['ControlPanel'].get('sr', 44100))
            self.spaceControls.load(dict["Space"])
            self.panel.setViewState(dict.get("View", {}))
        else:
            self.controls.setSamplingRate(dict['ControlPanel'].get('sr', 44100))
            # the room as it is when new, heard the way this computer is set up,
            # and seen from above: there it looks as it did in SoundGrain
            fresh = SPACE_DEFAULTS.copy()
            fresh.update({key: self.sg_audio.space[key] for key in FORMAT_KEYS})
            self.spaceControls.load(fresh)
            self.panel.setViewState({"view": "Top"})
        self.syncViewMenu()
        ### Main Frame ###
        self.setDraw(dict['MainFrame']['draw'])
        self.setLowpass(dict['MainFrame']['lowpass'])
        self.setFillPoints(dict['MainFrame']['fillPoints'])
        self.setEditionLevel(dict['MainFrame']['editionLevel'])
        size = dict['MainFrame']['size']
        if platform == 'darwin':
            if sys.platform == 'darwin':
                self.SetSize(size)
            elif sys.platform == "win32":
                self.SetSize((size[0]+10, size[1]+38))
            else:
                self.SetSize((size[0]+3, size[1]+13))
        elif platform == "win32":
            if sys.platform == 'darwin':
                self.SetSize((size[0]-10, size[1]-38))
            elif sys.platform == "win32":
                self.SetSize(size)
            else:
                self.SetSize((size[0]-7, size[1]-25))
        else:
            if sys.platform == 'darwin':
                self.SetSize((size[0]-3, size[1]-13))
            elif sys.platform == "win32":
                self.SetSize((size[0]+7, size[1]+25))
            else:
                self.SetSize(size)
        xfac, yfac = legacyFactors(dict)
        ### Control Frame ###
        self.granulatorControls.load(dict['ControlFrame'])
        ### Midi Frame ###
        self.midiSettings.load(dict.get("MidiSettings", None))
        ### Control panel ###
        self.controls.setType(dict['ControlPanel']['type'])
        self.controls.setClosed(dict['ControlPanel']['closed'])
        self.controls.setCutoff(dict['ControlPanel']['cutoff'])
        self.controls.setQ(dict['ControlPanel']['q'])
        self.controls.setPeriod(dict['ControlPanel']['period'])
        self.controls.setScaling(dict['ControlPanel']['scaling'])
        self.controls.setEqFreqs(dict['ControlPanel'].get('eqfreqs', [100, 500, 2000]))
        self.controls.setEqAmps(dict['ControlPanel'].get('eqamps', [0, 0, 0, 0]))
        self.controls.setCompValues(dict['ControlPanel'].get('compress', [-3, 2, 0.01, 0.1]))
        self.controls.setAmp(dict['ControlPanel']['globalamp'])
        self.controls.setFileFormat(dict['ControlPanel'].get('fileformat', 0))
        self.controls.setSampleType(dict['ControlPanel'].get('sampletype', 0))
        self.controls.loadSound(ensureNFD(dict['ControlPanel']['sound']))
        self.controls.setRecordFolder(ensureNFD(dict['ControlPanel'].get('recfolder', '~/Desktop')))
        self.controls.setRecordFilename(ensureNFD(dict['ControlPanel'].get('filename', 'snd')))
        ### Trajectories ###
        for i, t in enumerate(self.panel.getAllTrajectories()):
            t.setAttributes(dict['Trajectories'][str(i)], xfac, yfac)
        if 'MemorizedTrajectory' in dict:
            self.panel.memorizedTrajectory.setAttributes(dict['MemorizedTrajectory'], xfac, yfac)
        ### Grain Envelope ###
        if "Envelope" in dict:
            self.envelopeFrame.load(dict["Envelope"])
        if 'fxballs' in dict:
            self.panel.restoreFxBalls(dict["fxballs"], xfac, yfac)
        self.controls.resetPlaybackSliders()
        for t in self.panel.getAllTrajectories():
            if t.getActive():
                self.sg_audio.setTrajAmplitude(t.getId(), t.getAmplitude())

    def loadFile(self, path):
        if "Mixed sound" in self.controls.sndPath:
            status, saved_path = self.checkForMixedSound()
            if not status:
                return
            self.controls.sndPath = saved_path
        if self.midiSettings.IsShown():
            self.midiSettings.Hide()
        self.panel.removeAllFxBalls()
        f = open(path, 'r')
        msg = f.read()
        f.close()
        result, method = xmlrpclib.loads(msg)
        dict = result[0]
        if NEW_FILE in path:
            self.currentFile = None
            self.currentPath = None
            title = '%s %s - ' % (NAME, SG_VERSION)
            self.status.SetStatusText("")
        else:
            self.currentFile = path
            self.currentPath = os.path.split(path)[0]
            title = '%s %s - %s' % (NAME, SG_VERSION, os.path.split(self.currentFile)[1])
        if NEW_FILE in path and "Space" in dict:
            # a new project keeps the output this computer is set up for
            dict["Space"].update({key: self.sg_audio.space[key] for key in FORMAT_KEYS})
        self.panel.resetTrajectories()
        self.controls.setSelected(0)
        self.setState(dict)
        self.SetTitle(title)
        self.panel.needBitmap = True
        size = self.GetSize()
        if size[0] > self.screen_size[0]:
            x = self.screen_size[0] - 50
        else:
            x = size[0]
        if size[1] > self.screen_size[1]:
            y = self.screen_size[1] - 50
        else:
            y = size[1]
        size = (x, y)
        wx.CallAfter(self.panel.Refresh)
        wx.CallLater(100, self.SetSize, size)
        if self.currentFile is not None:
            self.rememberRecentProject(path)

    def createInitTempFile(self):
        d = {}
        for i, t in enumerate(self.panel.getAllTrajectories()):
            d[i] = str(t.getAttributes())
        self.temps.insert(0, d)

    def createTempFile(self):
        d = {}
        for i, t in enumerate(self.panel.getAllTrajectories()):
            d[i] = str(t.getAttributes())
        self.temps.insert(0, d)
        self.recall = self.undos = 0
        self.menu1.Enable(110, True)
        self.menu1.Enable(111, False)
        self.is_unsaved = True

    def recallTempFile(self, id):
        if self.temps and self.recall < len(self.temps):
            if id == 110:
                self.recall += 1
                self.undos += 1
            else:
                self.recall -= 1
                self.undos -= 1
            d = self.temps[self.recall]
            for i, t in enumerate(self.panel.getAllTrajectories()):
                t.setAttributes(eval(d[i]))
            self.panel.needBitmap = True
            self.Refresh()
        if self.recall >= len(self.temps) - 1:
            self.menu1.Enable(110, False)
        else:
            self.menu1.Enable(110, True)
        if self.undos == 0:
            self.menu1.Enable(111, False)
        else:
            self.menu1.Enable(111, True)
        self.is_unsaved = True

    def checkForMixedSound(self):
        return_status = True
        saved_path = ""
        if "Mixed sound" in self.controls.sndPath:
            if self.sg_audio.micRecording:
                self.controls.finishMic()
            dlg = wx.MessageDialog(self, "There is a mixed sound loaded in the drawing table, if you don't save it, it will be lost. Do you want to save it on disk ?",
                                   'Mixed sound no saved...', wx.YES_NO | wx.YES_DEFAULT | wx.CANCEL | wx.ICON_INFORMATION)
            ret = dlg.ShowModal()
            if ret == wx.ID_YES:
                save_dialog = True
                return_status = True
            elif ret == wx.ID_NO:
                save_dialog = False
                return_status = True
            else:
                save_dialog = False
                return_status = False
            dlg.Destroy()
            if save_dialog:
                ext = EXPORT_FORMATS[self.controls.fileformat].lower()
                wildcard = AUDIO_WILDCARD
                dlg2 = wx.FileDialog(self, message="Choose a filename...", 
                                     defaultDir=os.path.expanduser("~"),
                                     defaultFile="mixedtable.%s" % ext, 
                                     wildcard=wildcard, 
                                     style=wx.FD_SAVE | wx.FD_CHANGE_DIR)
                if dlg2.ShowModal() == wx.ID_OK:
                    path = dlg2.GetPath()
                    if path != "":
                        p, ext = os.path.splitext(path)
                        if ext.upper() in EXPORT_FORMATS:
                            fileformat = EXPORT_FORMATS[ext.upper()]
                        else:
                            fileformat = self.controls.fileformat
                        sampletype = self.controls.sampletype
                        self.sg_audio.table.save(path, fileformat, sampletype)
                        saved_path = path
                    else:
                        return_status = False
                else:
                    return_status = False
                dlg2.Destroy()
        return return_status, saved_path

    def OnClose(self, evt):
        newpath = False
        if self.controls.sndPath != "":
            status, path = self.checkForMixedSound()
            if not status:
                return
            if "Mixed sound" in self.controls.sndPath and path:
                self.controls.sndPath = path
                newpath = True
        if self.is_unsaved or newpath:
            if self.currentFile == None:
                curfile = "Granulator.%s" % PROJECT_EXT
            else:
                curfile = self.currentFile
            dlg = wx.MessageDialog(self, "Do you want to save the changes you made in the document %s ?" % curfile,
                                   'File Unsaved...', wx.YES_NO | wx.YES_DEFAULT | wx.CANCEL | wx.ICON_INFORMATION)
            ret = dlg.ShowModal()
            if ret == wx.ID_YES:
                self.handleSave(None)
            elif ret == wx.ID_CANCEL:
                return
            dlg.Destroy()
        if self.audioDriver in self.driverIndexes:
            auDriver = self.driversList[self.driverIndexes.index(self.audioDriver)]
        else:
            auDriver = ""
        miDriver = self.midiSettings.getInterface()
        with open(PREFFILE, "w", encoding=FILE_ENCODING) as f:
            f.write("audioDriver=%s\n" % auDriver)
            f.write("midiDriver=%s\n" % miDriver)
            f.write("samplePrecision=%s\n" % self.sample_precision)
            f.write("lastFilePath=%s\n" % self.lastFilePath)
            f.write("lastAudioPath=%s\n" % self.lastAudioPath)
            f.write("recentProjects=%s\n" % json.dumps(self.recentProjects))
            f.write("space=%s\n" % json.dumps(self.sg_audio.getSpace()))
            if self.inputDriver in self.inputDriverIndexes:
                f.write("inputDriver=%s\n" % self.inputDriversList[self.inputDriverIndexes.index(self.inputDriver)])
        # pyo sliders invoke their callbacks on paint, including paints queued
        # before quit. Stop those callbacks before removing audio objects.
        for window in wx.GetTopLevelWindows():
            silenceSliderCallbacks(window)
        if self.granulatorControls.IsShown():
            self.granulatorControls.Hide()
        if self.spaceControls.IsShown():
            self.spaceControls.Hide()
        # The MIDI listener owns a native PortTime callback independently of
        # the audio server. Stop it before Python teardown, when its callback
        # can no longer safely acquire the GIL.
        if hasattr(self.sg_audio, "listen"):
            self.sg_audio.listen.stop()
        self.controls.meter.OnClose(evt)
        if self.sg_audio.server.getIsStarted():
            self.sg_audio.server.stop()
            time.sleep(0.2)
        self.controls.shutdownServer()
        time.sleep(0.2)
        self.Destroy()

    def log(self, text):
        self.status.SetStatusText(text)

    def openCommandsPage(self, evt):
        win = CommandFrame(self, wx.ID_ANY, 
                           "%s %s - Documentation" % (NAME, SG_VERSION), 
                           size=(900, 650))

    def showAbout(self, evt):
        info = AboutDialogInfo()

        description = "Sondugrande is SoundGrain in a room: draw where the sound moves " \
        "in three dimensions, the same way SoundGrain lets you draw on the sound. " \
        "Every trajectory is a granular stream and a source in space, encoded to " \
        "Ambisonics (ACN / SN3D, 1st to 7th order) and heard on headphones, " \
        "loudspeakers or sent on to a decoder.\n\n" \
        "Sondugrande is a development of SoundGrain %s by Olivier Belanger, a graphical " \
        "interface where users can draw and edit trajectories to control granular " \
        "sound synthesis. Like SoundGrain it is written with Python and WxPython " \
        "and uses pyo as its audio engine, and it is free software under the GNU " \
        "General Public License version 3.\n\n" % SOUNDGRAIN_VERSION

        info.SetName(NAME)
        info.SetVersion('%s' % SG_VERSION)
        info.SetDescription(description)
        info.SetCopyright(u'SoundGrain (C) 2009-2018 Olivier Belanger\nSondugrande (C) %s femifleming' % SG_YEAR)
        AboutBox(info)

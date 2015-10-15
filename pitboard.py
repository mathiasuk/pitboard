# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
# Copyright (C) 2014 - Mathias Andre

import os
import platform
import sys
import traceback

import ac

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__),
                    'pitboardDLL/%s' % platform.architecture()[0])
)

from pitboardDLL.sim_info import info

APP_SIZE_X = 260
APP_SIZE_Y = 40

session = None


class UI(object):
    '''
    Object that deals with everything related to the app's widget
    '''
    def __init__(self, session_):
        self.session = session_
        self.widget = None
        self.labels = {}
        self.textures = {}

        self._create_widget()
        # self._create_labels()
        self._load_textures()

    def _create_widget(self):
        self.widget = ac.newApp('pitboard')
        ac.setSize(self.widget, APP_SIZE_X, APP_SIZE_Y)
        ac.setIconPosition(self.widget, -10000, -10000)
        ac.drawBorder(self.widget, 0)
        self.hide_bg()
        ac.addRenderCallback(self.widget, render_callback)

    def _create_label(self, name, text, x, y):
        label = ac.addLabel(self.widget, name)
        ac.setText(label, text)
        ac.setPosition(label, x, y)
        self.labels[name] = label

    def _create_labels(self):
        self._create_label('message1', '', 10, 30)

    def _load_textures(self):
        self.textures['board'] = ac.newTexture(
            'apps/python/pitboard/imgs/board.png')
        self.textures['A'] = ac.newTexture(
            'apps/python/pitboard/imgs/A.png')

    def hide_bg(self):
        ac.setBackgroundOpacity(self.widget, 0)

    def render(self):
        ac.glColor4f(1, 1, 1, 1)
        ac.glQuadTextured(0, 30, 260, 380, self.textures['board'])
        ac.glQuadTextured(10, 110, 40, 50, self.textures['A'])

    def set_bg_color(self, color):
        ac.setBackgroundColor(self.widget, *color[:-1])

    def set_title(self, text):
        ac.setTitle(self.widget, text)

    def show_bg(self):
        ac.setBackgroundOpacity(self.widget, 0.7)


class Session(object):
    '''
    Represent a racing sessions.
    '''
    def __init__(self):
        self.ui = None
        self._reset()

    def _is_race(self):
        '''
        Return true if the current session is a race
        '''
        return info.graphics.session == 2  # Only run in race mode

    def _reset(self):
        self.current_lap = 0
        self.laps = 0
        self.spline_pos = 0

    def render(self):
        self.ui.render()

    def update_ui(self):
        pass

    def update_data(self):
        if self._is_race():
            self.current_lap = info.graphics.completedLaps + 1  # 0 indexed
            self.spline_pos = info.graphics.normalizedCarPosition
            self.laps = info.graphics.numberOfLaps


def acMain(ac_version):
    global session  # pylint: disable=W0603

    # Create session object
    session = Session()

    # Initialise UI:
    ui = UI(session)
    session.ui = ui

    return "pitboard"


def acUpdate(deltaT):
    global session  # pylint: disable=W0602

    try:
        session.update_data()
        session.update_ui()
    except:  # pylint: disable=W0702
        exc_type, exc_value, exc_traceback = sys.exc_info()
        ac.console('pitboard Error (logged to file)')
        ac.log(repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))


def render_callback(deltaT):
    global session  # pylint: disable=W0602

    try:
        session.render()
    except:  # pylint: disable=W0702
        exc_type, exc_value, exc_traceback = sys.exc_info()
        session.ac.console('pitboard Error (logged to file)')
        session.ac.log(repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))

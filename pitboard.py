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

import glob
import os
import platform
import re
import string  # pylint: disable=W0402
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

# Mapping for special characters filenames
CHARS_MAPS = {
    '(': 'lpar',
    ')': 'rpar',
    '+': 'plus',
    '-': 'minus',
    '.': 'dot',
    ':': 'colon',
    '?': 'qmark',
}

session = None


class Card(object):
    '''
    Represent a single letter or symbol on the board
    '''
    def __init__(self, char, path, background, reflection):
        ac.console('*%s*' % char)
        self.char = char
        self.background = background
        self.reflection = reflection
        if path:
            self.texture = ac.newTexture(path)
        else:
            self.texture = None

        # Get width/height from filename
        r = re.match(r'[^_]+_(\d+)_(\d+).png', os.path.basename(path))
        if r:
            self.width, self.height = [int(x) for x in r.groups()]
        elif char == ' ':  # Special case for whitespace
            self.width = 15
            self.height = 50
        else:
            self.width = 40
            self.height = 50

        ac.console('%s, width: %d, height: %d' % (char, self.width, self.height))

    def render(self, x, y):
        if self.texture:
            ac.glColor4f(1, 1, 1, 1)
            ac.glQuadTextured(x, y, self.width, self.height, self.background)
            ac.glQuadTextured(x, y, self.width, self.height, self.texture)
            ac.glQuadTextured(x, y, self.width, self.height, self.reflection)


class Row(object):
    '''
    Represents a row of cards
    '''
    def __init__(self, x, y, max_width, library):
        self.x = x  # Coordinates of top-left corner of the row
        self.y = y
        self.max_width = max_width
        self.library = library
        self.width = 0
        self.cards = []

    def _clear(self):
        self.cards = []
        self.width = 0

    def _add_card(self, card):
        if self.width + card.width <= self.max_width:
            self.cards.append(card)
            self.width += card.width

    def render(self):
        x = self.x
        for card in self.cards:
            card.render(x, self.y)
            x += card.width

    def set_text(self, text):
        self._clear()
        for letter in text.upper():
            try:
                card = self.library[letter]
            except KeyError:
                card = self.library['?']
            self._add_card(card)


class Board(object):
    '''
    Represents the board itself
    '''
    def __init__(self, library):
        self.display = False
        self.rows = (
            Row(x=10, y=110, max_width=200, library=library),
            Row(x=10, y=170, max_width=200, library=library),
            Row(x=10, y=230, max_width=200, library=library),
            Row(x=10, y=290, max_width=200, library=library),
            Row(x=10, y=350, max_width=200, library=library),
        )
        self.texture = ac.newTexture('apps/python/pitboard/imgs/board.png')

    def render(self):
        if self.display:
            ac.glColor4f(1, 1, 1, 1)
            ac.glQuadTextured(0, 30, 260, 380, self.texture)

            for row in self.rows:
                row.render()


class UI(object):
    '''
    Object that deals with everything related to the app's widget
    '''
    def __init__(self, session_):
        self.labels = {}
        self.library = self._create_library()
        self.board = Board(self.library)
        self.session = session_
        self.textures = {}
        self.widget = None

        self._create_widget()

    def _create_library(self):
        '''
        Create a library of all available cards
        '''
        library = {}
        chars = string.ascii_uppercase + string.digits + \
            ''.join(CHARS_MAPS.keys()) + ' '

        bg = ac.newTexture('apps/python/pitboard/imgs/card_bg.png')
        reflect = ac.newTexture('apps/python/pitboard/imgs/card_reflect.png')

        for char in chars:
            try:
                pchar = CHARS_MAPS[char]
            except KeyError:
                pchar = char

            path = glob.glob(
                os.path.join('apps/python/pitboard/imgs/', '%s_*_*.png' % pchar)
            )
            path = path[0] if path else ''
            library[char] = Card(char, path, bg, reflect)

        return library

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

    def hide_bg(self):
        ac.setBackgroundOpacity(self.widget, 0)

    def render(self):
        self.board.render()

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
        self.position = 0
        self.spline_pos = 0

    def render(self):
        self.ui.render()

    def update_data(self):
        self.ui.board.display = True
        if self._is_race():
            self.current_lap = info.graphics.completedLaps
            # TODO: for practice, quali
            # self.position = ac.getCarLeaderboardPosition(0)
            self.position = ac.getCarRealTimeLeaderboardPosition(0) + 1
            self.laps = info.graphics.numberOfLaps
            self.spline_pos = info.graphics.normalizedCarPosition

            self.ui.board.rows[0].set_text(
                'P%d - L%d' % (self.position, self.laps - self.current_lap))
            self.ui.board.rows[2].set_text('(baR)')
            self.ui.board.rows[3].set_text('3.2:44-')
            self.ui.board.rows[4].set_text('%verylongaew')


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

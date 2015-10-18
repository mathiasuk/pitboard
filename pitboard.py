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
from datetime import datetime

import ac
import acsys

sys.path.insert(
    0, 'apps/python/pitboard/pitboardDLL/%s/' % platform.architecture()[0]
)

from pitboardDLL.sim_info import info

OPACITY = 0.8
DISPLAY_TIMEOUT = 15

APP_SIZE_X = 260
APP_SIZE_Y = 40
TEX_PATH = 'apps/python/pitboard/imgs/'

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

PRACTICE = 0
QUALIFY = 1
RACE = 2
HOTLAP = 3

# Define sectors frequency (0, 0.1, .., 0.9)
SECTORS = [x / 100.0 for x in range(0, 100, 10)]

session = None


class Car(object):
    '''
    Store information about car
    '''
    def __init__(self, index, name, session_type):
        self.index = index
        self.name = name
        self.position = -1

        if session_type == RACE:
            self.last_sector = None
            self.next_sector = None
            # Create a dict of sectors and timestamps
            # {0: None, 0.1: None, ... 0.9: None}
            self.sectors = dict([(x, None) for x in SECTORS])

    def _update_data_race(self):
        '''
        Update race specific data
        '''
        # Check if we've started a new sector, and store the current timestamp
        if self.next_sector is None:
            self._set_next_sector(self.spline_pos)
        else:
            spline_pos = self.spline_pos

            # Workaround to handle the last sector (0.96 is the same position
            # as -0.04)
            if self.next_sector == 0 and spline_pos >= max(SECTORS):
                spline_pos -= 1

            if spline_pos >= self.next_sector:
                # Store the current timestamp
                self.sectors[self.next_sector] = datetime.now()

                # Store the last known sector and set the next expected
                self.last_sector = self.next_sector
                self._set_next_sector(spline_pos)

    def _set_next_sector(self, spline):
        '''
        Set next_sector based on the given spline
        0.01 -> 0.05, 0.05 -> 0.1
        '''
        try:
            self.next_sector = [x for x in SECTORS if x > spline][0]
        except IndexError:
            self.next_sector = 0

    def update_data(self, session_type):
        self.spline_pos = ac.getCarState(
            self.index, acsys.CS.NormalizedSplinePosition)

        # The name can change if in no-booking mode
        self.name = ac.getDriverName(self.index)

        if session_type == RACE:
            self.position = ac.getCarRealTimeLeaderboardPosition(self.index) + 1
        else:
            self.position = ac.getCarLeaderboardPosition(self.index) + 1

        self._update_data_race()


class Card(object):
    '''
    Represent a single letter or symbol on the board
    '''
    def __init__(self, char, path, background, reflection):
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

    def render(self, x, y):
        if self.texture:
            ac.glColor4f(1, 1, 1, OPACITY)
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
            Row(x=10, y=410, max_width=200, library=library),
        )
        self.texture = ac.newTexture(os.path.join(TEX_PATH, 'board.png'))
        logo_path = os.path.join(TEX_PATH, 'logo.png')
        if os.path.exists(logo_path):
            self.logo = ac.newTexture(logo_path)
        else:
            self.logo = None

    def render(self):
        if self.display:
            ac.glColor4f(1, 1, 1, OPACITY)
            ac.glQuadTextured(0, 30, 260, 440, self.texture)

            if self.logo:
                ac.glQuadTextured(10, 40, 240, 60, self.logo)

            for row in self.rows:
                row.render()

    def update_rows(self, text):
        row = 0

        for line in text:
            self.rows[row].set_text(line)
            row += 1
            if row >= len(self.rows):
                break

        # Clear the rest of the board
        for row in range(row, len(self.rows)):
            self.rows[row].set_text('')


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

        bg = ac.newTexture(os.path.join(TEX_PATH, 'card_bg.png'))
        reflect = ac.newTexture(os.path.join(TEX_PATH, 'card_reflect.png'))

        for char in chars:
            try:
                pchar = CHARS_MAPS[char]
            except KeyError:
                pchar = char

            path = glob.glob(
                os.path.join(TEX_PATH, '%s_*_*.png' % pchar)
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

    def _check_session(self):
        '''
        Set the current session ID and the number of laps,
        Reset if a new session has started
        '''
        session_type = info.graphics.session
        current_lap = info.graphics.completedLaps

        if session_type != self.session_type and self.session_type != -1 or \
                current_lap < self.current_lap:
            # Session has been restarted or changed
            self._reset()

        self.current_lap = current_lap
        self.session_type = session_type

    def _update_board_quali(self):
        '''
        Displays:
         Position
         Name of car ahead in the standings (if any)
         Last laptime
        '''
        text = []

        car = self.get_player_car()
        if not car:
            return text

        ahead = self.get_car_by_position(car.position - 1)

        text.append('P%d' % car.position)

        if ahead:
            text.append(ahead.name)
            text.append('')
        else:
            text += ['', '']

        last_lap = info.graphics.iLastTime
        if last_lap:
            s, ms = divmod(last_lap, 1000)
            m, s = divmod(s, 60)
            text.append('%d:%d.%d' % (m, s, ms))

        if info.graphics.iCurrentTime < DISPLAY_TIMEOUT * 1000 and \
                self.current_lap > 0:
            # Display the board for the first 30 seconds
            self.ui.board.display = True
        else:
            self.ui.board.display = False

        return text

    def _update_board_race(self):
        '''
        Displays:
         Position - Laps left
         Name of car ahead (if any)
         Split to car ahead (if any)
         Last laptime
         Split to car behind (if any)
         Name of car behind (if any)
        '''
        text = []

        car = self.get_player_car()
        if not car:
            return text

        ahead = self.get_car_by_position(car.position - 1)
        behind = self.get_car_by_position(car.position + 1)

        text.append('P%d - L%d' %
                    (car.position, self.laps - self.current_lap - 1))

        split = self.get_split(car, ahead)
        if ahead and split:
            text.append(ahead.name)
            text.append(split)
        else:
            text += ['', '']

        last_lap = info.graphics.iLastTime
        if last_lap:
            s, ms = divmod(last_lap, 1000)
            m, s = divmod(s, 60)
            text.append('%d:%d.%d' % (m, s, ms))

        split = self.get_split(car, behind)
        if behind and split:
            text.append(split)
            text.append(behind.name)
        else:
            text += ['', '']

        if info.graphics.iCurrentTime < DISPLAY_TIMEOUT * 1000 and \
                self.current_lap > 0 or self.laps - self.current_lap == 1:
            # Display the board for the first 30 seconds, or once passed
            # the finish line
            self.ui.board.display = True
        else:
            self.ui.board.display = False

        return text

    def _update_cars(self):
        for i in range(ac.getCarsCount()):
            try:
                car = self.cars[i]
            except IndexError:
                name = ac.getDriverName(i)
                if name == -1:
                    # No such car
                    break
                car = Car(i, name, self.session_type)
                self.cars.append(car)

            car.update_data(self.session_type)

    def _reset(self):
        self.current_lap = 0
        self.laps = 0
        self.cars = []
        self.session_type = -1

    def get_car_by_position(self, position):
        '''
        Returns the car in the given position, or None
        '''
        for car in self.cars:
            if car.position == position:
                return car
        return None

    def get_player_car(self):
        '''
        Return the play's car or None
        '''
        try:
            return self.cars[0]
        except IndexError:
            return None

    def get_split(self, car1, car2):
        '''
        Returns the last available split time between two cars as a string
        '''
        if not car1 or not car2:
            return None

        # Get the last common sector (i.e: the last sector from the car behind)
        if car1.position > car2.position:
            last_sector = car1.last_sector
        else:
            last_sector = car2.last_sector

        if last_sector is None:
            # Car hasn't done a sector yet
            return None

        s1 = car1.sectors[last_sector]
        s2 = car2.sectors[last_sector]

        if not (s1 and s2):
            return None

        split = (s1 - s2).total_seconds()

        return '%+.2f' % split

    def update_board(self):
        if self.ui.board.display:
            # We don't update the board if it's currently displayed
            return

        text = []

        if self.session_type == RACE:
            text = self._update_board_race()
        elif self.session_type in (PRACTICE, QUALIFY, HOTLAP):
            text = self._update_board_quali()

        self.ui.board.update_rows(text)

    def update_data(self):
        self._check_session()
        self._update_cars()

        if self.session_type == RACE:
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
        session.update_board()
    except:  # pylint: disable=W0702
        exc_type, exc_value, exc_traceback = sys.exc_info()
        ac.console('pitboard Error (logged to file)')
        ac.log(repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))


def render_callback(deltaT):
    global session  # pylint: disable=W0602

    try:
        session.ui.render()
    except:  # pylint: disable=W0702
        exc_type, exc_value, exc_traceback = sys.exc_info()
        session.ac.console('pitboard Error (logged to file)')
        session.ac.log(repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))

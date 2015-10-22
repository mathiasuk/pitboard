# -*- coding: utf-8 -*-
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
# Copyright (C) 2014 - Mathias André

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

DISPLAY_TIMEOUT = 15
OPACITY = 0.8
SCALE = 1.0
SHORT_NAMES = True

DEBUG = False

APP_SIZE_X = 260 * SCALE
APP_SIZE_Y = 30
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
SECTORS = [n / 100.0 for n in range(0, 100, 10)]

session = None


<<<<<<< HEAD
def debug(msg):
    '''
    Log message to file
    '''
    if DEBUG:
        ac.log('Pitboard: %s' % msg)


def seconds_to_str(seconds):
=======
def seconds_to_str(seconds, precise=False):
>>>>>>> 971367acbdff751bdaa9523d4299eb372d861399
    '''
    Convert a time in seconds to a formatted string
    '''
    if precise:
        seconds = '%+.3f' % seconds
    elif seconds > -15 and seconds < 15:
        seconds = '%+.1f' % seconds
    else:
        seconds = '%+d' % round(seconds)

    # Strip heading 0: 0.1 -> .1
    if seconds[1] == 0:
        seconds = seconds[0] + seconds[2:]

    return seconds.rstrip('0').rstrip('.')


def split_to_str(split):
    '''
    Convert a split (timedelta) to a formatted string
    '''
    return seconds_to_str(split.total_seconds())


def time_to_str(laptime, show_ms=True):
    '''
    Convert a laptime in ms to a string formatted as mm:ss.ms
    '''
    s, ms = divmod(laptime, 1000)
    m, s = divmod(s, 60)

    if show_ms:
        return '%d:%02d.%d' % (m, s, ms)
    else:
        return '%d:%02d' % (m, s)


class Car(object):
    '''
    Store information about car
    '''
    def __init__(self, index, name, session_type):
        self.best_lap = None
        self.index = index
        self.name = name
        self.position = -1
        self.spline_pos = 0

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
            self.position = ac.getCarRealTimeLeaderboardPosition(self.index) + 1

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

    def get_name(self):
        '''
        Returns the driver's name
        '''
        if SHORT_NAMES:
            return self.name[:3]
        else:
            return self.name

    def update_data(self, session_type):
        self.spline_pos = ac.getCarState(
            self.index, acsys.CS.NormalizedSplinePosition)

        # The name can change if in no-booking mode
        self.name = ac.getDriverName(self.index)

        if session_type == RACE:
            self._update_data_race()
        else:
            self.position = ac.getCarLeaderboardPosition(self.index)
            best_lap = ac.getCarState(self.index, acsys.CS.BestLap)
            if best_lap > 0:
                self.best_lap = best_lap


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
            width, height = [int(x) for x in r.groups()]
        elif char == ' ':  # Special case for whitespace
            width = 15
            height = 50
        else:
            width = 40
            height = 50

        self.width = width * SCALE
        self.height = height * SCALE

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

        # Create 6 rows starting from 80 pixels, every 60 pixels
        self.rows = [
            Row(
                x=10 * SCALE,
                y=APP_SIZE_Y + y * SCALE,
                max_width=240 * SCALE,
                library=library
            ) for y in range(80, 440, 60)
        ]

        self.texture = ac.newTexture(os.path.join(TEX_PATH, 'board.png'))
        logo_path = os.path.join(TEX_PATH, 'logo.png')
        if os.path.exists(logo_path):
            self.logo = ac.newTexture(logo_path)
        else:
            self.logo = None

    def render(self):
        if self.display:
            ac.glColor4f(1, 1, 1, OPACITY)
            ac.glQuadTextured(0, APP_SIZE_Y, 260 * SCALE, 440 * SCALE,
                              self.texture)

            if self.logo:
                ac.glQuadTextured(10 * SCALE, APP_SIZE_Y + 10 * SCALE,
                                  240 * SCALE, 60 * SCALE, self.logo)

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

    def hide_bg(self):
        ac.setBackgroundOpacity(self.widget, 0)

    def render(self):
        self.board.render()


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

    def _get_split(self, car1, car2):
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

        return s1 - s2

    def _get_splits(self, player):
        '''
        Returns a dict of cars and their split time with the player
        '''
        splits = {}
        for car in self.cars[1:]:
            splits[car] = self._get_split(player, car)

        return splits

    def _reset(self):
        self.current_lap = 0
        self.laps = 0
        self.cars = []
        self.session_type = -1
        self.last_splits = {}

    def _update_board_quali(self):
        '''
        Displays:
         Position
         Name of car ahead in the standings (if any)
         Last laptime
        '''
        text = []

        current_time = info.graphics.iCurrentTime
        is_in_pit = info.graphics.isInPit
        last_lap = info.graphics.iLastTime
        pit_limiter_on = info.physics.pitLimiterOn
        time_left = info.graphics.sessionTimeLeft

        car = self.get_player_car()
        if not car:
            return text

        ahead = self.get_car_by_position(car.position - 1)

        text.append('P%d' % car.position)

        # Display name of car ahead in the standings (if any)
        if ahead:
            text.append(ahead.get_name())
            if car.best_lap and ahead.best_lap:
                text.append(
                    seconds_to_str(
                        (car.best_lap - ahead.best_lap) / 1000.0,
                        precise=True
                    )
                )
            else:
                text.append('')
        else:
            text += ['', '']

        # Display own lap time
        if last_lap and car.best_lap:
            text.append(time_to_str(car.best_lap))
            text.append(seconds_to_str(last_lap - car.best_lap))

        # Display time left in session
        text.append('LEFT ' + time_to_str(time_left, show_ms=False))

        if current_time < DISPLAY_TIMEOUT * 1000 and self.current_lap > 0 and \
                (not pit_limiter_on or not is_in_pit):
            # Display the board for the first 30 seconds, if not in pits

            # Update the text when the board is displayed
            if self.ui.board.display is False:
                self.ui.board.update_rows(text)
                debug('Updating board (quali), lap: %d' % self.current_lap)
				# TODO: debug cars
                debug('Text:\n %s \n' % '\n'.join(text))
            self.ui.board.display = True
        else:
            self.ui.board.display = False

        return

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

        # Get current split times
        splits = self._get_splits(car)

        # Display split to car ahead (if any)
        if ahead and splits[ahead]:
            text.append(ahead.get_name())
            line = split_to_str(splits[ahead])
            if ahead in self.last_splits:
                line += ' (%s)' % split_to_str(
                    splits[ahead] - self.last_splits[ahead])
            text.append(line)
        else:
            text += ['', '']

        # Display own lap time
        last_lap = info.graphics.iLastTime
        if last_lap:
            text.append(time_to_str(last_lap))

        # Display split to car behind (if any)
        if behind and splits[behind]:
            line = split_to_str(splits[behind])
            if behind in self.last_splits:
                line += ' (%s)' % split_to_str(
                    splits[behind] - self.last_splits[behind])
            text.append(line)
            text.append(behind.get_name())
        else:
            text += ['', '']

        if info.graphics.iCurrentTime < DISPLAY_TIMEOUT * 1000 and \
                self.current_lap > 0 or self.laps - self.current_lap == 1:
            # Display the board for the first 30 seconds, or once passed
            # the finish line

            # Update the text and save the current splits when the board is
            # displayed
            if self.ui.board.display is False:
                debug('Updating board (race), lap: %d' % self.current_lap)
                debug('Last splits: %s' % self.last_splits)
                debug('Current splits: %s' % splits)
                debug('Text:\n %s \n' % '\n'.join(text))
                self.ui.board.update_rows(text)
                self.last_splits = splits

            self.ui.board.display = True
        else:
            self.ui.board.display = False

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

    def update_board(self):
        if self.session_type == RACE:
            self._update_board_race()
        elif self.session_type in (PRACTICE, QUALIFY, HOTLAP):
            self._update_board_quali()

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
        ac.console('pitboard Error (logged to file)')
        ac.log(repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))

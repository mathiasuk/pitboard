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

# pylint: disable=W0602

from __future__ import unicode_literals

import glob
import json
import os
import platform
import re
import string  # pylint: disable=W0402
import sys
import traceback
from datetime import datetime, timedelta

import ac
import acsys

sys.path.insert(
    0, 'apps/python/pitboard/pitboardDLL/%s/' % platform.architecture()[0]
)

from pitboardDLL.sim_info import info

# Customisable constants
ZOOM_TRANSITION = 0.25
TITLE_TIMEOUT = 10  # Time in seconds during which we show the title

# Default for settings that can be changed in game
DETAILED_DELTA = True
DISPLAY_TIMEOUT = 45
FULLSIZE_SCALE = 1.0
FULLSIZE_TIMEOUT = 15
OPACITY = 0.8
ORIENTATION_X = 'L'  # 'L' or 'R'
ORIENTATION_Y = 'U'  # 'U' or 'D'
SHORT_NAMES = False
SMALLSIZE_SCALE = 0.5
USE_SURNAME = False

DEBUG = ac.getDriverName(0) == '0xdeadbee'

APP_SIZE_X = 120 * FULLSIZE_SCALE
APP_SIZE_Y = 30
TEX_PATH = 'apps/python/pitboard/imgs/'
PREFS_PATH = 'apps/python/pitboard/prefs.json'

PREFS_KEYS = (
    'detailed_delta',
    'display_timeout',
    'fullsize_scale',
    'fullsize_timeout',
    'opacity',
    'orientation_x',
    'orientation_y',
    'short_names',
    'smallsize_scale',
    'use_surname',
)

# Define colours
COLOURS = {
    'g': (0, 204 / 255, 0),
    'r': (1, 40 / 255, 0),
    'w': (1, 1, 1),
    'y': (1, 204 / 255, 0),
}

# Set default colour applied over cards' text texture
DEFAULT_COLOUR = 'y'

# Mapping for special characters filenames
CHARS_MAPS = {
    '&': 'amp',
    '*': 'asterisk',
    '\\': 'bslash',
    ':': 'colon',
    '.': 'dot',
    '|': 'downarrow',
    '!': 'emark',
    '=': 'equal',
    '>': 'gt',
    '(': 'lpar',
    '<': 'lt',
    '-': 'minus',
    '#': 'num',
    '+': 'plus',
    '?': 'qmark',
    ')': 'rpar',
    '^': 'uparrow',
    '_': 'uscore',
}

# Session status
OFF = 0
REPLAY = 1
LIVE = 2
PAUSE = 3

# Session type
PRACTICE = 0
QUALIFY = 1
RACE = 2
HOTLAP = 3


# Define sectors frequency (0, 0.1, .., 0.9)
SECTORS = [n / 100.0 for n in range(0, 100, 10)]

session = None


def debug(msg):
    '''
    Log message to file
    '''
    if DEBUG:
        ac.log('Pitboard: %s' % msg)


def debug_splits(splits):
    '''
    Return a string representation of the splits for logging
    '''
    s = ''
    for car, split in splits.items():
        s += '  %s (%s): %s\n' % (car.index, car.name,
                                  split.total_seconds() if split else 'none')

    return s


def ms_to_str(ms, precise=True, arrows=False):
    '''
    Convert a time in milliseconds to a formatted string
    If arrows is true ↑ and ↓ will be used instead of +/-
    '''
    seconds = ms / 1000.0
    if precise:
        seconds = '%+.3f' % seconds
    elif seconds > -15 and seconds < 15:
        seconds = '%+.1f' % seconds
    else:
        seconds = '%+d' % round(seconds)

    if arrows:
        if seconds[0] == '+':
            seconds = '^' + seconds[1:]
        else:
            seconds = '|' + seconds[1:]

    return seconds


def round_delta(delta):
    '''
    Round the delta to seconds and deciseconds
    '''
    return timedelta(seconds=round(delta.total_seconds() * 10) / 10)


def split_to_str(split, arrows=False):
    '''
    Convert a split (timedelta) to a formatted string
    '''
    return ms_to_str(split.total_seconds() * 1000, precise=False, arrows=arrows)


def time_to_str(laptime, show_ms=True):
    '''
    Convert a laptime in ms to a string formatted as mm:ss.ms
    '''
    s, ms = divmod(laptime, 1000)
    m, s = divmod(s, 60)

    if show_ms:
        return '%d:%02d.%03d' % (m, s, ms)
    else:
        return '%d:%02d' % (m, s)


class Car(object):
    '''
    Store information about car
    '''
    def __init__(self, index, name, _session, session_type):
        self.best_lap = None
        self.index = index
        self.lap = -1
        self.name = name
        self.position = -1
        self.session = _session
        self.spline_pos = 0

        if session_type == RACE:
            self.last_sector = None
            self.next_sector = None
            # Create a dict of sectors and timestamps
            # {0: None, 0.1: None, ... 0.9: None}
            self.sectors = dict([(x, None) for x in SECTORS])

    def __repr__(self):
        data = [
            'Index: %d' % self.index,
            'Name: %s' % self.name,
            'Position: %d' % self.position,
            'Spline: %.2f' % self.spline_pos,
            'Best: %s' % self.best_lap
        ]
        if hasattr(self, 'last_sector'):
            data.extend([
                'Last sector: %s' % self.last_sector,
                'Next sector: %s' % self.next_sector,
                'Sectors: %s' % self.sectors,
            ])
        return ', '.join(data)

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

    def get_name(self):
        '''
        Returns the driver's name
        '''
        if self.session.use_surname and ' ' in self.name:
            name = self.name.split()[1]
        else:
            name = self.name

        if self.session.short_names:
            return name[:3]
        else:
            return name

    def update_data(self, session_type):
        self.spline_pos = ac.getCarState(
            self.index, acsys.CS.NormalizedSplinePosition)
        self.lap = ac.getCarState(self.index, acsys.CS.LapCount)

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

        self.width = width
        self.height = height

    def render(self, x, y, opacity, scale, colour):
        if self.texture:
            width = self.width * scale
            height = self.height * scale
            ac.glColor4f(1, 1, 1, opacity)
            ac.glQuadTextured(x, y, width, height, self.background)

            # Render text with colour
            args = colour + (opacity, )
            ac.glColor4f(*args)
            ac.glQuadTextured(x, y, width, height, self.texture)

            ac.glColor4f(1, 1, 1, opacity)
            ac.glQuadTextured(x, y, width, height, self.reflection)


class Text(object):
    '''
    Represent text on the board, including the optional colour
    '''
    def __init__(self, text='', colour=''):
        self.text = text
        if colour:
            # If the colour string is shorter than the text we
            # complete it with the last given colour
            if len(text) > len(colour):
                self.colour = colour + colour[-1] * (len(text) - len(colour))
            else:
                self.colour = colour
        else:
            self.colour = DEFAULT_COLOUR * len(self.text)

    def __repr__(self):
        return self.text


class Row(object):
    '''
    Represents a row of cards
    '''
    def __init__(self, x, y, max_width, library):
        self.x = x  # Relative coordinates of top-left corner of the row
        self.y = y
        self.max_width = max_width
        self.library = library
        self.width = 0
        self.cards = []
        self.colours = []

    def _clear(self):
        self.cards = []
        self.colours = []
        self.width = 0

    def _add_card(self, card, colour):
        '''
        Add a card to the row, return True on success, False if
        the row if already full
        '''
        if self.width + card.width > self.max_width:
            return False

        self.cards.append(card)
        self.colours.append(COLOURS[colour])
        self.width += card.width
        return True

    def render(self, opacity, scale, board_x, board_y):
        '''
        Render the given row, x and y correspond to the absolute
        coordinate of the top left corner of the board
        '''
        x = board_x + self.x * scale
        y = board_y + self.y * scale
        for card, colour in zip(self.cards, self.colours):
            card.render(x, y, opacity, scale, colour)
            x += card.width * scale

    def set_text(self, text):
        self._clear()
        for letter, colour in zip(text.text.upper(), text.colour):
            try:
                card = self.library[letter]
            except KeyError:
                card = self.library['?']

            if not self._add_card(card, colour):
                break


class Board(object):
    '''
    Represents the board itself
    '''
    def __init__(self, library):
        self.display = False

        # Create 6 rows starting from 80 pixels, every 60 pixels
        self.rows = [
            Row(x=10, y=y, max_width=240, library=library)
            for y in range(80, 440, 60)
        ]

        # Look for a custom board, otherwise use the default
        name = ac.getDriverName(0)
        board_path = os.path.join(TEX_PATH, 'board_%s.png' % name)

        if not os.path.exists(board_path):
            board_path = os.path.join(TEX_PATH, 'board.png')

        self.texture = ac.newTexture(board_path)

        # Look for a player logo, otherwise use the default
        logo_path = os.path.join(TEX_PATH, 'logo_%s.png' % name)

        if os.path.exists(logo_path):
            self.logo = ac.newTexture(logo_path)
            return

        logo_path = os.path.join(TEX_PATH, 'logo.png')
        if os.path.exists(logo_path):
            self.logo = ac.newTexture(logo_path)
        else:
            self.logo = None

    def render(self, opacity, scale, orientation_x, orientation_y):
        '''
        Render the board frame and logo, call render
        for all the Rows
        '''
        if self.display:
            width = 260 * scale
            height = 440 * scale

            if orientation_x == 'L':
                x = 0
            else:
                x = APP_SIZE_X - width

            if orientation_y == 'U':
                y = APP_SIZE_Y
            else:
                y = -height

            ac.glColor4f(1, 1, 1, opacity)
            ac.glQuadTextured(x, y, width, height, self.texture)

            if self.logo:
                ac.glColor4f(1, 1, 1, opacity)
                ac.glQuadTextured(
                    x + 10 * scale,
                    y + 10 * scale,
                    240 * scale,
                    60 * scale,
                    self.logo
                )

            for row in self.rows:
                row.render(opacity, scale, x, y)

    def update_rows(self, text):
        row = 0

        for line in text:
            self.rows[row].set_text(line)
            row += 1
            if row >= len(self.rows):
                break

        # Clear the rest of the board
        for row in range(row, len(self.rows)):
            self.rows[row].set_text(Text())


class UI(object):
    '''
    Object that deals with everything related to the app's widget
    '''
    def __init__(self, session_):
        self.display_title = False
        self.display_title_start = None
        self.library = self._create_library()
        self.board = Board(self.library)
        self.session = session_
        self.prefs_button = None
        self.prefs_texture = ac.newTexture(os.path.join(TEX_PATH, 'prefs.png'))
        self.prefs_controls = {}
        self.prefs_visible = False
        self.widget = None
        self.x = 0  # Absolute x on screen
        self.y = 0  # Absolute y on screen

        self._create_widget()
        self.activated()

    def _create_label(self, name, text, x, y):
        label = ac.addLabel(self.widget, name)
        ac.setText(label, text)
        ac.setPosition(label, x, y)
        return label

    def _create_library(self):
        '''
        Create a library of all available cards
        '''
        # TODO: Add support for lowercase letter (with option in gui to
        # enable/disable)
        # Filenames should be e.g. b_low_29_50.png
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

    def _create_prefs_controls(self):
        spin = ac.addSpinner(self.widget, 'Display duration, -1 for always on')
        ac.setPosition(spin, 340, 55)
        ac.setRange(spin, -1, 60)
        ac.setStep(spin, 1)
        ac.setValue(spin, self.session.display_timeout)
        ac.setSize(spin, 120, 25)
        ac.addOnValueChangeListener(spin,
                                    callback_display_timeout_spinner_changed)
        ac.setVisible(spin, 0)
        self.prefs_controls['display_timeout_spinner'] = spin

        spin = ac.addSpinner(self.widget, 'Full size duration')
        ac.setPosition(spin, 340, 110)
        ac.setRange(spin, 0, 60)
        ac.setStep(spin, 1)
        ac.setValue(spin, self.session.fullsize_timeout)
        ac.setSize(spin, 120, 25)
        ac.addOnValueChangeListener(spin,
                                    callback_fullsize_timeout_spinner_changed)
        ac.setVisible(spin, 0)
        self.prefs_controls['fullsize_timeout_spinner'] = spin

        spin = ac.addSpinner(self.widget, 'Full size scale in %')
        ac.setPosition(spin, 340, 165)
        ac.setRange(spin, 20, 200)
        ac.setStep(spin, 10)
        ac.setValue(spin, self.session.fullsize_scale * 100)
        ac.setSize(spin, 120, 25)
        ac.addOnValueChangeListener(spin,
                                    callback_fullsize_scale_spinner_changed)
        ac.setVisible(spin, 0)
        self.prefs_controls['fullsize_scale_spinner'] = spin

        spin = ac.addSpinner(self.widget, 'Small size scale in %')
        ac.setPosition(spin, 340, 220)
        ac.setRange(spin, 10, 200)
        ac.setStep(spin, 10)
        ac.setValue(spin, self.session.smallsize_scale * 100)
        ac.setSize(spin, 120, 25)
        ac.addOnValueChangeListener(spin,
                                    callback_smallsize_scale_spinner_changed)
        ac.setVisible(spin, 0)
        self.prefs_controls['smallsize_scale_spinner'] = spin

        spin = ac.addSpinner(self.widget, 'Opacity in %')
        ac.setPosition(spin, 340, 275)
        ac.setRange(spin, 10, 100)
        ac.setStep(spin, 10)
        ac.setValue(spin, self.session.opacity * 100)
        ac.setSize(spin, 120, 25)
        ac.addOnValueChangeListener(spin,
                                    callback_opacity_spinner_changed)
        ac.setVisible(spin, 0)
        self.prefs_controls['opacity_spinner'] = spin

        check = ac.addCheckBox(self.widget, 'Use short name')
        ac.setPosition(check, 270, 320)
        ac.setSize(check, 10, 10)
        ac.setValue(check, self.session.short_names)
        ac.addOnCheckBoxChanged(check,
                                callback_short_name_checkbox_changed)
        ac.setVisible(check, 0)
        self.prefs_controls['short_name_checkbox'] = check

        check = ac.addCheckBox(self.widget, 'Use surname')
        ac.setPosition(check, 270, 340)
        ac.setSize(check, 10, 10)
        ac.setValue(check, self.session.use_surname)
        ac.addOnCheckBoxChanged(check,
                                callback_use_surname_checkbox_changed)
        ac.setVisible(check, 0)
        self.prefs_controls['short_name_checkbox'] = check

        check = ac.addCheckBox(self.widget, 'Detailed delta')
        ac.setPosition(check, 270, 360)
        ac.setSize(check, 10, 10)
        ac.setValue(check, self.session.detailed_delta)
        ac.addOnCheckBoxChanged(check,
                                callback_detailed_delta_checkbox_changed)
        ac.setVisible(check, 0)
        self.prefs_controls['detailed_delta_checkbox'] = check

        label = self._create_label('orientation', 'Orientation:', 270, 380)
        ac.setVisible(label, 0)
        self.prefs_controls['orientation'] = label

        button = ac.addButton(self.widget, 'change')
        ac.setPosition(button, 440, 380)
        ac.setSize(button, 60, 20)
        ac.setVisible(button, 0)
        self.prefs_controls['orientation_button'] = button
        ac.addOnClickedListener(button, callback_orientation_button)

    def _create_widget(self):
        self.widget = ac.newApp('pitboard')
        ac.setSize(self.widget, APP_SIZE_X, APP_SIZE_Y)
        ac.setIconPosition(self.widget, -10000, -10000)
        ac.drawBorder(self.widget, 0)
        ac.setBackgroundOpacity(self.widget, 0.2)

        # Create prefs button
        self.prefs_button = ac.addButton(self.widget, '')
        ac.setPosition(self.prefs_button, 7, 7)
        ac.setSize(self.prefs_button, 16, 16)
        ac.setBackgroundOpacity(self.prefs_button, 0)
        ac.drawBorder(self.prefs_button, 0)
        ac.addOnClickedListener(self.prefs_button, callback_prefs_button)

        self._create_prefs_controls()

        ac.addRenderCallback(self.widget, render_callback)
        ac.addOnAppActivatedListener(self.widget, activated_callback)

    def _set_orientation_label(self):
        text = 'Orientation: '
        if self.session.orientation_x == 'L':
            if self.session.orientation_y == 'U':
                text += 'top-left'
            else:
                text += 'bottom-left'
        else:
            if self.session.orientation_y == 'U':
                text += 'top-right'
            else:
                text += 'bottom-right'

        ac.setText(self.prefs_controls['orientation'], text)

    def activated(self):
        '''
        Called at start or when the app is (re)activated
        '''
        self.display_title = True
        self.display_title_start = datetime.now()

    def orientation_button_click(self):
        if self.session.orientation_x == 'L':
            if self.session.orientation_y == 'U':
                self.session.orientation_x = 'R'
            else:
                self.session.orientation_y = 'U'
        else:
            if self.session.orientation_y == 'U':
                self.session.orientation_y = 'B'
            else:
                self.session.orientation_x = 'L'

        self._set_orientation_label()

    def prefs_button_click(self):
        self.prefs_visible = not self.prefs_visible

        if self.prefs_visible:
            self._set_orientation_label()

            # Increase side of the widget, make controls visible
            ac.setSize(self.widget, 520, APP_SIZE_Y + 340)
            for control in self.prefs_controls.values():
                ac.setVisible(control, 1)
        else:
            # Decrease side of the widget, hide controls
            ac.setSize(self.widget, APP_SIZE_X, APP_SIZE_Y)
            for control in self.prefs_controls.values():
                ac.setVisible(control, 0)

            # Save preferences
            self.session.save_prefs()

    def update_ui(self):
        '''
        Called with on acUpdate, to update the title, opacity, etc.
        '''
        # Check if the widget has moved
        x, y = ac.getPosition(self.widget)
        if x != self.x or y != self.y:
            self.activated()
            self.x, self.y = x, y

        if self.display_title or self.prefs_visible:
            ac.setBackgroundOpacity(self.widget, 0.3)
            ac.setTitle(self.widget, 'pitboard')

            if not self.prefs_visible:
                display_time = (datetime.now() -
                                self.display_title_start).total_seconds()
                if display_time > TITLE_TIMEOUT:
                    self.display_title = False
        else:
            ac.setBackgroundOpacity(self.widget, 0)
            ac.setTitle(self.widget, '')

        ac.drawBorder(self.widget, 0)

    def render(self, opacity, scale, orientation_x, orientation_y):
        self.board.render(opacity, scale, orientation_x, orientation_y)

        if self.display_title or self.prefs_visible:
            ac.glColor4f(1, 1, 1, opacity)
            ac.glQuadTextured(7, 7, 16, 16, self.prefs_texture)


class Session(object):
    '''
    Represent a racing sessions.
    '''
    def __init__(self):
        self.ui = None
        self.detailed_delta = DETAILED_DELTA
        self.display_timeout = DISPLAY_TIMEOUT
        self.fuel_consumption = -1
        self.fullsize_scale = FULLSIZE_SCALE
        self.fullsize_timeout = FULLSIZE_TIMEOUT
        self.opacity = OPACITY
        self.orientation_x = ORIENTATION_X
        self.orientation_y = ORIENTATION_Y
        self.short_names = SHORT_NAMES
        self.smallsize_scale = SMALLSIZE_SCALE
        self.use_surname = USE_SURNAME

        # Fuel variables
        self.current_fuel = -1
        self.fuel_consumption = -1
        self.initial_fuel = -1
        self.refuel_lap = -1
        self.travelled_laps = 0

        self._reset()

        self._load_prefs()

    def _check_session(self):
        '''
        Set the current session ID and the number of laps,
        Reset if a new session has started
        '''
        session_status = info.graphics.status
        session_type = info.graphics.session
        current_lap = info.graphics.completedLaps

        if session_type != self.session_type and self.session_type != -1 or \
                current_lap < self.current_lap:
            # Session has been restarted or changed
            self._reset()

        self.current_lap = current_lap
        self.session_status = session_status
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

    def _load_prefs(self):
        '''
        Loads preferences from JSON file
        '''
        if not os.path.exists(PREFS_PATH):
            return

        try:
            f = open(PREFS_PATH)
        except Exception as e:
            ac.console('Pitboard: Error opining "%s": %s' % (PREFS_PATH, e))
            return

        data = f.readline()
        data = json.loads(data)
        for key, value in data.items():
            if key in PREFS_KEYS:
                setattr(self, key, value)
            else:
                ac.console('Unknown key "%s" in "%s"' % (key, PREFS_PATH))

    def _reset(self):
        self.current_lap = 0
        self.last_best_lap = None
        self.laps = 0
        self.cars = []
        self.scale = self.fullsize_scale
        self.session_type = -1
        self.last_splits = {}

    def _set_scale(self, current_time):
        '''
        Set the board based on the current time
        '''
        if current_time > self.fullsize_timeout:
            # Set the scale
            if current_time <= self.fullsize_timeout + ZOOM_TRANSITION:
                self.scale = self.fullsize_scale - \
                    ((current_time - self.fullsize_timeout) / ZOOM_TRANSITION) \
                    * (self.fullsize_scale - self.smallsize_scale)
            else:
                self.scale = self.smallsize_scale
        else:
            self.scale = self.fullsize_scale

    def _should_display_board_quali(self, current_time):
        '''
        Return True if the board should be displayed
        '''
        is_in_pit = info.graphics.isInPit
        pit_limiter_on = info.physics.pitLimiterOn

        return current_time > 0.2 and self.current_lap > 0 and \
            (current_time < self.display_timeout or
                self.display_timeout == -1) and \
            (not pit_limiter_on or not is_in_pit)

    def _update_board_quali(self):
        '''
        Displays:
         Position
         Name of car ahead in the standings (if any)
         Last laptime
        '''
        text = []

        current_time = info.graphics.iCurrentTime / 1000  # convert to seconds
        last_lap = info.graphics.iLastTime
        time_left = info.graphics.sessionTimeLeft

        car = self.get_player_car()
        if not car:
            return text

        ahead = self.get_car_by_position(car.position - 1)

        text.append(Text('P%d' % car.position))

        # Display name of car ahead in the standings (if any)
        if ahead:
            text.append(Text(ahead.get_name()))
            if car.best_lap and ahead.best_lap:
                text.append(
                    Text(ms_to_str((car.best_lap - ahead.best_lap)), 'r')
                )
            else:
                text.append(Text())
        else:
            text += [Text(), Text()]

        # Display own lap time
        if last_lap and car.best_lap:
            text.append(Text(time_to_str(last_lap)))
            if self.last_best_lap and car.best_lap != self.last_best_lap:
                # There is a new best lap
                delta = (last_lap - self.last_best_lap)
            else:
                delta = (last_lap - car.best_lap)
            if delta:
                colour = 'g' if delta < 0 else 'r'
                text.append(Text(ms_to_str(delta), colour))
            else:
                text.append(Text())

        # Display time left in session
        if time_left > 0:
            text.append(Text('LEFT ' + time_to_str(time_left, show_ms=False)))

        if self._should_display_board_quali(current_time):
            self._set_scale(current_time)

            # Update the text when the board is displayed
            if self.ui.board.display is False:
                self.ui.board.update_rows(text)
                self.last_best_lap = car.best_lap
                debug('Updating board (quali), lap: %d' % self.current_lap)

                for car in self.cars:
                    debug(car)
                debug('Text:\n %s \n' % '\n'.join([str(t) for t in text]))

            self.ui.board.display = True
        else:
            self.ui.board.display = False
            self.scale = self.fullsize_scale

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

        current_time = info.graphics.iCurrentTime / 1000  # convert to seconds
        last_lap = info.graphics.iLastTime
        session_time_left = 0
        if info.graphics.sessionTimeLeft > 0:
            session_time_left = info.graphics.sessionTimeLeft

        car = self.get_player_car()
        if not car:
            return text

        ahead = self.get_car_by_position(car.position - 1)
        behind = self.get_car_by_position(car.position + 1)

        if info.static.isTimedRace:
            text.append(Text('P%d - R%s' %
                (car.position, time_to_str(session_time_left, show_ms=False))))
        else:
            text.append(Text('P%d - L%d' %
                (car.position, self.laps - self.current_lap)))

        # Get current split times
        splits = self._get_splits(car)

        # Display split to car ahead (if any)
        if ahead and splits[ahead]:
            text.append(Text(ahead.get_name()))
            line = split_to_str(splits[ahead], arrows=True)
            colour = len(line) * 'r'

            if ahead in self.last_splits:
                delta = round_delta(splits[ahead]) - \
                        round_delta(self.last_splits[ahead])

                if self.detailed_delta:
                    line += ' (%s)' % split_to_str(delta)

                if delta.total_seconds() > 0:
                    colour = 'r' + colour[1:] + 'r'
                else:
                    colour = 'g' + colour[1:] + 'g'

            text.append(Text(line, colour))
        else:
            text += [Text(), Text()]

        # Display own lap time
        if last_lap:
            text.append(Text(time_to_str(last_lap)))

        # Display split to car behind (if any)
        if behind and splits[behind]:
            line = split_to_str(splits[behind], arrows=True)
            colour = len(line) * 'g'

            if behind in self.last_splits:
                delta = round_delta(splits[behind]) - \
                        round_delta(self.last_splits[behind])

                if self.detailed_delta:
                    line += ' (%s)' % split_to_str(delta)
                else:
                    line += ' (%s)' % split_to_str(delta)[0]

                if delta.total_seconds() > 0:
                    colour = 'r' + colour[1:] + 'r'
                else:
                    colour = 'g' + colour[1:] + 'g'

            text.append(Text(line, colour))
            text.append(Text(behind.get_name()))
        else:
            text += [Text(), Text()]

        if current_time > 0.2 and self.current_lap > 0 and \
                (current_time < self.display_timeout or
                 self.display_timeout == -1):
            # TODO: hide/display in pits (same as quali)
            # Display the board for the first 30 seconds, or once passed
            # the finish line

            self._set_scale(current_time)

            # Update the text and save the current splits when the board is
            # displayed
            if self.ui.board.display is False:
                debug('Updating board (race), lap: %d' % self.current_lap)
                debug('Last splits:\n%s' % debug_splits(self.last_splits))
                debug('Current splits:\n%s' % debug_splits(splits))
                for car in self.cars:
                    debug(car)
                debug('Text:\n %s \n' % '\n'.join([str(t) for t in text]))
                self.ui.board.update_rows(text)
                self.last_splits = splits

            self.ui.board.display = True
        else:
            self.ui.board.display = False
            self.scale = self.fullsize_scale

    def _update_cars(self):
        for i in range(ac.getCarsCount()):
            try:
                car = self.cars[i]
            except IndexError:
                name = ac.getDriverName(i)
                if name == -1:
                    # No such car
                    break
                car = Car(i, name, self, self.session_type)
                self.cars.append(car)

            car.update_data(self.session_type)

        if self.session_type == RACE:
            # Update the cars' race position, we could use
            # ac.getCarRealTimeLeaderboardPosition but it's not always reliable:
            for i, car in enumerate(sorted(
                    self.cars, key=lambda car: (-car.lap, -car.spline_pos))):
                car.position = i + 1

    def _update_fuel(self):
        # TODO:
        # Add variables to session
        #  - initial_fuel = -1
        #  - current_fuel = -1
        #  - refule_lap
        #  - fuel_consumption = -1
        #
        # If car is out of pit current fuel is > initial_fuel then update
        # initial fuel and reset initial_lap and fuel_consumption
        # (perhaps keep track of the old fuel_consumption in case of refueling
        # during pit stop?)
        #
        # If the car has travelled more than 1 lap since fuel reset then
        # update fuel consumption
        #
        # Add variable "should pit" if the amount of fuel left is less than 2
        # laps (configurable in UI?)
        #
        # Add variable "fuel need" to keep track of how much fuel is needed
        # to finish the race from the end of the current lap (check if
        # the new AC pit app asks for total amount or added amount of fuel
        #
        # Also keep track of min and max pit window: the player should pit
        # before the end of the pit window
        #
        # TODO: handle race/session restarts
        # TODO: How to handle when refueling with less fuel? (fuel change with car stopped?)

        current_fuel = info.physics.fuel

        # In hotlap mode the car starts before the pit straight but still
        # appears a lap 0, so we can compare the expected distance with the
        # actual distance
        if self.current_lap == 0 and info.graphics.distanceTraveled < (info.static.trackSPlineLength * info.graphics.normalizedCarPosition):
            return

        # When the car is in the pits we don't update the fuel info:
        if info.graphics.isInPit:
            return

        if current_fuel > 0 and current_fuel > self.current_fuel:
            # Player has refueled
            self.initial_fuel = current_fuel
            self.refuel_lap = self.current_lap + info.graphics.normalizedCarPosition
            # TODO: Should we reset fuel consumption as well?

            debug('Refuel: %s' % current_fuel)
            debug('Refuel lap: %f' % self.refuel_lap)
            debug('Consumption: %f' % self.fuel_consumption)

        self.current_fuel = current_fuel

        # If we've travelled at least one lap, update the average fuel consumption
        travelled_laps = self.current_lap + info.graphics.normalizedCarPosition - self.refuel_lap

        if travelled_laps < self.travelled_laps or \
                (travelled_laps - self.travelled_laps > 0.5):
            # When crossing the start finish line sometimes the spline gets
            # at a different time than  the current_lap which results in
            # incorrect data
            # We skip it if it looks like we've moved more than 1/2 a lap
            # since last update
            return
        else:
            self.travelled_laps = travelled_laps

        if travelled_laps > 1:
            self.fuel_consumption = (self.initial_fuel - current_fuel) / travelled_laps
        debug('Consumption: %f %d %f' % (self.fuel_consumption, self.current_lap, info.graphics.normalizedCarPosition))

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

    def render(self):
        '''
        Render the UI at the given scale
        '''
        self.ui.render(self.opacity, self.scale, self.orientation_x,
                       self.orientation_y)

    def save_prefs(self):
        '''
        Save preferences to JSON file
        '''
        try:
            f = open(PREFS_PATH, 'w')
        except Exception as e:
            ac.console('Can\'t open file "%s" for writing: %s' %
                       (PREFS_PATH, e))
            return

        data = dict((key, getattr(self, key)) for key in PREFS_KEYS)

        f.write(json.dumps(data))
        f.close()
        ac.console('Wrote prefs to file: %s' % data)

    def update_board(self):
        if self.session_status == REPLAY:
            # The board is not shown in replay mode
            self.ui.board.display = False
        elif self.session_type == RACE:
            self._update_board_race()
        elif self.session_type in (PRACTICE, QUALIFY, HOTLAP):
            self._update_board_quali()

    def update_data(self):
        self._check_session()
        self._update_cars()
        self._update_fuel()

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
    global session

    try:
        session.update_data()
        session.update_board()
        session.ui.update_ui()
    except:  # pylint: disable=W0702
        exc_type, exc_value, exc_traceback = sys.exc_info()
        ac.console('pitboard Error (logged to file)')
        ac.log(repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))


def render_callback(deltaT):
    global session

    try:
        session.render()
    except:  # pylint: disable=W0702
        exc_type, exc_value, exc_traceback = sys.exc_info()
        ac.console('pitboard Error (logged to file)')
        ac.log(repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))


def activated_callback(value):
    global session
    session.ui.activated()


#  Misc UI callbacks
def callback_detailed_delta_checkbox_changed(name, state):
    global session

    session.detailed_delta = state is 1


def callback_display_timeout_spinner_changed(value):
    global session

    session.display_timeout = value


def callback_fullsize_scale_spinner_changed(value):
    global session

    session.fullsize_scale = value / 100.0


def callback_fullsize_timeout_spinner_changed(value):
    global session

    session.fullsize_timeout = value


def callback_short_name_checkbox_changed(name, state):
    global session

    session.short_names = state is 1


def callback_smallsize_scale_spinner_changed(value):
    global session

    session.smallsize_scale = value / 100.0


def callback_use_surname_checkbox_changed(name, state):
    global session

    session.use_surname = state is 1


def callback_opacity_spinner_changed(value):
    global session

    session.opacity = value / 100.0


def callback_orientation_button(x, y):
    global session

    session.ui.orientation_button_click()


def callback_prefs_button(x, y):
    global session

    session.ui.prefs_button_click()

#! python
# coding=utf-8
#
# Small program to be installed in e.g. PATH, while real
# program is in a python package directory and accessible
# by import -- this version is written for MSWindows and
# should have suffix .pyw or be interpreted with pythonw.exe.
#
# Copyright (C) 2017 Ed Hynan
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.
#

import os
import sys

_script_path = os.path.realpath(__file__)
_script_dir  = os.path.dirname(_script_path)
_script_pkgs = os.path.join(_script_dir, 'pkgs')

sys.path.insert(0, _script_pkgs)

from wxmav_main import wxmav_main

if __name__ == '__main__':
    sys.exit(wxmav_main(argv = sys.argv))

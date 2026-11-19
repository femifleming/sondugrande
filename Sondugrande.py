#!/usr/bin/env python
# encoding: utf-8
"""
Sondugrande - SoundGrain in a room: draw where the sound moves in space.

A development of SoundGrain, Copyright 2009-2017 Olivier Belanger.

Sondugrande is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Sondugrande is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Sondugrande.  If not, see <http://www.gnu.org/licenses/>.

    Sondugrande                      the application
    Sondugrande project.sgr          open a project (a SoundGrain .sg opens too)
    Sondugrande --render ...         render a project offline (see sondugrande/render.py)
    Sondugrande --selftest folder    start, draw, play, record, check and quit
"""
import os
import sys


def main():
    """Launch Sondugrande, optionally opening a project supplied on the command line."""
    args = sys.argv[1:]
    # a windowed program on Windows has no console to write to
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")
    if args and args[0] == "--render":
        from sondugrande import render
        return render.main(args[1:])
    if args and args[0] == "--version":
        from sondugrande.constants import NAME, SG_VERSION, SOUNDGRAIN_VERSION
        print("%s %s (SoundGrain %s)" % (NAME, SG_VERSION, SOUNDGRAIN_VERSION))
        return 0
    if args and args[0] == "--selftest":
        from sondugrande import selftest
        return selftest.main(args[1:])
    from sondugrande.app import run
    return run(args[0] if args and not args[0].startswith("-") else None)


if __name__ == '__main__':
    sys.exit(main() or 0)

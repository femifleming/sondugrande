#!/usr/bin/env python
# encoding: utf-8
"""
Songrande - SoundGrain in a room: draw where the sound moves in space.

A development of SoundGrain, Copyright 2009-2017 Olivier Belanger.

Songrande is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Songrande is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Songrande.  If not, see <http://www.gnu.org/licenses/>.

    Songrande                      the application
    Songrande project.sgr          open a project (a SoundGrain .sg opens too)
    Songrande --render ...         render a project offline (see songrande/render.py)
    Songrande --selftest folder    start, draw, play, record, check and quit
"""
import os
import sys


def main():
    """Launch Songrande, optionally opening a project supplied on the command line."""
    args = sys.argv[1:]
    # a windowed program on Windows has no console to write to
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")
    if args and args[0] == "--render":
        from songrande import render
        return render.main(args[1:])
    if args and args[0] == "--version":
        from songrande.constants import NAME, SG_VERSION, SOUNDGRAIN_VERSION
        print("%s %s (SoundGrain %s)" % (NAME, SG_VERSION, SOUNDGRAIN_VERSION))
        return 0
    if args and args[0] == "--selftest":
        from songrande import selftest
        return selftest.main(args[1:])
    from songrande.app import run
    return run(args[0] if args and not args[0].startswith("-") else None)


if __name__ == '__main__':
    sys.exit(main() or 0)

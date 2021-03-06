#!/usr/bin/env python3

# This file is part of pyteensy.
# 
# pyteensy is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 2.1 of the License, or
# (at your option) any later version.
# 
# pyteensy is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
# 
# You should have received a copy of the GNU Lesser General Public License
# along with pyteensy.  If not, see <http://www.gnu.org/licenses/>.
#


''' This is the teensyevents program. It is intended to make a connection
with a teensy device. It registers some input lines in order to make
output the events that occur on that line of the teensy.
'''

from __future__ import print_function
import argparse as arg
import pyteensy as t

class CmdArgs(dict):
    """Just a dictionary with some static members"""
    DEVICE      = "device"   # string with device name
    LINES       = "lines"    # list of ints to be registered 
    SINGLESHOTS = "singles"  # list of ints to be registered as singleshot
    PARALLELPORT= "parallel" # int flag
    PORT        = "port"     # int with 
    UNIX        = "unix"     # flag whether or not to use the Unix teensy flavor.
    MIN_JITTER  = "min-jitter"# float minimal jitter perion in seconds
    MAX_JITTER  = "max-jitter"# float max jitter perion in seconds
    NUMBER      = "number"   # float max jitter perion in seconds

def parse_arguments():
    '''Parses commandline arguments'''

    description = ('teensyevents is a small utility to obtain trigger events '
        'from a teensy device. The device will connect at program start and '
        'lines registered by the user via the command line arguments will be '
        'printed to stdout on program termination.')
    
    parser = arg.ArgumentParser(description=description)
    parser.add_argument(
        "-d",
        "--device",
        type=str,
        help=(r'Specify the devicename. Example = -d"/dev/ttyACM0" or '
              '--device="COM5"'),
        default="/dev/ttyACM0"
        )
    parser.add_argument(
        "-l",
        "--lines",
        type=str,
        help=("Specify multiple lines "
              "separated by comma's eeg -l\"1,2,3,17\" "
              "The lines are registered permanently.")
        )
    parser.add_argument(
        "-s",
        "--singleshots",
        type=str,
        help=("Specify multiple lines "
              "separated by comma's eeg -l\"1,2,3,17\" "
              "The lines are registered as single shot.")
        )
    parser.add_argument(
        "-p",
        "--parallel",
        type=int,
        help ="Use parallel port to run some tests specify a number",
        default=-1
        )
    parser.add_argument(
        '-u',
        '--unix',
        action = 'store_true',
        help = "Instead of Teensy use a UnixTeensy class",
        default=False
        )
    parser.add_argument(
        '--min-jitter',
        type=float,
        help=(
            "Minimal jitter period in seconds, must be larger than 0, but "
            "smaller than the --max-jitter option. The default value = 0.0 ."
            ),
        default=0.0
        )
    parser.add_argument(
        '--max-jitter',
        type=float,
        help=(
            "Maximum jitter period in seconds, must be larger than "
            "the --min-jitter option. The default value = 1.0 ."
            ),
        default=1.0
        )
    parser.add_argument(
        '-n',
        '--number',
        type=int,
        help="The number toggles on the parallel port.",
        default=120
        )

    results = parser.parse_args()

    d = CmdArgs()
    if results.lines :
        linelist = [int(i) for i in results.lines.split(",")]
        d[d.LINES]      = linelist
    else:
        d[d.LINES]      = []

    if results.singleshots:
        linelist = [int(i) for i in results.singleshots.split(",")]
        d[d.SINGLESHOTS]= linelist
    else:
        d[d.SINGLESHOTS]= []

    if results.device:
        d[d.DEVICE]     = results.device
    
    d[d.PARALLELPORT] = results.parallel
    d[d.UNIX] = True if results.unix else False
    d[d.MIN_JITTER] = results.min_jitter
    d[d.MAX_JITTER] = results.max_jitter
    d[d.NUMBER] = results.number

    return d

def reg_lines(teensy, cmdargs):
    for i in cmdargs[cmdargs.LINES]:
        try:
            teensy.register_line(i)
        except t.TeensyError as e:
            if e.error == t.TeensError.INVALID_TRIGGER_LINE:
                exit("{} is an invalid trigger line.".format(i))
            else:
                exit(str(e))

def reg_single_shots(teensy, cmdargs):
    for i in cmdargs[cmdargs.SINGLESHOTS]:
        try:
            teensy.register_single_shot(i)
        except t.TeensError as e:
            if e.error == t.TeensError.INVALID_TRIGGER_LINE:
                exit("{} is an invalid trigger line.".format(i))
            else:
                exit(str(e))

def print_events(teensy, **kwargs):
    '''Gets all event from the teensy and prints them to a file
    The kwargs may be used as kwargs for the print function
    '''
    q = teensy.events
    while not q.empty():
        event = q.get(False)
        print(event, **kwargs)

def compare_events(times, queue):
    import numpy as np
    stamps = []
    while not queue.empty():
        stamps.append(queue.get().timestamp)
    stamps = np.array(stamps, dtype=float)
    stamps = stamps/1e6 # convert to seconds
    diffstamps = np.diff(stamps)
    difftimes  = np.diff(times)
    diffs = np.array([diffstamps, difftimes]).transpose()
    print(diffs)
    difference = difftimes - diffstamps
    print(difference.mean())
    difference[difference < 0] *= -1
    print(difference.mean())

def run_teensy_events():
    '''Runs the teensy events program; it is the main function.'''
    import sys
    import time
    arguments = parse_arguments()
    
    parport = None
    if arguments[arguments.PARALLELPORT] >= 0:
        import parallelpulse as pp
        try: 
            parport = pp.TogglePort(arguments[arguments.PARALLELPORT])
        except IOError:
            print(
                ("To resolve this IOError read the note in"
                 "parallelpulse.py docstring"),
                file=sys.stderr)
            raise
    
    # Select the proper Teensy Class
    if arguments[arguments.UNIX]:
        from pyteensy import UnixTeensy as Teensy
    else:
        from pyteensy import Teensy as Teensy

    trigtimes = []
    with Teensy(arguments[arguments.DEVICE]) as teensy:
        if not teensy.connected:
            exit(1)
        reg_lines(teensy, arguments)
        reg_single_shots(teensy, arguments)
        if parport: 
            print(
                "Using the parallel port to determine whether the teensy works."
                )
            trigtimes = pp.pulse_train(
                parport,
                number=arguments[arguments.NUMBER],
                jitter=(
                    arguments[arguments.MIN_JITTER],
                    arguments[arguments.MAX_JITTER]
                    )
                )
            time.sleep(.5)
            compare_events(trigtimes, teensy.events)
        else:
            print("Press ctr+D or ctrl+C to stop.")
            try:
                input()
            except EOFError:
                pass
            except KeyboardInterrupt:
                pass
            finally:
                print_events(teensy)

if __name__ == "__main__":
    run_teensy_events()

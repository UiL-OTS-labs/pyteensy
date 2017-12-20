#!/usr/bin/env python

#
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


'''Send some pulses on the parallel port.

NOTE:

For some systems it is important to rmmod the lp kernel module
and subsequently modprob the ppdev module, otherwise when the parallel.Parallel
class tries to claim a device it will throw a IOError with #6
'''

from __future__ import print_function

import numpy as np
import time
import threading
import parallel
try:
    #python3
    import queue as q
except ImportError:
    #python2
    import Queue as q

class TogglePort(object):
    '''
    Toggles the datalines of the parallel port
    '''
    
    ON = 0xFF
    OFF= 0x00

    def __init__(self, value=0xFF, port=0):
        '''Opens port and sets data.'''
        self.data = self.ON if value else self.OFF
        try :
            self.port = parallel.Parallel("/dev/parport{}".format(int(port)))
        except IOError:
            import sys
            print("\n\nplease read the NOTE in the program docstring\n\n",
                  file=sys.stderr)
            raise
        self.port.setData(self.data)
    
    def toggle(self):
        '''Toggle all lines from on to off or vice versa.
        '''
        self.data = self.ON if (self.data != self.ON) else self.OFF
        self.port.setData(self.data)

class _ToggleSignal(object):
    ''' a Callable object that can toggle a port and return the timestamp
    of when the port is toggled.
    '''

    def __init__(self, tport):
        self.tport = tport
        self.queue = q.Queue()
    
    def wait(self):
        '''returns the time when the port is toggled.'''
        return self.queue.get()

    def __call__(self):
        self.queue.put(time.time())
        self.tport.toggle()

def pulse_train(toggle, number=120, jitter=(0.0,1.0)):
    ''' Apply a train of toggle pulses, the interval will best described
    between a random value between jitter[0] and jitter[1]. So the default
    pulse train consists of 120 pulses with an uniform interval between 
    0 and 1 second. So it lasts about one minute.
    it returns the jittered interval between the pulses.
    '''
    arr         = np.random.uniform(jitter[0], jitter[1], int(number))
    signal      = _ToggleSignal(toggle)
    timestamps  = []
    for second in arr:
        waitobj = threading.Timer(second, signal)
        waitobj.start()
        timestamps.append(signal.wait())
    return timestamps

def _test():
    port = TogglePort(0)
    pulse_train(port, number=30)

if __name__ == "__main__":
    _test()

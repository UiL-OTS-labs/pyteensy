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

'''The pyteensy module exports the Teensy class and some utilities to use.
'''

from __future__ import print_function
import struct
import threading
import select
import os

try:
    # python 3
    import queue as q
except ImportError:
    # python 2
    import Queue as q

import serial as s
import serial.tools.list_ports
import pyteensy_version as pv

def list_devices():
    '''lists the available serial devices'''
    devs = serial.tools.list_ports.comports()
    return devs

def version():
    '''returns the current version of pyteensy.'''
    return pv.get_version()


ZEP_TEENSY_TO_ZEP_UUID = b"7d945241-0238-4c29-95e4-7d9864710ea2"
ZEP_ZEP_TO_TEENSY_UUID = b"91ae4c34-00b0-4d91-9000-ccc0989ac92a"

class _TeensyPackage(object):
    '''TeensyPackages are the packages that are send over the serial
    connection in order to communicate with a Teensy device. Teensy
    package contain a bytearray as internal buffer. Currently, the buffer
    can be at most 256 bytes long. A buffer contains a header of two bytes
    The first byte indicates the total length of the buffer and the second
    byte, determines the kind of message that is send.
    So conceptualy the buffer is something like:
    [messagesize, message type, 'p','a', 'y', 'l', 'o', 'a', 'd', '.', '.']
    Hence, the smallest packet send is a header only packet and the largest
    is a packet of 256 bytes with a header header + a payload of 254 bytes.
    '''

    # Message headers / identifies the type of message/package.
    IDENTIFY = 1
    REGISTER_INPUT = 2
    REGISTER_SINGLE_SHOT = 3
    DEREGISTER_INPUT = 4
    TIME = 5
    TIME_SET = 6
    ACKNOWLEDGE_SUCCES = 7
    ACKNOWLEDGE_FAILURE = 8
    ACKNOWLEDGE_LINE_INVALID = 9
    ACKNOWLEDGE_TIME = 10
    EVENT_TRIGGER = 11

    # multibyte values are send in little-endian format, hence the "<".
    _HEADER = "<BB"
    _UUID = "{}s".format(len(ZEP_TEENSY_TO_ZEP_UUID))
    _BYTE = "B"
    _UINT64 = "Q"

    # struct to help with (un)packing of bytes.
    _IDENTIFY = struct.Struct(_HEADER + _UUID)
    _REGISTER_INPUT = struct.Struct(_HEADER + _BYTE)
    _REGISTER_SINGLE_SHOT = struct.Struct(_HEADER + _BYTE)
    _DEREGISTER_INPUT = struct.Struct(_HEADER + _BYTE)
    _TIME = struct.Struct(_HEADER)
    _TIME_SET = struct.Struct(_HEADER + _UINT64)
    _ACKNOWLEDGE_SUCCES = struct.Struct(_HEADER)
    _ACKNOWLEDGE_FAILURE = struct.Struct(_HEADER)
    _ACKNOWLEDGE_LINE_INVALID = struct.Struct(_HEADER)
    _ACKNOWLEDGE_TIME = struct.Struct(_HEADER + _UINT64)
    _EVENT_TRIGGER = struct.Struct(_HEADER + _BYTE + _UINT64 + _BYTE)

    # header and maximum message payload size.
    _HDR_SZ = 2
    _MSG_SZ = 254

    # a dict that returns the right function to parse the message
    _payload_dict = {
        IDENTIFY                : _IDENTIFY.unpack,
        REGISTER_INPUT          : _REGISTER_INPUT.unpack,
        REGISTER_SINGLE_SHOT    : _REGISTER_SINGLE_SHOT.unpack,
        DEREGISTER_INPUT        : _DEREGISTER_INPUT.unpack,
        TIME                    : _TIME.unpack,
        TIME_SET                : _TIME_SET.unpack,
        ACKNOWLEDGE_SUCCES      : _ACKNOWLEDGE_SUCCES.unpack,
        ACKNOWLEDGE_FAILURE     : _ACKNOWLEDGE_FAILURE.unpack,
        ACKNOWLEDGE_LINE_INVALID: _ACKNOWLEDGE_LINE_INVALID.unpack,
        ACKNOWLEDGE_TIME        : _ACKNOWLEDGE_TIME.unpack,
        EVENT_TRIGGER           : _EVENT_TRIGGER.unpack
    }

    _events = set([EVENT_TRIGGER])

    def parse_packet(self):
        '''Parses the bytearray self.buf and returns a tuple of
        size, message_type and payload or None
        '''
        return self._payload_dict[self.buf[1]](self.buf)

    def __init__(self, buffer : bytearray = bytearray()):
        self.buf = buffer

    def __iter__(self):
        return iter(self.buf)

    def set_buffer(self, buf : bytearray):
        '''Set the buffer of the _TeensyPackage'''
        self.buf = buf

    def is_event(self) -> bool:
        '''returns whether or not this packet contains an teensy event'''
        if self.buf and len(self.buf) >= 2:
            return self.pkgtype() in self._events
        else:
            return false

    def prepare_identify(self, uuid):
        '''Prepares a Teensy packet to send an identify message to the Teensy.
        '''
        self.buf = bytearray(
            self._IDENTIFY.pack(
                self._HDR_SZ + len(uuid),
                self.IDENTIFY,
                uuid
                )
            )

    def prepare_register(self, line):
        '''Construct a message to send to register a trigger line.'''
        self.buf = bytearray(
            self._REGISTER_INPUT.pack(
                self._HDR_SZ + 1,
                self.REGISTER_INPUT,
                line
                )
            )

    def prepare_deregister(self, line):
        '''Construct a package to deregister a trigger line.'''
        self.buf = bytearray(
            self._DEREGISTER_INPUT.pack(
                self._HDR_SZ + 1,
                self.DEREGISTER_INPUT,
                line
                )
            )

    def prepare_single_shot(self, line):
        ''''Prepare a message to register a line on the teensy as singleshot.'''
        self.buf = bytearray(
            self._REGISTER_SINGLE_SHOT.pack(
                self._HDR_SZ + 1,
                self.REGISTER_SINGLE_SHOT,
                line
                )
            )

    def prepare_time(self):
        '''Prepare a message to request the teensy time.'''
        self.buf = bytearray(
            self._TIME.pack(
                self._HDR_SZ,
                self.TIME
                )
            )

    def prepare_set_time(self, time_us):
        '''Prepare a message to set the teensy time.'''
        self.buf = bytearray(
            self._TIME_SET.pack(
                self._HDR_SZ + 8,
                self.TIME_SET,
                time_us
                )
            )

    def pkgtype(self):
        '''Returns the package type'''
        return self.buf[1]

    def payload(self):
        '''Returns the package payload as a bytes array object'''
        return self.buf[2:]

    def __len__(self):
        return self.buf[0]

class TeensyEvent(object):
    '''An event send by a Teensy device to the worker thread of a python
    Teensy object. Currently there is only one Type of event. The most
    characterizing property of an event is that has a time stamp.
    '''
    def __init__(self, timestamp):
        '''Sets the timestamp'''
        self.timestamp = timestamp

    def __str__(self):
        raise NotImplementedError('Override this in subclass')

class TeensyLineEvent(TeensyEvent):
    '''This is a line event, it contains a value of the line that was
    triggered, a value whether the line went high or low and a timestamp.
    '''

    LOW = 0
    HIGH = 1

    def __init__(self, time, line, logiclevel):
        super(TeensyLineEvent, self).__init__(time)
        self.line = line
        self.logiclevel = self.HIGH if logiclevel else self.LOW

    def __str__(self):
        return "{}\t{}\t{}".format(self.timestamp, self.line, self.logiclevel)

class TeensyError(Exception):
    '''If an error occurs with a teensy device this will be raised.'''

    NO_ERROR = 0
    NOT_A_TEENSY = 1
    NOT_CONNECTED = 2
    UNABLE_TO_CONNECT = 3
    INVALID_TRIGGER_LINE = 4
    TEENSY_ERROR = 5

    _errdict = {
        NOT_A_TEENSY        : "Connected to something that is not a Teensy",
        NOT_CONNECTED       : "Operation requires a valid connection",
        UNABLE_TO_CONNECT   : "Unable to connect",
        INVALID_TRIGGER_LINE: "Invalid trigger line",
        TEENSY_ERROR        : "Unspecified Teensy error."
    }

    def __init__(self, error, extra=None):
        self.int_error = error
        self.extra = extra
        super(TeensyError, self).__init__()

    def __str__(self):
        if self.extra:
            return "TeensyError: {}, Extra info: {}".format(
                self._errdict[self.int_error], self.extra
                )
        else:
            return "TeensyError: {}".format(self._errdict[self.int_error])


class _TeensyTask(object):
    ''' Is used to communicate between the teensy client and the Teensy
    internal thread.
    '''
    def __init__(self, task, *args, **kwargs):
        self.task = task
        self.args = args
        self.kwargs = kwargs

    def has_payload(self):
        '''Returns whether the task has a payload/extra argument for the
        handler inside the thread.
        '''
        return len(self.args) or len(self.kwargs)

    def get_task(self):
        '''Return the task on hand'''
        return self.task

    def get_args(self):
        '''Return the args for the task'''
        return self.args

    def get_kwargs(self):
        '''Return the keyword arguments for the task'''
        return self.kwargs

class Teensy(object):
    '''Class that communicates with a teensy device.

    A device is opened on connection and subsequently a thread is started.
    Writing to the teensy device occurs from the thread. The thread monitors
    The eventqueue from the client and post a reply back, in the meanwhile the
    thread monitors events from the Teensy device.
    '''

    READ_TIMEOUT = 0.0001

    def __init__(self, devfn="/dev/ttyACM0"):
        ''' Opens communication with serial device.
        devfn is a path to the device name or something like COM5 on windows.
        '''
        super(Teensy, self).__init__()
        self.connected = False
        self._quit = None   # Becomes an event to stop the thread.
        self._thread = None   # Becomes the thread on connection
        self._tqueue = None   # Becomes Task queue on connection
        self._aqueue = None   # Becomes Answer queue on connection
        self.events = None   # Becomes queue for events on connection

        if devfn:
            self.connect(devfn)
        else:
            self._serial = None

    def close(self):
        ''' Closes the thread and the serial connection
        Make sure not to forget to call this function when you don't need
        the teensy anymore. In case of emergency use
        the "with Teensy() as instance:" syntax. If you forget to use this
        the thread doesn't shut down.
        '''
        self._quit.set()
        self._thread.join(0.1)
        if self._thread.isAlive():
            raise RuntimeError("Unable to close Teensy thread.")
        self._serial.close()

    def connect(self, devfn):
        '''Connects the instance of a Teensy class with an actual teensy
        instance. If the connection is successful, the internal thread
        to communicate with the device is started.
        '''
        if self.connected:
            self.close()
        try:
            self._serial = s.Serial(devfn, timeout=Teensy.READ_TIMEOUT)
        except s.SerialException as err:
            # Raise SerialException as a TeensyError()
            raise TeensyError(
                TeensyError.UNABLE_TO_CONNECT,
                str(err)
                )
        # empty queues to be sure.
        self._tqueue = q.Queue()
        self._aqueue = q.Queue()
        self.events = q.Queue()

        self._start_thread()

    def _start_thread(self):
        ''' Starts the internal thread.
        '''
        self._thread = threading.Thread(target=self.run, name=repr(self))
        self._thread.start()
        
        #sync with thread
        ans = self._aqueue.get(True, 1)
        if ans:
            raise TeensyError(ans)
        self.connected = True

    def run(self):
        ''' The Teensy thread, the Teensy is read from or written to from here.
        '''
        assert self._serial
        self._quit = threading.Event()
        timeout = 0.001 #one millisecond
        tasks = self._tqueue
        reply = self._aqueue

        try:
            self._identify()

            #sync with client
            reply.put(TeensyError.NO_ERROR)

            while not self._quit.is_set():
                try:
                    task = tasks.get(True, timeout)
                    answer = self._handle_task(task)
                    reply.put(answer)
                except q.Empty:
                    # Fetch events while we have incoming data.
                    while self._serial.in_waiting:
                        self._fetch_event()
        except Exception:
            # Abort from thread when an uncaught exception occurs.
            import sys
            import traceback
            print(traceback.print_exc(), file=sys.stderr)
            self.connected = False
            return

    def handle_event(self, event):
        '''When an event is received it is handled inside this handler. If
        you want custom behavior, you might want to override this function
        in a subclass. The default behavior is to queue all events inside
        the self.events member.
        '''
        self.events.put(event)

    def _read_packet(self, handle_event:bool=True) -> _TeensyPackage:
        '''Reads one packet from the stream, if it is an event it will be
        handled.'''
        while True:
            tbuf = bytearray()
            while not tbuf:
                tbuf.extend(self._serial.read())
            totsize = tbuf[0]
            while len(tbuf) != totsize:
                tbuf.extend(self._serial.read(totsize - len(tbuf)))
            pkt = _TeensyPackage(tbuf)
            if handle_event and pkt.is_event():
                _, _, line, timestamp, logic = pkt.parse_packet()
                self.handle_event(TeensyLineEvent(timestamp, line, logic))
            else:
                return pkt

    def _write_packet(self, pkt: _TeensyPackage):
        '''Write one teensy packet to the Teensy Device.'''
        self._serial.write(pkt)

    def _fetch_event(self):
        '''Try to read one event from the serial device.'''
        package = self._read_packet(False)
        assert package.is_event()
        _, _, line, timestamp, logic = package.parse_packet()
        event = TeensyLineEvent(timestamp, line, logic)
        self.handle_event(event)

    def _identify(self):
        '''Does a handshake with the teensy'''
        package = _TeensyPackage()
        package.prepare_identify(ZEP_ZEP_TO_TEENSY_UUID)
        self._write_packet(package)
        package = self._read_packet()
        _, type_, uuid = package.parse_packet()
        if type_ != _TeensyPackage.IDENTIFY:
            return TeensyError.NOT_A_TEENSY
        if uuid != ZEP_TEENSY_TO_ZEP_UUID:
            return TeensyError.NOT_A_TEENSY
        return TeensyError.NO_ERROR

    def register_line(self, line):
        '''Register one line on the teensy device. The line will trigger on
        rising and falling flanks.
        '''
        if not self.connected:
            raise TeensyError(TeensyError.NOT_CONNECTED)
        task = _TeensyTask(_TeensyPackage.REGISTER_INPUT, line)
        self._tqueue.put(task)
        reply = self._aqueue.get()
        if reply:
            raise TeensyError(reply)

    def _register_line(self, line):
        package = _TeensyPackage()
        package.prepare_register(line)
        self._write_packet(package)
        package = self._read_packet()
        _, reply = package.parse_packet()
        if   reply == _TeensyPackage.ACKNOWLEDGE_SUCCES:
            return TeensyError.NO_ERROR
        elif reply == _TeensyPackage.ACKNOWLEDGE_LINE_INVALID:
            return TeensyError.INVALID_TRIGGER_LINE
        else:
            return TeensyError.TEENSY_ERROR

    def register_single_shot(self, line):
        ''' Register a single shot Teensy line. The line can be triggered once.
        It depends on the current state of the Teensy whether it will be a
        rising or a falling flank.
        '''
        if not self.connected:
            raise TeensyError(TeensyError.NOT_CONNECTED)
        task = _TeensyTask(_TeensyPackage.REGISTER_SINGLE_SHOT, line)
        self._tqueue.put(task)
        reply = self._aqueue.get()
        if reply:
            raise TeensyError(reply)

    def _register_single_shot(self, line):
        package = _TeensyPackage()
        package.prepare_single_shot(line)
        self._write_packet(package)
        package = self._read_packet()
        _, reply, _ = package.parse_packet()
        if   reply == _TeensyPackage.ACKNOWLEDGE_SUCCES:
            return TeensyError.NO_ERROR
        elif reply == _TeensyPackage.ACKNOWLEDGE_LINE_INVALID:
            return TeensyError.INVALID_TRIGGER_LINE
        else:
            return TeensyError.TEENSY_ERROR

    def deregister_input(self, line):
        '''Deregister a previously registerd (single_shot) line.'''
        if not self.connected:
            raise TeensyError(TeensyError.NOT_CONNECTED)
        task = _TeensyTask(_TeensyPackage.DEREGISTER_INPUT, line)
        self._tqueue.put(task)
        reply = self._aqueue.get()
        if reply:
            raise TeensyError(reply)

    def _deregister_input(self, line):
        package = _TeensyPackage()
        package.prepare_deregister(line)
        self._write_packet(package)
        package = self._read_packet()
        _, reply = package.parse_packet()
        assert reply == _TeensyPackage.ACKNOWLEDGE_SUCCES
        return TeensyError.NO_ERROR

    def time(self):
        '''Obtain a timestamp from the Teensy.
        '''
        if not self.connected:
            raise TeensyError(TeensyError.NOT_CONNECTED)
        task = _TeensyTask(_TeensyPackage.TIME)
        self._tqueue.put(task)
        reply, time = self._aqueue.get()
        if reply:
            raise TeensyError(reply)
        return time

    def _time(self):
        package = _TeensyPackage()
        package.prepare_time()
        self._write_packet(package)
        package = self._read_packet()
        _, reply, time = package.parse_packet()
        if reply == _TeensyPackage.ACKNOWLEDGE_TIME:
            return TeensyError.NO_ERROR, time
        else:
            return TeensyError(TeensyError.TEENSY_ERROR), None

    def time_set(self, time):
        '''
        '''
        pass

    def _time_set(self):
        pass

    def _handle_task(self, task):
        '''Handles a Teensy task, like registering a input line etc.
        A task is a list of [TeensyPackage.MESSAGE and it arguments]
        '''
        #alias
        tp = _TeensyPackage
        tasks = {
            #tp.IDENTIFY             : None, # is handled differently
            tp.REGISTER_INPUT       : self._register_line,
            tp.REGISTER_SINGLE_SHOT : self._register_single_shot,
            tp.DEREGISTER_INPUT     : self._deregister_input,
            tp.TIME                 : self._time,
            tp.TIME_SET             : self._time_set,
            #tp.ACKNOWLEDGE_SUCCES only on teensy not on client
        }
        return tasks[task.task](*task.args, **task.kwargs)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

class UnixTeensy(Teensy):

    '''This class is just like the original teensy, however, it doesn't use
    the serial library, but reads straight from a device file eeg:
    /dev/ttyACM0.
    If I use the serial library, I experience that using the serial library
    consumes about all the processing power of one processor core. This class
    is written to address that issue.
    '''
    
    def __init__(self, devfn="/dev/ttyACM0"):
        ''' Opens communication with serial device.
        devfn is a path to the device name or something like COM5 on windows.
        '''
        self.connected = False
        self._quit = None   # Becomes an event to stop the thread.
        self._thread = None   # Becomes the thread on connection
        self._tqueue = None   # Becomes Task queue on connection
        self._aqueue = None   # Becomes Answer queue on connection
        self.events = None   # Becomes queue for events on connection

        if devfn:
            self.connect(devfn)
        else:
            self._serial = None

    def close(self):
        ''' Closes the thread and the serial connection
        Make sure not to forget to call this function when you don't need
        the teensy anymore. In case of emergency use
        the "with Teensy() as instance:" syntax. If you forget to use this
        the thread doesn't shut down.
        '''
        self._quit.set()
        self._thread.join(0.1)
        if self._thread.isAlive():
            raise RuntimeError("Unable to close Teensy thread.")
        os.close(self._serial)

    def connect(self, devfn):
        '''Connects the instance of a Teensy class with an actual teensy
        instance. If the connection is successful, the internal thread
        to communicate with the device is started.
        '''
        if self.connected:
            self.close()
        
        flags = os.O_RDWR
        try:
            # UNIX flavors
            flags |= os.O_NOCTTY
        except AttributeError:
            # windows
            flags |= os.O_BINARY

        try:
            self._serial = os.open(devfn, flags)
        except OSError as err:
            raise TeensyError(TeensyError.UNABLE_TO_CONNECT, str(err))
        
        # empty queues to be sure.
        self._tqueue = q.Queue()
        self._aqueue = q.Queue()
        self.events = q.Queue()

        self._start_thread()

    def run(self):
        ''' The Teensy thread, the Teensy is read from or written to from here.
        '''
        assert self._serial
        self._quit = threading.Event()
        timeout = 0.001 #one millisecond
        tasks = self._tqueue
        reply = self._aqueue

        try:
            self._identify()

            #sync with client
            reply.put(TeensyError.NO_ERROR)

            poller = select.poll()
            poller.register(self._serial, select.POLLIN)

            while not self._quit.is_set():
                try:
                    task = tasks.get(True, timeout)
                    answer = self._handle_task(task)
                    reply.put(answer)
                except q.Empty:
                    fevents = poller.poll(timeout)
                    while fevents:
                        self._fetch_event()
                        fevents = poller.poll(timeout)
                        
        except Exception:
            # Abort from thread when an uncaught exception occurs.
            import sys
            import traceback
            print(traceback.print_exc(), file=sys.stderr)
            self.connected = False
            return
    
    def _read_packet(self, handle_event:bool=True) -> _TeensyPackage:
        '''Reads one packet from the stream, if it is an event it will be
        handled.'''
        while True:
            tbuf = bytearray()
            while not tbuf:
                tbuf.extend(os.read(self._serial, 1))
            totsize = tbuf[0]
            while len(tbuf) != totsize:
                tbuf.extend(os.read(self._serial, totsize - len(tbuf)))
            pkt = _TeensyPackage(tbuf)
            if handle_event and pkt.is_event():
                _, _, line, timestamp, logic = pkt.parse_packet()
                self.handle_event(TeensyLineEvent(timestamp, line, logic))
            else:
                return pkt

    def _write_packet(self, pkt: _TeensyPackage):
        '''Write one teensy packet to the Teensy Device.'''
        os.write(self._serial, pkt.buf)

def _test():
    print (version())
    print ("serial version = {}".format(s.VERSION))
    for i in list_devices():
        print(i)
    with Teensy("/dev/ttyACM0") as teensy:
        print("current teensy time = {}".format(teensy.time()))
        pass

if __name__ == "__main__":
    _test()


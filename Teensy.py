#!/usr/bin/env python3

from __future__ import print_function
import serial as s
import serial.tools.list_ports
import struct
import threading
try:
    # python 3
    import queue as q
except ImportError:
    # python 2
    import Queue as q

def list_devices():
    devs = serial.tools.list_ports.comports()
    return devs

ZEP_TEENSY_TO_ZEP_UUID = b"7d945241-0238-4c29-95e4-7d9864710ea2"
ZEP_ZEP_TO_TEENSY_UUID = b"91ae4c34-00b0-4d91-9000-ccc0989ac92a"

class _TeensyPackage(object):
    ''' TeensyPackages are the packages that are send over the serial
    connection in order to communicate with a Teensy device.
    '''

    # Message headers / identifies the type of message/package.    
    IDENTIFY                = 1
    REGISTER_INPUT          = 2
    REGISTER_SINGLE_SHOT    = 3
    DEREGISTER_INPUT        = 4
    TIME                    = 5
    TIME_SET                = 6
    ACKNOWLEDGE_SUCCES      = 7
    ACKNOWLEDGE_FAILURE     = 8
    ACKNOWLEDGE_LINE_INVALID= 9
    ACKNOWLEDGE_TIME        = 10
    EVENT_TRIGGER           = 11
    
    # multibyte values are send in little-endian format, hence the "<".
    _HEADER     = "<BB" 
    _UUID       = "{}s".format(len(ZEP_TEENSY_TO_ZEP_UUID))
    _BYTE       = "B"
    _UINT64     = "Q"

    # struct to help with (un)packing of bytes.
    _IDENTIFY                   = struct.Struct(_HEADER + _UUID)
    _REGISTER_INPUT             = struct.Struct(_HEADER + _BYTE)
    _REGISTER_SINGLE_SHOT       = struct.Struct(_HEADER + _BYTE)
    _DEREGISTER_INPUT           = struct.Struct(_HEADER + _BYTE)
    _TIME                       = struct.Struct(_HEADER)
    _TIME_SET                   = struct.Struct(_HEADER + _UINT64)
    _ACKNOWLEDGE_SUCCES         = struct.Struct(_HEADER)
    _ACKNOWLEDGE_FAILURE        = struct.Struct(_HEADER)
    _ACKNOWLEDGE_LINE_INVALID   = struct.Struct(_HEADER)
    _ACKNOWLEDGE_TIME           = struct.Struct(_HEADER + _UINT64)
    _EVENT_TRIGGER              = struct.Struct(_HEADER + _BYTE + _UINT64
                                                + _BYTE)

    # header and maximum message payload size.
    _HDR_SZ  = 2
    _MSG_SZ  = 254

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

    def parse_packet(self):
        '''Parses the bytearray self.buf and returns a tuple of
        size, message_type and payload or None
        '''
        return self._payload_dict[self.buf[1]](self.buf)

    def __init__(self):
        self.buf = bytearray([0])

    def prepare_identify(self, uuid):
        self.buf  = bytearray (
                        self._IDENTIFY.pack(
                            self._HDR_SZ + len(uuid),
                            self.IDENTIFY, 
                            uuid
                            )
                        )

    def prepare_register(self, line):
        self.buf  = bytearray (
                        self._REGISTER_INPUT.pack(
                            self._HDR_SZ + 1,
                            self.REGISTER_INPUT,
                            line
                            )
                        )

    def prepare_deregister(self, line):
        self.buf  = bytearray (
                        self._DEREGISTER_INPUT.pack(
                            self._HDR_SZ + 1,
                            self.DEREGISTER_INPUT,
                            line
                            )
                        )

    def prepare_single_shot(self, line):
        self.buf  = bytearray (
                        self._REGISTER_SINGLE_SHOT.pack(
                            self._HDR_SZ + 1,
                            self.REGISTER_SINGLE_SHOT
                            )
                        )

    def prepare_time(self):
        self.buf  = bytearray (
                        self._TIME.pack(
                            self._HDR_SZ,
                            self.TIME
                            )
                        )

    def prepare_set_time(self, time_us):
        self.buf  = bytearray (
                        self._TIME_SET.pack(
                            self._HDR_SZ + 8,
                            self.TIME_SET,
                            time_us
                            )
                        )

    def read(self, serial):
        '''Reads one entire TeensyPackage from the serial device.'''
        tbuf = bytearray()
        while not tbuf: 
            tbuf += bytearray(serial.read())
        totsize = tbuf[0]
        while len(tbuf) != totsize:
            tbuf += serial.read(totsize - len(tbuf))
        self.buf = tbuf

    def write(self, serial):
        '''Writes the contents of the buffer to the serial device.'''
        serial.write(self.buf)

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

    LOW  = 0 
    HIGH = 1

    def __init__(self, time, line, logiclevel):
        super(TeensyLineEvent, self).__init__(time)
        self.line = line
        self.logiclevel = self.HIGH if logiclevel else self.LOW

    def __str__(self):
        return "{}\t{}\t{}".format(self.timestamp, self.line, self.logiclevel)

class TeensyError(Exception):
    
    NO_ERROR            = 0
    NOT_A_TEENSY        = 1
    NOT_CONNECTED       = 2
    UNABLE_TO_CONNECT   = 3
    INVALID_TRIGGER_LINE= 4
    TEENSY_ERROR        = 5

    _errdict = {
        NOT_A_TEENSY        : "Connected to something that is not a Teensy",
        NOT_CONNECTED       : "Operation requires a valid connection",
        UNABLE_TO_CONNECT   : "Unable to connect",
        INVALID_TRIGGER_LINE: "Invalid trigger line",
        TEENSY_ERROR        : "Unspecified Teensy error."
    }

    def __init__(self, error, extra=None):
        self.int_error  = error
        self.extra      = extra
        super(TeensyError, self).__init__()

    def __str__(self):
        if self.extra:
            return "TeensyError: {}, Extra info: {}".format(
                self._errdict(self.int_error), self.extra
                )
        else:
            return "TeensyError: {}".format(self._errdict[self.error])


class _TeensyTask(object):
    ''' Is used to communicate between the teensy client and the Teensy
    internal thread.
    '''
    def __init__(self, task, *args, **kwargs):
        self.task   = task
        self.args   = args
        self.kwargs = kwargs

    def has_payload(self):
            return len(self.args) or len(self.kwargs)

    def task(self):
        return self.task

    def args(self):
        return self.args

    def kwargs(self):
        return self.kwargs
        

class Teensy(object):
    '''Class that communicates with a teensy device.
    
    A device is opened on connection and subsequently a thread is started.
    '''
    
    READ_TIMEOUT = 0.0001

    def __init__(self, devfn="/dev/ttyACM0"):
        ''' Opens communication with serial device.
        devfn is a path to the device name or something like COM5 on windows.
        '''
        super(Teensy, self).__init__()
        self.connected = False
        self._quit     = None   # Becomes an event to stop the thread.
        self._thread   = None   # Becomes the thread on connection  
        self._tqueue   = None   # Becomes Task queue on connection
        self._aqueue   = None   # Becomes Answer queue on connection
        self.events    = None   # Becomes queue for events on connection

        if devfn:
            self.connect(devfn)
        else:
            self._serial   = None

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
        if self.connected:
            self.close()
        try:
            self._serial    = s.Serial(devfn, timeout=Teensy.READ_TIMEOUT)
        except s.SerialException as e:
            # Raise SerialException as a TeensyError()
            raise TeensyError(
                    TeensyError.UNABLE_TO_CONNECT,
                    str(e)
                    )
        # empty queues to be sure.
        self._tqueue    = q.Queue()
        self._aqueue    = q.Queue()
        self.events     = q.Queue()

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
        tasks   = self._tqueue
        reply   = self._aqueue

        try:
            self._identify()

            #sync with client
            reply.put(TeensyError.NO_ERROR)

            while not self._quit.is_set():
                try:
                    task    = tasks.get(True, timeout)
                    answer  = self._handleTask(task)
                    reply.put(answer)
                except q.Empty:
                    if self._serial.in_waiting:
                        self._fetch_event()
        except Exception as e:
            # Abort from thread when an exception occurs.
            import sys, traceback
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

    def _fetch_event(self):
        '''Try to read one event from the serial device.'''
        package = _TeensyPackage()
        package.read(self._serial)
        assert package.pkgtype() == _TeensyPackage.EVENT_TRIGGER
        size, type_, line, timestamp, logic = package.parse_packet()
        event = TeensyLineEvent(timestamp, line, logic)
        self.handle_event(event)

    
    def _identify(self):
        '''Does a handshake with the teensy'''
        package = _TeensyPackage()
        package.prepare_identify(ZEP_ZEP_TO_TEENSY_UUID)
        package.write(self._serial)
        package.read(self._serial)
        sz, t, uuid = package.parse_packet()
        if t != _TeensyPackage.IDENTIFY:
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
        package.write(self._serial)
        package.read(self._serial)
        psize, reply = package.parse_packet()
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
        package.write(self._serial)
        package.read(self._serial)
        psize, reply, payload = package.parse()
        if   reply == _TeensyPackage.ACKNOWLEDGE_SUCCES:
            return TeensyError.NO_ERROR
        elif reply == _TeensyPackage.ACKNOWLEDGE_LINE_INVALID:
            return TeensyError.INVALID_TRIGGER_LINE
        else:
            return TeensyError.TEENSY_ERROR

    def deregister_input(self, line):
        ''' Deregister a previously registerd (single_shot) line.
        '''
        if not self.connected:
            raise TeensyError(TeensyError.NOT_CONNECTED)
        task = TeensyTask(_TeensyPackage.DEREGISTER_INPUT, line)
        self._tqueue.put(task)
        reply = self._aqueue.get()
        if reply:
            raise TeensyError(reply)
    
    def _deregister_input(self, line):
        package = _TeensyPackage()
        package.prepare_deregister(line)
        package.write(self._serial)
        package.read(self._serial)
        psize, reply = package.parse_packet()
        assert reply == _TeensyPackage.ACKNOWLEDGE_SUCCES
        return TeensyError.NO_ERROR

    def time(self):
        '''Obtain a timestamp from the Teensy.
        '''
        if not self.connected:
            raise TeensyError(TeensyError.NOT_CONNECTED)
        task = _TeensyTask(_TeensyPackage.TIME)
        self._tqueue.put(task)
        reply = self._aqueue.get()
        if reply:
            raise TeensyError(reply)

    def _time(self):
        package = _TeensyPackage()
        package.prepare_time()
        package.write(self._serial)
        package.read(self._serial)
        msgsize, reply, time = package.parse_packet()
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
        
    def _handleTask(self, task):
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



def test():
    print ("serial version = {}".format(s.VERSION))
    for i in list_devices():
        print(i)
    with Teensy("/dev/ttyACM0") as teensy:
        pass

if __name__ == "__main__":
    test()
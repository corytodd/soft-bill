#!/usr/bin/env python
"""
Soft Bill is a virtual, RS-232 bill validator
author: me@corytodd.us


TODO: Implement master timeout (no poll, we must disable ourselves)
TODO: Bill enable/disable register
TODO: More useful cheat mocking
TODO: Check ACK number, resend last message if required

"""

from threading import Thread, Lock
import serial, time, sys
from Queue import Queue


MUTEX = Lock()


### Globals ###
# Not realistic, just a feel good value
POWER_UP = 0.4
# Time between states
TRANSITION = 0.9


def serial_runner(portname, acceptor):
    """
    Transmits state of an Acceptor over a serial port with the global poll rate

    Args:
        portname -- string portname to open

    Returns:
        None
    """

    ser = serial.Serial(
        port=portname,
        baudrate=9600,
        bytesize=serial.SEVENBITS,
        parity=serial.PARITY_EVEN,
        stopbits=serial.STOPBITS_ONE
    )
    
    try:

        while ser.isOpen() and acceptor.running:

            # Wait for data
            serial_in = ''
            while ser.inWaiting() > 0:
                serial_in += ser.read(1)
            if serial_in == '':
                continue

            MUTEX.acquire()

            msg = acceptor.get_message()

            # Set the ACK
            msg[2] |= (ord(serial_in[2]) & 1)

            acceptor.accept_or_return(serial_in)

            # Set the checksum
            msg[10] = msg[1] ^ msg[2]
            for byte in xrange(3, 5):
                msg[10] ^= msg[byte]


            # Send message to master
            ser.write(msg)
            MUTEX.release()

            # Slow down a bit, our virutal environment is too fast
            time.sleep(0.2)

    except serial.SerialException:
        print 'Terminating serial thread'

    ser.close()
    return

class Acceptor(object):
    """
    Describes the current state and events associated with this BA

    Note:
        There will only be one state at a time
        Multiple events may be set

    Args:
        None

    """

    def __init__(self):
        # Set to False to kill
        self.running = True
        # Say LRC is present for now
        self.lrc_ok = True

        # data byte 0
        self._state = 0x01
        # data byte 1
        self._event = 0x10
        # byte 2 - lower 3 bits
        self._ext = 0x01
        # byte 2 Upper 5 bits
        self._value = 0x00
        # byte 3 is reserverd
        self._resd = 0x00
        # byte 4 is model (00-7FH)
        self._model = 0x01
        # byte 5 is software revision (00-7FH)
        self._rev = 0x01

        # Some states are only sent once, handle them in a queue
        self._b0_ephemeral = Queue()
        self._b1_ephemeral = Queue()
        self._b2_ephemeral = Queue()

        # Used to recall in case of NAK
        self._last_msg = None

        # Simulate power up
        power_up = Thread(target=self._power_up)
        power_up.start()


    def _power_up(self):
        """
        Simulate BA power up
        """
        time.sleep(POWER_UP)
        self._ext &= ~(0x01)


    def _start_accepting(self, val):
        """
        Blocks the calling thread as this simulates bill movement from idle to
            escrow.

        Params:
            val -- integer index of note (0-7)

        Returns:
            None
        """
        # Accepting
        self._state = 0x02
        time.sleep(TRANSITION)

        # Escrow
        MUTEX.acquire()
        self._state = 0x04
        self._value = val
        MUTEX.release()


    def _accept_bill(self):
        """
        Simulate the movement of the bill from escrow to stacked

        Params:
            None

        Returns:
            None
        """
        # Stacking
        self._state = 0x08
        time.sleep(TRANSITION)
        # Stacked + Idle
        self._b0_ephemeral.put(0x10)
        self._state = 0x01


    def _return_bill(self):
        """
        Simulate the movement of the bill from escrow to returned

        Params:
            None

        Returns:
            None
        """
        # Returning
        self._state = 0x20
        time.sleep(TRANSITION)
        # Returned + Idle
        self._b0_ephemeral.put(0x50)
        self._state = 0x01


    def accept_or_return(self, master):
        """
        Process stack or return request from master

        Params:
            None

        Returns:
            None
        """
        # If we're in escrow and master says stack
        if ((ord(master[4]) & 0x20)) and (self._state == 0x04):
            self._accept_bill()
        # If we're in escrow and master says return
        elif ((ord(master[4]) & 0x40)) and (self._state == 0x04):
            self._return_bill()


    def get_message(self):
        """
        Returns current message as byte array

        Returns:
            byte array
        """
        self.check_lrc()

        state = self._state
        event = self._event
        ext = self._ext
        
        # Pull all ephemerals from queue
        if not self._b0_ephemeral.empty():
            state |= self._b0_ephemeral.get_nowait()
        if not self._b1_ephemeral.empty():
            event |= self._b1_ephemeral.get_nowait()
        if not self._b2_ephemeral.empty():
            ext |= self._b2_ephemeral.get_nowait()


        msg = bytearray([0x02, 0x0B, 0x20, state, event,
                         (ext | (self._value << 3)), self._resd, self._model,
                         self._rev, 0x03, 0x3A])

        self._last_msg = msg
        return msg


    def check_lrc(self):
        """
        Checks the state of the LRC and set event if required

        Params:
            None

        Returns:
            None
        """
        if self.lrc_ok:
            self._event |= 0x10
        else:
            self._event &= ~(0x10)


    def parse_cmd(self, cmd):
        """
        Applies the given command to modify the state/event of
        this acceptor

        Args:
            cmd -- string arg

        Returns:
            Int -- 0 if okay, 1 to exit, 2 to quit
        """
        if cmd is 'Q':
            return 1
        if cmd is '?' or cmd is 'H':
            return 2

        MUTEX.acquire()

        if cmd.isdigit():
            val = int(cmd, 10)            
            if val > 0 and val <= 7:
                # Are we idle?
                if self._state & 0x01 == 1:
                    feed = Thread(target=self._start_accepting, args=(val,))
                    feed.start()
                else:         
                    # Hols the phone, revoke anything in the state queue
                    # Set back to idle because we just had a double-insertion
                    self._b0_ephemeral = Queue()                           
                    self._state = 0x01
                    self._b1_ephemeral.put(0x02)  
            else:
                print "Invalid Bill Number {:s}".format(cmd)

        elif cmd is 'C':
            # Put Cheated
            self._b1_ephemeral.put(0x01)
        elif cmd is 'R':
            # Put Rejected
            self._b1_ephemeral.put(0x02)
        elif cmd is 'J':
            # Toggle Jammed
            self._event = self._event ^ 0x04
        elif cmd is 'F':
            # Toggle Stacker Full:
            self._event = self._event ^ 0x08
        elif cmd is 'P':
            # Toggle Cashbox Present
            self.lrc_ok = not self.lrc_ok
        elif cmd is 'W':
            # Toggle Powering Up
            self._ext = self._ext ^ 0x01
        elif cmd is 'I':
            # Put Invalid Command
            self._b2_ephemeral.put(0x02)
        elif cmd is 'X':
            # Put Unit Failure
            self._b2_ephemeral.put(0x04)
        else:
            print "Unknown Command: {:s}".format(cmd)


        MUTEX.release()
        return 0

### Main  Routine ###
def main(portname):
    """
    Application to simulate hardware bill validator

    Args:
        portname -- string portname e.g. COM2, /dev/tty.*
    """

    acceptor = Acceptor()

    cmd_table = '''

    H or ? to show Help
    Q or CTRL+C to Quit

    Bill position to simulate bill insertions:
    1 - $1   or 1st note
    2 - $2   or 2nd note
    3 - $5   or 3rd note
    4 - $10  or 4th note
    5 - $20  or 5th note
    6 - $50  or 6th note
    7 - $100 or 7th note

    Note:
    Software automatically changes states once mock bill insertion begins
    Idling->Accepting->Escrowed->{Stacking,Returning}->{Stacked,Returned}

    Toggle Events:
    C - Cheated
    R - Rejected (We think note is invalid)
    J - Jammed
    F - Stacker Full
    P - LRC present (cashbox: set to 1 means it's there)

    Extra Stuff:
    W - Powering up
    I - Invalid Command was received
    X - Failure (This BA has failed)
    '''


    print "Starting software BA on port {:s}".format(portname)

    serial_thread = Thread(target=serial_runner, args=(portname, acceptor))
    # Per note https://docs.python.org/2/library/threading.html#thread-objects
    # 16.2.1 Note: Daemon threads are abruptly stopped, set to false for proper
    # release of resources (i.e. our comm port)
    serial_thread.daemon = False
    serial_thread.start()

    # Loop until we are to exit
    try:
        print cmd_table
        while acceptor.running:

            cmd = raw_input()
            result = acceptor.parse_cmd(cmd)
            if result is 0:
                pass
            elif result is 1:
                acceptor.running = False
            elif result is 2:
                print cmd_table

    except KeyboardInterrupt:
        acceptor.running = False

    print '\n\nGoodbye!'
    serial_thread.join()
    print 'Port {:s} closed'.format(portname)

if __name__ == "__main__":
    main(sys.argv[1])

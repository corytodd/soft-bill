# -*- coding: utf-8 -*-
"""
Created on Sun Feb 01 09:14:47 2015

@author: me@corytodd.us
"""
from threading import Thread, Lock
from Queue import Queue
import time, serial

### Globals ###
# Not realistic, just a feel good value
POWER_UP = 0.4
# Time between states
TRANSITION = 0.9
CASHBOX_SIZE = 250


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
        
        # Accept all note as default
        self._enables = 0x07
        # Say LRC is present for now
        self._lrc_ok = True
        # Acceptor has it's own lock
        self._mutex = Lock()
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
        
        self._note_count = 0

        # Some states are only sent once, handle them in a queue
        self._b0_ephemeral = Queue()
        self._b1_ephemeral = Queue()
        self._b2_ephemeral = Queue()

        # Background worker thread
        self._serial_thread = None

        # Used to recall in case of NAK
        self._last_msg = None

        # Simulate power up
        power_up = Thread(target=self._power_up)
        power_up.start()


    def enable_note(self, index):
        """
        Set note enable bit so Acceptor accepts note
        
        Args:
            index -- integer index (1-7) of note to enable
        """        
        if index is not int:
            index = int(index)
        if index > 0 and index <= 7:
            self._enables |= index
            print "Enabled note {:d}".format(index)
        else:
            print "Invalid enable {:d}".format(index)
            
    def disable_note(self, index):
        """
        Clear note enable bit so Acceptor rejects note
        
        Args:
            index -- integer index (1-7) of note to disable
        """        
        if index is not int:
            index = int(index)
        if index > 0 and index <= 7:
            self._enables &= (~(index) & 0x07)
            print "Disabled note {:d}".format(index)
        else:
            print "Invalid disable {:d}".format(index)            


    def start(self, portname):
        """
        Start Acceptor in a non-daemon thread

        Args:
            portname -- string name of the port to open and listen on

        Returns:
            None

        """
        self._serial_thread = Thread(target=self._serial_runner, args=(portname,))
        # Per https://docs.python.org/2/library/threading.html#thread-objects
        # 16.2.1: Daemon threads are abruptly stopped, set to false for proper
        # release of resources (i.e. our comm port)
        self._serial_thread.daemon = False
        self._serial_thread.start()


    def stop(self):
        """
        Blocks until Acceptor can safely be stopped

        Args:
            None

        Returns:
            None
        """
        self.running = False
        self._serial_thread.join()


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

        self._mutex.acquire()

        # Handle bill feed command
        if cmd.isdigit():
            val = int(cmd, 10)
            # Is this bill enabled? Implicitly guarantees 0 < val <= 7
            if val & self._enables:
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
                if val is 0 or val > 7:
                    print "Invalid Bill Number {:s}".format(cmd)
                else:
                    print "Note is disabled"
                    # Send reject message
                    self._b1_ephemeral.put(0x02)
    
        # Handle bill enable/disable command
        elif len(cmd) is 2:
            if cmd[0] is 'D':
                self.disable_note(cmd[1])                    
            elif cmd[0] is 'E':
                self.enable_note(cmd[1])      
            else:
                print "Unkown E/D command {:s}".format(cmd)                
            
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
            self._lrc_ok = not self._lrc_ok
        elif cmd is 'W':
            # Toggle Powering Up
            self._ext = self._ext ^ 0x01
        elif cmd is 'I':
            # Put Invalid Command
            self._b2_ephemeral.put(0x02)
        elif cmd is 'X':
            # Put Unit Failure
            self._b2_ephemeral.put(0x04)
        elif cmd is 'Y':
            # Set note count back to zero
            self._note_count = 0
        else:
            print "Unknown Command: {:s}".format(cmd)


        self._mutex.release()
        return 0


    def _serial_runner(self, portname):
        """
        Transmits state of Acceptor over serial port using global poll rate

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

            while ser.isOpen() and self.running:

                # Wait for data
                serial_in = ''
                while ser.inWaiting() > 0:
                    serial_in += ser.read(1)
                if serial_in == '':
                    continue

                self._mutex.acquire()

                msg = self._get_message()

                # Set the ACK
                msg[2] |= (ord(serial_in[2]) & 1)

                self._accept_or_return(serial_in)

                # Set the checksum
                msg[10] = msg[1] ^ msg[2]
                for byte in xrange(3, 5):
                    msg[10] ^= msg[byte]


                # Send message to master
                ser.write(msg)
                self._mutex.release()

                # Slow down a bit, our virutal environment is too fast
                time.sleep(0.2)

        except serial.SerialException:
            print 'Terminating serial thread'

        ser.close()
        return


    def _accept_or_return(self, master):
        """
        Process stack or return request from master

        Args:
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


    def _get_message(self):
        """
        Returns current message as byte array

        Args:
            None

        Returns:
            byte array
        """
        self._check_lrc()

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


    def _check_lrc(self):
        """
        Checks the state of the LRC and set event if required

        Args:
            None

        Returns:
            None
        """
        if self._lrc_ok:
            self._event |= 0x10
        else:
            self._event &= ~(0x10)
            
        # Set stacker full if we have enough notes
        if self._note_count >= CASHBOX_SIZE:
            self._event |= 0x08            


    def _power_up(self):
        """
        Simulate BA power up - Block for POWER_UP milliseconds

        Args:
            None

        Returns:
            None
        """
        time.sleep(POWER_UP)
        self._ext &= ~(0x01)


    def _start_accepting(self, val):
        """
        Blocks the calling thread as this simulates bill movement from idle to
            escrow.

        Args:
            val -- integer index of note (0-7)

        Returns:
            None
        """
        # If stacker is full, set the stacker full flag and reject note
        if self._note_count >= CASHBOX_SIZE:
            self._event |= 0x08
            self._b1_ephemeral.put(0x02)
        else:
            # Accepting
            self._state = 0x02
            time.sleep(TRANSITION)
    
            # Escrow - Crtical that both of these bits are set!
            self._mutex.acquire()
            self._state = 0x04
            self._value = val
            self._mutex.release()


    def _accept_bill(self):
        """
        Simulate the movement of the bill from escrow to stacked

        Args:
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
        self._note_count = self._note_count + 1


    def _return_bill(self):
        """
        Simulate the movement of the bill from escrow to returned

        Args:
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

#!/usr/bin/env python

from threading import Thread, Lock
import serial, time, sys


mutex = Lock()


### Globals ###
# Not realistic, just a feel good value
POWER_UP = 0.4
# Time between states
TRANSITION = 0.9

# Background thread to handle serial comms
def serial_runner(portname, ba):
    """
    Transmits the state of an Acceptor over a serial port with the global poll rate
    
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
    
        while ser.isOpen() and ba.running:
                  
            msg = ba.get_message()
        
            # Wait for data
            serial_in = ''
            while ser.inWaiting() > 0:
                serial_in += ser.read(1)
            if (serial_in == ''): continue    
            
            mutex.acquire()            
            
            # Set the ACK
            msg[2] |= (ord(serial_in[2]) & 1)      
        
            
            # If we're in escrow and master says stack
            if ((ord(serial_in[4]) & 0x20)) and (ba.state == 0x04):
                ba.accept_bill()
            # If we're in escrow and master says return                
            elif ((ord(serial_in[4]) & 0x40)) and (ba.state == 0x04):
                ba.return_bill()
                
            # Set the checksum
            msg[10] = msg[1] ^ msg[2]
            for b in xrange(3,5):
                msg[10] ^= msg[b]
                
        
            # Send message to master
            ser.write(msg)
            time.sleep(0.2)                
                
            # Clear any events since we just sent message
            ba.clear_events()        
            ba.clear_ephemeral_state()
            mutex.release()
                       
    except serial.SerialException:
        print 'Terminating serial thread'
        pass
    
    ser.close()
    return        
    
class Acceptor:
    """
    Describes the current state and events associated with this BA
    
    Note:
        There will only be one state at a time
        Multiple events may be set
        
    Args:
        None

    """    
    
    def __init__(self):
        # data byte 0
        self.state = 0x01
        # data byte 1
        self.event = 0x10
        # note: this is the lower 3 bits of byte 2
        self.ext = 0x01
        # note: this is the upper 5 bits of byte 2
        self.value = 0x00
        # byte 3 is reserverd
        self.resd = 0x00
        # byte 4 is model (00-7FH)
        self.model = 0x01
        # byte 5 is software revision
        self.rev = 0x01
        # Set to False to kill
        self.running = True
        self.lrc_ok = True
        
        self.ephemeral = False
                
    def getByte2(self):
        """
        Returns the value of byte 2 wich contains 3 possible states
        along with any bill value
        
        Returns:
            int -- Logical OR of ext and value
        """
        return self.ext | (self.value << 3)
                    
                    
    def get_message(self):
        """
        Returns current message as byte array
        
        Returns:
            byte array
        """        
        
        #               start,  len,  ack,
        msg = bytearray([0x02, 0x0B, 0x20,             
        #               state   ,       event,
                        self.state,     self.event, 
        #               data         ,  reserved  ,                           
                        self.getByte2(),  self.resd, 
        #               model   ,       revision               
                        self.model,       self.rev, 
        #               ETX ,           Checksum   ,                         
                        0x03,           0x3A
                        ])
        return msg
                            
        
    def powered_up(self):
        """
        Clears the powering up flag in byte 2 of data
        """
        self.ext &= ~(0x01)
        
        
    def toggle(self, val, mask):
        """
        Sets or clears the the bit of val at the given mask
        """
        return val ^ mask
        
    def start_accepting(self, val):
        """
        Blocks the calling thread as this simulates bill movement from idle to
            escrow.
        
        Params:
            val -- integer index of note (0-7)
            
        Returns:
            None
        """
        # Accepting
        self.state = 0x02
        time.sleep(TRANSITION)
        
        # Escrow
        # Technically we should block the serial thread until BOTH
        # of these bytes are set... but let's see if we actually do see a race
        # condition. I doubt we will
        self.state = 0x04
        self.value = val
        
    def accept_bill(self):
        """
        Simulate the movement of the bill from escrow to stacked
        
        Params:
            None
            
        Returns:
            None
        """
        # Stacking
        self.state = 0x08
        time.sleep(TRANSITION)
        # Stacked + Idle
        self.state = 0x11
        # Set the ephemeral flag so we clear this once sent
        self.ephemeral = True
        
    def return_bill(self):
        """
        Simulate the movement of the bill from escrow to returned
        
        Params:
            None
            
        Returns:
            None
        """
        # Returning
        self.state = 0x20
        time.sleep(TRANSITION)
        # Returned + Idle
        self.state = 0x41
        # Set the ephemeral flag so we clear this once sent        
        self.ephemeral = True
        
    def clear_events(self):
        """
        Clears all events from BA
        
        Params:
            None
        
        Returns:
            None
        """
        self.check_lrc()
        
    def clear_ephemeral_state(self):
        """
        Clear any states that should only be sent one time
        
        Params:
            None
            
        Returns:
            None
        """
        if self.ephemeral:
            self.state = 0x01     
            self.ephemeral = False
        
    def check_lrc(self):
        """
        Checks the state of the LRC and set event if required
        
        Params:
            None
        
        Returns:
            None
        """
        if self.lrc_ok:
            self.event = 0x10
        else:
            self.event = 0x00
        
        
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


        if cmd.isdigit():
            val = int(cmd, 10)
            if val >= 0 and val <= 7:
                self.start_accepting(val)
            else:
                print "Invalid Bill Command"
                
            return 0

        mutex.acquire()            
        
        if cmd is 'C':
            # Toggle Cheated
            self.event = self.toggle(self.event, 0x01)
        elif cmd is 'R':
            # Toggle Rejected
            self.event = self.toggle(self.event, 0x02)
        elif cmd is 'J':
            # Toggle Jammed
            self.event = self.toggle(self.event, 0x04)
        elif cmd is 'F':
            # Toggle Stacker Full:
            self.event = self.toggle(self.event, 0x08)
        elif cmd is 'P':
            # Toggle Cashbox Present
            self.lrc_ok = not self.lrc_ok
        elif cmd is 'W':
            # Toggle Powering Up
            self.ext = self.toggle(self.ext, 0x01)
        elif cmd is 'I':
            # Toggle Invalid Command
            self.ext = self.toggle(self.ext, 0x02)
        elif cmd is 'X':
            # Toggle Unit Failure
            self.ext = self.toggle(self.ext, 0x04)
        else:
            print "Unknown Command: {:s}".format(cmd)            
            
            
        mutex.release()
        return 0        
    
### Main  Routine ###   
def main(portname):
    """
    Application to simulate hardware bill validator
    
    Args:
        portname -- string portname e.g. COM2, /dev/tty.*
    """    
    
    ba = Acceptor()
    
    cmd_table = '''
    
    ? or H to show this table at any time
    ctrl+c or Q to quit    
    
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
    
    t = Thread(target=serial_runner, args=(portname, ba))    
    # Per note https://docs.python.org/2/library/threading.html#thread-objects
    # 16.2.1 Note: Daemon threads are abruptly stopped, set to false for proper
    # release of resources (i.e. our comm port)
    t.daemon = False
    t.start()
    
    # Simulate powerup time, clear the powering up flag
    time.sleep(POWER_UP)
    ba.powered_up()
    
    # Loop until we are to exit
    try:
        print cmd_table
        while ba.running:
            
            cmd = raw_input()
            result = ba.parse_cmd(cmd)
            if result is 0:
                pass
            elif result is 1:
                ba.running = False
            elif result is 2:
                print cmd_table
            
    except KeyboardInterrupt:
        print '\n\nGoodbye!'
        ba.running = False
        pass
    
    
        
    t.join()        
    print 'Port {:s} closed'.format(portname)
    
if __name__ == "__main__":
    main(sys.argv[1])
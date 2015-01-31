#!/usr/bin/env python


import sys, threading
import serial, time

### Globals ###
# Change this value to modify polling rate. Currently 100 ms
PollRate = 0.1
# Just realistic, just a feel good value
PowerUp = 0.4

# Set to false to kill background serial thread
RUNNING = True


# Background thread to handle serial comms
def serial_runner(portname, ba):
    """
    Transmits the state of an Acceptor over a serial port with the global poll rate
    
    Args:
        portname -- string portname to open
        
    Returns:
        None
    """
    
    # Get access to our globals
    global RUNNING
 
    ser = serial.Serial(
        port=portname,
        baudrate=9600,
        bytesize=serial.SEVENBITS,
        parity=serial.PARITY_EVEN,
        stopbits=serial.STOPBITS_ONE
    )
    try:
    
        while ser.isOpen() and RUNNING:
                  
            msg = ba.get_message()
        
            # Wait for data
            serial_in = ''
            while ser.inWaiting() > 0:
                serial_in += ser.read(1)
            if (serial_in == ''): continue
            
            # Set the ACK
            msg[2] |= (ord(serial_in[2]) & 1)      
    
            # Set the checksum
            msg[10] = msg[1] ^ msg[2]
            for b in xrange(3,5):
                msg[10] ^= msg[b]
        
            # Send message to master
            ser.write(msg)
            time.sleep(0.1)
                       
            time.sleep(PollRate)    
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
        self.val = 0x00
        # byte 3 is reserverd
        self.resd = 0x00
        # byte 4 is model (00-7FH)
        self.model = 0x01
        # byte 5 is software revision
        self.rev = 0x01
        
    def getByte2(self):
        """
        Returns the value of byte 2 wich contains 3 possible states
        along with any bill value
        
        Returns:
            int -- Logical OR of ext and val
        """
        return self.ext | self.val
                    
                    
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
        
    def parse_cmd(self, cmd):
        """
        Applies the given command to modify the state/event of 
        this acceptor
        
        Args:
            cmd -- string arg

        Returns:QQ?,
            Int -- 0 if okay, 1 to exit, 2 to quit
        """        
        if cmd is 'Q':
            return 1
        if cmd is '?' or cmd is 'H':
            return 2
            

        if cmd.isdigit():
            val = int(cmd, 10)
            if val >= 0 and val <= 7:
                self.val = val
            else:
                print "Invalid Bill Command"
                
        elif cmd is 'C':
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
            self.event = self.toggle(self.event, 0x10)
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
            
        return 0
    
    
### Main  Routine ###   
def main(portname):
    """
    Application to simulate hardware bill validator
    
    Args:
        portname -- string portname e.g. COM2, /dev/tty.*

    """    
    
    
    global RUNNING
    BA = Acceptor()
    
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
    
    Note: Software automatically changes states once mock bill insertion begins
         
    Idling->Accepting->Escrowed->{Stacking, Returning}->{Stacked, Returned}
    
    Toggle Events:\n
    
    C - Cheated
    R - Rejected (We think note is invalid)
    J - Jammed
    F - Stacker Full
    P - LRC present (cashbox: set to 1 means it's there)
    
    W - Powering up
    I - Invalid Command was received
    X - Failure (This BA has failed)
    '''
    
    
    print "Starting software BA on port {:s}".format(portname)
    
    t = threading.Thread(target=serial_runner, args=(portname, BA))    
    # Per note https://docs.python.org/2/library/threading.html#thread-objects
    # 16.2.1 Note: Daemon threads are abruptly stopped, set to false for proper
    # release of resources (i.e. our comm port)
    t.daemon = False
    t.start()
    
    # Simulate power uptime, clear the powering up flag
    time.sleep(PowerUp)
    BA.powered_up()
    
    # Loop until we are to exit
    try:
        print cmd_table
        while RUNNING:
            
            cmd = raw_input()
            result = BA.parse_cmd(cmd)
            if result is 0:
                pass
            elif result is 1:
                RUNNING = False
            elif result is 2:
                print cmd_table
            
    except KeyboardInterrupt:
        print '\n\nGoodbye!'
        RUNNING = False
        pass
    
    
        
    t.join()        
    print 'Port {:s} closed'.format(portname)
    
if __name__ == "__main__":
    main(sys.argv[1])
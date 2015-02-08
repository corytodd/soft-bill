#!/usr/bin/env python
"""
Soft Bill is a virtual, RS-232 bill validator
@auth@or: me@corytodd.us
@version: 0.5

"""
import acceptor, autopilot
import sys


### Main  Routine ###
def main(portname):
    """
    Application to simulate hardware bill validator

    Args:
        portname -- string portname e.g. COM2, /dev/tty.*
    """

    slave = acceptor.Acceptor()

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
    Y - Empty Cashbox
    A - AutoPilot
    
    Bill Disable and Enables: (Only effective in interrupt mode)
    Dx - where x is the index to disable (e.g. D1 disables $1)
    Ex - where x in the index to enable  (e.g. E1 enables $1)
    L  - MSB -> LSB enable/disable (1 enabled, 0 disabled)
    '''


    print "Starting software BA on port {:s}".format(portname)
    slave.start(portname)
    
    # Acquire a pilot
    pilot = autopilot.AutoPilot(slave)

    # Loop until we are to exit
    try:
        print cmd_table
        while slave.running:

            cmd = raw_input()
            result = slave.parse_cmd(cmd)
            if result is 0:
                pass
            elif result is 1:
                slave.stop()
            elif result is 2:
                print cmd_table      
            elif result is 3:
                if not pilot.running:
                    pilot.start()
                else:
                    pilot.stop()
                

    except KeyboardInterrupt:
        slave.running = False

    print '\n\nGoodbye!'
    print 'Port {:s} closed'.format(portname)

if __name__ == "__main__":
    main(sys.argv[1])

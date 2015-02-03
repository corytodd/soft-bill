# -*- coding: utf-8 -*-
"""
Created on Mon Feb 02 20:46:41 2015

@author: catix
"""
from threading import Thread
import time,random


class AutoPilot(object):
    """
    Worker to simulate user activity on an Acceptor
    """

    CommandPool = ["H", 1, 2, 3, 4, 5, 6, 7, "C", "R", "J", "F", "P", "W", 
                   "I", "X", "Y", "E", "D"]
    
    def __init__(self, target):
        self.acceptor = target
        self.running = False
        self.pilot = Thread(target=self._do)
        
        
    def start(self):
        """
        Start autonomous operation
        
        Args:
            None
            
        Returns:
            None
        """
        print "Starting AutoPilot..."
        self.running = True
        self.pilot.daemon = True
        self.pilot.start()
        
    def stop(self):
        """
        Stop autonomous operation (blocking)
        
        Args:
            None
            
        Returns:
            None
        """
        print "Shutting down AutoPilot..."
        self.running = False        
        self.pilot.join()
        
        
    def _do(self):
        """
        Main worker thread for autopilot
        
        Args:
            None
            
        Returns:
            None
        """
        
        while self.running:
            # Get random command index
            cmd = str(random.choice(AutoPilot.CommandPool))
            
            # The E and D require params
            if cmd is "E" or cmd is "D":
                cmd += str(random.randint(1,7))
            
            # Do the task
            print "AutoPilot: {:s}".format(cmd)
            self.acceptor.parse_cmd(cmd)
            
            # Wait a bit
            sleep = random.uniform(0.9, 3.4)
            time.sleep(sleep)

        print "AutoPilot Terminated!"            
                
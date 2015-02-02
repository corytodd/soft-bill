# -*- coding: utf-8 -*-
"""
Created on Sun Feb 01 21:14:41 2015

@author: me@corytodd.us
"""
from threading import Thread
import time

class Monitor(object):
    """
    Essentially a resetable stopwatch that acts like a timeout
    handler
    """

    def __init__(self, interval, dead_fn):
        self.interval = interval
        self.dead_fn = dead_fn
        self.worker_thread = Thread(target=self.do_monitor)
        self.expired = False

    def start(self):
        """
        Starts the monitor

        Args:
            None

        Returns:
            None
        """
        self.worker_thread.start()

    def stop(self):
        """
        Stops the monitor

        Args:
            None

        Returns:
            None
        """
        self.interval = 0.1
        self.dead_fn = self._nop
        self.worker_thread.join()


    def do_monitor(self):
        """
        Perform the actual monitoring

        Args:
            None

        Returns:
            None
        """
        while not self.expired:
            self.expired = True
            time.sleep(self.interval)
        self.dead_fn()

    def reset(self):
        """
        Reset the monitor

        Args:
            None

        Returns:
            None
        """
        self.expired = False


    def _nop(self):
        """
        Dummy function
        """
        pass
    
# Soft Bill

## A virtual RS-232 Bill Acceptor
Emulate an RS-232 bill acceptor in software.


This application can be used to test your RS-232 master such as found [here](https://github.com/PyramidTechnologies/Python-RS-232)

### Requirements

 - Python 2.7
 - Null modem emulation
 - General knowledge of RS-232 protocol for bill validators
   See [here] (http://developers.pyramidacceptors.com/coding/2014/08/26/RS-232-Diagram.html)for a good visual summary

### Getting Started

 - Setup a null modem emulator
 - Setup your RS-232 master (write your own, fork another, etc)
 - Play with the code!

### Windows

 1. Install com0com
 2. Start up each your master and slave and attach them to the appropriate port e.g.
    
```

python main.py COM7 

``` 

### Linux

 1. [socat](http://stackoverflow.com/questions/23867143/null-modem-emulator-com0com-for-linux)
 2. Start up each your master and slave and attach them to the appropriate port e.g.
    
```

./main.py /dev/tty3

``` 

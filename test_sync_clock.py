#!/usr/bin/env python3

import time
import pyteensy

def cclock():
    ''' returns time in integral us
    '''
    return round(time.time() * 1e6)

if __name__ == "__main__":
    print("syncing default teensy")
    with pyteensy.Teensy() as teensy:
        threshold = [10, 20, 30, 40, 50, 60, 70, 80, 90]
        synced = False
        for i in range(10):
            for t in threshold:
                time.sleep(0.1)
                try:
                    teensy.sync_clock(cclock, t)
                    synced = True
                    print ("synced with {}".format(t))
                except pyteensy.TeensyError as e:
                    print ("Unable to sync with {}".format(t))
                if synced:
                    break
            if synced:
                break

            threshold = [t*10 for t in threshold]

    print("syncing unix teensy")
    with pyteensy.UnixTeensy() as teensy:
        threshold = [10, 20, 30, 40, 50, 60, 70, 80, 90]
        synced = False
        for i in range(10):
            for t in threshold:
                time.sleep(0.1)
                try:
                    teensy.sync_clock(cclock, t)
                    print("synced with {}".format(t))
                    synced = True
                except pyteensy.TeensyError as e:
                    print ("Unable to sync with {}".format(t))
                if synced:
                    break
            if synced:
                break
            threshold = [t*10 for t in threshold]



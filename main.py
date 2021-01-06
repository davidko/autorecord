#!/usr/bin/env python3

"""
Based off of a sample program from https://python-sounddevice.readthedocs.io/en/0.4.1/examples.html#recording-with-arbitrary-duration
"""

"""

The soundfile module (https://PySoundFile.readthedocs.io/) has to be installed!

"""
import argparse
import tempfile
import queue
import sys

import sounddevice as sd
import soundfile as sf
import numpy  # Make sure NumPy is loaded before it is used in the callback
assert numpy  # avoid "imported but unused" message (W0611)

import collections # for deque
import time
import traceback
import datetime
import threading

def int_or_str(text):
    """Helper function for argument parsing."""
    try:
        return int(text)
    except ValueError:
        return text


parser = argparse.ArgumentParser(add_help=False)
parser.add_argument(
    '-l', '--list-devices', action='store_true',
    help='show list of audio devices and exit')
args, remaining = parser.parse_known_args()
if args.list_devices:
    print(sd.query_devices())
    parser.exit(0)
parser = argparse.ArgumentParser(
    description=__doc__,
    formatter_class=argparse.RawDescriptionHelpFormatter,
    parents=[parser])
parser.add_argument(
    '-d', '--device', type=int_or_str,
    help='input device (numeric ID or substring)')
parser.add_argument(
    '-r', '--samplerate', type=int, help='sampling rate')
parser.add_argument(
    '-c', '--channels', type=int, default=1, help='number of input channels')
parser.add_argument(
    '-t', '--subtype', type=str, help='sound file subtype (e.g. "PCM_24")')
args = parser.parse_args(remaining)

q = queue.Queue()
prebuf = collections.deque(maxlen=50)

ENERGY_THRESH = 1.0

# States
IDLE = 0
RECORDING = 1

state = IDLE
count = 0
COUNT_THRESH = 10

file = None
file_lock = threading.Lock()

def callback(indata, frames, time, status):
    global ENERGY_THRESH
    global IDLE
    global RECORDING
    global state
    global count
    global COUNT_THRESH
    global file
    global file_lock
    global q

    """This is called (from a separate thread) for each audio block."""
    if status:
        print(status, file=sys.stderr)
        return

    # Add the sample to our prebuf deque
    prebuf.append(indata.copy())

    # Calculate the wave energy
    energy = (numpy.sum(indata**2))

    if state is IDLE:
        if energy > ENERGY_THRESH:
            if count > COUNT_THRESH:
                # Begin recording
                # Prepend the prebuf
                for block in prebuf:
                    q.put(block)
                
                # Append the current block
                q.put(indata.copy())

                # Open the file and update our state
                timestamp = datetime.datetime.today()
                filename = str(timestamp)
                file_lock.acquire()
                file = sf.SoundFile(
                    filename+'.wav', 
                    mode='x', 
                    samplerate=args.samplerate, 
                    channels=args.channels, 
                    subtype=args.subtype)
                state = RECORDING
                count = 0
                file_lock.release()
            else:
                count += 1
        else: # energy < ENERGY_THRESH
            count = 0
    elif state is RECORDING:
        q.put(indata.copy())
        if energy < ENERGY_THRESH:
            if count > COUNT_THRESH:
                # We are done recording this block. Close the file
                print('Done recording file!')
                file_lock.acquire()
                file.close()
                file = None
                count = 0
                state = IDLE
                file_lock.release()
            else:
                count += 1
        else:
            count = 0

try:
    if args.samplerate is None:
        device_info = sd.query_devices(args.device, 'input')
        # soundfile expects an int, sounddevice provides a float:
        args.samplerate = int(device_info['default_samplerate'])
        print('Sample rate: ' + str(args.samplerate))

    # Begin listening
    with sd.InputStream(samplerate=args.samplerate, device=args.device,
                        channels=args.channels, callback=callback):
        print('#' * 80)
        print('press Ctrl+C to stop the recording')
        print('#' * 80)
        while True:
            block = q.get()
            file_lock.acquire()
            if file:
                file.write(block)
            file_lock.release()

except KeyboardInterrupt:
    print('\nRecording finished')
    parser.exit(0)
except Exception as e:
    traceback.print_exc()
    parser.exit(type(e).__name__ + ': ' + str(e))

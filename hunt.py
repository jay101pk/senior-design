import threading
import time
import RPi.GPIO as GPIO
import serial
import discovery
import math

# NOTE: SEND = 1, LISTEN = 0

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(18, GPIO.OUT, initial=GPIO.LOW)
GPIO.output(18, GPIO.HIGH)

ser = serial.Serial(
    port='/dev/ttyS0',
    baudrate = 115200,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    bytesize=serial.EIGHTBITS,
    timeout=0
)

# convert text to bits
def text_to_bits(text, encoding='utf-8', errors='surrogatepass'):
    bits = bin(int.from_bytes(text.encode(encoding, errors), 'big'))
    return bits.zfill(8 * ((len(bits) + 7) // 8))

# convert bits to text
def text_from_bits(bits, encoding='utf-8', errors='surrogatepass'):
    n = int(bits, 2)
    return n.to_bytes((n.bit_length() + 7) // 8, 'big').decode(encoding, errors) or '\0'

def getBits(str):
    return ''.join(format(ord(x), 'b') for x in str)

# increment string's bits
def incBits(bits):
    x = int(bits, 2) + int('0001', 2)
    return '{:04b}'.format(x)

# listens for a syn
def listenForSyn(op_time, id):
    global aligned
    # time when we will stop listening for syn
    end_time = op_time + time.time()
    # if we read garbage and there is time left
    # keep listening for syn
    while time.time() < end_time:
        # set the read timeout
        ser.timeout = end_time - time.time()
        # reset the input buffer
        ser.reset_input_buffer()
        # read the received data
        x = ser.read(len(id))
        try:
            # decode data
            print('received: {} in listenForSyn'.format(x))
            data = x.decode()
            # if we got the expected syn (?)
            if len(data) == len(id):
                # write the our id and syn+1 to other node
                str = ('{},{}'.format(id, incBits(data))).encode()
                ser.write(str)
                print('sent: {} in listenForSyn'.format(str))
                aligned = True
                disc.setAligned()
                print('Aligned!')
                return
        except:
            pass

# listen for an ack response
def listenForAck(beacon_time, id):
    # set to true if we get an ACK
    global aligned
    # we need this to prevent us from exiting early
    end_time = time.time() + beacon_time
    while time.time() < end_time:
        # initially the read time will be the beacon_time
        # if we get garbage, the read time will be the
        # difference of the end time and the current time
        ser.timeout = end_time - time.time()
        # reset the input buffer
        ser.reset_input_buffer()
        # read in the received values
        x = ser.read((len(id)*2)+1)
        try:
            # decode data
            print('received: {} in listenForAck'.format(x))
            data = x.decode()
            # convert string to array
            data = data.split(',')
            # check to make sure the data is the correct length
            if len(data) == 2:
                # ensure we got the correct response
                if data[1] == incBits(id):
                    aligned = True
                    disc.setAligned()
                    print('Aligned!')
                    return
        except:
            pass

# send syn
def sendSyn(beacon_time, id):
    end_time = beacon_time + time.time()
    # clear output buffer
    ser.reset_output_buffer()
    str = ("{}".format(id)).encode()
    ser.write(str)
    print('sent: {} in sendSyn'.format(str))
    # don't start listening for ack until you've waited beacon_time seconds
    # not sure if we need this (?)
    
    '''
    if time.time() < end_time:
        sleep_time = end_time - time.time()
        time.sleep(sleep_time)
    '''

# 2-way handshake
def handshake(disc, id):
    aligned = False
    i = 0
    # get time constraints
    beacon_time = disc.getBeaconTime()
    # when the operation time ends
    op_time = disc.getPseudoSlotTime()
    # set write timeout since this is constant
    ser.write_timeout = beacon_time
    while i < len(id) and not aligned:
    #while 1 and not aligned:
        slot_end_time = op_time + time.time()
        # send syn and listen for ack
        if id[i] == '1':
            # change mode to transmission -> affects the angular velocity
            disc.changeMode(id[i])
            # repeatedly send syn and then listen for ack for op_time seconds
            while time.time() < slot_end_time and not aligned:
                # send out a syn
                sendSyn(beacon_time, id)
                # listen for an ack in response
                listenForAck(beacon_time, id)
        # listen for syn
        elif id[i] == '0':
            # change mode to reception -> affects the angular velocity
            disc.changeMode(id[i])
            # listen for an initial syn
            listenForSyn(op_time, id)
        i += 1
    # the 3d area was fully scanned, but we still failed to find the other node
    if not aligned:
        print('Could not find other node')
        disc.setAligned()
    return


if __name__ == "__main__":
    id = '1'
    #id = '0'
    idLen = len(id)
    # generate [ (floor(len(id) / 2) ) + 1 ] '0' bits for pseudo slot sequence
    for i in range(0, math.floor(idLen / 2) + 1):
        id += '0'
    # generate [ ( ceiling(len(id) / 2) ) + 1 ] '1' bits for pseudo slot sequence
    for i in range(0, math.ceil(idLen / 2)):
        id += '1'
    # servo path class
    disc = discovery.Discovery()
    disc.createPath()
    # servo path and handshake threads
    servoPathThread = threading.Thread(target=disc.scan)
    handshakeThread = threading.Thread(target=handshake, args=(disc, id))
    servoPathThread.start()
    handshakeThread.start()
    # wait till both end to exit
    servoPathThread.join()
    handshakeThread.join()

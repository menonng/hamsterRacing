import serial
from roboid import *

ham = Hamster()

arduino = serial.Serial('COM13', 9600, timeout=1)

while True:
    line = arduino.readline().decode('utf-8').strip()
    if not line:
        continue

    left, right = map(int, line.split(' | '))
    ham.wheels(left, right)


    print(left,right)
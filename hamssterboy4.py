#ma-ybe
from roboid import *
import random
import time
from arrowVision import start, get_direction

ham = Hamster()

distance = 38
basesp = 75
turnsp = 42

print('start')
print("종료하고 싶다면 'ctrl + c'를 Terminal 창에서 눌러라 애송이")

start()

direction = random.choice([0, 1])
left_prev = 0
right_prev = 0
block_time = 0

while True:
    left_raw = ham.left_proximity()
    right_raw = ham.right_proximity()

    left_sensor = (left_raw + left_prev) / 2
    right_sensor = (right_raw + right_prev) / 2
    left_prev = left_raw
    right_prev = right_raw

    sign = get_direction()

    if (left_sensor > distance or right_sensor > distance) and sign == "left":
        block_time = 0
        ham.wheels(-turnsp * 0.6, turnsp)
        print(f'sign-jwa | {left_sensor} | {right_sensor}')

    elif (left_sensor > distance or right_sensor > distance) and sign == "right":
        block_time = 0
        ham.wheels(turnsp, -turnsp * 0.6)
        print(f'sign-uuu | {left_sensor} | {right_sensor}')

    elif left_sensor > distance and right_sensor > distance:
        if block_time == 0:
            block_time = time.time()

        if left_sensor - right_sensor > 12:
            direction = 0
        elif right_sensor - left_sensor > 12:
            direction = 1

        if direction == 0 and left_sensor > 55:
            direction = 1
        elif direction == 1 and right_sensor > 55:
            direction = 0

        if time.time() - block_time > 2.0:
            ham.wheels(-turnsp, -turnsp)
            time.sleep(0.5)
            block_time = time.time()
            print(f'dui | {left_sensor} | {right_sensor}')
        elif direction == 0:
            ham.wheels(-turnsp * 0.6, turnsp)
            print(f'jwa | {left_sensor} | {right_sensor}')
        else:
            ham.wheels(turnsp, -turnsp * 0.6)
            print(f'uuu | {left_sensor} | {right_sensor}')

    elif left_sensor > distance:
        block_time = 0
        direction = 1
        speed = basesp - (left_sensor - distance) * 2.0
        if speed < -turnsp:
            speed = -turnsp
        ham.wheels(basesp, speed)
        print(f'uuu | {left_sensor} | {right_sensor}')

    elif right_sensor > distance:
        block_time = 0
        direction = 0
        speed = basesp - (right_sensor - distance) * 2.0
        if speed < -turnsp:
            speed = -turnsp
        ham.wheels(speed, basesp)
        print(f'jwa | {left_sensor} | {right_sensor}')

    else:
        block_time = 0
        ham.wheels(basesp, basesp)
        print(f'apb | {left_sensor} | {right_sensor}')

    wait(20)

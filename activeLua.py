import atexit
import os
import subprocess
import threading
import time
from pathlib import Path

import cv2

BASE_DIR = Path(__file__).resolve().parent

love_dir = Path(r"C:/Program Files/LOVE")
love_exe = love_dir / "lovec.exe"
if not love_exe.exists():
    love_exe = love_dir / "love.exe"

lua_dir = BASE_DIR / "lua"
game_dir = BASE_DIR / "lua_run"
image_path = game_dir / "current.jpg"
tmp_path = game_dir / "current.tmp"

stream_url = "http://192.168.66.1:9527/videostream.cgi?loginuse=admin&loginpas=admin"
write_interval = 0.1
stale_time = 1.0
echo_lua = True

direction = None
last_time = 0
lock = threading.Lock()
stop_event = threading.Event()
process = None
stats = {"read": 0, "saved": 0, "fail": 0}


def _prepare():
    game_dir.mkdir(exist_ok=True)

    conf = (lua_dir / "conf.lua").read_text(encoding="utf-8")
    conf = conf.replace("t.console = true", "t.console = false")
    (game_dir / "conf.lua").write_text(conf, encoding="utf-8")

    main = (lua_dir / "main.lua").read_text(encoding="utf-8")
    (game_dir / "main.lua").write_text("io.stdout:setvbuf('no') " + main, encoding="utf-8")


def _read_lua():
    global direction, last_time

    for line in process.stdout:
        text = line.strip()
        if not text:
            continue

        if text in ("left", "right", "unknown"):
            with lock:
                direction = text if text != "unknown" else None
                last_time = time.time()
            if echo_lua:
                print(f'lua | {text}')
        else:
            print(f'lua | {text}')


def _save(frame):
    ok, buf = cv2.imencode(".jpg", frame)
    if not ok:
        stats["fail"] += 1
        return

    try:
        tmp_path.write_bytes(buf.tobytes())
        os.replace(tmp_path, image_path)
        stats["saved"] += 1
    except OSError as e:
        if stats["fail"] == 0:
            print(f'save fail | {e}')
        stats["fail"] += 1


def _camera():
    cap = cv2.VideoCapture(stream_url)

    if not cap.isOpened():
        print(f'camera fail | {stream_url}')
        stop_event.set()
        return

    last_write = 0

    while not stop_event.is_set():
        ret, frame = cap.read()
        if not ret or frame is None:
            time.sleep(0.01)
            continue

        stats["read"] += 1

        if time.time() - last_write >= write_interval:
            _save(frame)
            last_write = time.time()

        cv2.imshow("Camera", frame)
        if cv2.waitKey(1) & 0xFF == 27:
            stop_event.set()

    cap.release()
    cv2.destroyAllWindows()


def start():
    global process

    _prepare()

    process = subprocess.Popen(
        [str(love_exe), str(game_dir)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="ignore",
        bufsize=1,
    )

    threading.Thread(target=_read_lua, daemon=True).start()
    threading.Thread(target=_camera, daemon=True).start()


def get_direction():
    with lock:
        if time.time() - last_time > stale_time:
            return None
        return direction


def stop():
    stop_event.set()
    if process is not None and process.poll() is None:
        process.terminate()


atexit.register(stop)


if __name__ == "__main__":
    start()

    try:
        while not stop_event.is_set():
            alive = process.poll() is None
            print(f'read {stats["read"]} | saved {stats["saved"]} | fail {stats["fail"]} | love {alive} | {get_direction()}')
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        stop()
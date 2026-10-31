import atexit
import math
import os
import re
import subprocess
import threading
import time
from pathlib import Path

import cv2
import numpy as np

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

overlay_mode = 2
analyze_interval = 0.25
crop_margin_x = 0
block_size = 10
threshold_ratio = 0.15

SKY = (187, 197, 57)
YELLOW = (17, 204, 255)
ORANGE = (0, 126, 255)
GREEN = (68, 187, 85)
RED = (69, 0, 255)
PINK = (204, 180, 255)
NAVY = (94, 42, 27)
WHITE = (255, 255, 255)


def _read_params():
    global crop_margin_x, block_size, threshold_ratio

    try:
        text = (lua_dir / "main.lua").read_text(encoding="utf-8")
    except OSError:
        return

    code = "\n".join(line.split("--")[0] for line in text.splitlines())

    found = re.search(r"crop_margin_x\s*=\s*(\d+)", code)
    crop_margin_x = int(found.group(1)) if found else 0

    found = re.search(r"get_sign_block_grid\(\s*img_data\s*,\s*(\d+)", code)
    if not found:
        found = re.search(r"block_size\s*=\s*block_size\s+or\s+(\d+)", code)
    if found:
        block_size = int(found.group(1))

    found = re.search(r"threshold_ratio\s*=\s*threshold_ratio\s+or\s+([\d.]+)", code)
    if found:
        threshold_ratio = float(found.group(1))


def _prepare():
    _read_params()
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
        return None

    try:
        tmp_path.write_bytes(buf.tobytes())
        os.replace(tmp_path, image_path)
        stats["saved"] += 1
    except OSError as e:
        if stats["fail"] == 0:
            print(f'save fail | {e}')
        stats["fail"] += 1

    return buf


def _longest_run(mask):
    pad = np.zeros((mask.shape[0], mask.shape[1] + 2), np.int8)
    pad[:, 1:-1] = mask
    d = np.diff(pad, axis=1)
    sy, sx = np.nonzero(d == 1)
    ey, ex = np.nonzero(d == -1)
    if len(sx) == 0:
        return 0, 0, 0, 0
    k = np.argmax(ex - sx)
    return int(ex[k] - sx[k]), int(sy[k]), int(sx[k]) + 1, int(ex[k])


def _analyze(frame):
    h, w = frame.shape[:2]
    b = frame[:, :, 0].astype(np.float32) / 255
    g = frame[:, :, 1].astype(np.float32) / 255
    r = frame[:, :, 2].astype(np.float32) / 255

    mask = (b > 0.4) & (b > r + 0.15) & (b > g + 0.15)
    mask[:, :crop_margin_x] = False
    mask[:, max(crop_margin_x, w - crop_margin_x):] = False
    found = int(mask.sum())

    result = {"mask": mask, "found": found, "total": w * h, "region": None, "reason": None}

    if found < 80:
        result["reason"] = "too few blue pixels"
        return result

    run_w, run_y, x1, x2 = _longest_run(mask)
    run_h, run_x, y1, y2 = _longest_run(mask.T)

    if run_w < 20 or run_h < 20:
        result["reason"] = "continuous area too small"
        return result

    side = max(run_w, run_h)
    center_x = (x1 + x2) / 2
    center_y = (y1 + y2) / 2

    min_x = math.floor(center_x - side / 2)
    max_x = min_x + side - 1
    min_y = math.floor(center_y - side / 2)
    max_y = min_y + side - 1

    min_x = max(1, min_x)
    min_y = max(1, min_y)
    max_x = min(w, max_x)
    max_y = min(h, max_y)

    crop_w = max_x - min_x + 1
    crop_h = max_y - min_y + 1
    grid_w = math.ceil(crop_w / block_size)
    grid_h = math.ceil(crop_h / block_size)

    x0 = min_x - 1
    y0 = min_y - 1
    blue = np.zeros((grid_h * block_size, grid_w * block_size), np.int32)
    valid = np.zeros_like(blue)
    part = mask[y0:y0 + grid_h * block_size, x0:x0 + grid_w * block_size]
    blue[:part.shape[0], :part.shape[1]] = part
    valid[:part.shape[0], :part.shape[1]] = 1

    blue_count = blue.reshape(grid_h, block_size, grid_w, block_size).sum(axis=(1, 3))
    total_count = valid.reshape(grid_h, block_size, grid_w, block_size).sum(axis=(1, 3))
    grid = blue_count > total_count * threshold_ratio

    left_cols = np.arange(1, grid_w + 1) <= grid_w / 2
    left = int(grid[:, left_cols].sum())
    right = int(grid[:, ~left_cols].sum())

    if left > right:
        side_dir = "left"
    elif right > left:
        side_dir = "right"
    else:
        side_dir = "unknown"

    result["region"] = {
        "box": (x0, y0, max_x - 1, max_y - 1),
        "origin": (x0, y0),
        "grid": grid,
        "mid": x0 + int(left_cols.sum()) * block_size,
        "side": side,
        "left": left,
        "right": right,
        "left_total": int(left_cols.sum()) * grid_h,
        "right_total": int((~left_cols).sum()) * grid_h,
        "direction": side_dir,
        "h_run": (run_y, x1 - 1, x2 - 1),
        "v_run": (run_x, y1 - 1, y2 - 1),
    }
    return result


def _panel(frame, lines):
    panel_w = 12 + max(cv2.getTextSize(t, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0][0] for t in lines)
    cv2.rectangle(frame, (0, 0), (panel_w, 12 + 20 * len(lines)), NAVY, -1)
    for i, t in enumerate(lines):
        color = YELLOW if i == len(lines) - 1 else WHITE
        cv2.putText(frame, t, (6, 20 + 20 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)


def _draw(frame, result, lua_direction):
    h, w = frame.shape[:2]
    mask = result["mask"]
    region = result["region"]

    if crop_margin_x > 0:
        frame[:, :crop_margin_x] = frame[:, :crop_margin_x] // 2
        frame[:, max(crop_margin_x, w - crop_margin_x):] = frame[:, max(crop_margin_x, w - crop_margin_x):] // 2

    if region:
        x0, y0 = region["origin"]
        layer = frame.copy()
        by, bx = np.nonzero(region["grid"])
        for gy, gx in zip(by, bx):
            px = x0 + gx * block_size
            py = y0 + gy * block_size
            color = GREEN if px < region["mid"] else ORANGE
            cv2.rectangle(layer, (px, py), (px + block_size - 1, py + block_size - 1), color, -1)
        cv2.addWeighted(layer, 0.45, frame, 0.55, 0, frame)

    step = max(2, w // 160)
    ys, xs = np.nonzero(mask[::step, ::step])
    ys = ys * step
    xs = xs * step
    for dy in (0, 1):
        for dx in (0, 1):
            frame[np.minimum(ys + dy, h - 1), np.minimum(xs + dx, w - 1)] = SKY

    lines = [f'blue {result["found"]} ({result["found"] / result["total"] * 100:.1f}%)']
    dir_text = "none"

    if region:
        x0, y0, x1, y1 = region["box"]
        cv2.rectangle(frame, (x0, y0), (x1, y1), YELLOW, 2)
        cv2.line(frame, (region["mid"], y0), (region["mid"], y1), PINK, 1)

        run_y, hx1, hx2 = region["h_run"]
        run_x, vy1, vy2 = region["v_run"]
        cv2.line(frame, (hx1, run_y), (hx2, run_y), RED, 1)
        cv2.line(frame, (run_x, vy1), (run_x, vy2), RED, 1)

        dir_text = region["direction"]
        on = region["left"] + region["right"]
        total = region["left_total"] + region["right_total"]

        if overlay_mode == 1:
            share = on if on else 1
            lines.append(f'region {region["side"]}px  L {region["left"]} ({region["left"] / share * 100:.0f}%)  R {region["right"]} ({region["right"] / share * 100:.0f}%)')
        else:
            lines.append(f'box {region["side"]}px  block {on}/{total} ({on / total * 100:.0f}%)  other {total - on} ({(total - on) / total * 100:.0f}%)')

            left_pct = region["left"] / region["left_total"] * 100 if region["left_total"] else 0
            right_pct = region["right"] / region["right_total"] * 100 if region["right_total"] else 0
            tags = (
                (f'L {left_pct:.0f}% ({region["left"]})', GREEN, False),
                (f'R {right_pct:.0f}% ({region["right"]})', ORANGE, True),
            )
            for text, color, on_right in tags:
                (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                bw = tw + 12
                bh = th + 12
                bx = region["mid"] if on_right else region["mid"] - bw
                by = y0 - bh if y0 >= bh else y0
                cv2.rectangle(frame, (bx, by), (bx + bw, by + bh), color, -1)
                cv2.rectangle(frame, (bx, by), (bx + bw, by + bh), NAVY, 1)
                cv2.putText(frame, text, (bx + 6, by + bh - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, NAVY, 1, cv2.LINE_AA)
    else:
        lines.append(f'none: {result["reason"]}')

    lines.append(f'dir {dir_text}  |  lua {lua_direction if lua_direction else "none"}')
    _panel(frame, lines)


def _camera():
    cap = cv2.VideoCapture(stream_url)

    if not cap.isOpened():
        print(f'camera fail | {stream_url}')
        stop_event.set()
        return

    last_write = 0
    last_analyze = 0
    result = None

    while not stop_event.is_set():
        ret, frame = cap.read()
        if not ret or frame is None:
            time.sleep(0.01)
            continue

        stats["read"] += 1

        if time.time() - last_write >= write_interval:
            buf = _save(frame)
            last_write = time.time()

            if buf is not None and time.time() - last_analyze >= analyze_interval:
                image = cv2.imdecode(buf, cv2.IMREAD_COLOR)
                if image is not None:
                    result = _analyze(image)
                    last_analyze = time.time()

        if result is not None and result["mask"].shape == frame.shape[:2]:
            _draw(frame, result, get_direction())

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
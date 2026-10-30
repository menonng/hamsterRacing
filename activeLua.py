import math
import subprocess
import time
import cv2
import numpy as np
from pathlib import Path
from roboid import *

BASE_DIR = Path(__file__).resolve().parent

love_exe = r"C:/Program Files/LOVE/love.exe"
game_dir = BASE_DIR / "lua"

process = subprocess.Popen([
    love_exe,
    game_dir
])

image_path = Path(game_dir) / "current.jpg"

cap = cv2.VideoCapture("MJPEG_URL")

SKY = (187, 197, 57)
YELLOW = (17, 204, 255)
ORANGE = (0, 126, 255)
GREEN = (68, 187, 85)
RED = (69, 0, 255)
PINK = (204, 180, 255)
NAVY = (94, 42, 27)
WHITE = (255, 255, 255)

analyze_interval = 0.1


def longest_run(mask):
    pad = np.zeros((mask.shape[0], mask.shape[1] + 2), np.int8)
    pad[:, 1:-1] = mask
    d = np.diff(pad, axis=1)
    sy, sx = np.nonzero(d == 1)
    ey, ex = np.nonzero(d == -1)
    if len(sx) == 0:
        return 0, 0, 0, 0
    k = np.argmax(ex - sx)
    return int(ex[k] - sx[k]), int(sy[k]), int(sx[k]) + 1, int(ex[k])


def analyze(frame):
    h, w = frame.shape[:2]
    b = frame[:, :, 0].astype(np.float32) / 255
    g = frame[:, :, 1].astype(np.float32) / 255
    r = frame[:, :, 2].astype(np.float32) / 255

    mask = (b > 0.4) & (b > r + 0.15) & (b > g + 0.15)
    found = int(mask.sum())

    result = {"mask": mask, "found": found, "total": w * h, "region": None, "reason": None}

    if found < 80:
        result["reason"] = "too few blue pixels"
        return result

    run_w, run_y, x1, x2 = longest_run(mask)
    run_h, run_x, y1, y2 = longest_run(mask.T)

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

    crop = mask[min_y - 1:max_y, min_x - 1:max_x]
    crop_w = max_x - min_x + 1
    left_cols = np.arange(1, crop_w + 1) <= crop_w / 2

    left = int(crop[:, left_cols].sum())
    right = int(crop[:, ~left_cols].sum())
    crop_h = max_y - min_y + 1
    left_area = int(left_cols.sum()) * crop_h
    right_area = (crop_w - int(left_cols.sum())) * crop_h

    if left > right:
        direction = "left"
    elif right > left:
        direction = "right"
    else:
        direction = "unknown"

    result["region"] = {
        "box": (min_x - 1, min_y - 1, max_x - 1, max_y - 1),
        "mid": min_x - 1 + crop_w // 2,
        "side": side,
        "left": left,
        "right": right,
        "left_area": left_area,
        "right_area": right_area,
        "direction": direction,
        "h_run": (run_y, x1 - 1, x2 - 1),
        "v_run": (run_x, y1 - 1, y2 - 1),
    }
    return result


def draw(frame, result):
    h, w = frame.shape[:2]
    mask = result["mask"]
    region = result["region"]

    step = max(2, w // 160)
    ys, xs = np.nonzero(mask[::step, ::step])
    ys = ys * step
    xs = xs * step

    colors = np.tile(np.array(SKY, np.uint8), (len(xs), 1))
    if region:
        x0, y0, x1, y1 = region["box"]
        inside = (xs >= x0) & (xs <= x1) & (ys >= y0) & (ys <= y1)
        colors[inside & (xs < region["mid"])] = GREEN
        colors[inside & (xs >= region["mid"])] = ORANGE

    for dy in (0, 1):
        for dx in (0, 1):
            frame[np.minimum(ys + dy, h - 1), np.minimum(xs + dx, w - 1)] = colors

    lines = [f'blue {result["found"]} ({result["found"] / result["total"] * 100:.1f}%)']

    if region:
        x0, y0, x1, y1 = region["box"]
        cv2.rectangle(frame, (x0, y0), (x1, y1), YELLOW, 2)
        cv2.line(frame, (region["mid"], y0), (region["mid"], y1), PINK, 1)

        run_y, hx1, hx2 = region["h_run"]
        run_x, vy1, vy2 = region["v_run"]
        cv2.line(frame, (hx1, run_y), (hx2, run_y), RED, 1)
        cv2.line(frame, (run_x, vy1), (run_x, vy2), RED, 1)

        area = region["left_area"] + region["right_area"]
        inside = region["left"] + region["right"]
        lines.append(f'box {region["side"]}px  blue {inside}/{area} ({inside / area * 100:.0f}%)  other {area - inside} ({(area - inside) / area * 100:.0f}%)')
        lines.append(f'dir {region["direction"]}')
    else:
        lines.append(f'none: {result["reason"]}')

    if region:
        x0, y0, x1, y1 = region["box"]
        tags = (
            (f'L {region["left"] / region["left_area"] * 100:.0f}% ({region["left"]})', GREEN, False),
            (f'R {region["right"] / region["right_area"] * 100:.0f}% ({region["right"]})', ORANGE, True),
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

    panel_w = 12 + max(cv2.getTextSize(t, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0][0] for t in lines)
    cv2.rectangle(frame, (0, 0), (panel_w, 12 + 20 * len(lines)), NAVY, -1)
    for i, t in enumerate(lines):
        color = YELLOW if i == len(lines) - 1 else WHITE
        cv2.putText(frame, t, (6, 20 + 20 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)


result = None
last_analyze = 0

try:
    while True:
        ret, frame = cap.read()

        if not ret:
            continue

        # current.jpg 실시간 갱신
        cv2.imwrite(str(image_path), frame)

        if result is None or time.time() - last_analyze >= analyze_interval:
            result = analyze(frame)
            last_analyze = time.time()

        draw(frame, result)

        # 실시간 카메라 화면 출력
        cv2.imshow("Camera", frame)

        # ESC를 누르면 종료
        if cv2.waitKey(1) & 0xFF == 27:
            break

finally:
    cap.release()
    cv2.destroyAllWindows()
    process.terminate()
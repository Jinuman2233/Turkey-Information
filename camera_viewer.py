"""camera_viewer.py

OpenCV로 웹캠(카메라) 화면을 실시간으로 보여주는 간단한 데스크톱 뷰어입니다.

기능
----
- 실시간 카메라 프리뷰 (FPS 표시)
- 스페이스바 / 's' 키로 현재 화면을 이미지 파일로 저장 (Pillow 사용)
- 'q' 키 또는 ESC 키, 창 닫기로 종료
- 카메라 인덱스, 저장 폴더, 해상도를 커맨드라인 옵션으로 지정 가능

실행 방법
--------
    python camera_viewer.py
    python camera_viewer.py --camera 1 --save-dir captures --width 1280 --height 720

실행 파일(exe)로 빌드하기 (PyInstaller)
--------------------------------------
    pyinstaller --onefile --name camera_viewer camera_viewer.py

빌드가 끝나면 `dist/camera_viewer` (Windows는 `dist/camera_viewer.exe`) 실행 파일이 생성됩니다.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import cv2
from PIL import Image

WINDOW_TITLE = "Camera Viewer (q: 종료, s/Space: 저장)"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="간단한 OpenCV 웹캠 뷰어")
    parser.add_argument(
        "--camera",
        type=int,
        default=0,
        help="사용할 카메라 장치 인덱스 (기본값: 0)",
    )
    parser.add_argument(
        "--save-dir",
        type=str,
        default="captures",
        help="캡처한 이미지를 저장할 폴더 (기본값: captures)",
    )
    parser.add_argument("--width", type=int, default=None, help="카메라 캡처 가로 해상도")
    parser.add_argument("--height", type=int, default=None, help="카메라 캡처 세로 해상도")
    return parser.parse_args(argv)


def open_camera(index: int, width: int | None, height: int | None) -> cv2.VideoCapture:
    capture = cv2.VideoCapture(index)
    if width:
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    if height:
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    return capture


def save_snapshot(frame, save_dir: Path) -> Path:
    """BGR(OpenCV) 프레임을 Pillow로 변환해 PNG 파일로 저장합니다."""
    save_dir.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    file_path = save_dir / f"capture_{timestamp}.png"

    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    Image.fromarray(rgb_frame).save(file_path)
    return file_path


def run(args: argparse.Namespace) -> int:
    save_dir = Path(args.save_dir)
    capture = open_camera(args.camera, args.width, args.height)

    if not capture.isOpened():
        print(f"[오류] 카메라(인덱스 {args.camera})를 열 수 없습니다.", file=sys.stderr)
        return 1

    print("카메라 뷰어를 시작합니다. 'q'/ESC로 종료, 's' 또는 Space로 스냅샷 저장.")

    prev_tick = cv2.getTickCount()
    fps = 0.0

    try:
        while True:
            ok, frame = capture.read()
            if not ok or frame is None:
                print("[오류] 카메라에서 프레임을 읽지 못했습니다.", file=sys.stderr)
                break

            current_tick = cv2.getTickCount()
            elapsed = (current_tick - prev_tick) / cv2.getTickFrequency()
            prev_tick = current_tick
            if elapsed > 0:
                fps = 0.9 * fps + 0.1 * (1.0 / elapsed)

            display_frame = frame.copy()
            cv2.putText(
                display_frame,
                f"FPS: {fps:.1f}",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (0, 255, 0),
                2,
            )

            cv2.imshow(WINDOW_TITLE, display_frame)
            key = cv2.waitKey(1) & 0xFF

            if key in (ord("q"), 27):  # 'q' 또는 ESC
                break
            if key in (ord("s"), ord(" ")):
                saved_path = save_snapshot(frame, save_dir)
                print(f"스냅샷 저장됨: {saved_path}")
    finally:
        capture.release()
        cv2.destroyAllWindows()

    return 0


def main() -> None:
    args = parse_args()
    sys.exit(run(args))


if __name__ == "__main__":
    main()

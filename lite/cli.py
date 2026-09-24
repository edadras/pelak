"""One-shot CLI for file/video without starting the web server."""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cv2

from lite.reader import PlateReader, process_image_file, process_video_file

OUTPUT_DIR = Path(os.getenv("LITE_OUTPUT_DIR", "/output"))
DATA_DIR = Path(os.getenv("LITE_DATA_DIR", "/data"))
PLATE_CONF = float(os.getenv("PLATE_CONF", "0.25"))
CHAR_CONF = float(os.getenv("CHAR_CONF", "0.25"))
FRAME_SKIP = int(os.getenv("LITE_FRAME_SKIP", "5"))


def resolve_path(path_str):
    target = Path(path_str)
    if target.exists():
        return target
    return DATA_DIR / path_str


def main():
    mode = os.getenv("LITE_MODE", "file")
    source = os.getenv("LITE_SOURCE", "")
    if not source:
        print("Set LITE_SOURCE to an image or video path.", file=sys.stderr)
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    reader = PlateReader.get(plate_conf=PLATE_CONF, char_conf=CHAR_CONF)
    target = resolve_path(source)

    if mode == "file":
        plates, annotated = process_image_file(reader, str(target))
        out_path = OUTPUT_DIR / f"{target.stem}_result.jpg"
        cv2.imwrite(str(out_path), annotated)
        print(json.dumps({"output": str(out_path), "plates": plates}, ensure_ascii=False, indent=2))
        return

    if mode == "video":
        out_path = OUTPUT_DIR / f"{target.stem}_annotated.mp4"
        results = process_video_file(
            reader, str(target), frame_skip=FRAME_SKIP, output_path=str(out_path)
        )
        json_path = OUTPUT_DIR / f"{target.stem}_results.json"
        json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {
                    "video_output": str(out_path),
                    "json_output": str(json_path),
                    "detections": len(results),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    print(f"Unsupported LITE_MODE for CLI: {mode}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()

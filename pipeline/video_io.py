"""
Frame extraction from uploaded video files and H.264 reassembly.
"""
from __future__ import annotations

import subprocess
import tempfile
import os
from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np

from config import MAX_FRAMES


def extract_frames(
    video_path: str,
    max_frames: int = MAX_FRAMES,
    stride: int = 1,
) -> Tuple[List[np.ndarray], float, int]:
    """
    Extract up to *max_frames* frames from *video_path*, subsampling evenly
    if the video is longer.

    Returns
    -------
    frames : list of BGR numpy arrays
    fps    : original frames-per-second
    total_frame_count : total frames in source video
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # Determine which frame indices to keep
    effective_total = max(1, total)
    if effective_total * stride > max_frames:
        # subsample evenly across the video
        indices = set(
            np.linspace(0, effective_total - 1, max_frames, dtype=int).tolist()
        )
    else:
        indices = set(range(0, effective_total, stride))

    # Downscale 4K+ videos to 1080p before pose detection — MediaPipe doesn't
    # need full resolution and decoding/storing 4K frames is very slow.
    MAX_DIM = 1080
    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    scale = min(1.0, MAX_DIM / max(width, height))

    frames: List[np.ndarray] = []
    sorted_indices = sorted(indices)

    for idx in sorted_indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if not ret:
            continue
        if scale < 1.0:
            new_w = int(width * scale)
            new_h = int(height * scale)
            frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
        frames.append(frame)

    cap.release()
    return frames, fps, total


def frames_to_video(
    frames: List[np.ndarray],
    output_path: str,
    fps: float = 30.0,
) -> str:
    """
    Write *frames* to an MP4 file at *output_path*.

    Attempts H.264 re-encode via ffmpeg so the file plays in browsers.
    Falls back to mp4v if ffmpeg is unavailable.

    Returns the final output path.
    """
    if not frames:
        raise ValueError("No frames to write")

    h, w = frames[0].shape[:2]

    # Write intermediate file with mp4v codec
    with tempfile.NamedTemporaryFile(suffix="_raw.mp4", delete=False) as tmp:
        raw_path = tmp.name

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(raw_path, fourcc, fps, (w, h))
    for frame in frames:
        writer.write(frame)
    writer.release()

    # Try H.264 re-encode with ffmpeg
    if _ffmpeg_available():
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i", raw_path,
                    "-vcodec", "libx264",
                    "-pix_fmt", "yuv420p",
                    "-preset", "fast",
                    "-crf", "23",
                    output_path,
                ],
                check=True,
                capture_output=True,
            )
            os.unlink(raw_path)
            return output_path
        except subprocess.CalledProcessError:
            pass  # fall through to raw copy

    # Fallback — just rename the raw file
    os.replace(raw_path, output_path)
    return output_path


def _ffmpeg_available() -> bool:
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            check=True,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

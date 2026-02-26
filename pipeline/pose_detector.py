"""
MediaPipe Pose wrapper — Tasks API (mediapipe >= 0.10).
"""
from __future__ import annotations

import os
import urllib.request
from dataclasses import dataclass
from typing import List, Optional, Tuple

import cv2
import mediapipe as mp
import numpy as np

from config import VISIBILITY_THRESHOLD

# ---------------------------------------------------------------------------
# Model management
# ---------------------------------------------------------------------------

_MODEL_URLS = {
    0: (
        "https://storage.googleapis.com/mediapipe-models/"
        "pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
    ),
    1: (
        "https://storage.googleapis.com/mediapipe-models/"
        "pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task"
    ),
    2: (
        "https://storage.googleapis.com/mediapipe-models/"
        "pose_landmarker/pose_landmarker_heavy/float16/1/pose_landmarker_heavy.task"
    ),
}
_MODEL_NAMES = {
    0: "pose_landmarker_lite.task",
    1: "pose_landmarker_full.task",
    2: "pose_landmarker_heavy.task",
}
_MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "models")


def _ensure_model(complexity: int) -> str:
    """Download the pose landmarker model if not already cached. Returns path."""
    complexity = max(0, min(2, complexity))
    os.makedirs(_MODELS_DIR, exist_ok=True)
    path = os.path.abspath(os.path.join(_MODELS_DIR, _MODEL_NAMES[complexity]))
    if not os.path.exists(path):
        url = _MODEL_URLS[complexity]
        print(f"Downloading MediaPipe pose model ({_MODEL_NAMES[complexity]}) ...")
        urllib.request.urlretrieve(url, path)
        print("Download complete.")
    return path


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class LandmarkResult:
    """Per-frame pose result.

    landmarks: list of (x, y, z, visibility) tuples — one per MediaPipe landmark.
               Coordinates are normalized [0, 1].
    frame_index: index in the original frame sequence.
    """
    landmarks: List[Tuple[float, float, float, float]]
    frame_index: int

    def get_point(self, idx: int) -> Optional[Tuple[float, float]]:
        """Return (x, y) for landmark *idx* if visibility >= threshold, else None."""
        if idx >= len(self.landmarks):
            return None
        x, y, _, vis = self.landmarks[idx]
        if vis < VISIBILITY_THRESHOLD:
            return None
        return (x, y)

    def get_pixel(
        self, idx: int, width: int, height: int
    ) -> Optional[Tuple[int, int]]:
        """Return pixel coordinates (px, py) for landmark *idx*, or None."""
        pt = self.get_point(idx)
        if pt is None:
            return None
        return (int(pt[0] * width), int(pt[1] * height))


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------

class PoseDetector:
    """Thin wrapper around MediaPipe PoseLandmarker (Tasks API)."""

    def __init__(
        self,
        model_complexity: int = 1,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
    ) -> None:
        model_path = _ensure_model(model_complexity)

        PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions
        RunningMode = mp.tasks.vision.RunningMode

        options = PoseLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=model_path),
            running_mode=RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=min_detection_confidence,
            min_pose_presence_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )
        self._landmarker = mp.tasks.vision.PoseLandmarker.create_from_options(options)
        # Monotonically increasing timestamp (ms); assume ~30 fps
        self._timestamp_ms: int = 0

    def detect(
        self, frame: np.ndarray, frame_index: int = 0
    ) -> Optional[LandmarkResult]:
        """Run pose detection on a single BGR frame.

        Returns a LandmarkResult or None if no pose detected.
        """
        self._timestamp_ms += 33  # ~30 fps cadence

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect_for_video(mp_image, self._timestamp_ms)

        if not result.pose_landmarks:
            return None

        landmarks = [
            (lm.x, lm.y, lm.z, lm.visibility)
            for lm in result.pose_landmarks[0]
        ]
        return LandmarkResult(landmarks=landmarks, frame_index=frame_index)

    def detect_batch(
        self, frames: List[np.ndarray]
    ) -> List[Optional[LandmarkResult]]:
        """Detect pose in each frame. Returns list aligned with *frames*."""
        return [self.detect(frame, i) for i, frame in enumerate(frames)]

    def close(self) -> None:
        self._landmarker.close()

    def __enter__(self) -> "PoseDetector":
        return self

    def __exit__(self, *args) -> None:
        self.close()

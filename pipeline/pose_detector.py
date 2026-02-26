"""
MediaPipe Pose wrapper.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import cv2
import mediapipe as mp
import numpy as np

from config import VISIBILITY_THRESHOLD


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
        """
        Return (x, y) for landmark *idx* if visibility >= threshold, else None.
        """
        if idx >= len(self.landmarks):
            return None
        x, y, _, vis = self.landmarks[idx]
        if vis < VISIBILITY_THRESHOLD:
            return None
        return (x, y)

    def get_pixel(
        self, idx: int, width: int, height: int
    ) -> Optional[Tuple[int, int]]:
        """
        Return pixel coordinates (px, py) for landmark *idx*, or None.
        """
        pt = self.get_point(idx)
        if pt is None:
            return None
        return (int(pt[0] * width), int(pt[1] * height))


class PoseDetector:
    """Thin wrapper around MediaPipe Pose."""

    def __init__(
        self,
        model_complexity: int = 1,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
    ) -> None:
        self._pose = mp.solutions.pose.Pose(
            static_image_mode=False,
            model_complexity=model_complexity,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )

    def detect(
        self, frame: np.ndarray, frame_index: int = 0
    ) -> Optional[LandmarkResult]:
        """
        Run pose detection on a single BGR frame.
        Returns a LandmarkResult or None if no pose detected.
        """
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = self._pose.process(rgb)

        if result.pose_landmarks is None:
            return None

        landmarks = [
            (lm.x, lm.y, lm.z, lm.visibility)
            for lm in result.pose_landmarks.landmark
        ]
        return LandmarkResult(landmarks=landmarks, frame_index=frame_index)

    def detect_batch(
        self, frames: List[np.ndarray]
    ) -> List[Optional[LandmarkResult]]:
        """
        Detect pose in each frame. Returns list aligned with *frames*.
        """
        return [self.detect(frame, i) for i, frame in enumerate(frames)]

    def close(self) -> None:
        self._pose.close()

    def __enter__(self) -> "PoseDetector":
        return self

    def __exit__(self, *args) -> None:
        self.close()

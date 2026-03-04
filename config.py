"""
Constants, landmark indices, and configuration for the CourtCoach pipeline.
"""

# MediaPipe Pose landmark indices
class Landmarks:
    NOSE = 0
    LEFT_SHOULDER = 11
    RIGHT_SHOULDER = 12
    LEFT_ELBOW = 13
    RIGHT_ELBOW = 14
    LEFT_WRIST = 15
    RIGHT_WRIST = 16
    LEFT_HIP = 23
    RIGHT_HIP = 24
    LEFT_KNEE = 25
    RIGHT_KNEE = 26
    LEFT_ANKLE = 27
    RIGHT_ANKLE = 28


# Skeleton connections for drawing
POSE_CONNECTIONS = [
    (Landmarks.LEFT_SHOULDER, Landmarks.RIGHT_SHOULDER),
    (Landmarks.LEFT_SHOULDER, Landmarks.LEFT_ELBOW),
    (Landmarks.LEFT_ELBOW, Landmarks.LEFT_WRIST),
    (Landmarks.RIGHT_SHOULDER, Landmarks.RIGHT_ELBOW),
    (Landmarks.RIGHT_ELBOW, Landmarks.RIGHT_WRIST),
    (Landmarks.LEFT_SHOULDER, Landmarks.LEFT_HIP),
    (Landmarks.RIGHT_SHOULDER, Landmarks.RIGHT_HIP),
    (Landmarks.LEFT_HIP, Landmarks.RIGHT_HIP),
    (Landmarks.LEFT_HIP, Landmarks.LEFT_KNEE),
    (Landmarks.LEFT_KNEE, Landmarks.LEFT_ANKLE),
    (Landmarks.RIGHT_HIP, Landmarks.RIGHT_KNEE),
    (Landmarks.RIGHT_KNEE, Landmarks.RIGHT_ANKLE),
]

# Visibility threshold — landmarks below this are treated as missing
VISIBILITY_THRESHOLD = 0.35

# Maximum frames to process (≈10s at 30fps)
MAX_FRAMES = 300

# Minimum pose detection rate before warning user
MIN_DETECTION_RATE = 0.40

# Wrist speed peak detection threshold (pixels/frame, normalized by frame diagonal)
WRIST_SPEED_THRESHOLD = 0.02

# Minimum frames between swing events
MIN_SWING_INTERVAL = 10

# Annotation colors (BGR)
SKELETON_COLOR = (0, 255, 0)       # green
JOINT_COLOR = (0, 200, 255)        # yellow-orange
ANGLE_TEXT_COLOR = (255, 255, 255) # white
WRIST_TRAIL_COLOR = (0, 100, 255)  # orange-red
WARNING_COLOR = (0, 0, 255)        # red

# Font scale for annotation text
FONT_SCALE = 0.45
FONT_THICKNESS = 1

# Wrist trail length (frames)
TRAIL_LENGTH = 15

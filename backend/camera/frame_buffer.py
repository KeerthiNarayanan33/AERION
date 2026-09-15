import time
import threading
from collections import deque
from typing import List, Tuple, Optional
import numpy as np

class RollingFrameBuffer:
    """
    Thread-safe circular ring buffer maintaining the last N seconds
    of video frames for pre-event evidence recording.
    """
    def __init__(self, fps: int = 30, buffer_seconds: int = 10):
        self.fps = max(1, fps)
        self.buffer_seconds = max(1, buffer_seconds)
        self.max_frames = self.fps * self.buffer_seconds
        self._buffer: deque = deque(maxlen=self.max_frames)
        self._lock = threading.Lock()

    def push(self, frame: np.ndarray, timestamp: Optional[float] = None) -> None:
        """Pushes a frame and timestamp into the circular ring buffer."""
        ts = timestamp if timestamp is not None else time.time()
        with self._lock:
            self._buffer.append((ts, frame))

    def get_latest(self) -> Optional[Tuple[float, np.ndarray]]:
        """Returns the most recent (timestamp, frame) or None if buffer is empty."""
        with self._lock:
            if not self._buffer:
                return None
            return self._buffer[-1]

    def get_window(self, seconds: Optional[float] = None) -> List[Tuple[float, np.ndarray]]:
        """
        Retrieves frames captured within the last `seconds` (defaults to entire buffer).
        Returns a list of (timestamp, frame) tuples ordered chronologically.
        """
        req_seconds = seconds if seconds is not None else self.buffer_seconds
        cutoff_time = time.time() - req_seconds
        with self._lock:
            return [item for item in self._buffer if item[0] >= cutoff_time]

    def clear(self) -> None:
        """Clears all frames from buffer."""
        with self._lock:
            self._buffer.clear()

    @property
    def current_size(self) -> int:
        with self._lock:
            return len(self._buffer)

    @property
    def capacity(self) -> int:
        return self.max_frames

import os
import time
from pathlib import Path
from typing import Dict, Any, List
from backend.logger import logger

class StorageManager:
    """
    Manages physical storage for evidence artifacts (snapshots and MP4 video recordings).
    Enforces disk capacity quotas and retention policies.
    """

    def __init__(
        self,
        base_dir: str = "storage",
        max_storage_mb: float = 2048.0,
        max_age_days: float = 7.0
    ):
        self.base_dir = Path(base_dir)
        self.snapshots_dir = self.base_dir / "snapshots"
        self.events_dir = self.base_dir / "events"
        self.max_storage_mb = max_storage_mb
        self.max_age_days = max_age_days

        # Ensure directory structure exists
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.events_dir.mkdir(parents=True, exist_ok=True)

    def get_snapshot_path(self, event_id: str) -> Path:
        """Returns target file path for an event snapshot image."""
        return self.snapshots_dir / f"{event_id}.jpg"

    def get_video_path(self, event_id: str) -> Path:
        """Returns target file path for an event MP4 video clip."""
        return self.events_dir / f"{event_id}.mp4"

    def get_storage_stats(self) -> Dict[str, Any]:
        """Calculates total file count and disk usage across evidence directories."""
        snapshot_files = list(self.snapshots_dir.glob("*.jpg"))
        video_files = list(self.events_dir.glob("*.mp4"))

        snapshot_bytes = sum(f.stat().st_size for f in snapshot_files if f.is_file())
        video_bytes = sum(f.stat().st_size for f in video_files if f.is_file())
        total_bytes = snapshot_bytes + video_bytes
        total_mb = round(total_bytes / (1024 * 1024), 2)

        return {
            "snapshot_count": len(snapshot_files),
            "video_count": len(video_files),
            "total_files": len(snapshot_files) + len(video_files),
            "total_bytes": total_bytes,
            "total_mb": total_mb,
            "max_storage_mb": self.max_storage_mb,
            "usage_percent": round((total_mb / max(1.0, self.max_storage_mb)) * 100, 1)
        }

    def enforce_retention_policy(self) -> int:
        """
        Prunes evidence files exceeding the maximum age or if total storage exceeds quota.
        Deletes oldest files first. Returns count of deleted files.
        """
        now = time.time()
        max_age_sec = self.max_age_days * 86400.0
        deleted_count = 0

        # Collect all files with timestamps
        all_files: List[Path] = []
        for d in (self.snapshots_dir, self.events_dir):
            for f in d.iterdir():
                if f.is_file():
                    all_files.append(f)

        # 1. Prune files older than max_age_days
        remaining_files: List[Path] = []
        for f in all_files:
            try:
                mtime = f.stat().st_mtime
                if (now - mtime) > max_age_sec:
                    f.unlink()
                    deleted_count += 1
                    logger.info(f"[STORAGE] Pruned expired evidence file: {f.name}")
                else:
                    remaining_files.append(f)
            except Exception as e:
                logger.warning(f"[STORAGE] Error checking file {f}: {e}")

        # 2. Check total storage quota
        total_bytes = sum(f.stat().st_size for f in remaining_files if f.is_file())
        max_bytes = self.max_storage_mb * 1024 * 1024

        if total_bytes > max_bytes:
            # Sort remaining files by mtime ascending (oldest first)
            remaining_files.sort(key=lambda p: p.stat().st_mtime)
            for f in remaining_files:
                if total_bytes <= max_bytes:
                    break
                try:
                    size = f.stat().st_size
                    f.unlink()
                    total_bytes -= size
                    deleted_count += 1
                    logger.info(f"[STORAGE] Pruned oldest file to meet quota: {f.name}")
                except Exception as e:
                    logger.warning(f"[STORAGE] Failed to delete file {f}: {e}")

        return deleted_count

# Global StorageManager Singleton
storage_manager = StorageManager()

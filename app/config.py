from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    workspace: Path = field(default_factory=lambda: PROJECT_ROOT / "runtime" / "jobs")
    max_upload_bytes: int = 30 * 1024 * 1024
    max_pages: int = 100
    queue_size: int = 5
    timeout_seconds: float = 180
    ttl_seconds: float = 3600
    tombstone_seconds: float = 86400
    cleanup_interval: float = 60
    max_memory_bytes: int = 1024 * 1024 * 1024
    max_workspace_bytes: int = 1024 * 1024 * 1024
    allowed_hosts: tuple[str, ...] = ("127.0.0.1", "localhost", "[::1]")

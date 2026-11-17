from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import uuid4


def create_job_dir(outputs: Path) -> Path:
    """Create an isolated job directory that cannot collide with another render."""
    outputs.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    job_dir = outputs / f"{stamp}_{uuid4().hex}"
    job_dir.mkdir(parents=False, exist_ok=False)
    for name in ("shots", "audio", "images"):
        (job_dir / name).mkdir()
    return job_dir

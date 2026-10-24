import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    home: Path
    queue: Path
    snapshot: Path
    port: int = 5050
    stale_seconds: int = 30

    @classmethod
    def from_env(cls):
        home = Path(__file__).resolve().parent.parent
        project = Path(os.environ.get('JEV_PROJECT_ROOT', str(home.parent)))
        return cls(home, Path(os.environ.get('JEV_GTM_QUEUE', str(project / 'gtm-research' / 'staged_outreach.json'))),
                   Path(os.environ.get('JEV_SNAPSHOT', str(home / 'inbox' / 'offline_snapshot.json'))),
                   int(os.environ.get('JEV_HUD_PORT', '5050')),
                   int(os.environ.get('JEV_STALE_SECONDS', '30')))

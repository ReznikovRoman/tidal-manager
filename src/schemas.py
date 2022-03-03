from dataclasses import dataclass


@dataclass
class PlaylistData:
    id: str
    name: str
    track_ids: list[str]

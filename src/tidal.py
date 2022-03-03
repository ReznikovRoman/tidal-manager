import logging
import os
from typing import Final, Iterator

import tidalapi
from dotenv import load_dotenv

from schemas import PlaylistData


load_dotenv()

logging.basicConfig(format='%(asctime)s - %(message)s', level=logging.INFO)


# use tidalapi.Session.login_oauth_simple() to get user credentials - session_id, access and refresh tokens
# TODO: refactor authentication: save tokens to the database
# TODO: rewrite Tidal client - use asynchronous requests (aiohttp), use batch load/save


class SourceLoader:
    """`Source` loader."""

    def __init__(self, session: tidalapi.Session):
        self._session = session
        self._user_id: Final[int] = session.user.id

    def get_playlists_data(self) -> Iterator[tuple[str, str]]:
        return ((playlist.id, playlist.name) for playlist in self._session.get_user_playlists(self._user_id))

    def get_playlist_track_ids(self, playlist_id: str) -> list[str]:
        return [
            track.id
            for track in self._session.get_playlist_items(playlist_id)
            if isinstance(track, tidalapi.Track)
        ]

    def load_playlist(self) -> Iterator[PlaylistData]:
        for playlist_id, playlist_name in self.get_playlists_data():
            yield PlaylistData(id=playlist_id, name=playlist_name, track_ids=self.get_playlist_track_ids(playlist_id))


class TargetSaver:
    """`Target` saver."""

    def __init__(self, session: tidalapi.Session):
        self._session = session
        self._user_id: Final[int] = session.user.id

    def _get_existing_playlists(self) -> dict[str, str]:
        return {
            playlist.name: playlist.id
            for playlist in self._session.get_user_playlists(self._user_id)
        }

    def _create_playlist(self, playlist_name: str) -> str:
        response = self._session.request(
            'POST', f'users/{self._user_id}/playlists', data={"title": playlist_name, "description": ""})
        return response.json()["uuid"]

    def create_playlist(self, playlist_name: str) -> str:
        existing_playlists = self._get_existing_playlists()
        if playlist_name in existing_playlists:
            return existing_playlists[playlist_name]
        return self._create_playlist(playlist_name)

    def add_track_to_playlist(self, track_id: str, playlist_id: str) -> None:
        self._session.request(
            'POST',
            f'playlists/{playlist_id}/items',
            data={"trackIds": track_id, "toIndex": 1},
            headers={
                "x-tidal-sessionid": self._session.session_id,
                "if-none-match": "*",
            },
        )

    def save_playlist(self, playlist: PlaylistData) -> None:
        playlist_id = self.create_playlist(playlist.name)
        logging.info(f"Save tracks to playlist `{playlist.name}`")
        for track_id in playlist.track_ids:
            self.add_track_to_playlist(track_id, playlist_id)


def transfer_tracks(source_session: tidalapi.Session, target_session: tidalapi.Session) -> None:
    source_loader = SourceLoader(source_session)
    target_saver = TargetSaver(target_session)

    logging.info("Load tracks from source account.")
    for playlist_tracks in source_loader.load_playlist():
        target_saver.save_playlist(playlist_tracks)


if __name__ == '__main__':
    source_session_ = tidalapi.Session()
    target_session_ = tidalapi.Session()
    source_connection_params: dict[str, str] = {
        'token_type': os.environ.get('TIDAL_AUTH_TOKEN_TYPE', 'Bearer'),
        'session_id': os.environ.get('TIDAL_SOURCE_SESSION_ID'),
        'access_token': os.environ.get('TIDAL_SOURCE_ACCESS_TOKEN'),
        'refresh_token': os.environ.get('TIDAL_SOURCE_REFRESH_TOKEN'),
    }
    target_connection_params: dict[str, str] = {
        'token_type': os.environ.get('TIDAL_AUTH_TOKEN_TYPE', 'Bearer'),
        'session_id': os.environ.get('TIDAL_TARGET_SESSION_ID'),
        'access_token': os.environ.get('TIDAL_TARGET_ACCESS_TOKEN'),
        'refresh_token': os.environ.get('TIDAL_TARGET_REFRESH_TOKEN'),
    }
    source_session_.load_oauth_session(**source_connection_params)
    target_session_.load_oauth_session(**target_connection_params)
    transfer_tracks(source_session_, target_session_)

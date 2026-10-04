"""Playlist discovery and single-item safety, without live websites."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mdm import media
from mdm.common import DEFAULTS
from mdm.http_engine import DownloadError

ITEM = {'id': 'item42', 'title': 'Current song', 'webpage_url': 'https://example.org/song',
        'formats': [{'height': 1080, 'vcodec': 'h264', 'acodec': 'aac'},
                    {'height': 720, 'vcodec': 'h264', 'acodec': 'aac'}]}
PLAYLIST = {'_type': 'playlist', 'title': 'Music collection', 'playlist_count': 40, 'entries': [ITEM]}

class Playlists(unittest.TestCase):
    def analyze(self, values):
        with patch.object(media, 'ytdlp_base', return_value=['yt-dlp']), patch.object(media, 'inspect_json', side_effect=values) as inspect:
            result = media.analyze('https://example.org/watch?v=item42&list=music', DEFAULTS)
            return result, inspect.call_args_list
    def test_current_item_and_full_playlist_choices(self):
        data, calls = self.analyze([PLAYLIST, ITEM])
        self.assertEqual(data['playlist']['count'], 40)
        by_id = {c['id']: c for c in data['choices']}
        for choice in ['best', 'audio', 'mp3', 'v:1080', 'playlist:best', 'playlist:audio', 'playlist:mp3', 'playlist:v:1080', 'mp4:best', 'mp4:v:1080', 'playlist:mp4:best', 'playlist:mp4:v:1080']:
            self.assertIn(choice, by_id)
        self.assertEqual(by_id['best']['group'], 'This item only')
        self.assertEqual(by_id['playlist:mp3']['title'], 'Music collection')
        self.assertIn('--flat-playlist', calls[0].args[2])
        self.assertIn('--playlist-items', calls[0].args[2])
        self.assertEqual(calls[0].args[2][-1], '1')
        self.assertIn('--no-playlist', calls[1].args[2])
    def test_pure_playlist_labels_first_item_and_resolves_url(self):
        data, _ = self.analyze([PLAYLIST, PLAYLIST])
        single = data['choices'][0]
        self.assertEqual(single['group'], 'First item only')
        self.assertEqual(single['url'], ITEM['webpage_url'])
        self.assertTrue(data['first_item'])
    def test_single_video_has_no_playlist_modes(self):
        data, _ = self.analyze([ITEM, ITEM])
        self.assertIsNone(data['playlist'])
        self.assertFalse(any(c['id'].startswith('playlist:') for c in data['choices']))
    def test_failed_playlist_probe_keeps_single_video(self):
        data, _ = self.analyze([DownloadError('Private list'), ITEM])
        self.assertIsNone(data['playlist'])
        self.assertTrue(data['warning'])
        self.assertEqual(data['choices'][0]['id'], 'best')
    def test_unavailable_preview_keeps_confirmed_playlist(self):
        data, _ = self.analyze([PLAYLIST, DownloadError('Deleted first item')])
        self.assertTrue(data['warning'])
        self.assertEqual([c['id'] for c in data['choices']], ['playlist:best', 'playlist:mp4:best', 'playlist:audio', 'playlist:mp3'])
    def test_unknown_count_is_not_sample_length(self):
        playlist = {**PLAYLIST, 'playlist_count': None, 'n_entries': 1}
        data, _ = self.analyze([playlist, ITEM])
        self.assertIsNone(data['playlist']['count'])
    def test_single_command_cannot_download_whole_playlist(self):
        task = {'folder': '/tmp/mdm-test', 'quality': 'mp3', 'url': 'https://example.org/list'}
        with patch.object(media, 'ytdlp_base', return_value=['yt-dlp']):
            cmd = media.media_command(task, DEFAULTS)
        self.assertIn('--no-playlist', cmd)
        self.assertEqual(cmd[cmd.index('--playlist-items') + 1], '1')
        self.assertNotIn('--yes-playlist', cmd)
    def test_full_playlist_command_archive_order_and_audio(self):
        task = {'folder': '/tmp/mdm-test', 'quality': 'playlist:mp3', 'url': 'https://example.org/list'}
        with patch.object(media, 'ytdlp_base', return_value=['yt-dlp']):
            cmd = media.media_command(task, DEFAULTS)
        self.assertIn('--yes-playlist', cmd)
        self.assertNotIn('--playlist-items', cmd)
        self.assertNotIn('--ignore-errors', cmd)  # Do not hide incomplete playlists.
        self.assertIn('--no-abort-on-error', cmd)
        self.assertIn('--download-archive', cmd)
        self.assertIn('%(playlist_index)', cmd[cmd.index('--output') + 1])
        self.assertEqual(cmd[cmd.index('--audio-format') + 1], 'mp3')
    def test_mp4_command_keeps_single_or_playlist_scope(self):
        for quality in ('mp4:v:1080', 'playlist:mp4:v:1080'):
            task = {'folder': '/tmp/mdm-test', 'quality': quality, 'url': 'https://example.org/list'}
            with patch.object(media, 'ytdlp_base', return_value=[sys.executable, '-X', 'utf8', '-m', 'yt_dlp', '--ignore-config']):
                cmd = media.media_command(task, DEFAULTS)
            self.assertEqual(Path(cmd[3]).name, 'mp4_engine.py')
            self.assertIn('--ignore-config', cmd)
            self.assertIn('height<=1080', cmd[cmd.index('-f')+1])
            self.assertNotIn('--remux-video', cmd)
            self.assertIn('--yes-playlist' if quality.startswith('playlist:') else '--no-playlist', cmd)

    def test_invalid_modes_rejected(self):
        for choice in ['playlist:', 'playlist:playlist:mp3', 'playlist:--exec=bad', None, 'playlist:v:-2', 'mp4:audio', 'mp4:mp4:best', 'playlist:mp4:--exec=bad']:
            with self.assertRaises(ValueError):
                media.split_choice(choice)
        self.assertEqual(media.split_choice('playlist:v:1080'), (True, 'v:1080'))

if __name__ == '__main__':
    unittest.main(verbosity=2)

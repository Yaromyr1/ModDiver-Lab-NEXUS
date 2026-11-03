"""Audio integration contracts: identity, naming, gains and safe preview behavior."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from audio_backend import AudioBackend


class AudioBackendTests(unittest.TestCase):
    def backend(self):
        b = AudioBackend.__new__(AudioBackend)
        b.labels = {'2': 'Liberator reload'}
        group = {'name': 'Sequence 1', 'stems': [{'slots': [
            {'source': '1', 'label': 'Take 1'},
            {'source': '2', 'label': 'Take 2'},
            {'source': '3', 'label': 'Unavailable cue', 'absent': True}]}]}
        b.session = SimpleNamespace(
            item=Mock(return_value={'name': 'Liberator', 'parts': [{'cue': 'bank:1'}, {'cue': 'bank:2'}]}),
            cue=Mock(return_value={'segments_detail': [group]}))
        return b

    def test_named_rows_keep_stable_source_ids_and_shared_clips_are_not_duplicated(self):
        b = self.backend()
        rows = b.sounds('liberator')
        self.assertEqual([r['source'] for r in rows], ['1', '2', '3'])
        self.assertEqual(rows[0]['name'], 'Sequence 1 · Take 1')
        self.assertEqual(rows[1]['name'], 'Liberator reload')
        self.assertTrue(rows[2]['absent'])
        self.assertEqual(rows[0]['item'], 'liberator')

    def test_gain_routes_to_original_or_replacement_and_rejects_invalid_values(self):
        b = self.backend()
        b.state = Mock(return_value={'assignments': {}})
        b.session.original_gain = Mock()
        b.session.update = Mock()
        b.edit_settings('1', '-3.5', True)
        b.session.original_gain.assert_called_once_with(['1'], -3.5)
        b.state.return_value = {'assignments': {'1': {}}}
        b.edit_settings('1', '2', False)
        b.session.update.assert_called_once_with('1', gain_db=2, fit_timing=False)
        for value in ('nan', 'inf', '-100', 'abc'):
            with self.assertRaises(ValueError): b.edit_settings('1', value, True)

    def test_custom_names_are_saved_without_changing_game_identity(self):
        b = self.backend()
        with tempfile.TemporaryDirectory() as folder:
            b.label_file = Path(folder) / 'names.json'
            b.rename('1', 'Liberator fire')
            self.assertIn('Liberator fire', b.label_file.read_text())
            self.assertEqual(b.sounds('liberator')[0]['source'], '1')
            self.assertEqual(b.sounds('liberator')[0]['name'], 'Liberator fire')

    def test_restore_removes_replacement_and_original_gain(self):
        b = self.backend()
        b.session.unassign = Mock()
        b.session.original_gain = Mock()
        b.restore('1')
        b.session.unassign.assert_called_once_with(['1'])
        b.session.original_gain.assert_called_once_with(['1'], 0)


class AudioSurfaceTests(unittest.TestCase):
    def setUp(self):
        import test_v2_ui
        test_v2_ui.DesktopTests.setUp(self)

    def test_bulk_volume_keeps_selection_and_refuses_unavailable_sounds(self):
        import asset_editor
        from audio_workspace import AudioWorkspace
        from unittest.mock import patch
        with patch.object(AudioWorkspace, 'connect'):
            editor = asset_editor.Editor(self.app)
            audio = editor.audio
            audio.backend = SimpleNamespace(labels={}, session=SimpleNamespace(stage='ready', project=True),
                                            edit_volume_many=Mock())
            audio.rows = [{'source': str(i), 'name': f'Sound {i}', 'group': 'Group'} for i in range(1, 4)]
            with patch.object(audio, 'preview'):
                audio.populate_sounds()
                audio.sounds.selection_set(['1', '2'])
                audio.select_sound()
                self.assertIn('2 sounds selected', audio.selection_note.get())
                audio.gain.set('4.5')
                with patch.object(audio, 'perform', side_effect=lambda title, work, done: work()):
                    audio.apply_gain()
                audio.backend.edit_volume_many.assert_called_once_with(['1', '2'], '4.5')
                audio.populate_sounds()
                self.assertEqual(audio.sounds.selection(), ('1', '2'))
                audio.rows[1]['absent'] = True
                audio.sync_controls()
                self.assertTrue(audio.volume_button.instate(['disabled']))
                audio.backend.edit_volume_many.reset_mock()
                audio.apply_gain()
                audio.backend.edit_volume_many.assert_not_called()
                self.assertIn('not installed', audio.status.get())
            editor.destroy()

    def test_studio_is_one_full_size_frame_and_returns_to_previous_page(self):
        import asset_editor
        from audio_workspace import AudioWorkspace
        from unittest.mock import patch
        import tkinter as tk
        app = self.app
        app._show('tools')
        app.deiconify()
        with patch.object(AudioWorkspace, 'connect'):
            editor = asset_editor.Editor(app)
            app.update()
            self.assertIs(asset_editor.Editor(app), editor)
            self.assertFalse(any(isinstance(w, tk.Toplevel) for w in app.winfo_children()))
            self.assertAlmostEqual(editor.winfo_width(), app.winfo_width(), delta=2)
            self.assertAlmostEqual(editor.winfo_height(), app.winfo_height(), delta=2)
            self.assertEqual(len(editor.tabs.tabs()), 4)
            editor.close()
            app.update()
            self.assertEqual(app.current, 'tools')
            self.assertIsNone(app._choice_screen)
            self.assertIsNone(app._asset_workspace)

    def test_busy_studio_cannot_close_and_cancels_its_timers_after_completion(self):
        import asset_editor
        from audio_workspace import AudioWorkspace
        from unittest.mock import patch
        app = self.app
        with patch.object(AudioWorkspace, 'connect'):
            editor = asset_editor.Editor(app)
            editor.audio.busy = True
            editor.close()
            self.assertTrue(editor.winfo_exists())
            self.assertIn('Wait', editor.audio.status.get())
            editor.audio.busy = False
            editor.close()
            app.update()
            self.assertIsNone(app._asset_workspace)

    def test_collection_navigation_waits_for_worker_and_takes_priority(self):
        import asset_editor
        from audio_workspace import AudioWorkspace
        from unittest.mock import patch
        with patch.object(AudioWorkspace, 'connect'):
            editor = asset_editor.Editor(self.app)
            audio = editor.audio
            audio.busy = True
            audio.select_item()
            audio.select_sound()
            self.assertEqual(audio.pending_navigation, 'item')
            audio.results.put((None, None, None))
            with patch.object(audio, 'select_item') as selected:
                audio.poll()
                selected.assert_called_once()
            self.assertIsNone(audio.pending_navigation)
            editor.destroy()
    def test_playhead_advances_completes_and_stop_resets_without_accumulating_items(self):
        import asset_editor
        from audio_workspace import AudioWorkspace
        from unittest.mock import patch
        with patch.object(AudioWorkspace, 'connect'):
            editor = asset_editor.Editor(self.app)
            audio = editor.audio
            audio.peaks = {'duration_ms': 1200, 'full': 255, 'peaks': [100]*50}
            audio.draw_wave()
            with patch('audio_workspace.time.monotonic', return_value=100):
                audio.start_playback_clock(1.2)
            count = len(audio.wave.find_all())
            with patch('audio_workspace.time.monotonic', return_value=100.3):
                audio.tick_playback()
            self.assertAlmostEqual(audio.play_position, .3)
            self.assertIn('0:00.30', audio.elapsed.get())
            self.assertEqual(len(audio.wave.find_all()), count)
            with patch('audio_workspace.time.monotonic', return_value=104):
                audio.tick_playback()
            self.assertEqual(audio.play_position, 1.2)
            self.assertIsNone(audio.play_started)
            self.assertTrue(audio.stop_button.instate(['disabled']))
            audio.stop()
            self.assertEqual(audio.play_position, 0)
            self.assertIsNone(audio.playback_timer)
            editor.destroy()

    def test_stop_cancels_a_preview_that_has_not_finished_preparing(self):
        import asset_editor
        from audio_workspace import AudioWorkspace
        from unittest.mock import patch
        from pathlib import Path
        with patch.object(AudioWorkspace, 'connect'):
            editor = asset_editor.Editor(self.app)
            audio = editor.audio
            callbacks = []
            with patch.object(audio, 'current', return_value={'source': '1'}), patch.object(audio, 'perform', side_effect=lambda title, work, done: callbacks.append(done)):
                audio.preview('original', True)
            audio.stop()
            callbacks[0]((Path('not-played.wav'), {'duration_ms': 1200, 'full': 255, 'peaks': [100]}))
            self.assertIsNone(audio.play_started)
            self.assertIsNone(audio.peaks)
            editor.destroy()

    def test_tools_and_creator_are_separate_and_actions_have_consistent_colors(self):
        app = self.app
        def texts(widget):
            out = []
            for child in widget.winfo_children():
                if 'text' in child.keys(): out.append(str(child.cget('text')))
                out.extend(texts(child))
            return out
        creator = texts(app.pages['creator'])
        tools = texts(app.pages['tools'])
        self.assertIn('Open Audio & Visual Studio', creator)
        self.assertIn('Open Native Data Editor', creator)
        self.assertNotIn('Open Audio & Visual Studio', tools)
        self.assertNotIn('OPEN NATIVE EDITOR', tools)
        self.assertIn('TOOLS', app.nav_buttons['tools'].cget('text'))
        self.assertIn('MOD CREATOR', app.nav_buttons['creator'].cget('text'))
        app._show('creator'); self.assertEqual(app.title_label.cget('text'), 'Mod Creator')
        app._show('tools'); self.assertEqual(app.title_label.cget('text'), 'Tools')
        self.assertEqual(app.style.lookup('Action.Primary.TButton', 'background'), '#ffd400')
        self.assertEqual(app.style.lookup('Action.Export.TButton', 'background'), '#247848')
        self.assertEqual(app.style.lookup('Action.Danger.TButton', 'background'), '#b83242')
    def test_audio_toolbar_wraps_at_small_window_widths(self):
        import asset_editor
        from audio_workspace import AudioWorkspace
        from unittest.mock import patch
        app = self.app
        app.deiconify()
        app.attributes('-fullscreen', False)
        app.state('normal')
        app.minsize(800, 640)
        app.geometry('980x720+32000+32000')
        with patch.object(AudioWorkspace, 'connect'):
            editor = asset_editor.Editor(app)
            app.update()
            audio = editor.audio
            toolbar = audio.new_button.master
            self.assertTrue(toolbar._compact)
            for button in (audio.new_button, audio.build_button, audio.undo_button, audio.redo_button):
                self.assertGreater(button.winfo_width(), 30)
                self.assertGreaterEqual(button.winfo_x(), 0)
                self.assertLessEqual(button.winfo_x()+button.winfo_width(), toolbar.winfo_width()+1)
            self.assertFalse(audio.more.winfo_manager())
            audio.toggle_more(); self.assertEqual(audio.more.winfo_manager(), 'pack')
            audio.toggle_more(); self.assertFalse(audio.more.winfo_manager())
            editor.destroy()

"""Language catalogs and native UI language-selection regressions."""
import ast
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import core
import localization
import nexus_mode
import yao_forge


class TranslationTests(unittest.TestCase):
    def tearDown(self):
        localization.set_language('en')

    def test_catalogs_cover_all_literal_translation_calls(self):
        keys = set()
        for path in Path(localization.__file__).parent.glob('*.py'):
            tree = ast.parse(path.read_text(encoding='utf-8-sig'))
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id == 'tr' and node.args
                        and isinstance(node.args[0], ast.Constant)
                        and isinstance(node.args[0].value, str)):
                    text = node.args[0].value
                    if any(char.isalpha() for char in text):
                        keys.add(text)
        for language, catalog in [('zh-CN', localization.ZH), ('ru', localization.RU)]:
            with self.subTest(language=language):
                self.assertFalse(keys - catalog.keys(), sorted(keys - catalog.keys()))
                self.assertTrue(all(isinstance(value, str) and value.strip() for value in catalog.values()))
        self.assertEqual(localization.ZH.keys(), localization.RU.keys())
        from string import Formatter
        def fields(text):
            return {name for _, name, _, _ in Formatter().parse(text) if name is not None}
        for catalog in (localization.ZH, localization.RU):
            for key, value in catalog.items():
                self.assertEqual(fields(key), fields(value), key)

    def test_guides_use_selected_language_and_translate_notices(self):
        import about_content
        for language, word in [('zh-CN', '版本'), ('ru', 'Версия')]:
            with self.subTest(language=language), patch.object(nexus_mode, 'NEXUS_BUILD', True):
                localization.set_language(language)
                blocks = about_content.blocks('2.3.4', language)
                self.assertIn(word, blocks[1][0])
                content = ''.join(text for text, _ in blocks)
                self.assertNotIn(nexus_mode.NEXUS_NOTICE, content)
                self.assertNotIn(about_content.MULTIPLAYER_WARNING, content)
                if language == 'ru':
                    self.assertIn('• KNOT - ModDiver Laboratory', content)

    def test_dynamic_labels_and_unknown_values(self):
        for language in ('en', 'zh-CN', 'ru'):
            localization.set_language(language)
            self.assertEqual(localization.tr(None), None)
            self.assertEqual(localization.tr('user-mod-123'), 'user-mod-123')
            self.assertEqual(localization.tr('C:/my mods/chef.zip'), 'C:/my mods/chef.zip')
            for label in ('12 mods', 'LOADERS  (3)', '· DEPLOYED 4', '02  /  BUILT-IN MOD'):
                result = localization.tr(label)
                self.assertEqual(result == label, language == 'en')
        localization.set_language('invalid')
        self.assertEqual(localization.language(), 'en')

    def test_nexus_pages_start_in_each_language_and_preserve_chef(self):
        for language in localization.LANGUAGES:
            with self.subTest(language=language), tempfile.TemporaryDirectory() as folder:
                chef = {'name': 'Chef Shared Loader 1.5.0', 'path': folder,
                        'type': 'arsenal', 'targets': [], 'enabled': True, 'category': 'loaders'}
                cfg = {'game': folder, 'mods': [chef], 'theme': dict(core.DEFAULT_THEME),
                       'language': language, 'check_updates_on_start': False, 'nomofomo': False}
                with patch.object(core, 'load_config', return_value=cfg), patch.object(core, 'save_config'), \
                     patch.object(nexus_mode, 'NEXUS_BUILD', True):
                    app = yao_forge.App()
                    try:
                        app.withdraw()
                        for timer in app.tk.call('after', 'info'):
                            app.after_cancel(timer)
                        self.assertIn(chef, app.cfg['mods'])
                        self.assertEqual(app.language_choice.get(), localization.LANGUAGES[language])
                        self.assertEqual(app.btn_presets.cget('text'), localization.tr('Mod Presets'))
                        self.assertEqual(app.btn_preview.cget('text'), localization.tr('Preview Deployment'))
                        texts = []
                        def visit(widget):
                            try: texts.append(str(widget.cget('text')))
                            except Exception: pass
                            for child in widget.winfo_children(): visit(child)
                        visit(app.pages['creator'])
                        self.assertIn(localization.tr('Open Audio Studio'), texts)
                        self.assertIn(localization.tr('Open Native Data Editor'), texts)
                        import asset_editor
                        from audio_workspace import AudioWorkspace
                        with patch.object(AudioWorkspace, 'connect'):
                            editor = asset_editor.Editor(app)
                            self.assertEqual(editor.audio.new_button.cget('text'), localization.tr('New audio mod'))
                            self.assertEqual(editor.audio.original_button.cget('text'), localization.tr('Play original'))
                            self.assertEqual(editor.audio.status.get(), localization.tr('Finding your game. Audio is read from your own installation.'))
                            editor.close()
                    finally:
                        app.destroy()

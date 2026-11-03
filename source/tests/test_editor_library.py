import copy
import ctypes
import json
import os
import re
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

import core
import moddiver_editor as editor


class EditorLibraryTests(unittest.TestCase):
    def test_session_progress_counts_validated_files_and_does_not_modify_game(self):
        reports = []
        before = {p: p.read_bytes() for p in self.game.rglob('*') if p.is_file()}
        session = editor.new_session(self.cfg, lambda *args: reports.append(args))
        self.assertEqual([(done, total) for _, done, total in reports], [(0, 1), (1, 1)])
        self.assertEqual((session / 'baseline' / self.name).read_bytes(), self.clean)
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.game = self.root / 'game'
        data = self.game / 'data/game'
        data.mkdir(parents=True)
        (data / 'game.dll').write_bytes(b'test game build')
        self.stock = self.root / 'stock'
        self.stock.mkdir()
        self.name = 'generated_test.dl_bin'
        self.clean = core.seal(b'clean baseline' * 8)
        (self.stock / self.name).write_bytes(self.clean)
        (data / self.name).write_bytes(core.seal(b'existing third party mod' * 8))
        self.cfg = {'game': str(self.game), 'mods': [], 'build': 123}
        p = patch.multiple(core, APP_DATA=self.root / 'app', STOCK=self.stock,
                           MODS_DIR=self.root / 'mods', CONFIG=self.root / 'app/config.json',
                           DEPLOYED=self.root / 'deployed.json', BACKUPS=self.root / 'backups')
        p.start()
        self.addCleanup(p.stop)
        self.session = editor.new_session(self.cfg)

    def revision(self, number, files=None):
        folder = self.session / 'output' / str(number)
        folder.mkdir(parents=True)
        if files is None:
            files = {'data/game/' + self.name: core.seal(b'editor change' * 8)}
        lines = ['MODDIVER_EDITOR_1']
        for name, blob in files.items():
            path = folder / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(blob)
            lines.append(name + '\t' + str(len(blob)))
        (folder / 'ready.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
        return folder

    def test_exports_update_one_entry_preserve_settings_and_never_touch_game(self):
        before = {p.relative_to(self.game): p.read_bytes() for p in self.game.rglob('*') if p.is_file()}
        self.assertEqual((self.session / 'baseline' / self.name).read_bytes(), self.clean)
        self.revision(1)
        with patch.object(core, 'deploy', side_effect=AssertionError('must not deploy')):
            self.assertEqual(editor.collect_exports(self.cfg), 1)
            entry = self.cfg['mods'][0]
            entry.update(enabled=False, name='My project', category='visual', selected={'Extra': False})
            self.cfg['mods'].insert(0, {'name': 'Other mod', 'path': 'other', 'enabled': True})
            self.revision(2, {})  # Resetting all settings removes obsolete payloads.
            self.assertEqual(editor.collect_exports(self.cfg), 1)
        self.assertEqual(len(self.cfg['mods']), 2)
        entry = self.cfg['mods'][1]
        self.assertFalse(entry['enabled'])
        self.assertEqual(entry['name'], 'My project')
        self.assertEqual(entry['category'], 'visual')
        self.assertEqual(entry['selected'], {'Extra': False})
        self.assertTrue(entry['editor_pending_deployment'])
        with zipfile.ZipFile(entry['path']) as package:
            self.assertEqual(package.namelist(), ['manifest.json'])
        self.assertEqual(before, {p.relative_to(self.game): p.read_bytes() for p in self.game.rglob('*') if p.is_file()})
        self.assertEqual(editor.collect_exports(self.cfg), 0)

    def test_failed_export_keeps_previous_zip_and_config(self):
        editor.publish_revision(self.cfg, self.session, self.revision(1))
        previous_cfg = copy.deepcopy(self.cfg)
        package = Path(self.cfg['mods'][0]['path'])
        previous_zip = package.read_bytes()
        bad = self.revision(2, {'data/game/' + self.name: b'truncated'})
        with self.assertRaises(ValueError):
            editor.publish_revision(self.cfg, self.session, bad)
        with patch.object(core, 'save_config', side_effect=OSError('disk full')):
            with self.assertRaisesRegex(OSError, 'disk full'):
                editor.publish_revision(self.cfg, self.session, self.revision(3))
        self.assertEqual(self.cfg, previous_cfg)
        self.assertEqual(package.read_bytes(), previous_zip)

    def test_pending_builds_recovered_once_and_partial_builds_ignored(self):
        partial = self.session / 'output/1'
        partial.mkdir()
        (partial / 'data.tmp').write_bytes(b'unfinished')
        self.revision(2)
        self.assertEqual(editor.collect_exports(self.cfg), 1)
        cfg_after_restart = json.loads(core.CONFIG.read_text(encoding='utf-8'))
        (self.session / 'output/2/handled').unlink()
        self.assertEqual(editor.collect_exports(cfg_after_restart), 0)
        self.assertEqual(len(cfg_after_restart['mods']), 1)

    def test_rejects_stale_stock_and_game_build(self):
        revision = self.revision(1)
        (self.stock / self.name).write_bytes(core.seal(b'new stock'))
        with self.assertRaisesRegex(ValueError, 'baseline changed'):
            editor.publish_revision(self.cfg, self.session, revision)
        (self.stock / self.name).write_bytes(self.clean)
        (self.game / 'data/game/game.dll').write_bytes(b'new game build')
        with self.assertRaisesRegex(ValueError, 'installation changed'):
            editor.publish_revision(self.cfg, self.session, revision)
        self.assertEqual(self.cfg['mods'], [])

    def test_rejects_unknown_targets_corrupt_crypto_and_incomplete_archives(self):
        for index, payload in enumerate(({'data/game/generated_unknown.dl_bin': self.clean},
                {'data/game/' + self.name: b'x' * 80}, {'data/9ba626afa44a3aa3.patch_0': b'\x11\0\0\xf0'},
                {'data/9ba626afa44a3aa3.patch_0.stream': b''}, {'data/game.dll': b'bad'}), 1):
            with self.subTest(index=index), self.assertRaises(ValueError):
                editor.publish_revision(self.cfg, self.session, self.revision(index, payload))
        unsafe = self.revision(6, {})
        (unsafe / 'ready.txt').write_text('MODDIVER_EDITOR_1\n../../escape\t10\n')
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            editor.publish_revision(self.cfg, self.session, unsafe)

    def test_complete_optional_resources_import_as_library_files(self):
        base = 'data/9ba626afa44a3aa3.patch_0'
        files = {base: b'\x11\0\0\xf0' + b'fixture', base + '.stream': b'', base + '.gpu_resources': b''}
        entry = editor.publish_revision(self.cfg, self.session, self.revision(1, files))
        parsed = core.parse_mod(entry['path'])
        self.assertEqual(len(parsed['files']), 3)

    def test_export_merges_with_other_library_mod_and_disable_removes_only_editor_changes(self):
        self.cfg['nomofomo'] = False
        stock = core.unseal(self.clean)
        edited, other = bytearray(stock), bytearray(stock)
        edited[0], other[30] = 1, 2
        base = 'data/9ba626afa44a3aa3.patch_0'
        payload = {'data/game/' + self.name: core.seal(bytes(edited)),
                   base: b'\x11\0\0\xf0fixture', base + '.stream': b'', base + '.gpu_resources': b''}
        entry = editor.publish_revision(self.cfg, self.session, self.revision(1, payload))
        other_mod = self.root / 'other'
        other_mod.mkdir()
        (other_mod / self.name).write_bytes(core.seal(bytes(other)))
        self.cfg['mods'].append({'path': str(other_mod), 'name': 'Other', 'enabled': True})
        target = self.game / 'data/game' / self.name
        target.write_bytes(self.clean)
        with patch('builtin_updater.ensure', return_value={}), \
             patch.object(core, 'correct_and_seal', side_effect=lambda stock, merged, floats: (core.seal(merged), 'fixture')):
            core.deploy(self.cfg, log=lambda _: None, dry_run=True)
            self.assertTrue(entry['editor_pending_deployment'])
            self.assertEqual(target.read_bytes(), self.clean)
            core.deploy(self.cfg, log=lambda _: None)
            merged = core.unseal(target.read_bytes())
            self.assertEqual((merged[0], merged[30]), (1, 2))
            self.assertFalse(entry['editor_pending_deployment'])
            self.assertTrue(list((self.game / 'data').glob('*.patch_*')))
            entry['enabled'] = False
            core.deploy(self.cfg, log=lambda _: None)
        self.assertEqual(core.unseal(target.read_bytes()), bytes(other))
        self.assertFalse(list((self.game / 'data').glob('*.patch_*')))

    def test_empty_export_restores_editor_targets_and_external_changes_stop_cleanup(self):
        self.cfg['nomofomo'] = False
        target = self.game / 'data/game' / self.name
        target.write_bytes(self.clean)
        entry = editor.publish_revision(self.cfg, self.session, self.revision(1))
        with patch('builtin_updater.ensure', return_value={}):
            core.deploy(self.cfg, log=lambda _: None)
            entry['enabled'] = False
            target.write_bytes(b'changed by another tool')
            with self.assertRaisesRegex(RuntimeError, 'changed by another tool'):
                core.deploy(self.cfg, log=lambda _: None)
            self.assertEqual(target.read_bytes(), b'changed by another tool')
            with zipfile.ZipFile(entry['path']) as package:
                target.write_bytes(package.read('data/game/' + self.name))
            editor.publish_revision(self.cfg, self.session, self.revision(2, {}))
            entry['enabled'] = True
            core.deploy(self.cfg, log=lambda _: None)
        self.assertEqual(target.read_bytes(), self.clean)
        self.assertEqual(core.load_deployed(), {})

    def test_invalid_enabled_package_keeps_deployed_output_and_pending_status(self):
        self.cfg['nomofomo'] = False
        entry = editor.publish_revision(self.cfg, self.session, self.revision(1))
        with patch('builtin_updater.ensure', return_value={}):
            core.deploy(self.cfg, log=lambda _: None)
            target = self.game / 'data/game' / self.name
            deployed = target.read_bytes()
            entry['editor_pending_deployment'] = True
            Path(entry['path']).write_bytes(b'incomplete package')
            messages = []
            core.deploy(self.cfg, log=messages.append)
            self.assertEqual(target.read_bytes(), deployed)
            self.assertTrue(entry['editor_pending_deployment'])
            self.assertTrue(any('package is missing or invalid' in message for message in messages))

    def test_launch_passes_isolated_export_paths_and_rejects_second_editor(self):
        with patch.object(editor, 'prepare', return_value=self.root), \
             patch.object(editor, '_process', None), \
             patch.object(editor.subprocess, 'Popen') as launch, \
             patch.object(editor.sys, 'platform', 'win32'):
            launch.return_value.poll.return_value = None
            editor.launch(cfg=self.cfg)
            env = launch.call_args.kwargs['env']
            self.assertEqual(env['MODDIVER_GAME_PATH'], str(self.game.resolve()))
            self.assertTrue(Path(env['MODDIVER_EDITOR_BASELINE'], self.name).is_file())
            self.assertTrue(Path(env['MODDIVER_EDITOR_OUTPUT']).is_dir())
            with self.assertRaisesRegex(ValueError, 'already open'):
                editor.launch(cfg=self.cfg)
            self.assertEqual(launch.call_count, 1)

    def test_ui_import_uses_background_task_and_waits_for_other_library_work(self):
        import yao_forge
        app = Mock(busy=False, _startup_automation_running=False, cfg=self.cfg)
        app._task.side_effect = lambda work, done: (work(), done())
        with patch.object(editor, 'pending_exports', return_value=iter([(self.session, self.session)])), \
             patch.object(editor, 'collect_exports', return_value=1) as collect:
            yao_forge.App._poll_editor_exports(app)
            collect.assert_called_once_with(self.cfg, app.log)
            app.refresh_mods.assert_called_once()
            app.after.assert_called_once_with(1000, app._poll_editor_exports)
        app.busy = True
        with patch.object(editor, 'pending_exports') as pending:
            yao_forge.App._poll_editor_exports(app)
            pending.assert_not_called()

    def test_settings_worker_handoff_waits_for_verified_import_before_library_return(self):
        request = self.session / 'requests/1'
        settings = request / 'project/ModDiver/StatEditor'
        settings.mkdir(parents=True)
        (settings / 'config.txt').write_text('changes on\n')
        (request / 'request.txt').write_text('MODDIVER_EDITOR_REQUEST_1\nreturn-to-library\n')
        def finish(timeout=None):
            self.revision(1)
            return 0
        child = Mock()
        child.wait.side_effect = finish
        child.__enter__ = Mock(return_value=child)
        child.__exit__ = Mock(return_value=False)
        runtime = core.APP_DATA / 'editors/moddiver'
        runtime.mkdir(parents=True)
        with patch.object(editor.subprocess, 'Popen', return_value=child) as launch:
            self.assertEqual(editor.collect_exports(self.cfg), 1)
        env = launch.call_args.kwargs['env']
        self.assertEqual(env['MODDIVER_EDITOR_WORKER'], '1')
        self.assertEqual(Path(env['MODDIVER_EDITOR_PROJECT']), request / 'project')
        self.assertEqual(env['MODDIVER_EDITOR_REVISION'], '1')
        self.assertIn('Library updated', (self.session / 'output/status.txt').read_text())
        self.assertTrue(editor.take_library_return())
        self.assertFalse(editor.take_library_return())
        self.assertFalse(list(editor.pending_work()))

    def test_worker_failure_does_not_close_editor_or_replace_library(self):
        request = self.session / 'requests/1'
        settings = request / 'project/ModDiver/StatEditor'
        settings.mkdir(parents=True)
        (settings / 'config.txt').write_text('changes on\n')
        (request / 'request.txt').write_text('MODDIVER_EDITOR_REQUEST_1\nreturn-to-library\n')
        child = Mock()
        child.wait.return_value = 1
        child.__enter__ = Mock(return_value=child)
        child.__exit__ = Mock(return_value=False)
        with patch.object(editor.subprocess, 'Popen', return_value=child):
            self.assertEqual(editor.collect_exports(self.cfg), 0)
        self.assertEqual(self.cfg['mods'], [])
        self.assertIn('failed', (self.session / 'output/status.txt').read_text())
        self.assertFalse(editor.take_library_return())

    def test_bundled_host_has_only_library_actions_and_compiles(self):
        folder = editor.prepare()
        host = (folder / 'app/host.lua').read_text(encoding='utf-8')
        self.assertNotIn('I.write_files(', host)
        self.assertNotIn('I.write_patch(', host)
        self.assertNotIn('S.sync(', host)
        self.assertNotIn('FP.sync(', host)
        self.assertIn('auto_export()', host)
        self.assertIn("label = 'Update library'", host)
        self.assertIn('MODDIVER_EDITOR_OUTPUT', (folder / 'moddiver-linux.py').read_text())
        compile((folder / 'moddiver-linux.py').read_text(), 'launcher', 'exec')
        if os.name == 'nt':
            lua = ctypes.CDLL(str(folder / 'lua51.dll'))
            lua.luaL_newstate.restype = ctypes.c_void_p
            lua.luaL_openlibs.argtypes = [ctypes.c_void_p]
            lua.luaL_loadstring.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
            lua.lua_pcall.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int]
            lua.luaL_loadfile.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
            lua.lua_tolstring.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
            lua.lua_tolstring.restype = ctypes.c_char_p
            lua.lua_close.argtypes = [ctypes.c_void_p]
            state = lua.luaL_newstate()
            try:
                lua.luaL_openlibs(state)
                for name in ('host.lua', 'library_bridge.lua', 'library_loading.lua', 'library_build_progress.lua', 'library_performance.lua',
                             'shodan_core/hostdata.lua', 'forge_helper/app/host.lua', 'community_first_person.lua'):
                    result = lua.luaL_loadfile(state, str(folder / 'app' / name).encode())
                    self.assertEqual(result, 0, lua.lua_tolstring(state, -1, None) if result else name)
                script = "package.path=" + json.dumps((folder / 'app/?.lua').as_posix()) + "..';'..package.path; assert(require('community_hostdata')); local f=assert(io.open(" + json.dumps((folder / 'app/shodan_core/stat_editor.lua').as_posix()) + ", 'rb')); local source=f:read('*a'); f:close(); assert(loadstring(require('moddiver_ui').patch(require('community_statpatch').patch(source))))"
                result = lua.luaL_loadstring(state, script.encode())
                if result == 0:
                    result = lua.lua_pcall(state, 0, 0, 0)
                self.assertEqual(result, 0, lua.lua_tolstring(state, -1, None) if result else '')
            finally:
                lua.lua_close(state)
                import _ctypes
                _ctypes.FreeLibrary(lua._handle)

    @unittest.skipUnless(os.name == 'nt', 'Bundled LuaJIT Windows runtime')
    def test_lua_automatic_build_exports_full_snapshot_and_blocks_game_writes(self):
        folder = editor.prepare()
        out = self.session / 'output'
        for number in (1, 2, 3):
            (out / str(number) / 'data/game').mkdir(parents=True)
        changed = self.root / 'changed.bin'
        changed.write_bytes(core.seal(b'edited data' * 8))
        def literal(path):
            return json.dumps(str(path).replace('\\', '/'))
        script = """
local ffi = require('ffi')
ffi.cdef('int MoveFileExA(const char *, const char *, uint32_t);')
local locations = {MODDIVER_EDITOR_BASELINE=BASELINE, MODDIVER_EDITOR_OUTPUT=OUTPUT}
os.getenv = function(key) return locations[key] end
local Library = dofile(BRIDGE)
local function read(path)
    local f = io.open(path, 'rb'); if not f then return nil end
    local bytes = f:read('*a'); f:close(); return bytes
end
local I = {read=read, mkdirs=function() end, list_files=function() return {'generated_test.dl_bin'} end}
local S = {source=function() return {main=string.char(17,0,0,240)..'steering', gpu='', stream=''} end}
local FP = {enabled=function() return true end, library_payload=function()
    return {{string.char(17,0,0,240)..'boot','',''}, {string.char(17,0,0,240)..'camera','',''}} end}
local G = {open_sealed=function() return 'plain', 5 end, game_dll_has=function() return true end,
    murmur64=function() return 1 end, clear_correction=function() return false end, free=function() end}
package.loaded.gamedata = G
Library.attach(I, S, FP)
local originals, ours, problems, count = I.originals(GAME)
assert(count == 1 and originals['generated_test.dl_bin'] == read(BASELINE..'/generated_test.dl_bin'))
assert(not pcall(I.write_files)); assert(not pcall(I.write_patch)); assert(not pcall(S.sync)); assert(not pcall(FP.sync))
package.loaded.hellpod = {settings=function() return {map_steering=true} end}
local state = {phase='ready', writes=1}
local C = {signatures=function() return 'f','v','h' end, flush=function() end, reload=function() end,
    diff=function() return {{name='generated_test.dl_bin'}} end}
local D = {codes=function() return true end, build=function() return read(CHANGED) end}
local V = {BASE='9ba626afa44a3aa3'}
local now = 0
local function clock() return now end
local function busy() end
local function say() end
local function log() end
local WARN, GOOD, MUTED = 1,2,3
local shim = {pump=function() end, key_down=function() return false end}
local bar = {}
ACTION_SOURCE
local requests, saves = 0, 0
state.flush_config = function() saves=saves+1; return true end
Library.request = function(I, finish) requests=requests+1; return requests end
local read_status = Library.status
Library.status = function() return nil end
auto_export()
assert(requests==0)
now=2
auto_export()
assert(requests==1 and saves==1)
assert(not read(OUTPUT..'/1/ready.txt')) -- The interactive process never builds.
install(true)
assert(finish_requested and saves==2)
assert(not install(true) and saves==2)
Library.status=function() return 'Library export failed' end
auto_export()
assert(not finish_requested and not exit_requested)
restore()
assert(removal_open)
removal_open=false
restore()
assert(removal_open) -- The popup opens on every click.
removal_open=false
install(true)
Library.status=function() return 'Library updated' end
auto_export()
assert(exit_requested)
exit_requested=false
Library.worker=true
assert(build())
assert(read(OUTPUT..'/1/ready.txt'))
D.codes=function() return nil, 'invalid edit' end
assert(not build())
assert(not read(OUTPUT..'/2/ready.txt'))
D.codes=function() return true end
assert(build())
assert(read(OUTPUT..'/2/ready.txt'))
closing=true
busy=function() error('Cannot paint after the window closes') end
shim.pump=function() error('Cannot pump after the window closes') end
D.build=function(c,progress) progress('final export'); return read(CHANGED) end
last_built=nil
auto_export()
assert(exit_requested and read(OUTPUT..'/3/ready.txt'))

"""
        for key, value in {'BASELINE': self.session / 'baseline', 'OUTPUT': out,
                           'BRIDGE': editor.BRIDGE / 'bridge.lua', 'CHANGED': changed,
                           'GAME': self.game / 'data/game'}.items():
            script = re.sub(r'(?<![A-Z_])' + key + r'\b', lambda _: literal(value), script)
        script = script.replace('ACTION_SOURCE', (editor.BRIDGE / 'actions.lua').read_text(encoding='utf-8'))
        lua = ctypes.CDLL(str(folder / 'lua51.dll'))
        lua.luaL_newstate.restype = ctypes.c_void_p
        lua.luaL_openlibs.argtypes = [ctypes.c_void_p]
        lua.luaL_loadstring.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        lua.lua_pcall.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int]
        lua.lua_tolstring.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        lua.lua_tolstring.restype = ctypes.c_char_p
        lua.lua_close.argtypes = [ctypes.c_void_p]
        state = lua.luaL_newstate()
        try:
            lua.luaL_openlibs(state)
            result = lua.luaL_loadstring(state, script.encode())
            if result == 0:
                result = lua.lua_pcall(state, 0, 0, 0)
            self.assertEqual(result, 0, lua.lua_tolstring(state, -1, None) if result else '')
        finally:
            lua.lua_close(state)
            import _ctypes
            _ctypes.FreeLibrary(lua._handle)
        self.assertEqual(editor.collect_exports(self.cfg), 3)
        with zipfile.ZipFile(self.cfg['mods'][0]['path']) as package:
            self.assertEqual(len(package.namelist()), 11)  # manifest, data, three archive triplets


if __name__ == '__main__':
    unittest.main()

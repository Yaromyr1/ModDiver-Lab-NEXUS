"""Exercise actual bundled Lua rendering with isolated editor settings."""
import ctypes
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import core
import moddiver_editor


@unittest.skipUnless(os.name == 'nt', 'Bundled Windows LuaJIT')
class RuntimeTests(unittest.TestCase):
    def test_worker_progress_is_revision_scoped_and_clears_after_success_or_failure(self):
        self.run_lua(r'''
local ffi=require('ffi')
local I=require('install')
local original=os.getenv
local root=original('LOCALAPPDATA'):gsub('\\','/')
local output=root..'/output'
local target='1'
os.getenv=function(key)
 if key=='MODDIVER_EDITOR_BASELINE' then return root end
 if key=='MODDIVER_EDITOR_OUTPUT' then return output end
 if key=='MODDIVER_EDITOR_WORKER' then return '0' end
 if key=='MODDIVER_EDITOR_REVISION' then return target end
 return original(key)
end
I.mkdirs(I.home); I.mkdirs(output)
local config=assert(io.open(I.home..'/config.txt','wb')); config:write('saved'); config:close()
local Library=require('library_bridge')
local tick=1; os.time=function() return tick end
assert(Library.request(I,true)==1)
assert(Library.build_progress(I).phase=='Preparing your saved edits')
Library.worker=true; Library.report('Encrypting and verifying mod files',2,4); Library.worker=false
tick=2
local progress=Library.build_progress(I)
assert(progress.done==2 and progress.total==4)
target='0'; Library.worker=true; Library.report('Stale result',1,1); Library.worker=false
tick=3
assert(Library.build_progress(I).phase=='Encrypting and verifying mod files')
local function status(text)
 local f=assert(io.open(output..'/status.txt','wb')); f:write(text); f:close()
end
status('1\nLibrary updated'); Library.status(I)
assert(not Library.build_progress(I))
assert(Library.request(I,false)==2)
status('2\nLibrary export failed'); tick=4; Library.status(I)
assert(not Library.build_progress(I))
''')

    def test_build_progress_panel_shows_measured_percentage_and_unknown_stage(self):
        self.run_lua(r'''
local labels={}
local shim={w=1000,h=700, fill=function() end, flush=function() end,
 text=function(text) labels[#labels+1]=text end}
local panel=require('library_build_progress')
panel.paint(shim,{phase='Encrypting mod files',done=2,total=4},true,1)
assert(labels[1]=='Creating your mod')
assert(labels[3]=='50% of this stage   ·   2 / 4 files')
panel.paint(shim,{phase='Preparing gameplay changes',done=0,total=0},false,2)
assert(labels[7]=='Working in the background')
assert(labels[8]=='You can keep editing. Your game files are unchanged.')
''')

    def run_lua(self, script):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(core, 'APP_DATA', root):
                folder = moddiver_editor.prepare()
            script = ('package.path=' + json.dumps((folder/'app/?.lua').as_posix()) +
                      "..';'..package.path\n" + script)
            with patch.dict(os.environ, {'MODDIVER_EDITOR_WORKER': '1', 'LOCALAPPDATA': str(root)}):
                lua = ctypes.CDLL(str(folder/'lua51.dll'))
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
                    status = lua.luaL_loadstring(state, script.encode())
                    if not status:
                        status = lua.lua_pcall(state, 0, 0, 0)
                    self.assertEqual(status, 0, lua.lua_tolstring(state, -1, None) if status else '')
                finally:
                    lua.lua_close(state)
                    import _ctypes
                    _ctypes.FreeLibrary(lua._handle)

    def test_loading_uses_real_counts_hides_worker_and_obeys_window_close(self):
        self.run_lua(r'''
local labels, frames = {}, 0
local shim={w=1000,h=700, pump=function() return true end, fill=function() end,
 text=function(text) labels[#labels+1]=text end, present=function() frames=frames+1 end}
local loading=require('library_loading').attach(shim,false)
loading.show('Reading',0,2)
loading.show('Reading',2,2)
assert(labels[3]=='0%   ·   0 / 2 files')
assert(labels[6]=='100%   ·   2 / 2 files')
loading.show('Finding stats',nil,nil)
assert(labels[9]=='Please wait')
require('library_loading').attach(shim,true).show('Hidden',0,1)
assert(frames==3)
shim.pump=function() return false end
assert(not pcall(loading.show,'Closed',0,1))
''')

    def test_optimized_fills_preserve_pixels_for_palette_clipping_and_resize(self):
        self.run_lua(r'''
local ffi=require('ffi')
local shim=require('engine_shim')
local style=require('moddiver_style')
shim.open('Render verification',{0,0,640,480})
local original=shim.fill
local function draw()
 shim.fill(0,0,shim.w,shim.h,{255,32,32,32})
 for _,c in ipairs({{255,255,213,0},{255,210,40,40},{255,120,130,180},{140,255,213,0}}) do
  shim.fill(-10,10,240,50,c)
  shim.fill(200,60,900,80,c)
  shim.fill(40,100,80,100,c)
 end
end
draw(); shim.flush()
local expected=ffi.string(shim.bits,shim.w*shim.h*4)
require('library_performance').attach(shim,style)
draw(); shim.flush()
assert(expected==ffi.string(shim.bits,shim.w*shim.h*4),'Rendered pixels changed')
-- Attachment is idempotent and bounded caches tolerate a different width.
local optimized=shim.fill
require('library_performance').attach(shim,style)
assert(shim.fill==optimized)
ffi.cdef('int DestroyWindow(void *);')
ffi.load('user32').DestroyWindow(shim.window)
''')

    def test_forge_skips_idle_redraws_and_repaints_on_invalidation(self):
        self.run_lua(r'''
local ffi=require('ffi')
local shim=require('engine_shim')
local original_pump, original_present=shim.pump,shim.present
local frames, paints, failure=0,0,nil
shim.pump=function()
 frames=frames+1
 if frames==5 then shim.version=shim.version+1 end
 return frames<10 and original_pump()
end
shim.focused=function() return false end
shim.present=function() paints=paints+1; original_present() end
shim.sleep=function() end
shim.message_box=function(text) failure=text end
local here=package.path:match('^(.-)%?%.lua')
dofile(here..'forge_helper/app/host.lua')
assert(not failure,failure)
assert(frames==10,'Forge loop failed')
assert(paints==2,'Forge should paint once, then once on invalidation; got '..paints)
ffi.cdef('int DestroyWindow(void *);')
ffi.load('user32').DestroyWindow(shim.window)
''')

"""Run the SHODAN Lua editor bridge (passives.lua / weapons.lua) through the vendored LuaJIT.

usage: editor_runner.py dump|apply passives|weapons <file> <out> [stock] [edits]
"""
import ctypes
import ctypes.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENDOR = ROOT / "vendor" / "shodan"

def _load_lua():
    candidates = [str(VENDOR / "lua51.dll")] if os.name == "nt" else [
        ctypes.util.find_library("luajit-5.1"), ctypes.util.find_library("luajit"),
        "libluajit-5.1.so.2", "libluajit-5.1.so"]
    for candidate in filter(None, candidates):
        try:
            return ctypes.CDLL(candidate)
        except OSError:
            continue
    raise RuntimeError("LuaJIT is required. On Debian/Ubuntu install it with: sudo apt install luajit")


dll = _load_lua()
dll.luaL_newstate.restype = ctypes.c_void_p
dll.luaL_openlibs.argtypes = [ctypes.c_void_p]
dll.luaL_loadfile.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
dll.luaL_loadfile.restype = ctypes.c_int
dll.lua_pcall.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int]
dll.lua_pcall.restype = ctypes.c_int
dll.lua_tolstring.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_size_t)]
dll.lua_tolstring.restype = ctypes.c_char_p
dll.lua_pushstring.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
dll.lua_setfield.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p]
LUA_GLOBALSINDEX = -10002


def main():
    if len(sys.argv) < 5:
        print("usage: editor_runner.py dump|apply passives|weapons <file> <out> [stock] [edits]")
        return 2
    mode, kind = sys.argv[1], sys.argv[2]
    script = "weapons.lua" if kind == "weapons" else "passives.lua"
    os.environ["YAO_SHODAN_APP"] = str(VENDOR / "app") + os.sep
    L = dll.luaL_newstate()
    dll.luaL_openlibs(L)
    for name, value in (("YAO_MODE", mode), ("YAO_FILE", sys.argv[3]), ("YAO_OUT", sys.argv[4]),
                        ("YAO_STOCK", sys.argv[5] if len(sys.argv) > 5 else ""),
                        ("YAO_EDITS", sys.argv[6] if len(sys.argv) > 6 else "")):
        dll.lua_pushstring(L, str(value).encode())
        dll.lua_setfield(L, LUA_GLOBALSINDEX, name.encode())
    r = dll.luaL_loadfile(L, str(ROOT / script).encode())
    if r != 0:
        n = ctypes.c_size_t()
        print("load error:", dll.lua_tolstring(L, -1, ctypes.byref(n)))
        return 1
    r = dll.lua_pcall(L, 0, 0, 0)
    if r != 0:
        n = ctypes.c_size_t()
        print("runtime error:", dll.lua_tolstring(L, -1, ctypes.byref(n)))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

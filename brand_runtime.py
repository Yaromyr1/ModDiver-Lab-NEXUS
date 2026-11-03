"""Brand a local CPython GUI executable without changing interpreter code."""
import ctypes
from ctypes import wintypes
from pathlib import Path
import subprocess
import zipfile


def brand_runtime(runtime_zip, work, csc, icon, version):
    work = Path(work)
    metadata = work / 'runtime_metadata.cs'
    metadata.write_text('''using System.Reflection;
[assembly: AssemblyTitle("ModDiver Lab")]
[assembly: AssemblyDescription("ModDiver Lab")]
[assembly: AssemblyProduct("ModDiver Lab")]
[assembly: AssemblyCompany("ModDiver Laboratory")]
[assembly: AssemblyCopyright("CPython: Python Software Foundation; ModDiver Laboratory: Yao")]
[assembly: AssemblyVersion("__VERSION__")]
class Metadata { static void Main() {} }
'''.replace('__VERSION__', '.'.join((version.split('.') + ['0'] * 4)[:4])), encoding='utf-8')
    stub = work / 'runtime_metadata.exe'
    subprocess.run([str(csc), '/nologo', '/target:winexe', f'/out:{stub}',
                    f'/win32icon:{icon}', str(metadata)], check=True, capture_output=True)
    target = work / 'ModDiver Lab.exe'
    with zipfile.ZipFile(runtime_zip) as archive:
        target.write_bytes(archive.read('pythonw.exe'))

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    ptr = ctypes.c_void_p
    kernel.LoadLibraryExW.argtypes = [wintypes.LPCWSTR, ptr, wintypes.DWORD]
    kernel.LoadLibraryExW.restype = ptr
    kernel.FreeLibrary.argtypes = [ptr]
    kernel.FindResourceExW.argtypes = [ptr, ptr, ptr, wintypes.WORD]
    kernel.FindResourceExW.restype = ptr
    kernel.SizeofResource.argtypes = [ptr, ptr]; kernel.SizeofResource.restype = wintypes.DWORD
    kernel.LoadResource.argtypes = [ptr, ptr]; kernel.LoadResource.restype = ptr
    kernel.LockResource.argtypes = [ptr]; kernel.LockResource.restype = ptr
    name_callback = ctypes.WINFUNCTYPE(wintypes.BOOL, ptr, ptr, ptr, ctypes.c_ssize_t)
    lang_callback = ctypes.WINFUNCTYPE(wintypes.BOOL, ptr, ptr, ptr, wintypes.WORD, ctypes.c_ssize_t)
    kernel.EnumResourceNamesW.argtypes = [ptr, ptr, name_callback, ctypes.c_ssize_t]
    kernel.EnumResourceLanguagesW.argtypes = [ptr, ptr, ptr, lang_callback, ctypes.c_ssize_t]

    def resource_name(value):
        return value if value <= 0xffff else ctypes.wstring_at(value)

    def identifier(value):
        return ptr(value) if isinstance(value, int) else ctypes.cast(ctypes.c_wchar_p(value), ptr)

    def resources(path):
        module = kernel.LoadLibraryExW(str(path), None, 2)
        if not module: raise ctypes.WinError(ctypes.get_last_error())
        result = []
        try:
            for kind in (3, 14, 16):  # RT_ICON, RT_GROUP_ICON, RT_VERSION
                def on_name(module, type_id, name_id, _):
                    def on_language(module, type_id, name_id, lang, _):
                        resource = kernel.FindResourceExW(module, type_id, name_id, lang)
                        size = kernel.SizeofResource(module, resource)
                        data = ctypes.string_at(kernel.LockResource(kernel.LoadResource(module, resource)), size)
                        result.append((kind, resource_name(name_id), lang, data))
                        return True
                    kernel.EnumResourceLanguagesW(module, type_id, name_id, lang_callback(on_language), 0)
                    return True
                kernel.EnumResourceNamesW(module, ptr(kind), name_callback(on_name), 0)
        finally:
            kernel.FreeLibrary(module)
        return result

    original, branded = resources(target), resources(stub)
    if {entry[0] for entry in branded} != {3, 14, 16}:
        raise RuntimeError('The branding resources are incomplete.')
    kernel.BeginUpdateResourceW.argtypes = [wintypes.LPCWSTR, wintypes.BOOL]
    kernel.BeginUpdateResourceW.restype = ptr
    kernel.UpdateResourceW.argtypes = [ptr, ptr, ptr, wintypes.WORD, ptr, wintypes.DWORD]
    kernel.EndUpdateResourceW.argtypes = [ptr, wintypes.BOOL]
    handle = kernel.BeginUpdateResourceW(str(target), False)
    if not handle: raise ctypes.WinError(ctypes.get_last_error())
    try:
        for kind, name, lang, _ in original:
            if not kernel.UpdateResourceW(handle, identifier(kind), identifier(name), lang, None, 0):
                raise ctypes.WinError(ctypes.get_last_error())
        for kind, name, lang, data in branded:
            buffer = ctypes.create_string_buffer(data)
            if not kernel.UpdateResourceW(handle, identifier(kind), identifier(name), lang, buffer, len(data)):
                raise ctypes.WinError(ctypes.get_last_error())
    except BaseException:
        kernel.EndUpdateResourceW(handle, True)
        raise
    if not kernel.EndUpdateResourceW(handle, False):
        raise ctypes.WinError(ctypes.get_last_error())
    if resources(target) != branded:
        # Enumeration order may differ, but resource contents must match exactly.
        if set(resources(target)) != set(branded):
            raise RuntimeError('Runtime branding did not verify.')
    return target

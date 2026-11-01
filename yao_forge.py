"""ModDiver Laboratory - desktop mod toolkit for Helldivers 2 data mods.

Deploy / purge / merge data mods and export a YAO DATA LOADER pack.
"""
import ctypes
import copy
import about_content
import log_events
import base64
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import webbrowser
import zipfile
from tkinter import ttk
from panel_dialogs import colorchooser, filedialog, messagebox, simpledialog, ResultScreen
from pathlib import Path

import core
import actions
import library_io
import library_presets
import gameplay_profiles
import asset_editor
import creator_page
import updater
import chef_updater
import shodan_updater
import decoder_ui
import schema_editor
import single_instance
import localization
import nav_icons
import maintenance
import platform_icons
import window_surface
import ui_polish
import choice_screen
from loading_ui import LoadingBar, LoadingBrand
from report_view import ReportView
from localization import tr

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("YAO.ModForge.1")
except Exception:
    pass

APP_NAME = "ModDiver Laboratory"
VERSION = "2.3.2"

THEMES = {
    "Helldiver": {"bg": "#080808", "panel": "#141414", "panel2": "#222222", "accent": "#ffd400",
                  "accent_text": "#080808", "text": "#ffffff", "muted": "#c4c4c4"},
    "Deep Signal": {"bg": "#10131f", "panel": "#1c2030", "panel2": "#30364b",
                    "accent": "#ff82b2", "accent_text": "#20101a", "text": "#f7edf5", "muted": "#b7b1cc"},
    "Midnight": {"bg": "#0b1020", "panel": "#121a2e", "panel2": "#1a2440", "accent": "#4f8cff",
                 "accent_text": "#0b1020", "text": "#e6ecff", "muted": "#8a93b0"},
    "Light": {"bg": "#eef0f3", "panel": "#ffffff", "panel2": "#e2e6ec", "accent": "#c8102e",
              "accent_text": "#ffffff", "text": "#1b1b1b", "muted": "#5f6672"},
    "High Contrast": {"bg": "#000000", "panel": "#0a0a0a", "panel2": "#161616", "accent": "#ffd400",
                      "accent_text": "#000000", "text": "#ffffff", "muted": "#a0a0a0"},
    "Ember": {"bg": "#140d0a", "panel": "#1e1310", "panel2": "#2a1a15", "accent": "#ff6b35",
              "accent_text": "#140d0a", "text": "#f2e6dd", "muted": "#a08a7c"},
    "Viper Ops": {"bg": "#0b110b", "panel": "#151e14", "panel2": "#253221", "accent": "#b6d04a",
                  "accent_text": "#10150d", "text": "#eef1df", "muted": "#a8b294"},
    "Hellpod Red": {"bg": "#130909", "panel": "#201111", "panel2": "#351b1b", "accent": "#f04438",
                    "accent_text": "#ffffff", "text": "#f7e8e6", "muted": "#c4a6a2"},
    "Bug Spray": {"bg": "#10130a", "panel": "#1b2110", "panel2": "#2c3518", "accent": "#d4e157",
                   "accent_text": "#171a0c", "text": "#f0f2d8", "muted": "#b5ba91"},
    "Automaton Steel": {"bg": "#0b1014", "panel": "#151d23", "panel2": "#25323a", "accent": "#49c6d9",
                         "accent_text": "#081216", "text": "#e2eef0", "muted": "#93a8ad"},
    "Super Earth": {"bg": "#091322", "panel": "#11223a", "panel2": "#1a3558", "accent": "#70b7ff",
                    "accent_text": "#07111e", "text": "#e9f2ff", "muted": "#a2bad5"},
    "Irradiated": {"bg": "#100d18", "panel": "#1c1628", "panel2": "#302342", "accent": "#c084fc",
                   "accent_text": "#160d20", "text": "#f1e9fa", "muted": "#b7a6cc"},
    "Medbay": {"bg": "#0b1515", "panel": "#122222", "panel2": "#1d3635", "accent": "#63e6be",
               "accent_text": "#071411", "text": "#e4f5f0", "muted": "#9cbab1"},
    "Dust Devil": {"bg": "#17110b", "panel": "#241b11", "panel2": "#392a19", "accent": "#e0a458",
                   "accent_text": "#1d140b", "text": "#f5eadb", "muted": "#bba58a"},
    "Eagle-1": {"bg": "#101018", "panel": "#1b1c28", "panel2": "#2a2c3c", "accent": "#ff9f43",
                "accent_text": "#1d1006", "text": "#f4f0e9", "muted": "#b4a99a"},
}
SWATCHES = ["#ffd400", "#ff6b35", "#ff4d4d", "#4f8cff", "#38d996", "#b06bff", "#ffffff", "#c8102e"]

ABOUT_BLOCKS = about_content.blocks(VERSION)


def _loader_family(name):
    value = str(name or "").casefold()
    if "chef" in value and "loader" in value:
        return "chef"
    return None


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.withdraw()
        self.cfg = core.load_config()
        localization.set_language(self.cfg.get('language', 'en'))
        self.theme = dict(self.cfg.get("theme") or core.DEFAULT_THEME)
        legacy_helldiver = (
            {"bg": "#0d0f0c", "panel": "#151a12", "panel2": "#1c2318", "accent": "#f4c542",
             "accent_text": "#151a12", "text": "#e8e6d9", "muted": "#8a8f7a"},
            {"bg": "#11140f", "panel": "#1a2018", "panel2": "#252d21", "accent": "#d6b84b",
             "accent_text": "#171a12", "text": "#ecebdc", "muted": "#a2a58f"},
        )
        if self.theme.get("preset") == "Helldiver" and any(
                all(self.theme.get(k) == v for k, v in old.items()) for old in legacy_helldiver):
            font_size = self.theme.get("font", core.DEFAULT_THEME["font"])
            self.theme = {**core.DEFAULT_THEME, "font": font_size}
            self.cfg["theme"] = dict(self.theme)
        self.title(tr(APP_NAME))
        dpi = self.winfo_fpixels("1i")
        self.tk.call("tk", "scaling", max(1.0, dpi / 72.0))
        scale = max(1.0, dpi / 96.0)
        self.geometry(f"{int(1180 * scale)}x{int(760 * scale)}")
        self.minsize(int(980 * scale), int(640 * scale))
        self.configure(bg=self.theme['bg'])
        self.update_idletasks()
        window_surface.install(self)
        self.attributes('-fullscreen', bool(self.cfg.get('fullscreen_on_maximize', False)))
        window_surface.install(self)
        self.bind('<Escape>', lambda event: self._exit_fullscreen())
        self.bind('<F11>', lambda event: self._set_fullscreen(not self.attributes('-fullscreen')))
        self.bind('<Configure>', self._maximize_to_fullscreen, add='+')
        self.configure(bg=self.theme["bg"])
        try:
            icon = Path(__file__).resolve().parent / 'branding/icon_64.png'
            if icon.exists():
                self._icon = tk.PhotoImage(master=self, file=str(icon))
                self.iconphoto(True, self._icon)
        except Exception:
            pass
        self._loading_tokens = {}
        self._loading_windows = {}
        import dialog_layer
        dialog_layer.install(self)
        self._progress_latest = None
        self._begin_loading('startup')
        self.deiconify()
        self.update_idletasks()
        core.clean_builtins(self.cfg)
        self.style = ttk.Style(self)
        self.style.theme_use("clam")
        self.log_queue = queue.Queue()
        self.texts = []
        self.nav_buttons = {}
        self.nav_button_frames = {}
        self.mod_action_buttons = []
        self.current = "mods"
        self.busy = False
        self.editor_proc = None
        self._update_check_active = False
        self._update_install_active = False
        self._stock_prompt_open = False
        self._stock_verify_started = False
        self._steam_verify_log_path = None
        self._steam_verify_log_offset = 0
        self._steam_verify_started_at = None
        self._steam_verify_phase = None
        self._steam_verify_continuation = None
        self._steam_capture_after_id = None
        self._build()
        self.bind_all("<MouseWheel>", self._scroll_tools, add="+")
        self.bind_all("<Button-4>", self._scroll_tools, add="+")
        self.bind_all("<Button-5>", self._scroll_tools, add="+")
        self.bind_all('<MouseWheel>', self._scroll_settings, add='+')
        self.bind_all('<Button-4>', self._scroll_settings, add='+')
        self.bind_all('<Button-5>', self._scroll_settings, add='+')
        self.bind_all('<Map>', self._style_mapped_widget, add='+')
        self.bind_all('<Enter>', self._clickable_cursor, add='+')
        self.apply_theme()
        self.refresh_status()
        self.after(100, self._drain)
        self.after(200, self._dark_titlebar)
        self.after(800, self._ensure_shortcut)
        self.after(5000, self._automatic_update_check)
        self.after(1800, self._archive_steam_build)
        self.after_idle(self._prompt_for_complete_stock)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after_idle(lambda: self._end_loading('startup'))
        self.after_idle(self._maximize_startup)

    def update_builtin_mods(self):
        if self.busy or self._update_install_active:
            return
        self._show('log')
        import builtin_updater
        if not self.cfg.get('game') or core.hellforge_root(self.cfg) is not None:
            self.log('Select a Helldivers 2 Steam game folder before updating built-in mods.')
            self.log('FAILED TO REPAIR/UPDATE BUILT-IN MODS', 'error')
            return
        if self._stock_verify_started:
            self.log('Steam verification is still being monitored; stock capture will start automatically two seconds after Steam finishes.')
            return
        if not getattr(self, '_builtin_repair_verify_confirmed', False):
            if not messagebox.askyesno(
                    tr('Verify game files before built-in repair'),
                    tr('Steam Verify restores official Helldivers 2 files and removes changes in the game '
                       'folder. Your ModDiver mod library stays intact and can be deployed again afterward. '
                       'Start Steam Verify now? ModDiver will download repair data while Steam works, then '
                       'automatically capture clean stock two seconds after Steam finishes, then repair.'),
                    parent=self._dialog_parent()):
                return
            try:
                self._capture_for_repair = True
                self._steam_verify_continuation = self.update_builtin_mods
                self._begin_steam_verification()
                self._stock_verify_started = True
                self._builtin_repair_verify_confirmed = True
                self.log('Repair data is downloading. Clean stock will be captured automatically two seconds after Steam finishes, then built-in mods will be repaired.')
            except Exception as exc:
                messagebox.showerror(tr(APP_NAME), tr(f'Could not start Steam Verify Integrity:\n\n{exc}'),
                                     parent=self._dialog_parent())
                self._capture_for_repair = False
                self._steam_verify_continuation = None
            return
        def done():
            self.refresh_status()
            result = self._task_result
            self._builtin_repair_verify_confirmed = False
            if isinstance(result, dict) and set(result) == set(builtin_updater.NAMES) and all(isinstance(value, Path) for value in result.values()):
                self.log('BUILT-IN MODS REPAIRED/UPDATED SUCCESSFULLY', 'success')
            else:
                self.log('FAILED TO REPAIR/UPDATE BUILT-IN MODS', 'error')
        self._task(lambda: builtin_updater.run_worker(dict(self.cfg), self.log), done)

    def _confirm_steam_verify_complete(self):
        return messagebox.askyesno(
            tr('Confirm Steam verification is complete'),
            tr('Has Steam finished verifying Helldivers 2 and returned to an idle state? '
               'Do not repair while Steam is still changing game files.'),
            parent=self._dialog_parent())

    def _capture_stock_then(self, continuation):
        def done():
            if self._task_error:
                self._stock_verify_started = False
                self._capture_for_repair = False
                self._steam_verify_continuation = None
                self.attributes('-topmost', False)
                messagebox.showerror(tr(APP_NAME), tr(self._task_error), parent=self._dialog_parent())
                return
            if self._task_result != core.REQUIRED_STOCK_FILES:
                messagebox.showerror(tr(APP_NAME), tr(f'Captured {self._task_result} of 55 clean files. '
                    'Steam verification may still be running; wait until Steam is idle and retry.'),
                    parent=self._dialog_parent())
                self._stock_verify_started = False
                self._capture_for_repair = False
                self._steam_verify_continuation = None
                self.attributes('-topmost', False)
                self.btn_capture.configure(text=tr('STEAM VERIFY + CAPTURE STOCK'))
                return
            try:
                import build_archive
                build_archive.capture_stock_folder(core.game_dir(self.cfg), core.STOCK)
            except Exception as exc:
                self._stock_verify_started = False
                self._capture_for_repair = False
                self._steam_verify_continuation = None
                self.attributes('-topmost', False)
                self.btn_capture.configure(text=tr('STEAM VERIFY + CAPTURE STOCK'))
                messagebox.showerror(tr(APP_NAME), tr(str(exc)), parent=self._dialog_parent())
                return
            self._stock_verify_started = False
            self._capture_for_repair = False
            self.attributes('-topmost', False)
            self.btn_capture.configure(text=tr('STEAM VERIFY + CAPTURE STOCK'))
            if hasattr(self, 'stock_action_status'):
                self.stock_action_status.configure(text=tr('Clean stock captured.'), foreground=self.theme['accent'])
            self.log('STOCK BASELINE CAPTURED SUCCESSFULLY', 'success')
            self.refresh_status()
            next_step, self._steam_verify_continuation = self._steam_verify_continuation, None
            (next_step or continuation)()
        self._task(lambda: core.capture_stock(self.cfg, self.log), done)

    def _automatic_update_and_repair(self):
        if not self.cfg.get('automated_updates_repairs_on_start', False):
            return
        if self.busy or self._update_install_active:
            self.after(1000, self._automatic_update_and_repair)
            return
        if getattr(self, '_startup_automation_running', False):
            return
        self._startup_automation_running = True
        self._set_buttons(False)
        self.log('Starting automated startup updates and repairs.')
        completed = threading.Event()
        outcome = {'lines': [], 'restart': None}

        def work():
            lines = outcome['lines']

            def attempt(label, action):
                try:
                    message = action()
                except Exception as exc:
                    message = 'FAILED — ' + str(exc)
                    self.log(label + ' startup update failed: ' + str(exc), 'error')
                lines.append(label + ': ' + message)

            def update_app():
                release = updater.find_update(VERSION)
                if release is None:
                    return f'up to date (v{VERSION})'
                exe = os.environ.get('YAO_FORGE_EXE')
                bootstrap = os.environ.get('YAO_FORGE_BOOTSTRAP')
                data_dir = os.environ.get('YAO_FORGE_DATA')
                if not data_dir or not (exe or bootstrap):
                    return f'v{release["version"]} is available, but this launch has no managed updater'
                try:
                    launcher_api = int(os.environ.get('YAO_FORGE_LAUNCHER_API') or 1)
                except ValueError:
                    launcher_api = 1
                updater.install_update(release, data_dir, launcher_api)
                outcome['restart'] = [exe] if exe else [sys.executable, bootstrap]
                return f'v{release["version"]} installed; restart to activate it'

            def update_shodan():
                import shodan_updater
                release = shodan_updater.latest_release()
                latest = self._version_tuple(release['version'])
                current = core.editor_version(core.EDITOR)
                if current and latest + (0,) * max(0, len(current)-len(latest)) <= current + (0,) * max(0, len(latest)-len(current)):
                    return f'up to date (v{release["version"]})'
                core.APP_DATA.mkdir(parents=True, exist_ok=True)
                with tempfile.TemporaryDirectory(prefix='startup-shodan-', dir=core.APP_DATA) as folder:
                    package = Path(folder) / release['name']
                    shodan_updater.download_release(release, package)
                    kind, destination = core.import_editor(package, expected_kind='shodan', expected_version=latest)
                return f'updated to v{release["version"]}'

            def update_chef():
                import chef_updater
                import tool_installations
                release = chef_updater.latest_release()
                latest = self._version_tuple(release['version'])
                current = self._current_chef_version()
                if current and latest + (0,) * max(0, len(current)-len(latest)) <= current + (0,) * max(0, len(latest)-len(current)):
                    return f'up to date (v{release["version"]})'
                core.APP_DATA.mkdir(parents=True, exist_ok=True)
                with tempfile.TemporaryDirectory(prefix='startup-chef-', dir=core.APP_DATA) as folder:
                    package_path = Path(folder) / release['name']
                    chef_updater.download_release(release, package_path)
                    package = core.parse_mod(package_path)
                    package_version = self._version_tuple(package.get('name'))
                    if _loader_family(package.get('name')) != 'chef' or not package.get('targets'):
                        raise ValueError('The downloaded file is not a valid Chef Shared Loader package.')
                    if package_version and package_version != latest:
                        raise ValueError('The package version does not match the release tag.')
                    tool_installations.replace_chef(self.cfg, package_path, self.log)
                return f'updated to v{release["version"]} in the mod library'

            attempt('ModDiver Laboratory', update_app)
            attempt('SHODAN Stat Editor', update_shodan)
            attempt('Chef Shared Loader', update_chef)
            lines.append('ModDiverEditor / CCM: no automatic release feed is configured; updates remain available through Import update.')
            try:
                import builtin_updater
                progress_lines = []
                result = builtin_updater.run_worker(dict(self.cfg), lambda message: (progress_lines.append(str(message)), self.log(message)))
                if result and set(result) == set(builtin_updater.NAMES):
                    for key, label in builtin_updater.NAMES.items():
                        value = result[key]
                        if isinstance(value, Path):
                            updated = any(label in item and 'repaired, updated and verified' in item for item in progress_lines)
                            lines.append(label + ': ' + ('repaired/updated and verified' if updated else 'verified; no rebuild was needed'))
                        else:
                            lines.append(label + ': FAILED — ' + str(value))
                elif not self.cfg.get('game') or core.hellforge_root(self.cfg) is not None:
                    lines.append('Three built-in mods: skipped — select a Helldivers 2 Steam game folder to repair them.')
                else:
                    lines.append('Three built-in mods: FAILED — the selected game is not a supported Steam installation.')
            except Exception as exc:
                self.log('Built-in mod startup repair failed: ' + str(exc), 'error')
                lines.append('Three built-in mods: FAILED — ' + str(exc))
            for line in lines:
                self.log('Startup maintenance: ' + line)
            completed.set()

        def safe_work():
            try:
                work()
            except Exception as exc:
                outcome['lines'].append('Startup maintenance: FAILED — ' + str(exc))
                self.log('Automated startup maintenance failed: ' + str(exc), 'error')
            finally:
                completed.set()

        def poll():
            if not completed.is_set():
                self.after(80, poll)
                return
            self._startup_automation_running = False
            self._set_buttons(True)
            try:
                self.refresh_mods()
                self.refresh_status()
            except Exception as exc:
                outcome['lines'].append('Refresh: ' + str(exc))
            if outcome['restart']:
                self._update_restart_command = outcome['restart']
            self._show_automated_maintenance_report(outcome['lines'], bool(outcome['restart']))

        threading.Thread(target=safe_work, name='Automated startup maintenance', daemon=True).start()
        self.after(80, poll)

    def _show_automated_maintenance_report(self, lines, restart_available):
        if choice_screen.active(self) is not None or getattr(self, '_confirmation_panel', None) is not None:
            self.after(250, lambda: self._show_automated_maintenance_report(lines, restart_available))
            return
        width = min(880, max(520, self.winfo_width() - 48))
        height = min(660, max(420, self.winfo_height() - 48))
        screen = choice_screen.ChoiceScreen(self, size=(width, height))
        panel = self.theme['panel']
        content = tk.Frame(screen.card, bg=panel, padx=24, pady=22)
        content.pack(fill='both', expand=True, padx=1, pady=1)
        tk.Label(content, text=tr('Automated Updates and Repairs'), bg=panel,
                 fg=self.theme['accent'], font=('Segoe UI Semibold', 20), anchor='w').pack(fill='x')
        tk.Label(content, text=tr('Startup maintenance report'), bg=panel,
                 fg=self.theme['muted'], font=('Segoe UI', 10), anchor='w').pack(fill='x', pady=(4, 16))
        report_panel = tk.Frame(content, bg=self.theme['panel2'], bd=0, highlightthickness=1,
                                highlightbackground='#777777', highlightcolor='#777777')
        report_panel.pack(fill='both', expand=True)
        report = tk.Text(report_panel, wrap='word', state='normal', bd=0, relief='flat',
                         bg=self.theme['panel2'], fg=self.theme['text'],
                         insertbackground=self.theme['text'], selectbackground=self.theme['accent'],
                         selectforeground=self.theme['accent_text'], font=('Segoe UI', 11),
                         padx=16, pady=14, spacing1=2, spacing3=7, cursor='xterm', height=12)
        report.pack(side='left', fill='both', expand=True)
        scrollbar = ttk.Scrollbar(report_panel, orient='vertical', command=report.yview)
        scrollbar.pack(side='right', fill='y')
        report.configure(yscrollcommand=scrollbar.set)
        report.insert('end', '\n'.join(lines))
        report.configure(state='disabled')
        buttons = tk.Frame(content, bg=panel)
        buttons.pack(fill='x', pady=(16, 0))
        close_button = ttk.Button(buttons, text=tr('OK'), style='Yellow.TButton', command=screen.close)
        close_button.pack(side='right')
        if restart_available:
            ttk.Button(buttons, text=tr('Restart to finish app update'), style='Accent.TButton',
                       command=lambda: (screen.close(), self._restart_updated_app())).pack(side='right', padx=(0, 8))
        screen.activate(close_button)

    def _archive_steam_build(self):
        import build_archive
        if self.busy:
            self.after(5000, self._archive_steam_build)
            return
        def work():
            build_archive.ensure_baselines()
            try:
                game = core.game_dir(self.cfg)
                build = build_archive.steam_build(game)
            except (OSError, ValueError, KeyError):
                self.log('Stock baseline check could not identify a complete Steam game build. Select the game folder and finish any Steam update first.', 'warning')
                return {'state': 'unavailable', 'path': build_archive.archive_root()}
            if core.load_deployed():
                self.log('Baseline check skipped: ModDiver Laboratory has deployed mods. Purge them before validating clean game files.')
                return {'state': 'managed-mods', 'path': build_archive.archive_root()}
            self.log('Archive: checking Steam build ' + build + '.')
            baseline = build_archive.find_matching_clean_baseline(game, build)
            if baseline is None:
                self.log('No verified clean baseline matches the current game files. Startup did not capture the live game; verify files through Steam or restore the clean game, then capture explicitly.')
                return {'state': 'unverified', 'path': build_archive.archive_root()}
            self.log('Baseline data ready: ' + str(baseline))
            return {'state': 'clean', 'path': baseline, 'build': build}

        def finished():
            result = self._task_result
            if self._task_error is not None or not isinstance(result, dict):
                return
            if result['state'] == 'clean':
                self.log('STOCK BASELINE DATA IS FOUND, CLEAN', 'success')
                self.log('')
                self.log(f'MODDIVER LABORATORY {VERSION} IS READY TO USE!', 'success')
            elif result['state'] == 'unverified':
                self.log('STOCK BASELINE DATA IS NOT VERIFIED CLEAN. No new baseline was captured.', 'warning')
        self._task(work, finished)

    # ---------------------------------------------------------------- layout
    def _build(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._sidebar()
        main = ttk.Frame(self, style="TFrame")
        main.grid(row=0, column=1, sticky="nsew")
        self.main_surface = main
        main.bind('<Configure>', lambda event: ui_polish.schedule(self), add='+')
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)
        self._header(main)
        self.content = ttk.Frame(main, style="TFrame")
        self.content.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 10))
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)
        self.pages = {}
        for name, builder in (("mods", self._page_mods), ("presets", lambda parent: library_presets.PresetsPage(parent, self)), ("deploy", self._page_deploy),
                              ("editor", self._page_editor), ("tools", self._page_tools),
                              ("creator", lambda parent: creator_page.CreatorPage(parent, self)),
                              ("log", self._page_log), ("about", self._page_about),
                              ("settings", self._page_settings)):
            page = builder(self.content)
            page.grid(row=0, column=0, sticky="nsew")
            page.grid_remove()
            self.pages[name] = page
        self.status = ttk.Label(main, text=tr("ready"), style="Muted.TLabel", anchor="w")
        self.status.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 8))
        self._show("mods")
        self._loading_windows[self][0].lift()

    def _sidebar(self):
        self.sidebar = tk.Frame(self, width=212, bd=0, highlightthickness=0)
        self.sidebar.grid(row=0, column=0, sticky="ns")
        self.sidebar.grid_propagate(False)
        self.brand = tk.Frame(self.sidebar, bd=0, highlightthickness=0)
        self.brand.pack(fill="x", pady=(20, 0))
        self.brand_image = tk.PhotoImage(master=self, file=str(core.ROOT / 'branding/sidebar/212.png'))
        self.brand_label = tk.Label(self.brand, image=self.brand_image, bd=0, highlightthickness=0)
        self.brand_label.pack(fill='x')
        self.brand.bind('<Configure>', self._resize_brand)
        self.brand_sub = tk.Label(self.sidebar, text=tr(f"v{VERSION}"), font=("Segoe UI", 9), anchor="w")
        self.brand_sub.pack(fill="x", padx=20, pady=(2, 22))
        self.nav_icons = {name: {state: nav_icons.make_icon(self, name, self.theme[color])
                                for state, color in (('active', 'accent'), ('idle', 'muted'))}
                          for name in ('mods', 'deploy', 'editor', 'tools', 'creator', 'log', 'about', 'settings')}
        for name, label in (("mods", "MOD LIBRARY"), ("deploy", "MERGE AND DEPLOY"), ("editor", "DATA BOT"), ("tools", "TOOLS"), ("creator", "MOD CREATOR"),
                            ("log", "LOG"), ("about", "ABOUT AND UPDATE"), ("settings", "⚙  SETTINGS")):
            border = tk.Frame(self.sidebar, bg="#666666", bd=0)
            border.pack(fill="x", padx=12, pady=2)
            b = tk.Button(border, text='  ' + tr(label).removeprefix('⚙  '),
                          image=self.nav_icons[name]['idle'], compound='left', anchor="w", bd=0, relief="flat",
                          font=("Segoe UI Semibold", 11), padx=10, pady=10, cursor="hand2",
                          highlightthickness=0,
                          command=lambda n=name: self._show(n))
            b.pack(fill="x")
            self.nav_buttons[name] = b
            self.nav_button_frames[name] = border
        self.sidebar_footer = tk.Label(self.sidebar, text="ALL IN ONE APP FOR HD2",
                                       font=("Segoe UI", 8), anchor="w", justify="left")
        self.sidebar_footer.pack(side="bottom", fill="x", padx=20, pady=14)
        self.start_btn = tk.Button(self.sidebar, text=tr("\u25b6  START GAME"), bd=0, relief="flat",
                                   font=("Segoe UI Semibold", 11), pady=10, cursor="hand2",
                                   command=self.launch_game)
        self.start_btn.pack(side="bottom", fill="x", padx=14, pady=(0, 10))

    def _resize_brand(self, event):
        sizes = (212, 256, 265, 318, 384, 424, 512)
        width = min(sizes, key=lambda size: abs(size-event.width))
        if getattr(self, '_brand_width', None) != width:
            self._brand_width = width
            self.brand_image = tk.PhotoImage(master=self, file=str(core.ROOT / f'branding/sidebar/{width}.png'))
            self.brand_label.configure(image=self.brand_image)

    def _header(self, parent):
        head = ttk.Frame(parent, style="TFrame")
        head.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 8))
        head.grid_columnconfigure(0, weight=1)
        self.title_label = ttk.Label(head, text=tr("Mod Library"), style="Title.TLabel")
        self.title_label.grid(row=0, column=0, sticky="w")
        self.subtitle_label = ttk.Label(head, text=tr("Add any mods, merge and deploy them with one click"),
                                        style="Muted.TLabel")
        self.subtitle_label.grid(row=1, column=0, sticky="w")
        self.chip = ttk.Frame(head, style='Chip.TFrame', padding=(10, 4))
        self.chip.grid(row=0, column=1, rowspan=2, sticky='e')
        self.stock_count_label = ttk.Label(self.chip, text=tr('STOCK'), style='Chip.TLabel')
        self.stock_count_label.pack(side='left')
        self.stock_number_label = ttk.Label(self.chip, text='?', style='StockBad.Chip.TLabel')
        self.stock_number_label.pack(side='left', padx=(4, 10))
        self.deployed_count_label = ttk.Label(self.chip, text='', style='Chip.TLabel')
        self.deployed_count_label.pack(side='left')
        self.fullscreen_icon = nav_icons.make_icon(self, 'exit_fullscreen', self.theme['text'])
        self.exit_fullscreen_button = ttk.Button(head, text='ESC', image=self.fullscreen_icon,
                                                compound='left', command=self._exit_fullscreen)
        self.exit_fullscreen_button.grid(row=0, column=2, rowspan=2, sticky='ne', padx=(14, 0))
        if not self.attributes('-fullscreen'):
            self.exit_fullscreen_button.grid_remove()

    def _set_fullscreen(self, enabled):
        # Change the native frame once; a normal -> fullscreen detour flashes
        # an unpainted client area while the compositor rebuilds the surface.
        if getattr(self, '_window_transition', False):
            return
        if bool(self.attributes('-fullscreen')) == bool(enabled):
            return
        self._window_transition = True
        try:
            self.configure(bg=self.theme['bg'])
            self.update_idletasks()
            self.attributes('-fullscreen', bool(enabled))
            if hasattr(self, 'exit_fullscreen_button'):
                if enabled:
                    self.exit_fullscreen_button.grid()
                else:
                    self.exit_fullscreen_button.grid_remove()
            if not enabled:
                if self.tk.call('tk', 'windowingsystem') == 'x11':
                    self.attributes('-zoomed', False)
                elif self.state() == 'zoomed':
                    self.state('normal')
            window_surface.install(self)
            self._dark_titlebar()
            self.update_idletasks()
            window_surface.repaint(self)
        finally:
            self.after_idle(lambda: setattr(self, '_window_transition', False))

    def _exit_fullscreen(self):
        self._set_fullscreen(False)

    def _maximize_to_fullscreen(self, event):
        if (not self.cfg.get('fullscreen_on_maximize', False) or event.widget != self
                or self.attributes('-fullscreen') or getattr(self, '_window_transition', False)):
            return
        maximized = self.state() == 'zoomed'
        if self.tk.call('tk', 'windowingsystem') == 'x11':
            maximized = maximized or bool(self.attributes('-zoomed'))
        if maximized:
            self._set_fullscreen(True)

    def _maximize_startup(self):
        try:
            self.state('zoomed')
        except tk.TclError:
            self.attributes('-zoomed', True)

    def _begin_loading(self, token, window=None):
        self._progress_latest = None
        window = window or self
        self._loading_tokens[token] = window
        if window not in self._loading_windows:
            panel = tk.Frame(self, bg=self.theme['bg'], bd=0)
            panel.popup = self
            panel.brand = LoadingBrand(panel, self.theme['bg'], self.theme['accent'])
            bar = LoadingBar(panel, self.theme['bg'])
            bar.pack(fill='x', padx=24, pady=8)
            self._loading_windows[window] = (panel, bar)
        panel, bar = self._loading_windows[window]
        panel.place(relx=0, rely=1, relwidth=1, anchor='sw', height=80)
        panel.lift()
        bar.configure(caption='Preparing operation')
        bar.start()

    def report_progress(self, phase, done, total):
        # Workers only replace a small Python value. The UI polls the latest
        # report, avoiding thousands of cross-thread Tk callbacks during I/O.
        self._progress_latest = (phase, done, total)

    def _end_loading(self, token):
        self._loading_tokens.pop(token, None)
        for window, (panel, bar) in list(self._loading_windows.items()):
            if not panel.winfo_exists():
                del self._loading_windows[window]
            elif window not in self._loading_tokens.values():
                bar.stop()
                panel.place_forget()
                bar.configure(value=100)

    def _show(self, name):
        if name == 'presets':
            self.pages[name].refresh()
        previous = self.pages.get(self.current)
        if previous is not None and self.current != name:
            previous.grid_remove()
        self.current = name
        self.pages[name].grid()
        self.pages[name].tkraise()
        titles = {"mods": ("Mod Library", "Add any mods, merge and deploy them with one click"),
                  "deploy": ("Deploy & Purge", "Write the merged pack to the game, or restore stock."),
                  "editor": ("DATA BOT", "Decode files or automatically repair and update broken mods."),
                  "tools": ("Tools", "External editors, game setup and maintenance."),
                  "creator": ("Mod Creator", "Choose what to create. Make your changes. Export your mod."),
                  "settings": ("Settings", "Language, desktop shortcut and appearance."),
                  "log": ("Log", "Everything the Laboratory did this session."),
                  "about": ("About and Update", "ModDiver Laboratory.")}
        titles['presets'] = ('Mod Presets', 'Save and restore your mod setups, order and component selections.')
        titles['options'] = ('Mod Options', 'Choose components. Changes are saved automatically for the next deployment.')
        t, s = titles[name]
        self.title_label.configure(text=tr(t))
        if name == 'editor':
            import platform_icons
            self._data_bot_platforms = platform_icons.make(self, ('windows', 'linux'))
            self.title_label.configure(image=self._data_bot_platforms, compound='right')
        else:
            self.title_label.configure(image='', compound='none')
        self.subtitle_label.configure(text=tr(s))
        for n, b in self.nav_buttons.items():
            state = 'active' if n == name else 'idle'
            color = self.theme['accent' if n == name else 'muted']
            self.nav_icons[n][state] = nav_icons.make_icon(self, n, color)
            b.configure(bg=self.theme["panel2"] if n == name else self.theme["panel"],
                        image=self.nav_icons[n][state],
                        fg=self.theme["accent"] if n == name else self.theme["muted"],
                        highlightcolor=self.theme["accent"])
            self.nav_button_frames[n].configure(bg=self.theme["accent"] if n == name else "#666666")
        self.title_label.grid()
        self.subtitle_label.grid()
        ui_polish.schedule(self)

    # ---------------------------------------------------------------- theme
    def _style_checkboxes(self, body):
        """Use shared, DPI-scaled indicators with clear selected and disabled states."""
        t, s = self.theme, self.style
        size = max(18, round(18 * float(self.tk.call('tk', 'scaling')) / (96 / 72)))
        images = getattr(self, '_checkbox_images', {})
        for state in ('off', 'on', 'hover', 'on_hover', 'disabled', 'on_disabled'):
            selected = state.startswith('on')
            disabled = 'disabled' in state
            border = t['accent'] if 'hover' in state else t['muted']
            fill = t['panel2'] if disabled or not selected else t['accent']
            image = images.get(state) or tk.PhotoImage(master=self, width=size, height=size)
            image.put(border, to=(0, 0, size, size))
            image.put(fill, to=(2, 2, size-2, size-2))
            if selected:
                ink = t['muted'] if disabled else t['accent_text']
                for x0, y0, x1, y1 in ((.23, .49, .43, .69), (.43, .69, .78, .30)):
                    for step in range(size + 1):
                        x = round((x0 + (x1-x0)*step/size)*size)
                        y = round((y0 + (y1-y0)*step/size)*size)
                        image.put(ink, to=(x-1, y-1, x+2, y+2))
            images[state] = image
        element = 'ModDiver.Check.indicator'
        if element not in s.element_names():
            s.element_create(element, 'image', images['off'],
                             ('disabled', 'selected', images['on_disabled']),
                             ('disabled', images['disabled']),
                             ('active', 'selected', images['on_hover']),
                             ('selected', images['on']), ('active', images['hover']),
                             width=size+10, border=0, sticky='w')
        self._checkbox_images = images
        for style in ('TCheckbutton', 'Yellow.TCheckbutton'):
            s.layout(style, [('Checkbutton.padding', {'sticky': 'nswe', 'children': [
                (element, {'side': 'left', 'sticky': 'w'}),
                ('Checkbutton.focus', {'side': 'left', 'sticky': 'w', 'children': [
                    ('Checkbutton.label', {'sticky': 'nswe'})]})]})])
            s.configure(style, background=t['panel'] if style.startswith('Yellow') else t['bg'], foreground=t['text'], font=body,
                        padding=(8, 7), indicatormargin=(0, 0, 9, 0), focuscolor=t['accent'])
            s.map(style, background=[('active', t['panel2'])],
                  foreground=[('disabled', t['muted']), ('active', t['accent'])])

    def apply_theme(self):
        t = self.theme
        s = self.style
        f = int(t.get("font", 10))
        body = ("Segoe UI", f)
        small = ("Segoe UI", max(8, f - 1))
        s.configure("TFrame", background=t["bg"])
        s.configure("Panel.TFrame", background=t["panel"])
        s.configure('SettingsCard.TFrame', background=t['bg'], bordercolor=t['panel2'],
                    borderwidth=1, relief='solid')
        s.configure('SettingsTitle.TLabel', background=t['bg'], foreground=t['text'],
                    font=('Segoe UI Semibold', f + 2))
        s.configure("TLabel", background=t["bg"], foreground=t["text"], font=body)
        s.configure("Muted.TLabel", background=t["bg"], foreground=t["muted"], font=small)
        s.configure("Panel.TLabel", background=t["panel"], foreground=t["text"], font=body)
        s.configure("PanelMuted.TLabel", background=t["panel"], foreground=t["muted"], font=small)
        s.configure("LinuxWarning.TLabel", background=t["panel"], foreground="#ff5c5c",
                    font=("Segoe UI Semibold", max(9, f - 1)))
        s.configure("Title.TLabel", background=t["bg"], foreground=t["accent"], font=("Segoe UI Semibold", f + 8))
        s.configure("Chip.TLabel", background=t["panel2"], foreground=t["muted"], font=("Segoe UI Semibold", f - 1),
                    padding=(0, 0))
        s.configure('Chip.TFrame', background=t['panel2'])
        s.configure("StockGood.Chip.TLabel", background=t["panel2"], foreground="#35d07f",
                    font=("Segoe UI Semibold", f - 1))
        s.configure("StockBad.Chip.TLabel", background=t["panel2"], foreground="#ff5c5c",
                    font=("Segoe UI Semibold", f - 1))
        s.configure("TButton", background=t["panel2"], foreground=t["text"], font=body, padding=(10, 6),
                    borderwidth=0, focusthickness=0)
        for base in ('TButton', 'Danger.TButton', 'Options.TButton', 'Accent.TButton'):
            s.configure('Library.' + base, padding=(5, 6))
        s.map("TButton", background=[("active", t["accent"]), ("pressed", t["accent"])],
              foreground=[("active", t["accent_text"]), ("pressed", t["accent_text"])])
        s.configure("Accent.TButton", background=t["accent"], foreground=t["accent_text"],
                    font=("Segoe UI Semibold", f))
        self._globe_icon = nav_icons.make_icon(self, 'globe', t['accent_text'])
        self.btn_get_mods.configure(image=self._globe_icon)
        s.map("Accent.TButton", background=[("disabled", t["panel2"]), ("pressed", "#000000"), ("active", "#000000")],
              foreground=[("disabled", t["muted"]), ("pressed", t["accent"]), ("active", t["accent"])])
        s.configure("Yellow.TButton", background="#ffd400", foreground="#111111",
                    font=("Segoe UI Semibold", f), padding=(10, 6), borderwidth=0, focusthickness=0)
        s.map("Yellow.TButton", background=[("disabled", t["panel2"]), ("pressed", "#000000"), ("active", "#000000")],
              foreground=[("disabled", t["muted"]), ("pressed", "#ffd400"), ("active", "#ffd400")])
        s.configure("Support.TButton", background="#238636", foreground="#ffffff",
                    font=("Segoe UI Semibold", f), padding=(10, 6), borderwidth=0, focusthickness=0)
        s.map("Support.TButton", background=[("pressed", "#196c2e"), ("active", t["panel2"])],
              foreground=[("pressed", "#ffffff"), ("active", t["text"])])
        s.configure("Patreon.TButton", background="#f96854", foreground="#ffffff",
                    font=("Segoe UI Semibold", f), padding=(10, 6), borderwidth=0, focusthickness=0)
        s.map("Patreon.TButton", background=[("pressed", "#df5948"), ("active", t["panel2"])],
              foreground=[("pressed", "#ffffff"), ("active", t["text"])])
        s.configure("SupportDialog.TFrame", background=t["bg"])
        s.configure("SupportTitle.TLabel", background=t["bg"], foreground=t["accent"],
                    font=("Segoe UI Semibold", f + 8))
        s.configure("SupportBody.TLabel", background=t["bg"], foreground=t["text"], font=body)
        s.configure("Danger.TButton", background=t["bad"], foreground="#ffffff")
        s.map("Danger.TButton", background=[("pressed", "#ad2521"), ("active", "#f04b45")],
              foreground=[("active", "#ffffff"), ("pressed", "#ffffff")])
        s.configure("Options.TButton", background=t["accent"], foreground=t["accent_text"],
                    font=("Segoe UI Semibold", f), padding=(10, 6), borderwidth=0, focusthickness=0)
        s.map("Options.TButton", background=[("disabled", t["panel2"]), ("pressed", "#000000"), ("active", "#000000")],
              foreground=[("disabled", t["muted"]), ("pressed", t["accent"]), ("active", t["accent"])])
        s.configure("Install.TButton", background="#238636", foreground="#ffffff",
                    font=("Segoe UI Semibold", f), padding=(10, 6), borderwidth=0, focusthickness=0)
        s.map("Install.TButton", background=[("pressed", "#196c2e"), ("active", "#2ea043")],
              foreground=[("pressed", "#ffffff"), ("active", "#ffffff")])
        s.configure("Update.TButton", background="#1266a8", foreground="#ffffff",
                    font=("Segoe UI Semibold", f), padding=(10, 6), borderwidth=0, focusthickness=0)
        s.map("Update.TButton", background=[("pressed", "#0d4f85"), ("active", "#258be0")],
              foreground=[("pressed", "#ffffff"), ("active", "#ffffff")])
        s.configure('Shortcut.TButton', background='#555555', foreground='#ffffff')
        s.configure('Neutral.TButton', background='#555555', foreground='#ffffff',
                    font=('Segoe UI Semibold', f), padding=(10, 6), borderwidth=0, focusthickness=0)
        s.map('Neutral.TButton', background=[('disabled', t['panel2']), ('pressed', '#444444'), ('active', '#666666')],
              foreground=[('disabled', t['muted']), ('pressed', '#ffffff'), ('active', '#ffffff')])
        s.map('Shortcut.TButton', background=[('pressed', '#444444'), ('active', '#666666')],
              foreground=[('pressed', '#ffffff'), ('active', '#ffffff')])
        s.configure('OS.TLabel', background=t['bg'], foreground=t['text'], padding=(10, 5),
                    borderwidth=1, relief='solid', bordercolor='#258be0',
                    lightcolor='#258be0', darkcolor='#258be0')
        s.configure('OSBadge.TFrame', background=t['panel2'], relief='solid', borderwidth=1)
        s.configure('OSBadge.TLabel', background=t['panel2'], foreground=t['text'],
                    font=('Segoe UI Semibold', 11))
        self.fullscreen_icon = nav_icons.make_icon(self, 'exit_fullscreen', t['text'])
        self.exit_fullscreen_button.configure(image=self.fullscreen_icon)
        s.configure("LibraryDanger.TButton", background="#b42318", foreground="#ffffff",
                    font=("Segoe UI Semibold", f), padding=(10, 6), borderwidth=0, focusthickness=0)
        s.map("LibraryDanger.TButton", background=[("pressed", "#7a160f"), ("active", "#e3342f")],
              foreground=[("pressed", "#ffffff"), ("active", "#ffffff")])
        s.configure("Treeview", background=t["panel"], fieldbackground=t["panel"], foreground=t["text"],
                    font=body, rowheight=max(24, f * 2 + 6), borderwidth=0)
        s.configure("Treeview.Heading", background=t["panel2"], foreground=t["muted"],
                    font=("Segoe UI Semibold", f - 1), relief="flat", padding=(8, 6))
        s.map("Treeview", background=[("selected", t["accent"])], foreground=[("selected", t["accent_text"])])
        s.map("Treeview.Heading", background=[("active", t["panel2"])])
        s.configure("TNotebook", background=t["bg"], borderwidth=0, tabmargins=(0, 0, 4, 0))
        s.configure("TNotebook.Tab", background=t["panel"], foreground=t["muted"], padding=(14, 6),
                    font=("Segoe UI Semibold", f - 1), borderwidth=0)
        s.map("TNotebook.Tab", background=[("selected", t["panel2"]), ("active", t["panel2"])],
              foreground=[("selected", t["accent"]), ("active", t["text"])])
        s.configure("TEntry", fieldbackground=t["panel"], foreground=t["text"], insertcolor=t["text"],
                    bordercolor=t["panel2"], lightcolor=t["panel2"], darkcolor=t["panel2"])
        for orientation in ('Vertical', 'Horizontal'):
            name = orientation + '.TScrollbar'
            s.configure(name, background=t['panel2'], troughcolor=t['bg'],
                        arrowcolor=t['text'], bordercolor=t['bg'],
                        lightcolor=t['panel2'], darkcolor=t['panel2'])
            s.map(name, background=[('pressed', t['accent']), ('active', t['muted'])],
                  arrowcolor=[('pressed', t['accent_text'])])
        self._style_checkboxes(body)
        s.configure("TCombobox", fieldbackground=t["panel"], background=t["panel2"], foreground=t["text"],
                    arrowcolor=t["text"], bordercolor=t["panel2"], lightcolor=t["panel2"], darkcolor=t["panel2"])
        s.map("TCombobox", fieldbackground=[("readonly", t["panel"]), ("disabled", t["panel"])],
              background=[("active", t["panel2"])], foreground=[("readonly", t["text"]), ("disabled", t["muted"])],
              selectbackground=[("readonly", t["panel"])], selectforeground=[("readonly", t["text"])])
        for option, value in {"background": t["panel"], "foreground": t["text"],
                              "selectBackground": t["accent"], "selectForeground": t["accent_text"]}.items():
            self.option_add("*TCombobox*Listbox." + option, value)
        self._theme_dropdowns(self)
        s.configure("Horizontal.TProgressbar", background=t["accent"], troughcolor=t["panel2"],
                    bordercolor=t["panel2"], lightcolor=t["accent"], darkcolor=t["accent"])
        s.configure("Horizontal.TScale", background=t["bg"], troughcolor=t["panel2"])
        self.configure(bg=t["bg"])
        if hasattr(self, 'mod_count_box'):
            self.mod_count_box.configure(bg=t['panel'], highlightbackground='#777777', highlightcolor='#777777')
            self.mod_count.configure(bg=t['panel'], fg=t['muted'])
        if hasattr(self, "tools_canvas"):
            self.tools_canvas.configure(background=t["bg"])
        if hasattr(self, 'creator_canvas'):
            self.creator_canvas.configure(bg=t['bg'])
        if hasattr(self, 'settings_canvas'):
            self.settings_canvas.configure(background=t['bg'])
        if hasattr(self, 'advanced_creator'):
            self.advanced_creator.configure(bg=t['panel'], highlightbackground='#ffd400')
        self.sidebar.configure(bg=t["panel"])
        self.brand.configure(bg=t["panel"])
        for parent in (self.sidebar, getattr(self, "brand", None)):
            if parent is None:
                continue
            for w in parent.winfo_children():
                if isinstance(w, tk.Label):
                    w.configure(bg=t["panel"], fg=t["muted"])
        for w in self.brand.winfo_children():
            if isinstance(w, tk.Label):
                w.configure(fg=t["accent"] if w.cget("text") == "MODDIVER" else t["text"])
        self.sidebar_footer.configure(bg=t["panel"], fg=t["muted"])
        for name, b in self.nav_buttons.items():
            b.configure(bg=t["panel2"] if name == self.current else t["panel"],
                        fg=t["accent"] if name == self.current else t["muted"],
                        activebackground=t["panel2"], activeforeground=t["accent"],
                        highlightcolor=t["accent"])
            self.nav_button_frames[name].configure(bg=t["accent"] if name == self.current else "#666666")
        self.start_btn.configure(bg=t["accent"], fg=t["accent_text"],
                                 activebackground="#000000", activeforeground=t["accent"])
        self.start_btn.bind("<Enter>", lambda event: self.start_btn.configure(bg="#000000", fg=self.theme["accent"]))
        self.start_btn.bind("<Leave>", lambda event: self.start_btn.configure(bg=self.theme["accent"], fg=self.theme["accent_text"]))
        for w in self.texts:
            try:
                w.configure(bg=t["panel"], fg=t["text"], insertbackground=t["text"],
                            selectbackground=t["accent"], selectforeground=t["accent_text"])
            except (tk.TclError,RuntimeError):
                pass
        bright=sum(self.winfo_rgb(t['panel']))>3*32768
        for widget in self.texts:
            if widget is not None:
                if widget in (getattr(self, 'deploy_log', None), getattr(self, 'log_text', None)):
                    widget.configure(font=('Consolas', int(t.get('log_font', 12))))
                widget.tag_configure('success',foreground='#16752b' if bright else '#65df92')
                widget.tag_configure('error',foreground='#b5161c' if bright else '#ff7272')
                widget.tag_configure('warning',foreground='#8b5700' if bright else '#f4c542')
                widget.tag_configure('info_blue',foreground='#1266a8' if bright else '#64b5ff')
        about = getattr(self, "about_text", None)
        if about is not None:
            try:
                about.tag_configure("h1", foreground=t["text"])
                about.tag_configure("sub", foreground=t["muted"])
                about.tag_configure("h2", foreground=t["accent"])
                about.tag_configure("body", foreground=t["text"])
                about.tag_configure("warning", foreground="#ff3333")
                about.tag_configure("name", foreground=t["text"])
                about.tag_configure("tool", foreground=t["muted"])
                about.tag_configure("num", foreground=t["text"])
                about.tag_configure("bullet", foreground=t["text"])
            except tk.TclError:
                pass
        for panel, bar in self._loading_windows.values():
            if panel.winfo_exists():
                panel.configure(bg=t['bg'])
                panel.brand.set_theme(t['bg'], t['accent'])
                bar.configure(bg=t['bg'])
        if hasattr(self, 'update_progress'):
            self.update_progress.configure(bg=t['bg'])
        if hasattr(self, 'log_font_scale'):
            self.log_font_scale.configure(bg=t['bg'], fg=t['text'], troughcolor=t['panel2'],
                                          highlightthickness=0, bd=0, activebackground=t['panel2'])
            self.log_font_scale.set(t.get('log_font', 12))
        if hasattr(self, "font_scale"):
            self.font_scale.configure(bg=t["bg"], fg=t["text"], troughcolor=t["panel2"],
                                      highlightthickness=0, bd=0, activebackground=t["panel2"])
        if hasattr(self, "mod_cards"):
            self.mod_cards.configure(bg=self.theme["bg"])
            self._retheme_mod_cards()
        try:
            self._refresh_titlebars(self)
        except Exception:
            pass
        ui_polish.action_styles(self)
        ui_polish.refresh(self)
        self.cfg["theme"] = dict(self.theme)
        core.save_config(self.cfg)

    def _theme_dropdowns(self, parent):
        # Popup listboxes already created by Tk do not re-read the option database.
        for widget in parent.winfo_children():
            if isinstance(widget, ttk.Combobox):
                popup = str(widget) + '.popdown.f.l'
                if self.tk.call('winfo', 'exists', popup):
                    self.tk.call(popup, 'configure', '-background', self.theme['panel'],
                                 '-foreground', self.theme['text'], '-selectbackground', self.theme['accent'],
                                 '-selectforeground', self.theme['accent_text'])
            self._theme_dropdowns(widget)

    def _set_theme(self, **kw):
        # Tk can invoke the Scale command again when its colours are configured.
        # Do not rebuild the library for an unchanged slider value: rebuilding
        # processes idle events and would otherwise re-enter apply_theme forever.
        if all(self.theme.get(key) == value for key, value in kw.items()):
            return
        self.theme.update(kw)
        if getattr(self, '_theme_pending', None):
            self.after_cancel(self._theme_pending)
            self._theme_pending = None
        if set(kw) <= {'font', 'log_font'}:
            self._theme_pending = self.after(70, self._apply_pending_theme)
        else:
            self.apply_theme()

    def _apply_pending_theme(self):
        if getattr(self, '_theme_pending', None):
            self.after_cancel(self._theme_pending)
        self._theme_pending = None
        self.apply_theme()

    def _bgr(self, color):
        h = color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return (b << 16) | (g << 8) | r

    def _refresh_titlebars(self, parent):
        if isinstance(parent, (tk.Tk, tk.Toplevel)):
            self._dark_titlebar(parent)
        for child in parent.winfo_children():
            self._refresh_titlebars(child)

    def _style_mapped_widget(self, event):
        widget = event.widget
        if isinstance(widget, tk.Toplevel):
            self.after_idle(lambda: self._dark_titlebar(widget) if widget.winfo_exists() else None)
            # Transient/grab setup can recreate the native frame after mapping.
            self.after(100, lambda: self._dark_titlebar(widget) if widget.winfo_exists() else None)
        ui_polish.decorate(self, widget)
        self._clickable_cursor(event)

    def _clickable_cursor(self, event):
        widget = event.widget
        if not isinstance(widget, tk.Misc):
            return
        try:
            clickable = widget.winfo_class() in {
                'Button', 'TButton', 'Checkbutton', 'TCheckbutton', 'Radiobutton',
                'TRadiobutton', 'Menubutton', 'TMenubutton', 'TCombobox',
                'TNotebook', 'Scale', 'TScale', 'Scrollbar', 'TScrollbar', 'Treeview'}
            clickable = clickable or any(widget.bind(sequence) for sequence in
                                         ('<Button-1>', '<ButtonRelease-1>', '<Double-Button-1>'))
            if clickable:
                disabled = 'state' in widget.keys() and str(widget.cget('state')) == 'disabled'
                widget.configure(cursor='arrow' if disabled else 'hand2')
        except tk.TclError:
            pass

    def _dark_titlebar(self, window=None):
        try:
            target = window or self
            if not target.winfo_exists():
                return
            user32 = ctypes.windll.user32
            user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
            user32.GetAncestor.restype = ctypes.c_void_p
            hwnd = user32.GetAncestor(target.winfo_id(), 2)  # GA_ROOT: decorated native frame
            if not hwnd:
                return
            gdi32 = ctypes.windll.gdi32
            gdi32.CreateSolidBrush.argtypes = [ctypes.c_uint]
            gdi32.CreateSolidBrush.restype = ctypes.c_void_p
            brushes = getattr(self, '_native_background_brushes', {})
            color = self._bgr(self.theme['bg'])
            if color not in brushes:
                brushes[color] = gdi32.CreateSolidBrush(color)
            self._native_background_brushes = brushes
            set_background = user32.SetClassLongPtrW if ctypes.sizeof(ctypes.c_void_p) == 8 else user32.SetClassLongW
            set_background.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
            set_background.restype = ctypes.c_void_p
            for surface in (hwnd, target.winfo_id()):
                set_background(surface, -10, brushes[color])  # GCLP_HBRBACKGROUND
            dwm = ctypes.windll.dwmapi
            dwm.DwmSetWindowAttribute.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                                 ctypes.c_void_p, ctypes.c_uint]
            dwm.DwmSetWindowAttribute.restype = ctypes.c_long
            one = ctypes.c_int(int(sum(self.winfo_rgb(self.theme['panel'])) < 3 * 32768))
            dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(one), 4)
            for attr, color in ((35, self.theme["panel"]), (34, self.theme["bg"]),
                                (36, self.theme["text"])):
                c = ctypes.c_int(self._bgr(color))
                dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(c), 4)
        except Exception:
            pass

    # ---------------------------------------------------------------- mods page
    def _page_mods(self, parent):
        page = ttk.Frame(parent, style="TFrame")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)
        bar = ttk.Frame(page, style="TFrame")
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        for index, (label, cmd) in enumerate((("+ Add ZIP / 7Z", self.add_zip), ("+ Add Folder", self.add_folder),
                           ("Purge All Mods", self.do_purge))):
            style = ("Danger.TButton" if label.startswith("Purge") else
                     "Accent.TButton" if label.startswith("+ Add") else
                     "Options.TButton" if label == "Options" else "TButton")
            button = ttk.Button(bar, text=tr(label), style='Library.' + style, width=0, command=cmd)
            button.grid(row=0, column=index, sticky='ew', padx=(0, 6))
            self.mod_action_buttons.append(button)
        self.loader_order_button = tk.Button(bar, relief='flat', bd=0, padx=8, pady=7,
                                             font=('Segoe UI Semibold', 9), cursor='hand2',
                                             command=self._toggle_loader_order)
        self.loader_order_button.grid(row=0, column=3, sticky='ew', padx=(0, 6))
        self.mod_action_buttons.append(self.loader_order_button)
        self._paint_loader_order()
        self.btn_lab_storage = ttk.Button(bar, text=tr('ADD MODS FROM LAB STORAGE'),
                                         style='Library.TButton', command=self.add_from_lab_storage)
        self.btn_lab_storage._action_icon_name = 'flask'
        ui_polish.update_icon(self, self.btn_lab_storage)
        self.btn_lab_storage.grid(row=0, column=4, sticky='ew', padx=(0, 6))
        self.mod_action_buttons.append(self.btn_lab_storage)
        self.btn_presets = ttk.Button(bar, text=tr('Mod Presets'), command=lambda: self._show('presets'))
        self.btn_presets.grid(row=0, column=5, sticky='ew', padx=(0, 6))
        self.mod_action_buttons.append(self.btn_presets)
        self.btn_view_mods = ttk.Button(bar, text=tr("View Mods Folder"), style='Library.TButton', width=0, command=self.view_mods_folder)
        self.btn_view_mods.grid(row=0, column=6, sticky='ew', padx=(0, 6))
        self.mod_action_buttons.append(self.btn_view_mods)
        bar.grid_columnconfigure(7, weight=1)
        self._globe_icon = nav_icons.make_icon(self, 'globe', self.theme['accent_text'])
        self.btn_get_mods = ttk.Button(bar, text=tr("Get Mods"), image=self._globe_icon, compound='left', style="Library.Accent.TButton", width=0, command=self.get_mods)
        self.btn_get_mods.grid(row=0, column=8, sticky='ew')
        ttk.Label(
            bar,
            text=(tr("Drag cards into LOADERS, GAMEPLAY or VISUAL & AUDIO, including empty groups. "
                     "Higher mods have priority within each group. Green ON includes a mod in the next installation; "
                     "use Merge and Install All to deploy.")),
            style="Muted.TLabel", wraplength=900, justify="left").grid(
                row=1, column=0, columnspan=9, sticky="nw", pady=(6, 0))
        wrap = ttk.Frame(page, style="Panel.TFrame")
        wrap.grid(row=1, column=0, sticky="nsew")
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_rowconfigure(0, weight=1)
        self.mod_canvas = tk.Canvas(wrap, background=self.theme["bg"], highlightthickness=0, bd=0, yscrollincrement=1)
        self.mod_canvas.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.mod_canvas.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self._library_rows = []
        self.mod_cards = self.mod_canvas
        self._library_bg_item = self.mod_canvas.create_image(0, 0, anchor='center')
        def scrolled(first, last):
            sb.set(first, last)
            self._position_library_background()
        self.mod_canvas.configure(yscrollcommand=scrolled)
        self.mod_canvas.bind('<Configure>', self._layout_library)
        self.bind_all("<MouseWheel>", self._scroll_mod_cards, add="+")
        self.bind_all("<Button-4>", self._scroll_mod_cards, add="+")
        self.bind_all("<Button-5>", self._scroll_mod_cards, add="+")
        self.bind("<Escape>",self._cancel_mod_drag,add="+")
        self.selected_mod_index = None
        self._mod_preview_cache = {}
        footer = ttk.Frame(page, style='TFrame')
        footer.grid(row=2, column=0, sticky='ew', pady=(8, 0))
        self.mod_count_box = tk.Frame(footer, bg=self.theme['panel'], bd=0, highlightthickness=1,
                                      highlightbackground='#777777', highlightcolor='#777777')
        self.mod_count = tk.Label(self.mod_count_box, text=tr('0 mods'), bg=self.theme['panel'],
                                  fg=self.theme['muted'], font=('Segoe UI', 9), padx=10, pady=4)
        self.mod_count.pack()
        self.mod_detail = ttk.Label(footer, text=tr("Priority: the top mod wins where two change the same value."),
                                    style="Muted.TLabel")
        self.mod_detail.pack(side='left', anchor='w')
        self.mod_count_box.pack(side='right', anchor='se')
        return page

    def _position_library_background(self):
        canvas = self.mod_canvas
        canvas.coords(self._library_bg_item, canvas.winfo_width()/2,
                      canvas.canvasy(0) + canvas.winfo_height()/2)
        canvas.tag_lower(self._library_bg_item)
        ui_polish.position_canvas(canvas)

    def _layout_library(self, event=None):
        canvas = self.mod_canvas
        width, height = max(1, canvas.winfo_width()), max(1, canvas.winfo_height())
        # Pre-scaled beaker images preserve 7% alpha without requiring Pillow.
        # Keep the complete beaker visible inside the library viewport.
        desired = min(width, height) * .96
        size = max((n for n in (256, 384, 512, 640, 768, 896, 1024) if n <= desired), default=256)
        if getattr(self, '_library_bg_size', None) != size:
            self._library_bg_size = size
            self._library_bg = tk.PhotoImage(master=self, file=str(Path(__file__).parent / 'library_background' / f'{size}.png'))
            canvas.itemconfigure(self._library_bg_item, image=self._library_bg)
        y = 0
        for item, widget, before, after in self._library_rows:
            canvas.itemconfigure(item, width=max(1, width-20))
            y += before
            canvas.coords(item, 10, y)
            y += widget.winfo_reqheight() + after
        canvas.configure(scrollregion=(0, 0, width, max(height, y)))
        ui_polish.paint_library(self)
        ui_polish.paint_library_chrome(self)
        self._position_library_background()

    def _library_row(self, widget, before, after):
        item = self.mod_canvas.create_window(10, 0, anchor='nw', window=widget, tags='mod_window')
        self._library_rows.append((item, widget, before, after))

    def get_mods(self):
        existing = choice_screen.active(self)
        if existing is not None:
            return existing
        screen = choice_screen.ChoiceScreen(self)
        frame = ttk.Frame(screen.card, padding=24)
        frame.pack(fill='both', expand=True, padx=1, pady=1)
        ttk.Label(frame, text=tr('Choose a mod website'), style='Title.TLabel').pack(anchor='w', pady=(0, 12))
        ttk.Label(frame, text=tr('Download a mod, then use Add ZIP / 7Z or Add Folder in the library.'),
                  wraplength=420, style='Muted.TLabel').pack(anchor='w', pady=(0, 16))
        self.mod_site_buttons = []
        for name, url, color in (
            ('Nexus Mods', 'https://www.nexusmods.com/games/helldivers2', '#d66a12'),
            ('AyakaMods', 'https://ayakamods.com/?game_id=119', '#008b8b'),
            ('HellForge', 'https://hf-mod.com/', '#c62828')):
            button = tk.Button(frame, text=tr(name), bg=color, fg='white', activebackground=color,
                               activeforeground='white', font=('Segoe UI Semibold', 12), relief='flat',
                               cursor='hand2', padx=24, pady=12,
                               command=lambda link=url: self._open_mod_site(link, screen))
            button.pack(fill='x', pady=5)
            self.mod_site_buttons.append(button)
        ttk.Label(frame, textvariable=screen.error, wraplength=420, style='Muted.TLabel').pack(fill='x')
        screen.cancel_button = ttk.Button(frame, text=tr('Close'), command=screen.close)
        screen.cancel_button.pack(pady=(14, 0))
        screen.cancel_button.bind('<Return>', screen.close)
        screen.activate(screen.cancel_button)
        return screen

    def _open_mod_site(self, url, parent):
        try:
            if not self._open_browser(url):
                raise RuntimeError(tr('No web browser could be opened.'))
            parent.error.set('')
        except Exception as exc:
            parent.error.set(tr(str(exc)))

    def _mod_selected(self, _event=None):
        i = self.selected_mod_index
        if i is None or i >= len(self.cfg["mods"]):
            return
        m = self.cfg["mods"][i]
        targets = ", ".join(m.get("targets", [])) or "no data targets"
        opts = ", ".join(m.get("options") or []) or "none"
        self.mod_detail.configure(text=tr(f"{m['name']}  |  {m['type']}  |  {targets}  |  options: {opts}"))

    def _scroll_mod_cards(self, event):
        if self.current != "mods":
            return
        if getattr(event, "num", None) == 4:
            units = -3
        elif getattr(event, "num", None) == 5:
            units = 3
        elif getattr(event, "delta", 0):
            units = -1 if event.delta > 0 else 1
        else:
            return
        self.mod_canvas.yview_scroll(units * 36, "units")
        return "break"

    def _add_paths(self, paths, loader_import=False, cleanup_sources=False, custom_loader=False):
        if self.busy:
            return
        self.busy = True
        self._set_buttons(False)
        self.log(f"reading {len(paths)} mod(s)...")

        def work():
            imported, errors = 0, []
            for path_index, p in enumerate(paths):
                self.report_progress('Importing mod packages', path_index, len(paths))
                try:
                    preview = core.parse_mod(p)
                    preview_name = str(preview.get("name", "")).casefold()
                    if "boot" in preview_name and "loader" in preview_name:
                        raise ValueError("This loader is no longer supported by ModDiver Laboratory.")
                    if loader_import:
                        if not preview.get("targets") or _loader_family(preview.get("name")) != "chef":
                            raise ValueError("Choose a Chef Shared Loader package with its manifest and deployable files.")
                    if _loader_family(preview.get('name')) == 'chef':
                        import tool_installations
                        tool_installations.replace_chef(self.cfg, p, self.log)
                        imported += 1
                        if cleanup_sources:
                            Path(p).unlink(missing_ok=True)
                        continue
                    managed_path = core.add_to_library(p)
                    m = core.parse_mod(managed_path)
                except Exception as exc:
                    self.log(f"  {p}: {exc}")
                    errors.append(str(exc))
                    if cleanup_sources:
                        Path(p).unlink(missing_ok=True)
                    continue
                opts = [o["name"] for o in m.get("options", [])]
                defaults = {o["name"]: bool(o.get("default", True)) for o in m.get("options", [])}
                if loader_import:
                    family = _loader_family(m.get("name"))
                    if family:
                        for previous in self.cfg["mods"]:
                            if _loader_family(previous.get("name")) == family:
                                previous["enabled"] = False
                                self.log(f"  disabled previous {family} loader: {previous.get('name')}")
                entry = {"path": m["path"], "name": m["name"], "type": m["type"],
                         "targets": m["targets"], "options": opts,
                         "selected": defaults, "enabled": True,
                         "runtime": bool(m.get("runtime"))}
                if loader_import or custom_loader:
                    entry['category'] = 'loaders'
                    self.cfg["mods"].insert(0, entry)
                else:
                    self.cfg["mods"].append(entry)
                self.log(f"  added {m['name']} ({m['type']}, {len(m['targets'])} targets)"
                         + ("  [runtime - needs a loader, will be skipped]" if m.get("runtime") else ""))
                imported += 1
                if loader_import:
                    self.log("  Chef loader is in the library; use Deploy to apply the update.")
                if cleanup_sources:
                    Path(p).unlink(missing_ok=True)
            self.report_progress('Mod packages processed', len(paths), len(paths))
            core.save_config(self.cfg)
            return imported, errors

        def finished(result, error):
            self._added()
            if error:
                self.log(f"ERROR importing mods: {error}")
            if loader_import:
                imported, errors = result or (0, [])
                message = ('Chef Shared Loader added. Deploy to install it.' if imported else
                           'Chef Shared Loader import failed:\n\n' + '\n'.join([error] if error else errors))
                self._update_notice(tr(APP_NAME), tr(message))

        self._background_update(work, finished, 'Mod package import')

    def _added(self):
        self._set_buttons(True)
        self.refresh_mods()
        self.refresh_status()

    def add_zip(self):
        paths = filedialog.askopenfilenames(
            title=tr("Add data mod archives"),
            filetypes=[("Mod archives", "*.zip *.7z"), ("ZIP archives", "*.zip"), ("7-Zip archives", "*.7z")],
            parent=self._dialog_parent())
        if paths:
            self._add_paths(paths)

    def add_folder(self):
        path = filedialog.askdirectory(title=tr("Add a mod folder"), parent=self._dialog_parent())
        if path:
            self._add_paths([path])

    def add_from_lab_storage(self):
        existing = choice_screen.active(self)
        if existing is not None:
            return existing
        if self.busy:
            return
        import lab_storage
        self._task(lambda: lab_storage.candidates(self.cfg),
                   lambda: lab_storage.StoragePicker(self, self._task_result)
                   if self._task_result is not None else None)

    def _selected_index(self):
        return self.selected_mod_index

    def remove_mod(self):
        if self.busy:return
        i = self._selected_index()
        if i is None:
            return
        actions.remove_mod(self.cfg, i, self.log)
        self.selected_mod_index = None
        self.refresh_mods()

    def toggle_mod(self):
        if self.busy:return
        i = self._selected_index()
        if i is None:
            return
        mod=self.cfg['mods'][i]
        was_enabled=mod.get('enabled',True)
        deployed=core.load_deployed()
        sources={str(Path(source).resolve()) for info in deployed.values() for source in info.get('sources',[]) if source}
        legacy_names={name for info in deployed.values() if not any(info.get('sources',[])) for name in info.get('mods',[])}
        def was_installed(item):
            return str(Path(item.get('path','')).resolve()) in sources or item.get('name') in legacy_names
        installed=was_installed(mod)
        actions.toggle_mod(self.cfg,i)
        # Keep the native canvas windows mapped: rebuilding the list here flashes
        # every card over the watermark and briefly shows unpositioned buttons.
        self._paint_mod_toggle(i)
        self._select_mod(i)
        root = core.hellforge_root(self.cfg)
        if root is not None:
            import hellforge
            receipt = hellforge.load_receipt(root)
            mid = next((mid for mid, info in receipt['mods'].items()
                        if info['source'] == str(Path(mod['path']).resolve())), None)
            if mid:
                self._task(lambda: hellforge._run(root, 'mod-switch', '--id', mid,
                           '--on', 'yes' if mod.get('enabled') else 'no'), self.refresh_status)
            return
        if was_enabled and installed:
            snapshot=copy.deepcopy(self.cfg)
            snapshot['mods']=[item for item in snapshot['mods'] if item.get('enabled') and was_installed(item)]
            snapshot['nomofomo']=bool(snapshot.get('nomofomo',True) and any(Path(t).name=='generated_customization_armor_sets.dl_bin' for t in deployed))
            for key in gameplay_profiles.PROFILES:
                profile_path = str((core.BUILTIN / 'gameplay' / (key + '.zip')).resolve())
                snapshot[key] = bool(snapshot.get(key, False) and profile_path in sources)
            def rebuild():
                actions.purge(snapshot,self.log)
                if core.load_deployed():raise RuntimeError('Some files could not be restored; remaining mods were not redeployed.')
                return actions.install_all(snapshot,self.log)
            self._task(rebuild,self.refresh_status)

    def _mod_preview(self, mod):
        path = str(mod.get("path") or "")
        if path in self._mod_preview_cache:
            return self._mod_preview_cache[path]
        candidates = []
        source = Path(path)
        try:
            if source.is_dir():
                manifest_path = source / "manifest.json"
                if manifest_path.is_file():
                    data = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
                    for key in ("IconPath", "iconPath", "Image", "image", "Preview", "preview"):
                        if data.get(key): candidates.append(str(data[key]))
                for name in ("thumbnail.png", "preview.png", "icon.png", "image.png", "cover.png"):
                    candidates.append(name)
                for candidate in candidates:
                    image_path = (source / candidate).resolve()
                    if image_path.is_relative_to(source.resolve()) and image_path.is_file():
                        image = tk.PhotoImage(master=self, file=str(image_path))
                        break
                else: image = None
            elif source.is_file() and source.suffix.casefold() == ".zip":
                with zipfile.ZipFile(source) as archive:
                    names = archive.namelist()
                    by_lower = {name.casefold(): name for name in names}
                    for name in names:
                        if name.casefold().endswith("/manifest.json") or name.casefold() == "manifest.json":
                            try:
                                data = json.loads(archive.read(name).decode("utf-8-sig"))
                                for key in ("IconPath", "iconPath", "Image", "image", "Preview", "preview"):
                                    if data.get(key): candidates.append(str(data[key]).lstrip("./\\"))
                            except Exception: pass
                            break
                    candidates.extend(("thumbnail.png", "preview.png", "icon.png", "image.png", "cover.png"))
                    found = next((v for k, v in by_lower.items() if any(k == c.casefold() or k.endswith("/" + c.casefold()) for c in candidates)), None)
                    image = tk.PhotoImage(master=self, data=base64.b64encode(archive.read(found))) if found else None
            else: image = None
        except Exception:
            image = None
        using_fallback = image is None
        if using_fallback and hasattr(self, '_fallback_mod_preview'):
            self._mod_preview_cache[path] = self._fallback_mod_preview
            return self._fallback_mod_preview
        if image is None:
            fallback = Path(__file__).resolve().parent / 'branding/icon_256.png'
            image = tk.PhotoImage(master=self, file=str(fallback)) if fallback.is_file() else None
        if image is not None:
            largest = max(image.width(), image.height())
            if largest > 88:
                factor = (largest + 79) // 80
                image = image.subsample(factor, factor)
            elif largest < 48:
                image = image.zoom(2, 2)
            elif largest < 68:
                image = image.zoom(3, 3).subsample(2, 2)
        if using_fallback:
            self._fallback_mod_preview = image
        self._mod_preview_cache[path] = image
        return image

    def _configure_mod_at(self, index):
        if self.busy:return
        self._select_mod(index)
        self.configure_mod()

    def configure_mod(self):
        if self.busy:return
        i = self._selected_index()
        if i is None:
            return
        m = self.cfg["mods"][i]
        opts = m.get("options") or []
        if not opts:
            self.log("THIS MOD HAS NO OPTIONS")
            return
        from mod_options import OptionsPage
        previous = self.pages.pop('options', None)
        if previous is not None:
            previous.destroy()
        page = OptionsPage(self.content, self, m)
        page.grid(row=0, column=0, sticky='nsew')
        self.pages['options'] = page
        self._show('options')
        ui_polish.refresh(self)

    def _paint_loader_order(self):
        first = self.cfg.get('loaders_deploy_first', False)
        self._loader_order_icon = nav_icons.make_icon(self, 'loader_up' if first else 'loader',
                                                      '#111111' if first else '#ffffff')
        self.loader_order_button.configure(
            image=self._loader_order_icon, compound='left',
            text=tr('LOADERS DEPLOY FIRST' if first else 'LOADERS DEPLOY LAST'),
            bg='#ffd400' if first else '#666666', fg='#111111' if first else '#ffffff',
            activebackground='#000000' if first else '#666666',
            activeforeground='#ffd400' if first else '#ffffff')

    def _toggle_loader_order(self):
        if self.busy:return
        self.cfg['loaders_deploy_first'] = not self.cfg.get('loaders_deploy_first', False)
        core.save_config(self.cfg)
        self._paint_loader_order()

    def _remove_mod_at(self, index):
        if self.busy:return
        self.selected_mod_index = index
        self.remove_mod()

    def _deployed_mods(self):
        root = core.hellforge_root(self.cfg)
        if root is not None:
            import hellforge
            sources = {info['source'] for info in hellforge.load_receipt(root)['mods'].values()}
            sources &= {str(Path(m.get('path') or '').resolve()) for m in self.cfg['mods'] if m.get('enabled', True)}
            return sources, set()
        deployed = core.load_deployed()
        return ({str(Path(source).resolve()) for info in deployed.values() for source in info.get('sources', []) if source},
                {name for info in deployed.values() if not any(info.get('sources', [])) for name in info.get('mods', [])})

    def _deployment_color(self, mod, sources, names):
        installed = str(Path(mod.get('path') or '').resolve()) in sources or mod.get('name') in names
        return '#238636' if installed else '#b42318'

    def _refresh_deployment_outlines(self):
        sources, names = self._deployed_mods()
        for index, card in getattr(self, 'mod_card_widgets', {}).items():
            card.preview_widget.configure(highlightbackground=self._deployment_color(self.cfg['mods'][index], sources, names))

    def refresh_mods(self):
        view=self.mod_canvas.yview()[0]
        self._cancel_mod_drag()
        if not hasattr(self, "mod_cards"):
            return
        for _, widget, _, _ in self._library_rows:
            widget.destroy()
        active_paths = {str(mod.get('path') or '') for mod in self.cfg['mods']}
        self._mod_preview_cache = {path: image for path, image in self._mod_preview_cache.items()
                                   if path in active_paths}
        self.mod_canvas.delete('mod_window')
        self._library_rows = []
        self.mod_card_widgets = {}
        self.mod_toggle_widgets = {}
        groups = {key: [] for key in core.LIBRARY_CATEGORIES}
        self._category_headers = {}
        self._trash_icon = nav_icons.make_icon(self, 'trash', '#e3342f', self.theme['accent'])
        for i, m in enumerate(self.cfg["mods"]):
            groups[core.library_category(m)].append((i, m))
        sources, names = self._deployed_mods()
        order = 0
        for key, label in (("loaders", "LOADERS"), ("gameplay", "GAMEPLAY"), ("visual", "VISUAL & AUDIO")):
            header = tk.Label(self.mod_cards, text=tr(f"{label}  ({len(groups[key])})"),
                              bg=self.theme["bg"], fg=self.theme["accent"],
                              font=("Segoe UI Semibold", 12), anchor="w")
            header.category_icon = nav_icons.make_icon(self, key, self.theme['accent'])
            header.configure(image=header.category_icon, compound='left', padx=6)
            header.category_label = label
            self._category_headers[key] = header
            self._library_row(header, 12, 7)
            for i, m in groups[key]:
                order += 1
                source_missing = not Path(m.get("path") or "").exists()
                enabled = m.get("enabled", True)
                card = tk.Frame(self.mod_cards, bg=self.theme["panel"], highlightthickness=2,
                                highlightbackground=self.theme["accent"] if i == self.selected_mod_index else self.theme["panel2"],
                                highlightcolor=self.theme["accent"])
                self._library_row(card, 4, 4)
                self.mod_card_widgets[i] = card
                card.grid_columnconfigure(1, weight=1)
                preview = self._mod_preview(m)
                pic = tk.Label(card, image=preview, bg=self.theme["panel"], width=84, height=84,
                               highlightthickness=2, highlightbackground=self._deployment_color(m, sources, names))
                card.preview_widget = pic
                pic.grid(row=0, column=0, rowspan=2, padx=10, pady=9)
                name = m["name"] + ("   [missing source]" if source_missing else "") + ("   [runtime]" if m.get("runtime") else "")
                name_label = tk.Label(card, text=f"{order}.  {tr(name)}", bg=self.theme["panel"], fg=self.theme["text"],
                                      font=("Segoe UI Semibold", 11), anchor="w")
                card.name_widget = name_label
                card.mod_title = tr(name)
                name_label.grid(row=0, column=1, sticky="ew", padx=(4, 8), pady=(11, 2))
                meta = tk.Label(card, text=tr(f"{m['type']}   ·   {len(m.get('targets', []))} targets"),
                                bg=self.theme["panel"], fg=self.theme["muted"], anchor="w")
                meta.grid(row=1, column=1, sticky="ew", padx=(4, 8), pady=(0, 10))
                toggle = tk.Button(card, text=tr("●  ON  · click to disable" if enabled else "●  OFF  · click to enable"),
                                   bg="#238636" if enabled else "#b42318", fg="white", activeforeground="white",
                                   activebackground="#2ea043" if enabled else "#e3342f", relief="flat", bd=0,
                                   font=("Segoe UI Semibold", 9), padx=12, pady=8, cursor="hand2",
                                   command=lambda idx=i: self._toggle_mod_at(idx))
                options = ttk.Button(card, text="🔧︎", style="Options.TButton", width=3,
                                     command=lambda idx=i: self._configure_mod_at(idx))
                options.grid(row=0, column=2, rowspan=2, padx=(4, 0), pady=10)
                options.configure(state="disabled" if self.busy else "normal")
                card.options_widget = options
                toggle.grid(row=0, column=3, rowspan=2, padx=12, pady=10)
                toggle.configure(state="disabled" if self.busy else "normal")
                trash_border = tk.Frame(card, bg='#e3342f', padx=1, pady=1, bd=0)
                trash = tk.Button(trash_border, image=self._trash_icon, bg=self.theme['panel'],
                                  activebackground=self.theme['panel2'], relief='flat', bd=0,
                                  padx=6, pady=8, cursor='hand2', highlightthickness=1,
                                  highlightbackground='#e3342f', highlightcolor='#e3342f',
                                  command=lambda idx=i: self._remove_mod_at(idx))
                trash.pack()
                trash_border.grid(row=0, column=4, rowspan=2, padx=(0, 10), pady=10)
                card.trash_border = trash_border
                trash.configure(state='disabled' if self.busy else 'normal')
                card.trash_widget = trash
                self.mod_toggle_widgets[i]=toggle
                for widget in (card, pic, name_label, meta):
                    self._bind_mod_drag(widget, i)
        count = tr(f"{len(self.cfg['mods'])} mods")
        if self.cfg.get('active_mod_preset'):
            count += '  ·  ' + self.cfg['active_mod_preset']
        self.mod_count.configure(text=count)
        self.after_idle(self._layout_library)
        self.mod_canvas.yview_moveto(view)

    def _retheme_mod_cards(self):
        if not hasattr(self, 'mod_card_widgets'):
            self.refresh_mods()
            return
        t = self.theme
        self._trash_icon = nav_icons.make_icon(self, 'trash', '#e3342f', t['accent'])
        for key, header in self._category_headers.items():
            header.category_icon = nav_icons.make_icon(self, key, t['accent'])
            header.configure(bg=t['bg'], fg=t['accent'], image=header.category_icon)
        for index, card in self.mod_card_widgets.items():
            card.configure(bg=t['panel'], highlightbackground=t['accent'] if index == self.selected_mod_index else t['panel2'])
            for child in card.winfo_children():
                if isinstance(child, tk.Label):
                    child.configure(bg=t['panel'], fg=t['text'] if child is card.name_widget else t['muted'])
            card.trash_widget.configure(bg=t['panel'], activebackground=t['panel2'], image=self._trash_icon)
        self._paint_loader_order()

    def _paint_mod_toggle(self, index):
        enabled = self.cfg['mods'][index].get('enabled', True)
        self.mod_toggle_widgets[index].configure(
            text=tr("●  ON  · click to disable" if enabled else "●  OFF  · click to enable"),
            bg="#238636" if enabled else "#b42318",
            activebackground="#2ea043" if enabled else "#e3342f")

    def _select_mod(self, index):
        self.selected_mod_index = index
        for card_index, card in self.mod_card_widgets.items():
            card.configure(highlightthickness=2,
                           highlightbackground=self.theme["accent"] if card_index == index else self.theme["panel2"])
        self._mod_selected()

    def _drag_mod_press(self,index,event):
        if self.busy:return 'break'
        self._cancel_mod_drag()
        self._mod_drag=(index,event.y_root)
        self._drag_y=event.y_root
        self._select_mod(index)
        self.mod_card_widgets[index].configure(cursor='fleur')
        return 'break'

    def _cancel_mod_drag(self,event=None):
        if getattr(self,'_drag_timer',None):self.after_cancel(self._drag_timer)
        self._drag_timer=None
        if getattr(self,'_drop_marker',None):self._drop_marker.place_forget()
        if getattr(self,'_drop_line',None):self.mod_canvas.itemconfigure(self._drop_line,state='hidden')
        self._drop_position = None
        drag=getattr(self,'_mod_drag',None)
        if drag and drag[0] in self.mod_card_widgets:self.mod_card_widgets[drag[0]].configure(cursor='')
        self._mod_drag=None

    def _drag_target(self):
        # Header boundaries make empty categories valid drop zones too.
        category = core.LIBRARY_CATEGORIES[0]
        for key, header in self._category_headers.items():
            if self._drag_y >= header.winfo_rooty():
                category = key
        positions = [i for i, mod in enumerate(self.cfg['mods'])
                     if core.library_category(mod) == category and i != self._mod_drag[0]]
        if not positions:
            return None, True, category
        target = min(positions, key=lambda i: abs(self.mod_card_widgets[i].winfo_rooty() +
                     self.mod_card_widgets[i].winfo_height()/2 - self._drag_y))
        card = self.mod_card_widgets[target]
        return target, self._drag_y > card.winfo_rooty() + card.winfo_height()/2, category

    def _drag_mod_release(self,index,event):
        drag=getattr(self,'_mod_drag',None)
        if not drag:return
        self._drag_y=event.y_root
        target,after,category=self._drag_target()
        self._cancel_mod_drag()
        if self.busy or abs(event.y_root-drag[1])<8:return
        top=self.mod_canvas.winfo_rooty()
        if not top<=event.y_root<=top+self.mod_canvas.winfo_height():return
        old_mods = list(self.cfg['mods'])
        self.selected_mod_index=actions.reorder_mod(self.cfg,drag[0],target,after,category)
        # Reuse canvas windows and images. Destroying/recreating all cards flashes
        # the background and forces thumbnails and native windows to repaint.
        remap = {old: next(i for i, mod in enumerate(self.cfg['mods']) if mod is item)
                 for old, item in enumerate(old_mods)}
        cards = {remap[i]: card for i, card in self.mod_card_widgets.items()}
        toggles = {remap[i]: button for i, button in self.mod_toggle_widgets.items()}
        row_by_card = {widget: row for row in self._library_rows for widget in [row[1]] if widget in cards.values()}
        header_rows = {row[1]: row for row in self._library_rows if row[1] not in row_by_card}
        self._library_rows = []
        for category, header in self._category_headers.items():
            indices = [i for i, mod in enumerate(self.cfg['mods']) if core.library_category(mod) == category]
            header.configure(text=tr(f'{header.category_label}  ({len(indices)})'))
            self._library_rows.append(header_rows[header])
            self._library_rows.extend(row_by_card[cards[i]] for i in indices)
        self.mod_card_widgets, self.mod_toggle_widgets = cards, toggles
        for i, card in cards.items():
            toggles[i].configure(command=lambda idx=i:self._toggle_mod_at(idx))
            for widget in (card, *card.winfo_children()):
                if widget not in (toggles[i], card.options_widget, card.trash_widget):self._bind_mod_drag(widget, i)
            card.options_widget.configure(command=lambda idx=i:self._configure_mod_at(idx))
            card.trash_widget.configure(command=lambda idx=i:self._remove_mod_at(idx))
        for number, row in enumerate((row for row in self._library_rows if row[1] in cards.values()), 1):
            card = row[1]
            card.name_widget.configure(text=f"{number}.  {card.mod_title}")
        self._layout_library()
        self._select_mod(self.selected_mod_index)

    def _bind_mod_drag(self,widget,index):
        widget.configure(cursor='hand2')
        widget.bind('<ButtonPress-1>',lambda e,i=index:self._drag_mod_press(i,e))
        widget.bind('<B1-Motion>',self._drag_mod_motion)
        widget.bind('<ButtonRelease-1>',lambda e,i=index:self._drag_mod_release(i,e))

    def _drag_mod_motion(self,event):
        if self.busy or not getattr(self,'_mod_drag',None):return
        self._drag_y=event.y_root
        if abs(self._drag_y-self._mod_drag[1])<8:return
        if not getattr(self,'_drag_timer',None):self._drag_tick()

    def _drag_tick(self):
        self._drag_timer=None
        if self.busy or not getattr(self,'_mod_drag',None):return
        local=self._drag_y-self.mod_canvas.winfo_rooty()
        height=self.mod_canvas.winfo_height()
        if local<36:self.mod_canvas.yview_scroll(-8,'units')
        elif local>height-36:self.mod_canvas.yview_scroll(8,'units')
        target,after,category=self._drag_target()
        card = self.mod_card_widgets[target] if target is not None else self._category_headers[category]
        y=card.winfo_rooty()-self.mod_canvas.winfo_rooty()+(card.winfo_height() if after else 0)
        position = (target, after, round(self.mod_canvas.canvasy(y)))
        if position != getattr(self, '_drop_position', None):
            self._drop_position = position
            if not getattr(self,'_drop_line',None):
                self._drop_line=self.mod_canvas.create_line(0,0,0,0,width=3)
            cy = self.mod_canvas.canvasy(max(0,min(height-3,y)))
            self.mod_canvas.coords(self._drop_line,10,cy,self.mod_canvas.winfo_width()-10,cy)
            self.mod_canvas.itemconfigure(self._drop_line,fill=self.theme['accent'],state='normal')
            self.mod_canvas.tag_raise(self._drop_line)
        self._drag_timer=self.after(16,self._drag_tick)

    def _toggle_mod_at(self, index):
        self.selected_mod_index = index
        self.toggle_mod()

    # ---------------------------------------------------------------- deploy page
    def _page_deploy(self, parent):
        page = ttk.Frame(parent, style="TFrame")
        page.grid_columnconfigure(0, weight=1)
        row = ttk.Frame(page, style="TFrame")
        row.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(row, text=tr("Game folder")).pack(side="left")
        self.game_var = tk.StringVar(master=self, value=self.cfg["game"])
        entry = ttk.Entry(row, textvariable=self.game_var, width=70)
        entry.pack(side="left", padx=8, fill="x", expand=True)
        entry.bind("<FocusOut>", lambda e: self._save_game())
        ttk.Button(row, text=tr("Browse"), command=self._browse_game).pack(side="left")
        stat = ttk.Frame(page, style="TFrame")
        stat.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        self.stock_label = ttk.Label(stat, text=tr("Stock: not captured"), style="Muted.TLabel")
        self.stock_label.pack(side="left")
        self.deployed_label = ttk.Label(stat, text=tr("   Deployed: 0"), style="Muted.TLabel")
        self.deployed_label.pack(side="left")
        bar = ttk.Frame(page, style="TFrame")
        bar.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        self.btn_install = ttk.Button(bar, text=tr("MERGE and INSTALL ALL"), style="Install.TButton", command=self.install_all)
        self.btn_install.pack(side="left", padx=(0, 6))
        self.btn_preview = ttk.Button(bar, text=tr("Preview Deployment"), style="Neutral.TButton",
                                      command=lambda: self.install_all(dry_run=True))
        self.btn_preview._semantic_role = 'secondary'
        self.btn_preview.pack(side="left", padx=(0, 6))
        self.btn_purge = ttk.Button(bar, text=tr("Purge All Mods"), style="Danger.TButton", command=self.do_purge)
        self.btn_purge.pack(side="left", padx=(0, 6))
        self.btn_export = ttk.Button(bar, text=tr("Export Mod Library"), style='Neutral.TButton', command=self.do_export)
        self.btn_export._semantic_role = 'secondary'
        self.btn_export.pack(side="left", padx=(0, 6))
        self.btn_import = ttk.Button(bar, text=tr("Import Mod Library"), style='Neutral.TButton', command=self.do_import_library)
        self.btn_import._semantic_role = 'secondary'
        self.btn_import.pack(side="left", padx=(6, 0))
        self.btn_deploy_clear_log = ttk.Button(bar, text=tr('Clear Log'), command=self.clear_log)
        self.btn_deploy_clear_log.pack(side='left', padx=(6, 0))
        deploy_actions = (self.btn_install, self.btn_preview, self.btn_purge, self.btn_export, self.btn_import,
                          self.btn_deploy_clear_log)
        for button in deploy_actions:
            button.pack_forget()
        def arrange_deploy_actions(event=None):
            compact = bar.winfo_width() < sum(button.winfo_reqwidth()+6 for button in deploy_actions)
            if getattr(bar, '_compact', None) == compact:
                return
            bar._compact = compact
            for index, button in enumerate(deploy_actions):
                row, column = (1, index-2) if compact and index >= 2 else (0, index)
                button.grid(row=row, column=column, sticky='w', padx=(0, 6), pady=(6 if row else 0, 0))
        bar.bind('<Configure>', arrange_deploy_actions)
        self.after_idle(arrange_deploy_actions)
        ttk.Label(page, text=tr('For HellForge, select its installation folder. Complete packages, runtime files and load order are managed through HellForge; its external-launcher CLI is required.'),
                  style='Muted.TLabel', wraplength=760).grid(row=6,column=0,sticky='w',pady=(8,0))
        self.btn_purge_library = ttk.Button(page, text=tr("Completely Purge Mod Library"),
                                            style="LibraryDanger.TButton", command=self.purge_mod_library)
        self.btn_purge_library.grid(row=5, column=0, sticky="e", pady=(8, 0))
        self.deploy_log = ReportView(page, background_folder='wordmark_background', height=16, wrap="word", font=("Consolas", 9))
        self.deploy_log.grid(row=4, column=0, sticky="nsew")
        page.grid_rowconfigure(4, weight=1)
        self.texts.append(self.deploy_log)
        self.deploy_log.configure(state="disabled")
        return page

    def _save_game(self):
        self.cfg["game"] = self.game_var.get().strip()
        core.save_config(self.cfg)
        self.refresh_status()

    def _browse_game(self):
        path = filedialog.askdirectory(title=tr("Helldivers 2 folder"), parent=self._dialog_parent())
        if path:
            self.game_var.set(path)
            self._save_game()

    def capture_stock(self):
        if self.busy:return
        def capture():
            return core.capture_stock(self.cfg, self.log)
        def finished():
            if self._task_error is not None:
                messagebox.showerror(tr(APP_NAME), tr(self._task_error), parent=self._dialog_parent())
            else:
                if self._task_result == core.REQUIRED_STOCK_FILES:
                    self.log('STOCK BASELINE CAPTURED SUCCESSFULLY', 'success')
                else:
                    self.log(f"GAME FILES SAVED ({self._task_result} files)")
            self.refresh_status()
            self._stock_verify_started = False
            self.btn_capture.configure(text=tr('STEAM VERIFY + CAPTURE STOCK'))
            if hasattr(self, 'stock_action_status'):
                if self._task_error is not None:
                    message = tr('Stock capture failed. Check the game folder and try again.')
                elif self._task_result == core.REQUIRED_STOCK_FILES:
                    message = tr('Clean stock baseline complete: 55 files.')
                else:
                    message = tr(f'Captured {self._task_result} of 55 files. Verify game files and retry.')
                self.stock_action_status.configure(text=message)
            self._stock_prompt_open = False
            if self._task_error is not None or self._task_result != core.REQUIRED_STOCK_FILES:
                self.after_idle(self._prompt_for_complete_stock)
        self._task(capture, finished)

    def _prompt_for_complete_stock(self):
        """Prompt until all 55 clean stock files have been captured."""
        if self.busy or self._stock_prompt_open or getattr(self, '_choice_screen', None) is not None:
            return
        if core.hellforge_root(self.cfg) is not None:
            return
        count = core.stock_file_count()
        if count == core.REQUIRED_STOCK_FILES:
            return
        self._stock_prompt_open = True
        self._show('deploy')
        screen = choice_screen.ChoiceScreen(self, size=(960, 720))
        screen.bind('<Escape>', lambda event: self._dismiss_stock_prompt(screen))
        panel = screen.card
        panel.configure(padx=22, pady=18)

        actions = ttk.Frame(panel)
        actions.pack(side='bottom', fill='x', padx=14, pady=(10, 8))
        skip = ttk.Button(actions, text=tr('Skip and verify later'), style='TButton',
                          command=lambda: self._dismiss_stock_prompt(screen))
        skip.pack(side='right')
        verify = ttk.Button(actions, text=tr('STEAM VERIFY + CAPTURE STOCK'), style='Accent.TButton',
                            command=lambda: self._combined_stock_action(
                                verify, status, screen=screen))
        verify.pack(side='right', padx=(0, 10), ipadx=8, ipady=4)
        status = tk.Label(actions,
                 text=tr('Skip hides this reminder for now. Full functions require all 55 clean files.'),
                 bg=self.theme['panel'], fg=self.theme['muted'], font=('Segoe UI', 9),
                 wraplength=440, justify='left', anchor='w')
        status.pack(side='left', fill='x', expand=True, padx=(0, 12))

        tk.Label(panel, text=tr('CLEAN STOCK DATA REQUIRED'), bg=self.theme['panel'],
                 fg=self.theme['accent'], font=('Segoe UI Semibold', 22),
                 anchor='w').pack(fill='x', padx=14, pady=(8, 3))
        tk.Label(panel, text=tr('A clean baseline is necessary for ModDiver Lab to work accurately.'),
                 bg=self.theme['panel'], fg=self.theme['muted'],
                 font=('Segoe UI', 11), anchor='w').pack(fill='x', padx=16, pady=(0, 10))

        warning = tk.Frame(panel, bg=self.theme['panel2'], highlightthickness=1,
                           highlightbackground='#ff5c5c')
        warning.pack(fill='x', padx=14, pady=(0, 10))
        tk.Label(warning, text=tr(f'BASELINE STATUS   {count} OF 55 FILES'),
                 bg=self.theme['panel2'], fg='#ff6b6b',
                 font=('Segoe UI Semibold', 11), anchor='w').pack(fill='x', padx=12, pady=(8, 3))
        tk.Label(warning,
                 text=tr('ModDiver Lab will not have full functions until clean game data is captured.'),
                 bg=self.theme['panel2'], fg=self.theme['text'], font=('Segoe UI Semibold', 10),
                 wraplength=860, justify='left', anchor='w').pack(fill='x', padx=12, pady=(0, 8))

        body = tk.Frame(panel, bg=self.theme['panel'])
        body.pack(fill='both', expand=True, padx=14, pady=(0, 4))
        canvas = tk.Canvas(body, bg=self.theme['panel'], bd=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(body, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        content = tk.Frame(canvas, bg=self.theme['panel'])
        content_window = canvas.create_window((0, 0), window=content, anchor='nw')
        content.bind('<Configure>', lambda event: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(content_window, width=event.width))

        tk.Label(content, text=tr('WHAT IS CAPTURING CLEAN DATA?'), bg=self.theme['panel'],
                 fg=self.theme['text'], font=('Segoe UI Semibold', 13),
                 anchor='w').pack(fill='x', padx=4, pady=(4, 7))
        explanation = (
            'Capturing data means ModDiver Lab reads and saves the generated .dl_bin game data files '
            'from your game installation. It does NOT read your account information or copy your main '
            '22 GB game installation.\n\n'
            'Clean means these game data files have no mods. ModDiver Lab needs clean data to accurately '
            'merge, deploy, repair and update your mods. After capture, PURGE can restore the clean stock '
            'files for game data managed by ModDiver, removing ModDiver-managed changes. Steam Verify '
            'Integrity can also restore official game files.'
        )
        tk.Label(content, text=tr(explanation), bg=self.theme['panel'], fg=self.theme['muted'],
                 font=('Segoe UI', 11), wraplength=870, justify='left',
                 anchor='nw').pack(fill='x', padx=4, pady=(0, 14))

        steps = tk.Frame(content, bg=self.theme['panel2'])
        steps.pack(fill='x', padx=4, pady=(0, 10))
        tk.Label(steps, text=tr('RECOMMENDED STEPS'), bg=self.theme['panel2'],
                 fg=self.theme['text'], font=('Segoe UI Semibold', 11),
                 anchor='w').pack(fill='x', padx=12, pady=(8, 3))
        tk.Label(steps,
                 text=tr('1. Close Helldivers 2 and any mod manager.\n'
                         '2. Click STEAM VERIFY + CAPTURE STOCK below. This starts Steam verification.\n'
                         '3. ModDiver automatically captures clean data two seconds after verification finishes.\n'
                         '4. Wait for the stock count to reach 55. Available on Windows and Linux.'),
                 bg=self.theme['panel2'], fg=self.theme['muted'], font=('Segoe UI', 10),
                 wraplength=850, justify='left', anchor='w').pack(fill='x', padx=12, pady=(0, 10))
        screen.activate(verify)

    def _dismiss_stock_prompt(self, screen):
        if screen.winfo_exists():
            screen.destroy()
        self._stock_prompt_open = False
        if self._stock_verify_started:
            self.btn_capture.configure(text=tr('VERIFYING STEAM…'))
            if hasattr(self, 'stock_action_status'):
                self.stock_action_status.configure(
                    text=tr('Steam verification started. ModDiver will capture clean stock automatically after it finishes.'),
                    foreground=self.theme['accent'])

    def _merge_deploy_stock_action(self):
        self._combined_stock_action(self.btn_capture, self.stock_action_status)

    def _capture_clean_stock_direct(self):
        """Capture immediately when the user confirms the game is already clean."""
        self._stock_verify_started = False
        self.btn_capture.configure(text=tr('STEAM VERIFY + CAPTURE STOCK'))
        self.stock_action_status.configure(
            text=tr('Capturing the current game files directly. Use this only when no mods are active.'),
            foreground=self.theme['muted'])
        self.capture_stock()

    def _combined_stock_action(self, button, status_label=None, screen=None):
        if self._stock_verify_started:
            self.log('Steam verification is in progress. Clean stock will be captured automatically two seconds after Steam finishes.')
            return
        prompt_status = status_label if screen is not None else None
        try:
            if not messagebox.askyesno(
                    tr('Prepare clean game data'),
                    tr('Steam Verify will restore official game files. This removes files installed in the '
                       'game folder, including ModDiver deployment; your mod library stays in ModDiver and '
                       'can be deployed again afterward. Repair data will download in the background. '
                       'ModDiver will capture clean stock automatically two seconds after Steam finishes.'),
                    parent=self._dialog_parent()):
                return
            if screen is not None:
                self._dismiss_stock_prompt(screen)
            self._show('log')
            self.deiconify()
            self.lift()
            self.attributes('-topmost', True)
            self.update_idletasks()
            self._steam_verify_continuation = self._after_stock_capture
            self._begin_steam_verification()
            if button.winfo_exists():
                button.configure(text=tr('VERIFYING STEAM…'))
            self.btn_capture.configure(text=tr('VERIFYING STEAM…'))
            if hasattr(self, 'stock_action_status'):
                self.stock_action_status.configure(
                    text=tr('Repair data is downloading. Steam verification progress is in the log; clean stock will be captured automatically when it finishes.'),
                    foreground=self.theme['accent'])
            if prompt_status is not None and prompt_status.winfo_exists():
                prompt_status.configure(
                    text=tr('Repair data is downloading. Clean stock will be captured automatically when Steam finishes.'),
                    foreground=self.theme['accent'] if isinstance(status_label, ttk.Label) else self.theme['accent'])
        except Exception as exc:
            self._stock_verify_started = False
            self._steam_verify_continuation = None
            self._capture_for_repair = False
            self.attributes('-topmost', False)
            self.log(f'Could not start Steam Verify Integrity: {exc}', 'error')
            if prompt_status is not None and prompt_status.winfo_exists():
                prompt_status.configure(text=tr(f'Could not start Steam verification: {exc}'),
                                        foreground='#ff5c5c')
            else:
                messagebox.showerror(tr(APP_NAME), tr(f'Could not start Steam Verify Integrity:\n\n{exc}'),
                                     parent=self._dialog_parent())

    def _begin_steam_verification(self):
        # Mark active before launching Steam; Tk may process callbacks during shell handoff.
        self._stock_verify_started = True
        log_path = core.steam_content_log(core.game_dir(self.cfg))
        self._steam_verify_log_path = log_path
        self._steam_verify_log_offset = log_path.stat().st_size if log_path and log_path.exists() else 0
        self._steam_verify_started_at = time.monotonic()
        self._steam_verify_phase = 'starting'
        self.attributes('-topmost', True)
        self.deiconify()
        self.lift()
        core.steam_verify()
        self.log('STEAM VERIFY REQUESTED : GRANTED')
        self.log('Steam verification progress is shown as live phases; Steam does not expose a file-validation percentage here.')
        self._prefetch_repair_data()
        self._poll_steam_verification()

    def _poll_steam_verification(self):
        if not self._stock_verify_started:
            return
        elapsed = max(0, int(time.monotonic() - (self._steam_verify_started_at or time.monotonic())))
        phase = self._steam_verify_phase or 'waiting for Steam'
        path = self._steam_verify_log_path
        if path and path.is_file():
            try:
                with path.open('rb') as stream:
                    stream.seek(self._steam_verify_log_offset)
                    raw = stream.read()
                    self._steam_verify_log_offset = stream.tell()
                lines = raw.decode('utf-8', errors='replace').splitlines()
                relevant = [line for line in lines if '553850' in line]
                for line in relevant:
                    lower = line.lower()
                    if 'start validating appid 553850' in lower:
                        phase = 'verification queued'
                    if 'verifying installed' in lower:
                        phase = 'verifying installed files'
                    elif any(word in lower for word in ('downloading', 'staging', 'committing')):
                        phase = 'restoring changed files'
                    if ('app update changed : none' in lower or 'scheduler finished : removed from schedule' in lower):
                        phase = 'verification complete'
            except OSError:
                phase = 'Steam is working; progress log unavailable'
        if phase != self._steam_verify_phase:
            self._steam_verify_phase = phase
            if phase == 'verification complete':
                self.log(f'Steam verification finished ({elapsed // 60:02d}:{elapsed % 60:02d}). Capturing clean stock in 2 seconds.')
                if hasattr(self, 'stock_action_status'):
                    self.stock_action_status.configure(
                        text=tr('Steam verification finished. Capturing clean stock automatically in 2 seconds.'),
                        foreground=self.theme['accent'])
                if self._steam_capture_after_id is None:
                    self._steam_capture_after_id = self.after(2000, self._capture_stock_after_steam)
        if phase != 'verification complete':
            self.log(f'Steam verification: {phase} ({elapsed // 60:02d}:{elapsed % 60:02d} elapsed).')
            if hasattr(self, 'stock_action_status'):
                self.stock_action_status.configure(
                    text=tr(f'Steam verification: {phase}. ModDiver is above Steam; shared repair data is downloading.'),
                    foreground=self.theme['accent'])
            self.after(1000, self._poll_steam_verification)

    def _capture_stock_after_steam(self):
        self._steam_capture_after_id = None
        if not self._stock_verify_started:
            return
        self._stock_verify_started = False
        continuation = self._steam_verify_continuation or self._after_stock_capture
        self._capture_stock_then(continuation)

    def _prefetch_repair_data(self):
        """Download shared repair witnesses while Steam Verify is running."""
        import repair_data
        import threading
        folder = core.ROOT / 'builtin' / 'gameplay'
        destination = core.APP_DATA / 'tmp' / 'repair-data-prefetch'
        def work():
            try:
                packages = repair_data.prefetch(folder, destination, progress=self.log)
                self.after(0, lambda: self.log(f'Repair data ready for the next repair ({len(packages)} package(s)).'))
            except Exception as exc:
                message = str(exc)
                self.after(0, lambda: self.log('Repair data prefetch failed: ' + message, 'error'))
        threading.Thread(target=work, daemon=True).start()

    def _after_stock_capture(self):
        self._stock_verify_started = False
        self.btn_capture.configure(text=tr('STEAM VERIFY + CAPTURE STOCK'))
        if hasattr(self, 'stock_action_status'):
            self.stock_action_status.configure(text=tr('Clean stock captured.'), foreground=self.theme['accent'])
        self.refresh_status()

    def _task(self, fn, done):
        if self.busy:
            return
        self.busy = True
        self._task_result = None
        self._task_error = None
        self._set_buttons(False)
        completed = threading.Event()

        def poll():
            if completed.is_set():
                self._set_buttons(True)
                done()
            else:
                self.after(40, poll)

        def work():
            try:
                self._task_result = fn()
            except Exception as exc:
                self._task_error = str(exc)
                if isinstance(exc, core.BuiltinModsUnavailable):
                    self.log('')
                    self.log('')
                    self.log('BUILT-IN MODS NEED TO BE PREPARED BEFORE INSTALLATION:', 'error')
                    self.log('1. Open Mod Creator > Tools > TOOL UPDATES.', 'error')
                    self.log('2. Click UPDATE/REPAIR built-in mods and wait for all selected mods to finish.', 'error')
                    self.log('3. Return to Merge and Install All to try again.', 'error')
                    if exc.instructions:
                        self.log('Details: ' + ' | '.join(exc.instructions), 'error')
                    self.log('')
                    self.log('')
                else:
                    import traceback
                    self.log(f"ERROR: {exc}")
                    self.log(traceback.format_exc())
            finally:
                completed.set()

        threading.Thread(target=work, daemon=True).start()
        self.after(40, poll)

    def _set_buttons(self, on):
        self.busy = not on
        if on:
            self._end_loading('operation')
        else:
            self._begin_loading('operation')
        state = "normal" if on else "disabled"
        for b in (self.btn_install, self.btn_preview, self.btn_capture, self.btn_capture_direct, self.btn_purge, self.btn_export, self.btn_import,
                  self.btn_deploy_clear_log, self.btn_verify,
                  self.btn_purge_library, self.btn_update_builtins, *self.mod_action_buttons, *getattr(self,"mod_toggle_widgets",{}).values(),
                  *(widget for card in getattr(self, "mod_card_widgets", {}).values()
                    for widget in (card.options_widget, card.trash_widget))):
            b.configure(state=state)
        for button in (self.btn_check_chef, self.btn_check_shodan, self.btn_import_ccm, self.btn_import_chef):
            button.configure(state=state)
        self.btn_check_update.configure(state='disabled' if self.busy or self._update_check_active or self._update_install_active else 'normal')

    def install_all(self, dry_run=False):
        if not self.cfg.get('game'):
            messagebox.showinfo(tr(APP_NAME), tr('Choose your Helldivers 2 game folder in Merge and Deploy before continuing.'), parent=self._dialog_parent())
            self._show('deploy')
            return
        if not dry_run and not core.load_deployed() and (not core.STOCK.exists() or not any(core.STOCK.glob('*.dl_bin'))):
            if messagebox.askyesno(tr('Clean stock required'),
                                   tr('Capture clean game files before installing. Open the stock capture tools now?'),
                                   parent=self._dialog_parent()):
                self._show('tools')
            return
        def install():
            if not dry_run and not core.load_deployed():
                import build_archive
                try:
                    build_archive.steam_build(core.game_dir(self.cfg))
                except (OSError, ValueError):
                    pass  # Non-Steam installations retain the existing deployment workflow.
                else:
                    build_archive.ensure_baselines()
            return actions.install_all(self.cfg, self.log, dry_run=dry_run, progress=self.report_progress)
        def finished():
            self.refresh_status()
            if self._task_error is not None:
                return
            if dry_run:
                self.log('Review the preview above. It makes no game file changes.', 'info')
            else:
                self.cfg['first_deploy_complete'] = True
                core.save_config(self.cfg)
        self._task(install, finished)

    def do_purge(self):
        def purged():
            self.refresh_status()
            self.after(100, self._archive_steam_build)
        self._task(lambda: actions.purge(self.cfg, self.log), purged)

    def view_mods_folder(self):
        if self.busy:
            return
        self.busy = True
        self._set_buttons(False)
        self.log("preparing managed Mods folder; existing external sources will be copied, originals kept")

        def work():
            try:
                copied, errors = core.migrate_mod_sources(self.cfg, self.log)
                self._task_result = (copied, errors, None)
            except Exception as exc:
                self._task_result = (0, [], exc)
            self.after(0, self._mods_folder_ready)

        threading.Thread(target=work, daemon=True).start()

    def _mods_folder_ready(self):
        self._set_buttons(True)
        copied, errors, error = self._task_result
        if error:
            messagebox.showerror(tr(APP_NAME), tr(f"Could not prepare the mod library:\n\n{error}"), parent=self._dialog_parent())
            return
        self.log(f"managed Mods folder ready ({copied} existing mod source(s) copied; {len(errors)} could not be copied)", "error" if errors else "info")
        self.refresh_mods()
        self.open_output_folder(core.MODS_DIR)

    def _open_browser(self, url):
        if os.name != 'nt' and os.environ.get('YAO_FORGE_DISTROBOX'):
            core.linux_open(url)
            return True
        return webbrowser.open(url)

    def _center_dialog(self, dialog):
        dialog.update_idletasks()
        width, height = dialog.winfo_reqwidth(), dialog.winfo_reqheight()
        x = self.winfo_rootx() + (self.winfo_width() - width) // 2
        y = self.winfo_rooty() + (self.winfo_height() - height) // 2
        dialog.geometry(f'{width}x{height}+{max(0, x)}+{max(0, y)}')
        self._dark_titlebar(dialog)

    def _dialog_parent(self):
        for panel, bar in reversed(list(self._loading_windows.values())):
            if panel.winfo_exists() and panel.winfo_manager():
                return panel.popup
        grabbed = self.grab_current()
        return grabbed.winfo_toplevel() if grabbed is not None else self

    def _ask_themed(self, title, message, parent=None, cancel_label='Cancel'):
        return self._message_themed(title, message, confirm=True, parent=parent, cancel_label=cancel_label)

    def _message_themed(self, title, message, *, confirm=False, parent=None, cancel_label='Cancel'):
        if confirm:
            return messagebox.askyesno(title, message, parent=parent or self, cancel_label=cancel_label)
        return messagebox.showinfo(title, message, parent=parent or self)

    def _confirm_themed(self, title, message, *, on_confirm=None, confirm_style='Danger.TButton'):
        """Confirm within the app without a native modal window or nested event loop."""
        existing = getattr(self, '_confirmation_panel', None)
        if existing is not None and existing.winfo_exists():
            existing.cancel_button.focus_set()
            return
        previous_focus = self.focus_get()
        overlay = tk.Frame(self, bg=self.theme['bg'])
        self._confirmation_panel = overlay
        overlay.place(x=0, y=0, relwidth=1, relheight=1)
        overlay.lift()
        card = tk.Frame(overlay, bg=self.theme['panel'], bd=0,
                        highlightthickness=1, highlightbackground=self.theme['accent'])
        card.place(relx=.5, rely=.5, anchor='center')
        tk.Label(card, text=title, bg=self.theme['panel'], fg=self.theme['text'],
                 font=('Segoe UI Semibold', 14), anchor='w').pack(fill='x', padx=24, pady=(24, 12))
        tk.Label(card, text=message, bg=self.theme['panel'], fg=self.theme['text'],
                 wraplength=520, justify='left', anchor='w').pack(fill='x', padx=24, pady=(0, 20))
        buttons = ttk.Frame(card)
        buttons.pack(fill='x', padx=24, pady=(0, 24))

        def finish(accepted=False):
            if not overlay.winfo_exists():
                return 'break'
            overlay.grab_release()
            overlay.destroy()
            self._confirmation_panel = None
            if previous_focus is not None and previous_focus.winfo_exists():
                previous_focus.focus_set()
            if accepted and not self.busy:
                on_confirm()
            return 'break'

        cancel = ttk.Button(buttons, text=tr('Cancel' if on_confirm else 'OK'), command=finish)
        cancel.pack(side='right', padx=(8, 0))
        yes = ttk.Button(buttons, text=tr('Yes'), style=confirm_style, command=lambda: finish(True))
        if on_confirm:
            yes.pack(side='right')
        overlay.cancel_button = cancel
        overlay.confirm_button = yes
        # Restrict input to this visible panel. No native window is created.
        overlay.grab_set()
        cancel.focus_set()
        for widget in (overlay, card, buttons, cancel, yes):
            widget.bind('<Escape>', lambda event: finish())
        cancel.bind('<Return>', lambda event: finish())
        yes.bind('<Return>', lambda event: finish(True))

    def _update_notice(self, title, message, parent=None):
        self._confirm_themed(title, message, confirm_style='Accent.TButton')

    def _update_prompt(self, title, message, on_confirm):
        self._confirm_themed(title, message, on_confirm=on_confirm, confirm_style='Accent.TButton')

    def _background_update(self, work, finished, name='Tool update'):
        """Workers handle I/O only; Tk polls and presents results on its own thread."""
        completed = threading.Event()
        result, error = None, None

        def worker():
            nonlocal result, error
            try:
                result = work()
            except Exception as exc:
                error = str(exc)
            finally:
                completed.set()

        def poll():
            if completed.is_set():
                finished(result, error)
            else:
                self.after(40, poll)

        try:
            threading.Thread(target=worker, name=name, daemon=True).start()
        except Exception as exc:
            finished(None, str(exc))
            return
        self.after(40, poll)

    def purge_mod_library(self):
        if self.busy:
            return
        folder = core.MODS_DIR
        self._confirm_themed(
            tr("Completely Purge Mod Library"),
            tr("Permanently delete every imported or captured mod file in this ModDiverLab folder and clear all Mods entries?\n\n"
               f"{folder}\n\n"
               "This does not restore or change game files, deployed mods, Stock snapshots, or deployment backups. "
               "Use Purge All Mods separately if you also want to restore deployed game files."),
            on_confirm=lambda: self._task(lambda: core.purge_mod_library(self.cfg, self.log), self._library_purged))

    def _library_purged(self):
        self.refresh_mods()
        self.refresh_status()

    def do_export(self):
        path = filedialog.asksaveasfilename(defaultextension=".zip", initialfile="ModDiver Library.zip",
                                            filetypes=[("ZIP", "*.zip")], parent=self._dialog_parent())
        if not path:
            return
        self._task(lambda: library_io.export_library(self.cfg, path, self.log), self.refresh_status)

    def do_import_library(self):
        if self.busy:
            return
        path = self._choose_import_source(tr("Import Library"), [("ZIP", "*.zip")])
        if path:
            self._task(lambda: library_io.import_library(self.cfg, path, self.log), self._library_purged)

    def launch_game(self):
        try:
            root = core.hellforge_root(self.cfg)
            if root is not None:
                if os.name == 'nt':os.startfile(str(root / 'HellForge.exe'))
                else:
                    proton = os.environ.get('PROTON')
                    if not proton:raise RuntimeError('Set PROTON to launch HellForge on Linux.')
                    script = root / 'app' / 'linux' / 'hellforge-linux.sh'
                    subprocess.Popen(['bash', str(script), str(root / 'HellForge.exe')], cwd=root)
                self.log('Opened HellForge. Press PLAY in its launcher.')
                return
            core.launch_game()
            self.log("launching Helldivers 2")
        except Exception as exc:
            self.log("launch: " + str(exc))

    def steam_verify(self):
        if not messagebox.askyesno(
                tr("Verify Steam Files"),
                tr("Steam will re-download every changed game file, reverting ALL mods and tools "
                "(Will take some time. If you captured a clean game, you can use that instead).\n\nContinue?"), parent=self._dialog_parent()):
            return
        try:
            core.steam_verify()
            self.log("STEAM VERIFY REQUESTED : GRANTED")
        except Exception as exc:
            self.log("steam: " + str(exc))
    def _page_editor(self, parent):
        return decoder_ui.Decoder(parent, self)

    def _page_tools(self, parent):
        import tools_page
        return tools_page.build(self, parent)

    def _toggle_gameplay_profile(self, key):
        self.cfg[key] = bool(self.gameplay_vars[key].get())
        core.save_config(self.cfg)
        self.log(gameplay_profiles.PROFILES[key] + (' enabled for next installation' if self.cfg[key] else ' disabled for next installation; purge to restore an installed copy'))

    def configure_unlocker(self):
        import hdremix
        existing = choice_screen.active(self)
        if existing is not None:
            return existing
        screen = ResultScreen(self, tr('Hidden Equipment Unlock — HD REMIX 0.5.4'),
                              tr('Choose cosmetic categories for the next Merge and Install All.'))
        values = {}
        for group in hdremix.CATALOG['groups']:
            variable = tk.BooleanVar(master=screen, value=bool(int(self.cfg.get('unlock_groups', 63)) & group['bit']))
            values[group['bit']] = variable
            ttk.Checkbutton(screen.content, text=tr(group['name']), variable=variable).pack(anchor='w', pady=5)
        padding = tk.BooleanVar(master=screen, value=bool(self.cfg.get('unlock_padding', False)))
        ttk.Checkbutton(screen.content, text=tr('Colored B-01 Extra Padding (verifies native passive first)'), variable=padding).pack(anchor='w', pady=10)
        def save():
            self.cfg['unlock_groups'] = sum(bit for bit, var in values.items() if var.get())
            self.cfg['unlock_padding'] = padding.get()
            core.save_config(self.cfg)
            screen.close()
        screen.buttons([('Cancel', None), ('Save Settings', None)])
        screen.option_buttons[1].configure(command=save)
        screen.group_values, screen.padding_value = values, padding
        return screen

    def _scroll_tools(self, event):
        if self.current not in ("tools", "creator") or event.widget.winfo_toplevel() is not self or choice_screen.active(self):
            return
        if getattr(event, "num", None) == 4:
            units = -3
        elif getattr(event, "num", None) == 5:
            units = 3
        elif getattr(event, "delta", 0):
            units = -1 if event.delta > 0 else 1
        else:
            return
        canvas = self.creator_canvas if self.current == "creator" else self.tools_canvas
        canvas.yview_scroll(units, "units")
        return "break"

    def _choose_import_source(self, title, archive_types):
        screen = ResultScreen(self, title, 'Choose an archive or an extracted folder.')
        def pick(folder=False):
            path = (filedialog.askdirectory(parent=screen, title=tr(title)) if folder else
                    filedialog.askopenfilename(parent=screen, title=tr(title), filetypes=archive_types))
            if path:
                screen.finish(path)
        screen.buttons([('Cancel', None), ('Choose Folder', None), ('Choose Archive', None)])
        screen.option_buttons[1].configure(command=lambda: pick(True))
        screen.option_buttons[2].configure(command=pick)
        return screen.wait()

    def import_ccm_editor(self):
        if self.busy:
            return
        source = self._choose_import_source(
            "Import Combined Community Mods Update",
            [("ZIP archives", "*.zip"), ("All files", "*.*")])
        if not source:
            return
        self._import_editor_package(source, "ccm")

    def _import_editor_package(self, source, expected_kind):
        if self.busy:
            return
        label = 'SHODAN Stat Editor' if expected_kind == 'shodan' else 'Combined Community Mods'
        self._set_buttons(False)
        self.report_progress(f'Importing {label}', 0, 0)
        self.log(f'importing {label} package: {source}')

        def finished(result, error):
            self._set_buttons(True)
            if error:
                self.log(f'{label} import failed: {error}', 'error')
                self._update_notice(tr(APP_NAME), tr(f'{label} import failed:\n\n{error}'))
                return
            kind, destination = result
            self.log(f'imported {label} to {destination}')
            self._update_notice(tr(APP_NAME), tr(f'{label} is now the active editor.\n\nImported to:\n{destination}'))

        self._background_update(lambda: core.import_editor(source, expected_kind=expected_kind), finished)

    def import_new_loader(self):
        if self.busy:
            return
        source = self._choose_import_source(
            "Import New Loader",
            [("Loader archives", "*.zip *.7z"), ("ZIP archives", "*.zip"),
             ("7-Zip archives", "*.7z"), ("All files", "*.*")])
        if source:
            self._add_paths([source], loader_import=True)

    def _current_shodan_version(self):
        editor_root = Path(core.EDITOR)
        for candidate in (editor_root / "app" / "build.txt", editor_root / "README.txt"):
            try:
                content = candidate.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            match = re.search(r"(?im)^\s*(?:version\s*=\s*v?|SHODAN Stat Editor Offline v)(\d+(?:\.\d+)+)", content)
            if match:
                return tuple(int(part) for part in match.group(1).split("."))
        return ()

    def check_shodan_editor_update(self):
        self._check_tool_update(shodan_updater, 'SHODAN Stat Editor',
                                self._current_shodan_version, self._download_shodan_release)

    def _check_tool_update(self, service, label, current_version, download):
        if self.busy:
            return
        self._set_buttons(False)
        self.report_progress(f'Checking {label} for updates', 0, 0)
        self.log(f'checking GitHub for a {label} update')

        def work():
            release = service.latest_release()
            latest = self._version_tuple(release['version'])
            if not latest:
                raise ValueError('The release has no valid version.')
            return release, latest, current_version()

        def checked(result, error):
            self._set_buttons(True)
            if error:
                self.log(f'{label} update check failed: {error}', 'error')
                self._update_notice(tr(APP_NAME), tr(f'Could not check GitHub for {label} updates:\n\n{error}'))
                return
            release, latest, current = result
            length = max(len(latest), len(current))
            if current and latest + (0,) * (length-len(latest)) <= current + (0,) * (length-len(current)):
                self.log(f'{label} is up to date ({release["version"]})')
                self._update_notice(tr(APP_NAME), tr(f'{label} is up to date.\n\nLatest release: {release["version"]}'))
                return
            self._update_prompt(tr(APP_NAME),
                                tr(f'{label} {release["version"]} is available.\n\nDownload and install it now?'),
                                lambda: download(release))

        self._background_update(work, checked, f'{label} release check')

    def _download_shodan_release(self, release):
        if self.busy:
            return
        self._set_buttons(False)
        self.report_progress('Downloading SHODAN Stat Editor', 0, 0)
        self.log(f'downloading SHODAN Stat Editor {release["version"]}')

        def work():
            # Directory creation and temporary-file failures must also restore the UI.
            core.APP_DATA.mkdir(parents=True, exist_ok=True)
            fd, filename = tempfile.mkstemp(prefix='tool-update-', suffix='.zip', dir=str(core.APP_DATA))
            os.close(fd)
            download_path = Path(filename)
            keep = False
            try:
                shodan_updater.download_release(release, download_path)
                result = core.import_editor(download_path, expected_kind='shodan',
                                            expected_version=self._version_tuple(release['version']))
                installed = self._current_shodan_version()
                if installed and installed != self._version_tuple(release['version']):
                    raise ValueError('The installed package version does not match the GitHub release tag.')
                return result
            finally:
                if not keep:
                    download_path.unlink(missing_ok=True)

        def finished(result, error):
            self._set_buttons(True)
            if error:
                self.log(f'SHODAN Stat Editor update failed: {error}', 'error')
                self._update_notice(tr(APP_NAME), tr(f'SHODAN Stat Editor update failed:\n\n{error}'))
                return
            kind, destination = result
            self.log(f'updated SHODAN Stat Editor to {release["version"]}: {destination}')
            self._update_notice(tr(APP_NAME), tr(f'SHODAN Stat Editor {release["version"]} is now active.\n\n{destination}'))

        self._background_update(work, finished, 'SHODAN Stat Editor download')

    @staticmethod
    def _version_tuple(value):
        match = re.search(r"(?<!\d)(\d+(?:\.\d+)+)", str(value or ""))
        if not match:
            return ()
        return tuple(int(part) for part in match.group(1).split("."))

    def _current_chef_version(self):
        versions = []
        for mod in self.cfg.get("mods", []):
            if not mod.get("enabled") or _loader_family(mod.get("name")) != "chef":
                continue
            version = self._version_tuple(mod.get("name"))
            if version:
                versions.append(version)
        if not versions:
            bundled = core.parse_mod(core.BUILTIN / "chef_loader")
            version = self._version_tuple(bundled.get("name"))
            if version:
                versions.append(version)
        return max(versions) if versions else ()

    def check_chef_loader_update(self):
        self._check_tool_update(chef_updater, 'Chef Shared Loader',
                                self._current_chef_version, self._download_chef_release)

    def _download_chef_release(self, release):
        if self.busy:
            return
        self._set_buttons(False)
        self.report_progress('Downloading Chef Shared Loader', 0, 0)
        self.log(f'downloading Chef Shared Loader {release["version"]}')

        def work():
            # Directory creation and temporary-file failures must also restore the UI.
            core.APP_DATA.mkdir(parents=True, exist_ok=True)
            fd, filename = tempfile.mkstemp(prefix='tool-update-', suffix='.zip', dir=str(core.APP_DATA))
            os.close(fd)
            download_path = Path(filename)
            keep = False
            try:
                chef_updater.download_release(release, download_path)
                package = core.parse_mod(download_path)
                package_version = self._version_tuple(package.get('name'))
                if _loader_family(package.get('name')) != 'chef' or not package.get('targets'):
                    raise ValueError('The downloaded ZIP is not a valid Chef Shared Loader package.')
                if package_version and package_version != self._version_tuple(release['version']):
                    raise ValueError('The downloaded package version does not match the GitHub release tag.')
                keep = True
                return str(download_path)
            finally:
                if not keep:
                    download_path.unlink(missing_ok=True)

        def finished(result, error):
            self._set_buttons(True)
            if error:
                self.log(f'Chef Shared Loader update failed: {error}', 'error')
                self._update_notice(tr(APP_NAME), tr(f'Chef Shared Loader update failed:\n\n{error}'))
                return
            self._add_paths([result], loader_import=True, cleanup_sources=True)

        self._background_update(work, finished, 'Chef Shared Loader download')

    def import_presets(self):
        if self.busy: return
        paths = filedialog.askopenfilenames(
            title=tr("Import SHODAN presets"), parent=self._dialog_parent(),
            filetypes=[("SHODAN preset", "*.txt"), ("All files", "*.*")])
        if not paths:
            return
        dest = core.EDITOR_CFG
        def work():
            dest.mkdir(parents=True, exist_ok=True)
            n = 0
            for p in paths:
                try:
                    shutil.copy2(p, dest / Path(p).name)
                    n += 1
                except Exception as exc:
                    self.log(f"preset {p}: {exc}")
            return n
        def done():
            if self._task_result is not None:
                self.log(f"imported {self._task_result} SHODAN preset(s) to {dest}")
                self._message_themed(APP_NAME, tr(f"Imported {self._task_result} preset(s) into the SHODAN preset folder:\n\n{dest}"))
        self._task(work, done)

    def open_output_folder(self, folder):
        try:
            folder = Path(folder)
            folder.mkdir(parents=True, exist_ok=True)
            if os.name == "nt":
                os.startfile(str(folder))
            else:
                core.linux_open(folder)
        except Exception as exc:
            messagebox.showerror(tr(APP_NAME), tr(f"Could not open folder:\n{folder}\n\n{exc}"), parent=self._dialog_parent())

    def install_chef_loader(self):
        if self.busy:
            return
        # Prefer the newest available package, including previously downloaded
        # loaders that have been disabled or belong to another preset.
        def work():
            bundled_mod = core.parse_mod(core.BUILTIN / 'chef_loader')
            candidates = [bundled_mod]
            for mod in self.cfg.get('mods', []):
                if _loader_family(mod.get('name')) == 'chef' and Path(mod.get('path', '')).exists():
                    candidates.append(mod)
            import lab_storage
            candidates.extend(mod for mod in lab_storage.candidates(self.cfg)
                              if _loader_family(mod.get('name')) == 'chef')
            newest = max(candidates, key=lambda mod: self._version_tuple(mod.get('name')))
            import tool_installations
            tool_installations.replace_chef(self.cfg, newest['path'], self.log)
            return True
        def done():
            self.refresh_mods()
            if self._task_result:
                self._message_themed(APP_NAME, tr("Chef Shared Loader added. Deploy to install it."))
        self._task(work, done)

    def _multiplayer_warning(self):
        enabled = (self.multiplayer_warnings.get() if hasattr(self, 'multiplayer_warnings')
                   else self.cfg.get('show_multiplayer_warning', True))
        if enabled:
            self._message_themed('MULTIPLAYER WARNING',
                'Do not use stat editing mods in Helldivers 2 public multiplayer!\nsee about for more.')

    def open_native_editor(self):
        self._multiplayer_warning()
        return schema_editor.Editor(self)

    def open_editor_ccm(self):
        try:
            import moddiver_editor
            self._multiplayer_warning()
            moddiver_editor.launch(self.cfg.get('game') or None)
            self.log("launched ModDiverEditor")
        except Exception as exc:
            self._message_themed('ModDiverEditor', str(exc))

    def import_moddiver_editor(self):
        if self.busy:
            return
        source = filedialog.askopenfilename(title=tr('Import ModDiverEditor update'),
            parent=self._dialog_parent(), filetypes=[('Editor package', '*.zip')])
        if not source:
            return
        def work():
            import moddiver_editor
            import zipfile
            with zipfile.ZipFile(source) as archive:
                names = {name.split('/', 1)[-1] for name in archive.namelist()}
                if not {'ModDiver Shodan Editor.exe', 'moddiver-linux.py', 'lua51.dll'} <= names:
                    raise ValueError('Choose a complete ModDiverEditor Windows/Linux ZIP.')
            # Keep the bundled package intact; the imported copy belongs to this user.
            target = core.APP_DATA / 'editors/ModDiverEditor.zip'
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            moddiver_editor.PACKAGE = target
            moddiver_editor.prepare()
        def finished(result, error):
            self._set_buttons(True)
            if error:
                self.log(f'ModDiverEditor import failed: {error}', 'error')
                self._update_notice('ModDiverEditor', tr(f'Editor update import failed:\n\n{error}'))
                return
            self.log('Imported ModDiverEditor update')
            self._update_notice('ModDiverEditor', tr('Editor update imported successfully.'))
        self._set_buttons(False)
        self.report_progress('Importing ModDiverEditor', 0, 0)
        self._background_update(work, finished, 'ModDiverEditor import')

    def import_presets_ccm(self):
        if self.busy: return
        paths = filedialog.askopenfilenames(
            title=tr("Import ModDiverEditor presets"), parent=self._dialog_parent(),
            filetypes=[("Preset", "*.ini"), ("All files", "*.*")])
        if not paths:
            return
        dest = core.EDITOR_CCM_PRESETS
        import moddiver_editor
        runtime_dest = moddiver_editor.prepare() / 'app/forge_helper/forge_presets'
        def work():
            dest.mkdir(parents=True, exist_ok=True)
            runtime_dest.mkdir(parents=True, exist_ok=True)
            n = 0
            for p in paths:
                try:
                    name = Path(p).name
                    shutil.copy2(p, dest / name)
                    shutil.copy2(p, runtime_dest / name)
                    n += 1
                except Exception as exc:
                    self.log(f"preset {p}: {exc}")
            return n
        def done():
            if self._task_result is not None:
                self.log(f"imported {self._task_result} ModDiverEditor preset(s)")
                self._message_themed(APP_NAME, tr(f"Imported {self._task_result} preset(s) into ModDiverEditor.\n\nSaved copies:\n{dest}"))
        self._task(work, done)

    def open_editor(self):
        exe = core.EDITOR / "SHODAN Stat Editor Offline.exe"
        if not exe.exists():
            messagebox.showerror(tr(APP_NAME), tr(f"SHODAN Editor not found:\n{exe}"), parent=self._dialog_parent())
            return
        try:
            self._multiplayer_warning()
            subprocess.Popen([str(exe)], cwd=str(core.EDITOR))
            self.log("launched SHODAN stat editor")
        except Exception as exc:
            self.log(f"editor: {exc}")

    def toggle_nomofomo(self):
        self.cfg["nomofomo"] = bool(self.nomofomo_var.get())  # key is read by core.py; do not rename
        core.save_config(self.cfg)
        self.log(f"Unlock Hidden Equipment {'enabled' if self.cfg['nomofomo'] else 'disabled'}")

    def capture_game_mod(self):
        name = simpledialog.askstring(tr("Capture"), tr("Name for the captured editor changes:"),
                                      initialvalue="Stat Editor changes", parent=self._dialog_parent())
        if not name:
            return

        def done():
            self.refresh_mods()
            self.refresh_status()
            m = self._task_result
            if not m:
                return
            lines = ["Captured as a library mod.", "", "Library folder:", str(m.get("path", ""))]
            if m.get("package"):
                lines += ["", "Portable file mod:", m["package"]]
            if m.get("arsenal_package"):
                lines += ["", "Arsenal data pack:", m["arsenal_package"],
                          "", "Arsenal: import the *-Arsenal.zip, enable it, Deploy, "
                          "launch, exit normally, then launch again."]
            if m.get("arsenal_package"):
                lines += ["", "The pack includes the YAO loader; do not enable another "
                          "boot replacement with it."]
            messagebox.showinfo(tr(APP_NAME), tr("\n".join(lines)), parent=self._dialog_parent())

        self._task(lambda: core.capture_game_mod(self.cfg, self.log, name), done)

    # ---------------------------------------------------------------- themes page
    def _page_settings(self, parent):
        outer = ttk.Frame(parent)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)
        header = ttk.Frame(outer)
        header.grid(row=0, column=0, columnspan=2, sticky='ew', pady=(0, 16))
        self.settings_save_button = ttk.Button(header, text=tr('Save Settings'), style='Accent.TButton', command=self.save_settings)
        self.settings_save_button.pack(side='right')
        ttk.Label(header, text=tr('Make Laboratory your own'), style='SettingsTitle.TLabel').pack(anchor='w')
        ttk.Label(header, text=tr('Manage your workspace, appearance and local storage.'), style='Muted.TLabel').pack(anchor='w', pady=(4, 0))
        canvas = tk.Canvas(outer, highlightthickness=0, bg=self.theme['bg'])
        scrollbar = ttk.Scrollbar(outer, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=1, column=0, sticky='nsew')
        scrollbar.grid(row=1, column=1, sticky='ns')
        page = ttk.Frame(canvas, padding=(0, 0, 12, 12))
        window = canvas.create_window((0, 0), window=page, anchor='nw')
        page.columnconfigure((0, 1), weight=1, uniform='settings')
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(window, width=event.width))
        page.bind('<Configure>', lambda _: canvas.configure(scrollregion=canvas.bbox('all')))
        self.settings_canvas = canvas

        def card(title, description, row, column=0, span=1):
            frame = ttk.Frame(page, style='SettingsCard.TFrame', padding=20)
            frame.grid(row=row, column=column, columnspan=span, sticky='nsew', padx=(0, 12) if span == 1 and column == 0 else 0, pady=(0, 14))
            ttk.Label(frame, text=tr(title), style='SettingsTitle.TLabel').pack(anchor='w')
            ttk.Label(frame, text=tr(description), style='Muted.TLabel', wraplength=300 if span == 1 else 760).pack(anchor='w', pady=(4, 16))
            return frame

        preferences = card('Preferences', 'Choose your language and editor prompts.', 0)
        self.os_badge = ttk.Frame(preferences, style='OSBadge.TFrame', padding=(8, 5))
        self.os_badge.pack(anchor='w', pady=(0, 16))
        os_platform = 'linux' if sys.platform.startswith('linux') else 'windows'
        self._settings_platform_icon = platform_icons.make(self, (os_platform,))
        ttk.Label(self.os_badge, image=self._settings_platform_icon, style='OSBadge.TLabel').pack(side='left', padx=(0, 6))
        ttk.Label(self.os_badge, text=maintenance.operating_system(), style='OSBadge.TLabel').pack(side='left')
        ttk.Label(preferences, text=tr('Language')).pack(anchor='w')
        self.language_choice = tk.StringVar(master=self, value=localization.LANGUAGES.get(localization.language(), 'English'))
        self.language_box = ttk.Combobox(preferences, state='readonly', textvariable=self.language_choice,
                                         values=list(localization.LANGUAGES.values()), width=25)
        self.language_box.pack(anchor='w', pady=(6, 6))
        self.language_box.bind('<<ComboboxSelected>>', self._save_language)
        ttk.Label(preferences, text=tr('Changing language restarts the app.'), style='Muted.TLabel', wraplength=300).pack(anchor='w')
        ttk.Separator(preferences).pack(fill='x', pady=16)
        self.multiplayer_warnings = tk.BooleanVar(master=self, value=self.cfg.get('show_multiplayer_warning', True))
        self.multiplayer_warning_check = ttk.Checkbutton(preferences, text=tr('Show multiplayer editor warnings'),
            variable=self.multiplayer_warnings, style='Yellow.TCheckbutton')
        self.multiplayer_warning_check.pack(anchor='w')
        self.automated_updates_repairs = tk.BooleanVar(
            master=self, value=bool(self.cfg.get('automated_updates_repairs_on_start', False)))
        self.automated_updates_repairs_check = ttk.Checkbutton(
            preferences, text=tr('Automated updates and repairs'),
            variable=self.automated_updates_repairs, style='Yellow.TCheckbutton',
            command=self._save_automated_updates_preference)
        self.automated_updates_repairs_check.pack(anchor='w', pady=(8, 0))
        ttk.Label(preferences,
            text=tr('Off by default. At startup, updates the app and available built-in tools, repairs all three built-in mods, then shows a full-screen report.'),
            style='Muted.TLabel', wraplength=300, justify='left').pack(anchor='w', pady=(4, 0))

        self.utilities_section = card('Utilities', 'Window behavior and everyday maintenance.', 0, 1)
        self.fullscreen_on_maximize = tk.BooleanVar(master=self, value=self.cfg.get('fullscreen_on_maximize', False))
        self.fullscreen_check = ttk.Checkbutton(self.utilities_section, text=tr('Fullscreen when maximizing'),
            variable=self.fullscreen_on_maximize, style='Yellow.TCheckbutton', command=self._change_fullscreen_option)
        self.fullscreen_check.pack(anchor='w')
        ttk.Label(self.utilities_section, text=tr('Off by default. Use normal minimize and maximize controls, or enable fullscreen and press Esc to exit.'),
                  style='Muted.TLabel', wraplength=320).pack(anchor='w', pady=(4, 16))
        utility_buttons = ttk.Frame(self.utilities_section)
        utility_buttons.pack(anchor='w', pady=(0, 10))
        self.restart_button = ttk.Button(utility_buttons, text=tr('RESTART THE APP'), style='Update.TButton', command=self._restart_app)
        self.restart_button.pack(side='left', padx=(0, 8))
        self.delete_local_data_button = ttk.Button(utility_buttons, text='DELETE LOCAL DATA', style='Update.TButton', command=self._delete_local_data)
        self.delete_local_data_button.pack(side='left')
        self.delete_local_data_description = ttk.Label(self.utilities_section,
            text='Deletes local settings, mods, backups, and the clean stock baseline. Capture a new clean baseline after restarting.',
            style='Muted.TLabel', wraplength=320)
        self.delete_local_data_description.pack(anchor='w', pady=(0, 16))
        self.shortcut_button = ttk.Button(self.utilities_section, text=tr('GENERATE NEW DESKTOP SHORTCUT'),
                                          style='Shortcut.TButton', command=self.generate_shortcut)
        self.shortcut_button.pack(anchor='w')

        stock_setup = card('Clean Stock Baseline',
                           'Verify the game with Steam, then capture clean stock files. Required for accurate merge, deploy, repair and updates.',
                           1, span=2)
        stock_action_row = ttk.Frame(stock_setup, style='TFrame')
        stock_action_row.pack(fill='x', pady=(0, 8))
        self.stock_action_status = ttk.Label(stock_action_row,
            text=tr('Verify first for the recommended setup, or capture directly only after confirming the game is clean.'),
            style='Muted.TLabel', wraplength=440)
        self.stock_action_status.pack(side='left', fill='x', expand=True, padx=(0, 14))
        self.btn_capture_direct = ttk.Button(stock_action_row, text=tr('My game is clean. Capture.'),
                                             style='Neutral.TButton', command=self._capture_clean_stock_direct)
        self.btn_capture_direct.pack(side='right', padx=(8, 0), ipadx=8, ipady=5)
        self.btn_capture = ttk.Button(stock_action_row, text=tr('STEAM VERIFY + CAPTURE STOCK'),
                                      style='Update.TButton', command=self._merge_deploy_stock_action)
        self.btn_capture.pack(side='right', ipadx=12, ipady=5)
        self.btn_verify = self.btn_capture

        appearance = card('Appearance', 'Choose a preset, fine-tune colors and set comfortable text sizes.', 2, span=2)
        self._page_themes(appearance).pack(fill='both', expand=True)
        uninstall = card('Uninstall', 'Remove this installation and all app data, including protected baseline data.', 3, span=2)
        self.uninstall_button = ttk.Button(uninstall, text='UNINSTALL MODDIVER LAB', style='Danger.TButton', command=self._uninstall_app)
        self.uninstall_button.pack(anchor='w')
        return outer

    def _change_fullscreen_option(self):
        enabled = self.fullscreen_on_maximize.get()
        self.cfg['fullscreen_on_maximize'] = enabled
        core.save_config(self.cfg)
        self._set_fullscreen(enabled)

    def _delete_local_data(self):
        if not self._can_close():
            return
        if self._ask_themed(APP_NAME, tr('Delete local settings, imported mods, backups, and the captured clean stock baseline? You will need to capture clean stock again after restart.'), parent=self):
            self._maintain_installation(uninstall=False)

    def _uninstall_app(self):
        if not self._can_close():
            return
        if self._ask_themed(APP_NAME, 'Uninstall ModDiver Lab and delete all its local data, including settings, mods, backups, repaired mods and archives?', parent=self, cancel_label='No'):
            self._maintain_installation(uninstall=True)

    def _maintain_installation(self, uninstall):
        try:
            plan = maintenance.make_plan(core.APP_DATA, core.ROOT, uninstall=uninstall)
            plan['background'] = self.theme['bg']
            plan['caption'] = self.theme['panel']
            plan['caption_text'] = self.theme['text']
            plan['secondary'] = self.theme['accent']
            maintenance.launch(plan)
        except Exception as exc:
            messagebox.showerror(tr(APP_NAME), str(exc), parent=self._dialog_parent())
            return
        # The helper waits for this process to exit before touching any files.
        self._restart_command = None
        self._close(force=True)

    def _save_language(self, _event=None):
        code = next(code for code, name in localization.LANGUAGES.items() if name == self.language_choice.get())
        previous = self.cfg.get('language', 'en')
        if code == previous:
            return
        if not self._can_close():
            self.language_choice.set(localization.LANGUAGES[previous])
            return
        self.cfg['language'] = code
        self.save_settings()
        self._restart_app(checked=True)

    def _restart_app(self, checked=False):
        if not checked and not self._can_close():
            return
        # Relaunch after main() releases the instance lock, so the new process
        # cannot mistake this closing window for an already running instance.
        self._restart_command = getattr(self, '_update_restart_command', None) or [sys.executable, str(Path(__file__).resolve())]
        self._close(force=True)

    def _scroll_settings(self, event):
        if self.current != 'settings':
            return
        direction = -1 if getattr(event, 'num', 0) == 4 or getattr(event, 'delta', 0) > 0 else 1
        self.settings_canvas.yview_scroll(direction * 3, 'units')
        return 'break'

    def generate_shortcut(self):
        self._ensure_shortcut(force=True)

    def _page_themes(self, parent):
        page = ttk.Frame(parent, style="TFrame")
        page.grid_columnconfigure(0, weight=1)
        ttk.Label(page, text=tr("Presets"), style="Title.TLabel").grid(row=0, column=0, sticky="w")
        presets = ttk.Frame(page, style="TFrame")
        presets.grid(row=1, column=0, sticky="ew", pady=(6, 16))
        presets.columnconfigure((0, 1, 2), weight=1, uniform="presets")
        for i, (name, t) in enumerate(THEMES.items()):
            row, col = divmod(i, 3)
            b = tk.Button(presets, text=tr(name), width=0, height=2, bd=1, relief="solid", cursor="hand2",
                          bg=t["panel"], fg=t["accent"], activebackground=t["panel2"],
                          activeforeground=t["accent"], font=("Segoe UI Semibold", 10),
                          command=lambda n=name: self.apply_preset(n))
            b.grid(row=row, column=col, padx=(0, 8), pady=(0, 9), sticky="ew")
        controls_row = (len(THEMES) + 2) // 3
        ttk.Label(page, text=tr("Accent"), style="Title.TLabel").grid(row=controls_row, column=0, sticky="w")
        sw = ttk.Frame(page, style="TFrame")
        sw.grid(row=controls_row + 1, column=0, sticky="w", pady=(6, 16))
        for c in SWATCHES:
            b = tk.Button(sw, bg=c, width=3, height=1, bd=0, relief="flat", cursor="hand2",
                          command=lambda col=c: self._set_theme(accent=col,
                                                                accent_text="#151a12" if col in ("#ffd400", "#ffffff", "#38d996") else "#ffffff"))
            b.pack(side="left", padx=(0, 6))
        ttk.Label(page, text=tr("Custom colors"), style="Title.TLabel").grid(row=controls_row + 2, column=0, sticky="w")
        custom = ttk.Frame(page, style="TFrame")
        custom.grid(row=controls_row + 3, column=0, sticky="w", pady=(6, 10))
        for key, label in (("bg", "Background"), ("panel", "Panel"), ("text", "Text"), ("accent", "Accent")):
            ttk.Button(custom, text=tr(label), command=lambda k=key: self.pick_color(k)).pack(side="left", padx=(0, 8))
        ttk.Label(page, text=tr("Font size"), style="Title.TLabel").grid(row=controls_row + 4, column=0, sticky="w", pady=(8, 0))
        self.font_scale = tk.Scale(page, from_=8, to=16, orient="horizontal", length=260,
                                   showvalue=True)
        self.font_scale.set(self.theme.get("font", 10))
        self.font_scale.configure(command=lambda v: self._set_theme(font=int(float(v))))
        self.font_scale.grid(row=controls_row + 5, column=0, sticky="w")
        bar = ttk.Frame(page, style="TFrame")
        ttk.Label(page, text=tr("Log font size"), style="Title.TLabel").grid(row=controls_row + 6, column=0, sticky='w', pady=(8, 0))
        self.log_font_scale = tk.Scale(page, from_=9, to=24, orient='horizontal', length=260, showvalue=True)
        self.log_font_scale.set(self.theme.get('log_font', 12))
        self.log_font_scale.configure(command=lambda v: self._set_theme(log_font=int(float(v))))
        self.log_font_scale.grid(row=controls_row + 7, column=0, sticky='w')
        bar.grid(row=controls_row + 8, column=0, sticky="w", pady=(14, 0))
        ttk.Button(bar, text=tr("Reset"), command=self.apply_reset).pack(side="left")
        return page

    def apply_preset(self, name):
        base = dict(core.DEFAULT_THEME)
        base.update(THEMES[name])
        base["preset"] = name
        self.theme = base
        self.apply_theme()

    def pick_color(self, key):
        color = colorchooser.askcolor(color=self.theme.get(key), title=tr(f"Pick {key}"), parent=self._dialog_parent())[1]
        if color:
            self._set_theme(**{key: color})

    def save_settings(self):
        self.cfg['theme'] = dict(self.theme)
        self.cfg['show_multiplayer_warning'] = self.multiplayer_warnings.get()
        self.cfg['fullscreen_on_maximize'] = self.fullscreen_on_maximize.get()
        if hasattr(self, 'startup_updates'):
            self.cfg['check_updates_on_start'] = self.startup_updates.get()
        if hasattr(self, 'automated_updates_repairs'):
            self.cfg['automated_updates_repairs_on_start'] = self.automated_updates_repairs.get()
        self.cfg['language'] = next(code for code, name in localization.LANGUAGES.items()
                                    if name == self.language_choice.get())
        core.save_config(self.cfg)
        self.log('settings saved')

    def _save_automated_updates_preference(self):
        self.cfg['automated_updates_repairs_on_start'] = self.automated_updates_repairs.get()
        core.save_config(self.cfg)

    def apply_reset(self):
        self.theme = dict(core.DEFAULT_THEME)
        self.apply_theme()

    # ---------------------------------------------------------------- log / about
    def _page_log(self, parent):
        page = ttk.Frame(parent, style="TFrame")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)
        bar = ttk.Frame(page, style="TFrame")
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(bar, text=tr("Clear Log"), command=self.clear_log).pack(side="left")
        ttk.Button(bar,text=tr("Copy Log"),command=self.copy_log).pack(side="left",padx=6)
        self.log_text = ReportView(page, background_folder='wordmark_background', wrap="word", font=("Consolas", 9))
        self.log_text.grid(row=1, column=0, sticky="nsew")
        sb = ttk.Scrollbar(page, orient="vertical", command=self.log_text.yview)
        sb.grid(row=1, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=sb.set, state="disabled")
        self.texts.append(self.log_text)
        return page

    def _page_about(self,parent):
        page=ttk.Frame(parent);page.columnconfigure(0,weight=1);page.rowconfigure(3,weight=1)
        nav=ttk.Frame(page);nav.grid(row=2,column=0,columnspan=2,sticky='ew',pady=(0,8))
        ttk.Label(nav,text=tr('Guide section')).pack(side='left')
        chooser=ttk.Combobox(nav,state='readonly',width=38,values=[title for title,_ in about_content.sections(localization.language())])
        chooser.pack(side='left',padx=8);chooser.current(0)
        self.about_query=tk.StringVar(master=self)
        query=ttk.Entry(nav,textvariable=self.about_query,width=22);query.pack(side='left',fill='x',expand=True)
        query.bind('<Return>',lambda _:self._find_about())
        ttk.Button(nav,text=tr('Find next'),command=self._find_about).pack(side='left',padx=6)
        text=tk.Text(page,wrap='word',bd=0,highlightthickness=0,font=('Segoe UI',10),padx=16,pady=12,cursor='arrow',spacing1=2,spacing3=4)
        text.grid(row=3,column=0,sticky='nsew')
        scroll=ttk.Scrollbar(page,command=text.yview);scroll.grid(row=3,column=1,sticky='ns');text.configure(yscrollcommand=scroll.set)
        text.tag_configure('h1',font=('Segoe UI',24,'bold'),spacing3=8)
        text.tag_configure('sub',font=('Segoe UI',11),spacing3=12)
        text.tag_configure('h2',font=('Segoe UI',13,'bold'),spacing1=18,spacing3=8)
        text.tag_configure('warning', foreground='#ff3333', font=('Segoe UI', 11, 'normal'), spacing3=12)
        text.tag_configure('body',font=('Segoe UI',10),spacing3=6)
        text.tag_configure('search',background='#ffe600',foreground='#111111')
        marks={}
        for chunk,tag in about_content.blocks(VERSION, localization.language()):
            if tag=='h2':
                mark='section_'+str(len(marks));text.mark_set(mark,'end-1c');text.mark_gravity(mark,'left');marks[chunk.strip()]=mark
            if tag == 'h1': chunk = tr('User guide') + '\n'
            if tag == 'sub': chunk = tr('Version ') + VERSION + ' • ' + tr('Setup, mod options and reference') + '\n\n'
            text.insert('end',chunk,tag)
        chooser.bind('<<ComboboxSelected>>',lambda _:text.see(marks[chooser.get()]))
        text.configure(state='disabled');self.about_text=text;self.texts.append(text)
        updates=ttk.Frame(page,style='Panel.TFrame',padding=12);updates.grid(row=1,column=0,columnspan=2,sticky='ew',pady=(8,0))
        self.btn_check_update=ttk.Button(updates,text=tr('Check for Updates'),style='Update.TButton',command=lambda:self._check_for_updates(manual=True))
        self.btn_check_update.pack(side='left')
        ttk.Button(updates,text=tr('Release Downloads'),command=lambda:self._open_browser('https://github.com/'+updater.REPOSITORY+'/releases/latest')).pack(side='left',padx=6)
        ttk.Button(updates,text=tr('Open App Data'),command=lambda:self.open_output_folder(core.APP_DATA)).pack(side='left')
        self.btn_restart_update=ttk.Button(updates,text=tr('Restart to Update'),style='Accent.TButton',command=self._restart_updated_app)
        self.startup_updates=tk.BooleanVar(master=self, value=self.cfg.get('check_updates_on_start',True))
        ttk.Checkbutton(page,text=tr('Check for app updates every time the app starts'),variable=self.startup_updates,command=self._save_update_preference).grid(row=4,column=0,sticky='w',pady=5)
        progress=ttk.Frame(page);progress.grid(row=5,column=0,columnspan=2,sticky='ew');progress.columnconfigure(0,weight=1)
        self.update_status=ttk.Label(progress,text='',style='Muted.TLabel')
        self.update_status.grid(row=0,column=0,sticky='w')
        self.update_progress=LoadingBar(progress, self.theme['bg']);self.update_progress.grid(row=0,column=1,padx=(8,0))
        self.update_progress.grid_remove()
        support=ttk.Frame(page);support.grid(row=6,column=0,columnspan=2,sticky='ew',pady=(10,0))
        ttk.Button(support,text=tr('SUPPORT'),style='Support.TButton',command=self.open_support_page).pack(side='right')
        return page

    def _find_about(self):
        text=self.about_text;query=self.about_query.get().strip()
        previous=text.tag_ranges('search');start=str(previous[-1]) if previous else '1.0'
        text.tag_remove('search','1.0','end')
        if not query:return
        found=text.search(query,start,stopindex='end',nocase=True) or text.search(query,'1.0',stopindex=start,nocase=True)
        if found:
            text.tag_add('search',found,f'{found}+{len(query)}c');text.see(found)
        else:self.status.configure(text=tr('No matching guide text: '+query))

    def _save_update_preference(self):
        self.cfg['check_updates_on_start']=self.startup_updates.get();core.save_config(self.cfg)

    def open_support_page(self):
        existing = choice_screen.active(self)
        if existing is not None:
            return existing
        screen = choice_screen.ChoiceScreen(self)
        frame = ttk.Frame(screen.card, style='SupportDialog.TFrame', padding=24)
        frame.pack(fill='both', expand=True, padx=1, pady=1)
        ttk.Label(frame, text=tr('Thank you!'), style='SupportTitle.TLabel').pack(pady=(2, 8))
        ttk.Label(frame, text=tr('Which one works best for you?'), style='SupportBody.TLabel').pack(pady=(0, 8))
        ttk.Label(frame, text=tr('Support is completely optional. ModDiver Lab will forever be free and open-source.'),
                  style='SupportBody.TLabel', wraplength=360, justify='center').pack(pady=(0, 18))
        buttons = ttk.Frame(frame, style='SupportDialog.TFrame')
        buttons.pack(fill='x')

        def open_link(url):
            try:
                if not self._open_browser(url):
                    raise RuntimeError(tr('No web browser could be opened.'))
                screen.close()
            except Exception as exc:
                screen.error.set(tr(f'Could not open the support page:\n\n{exc}'))

        screen.support_buttons = []
        for label, style, url in (('Patreon', 'Patreon.TButton', 'https://www.patreon.com/cw/YaoDev'),
                                   ('Ko-fi', 'Accent.TButton', 'https://ko-fi.com/yaodev')):
            button = ttk.Button(buttons, text=tr(label), style=style, command=lambda link=url: open_link(link))
            button.pack(side='left', expand=True, fill='x', padx=6)
            screen.support_buttons.append(button)
        ttk.Label(frame, textvariable=screen.error, wraplength=360, style='SupportBody.TLabel').pack(fill='x')
        screen.cancel_button = ttk.Button(frame, text=tr('Cancel'), command=screen.close)
        screen.cancel_button.pack(pady=(14, 0))
        screen.cancel_button.bind('<Return>', screen.close)
        screen.activate(screen.cancel_button)
        return screen

    def _automatic_update_check(self):
        if self.cfg.get('automated_updates_repairs_on_start', False):
            self._automatic_update_and_repair()
            return
        if not self.cfg.get("check_updates_on_start",True):
            return
        self.cfg["update_check_timestamp"] = time.time()
        core.save_config(self.cfg)
        self._check_for_updates(manual=False)

    def _check_for_updates(self, manual=False):
        if self.busy:
            if manual:
                self._update_notice(tr(APP_NAME), tr('Finish the current operation, then check for updates again.'))
            else:
                self.after(500, lambda: self._check_for_updates(manual=False))
            return
        if self._update_check_active or self._update_install_active:
            if manual:
                self._update_notice(tr(APP_NAME), tr("An update operation is already in progress."))
            return
        if manual:
            self.cfg["update_check_timestamp"] = time.time()
            core.save_config(self.cfg)
        self._update_check_active = True
        self.btn_check_update.configure(state="disabled")
        self.update_status.configure(text=tr("Checking for a newer stable release…"))

        self._background_update(lambda: updater.find_update(VERSION),
                                lambda release, error: self._update_check_finished(manual, release, error),
                                'ModDiver update check')

    def _update_check_finished(self, manual, release, error):
        panel = getattr(self, '_confirmation_panel', None)
        if self.busy or (panel is not None and panel.winfo_exists()) or choice_screen.active(self) is not None:
            self.after(250, lambda: self._update_check_finished(manual, release, error))
            return
        self._update_check_active = False
        self.btn_check_update.configure(state="normal")
        if error is not None:
            self.log("update check failed: " + str(error),"error")
            self.update_status.configure(text=tr("Could not check for updates. Try again or use Release Downloads."))
            if manual:
                self._update_notice(tr(APP_NAME), tr(f"Could not check for updates:\n\n{error}"))
            return
        if release is None:
            self.update_status.configure(text=tr(f"You have the latest available stable version (v{VERSION})."))
            if manual:
                self._update_notice(tr(APP_NAME), tr(f"ModDiver Laboratory is up to date! (v{VERSION})."))
            return

        self.update_status.configure(text=tr(f"Version {release['version']} is available."))
        prompt = (f"ModDiver Laboratory v{release['version']} is available.\n\n"
                  f"You have v{VERSION}. Download and install the update now?")
        self._update_prompt(tr(APP_NAME), tr(prompt), lambda: self._download_update(release))

    def _download_update(self,release):
        if self.busy:
            self._update_notice(tr(APP_NAME),tr('Finish the current operation, then check for updates again.'),parent=self);return
        exe=os.environ.get('YAO_FORGE_EXE');bootstrap=os.environ.get('YAO_FORGE_BOOTSTRAP')
        data_dir=os.environ.get('YAO_FORGE_DATA')
        if not data_dir or not (exe or bootstrap):
            self._update_notice(tr(APP_NAME),tr('Start with ModDiver Laboratory.exe on Windows or run-linux.sh on Linux to install updates here. Use Release Downloads for the full package.'),parent=self)
            self.update_status.configure(text=tr('Use the launcher for in-app installation, or choose Release Downloads.'));return
        try:launcher_api=int(os.environ.get('YAO_FORGE_LAUNCHER_API') or 1)
        except ValueError:launcher_api=1
        command=[exe] if exe else [sys.executable,bootstrap]
        self._update_install_active=True;self._set_buttons(False);self.btn_check_update.configure(state='disabled')
        self.update_progress.grid();self.update_progress.configure(value=0);self.update_status.configure(text=tr('Starting update download…'))
        self.log(f"Downloading ModDiver Laboratory {release['version']}")
        def progress(phase,done,total):
            self.report_progress(phase,done,total)
        self._background_update(
            lambda: updater.install_update(release, data_dir, launcher_api, progress=progress),
            lambda result, error: self._update_install_finished(release, command, error),
            'ModDiver update download')

    def _show_update_progress(self,phase,done,total):
        percent=100*done/max(total,1)
        self.update_progress.grid()
        self.update_progress.stop()
        self.update_progress.configure(value=percent, caption=phase)
        for panel, bar in self._loading_windows.values():
            if panel.winfo_exists():
                bar.stop()
                bar.configure(value=percent, caption=phase)
        detail=f'{done/1048576:.1f} / {total/1048576:.1f} MB' if phase=='Downloading' else f'{percent:.0f}%'
        self.update_status.configure(text=tr(f'{phase} — {detail}'))

    def _update_install_finished(self,release,command,error):
        self._update_install_active=False;self._set_buttons(True);self.btn_check_update.configure(state='normal')
        self.update_progress.grid_remove()
        if error:
            self.log('Update failed: '+str(error),'error');self.update_status.configure(text=tr('Update failed. Your current version is still active; see Log.'))
            self._update_notice(tr(APP_NAME),tr(f'The update could not be installed:\n\n{error}'),parent=self);return
        self._update_restart_command=command
        self.btn_restart_update.pack(side='left',padx=6)
        self.update_status.configure(text=tr(f"Version {release['version']} installed. Restart when ready."))
        self.log(f"Updated to {release['version']}; restart to use it.",'success')
        self._update_prompt(tr(APP_NAME), tr('Update installed. Restart ModDiver Laboratory now?'), self._restart_updated_app)

    def _restart_updated_app(self):
        if getattr(self, '_update_restart_command', None):
            self._restart_app()

    # ---------------------------------------------------------------- log plumbing
    def log(self, msg, level=None):
        self.log_queue.put(log_events.Message(msg,level or log_events.classify(msg)))

    def _drain(self):
        progress, self._progress_latest = self._progress_latest, None
        if progress:
            phase, done, total = progress
            if self._update_install_active:
                self._show_update_progress(phase, done, total)
            else:
                for panel, bar in self._loading_windows.values():
                    if panel.winfo_exists() and panel.winfo_manager():
                        if total:
                            bar.stop()
                        else:
                            bar.start()
                        bar.configure(value=100*done/total if total else None, caption=phase)
        pending = []
        for _ in range(60):
            try:
                msg = self.log_queue.get_nowait()
            except queue.Empty:
                break
            line = ("\n" if not str(msg).strip() else f"[{time.strftime('%H:%M:%S')}] {msg}\n")
            pending.extend((line, log_events.classify(msg)))
        if pending:
            for w in (getattr(self, "deploy_log", None), getattr(self, "log_text", None)):
                if w is not None:
                    try:
                        w.configure(state="normal")
                        w.insert("end", *pending)
                        if int(w.index('end-1c').split('.')[0]) > 5000:
                            w.delete('1.0', '1000.0')
                        w.see("end")
                        w.configure(state="disabled")
                    except tk.TclError:
                        pass
            if choice_screen.active(self) is None:
                try:
                    self.status.configure(text=tr(msg[:140]))
                except tk.TclError:
                    pass
        self.after(120, self._drain)

    def refresh_status(self):
        self._refresh_deployment_outlines()
        root = core.hellforge_root(self.cfg)
        if root is not None:
            import hellforge
            count = len(hellforge.load_receipt(root)['mods'])
            self.stock_label.configure(text=tr('HellForge manages game files'))
            self.deployed_label.configure(text=tr(f'   Deployed: {count} packages'))
            self.stock_count_label.configure(text=tr('HELLFORGE'))
            self.stock_number_label.configure(text=str(count), style='Chip.TLabel')
            self.deployed_count_label.configure(text=tr('MODS'))
            self.btn_capture.configure(state='disabled')
            self.btn_capture_direct.configure(state='disabled')
            self.btn_verify.configure(state='disabled')
            return
        if not self.busy:
            self.btn_capture.configure(state='normal')
            self.btn_capture_direct.configure(state='normal')
            self.btn_verify.configure(state='normal')
        stock = len(list(core.STOCK.glob("*.dl_bin"))) if core.STOCK.exists() else 0
        deployed = len(core.load_deployed())
        self.stock_label.configure(text=tr(f"Stock: {stock} files" if stock else "Stock: not captured"))
        self.deployed_label.configure(text=tr(f"   Deployed: {deployed}"))
        self.stock_count_label.configure(text=tr('STOCK'))
        self.stock_number_label.configure(text=str(stock), style=(
            'StockGood.Chip.TLabel' if stock == core.REQUIRED_STOCK_FILES else 'StockBad.Chip.TLabel'))
        self.deployed_count_label.configure(text=tr(f'· DEPLOYED {deployed}'))

    def _can_close(self):
        editors=[*self.winfo_children(),self.pages.get('editor')]
        if any(token != 'startup' for token in self._loading_tokens) or self.busy or self._update_install_active or any(getattr(w,'busy',False) is True for w in editors if w is not None):
            messagebox.showinfo(tr(APP_NAME),tr('Wait for the current operation to finish before closing.'),parent=self._dialog_parent());return False
        if self.editor_proc is not None and self.editor_proc.poll() is None:
            messagebox.showinfo(tr(APP_NAME),tr('Close the external editor before closing or restarting Laboratory.'),parent=self._dialog_parent());return False
        for child in editors:
            document=getattr(child,'document',getattr(child,'archive',None))
            data=getattr(document,'data',document)
            pending=getattr(data,'replacements',None)
            if isinstance(child,decoder_ui.Decoder) and child.current is not None and child.editor.cget('state')!='disabled':
                pending=pending or child.editor.get('1.0','end-1c')!=child.rendered
            if isinstance(child, asset_editor.Editor):
                pending = child.has_unsaved_changes()
            if pending:
                return messagebox.askyesno(tr(APP_NAME),tr('An editor has unsaved changes. Discard them and close?'),parent=self._dialog_parent())
        return True

    def _close(self,force=False):
        if not force and not self._can_close():return
        self._cancel_mod_drag()
        try:
            core.save_config(self.cfg)
        finally:
            if self.editor_proc is not None and self.editor_proc.poll() is None:
                self.editor_proc.terminate()
                try:
                    self.editor_proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.editor_proc.kill()
            self.destroy()

    def _ensure_shortcut(self, force=False):
        if os.name != "nt":
            if force:
                self._linux_shortcut()
            return
        if self.cfg.get("shortcut_v2") and self.cfg.get('shortcut_brand') == 'hex-v1' and not force:
            return
        exe = os.environ.get("YAO_FORGE_EXE")
        if not exe or not Path(exe).exists():
            if force:
                messagebox.showerror(tr(APP_NAME), tr('Start the app using ModDiver Laboratory.exe to create its desktop shortcut.'), parent=self._dialog_parent())
            return
        try:
            shortcut_icon = core.APP_DATA / 'moddiver_badge_hex.ico'
            core.APP_DATA.mkdir(parents=True, exist_ok=True)
            shutil.copy2(core.ROOT / 'icon.ico', shortcut_icon)
            ps = ("$ws=New-Object -ComObject WScript.Shell; "
                  "$s=$ws.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'ModDiver Laboratory.lnk')); "
                  "$s.TargetPath='" + exe.replace("'", "''") + "'; "
                  "$s.WorkingDirectory='" + str(Path(exe).parent).replace("'", "''") + "'; "
                  "$s.IconLocation='" + str(shortcut_icon).replace("'", "''") + "'; "
                  "$s.Save()")
            subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           creationflags=0x08000000, timeout=30, check=True, capture_output=True)
            self.cfg["shortcut_v2"] = True
            self.cfg['shortcut_brand'] = 'hex-v1'
            core.save_config(self.cfg)
            self.log("desktop shortcut created")
            if force:
                messagebox.showinfo(tr(APP_NAME), tr('Desktop shortcut created.'), parent=self._dialog_parent())
        except Exception as exc:
            self.log("shortcut: " + str(exc))
            if force:
                messagebox.showerror(tr(APP_NAME), tr(str(exc)), parent=self._dialog_parent())

    def _linux_shortcut(self):
        bootstrap = os.environ.get('YAO_FORGE_BOOTSTRAP')
        if not bootstrap or not Path(bootstrap).is_file():
            messagebox.showerror(APP_NAME, tr('Start with run-linux.sh to create a desktop shortcut.'), parent=self._dialog_parent())
            return
        try:
            desktop = Path.home() / 'Desktop'
            if shutil.which('xdg-user-dir'):
                result = subprocess.run(['xdg-user-dir', 'DESKTOP'], capture_output=True, text=True, check=True, timeout=5)
                if result.stdout.strip():
                    desktop = Path(result.stdout.strip())
            desktop.mkdir(parents=True, exist_ok=True)
            icon = core.APP_DATA / 'moddiver_badge_hex.png'
            shutil.copy2(core.ROOT / 'branding/icon_256.png', icon)
            def quote(value):
                return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%') + '"'
            command = f'{quote(sys.executable)} {quote(Path(bootstrap).resolve())}'
            container = os.environ.get('YAO_FORGE_DISTROBOX')
            if container:
                command = ('distrobox enter --name ' + quote(container) + ' -- env ' +
                           quote('YAO_FORGE_DISTROBOX=' + container) + ' ' + command)
            entry = desktop / 'ModDiver Laboratory.desktop'
            entry.write_text('[Desktop Entry]\nType=Application\nName=ModDiver Lab\n'
                             f'Exec={command}\n'
                             f'Icon={icon}\nTerminal=false\nCategories=Game;Utility;\n', encoding='utf-8')
            entry.chmod(0o755)
            messagebox.showinfo(APP_NAME, tr('Desktop shortcut created. Your desktop may ask you to allow launching it.'), parent=self._dialog_parent())
        except Exception as exc:
            self.log('shortcut: ' + str(exc), 'error')
            messagebox.showerror(APP_NAME, str(exc), parent=self._dialog_parent())

    def copy_log(self):
        self.clipboard_clear();self.clipboard_append(self.log_text.get("1.0","end-1c"))
        self.status.configure(text=tr("Log copied to clipboard."))

    def clear_log(self):
        for w in (getattr(self, "deploy_log", None), getattr(self, "log_text", None)):
            if w is not None:
                w.configure(state="normal")
                w.delete("1.0", "end")
                w.configure(state="disabled")

    def destroy(self):
        # Pending titlebar/theme callbacks must not outlive their Tk widgets.
        for token in self.tk.call('after', 'info'):
            self.tk.call('after', 'cancel', token)
        super().destroy()


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--lua-runner":
        import lua_runner
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        raise SystemExit(lua_runner.main())
    lock = single_instance.InstanceLock(core.APP_DATA)
    if not lock.acquire():
        return
    try:
        app = App()
        app.mainloop()
    finally:
        lock.release()
    command = getattr(app, '_restart_command', None)
    if command:
        try:
            subprocess.Popen(command, cwd=str(Path(command[-1]).parent), close_fds=True)
        except Exception as exc:
            messagebox.showerror(tr(APP_NAME), tr(f'Could not restart the app:\n\n{exc}'), parent=self._dialog_parent())


if __name__ == "__main__":
    main()



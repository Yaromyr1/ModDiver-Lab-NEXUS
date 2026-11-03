"""Tools flight deck: focused actions, saved custom slots and responsive cards."""
import copy
from pathlib import Path
import tkinter as tk
from tkinter import ttk

import core
import nexus_mode
import custom_tools
import gameplay_profiles
import ui_polish
from localization import tr
from panel_dialogs import ResultScreen, filedialog

DESCRIPTIONS = {
    'nomofomo': 'Bring hidden armor, helmets and capes into your loadout. Choose the cosmetic categories you want to reveal.',
    'stratagem_bounce_removed': 'Keep stratagem beacons where they land for more predictable placement on the battlefield.',
    'consistent_vaulting': 'Climb over obstacles more reliably, with smoother vaulting from slopes and uneven ground.',
}


def build(app, parent):
    page = ttk.Frame(parent)
    page.rowconfigure(0, weight=1)
    page.columnconfigure(0, weight=1)
    canvas = app.tools_canvas = tk.Canvas(page, highlightthickness=0, borderwidth=0, bg=app.theme['bg'])
    scroll = ttk.Scrollbar(page, orient='vertical', command=canvas.yview)
    canvas.configure(yscrollcommand=scroll.set)
    canvas.grid(row=0, column=0, sticky='nsew')
    scroll.grid(row=0, column=1, sticky='ns')
    body = ttk.Frame(canvas, padding=(0, 0, 8, 24))
    body.columnconfigure(0, weight=1)
    window = canvas.create_window((0, 0), window=body, anchor='nw')
    body.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
    canvas.bind('<Configure>', lambda e: canvas.itemconfigure(window, width=e.width))

    def label(parent, text, muted=False, size=None):
        widget = ttk.Label(parent, text=tr(text), style='PanelMuted.TLabel' if muted else 'Panel.TLabel',
                           wraplength=700, justify='left')
        if size:
            widget.configure(font=('Segoe UI Semibold', size))
        widget.pack(anchor='w', fill='x', pady=(0, 8))
        def wrap(e):
            width = max(100, e.width-44)
            if getattr(widget, '_wrap_width', None) != width:
                widget._wrap_width = width
                widget.configure(wraplength=width)
        parent.bind('<Configure>', wrap, add='+')
        return widget

    def card(parent, eyebrow, title, description, platforms=()):
        frame = ttk.Frame(parent, style='Panel.TFrame', padding=22)
        label(frame, eyebrow, True, 9)
        title_label = label(frame, title, size=16)
        if platforms:
            import platform_icons
            title_label.configure(image=platform_icons.make(app, platforms), compound='right')
        label(frame, description, True)
        return frame

    def button(parent, text, action, primary=False, style=None):
        widget = ttk.Button(parent, text=tr(text), command=action,
                            style=style or ('Yellow.TButton' if primary else 'TButton'))
        if primary:
            widget._semantic_role = 'primary'
            widget.configure(style=ui_polish.ACTION_STYLES['primary'])
        if text in ('Import presets', 'Import loader update', 'Capture as mod', 'Armory presets', 'Saved presets', 'Mod Library'):
            widget._semantic_role = 'secondary'
            widget.configure(style=ui_polish.ACTION_STYLES['secondary'])
        widget.pack(side='left', padx=(0, 8), pady=(4, 4))
        return widget

    def actions(frame):
        row = ttk.Frame(frame, style='Panel.TFrame')
        row.pack(anchor='w', fill='x', pady=(6, 0))
        return row

    def section(row, number, title, hint):
        header = ttk.Frame(body, padding=(2, 18, 0, 10))
        header.grid(row=row, column=0, sticky='ew')
        ttk.Label(header, text=number + '  /  ' + tr(title), style='SettingsTitle.TLabel').pack(anchor='w')
        ttk.Label(header, text=tr(hint), style='Muted.TLabel', wraplength=760).pack(anchor='w', pady=(4, 0))

    hero = card(body, 'MODDIVER LABORATORY  /  TOOL DECK', 'Your tools. One launchpad.',
                'Launch an editor, connect your own tools, or prepare your next loadout.')
    hero.grid(row=0, column=0, sticky='ew')
    rail = actions(hero)
    button(rail, 'My custom tools', lambda: canvas.yview_moveto(custom.winfo_y()/max(1, body.winfo_height())), True)
    button(rail, 'Open Mod Creator', lambda: app._show('creator'))
    app.hellforge_tools_note = ttk.Label(hero, text='', style='PanelMuted.TLabel', wraplength=900)
    app.hellforge_tools_note.pack(fill='x', pady=(8, 0))
    section(1, '01', 'Custom tools', 'Your personal kit. Name a slot now, connect a file whenever you are ready.')
    custom = ttk.Frame(body)
    custom.grid(row=2, column=0, sticky='ew')
    app.custom_tools_section = custom

    def render_custom():
        for child in custom.winfo_children():
            child.destroy()
        records = app.cfg.get('custom_tools', [])
        for index, record in enumerate(records):
            path = record.get('path', '')
            is_loader = record.get('kind') == 'loader'
            status = ('LOADER PACKAGE' if is_loader else 'EXECUTABLE / SCRIPT') if path else 'READY TO CONNECT'
            frame = card(custom, f'{index+1:02d}  /  {status}', record['name'],
                         str(path) if path else 'Choose an executable, script, shortcut or loader package.')
            frame.pack(fill='x', pady=(0, 10))
            row = actions(frame)
            if path:
                button(row, 'Add to library' if is_loader else 'Launch tool', lambda item=record: run(item), True)
            button(row, 'Change file' if path else 'Choose file', lambda item=record: attach(item), not path)
            button(row, 'Loader folder', lambda item=record: attach(item, True))
            button(row, 'Rename', lambda item=record: name_dialog(item))
            button(row, 'Remove', lambda item=record: remove(item))
        footer = ttk.Frame(custom)
        footer.pack(fill='x', pady=(2, 0))
        if len(records) < custom_tools.LIMIT:
            app.add_custom_tool_button = ttk.Button(footer,
                text=tr('Add another tool' if records else 'Add Custom Tool 1'),
                style='Yellow.TButton', command=name_dialog)
            app.add_custom_tool_button.pack(side='left')
        else:
            app.add_custom_tool_button = None
        ttk.Label(footer, text=f'{len(records)} / 3 '+tr('custom tools'), style='Muted.TLabel').pack(side='right')
        ui_polish.creator_layout(custom)
        ui_polish.schedule(app)

    def name_dialog(record=None):
        if app.busy:
            return
        screen = ResultScreen(app, tr('Rename tool' if record else 'Add custom tool'),
                              tr('Give this tool a name. It will be remembered next time you open the app.'))
        value = tk.StringVar(master=screen, value=record['name'] if record else '')
        entry = ttk.Entry(screen.content, textvariable=value, width=50)
        entry.pack(fill='x')
        error = ttk.Label(screen.content, text='', style='Muted.TLabel')
        error.pack(anchor='w', pady=(8, 0))
        def save():
            records = app.cfg.setdefault('custom_tools', [])
            prior_name = record['name'] if record else None
            added = None
            try:
                if record:
                    others = [item for item in records if item is not record]
                    validated = custom_tools.add({'custom_tools': others}, value.get())
                    record['name'] = validated['name']
                else:
                    added = custom_tools.add(app.cfg, value.get())
                core.save_config(app.cfg)
            except Exception as exc:
                if record:
                    record['name'] = prior_name
                elif added is not None:
                    records.remove(added)
                error.configure(text=str(exc))
                return
            screen.close()
            render_custom()
        screen.buttons([('Cancel', None), ('Confirm name', None)])
        screen.option_buttons[1].configure(command=save, style='Yellow.TButton')
        entry.bind('<Return>', lambda e: save())
        entry.focus_set()
        entry.selection_range(0, 'end')
        return screen

    def attach(record, folder=False):
        if app.busy:
            return
        source = (filedialog.askdirectory(title=tr('Choose loader folder'), parent=app._dialog_parent()) if folder else
                  filedialog.askopenfilename(title=tr('Connect custom tool'), parent=app._dialog_parent(),
                    filetypes=[('Tools and loaders', '*.exe *.com *.lnk *.py *.ps1 *.bat *.cmd *.sh *.AppImage *.zip *.7z'),
                               ('All files', '*.*')]))
        if not source:
            return
        before = dict(record)
        try:
            custom_tools.attach(record, source)
            if record['kind'] == 'loader':
                parsed = core.parse_mod(record['path'])
                if not parsed.get('targets') and not parsed.get('runtime'):
                    raise ValueError('This package has no supported loader or mod files.')
            core.save_config(app.cfg)
        except Exception as exc:
            record.clear()
            record.update(before)
            app._message_themed('Custom tool', str(exc))
        render_custom()

    def run(record):
        if app.busy:
            return
        try:
            if record.get('kind') == 'loader':
                app._add_paths([record['path']], custom_loader=True)
            else:
                custom_tools.launch(record)
                app.log('Opened custom tool: ' + record['name'])
        except Exception as exc:
            app._message_themed('Custom tool', str(exc))

    def remove(record):
        if app.busy:
            return
        # Removes only the shortcut. Its original file belongs to the user.
        app.cfg['custom_tools'].remove(record)
        core.save_config(app.cfg)
        render_custom()

    app.render_custom_tools = render_custom
    app.add_custom_tool = name_dialog
    render_custom()
    editor_cards = []
    if nexus_mode.NEXUS_BUILD:
      section(3, '02', 'Built-in mods', 'Choose what joins Install All. Data Bot prepares each mod for your installed game.')
    else:
      section(3, '02', 'Editors & loaders', 'From stat editing to Lua mods, pick the right tool for your session.')
      editors = ttk.Frame(body)
      editors.grid(row=4, column=0, sticky='ew')
      ccm = card(editors, 'LINUX AND WINDOWS EDITOR', 'ModDiverEditor',
               'Edit stats on Windows or Linux. Changes export automatically to one Mod Library entry. Use Preview Deployment, then Merge and Install All to apply them.', ('windows', 'linux'))
      app.moddiver_editor_card = ccm
      ccm.configure(style='EditorOutline.TFrame', borderwidth=1, relief='solid')
      row = actions(ccm)
      row._flow_single = True
      button(row, 'Open ModDiverEditor', app.open_editor_ccm, True)
      row = actions(ccm)
      button(row, 'Mod Library', lambda: app._show('mods'))
      button(row, 'Import presets', app.import_presets_ccm)
      button(row, 'Armory presets', lambda: app.open_output_folder(core.EDITOR_CCM_PRESETS))
      editor_cards.append(ccm)
      shodan = card(editors, 'STAT EDITOR', 'SHODAN',
                  'Fine-tune weapons, vehicles, stratagems and armor passives. Capture your changes as a reusable mod.', ('windows',))
      app.shodan_editor_card = shodan
      shodan.configure(style='EditorPlain.TFrame', borderwidth=1, relief='solid')
      row = actions(shodan)
      button(row, 'Open SHODAN', app.open_editor, True)
      app.btn_check_shodan = button(row, 'Check for updates', app.check_shodan_editor_update, style='Update.TButton')
      row = actions(shodan)
      button(row, 'Capture as mod', app.capture_game_mod)
      button(row, 'Import presets', app.import_presets)
      button(row, 'Saved presets', lambda: app.open_output_folder(core.EDITOR_CFG))
      editor_cards.append(shodan)
      # Share description space so both action rows align even when text wraps.
      for frame in editor_cards:
          frame.columnconfigure(0, weight=1)
          frame.rowconfigure(2, weight=1)
          children = frame.winfo_children()
          for child in children:
              child.pack_forget()
          for index, child in enumerate(children):
              child.grid(row=index, column=0, sticky='nsew' if index == 2 else 'ew',
                         pady=(0, 8) if index < 3 else (6, 0))
      for index, frame in enumerate(editor_cards):
          frame.grid(row=index, column=0, sticky='nsew', pady=(0, 12))
      def layout(e):
          columns = 2 if e.width >= 1100 else 1
          if getattr(editors, '_columns', None) == columns:
              return
          editors._columns = columns
          for i, frame in enumerate(editor_cards):
              frame.grid(row=i//columns, column=i%columns, padx=(0, 12 if columns == 2 and i == 0 else 0))
          for i in range(2):
              editors.columnconfigure(i, weight=1 if i < columns else 0, uniform='editors' if i < columns else '', minsize=0)
      editors.bind('<Configure>', layout)
    if not nexus_mode.NEXUS_BUILD:
      chef = card(body, 'LUA RUNTIME', 'Chef Shared Loader',
                'Run compatible Lua mods side by side with a shared in-game menu. Add the loader to your library, then Deploy.',
                ('windows', 'linux'))
      chef.grid(row=5, column=0, sticky='ew')
      row = actions(chef)
      button(row, 'Add Chef Loader', app.install_chef_loader, True)
      app.btn_check_chef = button(row, 'Check for updates', app.check_chef_loader_update, style='Update.TButton')
      app.btn_import_chef = button(row, 'Import loader update', app.import_new_loader)
    if not nexus_mode.NEXUS_BUILD:
      section(6, '03', 'Built-in mods', 'Choose what joins Install All. Data Bot prepares each mod for your installed game.')
    builtins = ttk.Frame(body)
    builtins.grid(row=4 if nexus_mode.NEXUS_BUILD else 7, column=0, sticky='ew')
    app.gameplay_vars = {}
    app.builtin_widgets = []
    unlock_name = 'contentUnlock' if nexus_mode.NEXUS_BUILD else 'Hidden Content Unlocker'
    for index, (key, title) in enumerate({'nomofomo': unlock_name, **gameplay_profiles.PROFILES}.items()):
        frame = card(builtins, f'{index+1:02d}  /  BUILT-IN MOD', title, DESCRIPTIONS[key],
                     ('windows', 'linux'))
        frame.pack(fill='x', pady=(0, 10))
        var = tk.BooleanVar(master=app, value=bool(app.cfg.get(key, True)))
        if key == 'nomofomo':
            app.nomofomo_var = var
            command = app.toggle_nomofomo
        else:
            app.gameplay_vars[key] = var
            command = lambda k=key: app._toggle_gameplay_profile(k)
        checkbox = ttk.Checkbutton(frame, text=tr('Include with Install All'), variable=var,
                                   style='Yellow.TCheckbutton', command=command)
        checkbox.pack(anchor='w')
        app.builtin_widgets.append(checkbox)
        if key == 'nomofomo':
            row = actions(frame)
            app.builtin_widgets.append(button(row, 'Configure unlock categories', app.configure_unlocker))
    repair_description = (
        'Built-in mod outputs are generated and verified for your current Steam build when first needed. Install All does this automatically after a clean capture. For a game update or changed options, click Update / repair built-in mods. Find Steam Verify + Capture Stock in Settings > Clean Stock Baseline.'
        if nexus_mode.NEXUS_BUILD else
        'Update and verify all three built-in mods against clean game data. Successful updates replace the previous managed version.')
    updates = card(body, 'MAINTENANCE  /  DATA BOT', 'Keep your kit current', repair_description)
    updates.grid(row=5 if nexus_mode.NEXUS_BUILD else 8, column=0, sticky='ew', pady=(6, 0))
    row = actions(updates)
    app.btn_update_builtins = button(row, 'Update / repair built-in mods', app.update_builtin_mods, style='Update.TButton')
    button(row, 'Open capture folder', lambda: app.open_output_folder(core.APP_DATA/'mods'))
    ui_polish.creator_layout(body)
    return page

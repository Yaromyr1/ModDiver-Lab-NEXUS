"""ModDiver's integration with the bundled MPL audioStudio core."""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ENGINE = Path(__file__).resolve().parent / 'vendor' / 'audio_engine'


def configure(cache):
    # Keep caches and preferences separate from a standalone audioStudio installation.
    if sys.version_info < (3, 12):
        raise RuntimeError('Audio studio requires Python 3.12 or newer. The Windows launcher includes a compatible runtime.')
    os.environ['audioStudio_CACHE'] = str(cache)
    if str(ENGINE) not in sys.path:
        sys.path.insert(0, str(ENGINE))
    if os.name == 'nt' and sys.version_info[:2] == (3, 14):
        native = str(ENGINE / 'windows')
        if native not in sys.path:
            sys.path.insert(0, native)
    try:
        from audioStudio import wem
        from audioStudio.editor import Session
    except ImportError as exc:
        raise RuntimeError('Audio engine dependencies are missing. Use the Windows launcher with its Python 3.14 runtime, '
                           'or install Python 3.12+, lz4 and Pillow on Linux.') from exc
    for name, binary in [('FFMPEG', 'ffmpeg'), ('FFPROBE', 'ffprobe'),
                         ('VGMSTREAM', 'vgmstream-cli'), ('WAV2WEM', 'wav2wem')]:
        local = ENGINE / 'tools' / (binary + '.exe')
        setattr(wem, name, str(local) if os.name == 'nt' and local.exists() else shutil.which(binary) or binary)
    if os.name == 'nt':
        # Module-local adapter: suppress converter console windows without changing the vendored sources.
        from audioStudio import audio, editor
        class QuietTools:
            def __getattr__(self, name):
                return getattr(subprocess, name)
            def run(self, *args, **kwargs):
                kwargs.setdefault('creationflags', subprocess.CREATE_NO_WINDOW)
                return subprocess.run(*args, **kwargs)
        for module in (wem, audio, editor):
            module.subprocess = QuietTools()
    return Session


class AudioBackend:
    def __init__(self, cache):
        self.cache = Path(cache)
        self.session = configure(self.cache)(load=False)
        self.label_file = self.cache / 'moddiver-labels.json'
        try:
            self.labels = json.loads(self.label_file.read_text(encoding='utf-8'))
            if not isinstance(self.labels, dict): self.labels = {}
            self.labels = {str(k): v for k, v in self.labels.items() if isinstance(v, str)}
        except (OSError, ValueError):
            self.labels = {}

    def load(self, game=None, progress=None):
        from audioStudio.editor import load_settings, save_settings
        chosen = game or load_settings().get('game_data')
        self.session._load_game(chosen, progress=progress)
        self.session.require_game()
        save_settings(game_data=str(self.session.ix.game.data))
        return self.categories()

    def categories(self):
        out = list(self.session.index()['categories'])
        archives = self.session.archives()
        # Named catalogue first; every archive remains discoverable, including new game audio.
        out.append({'id': 'archives', 'name': 'All game archives', 'sections': [
            {'id': 'archives/all', 'name': 'Named and unclassified audio', 'items': [
                {'id': 'archive:' + a['id'], 'name': ' / '.join(a['names'][:2]) or 'Unclassified archive ' + a['id'],
                 'parts': [], 'count': a['sounds']} for a in archives]}]})
        return out

    def sounds(self, item_id):
        item = self.session.item(item_id)
        rows = []
        seen = set()
        for part in item['parts']:
            cue = self.session.cue(part['cue'], mine=True)
            for group in cue.get('segments_detail', []):
                for stem in group.get('stems', []):
                    for number, slot in enumerate(stem.get('slots', []), 1):
                        sid = str(slot['source'])
                        if sid in seen:
                            continue
                        seen.add(sid)
                        group_name = group.get('name') or part.get('name') or 'Unidentified sound'
                        name = slot.get('label') or f'Take {number}'
                        if name.lower().startswith(('take ', 'clip ', 'sound ')):
                            name = f'{group_name} · {name}'
                        rows.append({**slot, 'source': sid, 'name': self.labels.get(sid) or name,
                                     'group': group_name, 'cue': str(part['cue']),
                                     'item': item_id, 'item_name': item['name']})
        return rows

    def state(self):
        return self.session.project_state() if self.session.project else {'assignments': {}, 'gains': {}}

    def rename(self, sid, name):
        sid, name = str(sid), str(name).strip()
        labels = dict(self.labels)
        if name:
            labels[sid] = name
        else:
            labels.pop(sid, None)
        self.label_file.parent.mkdir(parents=True, exist_ok=True)
        from merge_engine import atomic_write
        atomic_write(self.label_file, json.dumps(labels, ensure_ascii=False, indent=2).encode('utf-8'))
        self.labels = labels

    def check_destination(self, filename):
        from audioStudio.game import in_game_folder
        if self.session.ix and in_game_folder(Path(filename).parent, self.session.ix.game.data):
            raise ValueError('Choose a project or export location outside the installed game folder.')

    def assign(self, sid, filename, label):
        import uuid
        source = Path(filename)
        project = self.session._need_project()
        self.check_destination(project.path)
        folder = project.path.parent / 'audio' / 'imports'
        folder.mkdir(parents=True, exist_ok=True)
        output = folder / (uuid.uuid4().hex[:10] + '-' + source.name)
        shutil.copy2(source, output)
        return self.session.assign(sid, str(output.resolve()), label)

    def edit_settings(self, sid, gain, timing):
        gain = float(gain)
        if not -96 <= gain <= 96:
            raise ValueError('Gain must be between -96 and +96 dB.')
        if str(sid) in self.state()['assignments']:
            return self.session.update(sid, gain_db=gain, fit_timing=bool(timing))
        return self.session.original_gain([sid], gain)

    def edit_volume_many(self, sources, gain):
        """Set a selection's absolute gain in one saved, undoable transaction.

        Timing belongs to each replacement and is deliberately preserved here.
        """
        gain = float(gain)
        if not -96 <= gain <= 96:
            raise ValueError('Gain must be between -96 and +96 dB.')
        session = self.session
        sids = list(dict.fromkeys(session._source(s) for s in sources))
        if not sids:
            raise ValueError('Select a sound first.')

        def apply(project):
            replacements = {session._target(r.target): r for r in project.replacements}
            for sid in sids:
                for target in [t for t in project.gains if session._target(t) == sid]:
                    del project.gains[target]
                if sid in replacements:
                    replacements[sid].gain_db = gain
                elif gain:
                    project.gains[sid] = gain
        return session._edit('gain', apply)

    def restore(self, sid):
        self.session.unassign([sid])
        return self.session.original_gain([sid], 0)

    def trim(self, sid, start, end):
        from audioStudio import wem
        from audioStudio.audio import duration_ms
        self.check_destination(self.session._need_project().path)
        source = self.session.project_audio(int(sid))
        start, end = float(start), float(end)
        duration = (duration_ms(source) or 0) / 1000
        if not 0 <= start < end <= duration + .001:
            raise ValueError(f'Enter a valid range inside the replacement: 0 to {duration:.3f} seconds.')
        folder = self.session.project.path.parent / 'audio' / 'edits'
        folder.mkdir(parents=True, exist_ok=True)
        output = folder / f'{sid}-{time.time_ns()}.wav'
        subprocess.run([wem.FFMPEG, '-v', 'error', '-i', wem.decoded(source), '-ss', str(start), '-t', str(end-start),
                        '-ar', '48000', '-ac', '2', '-c:a', 'pcm_s16le', str(output)],
                       check=True, capture_output=True, creationflags=0x08000000 if os.name == 'nt' else 0)
        return self.session.assign(sid, str(output.resolve()), self.labels.get(str(sid)) or source.stem)

    def preview(self, sid, side):
        from audioStudio import audio, wem
        s = self.session
        state = self.state()
        assignment = state['assignments'].get(str(sid))
        path = s.vanilla_wav(int(sid)) if side == 'original' else s.project_audio(int(sid)) if assignment else s.vanilla_wav(int(sid))
        gain = 0 if side == 'original' else assignment['gain_db'] if assignment else state['gains'].get(str(sid), 0)
        out = self.cache / 'moddiver-preview' / f'{sid}-{side}.wav'
        out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([wem.FFMPEG, '-y', '-v', 'error', '-i', wem.decoded(path), '-af', f'volume={gain}dB',
                        '-ar', '48000', '-ac', '2', '-c:a', 'pcm_s16le', str(out)],
                       check=True, capture_output=True, creationflags=0x08000000 if os.name == 'nt' else 0)
        return out, audio.peaks(out, buckets=500)

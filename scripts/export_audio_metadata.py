#!/usr/bin/env python3
"""Recursively export audio metadata. Requires ffprobe; optionally uses mutagen.

Usage: python3 export_audio_metadata.py '/path/to/music'
Binary tag values (including artwork) use {"encoding": "base64", "data": ...}.
Audio samples and artwork pixels decoded by ffprobe are never exported.
"""

import argparse
import base64
from collections.abc import Mapping
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

try:
    import mutagen
except ImportError:
    mutagen = None


AUDIO_EXTENSIONS = {
    '.aac', '.ac3', '.aif', '.aiff', '.aifc', '.alac', '.amr', '.ape',
    '.au', '.bwf', '.caf', '.dff', '.dsf', '.dts', '.flac', '.m4a',
    '.m4b', '.mka', '.mp2', '.mp3', '.mp4', '.mpc', '.oga', '.ogg',
    '.opus', '.ra', '.snd', '.spx', '.tak', '.tta', '.wav', '.wave',
    '.webm', '.wma', '.wv',
}


def json_value(value):
    """Keep structured tags and losslessly encode binary tag payloads."""
    if isinstance(value, bytes):
        return {'encoding': 'base64', 'data': base64.b64encode(value).decode('ascii')}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(v) for v in value]
    if hasattr(value, '__dict__'):
        return {'type': type(value).__name__,
                'fields': json_value(vars(value))}
    return str(value)


def read_file(path, root, ffprobe, timeout):
    entry = {'path': path.relative_to(root).as_posix(), 'errors': []}
    try:
        stat = path.stat()
        entry.update(size_bytes=stat.st_size,
                     modified_utc=datetime.fromtimestamp(
                         stat.st_mtime, timezone.utc).isoformat())
        result = subprocess.run(
            [ffprobe, '-v', 'error', '-show_format', '-show_streams',
             '-show_chapters', '-show_programs', '-print_format', 'json', str(path)],
            capture_output=True, text=True, errors='replace', timeout=timeout,
        )
        if result.returncode:
            entry['errors'].append(result.stderr.strip() or 'ffprobe failed')
        else:
            entry['ffprobe'] = json.loads(result.stdout)
        if mutagen is not None:
            try:
                audio = mutagen.File(path, easy=False)
                if audio is not None:
                    entry['mutagen'] = {
                        'type': type(audio).__name__,
                        'tags': json_value(audio.tags) if audio.tags is not None else {},
                    }
                    if hasattr(audio, 'pictures'):
                        entry['mutagen']['pictures'] = json_value(audio.pictures)
            except Exception as exc:
                entry['errors'].append(f'Mutagen: {exc}')
    except Exception as exc:
        entry['errors'].append(f'{type(exc).__name__}: {exc}')
    return entry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--output', default='audio_metadata.json',
                        help='JSON filename inside the scanned root (default: %(default)s)')
    parser.add_argument('--timeout', type=float, default=120,
                        help='Maximum ffprobe seconds per file (default: %(default)s)')
    parser.add_argument('--all-files', action='store_true',
                        help='Probe every file, including files with unknown extensions')
    args = parser.parse_args()
    root = args.folder.expanduser().resolve()
    if not root.is_dir():
        parser.error(f'Folder does not exist: {root}')
    if Path(args.output).name != args.output or not args.output.endswith('.json'):
        parser.error('--output must be a filename ending in .json')
    if args.timeout <= 0:
        parser.error('--timeout must be positive')
    ffprobe = shutil.which('ffprobe')
    if not ffprobe:
        parser.error('ffprobe is required. On macOS install it with: brew install ffmpeg')
    output = root / args.output
    warnings = []
    if mutagen is None:
        warnings.append('Mutagen unavailable: only ffprobe metadata is included. '
                        'For additional raw tags/artwork: python3 -m pip install mutagen')
        print(warnings[-1], file=sys.stderr)
    count = failures = 0
    temp_path = None
    try:
        # Stream records to disk so large libraries do not fill memory.
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=root,
                                         prefix='.audio_metadata-', suffix='.tmp',
                                         delete=False) as target:
            temp_path = Path(target.name)
            header = {'root': str(root),
                      'created_utc': datetime.now(timezone.utc).isoformat(),
                      'readers': ['ffprobe'] + (['mutagen'] if mutagen else []),
                      'warnings': warnings}
            target.write(json.dumps(header, ensure_ascii=True)[:-1] + ', "files": [\n')

            def walk_error(error):
                warnings.append(str(error))
                print(f'Cannot scan directory: {error}', file=sys.stderr)

            for directory, dirs, names in os.walk(root, onerror=walk_error, followlinks=False):
                dirs.sort()
                for name in sorted(names):
                    path = Path(directory) / name
                    if path in (output, temp_path) or path.is_symlink():
                        continue
                    if not args.all_files and path.suffix.lower() not in AUDIO_EXTENSIONS:
                        continue
                    entry = read_file(path, root, ffprobe, args.timeout)
                    if count:
                        target.write(',\n')
                    json.dump(entry, target, ensure_ascii=True)
                    count += 1
                    failures += bool(entry['errors'])
                    print(f'[{count}] {entry["path"]}', file=sys.stderr, flush=True)
            target.write('\n], "summary": ')
            json.dump({'files_processed': count, 'files_with_errors': failures,
                       'scan_warnings': warnings}, target)
            target.write('}\n')
        os.replace(temp_path, output)
        print(f'Saved {count} records ({failures} with errors) to {output}')
        return 1 if failures or warnings else 0
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('\nCancelled; existing output preserved.', file=sys.stderr)
        sys.exit(130)

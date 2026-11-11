"""Verify every raw file against its registered checksum and size and write data/raw/MANIFEST.csv."""
import csv

import raw_common as R

FIELDS = ['file', 'original_name', 'source', 'contents', 'years', 'csv_rows', 'bytes', 'retrieved', 'sha256']


def build_manifest():
    registered = {f['path']: f for f in R.CONFIG['files']}
    incoming = R.ROOT / R.CONFIG['incoming_directory']
    manifest = R.ROOT / R.CONFIG['manifest']
    present = sorted(p.relative_to(R.RAW).as_posix() for p in R.RAW.rglob('*')
                     if p.is_file() and p != manifest and incoming not in p.parents)
    undocumented = [p for p in present if p not in registered]
    missing = [p for p in registered if p not in present]
    changed = [p for p in present if p in registered and (R.sha256(R.RAW / p) != registered[p]['sha256']
               or (R.RAW / p).stat().st_size != registered[p]['bytes'])]
    waiting = sorted(p.name for p in incoming.iterdir() if p.is_file()) if incoming.is_dir() else []
    pending = [p['path'] for p in R.CONFIG['pending'] if p['path'] not in registered]
    summary = dict(registered=len(registered), present=len(present), undocumented=undocumented,
                   missing=missing, changed=changed, incoming=waiting, pending=pending)
    if undocumented or missing or changed:
        R.write_report('01_manifest.json', __file__, summary, status='FAILED')
        R.require(False, f'Raw files do not match raw_config.json; see outputs/raw_data/01_manifest.json: {summary}')
    pending_path = manifest.with_name(manifest.name + '.tmp')
    with pending_path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream)
        writer.writerow(FIELDS)
        for path in sorted(registered):
            entry = registered[path]
            writer.writerow([path] + ['' if entry[f] is None else entry[f] for f in FIELDS[1:]])
    pending_path.replace(manifest)
    R.write_report('01_manifest.json', __file__, summary, status='PASSED')
    print(f'[01] Complete; {len(registered)} raw files verified; {len(pending)} pending; '
          f'{len(waiting)} in _incoming', flush=True)


if __name__ == '__main__':
    build_manifest()

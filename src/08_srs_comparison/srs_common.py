"""Shared paths, readers, statistics and reports for the comparison with the Sample Registration System."""
import csv
import hashlib
import io
import json
import math
import zipfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CONFIG_PATH = HERE / 'srs_config.json'
CONFIG = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
RAW_CONFIG = json.loads((ROOT / CONFIG['raw_config']).read_text(encoding='utf-8'))
RAW = ROOT / CONFIG['raw_directory']
WORK = ROOT / 'data/processed/srs_comparison'
OUT = ROOT / 'outputs/srs_comparison'
INDIA = CONFIG['india']


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write_report(filename, script, summary, **details):
    OUT.mkdir(parents=True, exist_ok=True)
    report = dict(config_version=CONFIG['version'], generated_at_utc=datetime.now(timezone.utc).isoformat(),
                  script_sha256=sha256(script), srs_config_sha256=sha256(CONFIG_PATH), summary=summary, **details)
    pending = OUT / (filename + '.tmp')
    pending.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    pending.replace(OUT / filename)
    return report


def number(value):
    return f'{value:.12g}' if isinstance(value, float) else value


def write_csv(filename, header, rows):
    WORK.mkdir(parents=True, exist_ok=True)
    path = WORK / filename
    pending = path.with_name(path.name + '.tmp')
    with pending.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        writer.writerows([number(v) for v in row] for row in rows)
    pending.replace(path)
    return path


def read_csv(path):
    with Path(path).open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


def gbd_by_age(requests, ages):
    """Return all-cause deaths (number, both sexes) by (location, age, year) from the registered Results Tool archives."""
    values = {}
    for entry in [f for f in RAW_CONFIG['files'] if f['request'] in requests]:
        path = RAW / entry['path']
        require(sha256(path) == entry['sha256'], f'{path} differs from its registered checksum')
        with zipfile.ZipFile(path) as archive:
            member = next(m for m in archive.namelist() if m.lower().endswith('.csv'))
            with archive.open(member) as stream:
                for r in csv.DictReader(io.TextIOWrapper(stream, encoding='utf-8-sig', newline='')):
                    if r['measure_name'] == 'Deaths' and r['metric_name'] == 'Number' and r['age_name'] in ages:
                        values[(r['location_name'], r['age_name'], int(r['year']))] = float(r['val'])
    require(values, f'No deaths read from {requests}')
    return values


def ranks(values):
    """Return ranks starting at 1, with ties given their average rank."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    out, i = [0.0] * len(values), 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return out


def spearman(x, y):
    a, b = ranks(x), ranks(y)
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    sa, sb = math.sqrt(sum((v - ma) ** 2 for v in a)), math.sqrt(sum((v - mb) ** 2 for v in b))
    return sum((u - ma) * (v - mb) for u, v in zip(a, b)) / (sa * sb) if sa and sb else ''

"""Shared paths, readers and reports for the neonatal and maternal sepsis stages."""
import csv
import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CONFIG_PATH = HERE / 'neonatal_maternal_config.json'
CONFIG = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
RAW_CONFIG = json.loads((ROOT / CONFIG['raw_config']).read_text(encoding='utf-8'))
RAW = ROOT / CONFIG['raw_directory']
ESTIMATES = ROOT / CONFIG['estimates_directory']
WORK = ROOT / 'data/processed/neonatal_maternal'
OUT = ROOT / 'outputs/neonatal_maternal'
INDIA, DEATHS = CONFIG['india'], CONFIG['deaths']
YEARS = range(CONFIG['series_years'][0], CONFIG['series_years'][1] + 1)
NEONATAL, MATERNAL = CONFIG['causes']['neonatal'], CONFIG['causes']['maternal']


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
                  script_sha256=sha256(script), neonatal_maternal_config_sha256=sha256(CONFIG_PATH), summary=summary, **details)
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


def read_csv(filename, directory=WORK):
    with (directory / filename).open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


def raw_file(path):
    """Return the path of a raw file registered in raw_config.json, after checking its SHA-256."""
    entry = next((f for f in RAW_CONFIG['files'] if f['path'] == path), None)
    require(entry is not None, f'{path} is not registered in {CONFIG["raw_config"]}')
    full = RAW / path
    require(full.is_file() and sha256(full) == entry['sha256'], f'{full} is missing or differs from its registered checksum')
    return full


def results(requests, key_fields, measure=DEATHS, metric='Number', causes=None, ages=None, interval=False):
    """Return {key: value}, or {key: (val, lower, upper)}, for one measure and metric from the Results Tool archives of the requests."""
    values = {}
    for entry in [f for f in RAW_CONFIG['files'] if f['request'] in requests]:
        with zipfile.ZipFile(raw_file(entry['path'])) as archive:
            member = next(m for m in archive.namelist() if m.lower().endswith('.csv'))
            with archive.open(member) as stream:
                for r in csv.DictReader(io.TextIOWrapper(stream, encoding='utf-8-sig', newline='')):
                    if (r['measure_name'] != measure or r['metric_name'] != metric or (causes and r['cause_name'] not in causes)
                            or (ages and r['age_name'] not in ages)):
                        continue
                    key = tuple(int(r[f]) if f == 'year' else r[f] for f in key_fields)
                    require(key not in values, f'{entry["path"]}: duplicate {key}')
                    values[key] = (float(r['val']), float(r['lower']), float(r['upper'])) if interval else float(r['val'])
    require(values, f'No values read from {requests}')
    return values


def population():
    """Return population by (location, sex, year) at all ages and by (location, age, year) for both sexes, as deaths / death rate per 100,000."""
    key = ('location_name', 'sex_name', 'year')
    number = results(CONFIG['requests']['all_cause'], key + ('age_name',))
    rate = results(CONFIG['requests']['all_cause'], key + ('age_name',), metric='Rate')
    by_sex = {k[:3]: number[k] / rate[k] * 1e5 for k in number if k[3] == CONFIG['all_ages']}
    age_key = ('location_name', 'age_name', 'year')
    number = results(CONFIG['requests']['population_by_age'], age_key)
    rate = results(CONFIG['requests']['population_by_age'], age_key, metric='Rate')
    return by_sex, {k: number[k] / rate[k] * 1e5 for k in number}


def ratio_range(name, pairs, tolerance):
    """Check that every value / reference ratio (zero references skipped) lies within tolerance of 1; return count and range."""
    ratios = [v / r for v, r in pairs if r]
    require(ratios, f'{name}: nothing to compare')
    low, high = min(ratios), max(ratios)
    require(abs(low - 1) <= tolerance and abs(high - 1) <= tolerance, f'{name}: ratios {low:.12f}-{high:.12f}')
    return dict(n=len(ratios), min=low, max=high)


def percent_change(start, end):
    return 100 * (end / start - 1) if start else ''

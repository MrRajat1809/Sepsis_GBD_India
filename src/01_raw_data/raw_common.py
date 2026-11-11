"""Shared paths, readers, cause hierarchy and reports for the raw-data checks."""
import csv
import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CONFIG_PATH = HERE / 'raw_config.json'
CONFIG = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
CAUSES_PATH = ROOT / 'src/common/gbd_causes.json'
CAUSES = json.loads(CAUSES_PATH.read_text(encoding='utf-8'))
RAW = ROOT / CONFIG['raw_directory']
OUT = ROOT / 'outputs/raw_data'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(path.name + '.tmp')
    pending.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
    pending.replace(path)


def write_report(filename, script, summary, **details):
    report = dict(config_version=CONFIG['version'], generated_at_utc=datetime.now(timezone.utc).isoformat(),
                  script_sha256=sha256(script), raw_config_sha256=sha256(CONFIG_PATH),
                  common_sha256={p.name: sha256(p) for p in sorted((ROOT / 'src/common').glob('*.json'))},
                  summary=summary, **details)
    write_json(OUT / filename, report)
    return report


def years_of(text):
    """Return the years in a field such as '1990-1996' or '1990, 2019, 2021'."""
    years = []
    for part in text.split(','):
        lo, _, hi = part.strip().partition('-')
        years.extend(range(int(lo), int(hi or lo) + 1))
    return years


def files_for(*requests):
    """Return the registered files downloaded for the given Results Tool requests."""
    return [f for f in CONFIG['files'] if f['request'] in requests]


def results_rows(path):
    """Yield the rows, as text, of the single CSV in a Results Tool archive."""
    with zipfile.ZipFile(path) as archive:
        members = [i.filename for i in archive.infolist()]
        csvs = [m for m in members if m.lower().endswith('.csv')]
        require(len(csvs) == 1 and sorted(members) == sorted(csvs + ['citation.txt']),
                f'{path.name}: expected one CSV and citation.txt, found {members}')
        with archive.open(csvs[0]) as stream:
            reader = csv.DictReader(io.TextIOWrapper(stream, encoding='utf-8-sig', newline=''))
            require(reader.fieldnames == CONFIG['results_tool_columns'], f'{path.name}: unexpected columns {reader.fieldnames}')
            yield from reader


def load_values(entry, key_fields):
    """Read one archive, check it against its request and return {key: val} and a file summary."""
    request = CONFIG['requests'][entry['request']]
    path = RAW / entry['path']
    values, seen, negative, outside = {}, {f: set() for f in ('measure_name', 'metric_name', 'age_name', 'sex_name', 'year', 'location_name')}, 0, 0
    rows = 0
    for r in results_rows(path):
        rows += 1
        for field, found in seen.items():
            found.add(r[field])
        value, lower, upper = float(r['val']), float(r['lower']), float(r['upper'])
        negative += value < 0
        outside += not (lower - 1e-9 <= value <= upper + 1e-9)
        key = tuple(r[f] for f in key_fields)
        require(key not in values, f'{path.name}: duplicate key {key}')
        values[key] = value
    expected = dict(measure_name=request['measures'], metric_name=request['metrics'], age_name=request['ages'],
                    sex_name=request['sexes'], year=[str(y) for y in years_of(entry['years'])])
    for field, wanted in expected.items():
        require(seen[field] == set(wanted), f'{path.name}: {field} {sorted(seen[field])}, expected {sorted(wanted)}')
    require(len(seen['location_name']) == request['locations'], f'{path.name}: {len(seen["location_name"])} locations')
    require(rows == entry['csv_rows'], f'{path.name}: {rows} rows, expected {entry["csv_rows"]}')
    require(not negative and not outside, f'{path.name}: {negative} negative values, {outside} values outside their interval')
    return values, dict(file=entry['path'], request=entry['request'], rows=rows, locations=len(seen['location_name']))


def cause_hierarchy():
    """Return the level 2 causes and the level 3 -> 2 and level 4 -> 3 parents from the GBD 2023 cause list (Table S1)."""
    spec = CONFIG['cause_list']
    aliases = spec['name_aliases']
    level2, parent3, parent4 = [], {}, {}
    with zipfile.ZipFile(RAW / spec['path']) as archive:
        member = [i for i in archive.infolist() if spec['table'] in i.filename][0]
        with archive.open(member) as stream:
            reader = csv.reader(io.TextIOWrapper(stream, encoding='utf-8-sig', errors='replace', newline=''))
            next(reader), next(reader)
            # The table lists causes in hierarchy order, so a cause's parent is the last cause one level up.
            current2 = current3 = None
            for row in reader:
                if len(row) < 2:
                    continue
                name, level = aliases.get(row[0].strip(), row[0].strip()), row[1].strip()
                if level == '2':
                    current2 = name
                    level2.append(name)
                elif level == '3':
                    current3 = name
                    parent3[name] = current2
                elif level == '4':
                    parent4[name] = current3
    return level2, parent3, parent4


def ratio_range(ratios):
    ratios = list(ratios)
    require(ratios, 'No values to compare')
    return dict(n=len(ratios), min=min(ratios), max=max(ratios))


def exact(name, ratios, tolerance=1e-6):
    """Check that every ratio is 1 within the tolerance and return their count and range."""
    result = ratio_range(ratios)
    require(abs(result['min'] - 1) <= tolerance and abs(result['max'] - 1) <= tolerance,
            f'{name}: ratio range {result["min"]:.6f}-{result["max"]:.6f}')
    return result

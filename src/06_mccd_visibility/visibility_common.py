"""Shared paths, unit mapping, statistics and reports for the death certification visibility stages."""
import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CONFIG_PATH = HERE / 'visibility_config.json'
CONFIG = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
MCCD = ROOT / CONFIG['mccd_directory']
ESTIMATES = ROOT / CONFIG['estimates_directory']
WORK = ROOT / 'data/processed/mccd_visibility'
OUT = ROOT / 'outputs/mccd_visibility'
INDIA = CONFIG['india']
YEARS = range(CONFIG['years'][0], CONFIG['years'][1] + 1)
AP_TG = CONFIG['andhra_telangana']


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_report(filename, script, summary, **details):
    OUT.mkdir(parents=True, exist_ok=True)
    report = dict(config_version=CONFIG['version'], generated_at_utc=datetime.now(timezone.utc).isoformat(),
                  script_sha256=sha256(script), visibility_config_sha256=sha256(CONFIG_PATH), summary=summary, **details)
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


def unit_of(gbd_unit, year):
    """Return the comparison unit of a GBD unit: Andhra Pradesh and Telangana are combined up to the split year."""
    return AP_TG['unit'] if gbd_unit in AP_TG['gbd_units'] and year <= AP_TG['through'] else gbd_unit


def members(unit, year):
    """Return the MCCD States/UTs that make up a comparison unit in a year."""
    rules = CONFIG['combined_units'].get(unit) or (AP_TG['members'] if unit == AP_TG['unit'] else None)
    if rules is None:
        return [unit]
    rule = next((r for r in rules if r['from'] <= year <= r['to']), None)
    require(rule is not None, f'No member rule for {unit} in {year}')
    return rule['members']


def ranks(values):
    """Return ranks starting at 1, with ties given their average rank."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return out


def pearson(x, y):
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    sx = math.sqrt(sum((a - mx) ** 2 for a in x))
    sy = math.sqrt(sum((b - my) ** 2 for b in y))
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy) if sx and sy else ''


def spearman(x, y):
    return pearson(ranks(x), ranks(y))


def log_slope(years, values):
    """Return the least-squares slope of log(value) on year as an annual percentage change."""
    logs = [math.log(v) for v in values]
    my, ml = sum(years) / len(years), sum(logs) / len(logs)
    slope = sum((a - my) * (b - ml) for a, b in zip(years, logs)) / sum((a - my) ** 2 for a in years)
    return 100 * (math.exp(slope) - 1)

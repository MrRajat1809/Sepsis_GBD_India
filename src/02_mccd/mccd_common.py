"""Shared paths, configuration and reports for the MCCD stages."""
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CONFIG_PATH = HERE / 'mccd_config.json'
CONFIG = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
RAW = ROOT / CONFIG['raw_directory']
WORK = ROOT / 'data/processed/mccd'
OUT = ROOT / 'outputs/mccd'
YEARS = range(CONFIG['years'][0], CONFIG['years'][1] + 1)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def text_path(year):
    return WORK / f'report_{year}.txt'


def write_report(filename, script, summary, **details):
    OUT.mkdir(parents=True, exist_ok=True)
    report = dict(config_version=CONFIG['version'], generated_at_utc=datetime.now(timezone.utc).isoformat(),
                  script_sha256=sha256(script), mccd_config_sha256=sha256(CONFIG_PATH), summary=summary, **details)
    pending = OUT / (filename + '.tmp')
    pending.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    pending.replace(OUT / filename)
    return report


def write_csv(filename, header, rows):
    WORK.mkdir(parents=True, exist_ok=True)
    path = WORK / filename
    pending = path.with_name(path.name + '.tmp')
    with pending.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        writer.writerows(rows)
    pending.replace(path)
    return path


def read_csv(filename):
    with (WORK / filename).open(encoding='utf-8') as stream:
        return list(csv.DictReader(stream))

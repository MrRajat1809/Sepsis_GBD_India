"""Shared paths, readers and reports for the economic loss stages."""
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CONFIG_PATH = HERE / 'economic_config.json'
CONFIG = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
ESTIMATES = ROOT / CONFIG['estimates_directory']
WORK = ROOT / 'data/processed/economic_loss'
OUT = ROOT / 'outputs/economic_loss'
INDIA = CONFIG['india']


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_report(filename, script, summary, **details):
    OUT.mkdir(parents=True, exist_ok=True)
    report = dict(config_version=CONFIG['version'], generated_at_utc=datetime.now(timezone.utc).isoformat(),
                  script_sha256=sha256(script), economic_config_sha256=sha256(CONFIG_PATH), summary=summary, **details)
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


def fiscal_label(start):
    return f'{start}-{str(start + 1)[2:]}'

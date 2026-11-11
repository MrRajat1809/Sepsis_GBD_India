"""Shared paths, printed-table layout, rounding bounds, GBD death reader and reports for the appendix table stages."""
import csv
import hashlib
import io
import itertools
import json
import re
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CONFIG_PATH = HERE / 'appendix_config.json'
CONFIG = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
CAUSES_PATH = ROOT / 'src/common/gbd_causes.json'
CAUSES = json.loads(CAUSES_PATH.read_text(encoding='utf-8'))
RAW_CONFIG = json.loads((ROOT / CONFIG['raw_config']).read_text(encoding='utf-8'))
RAW = ROOT / CONFIG['raw_directory']
WORK = ROOT / 'data/processed/appendix_tables'
OUT = ROOT / 'outputs/appendix_tables'
WORDS = 'appendix_words.csv'
WORD_FIELDS = ['document', 'page', 'block', 'line', 'word', 'x0', 'y0', 'x1', 'y1', 'text']
VALUE = re.compile(r'^\d+(?:\.\d+)?$')
INTERVAL = re.compile(r'^\((\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)\)$')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_report(filename, script, summary, **details):
    OUT.mkdir(parents=True, exist_ok=True)
    report = dict(config_version=CONFIG['version'], generated_at_utc=datetime.now(timezone.utc).isoformat(),
                  script_sha256=sha256(script), appendix_config_sha256=sha256(CONFIG_PATH),
                  common_sha256={p.name: sha256(p) for p in sorted((ROOT / 'src/common').glob('*.json'))},
                  summary=summary, **details)
    pending = OUT / (filename + '.tmp')
    pending.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
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
    with (WORK / filename).open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


def raw_file(path):
    """Return the path of a raw file registered in raw_config.json, checked against its registered SHA-256."""
    entry = next((f for f in RAW_CONFIG['files'] if f['path'] == path), None)
    require(entry is not None, f'{path} is not registered in {CONFIG["raw_config"]}')
    full = RAW / path
    require(full.is_file() and sha256(full) == entry['sha256'], f'{full} is missing or differs from its registered checksum')
    return full


def half_unit(text):
    """Return half the last printed unit of a value; whole numbers are counts printed to 3 significant figures."""
    if '.' in text:
        return 0.5 * 10 ** -len(text.split('.')[1])
    unit = 10 ** max(len(text) - 3, 0)
    require(int(text) % unit == 0, f'{text} has more than 3 significant figures')
    return 0.5 * unit


def rounding_gap(left, right):
    """Return the gap between two sums of printed values and the most that the rounding of those values can explain."""
    gap = abs(sum(float(t) for t in left) - sum(float(t) for t in right))
    return gap, sum(half_unit(t) for t in left) + sum(half_unit(t) for t in right)


def same_within_rounding(name, left, right):
    """Check that two sums of printed values agree within the rounding of every value in them; return gap / bound."""
    gap, bound = rounding_gap(left, right)
    require(gap <= bound + 1e-6, f'{name}: sums differ by {gap:,.1f}, more than the rounding bound {bound:,.1f}')
    return gap / bound if bound else 0.0


def population_interval(number, rate):
    """Return the range of populations consistent with a printed death count and rate per 100,000, or None."""
    # For very small populations the printed rate is not the printed count over a single population.
    if float(number) < CONFIG['population_minimum_deaths'] or float(rate) <= 0:
        return None
    low = (float(number) - half_unit(number)) / (float(rate) + half_unit(rate)) * 1e5
    high_rate = float(rate) - half_unit(rate)
    return low, (float(number) + half_unit(number)) / high_rate * 1e5 if high_rate > 0 else float('inf')


def common_population(name, intervals):
    """Check that one population fits every printed count and rate that share a denominator, and return its range."""
    intervals = [i for i in intervals if i]
    if len(intervals) < 2:
        return dict(n=len(intervals))
    low, high = max(i[0] for i in intervals), min(i[1] for i in intervals)
    require(low <= high * (1 + 1e-12), f'{name}: no single population fits all {len(intervals)} count/rate pairs')
    return dict(n=len(intervals), low=round(low), high=round(high))


def column_of(word, columns):
    """Return the label column whose x range holds the centre of a word, or None."""
    centre = (float(word['x0']) + float(word['x1'])) / 2
    return next((name for name, (low, high) in columns.items() if low <= centre < high), None)


def parse_cells(tokens, count, cell_format):
    """Return (value, lower, upper) for each of count printed cells, or None when the tokens do not form them."""
    # A 'plain' cell is one number; an 'interval' cell is two tokens, 'value' and '(lower-upper)'.
    if cell_format == 'plain':
        return [(t, '', '') for t in tokens] if len(tokens) == count and all(map(VALUE.match, tokens)) else None
    if len(tokens) != 2 * count:
        return None
    cells = []
    for value, interval in zip(tokens[::2], tokens[1::2]):
        bounds = INTERVAL.match(interval)
        if not (VALUE.match(value) and bounds):
            return None
        cells.append((value, bounds.group(1), bounds.group(2)))
    return cells


def table_layout(table):
    """Return one record per printed cell of an appendix table, with its row labels, and a summary of the layout."""
    spec = CONFIG['tables'][table]
    first, last = spec['pages']
    columns, start = spec['label_columns'], spec['value_start_x']
    lead = next(iter(columns))
    fields, cells = list(spec['cells']), list(itertools.product(*spec['cells'].values()))
    years = spec['cells'].get('year')
    blocks = defaultdict(list)
    for word in read_csv(WORDS):
        if word['document'] == spec['document'] and first <= int(word['page']) <= last:
            blocks[(int(word['page']), int(word['block']))].append(word)
    require({p for p, _ in blocks} == set(range(first, last + 1)), f'Table {table}: pages {first}-{last} not all present')
    records, page_text, header_years, notes, wrapped, held = [], defaultdict(list), defaultdict(list), [], [], None
    note_page = None

    def release():
        """Put a held label line back with the page text when no row has joined it."""
        nonlocal held
        if held:
            page_text[held[0]].append(held[1])
        held = None

    # PyMuPDF puts each printed row in its own text block; the other blocks are titles, column headers, notes,
    # page numbers and first lines of wrapped labels.
    for (page, block), words in sorted(blocks.items()):
        words.sort(key=lambda w: (int(w['line']), int(w['word'])))
        text = ' '.join(w['text'] for w in words)
        values = [w['text'] for w in words if float(w['x0']) >= start]
        labels = [w for w in words if float(w['x0']) < start]
        parsed = parse_cells(values, len(cells), spec['cell_format']) if values else None
        if parsed is None:
            release()
            # The table note starts 'Table <name>:' (the title has a full stop) and runs on to the page number.
            if text.startswith(f'Table {table}:'):
                notes.append(text)
                note_page = page
            elif note_page == page and not text.isdigit():
                notes[-1] += ' ' + text
            elif not values and labels and all(column_of(w, columns) == lead for w in labels):
                # Words of the first label column alone: the first line of a wrapped label, joined to the row just below.
                held = (page, text, max(float(w['y0']) for w in labels))
            else:
                page_text[page].append(text)
                lines = defaultdict(list)
                for w in words:
                    lines[w['line']].append(w)
                # A line of years alone is a year header; the x positions of its words give the printed year order.
                for line in lines.values():
                    if years and all(w['text'] in years for w in line):
                        header_years[page].extend((float(w['x0']), w['text']) for w in line)
            if text.isdigit():
                note_page = None
            continue
        note_page = None
        row_columns = defaultdict(list)
        for w in labels:
            column = column_of(w, columns)
            require(column, f'Table {table} page {page}: label {w["text"]!r} lies outside the label columns')
            row_columns[column].append(w['text'])
        if held and held[0] == page and min(float(w['y0']) for w in labels) - held[2] <= CONFIG['wrap_max_gap']:
            row_columns[lead].insert(0, held[1])
            wrapped.append(' '.join(row_columns[lead]))
            held = None
        release()
        row = {name: ' '.join(row_columns[name]) for name in columns}
        require(all(row.values()), f'Table {table} page {page}: row with an empty label: {text}')
        for key, (value, lower, upper) in zip(cells, parsed):
            records.append(dict(page=page, **row, **dict(zip(fields, key)), val=value, lower=lower, upper=upper))
    release()
    # Every page must carry the required header text and, where the table has years, the years in configured order.
    for page in range(first, last + 1):
        joined = ' '.join(page_text[page])
        required = spec['page_text']['every'] + (spec['page_text']['first'] if page == first else [])
        missing = [t for t in required if t not in joined]
        require(not missing, f'Table {table} page {page}: missing header text {missing}')
        if years:
            found = [y for _, y in sorted(header_years[page])]
            require(found == years, f'Table {table} page {page}: year headers {found}')
    require(len(records) == spec['rows'] * len(cells), f'Table {table}: {len(records) // len(cells)} rows, expected {spec["rows"]}')
    return records, dict(pages=f'{first}-{last}', rows=len(records) // len(cells),
                         wrapped_labels={label: wrapped.count(label) for label in dict.fromkeys(wrapped)}, notes=notes)


def check_intervals(table, records):
    """Check that every printed value lies inside its printed uncertainty interval."""
    outside = [r for r in records if not float(r['lower']) <= float(r['val']) <= float(r['upper'])]
    require(not outside, f'Table {table}: {len(outside)} values outside their uncertainty interval, e.g. {outside[:1]}')
    return dict(n=len(records), outside=0)


def gbd_deaths(requests, locations):
    """Return deaths (number, both sexes) by (location, age, cause, year) from the registered archives of the requests."""
    values = {}
    for entry in [f for f in RAW_CONFIG['files'] if f['request'] in requests]:
        with zipfile.ZipFile(raw_file(entry['path'])) as archive:
            member = next(m for m in archive.namelist() if m.lower().endswith('.csv'))
            with archive.open(member) as stream:
                for r in csv.DictReader(io.TextIOWrapper(stream, encoding='utf-8-sig', newline='')):
                    require((r['measure_name'], r['metric_name'], r['sex_name']) == ('Deaths', 'Number', 'Both'),
                            f'{entry["path"]}: unexpected measure, metric or sex')
                    if r['location_name'] in locations:
                        values[(r['location_name'], r['age_name'], r['cause_name'], r['year'])] = float(r['val'])
    return values

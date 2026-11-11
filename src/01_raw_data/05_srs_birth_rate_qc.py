"""Check the SRS state birth rates in two editions of the RBI Handbook of Statistics on Indian States and write them
as one table, as printed, to data/processed/raw_data/srs_birth_rate.csv."""
import csv
import re

import openpyxl

import raw_common as R

SPEC = R.CONFIG['srs_birth_rate']
VALUE = re.compile(r'^\d+(\.\d+)?$')


def read_table(table):
    """Return {(State/UT, year): printed text} from one Handbook table, across its sheets, and the rows absent from a sheet."""
    entry = next(f for f in R.CONFIG['files'] if f['path'] == table['path'])
    R.require(R.sha256(R.RAW / table['path']) == entry['sha256'], f'{table["path"]} differs from its registered checksum')
    workbook = openpyxl.load_workbook(R.RAW / table['path'], read_only=True, data_only=True)
    R.require(workbook.sheetnames == table['sheets'], f'{table["path"]}: sheets {workbook.sheetnames}')
    values, years_seen, sheet_states = {}, [], []
    for sheet in table['sheets']:
        # Empty cells are dropped, so a row missing a value or marker for some year comes up short.
        rows = [[c for c in r if c not in (None, '')] for r in workbook[sheet].iter_rows(values_only=True)]
        rows = [r for r in rows if r]
        header = next(r for r in rows if str(r[0]).startswith(SPEC['header_prefix']))
        years = header[1:]
        R.require(all(isinstance(y, int) for y in years), f'{table["path"]} {sheet}: year headers {years}')
        years_seen += years
        sheet_states.append(set())
        for r in rows[rows.index(header) + 1:]:
            if not isinstance(r[0], str) or len(r) == 1:
                continue
            R.require(len(r) == len(header), f'{table["path"]} {sheet}: row with an empty cell: {r}')
            name = SPEC['name_aliases'].get(r[0].strip(), r[0].strip())
            sheet_states[-1].add(name)
            for year, value in zip(years, r[1:]):
                R.require((name, year) not in values, f'{table["path"]}: {name} {year} printed twice')
                values[(name, year)] = str(value)
    R.require(years_seen == list(range(table['years'][0], table['years'][1] + 1)), f'{table["path"]}: years {years_seen}')
    absent = {s: [sheet for sheet, names in zip(table['sheets'], sheet_states) if s not in names] for s in set().union(*sheet_states)}
    return values, {s: v for s, v in absent.items() if v}


def check_birth_rates():
    read = [read_table(t) for t in SPEC['tables']]
    tables = [values for values, _ in read]
    low, high = SPEC['plausible_range']
    # '.' is not applicable and '-' not available; a value ending in '*' is a State/UT reported together with another.
    markers = {SPEC['not_applicable'], SPEC['not_available']}
    numeric = lambda v: float(v.rstrip(SPEC['combined_marker'])) if VALUE.match(v.rstrip(SPEC['combined_marker'])) else None
    checks, coverage = {}, {}
    for spec, (values, absent) in zip(SPEC['tables'], read):
        bad = [(k, v) for k, v in values.items() if v not in markers and not (numeric(v) is not None and low <= numeric(v) <= high)]
        R.require(not bad, f'{spec["path"]}: values that are not plausible birth rates or markers: {bad[:5]}')
        states = {s for s, _ in values}
        R.require(SPEC['national'] in states and SPEC['national'] not in absent, f'{spec["path"]}: no complete {SPEC["national"]} row')
        coverage[spec['path']] = dict(states=len(states) - 1, rows_absent_from_a_sheet=absent,
                                      combined_values=sorted(f'{s} {y}' for (s, y), v in values.items()
                                                             if v.endswith(SPEC['combined_marker'])))
    first, second = tables
    overlap = [k for k in first if k in second]
    differ = [(k, first[k], second[k]) for k in overlap if first[k] != second[k]]
    R.require(overlap and not differ, f'The editions disagree in overlapping years: {differ[:5]}')
    checks['editions_agree'] = dict(overlapping_values=len(overlap), differences=0)
    # A value far from both neighbouring years is allowed only as a printed irregularity listed in the configuration.
    listed = {(i['state'], i['year']): str(i['value']) for i in SPEC['printed_irregularities']}
    jumps = []
    for values in tables:
        for (state, year), v in values.items():
            around = [numeric(values.get((state, year + d), '.')) for d in (-1, 1)]
            if numeric(v) is not None and None not in around and all(abs(numeric(v) - a) > SPEC['isolated_jump'] for a in around):
                jumps.append((state, year, v))
    found = {(s, y): v for s, y, v in jumps}
    R.require(found == listed, f'Isolated jumps differ from the listed printed irregularities: {sorted(set(found.items()) ^ set(listed.items()))}')
    checks['printed_irregularities'] = [dict(state=s, year=y, value=v) for (s, y), v in sorted(found.items())]
    merged, source = {}, {}
    for spec, values in zip(SPEC['tables'], tables):
        merged.update(values)
        source.update({k: spec['path'] for k in values})
    states = sorted({s for s, _ in merged} - {SPEC['national']})
    years = sorted({y for _, y in merged})
    out = R.ROOT / 'data/processed/raw_data' / 'srs_birth_rate.csv'
    out.parent.mkdir(parents=True, exist_ok=True)
    pending = out.with_name(out.name + '.tmp')
    with pending.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream)
        writer.writerow(['state', 'year', 'printed', 'table'])
        writer.writerows([s, y, merged[(s, y)], source[(s, y)]] for s, y in sorted(merged))
    pending.replace(out)
    india = {str(y): merged[(SPEC['national'], y)] for y in (years[0], 2000, 2010, 2019, years[-1])}
    summary = dict(tables=len(tables), states=len(states), years=f'{years[0]}-{years[-1]}')
    R.write_report('05_srs_birth_rate_qc.json', __file__, summary, status='PASSED', checks=checks, coverage=coverage,
                   india_per_1000=india)
    print(f'[05] Complete; SRS birth rates for {len(states)} States/UTs, {years[0]}-{years[-1]}; editions agree on '
          f'{len(overlap)} overlapping values; {len(found)} printed irregularity listed', flush=True)


if __name__ == '__main__':
    check_birth_rates()

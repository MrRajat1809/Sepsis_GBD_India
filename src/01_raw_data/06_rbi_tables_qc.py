"""Check the RBI Handbook tables of SRS death, infant and maternal mortality rates and of state domestic product, and
write them as one table, as printed, to data/processed/raw_data/rbi_tables.csv."""
import csv
import re
from collections import defaultdict

import openpyxl

import raw_common as R

SPEC = R.CONFIG['rbi_tables']
VALUE = re.compile(r'^\d+(\.\d+)?$')


def expected_periods(spec):
    """Return the periods a table must cover: calendar years, financial years ('2011-12') or listed three-year periods."""
    if spec['kind'] == 'period':
        return spec['periods']
    first, last = spec['periods']
    return [y if spec['kind'] == 'year' else f'{y}-{str(y + 1)[2:]}' for y in range(first, last + 1)]


def read_table(name, spec):
    """Return {(State/UT, period): printed text}, the rows absent from a sheet and the row labels corrected."""
    entry = next(f for f in R.CONFIG['files'] if f['path'] == spec['path'])
    R.require(R.sha256(R.RAW / spec['path']) == entry['sha256'], f'{spec["path"]} differs from its registered checksum')
    workbook = openpyxl.load_workbook(R.RAW / spec['path'], read_only=True, data_only=True)
    R.require(workbook.sheetnames == spec['sheets'], f'{name}: sheets {workbook.sheetnames}')
    values, periods, sheet_states, aliased = {}, [], [], set()
    for sheet in spec['sheets']:
        # Empty cells are dropped, so a row missing a value or marker for some period comes up short.
        rows = [[c for c in r if c not in (None, '')] for r in workbook[sheet].iter_rows(values_only=True)]
        rows = [r for r in rows if r]
        header = next(i for i, r in enumerate(rows) if str(r[0]).startswith(spec.get('header_prefix', 'State')))
        # The domestic product tables print their periods on the row below the header.
        found, first = (rows[header][1:], header + 1) if spec['period_row'] == 'header' else (rows[header + 1], header + 2)
        periods += found
        sheet_states.append(set())
        for r in rows[first:]:
            if not isinstance(r[0], str) or len(r) == 1:
                continue
            R.require(len(r) == len(found) + 1, f'{name} {sheet}: row with an empty cell: {r}')
            label = r[0].strip()
            state = SPEC['name_aliases'].get(label, label)
            if state != label:
                aliased.add(f'{label} -> {state}')
            sheet_states[-1].add(state)
            for period, value in zip(found, r[1:]):
                R.require((state, period) not in values, f'{name}: {state} {period} printed twice')
                values[(state, period)] = str(value)
    R.require(periods == expected_periods(spec), f'{name}: periods {periods}')
    absent = {s: [sh for sh, names in zip(spec['sheets'], sheet_states) if s not in names] for s in set().union(*sheet_states)}
    return values, {s: v for s, v in absent.items() if v}, sorted(aliased)


def numeric(text, spec):
    """Return a printed value as a number, ignoring the combined marker, or None for a marker."""
    stripped = text.rstrip(spec['combined_marker'])
    return float(stripped) if VALUE.match(stripped) else None


def check_rbi_tables():
    tables, coverage = {}, {}
    for name, spec in SPEC['tables'].items():
        values, absent, aliased = read_table(name, spec)
        low, high = spec['range']
        bad = [(k, v) for k, v in values.items()
               if v not in spec['markers'] and not (numeric(v, spec) is not None and low <= numeric(v, spec) <= high)]
        R.require(not bad, f'{name}: values that are neither plausible nor markers: {bad[:5]}')
        states = {s for s, _ in values}
        if spec['national']:
            R.require(spec['national'] in states and spec['national'] not in absent, f'{name}: no complete {spec["national"]} row')
        tables[name] = values
        coverage[name] = dict(states=len(states) - bool(spec['national']), periods=f'{expected_periods(spec)[0]} to {expected_periods(spec)[-1]}',
                              values=sum(numeric(v, spec) is not None for v in values.values()),
                              not_available=sum(v in spec['markers'] for v in values.values()), rows_absent_from_a_sheet=absent,
                              combined_values=sorted(f'{s} {p}' for (s, p), v in values.items() if v.endswith(spec['combined_marker'])),
                              labels_corrected=aliased)
    checks = {}
    # In the base year current and constant prices are the same, so the two tables must agree up to rounding.
    base = SPEC['base_year']
    for total_current, capita_current, total_constant, capita_constant in SPEC['pairs']:
        for total, tolerance in ((('nsdp', total_current, total_constant), SPEC['base_year_tolerance_lakh']),
                                 (('per_capita', capita_current, capita_constant), SPEC['base_year_tolerance_rupees'])):
            label, current, constant = total
            gaps = [abs(numeric(tables[current][k], SPEC['tables'][current]) - numeric(v, SPEC['tables'][constant]))
                    for k, v in tables[constant].items() if k[1] == base and numeric(v, SPEC['tables'][constant]) is not None]
            R.require(gaps and max(gaps) <= tolerance, f'{label}: current and constant prices differ in {base} by up to {max(gaps)}')
            checks[f'{label}_base_year_current_equals_constant'] = dict(n=len(gaps), largest_difference=max(gaps))
        # NSDP (rupees lakh) * 1e5 / per-capita NSDP (rupees) is the population, which cannot depend on prices.
        implied = defaultdict(dict)
        for kind, total, capita in (('current', total_current, capita_current), ('constant', total_constant, capita_constant)):
            for key, v in tables[total].items():
                t, c = numeric(v, SPEC['tables'][total]), numeric(tables[capita].get(key, '-'), SPEC['tables'][capita])
                if t is not None and c is not None:
                    implied[key][kind] = t * 1e5 / c
        ratios = [p['current'] / p['constant'] for p in implied.values() if len(p) == 2]
        R.require(ratios and max(abs(r - 1) for r in ratios) <= SPEC['implied_population_tolerance'],
                  'Population implied by total and per-capita product differs between current and constant prices')
        checks['implied_population_current_over_constant'] = dict(n=len(ratios), min=min(ratios), max=max(ratios))
    out = R.ROOT / 'data/processed/raw_data' / 'rbi_tables.csv'
    out.parent.mkdir(parents=True, exist_ok=True)
    pending = out.with_name(out.name + '.tmp')
    with pending.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream)
        writer.writerow(['table', 'state', 'period', 'printed'])
        for name, values in tables.items():
            writer.writerows([name, s, p, v] for (s, p), v in sorted(values.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))))
    pending.replace(out)
    summary = dict(tables=len(tables), values=sum(c['values'] for c in coverage.values()))
    R.write_report('06_rbi_tables_qc.json', __file__, summary, status='PASSED', checks=checks, coverage=coverage)
    print(f'[06] Complete; {len(tables)} RBI Handbook tables, {summary["values"]:,} values; current and constant prices agree '
          f'in {base}; implied populations agree within {SPEC["implied_population_tolerance"]:.0e}', flush=True)


if __name__ == '__main__':
    check_rbi_tables()

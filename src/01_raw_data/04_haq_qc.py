"""Check the GBD 2016 Healthcare Access and Quality Index download for India and its 31 subnational units."""
import csv
import io
import zipfile
from collections import Counter

import raw_common as R

SPEC = R.CONFIG['haq']


def haq_rows():
    """Return the rows of the one data CSV in the HAQ archive (the other member is its codebook)."""
    with zipfile.ZipFile(R.RAW / SPEC['path']) as archive:
        members = archive.namelist()
        data = [m for m in members if m.lower().endswith('.csv') and 'CODEBOOK' not in m.upper()]
        R.require(len(data) == 1 and len(members) == 2, f'{SPEC["path"]}: expected one data CSV and one codebook, found {members}')
        with archive.open(data[0]) as stream:
            reader = csv.DictReader(io.TextIOWrapper(stream, encoding='utf-8-sig', newline=''))
            R.require(reader.fieldnames == SPEC['columns'], f'{SPEC["path"]}: unexpected columns {reader.fieldnames}')
            return list(reader)


def gbd2023_units():
    """Return India and its subnational units as named in the GBD 2023 all-cause download."""
    return {r['location_name'] for entry in R.files_for('allcause') for r in R.results_rows(R.RAW / entry['path'])}


def check_haq():
    rows = haq_rows()
    entry = next(f for f in R.CONFIG['files'] if f['path'] == SPEC['path'])
    R.require(len(rows) == entry['csv_rows'], f'{SPEC["path"]}: {len(rows)} rows, expected {entry["csv_rows"]}')
    # GBD 2016 names two of the units differently from GBD 2023; the aliases map them across.
    national, aliases = SPEC['national'], SPEC['name_aliases']
    india = [r for r in rows if r['location_name'] == national or r['parent_location'] == national]
    names = {aliases.get(r['location_name'], r['location_name']) for r in india}
    R.require(len(names) == SPEC['units'] + 1, f'{len(names) - 1} subnational units for {national}')
    R.require(names == gbd2023_units(), f'HAQ locations differ from GBD 2023: {sorted(names ^ gbd2023_units())}')
    years = {int(r['year_id']) for r in rows}
    R.require(sorted(years) == SPEC['years'], f'HAQ years {sorted(years)}')
    cells = Counter((r['location_name'], r['indicator_id'], r['year_id']) for r in india)
    R.require(max(cells.values()) == 1, 'Duplicate HAQ rows')
    R.require(len(cells) == len(names) * SPEC['indicators'] * len(years), 'Missing HAQ rows for India or its units')
    # One indicator is the HAQ Index itself; the others are the scaled scores of the amenable causes.
    index = [r for r in rows if r['indicator_id'] == SPEC['index_indicator_id']]
    outside = [r for r in index if not (0 <= float(r['lower']) <= float(r['val']) <= float(r['upper']) <= 100)]
    R.require(not outside, f'{len(outside)} HAQ Index values outside their interval or 0-100')
    R.require(any(r['location_name'] == SPEC['global'] for r in index), 'No global HAQ Index')
    indian = {r['location_name'] for r in india}
    values = {(aliases.get(r['location_name'], r['location_name']), int(r['year_id'])): float(r['val']) for r in index
              if r['location_name'] in indian or r['location_name'] == SPEC['global']}
    last = SPEC['years'][-1]
    units = sorted((values[(n, last)], n) for n in names if n != national)
    summary = dict(rows=len(rows), india_rows=len(india), units=len(names) - 1, years=sorted(years))
    R.write_report('04_haq_qc.json', __file__, summary, status='PASSED',
                   checks=dict(index_values_within_interval=len(index), cells_complete=len(cells)),
                   haq_index={f'{n} {y}': values[(n, y)] for n in (SPEC['global'], national) for y in (SPEC['years'][0], last)},
                   units_lowest_highest_last_year=dict(lowest=units[0], highest=units[-1]))
    print(f'[04] Complete; HAQ Index for {national}, {len(names) - 1} units and {len(years)} years; {last}: '
          f'{units[0][1]} {units[0][0]} to {units[-1][1]} {units[-1][0]}', flush=True)


if __name__ == '__main__':
    check_haq()

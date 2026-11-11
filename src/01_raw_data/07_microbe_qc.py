"""Check the IHME MICROBE downloads for India, 2021 (deaths by infectious syndrome, by pathogen and by antimicrobial
resistance status) and write them as one table, as downloaded, to data/processed/raw_data/microbe.csv."""
import csv
from collections import defaultdict

import raw_common as R

SPEC = R.CONFIG['microbe']
VALUES = ('Value', 'Lower', 'Upper')


def read_view(name, view):
    """Return {key: {metric: row}} for one view, after checking its number and rate files."""
    rows = defaultdict(dict)
    for metric, label in SPEC['metrics'].items():
        path = view[metric]
        entry = next(f for f in R.CONFIG['files'] if f['path'] == path)
        R.require(R.sha256(R.RAW / path) == entry['sha256'], f'{path} differs from its registered checksum')
        with (R.RAW / path).open(encoding='utf-8', newline='') as stream:
            records = list(csv.DictReader(stream))
        R.require(len(records) == view['rows'], f'{path}: {len(records)} rows, expected {view["rows"]}')
        for record in records:
            # Each download is the chart on screen, so every row must carry the location, age, sex, measure, year
            # and metric the chart was drawn for.
            for column, expected in {**SPEC['fixed'], 'Metric': label}.items():
                R.require(record[column] == expected, f'{path}: {column} is {record[column]!r}, expected {expected!r}')
            low, value, high = (float(record[c]) for c in ('Lower', 'Value', 'Upper'))
            R.require(0 <= low <= value <= high, f'{path}: value outside its interval: {record}')
            key = tuple(record[k] for k in view['key'])
            R.require(metric not in rows[key], f'{path}: {key} appears twice')
            rows[key][metric] = record
        if 'counterfactuals' in view:
            found = {r['Counterfactual'] for r in records}
            R.require(found == set(view['counterfactuals']), f'{path}: counterfactuals {sorted(found)}')
    R.require(all(len(m) == 2 for m in rows.values()), f'{name}: number and rate files cover different rows')
    return rows


def close(a, b, tolerance):
    """Return whether a and b agree within a relative tolerance (absolute for values below 1)."""
    return abs(a - b) <= tolerance * max(abs(a), abs(b), 1.0)


def check_microbe():
    views = {name: read_view(name, view) for name, view in SPEC['views'].items()}
    # Every count / rate pair, in every view, must imply the same population.
    populations = [float(m['number'][c]) / float(m['rate'][c]) * 1e5 for rows in views.values() for m in rows.values()
                   for c in VALUES if float(m['rate'][c]) > 0]
    spread = max(populations) / min(populations) - 1
    R.require(spread <= SPEC['implied_population_tolerance'], f'Counts and rates imply different populations (spread {spread:.2e})')
    tolerance = SPEC['sum_tolerance']
    deaths = lambda rows, key: float(rows[key]['number']['Value'])
    syndromes, detailed, resistance = views['syndromes'], views['amr_detailed'], views['amr_by_resistance']
    # Deaths associated with resistance, susceptible and untested make up each syndrome's deaths.
    by_syndrome = defaultdict(float)
    for (syndrome, _), metrics in detailed.items():
        by_syndrome[syndrome] += float(metrics['number']['Value'])
    R.require(set(by_syndrome) == {s for s, in syndromes}, 'The resistance view covers different syndromes')
    bad = [s for s, total in by_syndrome.items() if not close(total, deaths(syndromes, (s,)), tolerance)]
    R.require(not bad, f'Resistance categories do not add up to syndrome deaths: {bad}')
    assessed = {s for s, c in resistance}
    bad = [s for s in assessed if not close(deaths(resistance, (s, 'Associated')), deaths(detailed, (s, 'Associated')), tolerance)]
    R.require(not bad, f'Deaths associated with resistance differ between the two views: {bad}')
    bad = [s for s in assessed if deaths(resistance, (s, 'Attributable')) > deaths(resistance, (s, 'Associated'))]
    R.require(not bad, f'Attributable deaths exceed associated deaths: {bad}')
    out = R.ROOT / 'data/processed/raw_data' / 'microbe.csv'
    out.parent.mkdir(parents=True, exist_ok=True)
    pending = out.with_name(out.name + '.tmp')
    with pending.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream)
        writer.writerow(['view', 'infectious_syndrome', 'pathogen', 'pathogen_type', 'counterfactual', 'deaths', 'deaths_lower',
                         'deaths_upper', 'rate', 'rate_lower', 'rate_upper'])
        for name, rows in views.items():
            for metrics in rows.values():
                n, r = metrics['number'], metrics['rate']
                writer.writerow([name, n['Infectious syndrome'], n['Pathogen'], n.get('Pathogen Type', ''), n.get('Counterfactual', ''),
                                 n['Value'], n['Lower'], n['Upper'], r['Value'], r['Lower'], r['Upper']])
    pending.replace(out)
    total = sum(deaths(syndromes, k) for k in syndromes)
    associated = sum(deaths(resistance, (s, 'Associated')) for s in assessed)
    attributable = sum(deaths(resistance, (s, 'Attributable')) for s in assessed)
    summary = dict(views=len(views), rows=sum(len(v) for v in views.values()), infection_deaths=total,
                   deaths_associated_with_resistance=associated, deaths_attributable_to_resistance=attributable,
                   implied_population=sum(populations) / len(populations))
    R.write_report('07_microbe_qc.json', __file__, summary, status='PASSED',
                   checks=dict(implied_population_spread=spread, syndromes_with_resistance_status=len(assessed),
                               pathogen_deaths=sum(deaths(views['pathogens'], k) for k in views['pathogens'])))
    print(f'[07] Complete; {len(views)} MICROBE views, {summary["rows"]} rows; India 2021: {total:,.0f} infection-related deaths, '
          f'{associated:,.0f} associated with and {attributable:,.0f} attributable to resistance', flush=True)


if __name__ == '__main__':
    check_microbe()

"""Check that every figure and table exists, is unchanged since its stage wrote it and matches its sources in data/processed,
and write MANIFEST.csv (file, size, hash, producing stage, caption note)."""
import csv
import json
import struct
from collections import defaultdict

import figures_common as F

TOLERANCE = F.CONFIG['qc_relative_tolerance']


def close(a, b):
    """Return whether a equals b within the configured relative tolerance (absolute when b is below 1)."""
    return abs(float(a) - float(b)) <= TOLERANCE * max(1.0, abs(float(b)))


def read_output(filename):
    """Return the rows of a CSV this group wrote, as dicts."""
    with (F.OUT / filename).open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


def png_size(path):
    """Return a PNG's width and height in pixels, read from its header."""
    header = path.read_bytes()[:24]
    F.require(header[:8] == b'\x89PNG\r\n\x1a\n', f'{path.name}: not a PNG')
    return struct.unpack('>II', header[16:24])


def compare(name, pairs):
    """Check that each (label, plotted, source) pair matches, and return the number of values compared."""
    bad = [label for label, plotted, source in pairs if not close(plotted, source)]
    F.require(not bad, f'{name}: {len(bad)} plotted values differ from their source, e.g. {bad[:3]}')
    return len(pairs)


def check_values():
    """Check the plotted values and the central values of three tables against their sources; return the count per product."""
    counts = {}
    # Fig1: map rates, fills darkening as the rate rises, every mapped GBD unit in both panels
    rates = {(r['location'], int(r['year'])): float(r['age_standardised_rate']) for r in F.read_csv('state_estimates', 'rates_annual.csv')
             if r['sex'] == 'Both'}
    year, base = F.CONFIG['years']['map'], F.CONFIG['years']['map_base']
    figure = read_output('Fig1_data.csv')
    F.require({(r['panel'], int(r['year'])) for r in figure} == {('a', base), ('b', year)}, f'Fig1: panels are not {base} (a) and {year} (b)')
    pairs = [(f"{r['panel']}:{r['unit']}", r['value'], rates[(r['unit'], int(r['year']))]) for r in figure]
    lightness = [F.hex_to_oklch(r['fill'])[0] for r in sorted(figure, key=lambda r: float(r['value']))]
    F.require(all(b <= a + 1e-6 for a, b in zip(lightness, lightness[1:])), 'Fig1: fills do not darken as the rate rises')
    mapped = {r['gbd_unit'] for r in F.read_csv('raw_data', F.CONFIG['map']['boundary'])} - {''}
    for panel in ('a', 'b'):
        F.require({r['unit'] for r in read_output('Fig1_data.csv') if r['panel'] == panel} == mapped,
                  f'Fig1 panel {panel} does not cover the mapped GBD units exactly')
    counts['Fig1'] = compare('Fig1', pairs)

    # Fig2: India's deaths and intervals by type of cause (A) and deaths by age group (B, C)
    ui = {(r['measure'], int(r['year'])): r for r in F.read_csv('state_estimates', 'uncertainty_annual.csv')
          if r['location'] == F.INDIA and r['sex'] == 'Both'}
    group_of = {age: g for g, ages in F.CONFIG['trend_age_groups'].items() for age in ages}
    by_age = defaultdict(float)
    for r in F.read_csv('state_estimates', 'estimates_by_age.csv'):
        if r['location'] == F.INDIA:
            by_age[(r['component'], int(r['year']), group_of[r['age_group']])] += float(r['sepsis_deaths']) / 1e6
    pairs = []
    for r in read_output('Fig2_data.csv'):
        key = f"{r['panel']}:{r['year']}:{r['component']}:{r['age_group']}"
        if r['panel'] == 'A':
            source = ui[(r['component'], int(r['year']))]
            pairs += [(f'{key}:{k}', r[c], float(source[k]) / 1e6) for c, k in (('deaths_millions', 'val'), ('lower', 'lower'), ('upper', 'upper'))]
        else:
            pairs.append((key, r['deaths_millions'], by_age[(r['component'], int(r['year']), r['age_group'])]))
    counts['Fig2'] = compare('Fig2', pairs)

    # Fig3: values, panel of each cause, and ranks recomputed from the deaths
    causes = {(int(r['year']), r['cause']): r for r in F.read_csv('state_estimates', 'uncertainty_by_cause.csv') if r['location'] == F.INDIA}
    component = {'A': 'infectious', 'B': 'non_infectious'}
    pairs, ranks = [], defaultdict(list)
    for r in read_output('Fig3_data.csv'):
        source = causes[(int(r['year']), r['cause'])]
        F.require(source['component'] == component[r['panel']], f"Fig3: {r['cause']} is not {component[r['panel']]}")
        pairs += [(f"{r['panel']}:{r['year']}:{r['cause']}:{k}", r[k if k != 'val' else 'deaths'], source[k]) for k in ('val', 'lower', 'upper')]
        ranks[(r['panel'], r['year'])].append((int(r['rank']), r['cause']))
    for (panel, year), listed in ranks.items():
        order = sorted((c for (y, c), v in causes.items() if y == int(year) and v['component'] == component[panel] and float(v['val']) > 0),
                       key=lambda c: (-float(causes[(int(year), c)]['val']), c))
        F.require(all(order.index(c) + 1 == k for k, c in listed), f'Fig3: ranks in panel {panel}, {year} differ from the deaths')
    counts['Fig3'] = compare('Fig3', pairs)

    # Fig4: rates and intervals, parts adding up to the total, each unit's highlighted leading causes, causes per group
    year, per = F.CONFIG['years']['state_causes'], F.CONFIG['state_causes_per_group']
    by_cause = [r for r in F.read_csv('state_estimates', 'rates_by_cause.csv') if int(r['year']) == year]
    cause_rates = {(r['location'], r['cause']): float(r['sepsis_asr']) for r in by_cause}
    component = {r['cause']: r['component'] for r in by_cause}
    annual = {r['location']: r for r in F.read_csv('state_estimates', 'rates_annual.csv') if r['sex'] == 'Both' and int(r['year']) == year}
    total_ui = {r['location']: r for r in F.read_csv('state_estimates', 'uncertainty_annual.csv')
                if r['sex'] == 'Both' and int(r['year']) == year and r['measure'] == 'age_standardised_rate'}
    pairs, highlighted, shown = [], defaultdict(set), set()
    for r in read_output('Fig4_data.csv'):
        key = f"{r['panel']}:{r['unit']}:{r['measure']}"
        if r['panel'] == 'A':
            pairs.append((key, r['value'], annual[r['unit']][r['measure']]))
            if r['lower']:
                pairs += [(f'{key}:{k}', r[k], total_ui[r['unit']][k]) for k in ('lower', 'upper')]
            continue
        pairs.append((key, r['value'], cause_rates[(r['unit'], r['measure'])]))
        shown.add(r['measure'])
        if r['leading'] == '1':
            highlighted[r['unit']].add(r['measure'])
    for unit, row in annual.items():
        pairs.append((f'A:{unit}:parts', float(row['asr_infectious']) + float(row['asr_non_infectious']), row['age_standardised_rate']))
        leaders = {max((c for c in component if component[c] == g), key=lambda c: cause_rates[(unit, c)]) for g in ('infectious', 'non_infectious')}
        F.require(highlighted[unit] == leaders, f'Fig4: {unit} highlights {sorted(highlighted[unit])}, but its leading causes are {sorted(leaders)}')
        F.require(leaders <= shown, f'Fig4: a leading cause of {unit} is not shown')
    F.require(all(sum(component[c] == g for c in shown) >= per for g in ('infectious', 'non_infectious')),
              f'Fig4: fewer than {per} causes in a group')
    counts['Fig4'] = compare('Fig4', pairs)

    # Fig5: ratios and hollow points (A), trend (B), waterfall steps adding up to the count ratio's change (C), and the
    # count ratio as the product of its three factors
    visibility = {(r['unit'], int(r['year'])): r for r in F.read_csv('mccd_visibility', 'visibility.csv')}
    changes = {(r['unit'], r['measure']): r['annual_percent_change'] for r in F.read_csv('mccd_visibility', 'trends.csv')}
    rows_name = F.CONFIG['visibility_rows']
    flag = F.CONFIG['registered_over_estimated_flag']
    pairs, steps = [], {}
    for r in read_output('Fig5_data.csv'):
        if r['panel'] == 'A':
            source = visibility[(rows_name['india'] if r['unit'] == F.INDIA else r['unit'], int(r['year']))]
            measure = r['measure'].replace('_percent', '')
            pairs.append((f"A:{r['unit']}:{measure}", r['value'], 100 * float(source[measure])))
            hollow = r['unit'] != F.INDIA and source['registration_completeness'] != '' and float(source['registration_completeness']) > flag
            F.require(int(r['hollow']) == hollow, f"Fig5: {r['unit']} is drawn {'hollow' if r['hollow'] == '1' else 'filled'} wrongly")
        elif r['panel'] == 'B':
            pairs.append((f"B:{r['year']}", r['value'], 100 * float(visibility[(r['unit'], int(r['year']))]['visibility_count'])))
        else:
            pairs.append((f"C:{r['measure']}", r['value'], changes[(r['unit'], r['measure'])]))
            steps[r['measure']] = (float(r['start']), float(r['value']))
    factors = [steps[m] for m in ('registration_completeness', 'certification_coverage', 'visibility_share')]
    pairs += [(f'C:start:{k}', start, sum(v for _, v in factors[:k])) for k, (start, _) in enumerate(factors)]
    F.require(steps['visibility_count'][0] == 0 and abs(sum(v for _, v in factors) - steps['visibility_count'][1]) < 0.1,
              'Fig5: the factors in panel C do not add up to the change in the count ratio')
    trend = [s for (u, _), s in visibility.items() if u == rows_name['trend'] and s['registration_completeness'] != '']
    pairs += [(f"identity:{s['year']}", float(s['visibility_share']) * float(s['certification_coverage']) * float(s['registration_completeness']),
               s['visibility_count']) for s in trend]
    counts['Fig5'] = compare('Fig5', pairs)

    # Tables: the central values of Table1, SuppTable6 and SuppTable7
    deaths = {(r['location'], int(r['year'])): r for r in F.read_csv('state_estimates', 'uncertainty_annual.csv')
              if r['sex'] == 'Both' and r['measure'] == 'sepsis_deaths'}
    table = read_output('Table1.csv')
    pairs = []
    for r in table:
        for y in F.CONFIG['years']['tables']:
            cell = next(v for k, v in r.items() if k.startswith(str(y)))
            pairs.append((f"{r['Location']}:{y}", round(float(cell.split(' ')[0].replace(',', '')), 1),
                          round(float(deaths[(r['Location'], y)]['val']) / 1000, 1)))
    counts['Table1'] = compare('Table1', pairs)

    microbe = [r for r in F.read_csv('raw_data', 'microbe.csv')]
    syndromes = {r['infectious_syndrome']: r for r in microbe if r['view'] == 'syndromes'}
    pairs = []
    for r in read_output('SuppTable6.csv'):
        if r['Infectious syndrome'] in syndromes:
            pairs.append((r['Infectious syndrome'], float(r['Deaths (thousands, 95% UI)'].split(' ')[0].replace(',', '')),
                          round(float(syndromes[r['Infectious syndrome']]['deaths']) / 1000, 1)))
    F.require(len(pairs) == len(syndromes), 'SuppTable6 does not list every infectious syndrome')
    counts['SuppTable6'] = compare('SuppTable6', pairs)
    pathogens = {r['pathogen']: r for r in microbe if r['view'] == 'pathogens'}
    pairs = [(r['Pathogen'], float(r['Deaths (thousands, 95% UI)'].split(' ')[0].replace(',', '')),
              round(float(pathogens[r['Pathogen']]['deaths']) / 1000, 1))
             for r in read_output('SuppTable7.csv')]
    F.require(len(pairs) == len(pathogens), 'SuppTable7 does not list every pathogen')
    counts['SuppTable7'] = compare('SuppTable7', pairs)
    return counts


def build_qc():
    expected = F.CONFIG['expected']
    reports = {p.name: json.loads(p.read_text(encoding='utf-8')) for p in sorted(F.OUT.glob('0[0-9]_*.json')) if not p.name.startswith('07_')}
    F.require(len(reports) == 6, f'Expected the reports of stages 01-06, found {sorted(reports)}')
    producer, captions, stale = {}, {}, []
    for name, report in reports.items():
        # Inputs changed since the stage ran; outputs missing or changed since it wrote them
        for key, digest in report['inputs'].items():
            group, filename = key.split('/', 1)
            if F.sha256(F.ROOT / F.CONFIG['directories'][group] / filename) != digest:
                stale.append(f'{name}: {key}')
        recorded = report.get('files') or report.get('export', {}).get('files', {})
        for filename, record in recorded.items():
            digest = record if isinstance(record, str) else record['sha256']
            F.require((F.OUT / filename).is_file(), f'{filename} missing (recorded by {name})')
            F.require(F.sha256(F.OUT / filename) == digest, f'{filename} changed after {name} wrote it')
            producer[filename] = name
        # Figures: PNG at the recorded size and the configured resolution, PDF without a creation date
        if 'export' in report:
            figure = report['summary']['figure']
            captions[figure] = report.get('caption_note', '')
            width, height = png_size(F.OUT / f'{figure}.png')
            F.require((width, height) == (round(report['export']['width_inches'] * F.CONFIG['dpi']),
                                          round(report['export']['height_inches'] * F.CONFIG['dpi'])),
                      f'{figure}.png: unexpected size {width}x{height}')
            F.require(b'/CreationDate' not in (F.OUT / f'{figure}.pdf').read_bytes(), f'{figure}.pdf carries a creation date')
            producer[f'{figure}_data.csv'] = name
    F.require(not stale, 'Reports rest on changed inputs; rerun the stages: ' + '; '.join(stale))
    wanted = [f'{f}.{e}' for f in expected['figures'] for e in ('pdf', 'png')] + [f'{f}_data.csv' for f in expected['figures']]
    wanted += [f'{t}.{e}' for t in expected['tables'] for e in ('csv', 'tex')]
    missing = [w for w in wanted if w not in producer]
    F.require(not missing, f'Products not recorded by any stage: {missing}')
    counts = check_values()
    rows = []
    for filename in wanted:
        stem = filename.split('.')[0].replace('_data', '')
        rows.append([filename, (F.OUT / filename).stat().st_size, F.sha256(F.OUT / filename), producer[filename].replace('.json', '.py'),
                     captions.get(stem, '') if filename.endswith('.pdf') else ''])
    F.write_rows('MANIFEST.csv', ['file', 'bytes', 'sha256', 'stage', 'caption_note'], rows)
    summary = dict(figures=len(expected['figures']), tables=len(expected['tables']), files=len(rows),
                   values_checked=sum(counts.values()))
    F.write_report('07_figures_qc.json', __file__, summary,
                   inputs=[('state_estimates', 'rates_annual.csv'), ('state_estimates', 'uncertainty_annual.csv'),
                           ('state_estimates', 'estimates_by_age.csv'), ('state_estimates', 'uncertainty_by_cause.csv'),
                           ('state_estimates', 'rates_by_cause.csv'), ('mccd_visibility', 'visibility.csv'),
                           ('mccd_visibility', 'trends.csv'), ('raw_data', 'microbe.csv'), ('raw_data', F.CONFIG['map']['boundary'])],
                   values_checked=counts, manifest_sha256=F.sha256(F.OUT / 'MANIFEST.csv'))
    print(f"[07] Complete; {summary['figures']} figures and {summary['tables']} tables ({summary['files']} files) checked; "
          f"{summary['values_checked']:,} plotted or tabulated values match their sources", flush=True)


if __name__ == '__main__':
    build_qc()

"""Extract appendix Table S8 (sepsis-related deaths by region and country, all ages) as printed and check that it adds up."""
from collections import defaultdict

import appendix_common as A

SPEC = A.CONFIG['tables']['S8']
HEADER = ['page', 'location', 'location_type', 'year', 'cause_group', 'metric', 'val', 'lower', 'upper']


def extract_table_s8():
    records, layout = A.table_layout('S8')
    regions = set(SPEC['regions'])
    for r in records:
        r['location_type'] = 'Region' if r['location'] in regions else 'Country'
    checks = dict(intervals=A.check_intervals('S8', records))
    cell = {(r['location'], r['year'], r['cause_group'], r['metric']): r['val'] for r in records}
    locations = list(dict.fromkeys(r['location'] for r in records))
    A.require(len(locations) == SPEC['rows'], f'Table S8: {SPEC["rows"] - len(locations)} repeated location names')
    A.require(regions <= set(locations), f'Table S8: regions not found {sorted(regions - set(locations))}')
    A.require(A.CONFIG['gbd2021_comparison']['india'] in locations, 'Table S8: India not found')
    all_causes, non_infectious = SPEC['cells']['cause_group']
    exceed = [(l, y, m) for l in locations for y in SPEC['cells']['year'] for m in SPEC['cells']['metric']
              if float(cell[(l, y, non_infectious, m)]) - A.half_unit(cell[(l, y, non_infectious, m)])
              > float(cell[(l, y, all_causes, m)]) + A.half_unit(cell[(l, y, all_causes, m)])]
    A.require(not exceed, f'Table S8: non-infectious deaths exceed deaths from all causes for {exceed[:3]}')
    checks['non_infectious_within_all_causes'] = dict(n=len(locations) * 6, exceed=0)  # 3 years x 2 metrics
    # The counts and rates of one location and year share that location's population as denominator.
    fits = [A.common_population(f'Table S8 {l} {y}', [A.population_interval(cell[(l, y, g, 'Number')], cell[(l, y, g, 'Rate')])
                                                      for g in SPEC['cells']['cause_group']])
            for l in locations for y in SPEC['cells']['year']]
    checks['one_population_per_location_year'] = dict(location_years=len(fits), compared=sum(f['n'] > 1 for f in fits))
    # The regions and the countries each cover the world, so their sums must agree within rounding.
    sums = {}
    for year in SPEC['cells']['year']:
        for group in SPEC['cells']['cause_group']:
            parts = defaultdict(list)
            for l in locations:
                parts['Region' if l in regions else 'Country'].append(cell[(l, year, group, 'Number')])
            sums[f'{year} {group}'] = dict(regions=sum(map(float, parts['Region'])), countries=sum(map(float, parts['Country'])),
                                           gap_over_bound=A.same_within_rounding(f'Table S8 {year} {group}: regions / countries',
                                                                                 parts['Region'], parts['Country']))
    checks['regions_equal_countries'] = sums
    rows = [[r[h] for h in HEADER] for r in records]
    A.write_csv('table_s8.csv', HEADER, rows)
    india = {f'{y} {g}': cell[('India', y, g, 'Number')] for y in SPEC['cells']['year'] for g in SPEC['cells']['cause_group']}
    summary = dict(locations=len(locations), regions=len(regions), countries=len(locations) - len(regions), cells=len(rows))
    A.write_report('02_table_s8.json', __file__, summary, status='PASSED', layout=layout, india_deaths=india, checks=checks)
    print(f'[02] Complete; Table S8: {len(locations)} locations, {len(rows):,} cells; '
          f'{len(checks)} checks passed', flush=True)


if __name__ == '__main__':
    extract_table_s8()

"""Check the GBD 2021 Results Tool downloads against their requests and against each other."""
from collections import defaultdict

import raw_common as R

TOL = R.CONFIG['tolerances']
KEY = ('location_name', 'age_name', 'cause_name', 'year')
UNITS_EXCLUDED = ('India', 'Global')


def load(request, files):
    """Return the values of every file of the request, appending each file's summary to files."""
    values = {}
    for entry in R.files_for(request):
        part, summary = R.load_values(entry, KEY)
        values.update(part)
        files.append(summary)
    return values


def ages_to_all_ages(name, values):
    """Check that the age groups add up to All ages wherever All ages exceeds one death."""
    total = defaultdict(float)
    for (location, age, cause, year), value in values.items():
        if age != 'All ages':
            total[(location, cause, year)] += value
    return R.exact(name, (total[(l, c, y)] / v for (l, a, c, y), v in values.items() if a == 'All ages' and v > 1),
                   TOL['sum_identity'])


def by_location_age_year(values):
    """Return the sum over causes for each location, age group and year."""
    total = defaultdict(float)
    for (location, age, cause, year), value in values.items():
        total[(location, age, year)] += value
    return total


def states_to_india(name, values):
    """Check that the 31 subnational units add up to India for every key where India is above the minimum."""
    total = defaultdict(float)
    for (location, age, cause, year), value in values.items():
        if location not in UNITS_EXCLUDED:
            total[(age, cause, year)] += value
    return R.exact(name, (total[(a, c, y)] / v for (l, a, c, y), v in values.items()
                          if l == 'India' and v > TOL['states_minimum_india_value']), TOL['states_to_india'])


def check_downloads():
    files, checks = [], {}
    print('[03] Reading GBD 2021 downloads', flush=True)
    level2, level3, level4 = load('R6_level2', files), load('R6_level3', files), load('R6_level4', files)
    R.require({k[2] for k in level4} == set(R.CAUSES['level4_causes']), 'Level 4 file does not hold the five level 4 causes')
    for name, values in (('level2', level2), ('level3', level3), ('level4', level4)):
        checks[f'{name}_ages_to_all_ages'] = ages_to_all_ages(f'GBD 2021 {name} ages / All ages', values)
        checks[f'{name}_states_to_india'] = states_to_india(f'GBD 2021 {name} states / India', values)
    total2, total3 = by_location_age_year(level2), by_location_age_year(level3)
    checks['level3_to_level2'] = R.exact('GBD 2021 level 3 / level 2', (total3[k] / v for k, v in total2.items() if v > 0),
                                         TOL['sum_identity'])
    shares = {}
    for cause, parent in R.CAUSES['level4_causes'].items():
        values = [v / level3[(l, a, parent, y)] for (l, a, c, y), v in level4.items()
                  if c == cause and level3.get((l, a, parent, y), 0) > 0]
        R.require(values and max(values) <= 1 + 1e-9, f'{cause} exceeds its parent {parent}')
        shares[cause] = dict(n=len(values), max_share=max(values))
    checks['level4_within_parent'] = shares
    summary = dict(files=len(files), rows=sum(f['rows'] for f in files), level3_causes=len({k[2] for k in level3}))
    R.write_report('03_gbd2021_qc.json', __file__, summary, status='PASSED', files=files, checks=checks)
    print(f'[03] Complete; {len(files)} GBD 2021 files, {summary["rows"]:,} rows, {len(checks)} checks passed', flush=True)


if __name__ == '__main__':
    check_downloads()

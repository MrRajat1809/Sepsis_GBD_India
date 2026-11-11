"""Check the GBD 2023 Results Tool downloads against their requests and against each other."""
from collections import defaultdict

import raw_common as R

TOL = R.CONFIG['tolerances']
INDIA = 'India'
YLL = 'YLLs (Years of Life Lost)'


def load(requests, key_fields, files):
    """Return the values of every file of the requests, appending each file's summary to files."""
    values = {}
    for entry in R.files_for(*requests):
        part, summary = R.load_values(entry, key_fields)
        values.update(part)
        files.append(summary)
    return values


def states_to_india(name, values, location_index):
    """Check that the 31 subnational units add up to India for every key where India is above the minimum."""
    total, india = defaultdict(float), {}
    for key, value in values.items():
        rest = key[:location_index] + key[location_index + 1:]
        if key[location_index] == INDIA:
            india[rest] = value
        else:
            total[rest] += value
    return R.exact(name, (total[k] / v for k, v in india.items() if v > TOL['states_minimum_india_value']),
                   TOL['states_to_india'])


def within_state_range(values):
    """Check that India's rate lies within the range of its 31 units for every key (rates are not additive)."""
    ranges, outside = defaultdict(list), 0
    for (location, *rest), value in values.items():
        if location != INDIA:
            ranges[tuple(rest)].append(value)
    for (location, *rest), value in values.items():
        if location == INDIA:
            outside += not (min(ranges[tuple(rest)]) - 1e-9 <= value <= max(ranges[tuple(rest)]) + 1e-9)
    R.require(outside == 0, f'{outside} India rates outside the range of the 31 units')
    return dict(n=len(ranges), outside=outside)


def sum_over_causes(name, values, causes, reference):
    """Check that the given causes add up to the all-cause reference for every location, sex and year."""
    total = defaultdict(float)
    for (location, sex, cause, year), value in values.items():
        if cause in causes:
            total[(location, sex, year)] += value
    return R.exact(name, (total[k] / reference[k] for k in total), TOL['sum_identity'])


def children_to_parent(name, children, parent_of, parents):
    """Check that the child causes add up to their parent for every location, sex and year."""
    total = defaultdict(float)
    for (location, sex, cause, year), value in children.items():
        total[(location, sex, parent_of[cause], year)] += value
    return R.exact(name, (total[k] / parents[k] for k in total if parents[k] > 0), TOL['sum_identity'])


def level4_share(values, parents):
    """Check that each level 4 cause never exceeds its level 3 parent and return its largest share."""
    out = {}
    for cause, parent in R.CAUSES['level4_causes'].items():
        shares = [v / parents[(l, s, parent, y)] for (l, s, c, y), v in values.items()
                  if c == cause and parents.get((l, s, parent, y), 0) > 0]
        R.require(shares and max(shares) <= 1 + 1e-9, f'{cause} exceeds its parent {parent}')
        out[cause] = dict(n=len(shares), max_share=max(shares))
    return out


def check_downloads():
    level2, parent3, _ = R.cause_hierarchy()
    level4 = list(R.CAUSES['level4_causes'])
    files, checks = [], {}
    print('[02] Reading GBD 2023 downloads', flush=True)
    allcause = load(['allcause'], ('measure_name', 'metric_name', 'age_name', 'location_name', 'sex_name', 'year'), files)
    # Keyed by (location, sex, year).
    deaths = {k[3:]: v for k, v in allcause.items() if k[:3] == ('Deaths', 'Number', 'All ages')}
    asr = {k[3:]: v for k, v in allcause.items() if k[:3] == ('Deaths', 'Rate', 'Age-standardized')}
    ylls = {k[3:]: v for k, v in allcause.items() if k[:3] == (YLL, 'Number', 'All ages')}
    checks['allcause_states_to_india'] = states_to_india('all-cause deaths and YLLs',
                                                         {k: v for k, v in allcause.items() if k[1] == 'Number'}, 3)

    key = ('location_name', 'sex_name', 'cause_name', 'year')
    r1, r2 = load(['R1'], key, files), load(['R2'], key, files)
    causes3 = {k[2] for k in r1}
    R.require(causes3 <= set(parent3), f'Level 3 causes missing from the cause list: {sorted(causes3 - set(parent3))}')
    R.require(set(r2) == set(r1), 'Request 2 keys differ from Request 1')
    checks['R1_level3_to_allcause'] = sum_over_causes('R1 level 3 / all causes', r1, causes3, deaths)
    checks['R1_states_to_india'] = states_to_india('R1 states / India', r1, 0)
    checks['R2_level3_to_allcause_rate'] = sum_over_causes('R2 level 3 / all-cause rate', r2, causes3, asr)
    checks['R2_india_within_states'] = within_state_range(r2)

    r3a, r3b = load(['R3a'], key, files), load(['R3b'], key, files)
    R.require({k[2] for k in r3a} == set(level2) | set(level4), 'Request 3 causes are not level 2 plus the level 4 causes')
    R.require(set(r3b) == set(r3a), 'Request 3b keys differ from Request 3a')
    l2a = {k: v for k, v in r3a.items() if k[2] in level2}
    l2b = {k: v for k, v in r3b.items() if k[2] in level2}
    checks['R3a_level2_to_allcause'] = sum_over_causes('R3a level 2 / all causes', r3a, set(level2), deaths)
    checks['R3a_level3_to_level2'] = children_to_parent('R1 level 3 / R3a level 2', r1, parent3, l2a)
    checks['R3a_level4_within_parent'] = level4_share({k: v for k, v in r3a.items() if k[2] in level4}, r1)
    checks['R3a_states_to_india'] = states_to_india('R3a states / India', r3a, 0)
    checks['R3b_level2_to_allcause_rate'] = sum_over_causes('R3b level 2 / all-cause rate', r3b, set(level2), asr)
    checks['R3b_level3_to_level2_rate'] = children_to_parent('R2 level 3 / R3b level 2', r2, parent3, l2b)
    checks['R3b_level4_within_parent'] = level4_share({k: v for k, v in r3b.items() if k[2] in level4}, r2)
    checks['R3b_india_within_states'] = within_state_range(r3b)

    r5 = load(['R5'], ('location_name', 'age_name', 'metric_name', 'year'), files)
    groups = R.CAUSES['age_groups']
    locations, years = {k[0] for k in r5}, {k[3] for k in r5}
    checks['R5_ages_to_all_ages'] = R.exact('R5 age groups / All ages',
                                            (sum(r5[(l, a, 'Number', y)] for a in groups) / r5[(l, 'All ages', 'Number', y)]
                                             for l in locations for y in years), TOL['sum_identity'])
    checks['R5_to_allcause'] = R.exact('R5 All ages / all-cause file',
                                       (r5[(l, 'All ages', 'Number', y)] / deaths[(l, 'Both', y)] for l in locations for y in years),
                                       TOL['sum_identity'])
    checks['R5_states_to_india'] = states_to_india('R5 states / India', {k: v for k, v in r5.items() if k[2] == 'Number'}, 0)
    population = lambda l, a, y: r5[(l, a, 'Number', y)] / r5[(l, a, 'Rate', y)] * 1e5
    checks['R5_population_ages_to_all_ages'] = R.exact('R5 implied population',
                                                       (sum(population(l, a, y) for a in groups) / population(l, 'All ages', y)
                                                        for l in locations for y in years), TOL['states_to_india'])

    # Request 4 is checked only once its files are registered.
    present = [f for f in R.files_for('R4')]
    if present:
        r4 = load(['R4'], ('measure_name', 'location_name', 'age_name', 'cause_name', 'year'), files)
        R.require({k[3] for k in r4} == causes3 | set(level4), 'Request 4 causes are not level 3 plus the level 4 causes')
        by_age = defaultdict(float)
        for (measure, location, age, cause, year), value in r4.items():
            by_age[(measure, location, cause, year)] += value
        reference = {**{k: v for k, v in r1.items() if k[1] == 'Both'}, **{k: v for k, v in r3a.items() if k[1] == 'Both'}}
        checks['R4_ages_to_all_ages_deaths'] = R.exact('R4 age groups / R1 and R3a all ages',
                                                       (v / reference[(l, 'Both', c, y)] for (m, l, c, y), v in by_age.items()
                                                        if m == 'Deaths' and reference.get((l, 'Both', c, y), 0) > 0), TOL['sum_identity'])
        total = defaultdict(float)
        for (measure, location, cause, year), value in by_age.items():
            if measure == YLL and cause in causes3:
                total[(location, 'Both', year)] += value
        checks['R4_ylls_to_allcause'] = R.exact('R4 level 3 YLLs / all-cause YLLs',
                                                (v / ylls[k] for k, v in total.items()), TOL['sum_identity'])
        checks['R4_states_to_india'] = states_to_india('R4 states / India', r4, 1)
    pending = [p['path'] for p in R.CONFIG['pending'] if p['path'] not in {f['path'] for f in R.CONFIG['files']}]
    summary = dict(files=len(files), rows=sum(f['rows'] for f in files), level3_causes=len(causes3),
                   level2_causes=len(level2), pending=pending)
    R.write_report('02_gbd2023_qc.json', __file__, summary, status='PASSED', files=files, checks=checks)
    print(f'[02] Complete; {len(files)} GBD 2023 files, {summary["rows"]:,} rows, {len(checks)} checks passed; '
          f'{len(pending)} pending', flush=True)


if __name__ == '__main__':
    check_downloads()

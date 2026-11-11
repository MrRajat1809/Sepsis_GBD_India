"""Extract appendix Table S10 (global sepsis-related deaths by underlying cause and age group) as printed and check that it adds up."""
from collections import Counter, defaultdict

import appendix_common as A

SPEC = A.CONFIG['tables']['S10']
HEADER = ['page', 'cause', 'cause_level', 'cause_type', 'age_group', 'year', 'metric', 'val', 'lower', 'upper']
YEARS, ALL_AGES, AGES = SPEC['cells']['year'], SPEC['all_ages'], SPEC['age_groups']


def check_structure(records):
    """Check that levels, types and age groups are known, and that each cause has one type, an all-ages row and no repeated row."""
    rows = {(r['cause'], r['cause_level'], r['age_group']) for r in records}
    A.require(len(rows) * len(YEARS) * 2 == len(records), 'Table S10: a cause, level and age group is printed twice')
    A.require({r['cause_level'] for r in records} <= set(SPEC['levels']), 'Table S10: unexpected cause level')
    A.require({r['cause_type'] for r in records} <= set(SPEC['types']), 'Table S10: unexpected cause type')
    A.require({a for _, _, a in rows} <= set(AGES) | {ALL_AGES}, 'Table S10: unexpected age group')
    causes = {(c, l) for c, l, _ in rows}
    A.require(all((c, l, ALL_AGES) in rows for c, l in causes), 'Table S10: a cause has no all-ages row')
    types = defaultdict(set)
    for r in records:
        types[(r['cause'], r['cause_level'])].add(r['cause_type'])
    A.require(all(len(t) == 1 for t in types.values()), 'Table S10: a cause is printed with two cause types')
    return dict(causes=len(causes), by_level=dict(Counter(l for _, l in causes)),
                age_rows_not_printed=len(causes) * (len(AGES) + 1) - len(rows))


def check_age_sums(number):
    """Check that age groups add up to all ages within rounding, except the printed irregularities listed in the configuration."""
    listed = {(e['cause'], e['cause_level'], e['year']) for e in SPEC['age_sum_exceptions']}
    ratios, irregular = [], []
    for (cause, level, age, year), value in number.items():
        if age == ALL_AGES:
            parts = [number[(cause, level, a, year)] for a in AGES if (cause, level, a, year) in number]
            gap, bound = A.rounding_gap(parts, [value])
            if gap <= bound + 1e-6:
                ratios.append(gap / bound if bound else 0.0)
                continue
            A.require((cause, level, year) in listed, f'Table S10 {cause} (level {level}) {year}: age groups add up to '
                      f'{sum(map(float, parts)):,.0f}, all ages {value}; beyond the rounding bound {bound:,.1f}')
            irregular.append(dict(cause=cause, cause_level=level, year=year, age_groups_sum=sum(map(float, parts)),
                                  all_ages=value, rounding_bound=bound))
    A.require(len(irregular) == len(listed), f'Table S10: listed age-sum exceptions not found: {sorted(listed)}')
    return dict(n=len(ratios) + len(irregular), max_gap_over_bound=max(ratios), printed_irregularities=irregular)


def check_level_totals(number, types):
    """Check that, within each cause type, levels 1-3 add up to the level above; level 4 covers only some level 3 causes."""
    out = {}
    for kind in SPEC['types']:
        for year in YEARS:
            totals = {level: [v for (c, l, a, y), v in number.items() if a == ALL_AGES and y == year and l == level
                              and types[(c, l)] == kind] for level in SPEC['levels'][:4]}
            out[f'{kind} {year}'] = {f'level {low} / level {high}': A.same_within_rounding(
                f'Table S10 {kind} {year}: level {low} / level {high}', totals[low], totals[high])
                for high, low in zip(SPEC['levels'][:3], SPEC['levels'][1:4])}
    return out


def check_global_total(number):
    """Check that the level 0.5 causes add up to the regions, and to the countries, of Table S8."""
    s8 = A.read_csv('table_s8.csv')
    out = {}
    for year in YEARS:
        top = [v for (c, l, a, y), v in number.items() if l == SPEC['levels'][0] and a == ALL_AGES and y == year]
        for kind in ('Region', 'Country'):
            parts = [r['val'] for r in s8 if r['location_type'] == kind and r['year'] == year
                     and r['cause_group'] == 'All causes' and r['metric'] == 'Number']
            out[f'{year} {kind.lower()} sum'] = A.same_within_rounding(f'Table S10 {year} / Table S8 {kind} sum', top, parts)
    return out


def extract_table_s10():
    records, layout = A.table_layout('S10')
    checks = dict(intervals=A.check_intervals('S10', records), structure=check_structure(records))
    number = {(r['cause'], r['cause_level'], r['age_group'], r['year']): r['val'] for r in records if r['metric'] == 'Number'}
    rate = {(r['cause'], r['cause_level'], r['age_group'], r['year']): r['val'] for r in records if r['metric'] == 'Rate'}
    types = {(r['cause'], r['cause_level']): r['cause_type'] for r in records}
    checks['age_groups_to_all_ages'] = check_age_sums(number)
    # All causes in one age group and year share the world population of that age group as denominator.
    populations = defaultdict(list)
    for key, value in number.items():
        populations[key[2:]].append(A.population_interval(value, rate[key]))
    checks['one_population_per_age_year'] = {f'{a} {y}': A.common_population(f'Table S10 {a} {y}', i)
                                             for (a, y), i in sorted(populations.items())}
    checks['levels_add_up'] = check_level_totals(number, types)
    checks['global_total_vs_table_s8'] = check_global_total(number)
    rows = [[r[h] for h in HEADER] for r in records]
    A.write_csv('table_s10.csv', HEADER, rows)
    summary = dict(rows=layout['rows'], causes=checks['structure']['causes'], cells=len(rows))
    A.write_report('03_table_s10.json', __file__, summary, status='PASSED', layout=layout, checks=checks)
    print(f'[03] Complete; Table S10: {layout["rows"]:,} rows, {summary["causes"]} causes, {len(rows):,} cells; '
          f'{len(checks)} checks passed', flush=True)


if __name__ == '__main__':
    extract_table_s10()

"""Compare Tables S8 and S10 with the GBD 2021 downloads and reproduce IHME's infectious sepsis totals."""
import appendix_common as A

SPEC, S10 = A.CONFIG['gbd2021_comparison'], A.CONFIG['tables']['S10']
TOL, ABS, GLOBAL, INDIA = SPEC['tolerance'], SPEC['absolute_tolerance_deaths'], SPEC['global'], SPEC['india']
SETS = A.CAUSES['infectious_underlying_causes']
LEVELS = dict(zip(('level2', 'level3', 'level4'), SPEC['requests']))
BANDS = {**A.CAUSES['sepsis_age_bands'], S10['all_ages']: [SPEC['all_ages']]}


def check_infectious_set(s10, gbd):
    """Check that the infectious cause set in src/common is the infectious branch of Table S10."""
    kind = {(r['cause'], r['cause_level']): r['cause_type'] for r in s10}
    infectious = {c for (c, _), t in kind.items() if t == 'Infectious'}
    groups = {c for (c, l), t in kind.items() if t == 'Infectious' and l == '2'}
    gbd_groups = {c for _, _, c, _ in gbd[LEVELS['level2']]}
    added = set(SETS['level3']) | set(SETS['level4'])
    A.require(set(SETS['level2']) <= groups, f'Not infectious level 2 groups in Table S10: {sorted(set(SETS["level2"]) - groups)}')
    # Table S10 also prints infectious groups of its own, such as infectious maternal and neonatal diseases.
    A.require(not (groups - set(SETS['level2'])) & gbd_groups,
              f'Table S10 counts further GBD level 2 groups as infectious: {sorted((groups - set(SETS["level2"])) & gbd_groups)}')
    A.require(added <= infectious, f'Not infectious in Table S10: {sorted(added - infectious)}')
    excluded = set(SETS['listed_in_s3_but_not_in_ihme_totals'])
    A.require(not excluded & infectious, f'Infectious in Table S10: {sorted(excluded & infectious)}')
    children = set(SETS['level2_children_excluded'])
    A.require(children <= excluded and children <= {c for _, _, c, _ in gbd[LEVELS['level3']]},
              f'Excluded level 3 causes must be listed as excluded and present in the GBD 2021 level 3 download: {sorted(children)}')
    return dict(level2_groups=sorted(SETS['level2']), table_s10_only_groups=sorted(groups - set(SETS['level2'])),
                added_causes=sorted(added), level2_children_excluded=sorted(children), not_infectious=sorted(excluded))


def infectious_deaths(gbd, location, ages, year):
    """Return deaths from the infectious level 2 groups, less their excluded level 3 causes, plus the added causes."""
    get = lambda level, cause: sum(gbd[LEVELS[level]].get((location, a, cause, year), 0.0) for a in ages)
    return (sum(get(level, cause) for level in LEVELS for cause in SETS[level])
            - sum(get('level3', cause) for cause in SETS['level2_children_excluded']))


def compare(name, reproduced, ihme):
    """Check that a reproduced infectious total lies within the tolerance of IHME's."""
    ratio = reproduced / ihme
    A.require(abs(ratio - 1) <= TOL, f'{name}: infectious deaths {reproduced:,.0f} vs IHME {ihme:,.0f}')
    return dict(reproduced=round(reproduced), ihme=ihme, ratio=ratio)


def reproduce_totals(gbd, s8, s10):
    """Reproduce IHME's infectious totals: India's from Table S8 (all minus non-infectious causes), global by age from Table S10."""
    out = {}
    s8 = {(r['year'], r['cause_group']): float(r['val']) for r in s8 if r['location'] == INDIA and r['metric'] == 'Number'}
    for year in S10['cells']['year']:
        out[f'{INDIA} {year} {SPEC["all_ages"]}'] = compare(f'{INDIA} {year}', infectious_deaths(
            gbd, INDIA, [SPEC['all_ages']], year), s8[(year, 'All causes')] - s8[(year, 'Non-infectious causes')])
    total = S10['infectious_total']
    for r in s10:
        if (r['cause'], r['cause_level'], r['metric']) == (total['cause'], total['cause_level'], 'Number'):
            out[f'{GLOBAL} {r["year"]} {r["age_group"]}'] = compare(f'{GLOBAL} {r["year"]} {r["age_group"]}', infectious_deaths(
                gbd, GLOBAL, BANDS[r['age_group']], r['year']), float(r['val']))
    return out


def compare_causes(gbd, s10):
    """Check Table S10 level 3-4 causes against all their GBD 2021 deaths: equal when infectious, not larger otherwise."""
    deaths = {k: v for request in SPEC['requests'] for k, v in gbd[request].items() if k[0] == GLOBAL}
    names = {c for _, _, c, _ in deaths}
    aliases = SPEC['cause_name_aliases']
    printed, unmatched = set(), set()
    infectious_gap, largest_share, cells = 0.0, 0.0, 0
    for r in s10:
        if r['metric'] != 'Number' or r['cause_level'] not in SPEC['compared_levels']:
            continue
        cause = aliases.get(r['cause'], r['cause'])
        # Most level 4 causes and a few level 3 names (e.g. Electrocution) have no GBD 2021 download; they are counted, not compared.
        if cause not in names:
            unmatched.add((r['cause'], r['cause_level']))
            continue
        printed.add((cause, r['age_group'], r['year']))
        total = sum(deaths.get((GLOBAL, a, cause, r['year']), 0.0) for a in BANDS[r['age_group']])
        value, half, name = float(r['val']), A.half_unit(r['val']), f'{r["cause"]} {r["age_group"]} {r["year"]}'
        allowed = half + TOL * total + ABS
        if r['cause_type'] == 'Infectious':
            A.require(abs(value - total) <= allowed, f'{name}: Table S10 {value:,.0f}, GBD 2021 {total:,.1f}')
            infectious_gap = max(infectious_gap, abs(value - total) / allowed)
        else:
            A.require(value - total <= allowed, f'{name}: Table S10 {value:,.0f} exceeds GBD 2021 deaths {total:,.1f}')
            largest_share = max(largest_share, value / total if total else 0.0)
        cells += 1
    level3 = {c for _, _, c, _ in gbd[LEVELS['level3']]}
    return dict(cells=cells, infectious_largest_gap_over_allowed=infectious_gap, non_infectious_largest_share=largest_share,
                table_s10_causes_not_downloaded=len(unmatched),
                gbd_level3_causes_not_in_table_s10=sorted(level3 - {c for c, _, _ in printed}))


def compare_with_gbd2021():
    s8, s10 = A.read_csv('table_s8.csv'), A.read_csv('table_s10.csv')
    gbd = {request: A.gbd_deaths([request], {GLOBAL, INDIA}) for request in SPEC['requests']}
    checks = dict(infectious_set=check_infectious_set(s10, gbd), infectious_totals=reproduce_totals(gbd, s8, s10),
                  table_s10_causes=compare_causes(gbd, s10))
    ratios = [v['ratio'] for v in checks['infectious_totals'].values()]
    summary = dict(totals=len(ratios), ratio_min=min(ratios), ratio_max=max(ratios), cells=checks['table_s10_causes']['cells'])
    A.write_report('04_gbd2021_comparison.json', __file__, summary, status='PASSED', checks=checks)
    print(f'[04] Complete; {len(ratios)} infectious totals within {TOL:.1%} of IHME (ratios {min(ratios):.4f}-{max(ratios):.4f}); '
          f'{summary["cells"]:,} Table S10 cells consistent with GBD 2021 deaths', flush=True)


if __name__ == '__main__':
    compare_with_gbd2021()

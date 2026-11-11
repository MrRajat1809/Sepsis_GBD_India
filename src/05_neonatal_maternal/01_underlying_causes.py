"""Neonatal and maternal sepsis as underlying causes of death by state, sex and year, 1990-2023 (GBD 2023, with 95%
intervals): deaths, share of all neonatal or maternal disorder deaths, crude rate per 100,000 and age-standardised rate."""
from collections import defaultdict

import neonatal_maternal_common as N

HEADER = ['location', 'sex', 'year', 'cause', 'deaths', 'deaths_lower', 'deaths_upper', 'parent_deaths', 'share_of_parent',
          'population', 'crude_rate', 'age_standardised_rate', 'asr_lower', 'asr_upper']


def build_underlying():
    parents = {N.NEONATAL['cause']: N.NEONATAL['parent'], N.MATERNAL['cause']: N.MATERNAL['parent']}
    key = ('location_name', 'sex_name', 'cause_name', 'year')
    deaths = N.results(N.CONFIG['requests']['deaths_level4'], key, causes=set(parents), interval=True)
    rates = N.results(N.CONFIG['requests']['rates_level4'], key, causes=set(parents), metric='Rate', interval=True)
    parent = N.results(N.CONFIG['requests']['deaths_level3'], key, causes=set(parents.values()))
    population, _ = N.population()
    locations = sorted({k[0] for k in deaths})
    rows, sexes_of = [], {}
    for cause, parent_cause in parents.items():
        # GBD estimates maternal sepsis for women only, so it has no male rows.
        sexes_of[cause] = [s for s in N.CONFIG['sexes'] if any(k[1] == s and k[2] == cause for k in deaths)]
        for location in locations:
            for sex in sexes_of[cause]:
                for year in N.YEARS:
                    d, r = deaths[(location, sex, cause, year)], rates[(location, sex, cause, year)]
                    p, pop = parent[(location, sex, parent_cause, year)], population[(location, sex, year)]
                    rows.append([location, sex, year, cause, *d, p, d[0] / p, pop, d[0] / pop * 1e5, *r])
    N.write_csv('underlying_annual.csv', HEADER, rows)
    checks = check(rows, sexes_of)
    india = {f'{r[3].split()[0].lower()} {r[2]}': dict(deaths=[round(v) for v in r[4:7]], share_of_parent=round(r[8], 4),
                                                       age_standardised_rate=[round(v, 3) for v in r[11:14]])
             for r in rows if r[0] == N.INDIA and r[1] == 'Both' and r[2] in (1990, 2019, 2021, 2023)}
    summary = dict(locations=len(locations), years=f'{N.YEARS[0]}-{N.YEARS[-1]}', rows=len(rows),
                   sexes={c: s for c, s in sexes_of.items()})
    N.write_report('01_underlying_causes.json', __file__, summary, status='PASSED', checks=checks, india=india)
    n2023, m2023 = india[f'neonatal {N.YEARS[-1]}'], india[f'maternal {N.YEARS[-1]}']
    print(f'[01] Complete; {len(rows):,} rows; India {N.YEARS[-1]}: neonatal sepsis {n2023["deaths"][0]:,} deaths '
          f'({100 * n2023["share_of_parent"]:.1f}% of neonatal disorders), maternal sepsis {m2023["deaths"][0]:,} '
          f'({100 * m2023["share_of_parent"]:.1f}% of maternal disorders)', flush=True)


def check(rows, sexes_of):
    """Check intervals and shares, and that states add up to India and sexes to both sexes; return the check summary."""
    checks = {}
    outside = [r for r in rows if not (r[5] <= r[4] <= r[6] and r[12] <= r[11] <= r[13])]
    N.require(not outside, f'{len(outside)} values outside their uncertainty interval')
    N.require(all(0 <= r[8] <= 1 for r in rows), 'A level 4 cause exceeds its parent')
    states, india = defaultdict(float), {}
    for r in rows:
        if r[0] == N.INDIA:
            india[(r[1], r[2], r[3])] = r[4]
        else:
            states[(r[1], r[2], r[3])] += r[4]
    checks['states_to_india'] = N.ratio_range('States / India', [(states[k], v) for k, v in india.items() if v > 1], 1e-6)
    both = {(r[0], r[2], r[3]): r[4] for r in rows if r[1] == 'Both'}
    sexes = defaultdict(float)
    for r in rows:
        if r[1] != 'Both':
            sexes[(r[0], r[2], r[3])] += r[4]
    checks['sexes_to_both'] = N.ratio_range('Male + female (female only for maternal sepsis) / both sexes',
                                            [(v, both[k]) for k, v in sexes.items() if both[k] > 1], 1e-6)
    N.require('Male' not in sexes_of[N.MATERNAL['cause']], 'Maternal sepsis has male rows')
    checks['values_within_intervals'] = dict(n=len(rows), outside=0)
    return checks


if __name__ == '__main__':
    build_underlying()

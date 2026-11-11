"""All sepsis-related maternal deaths by state and year, 1990-2023, for women and both sexes: maternal sepsis as the
underlying cause plus the sepsis-related share of other maternal disorders, from state_estimates stage 05."""
from collections import defaultdict

import neonatal_maternal_common as N

HEADER = ['location', 'sex', 'year', 'maternal_sepsis', 'other_maternal_disorders', 'sepsis_related', 'maternal_deaths',
          'sepsis_related_share', 'population', 'sepsis_related_rate', 'projection']


def build_maternal():
    cause, parent = N.MATERNAL['cause'], N.MATERNAL['parent']
    sepsis, deaths = defaultdict(float), defaultdict(float)
    for r in N.read_csv('estimates_annual.csv', N.ESTIMATES):
        if r['cause'] in (cause, parent) and r['sex'] != 'Male':
            key = (r['location'], r['sex'], int(r['year']))
            sepsis[key + (r['cause'],)] += float(r['sepsis_deaths'])
            deaths[key] += float(r['deaths'])
    population, _ = N.population()
    rows = []
    for key in sorted(deaths):
        own, other = sepsis[key + (cause,)], sepsis[key + (parent,)]
        # Rates are per 100,000 population of the same sex; sepsis-related shares from 2022 on are projections.
        rows.append([*key, own, other, own + other, deaths[key], (own + other) / deaths[key] if deaths[key] else 0.0,
                     population[key], (own + other) / population[key] * 1e5, int(key[2] >= N.CONFIG['first_projection_year'])])
    reported = N.results(N.CONFIG['requests']['deaths_level3'], ('location_name', 'sex_name', 'cause_name', 'year'), causes={parent})
    checks = dict(maternal_deaths_to_gbd=N.ratio_range('Maternal deaths / GBD 2023 maternal disorders', [
        (r[6], reported[(r[0], r[1], parent, r[2])]) for r in rows], 1e-9))
    underlying = {(r['location'], r['sex'], int(r['year'])): float(r['deaths']) for r in N.read_csv('underlying_annual.csv')
                  if r['cause'] == cause}
    checks['maternal_sepsis_to_stage_01'] = N.ratio_range('Maternal sepsis / stage 01', [
        (r[3], underlying[(r[0], r[1], r[2])]) for r in rows if r[3] > 0], 1e-9)
    N.require(all(0 <= r[7] <= 1 for r in rows), 'Sepsis-related maternal deaths exceed maternal deaths')
    N.write_csv('maternal_annual.csv', HEADER, rows)
    india = {str(r[2]): dict(maternal_sepsis=round(r[3]), sepsis_related=round(r[5]), share_of_maternal_deaths=round(r[7], 3),
                             maternal_sepsis_part=round(r[3] / r[5], 3), projection=bool(r[10]))
             for r in rows if r[0] == N.INDIA and r[1] == 'Female' and r[2] in (1990, 2000, 2010, 2019, 2021, 2023)}
    N.write_report('03_maternal_sepsis_related.json', __file__, dict(rows=len(rows)), status='PASSED', checks=checks, india_women=india)
    last = india[str(N.YEARS[-1])]
    print(f'[03] Complete; {len(rows):,} rows; India {N.YEARS[-1]} (projected): {last["sepsis_related"]:,} sepsis-related maternal '
          f'deaths ({100 * last["share_of_maternal_deaths"]:.1f}% of maternal deaths), of which '
          f'{100 * last["maternal_sepsis_part"]:.0f}% maternal sepsis as underlying cause', flush=True)


if __name__ == '__main__':
    build_maternal()

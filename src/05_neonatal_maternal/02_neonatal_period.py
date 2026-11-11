"""All sepsis-related deaths in the first 28 days of life by state, in the GBD 2023 years with age detail, from the
estimates by age of state_estimates stage 04; rates are per 100,000 population of the same age."""
from collections import defaultdict

import neonatal_maternal_common as N

# Neonatal sepsis as underlying cause, the sepsis-related share of other neonatal disorders (such as preterm birth),
# other infectious causes (all sepsis-related) and the sepsis-related share of other non-infectious causes.
PARTS = ['neonatal_sepsis', 'other_neonatal_disorders', 'other_infectious', 'other_non_infectious']
HEADER = ['location', 'year', 'age_group', *PARTS, 'sepsis_related', 'all_deaths', 'sepsis_related_share', 'population',
          'sepsis_related_rate', 'neonatal_sepsis_rate', 'projection']


def part_of(row):
    """Return which of the four parts an estimate row belongs to."""
    if row['cause'] == N.NEONATAL['cause']:
        return 'neonatal_sepsis'
    if row['cause'] == N.NEONATAL['parent']:
        return 'other_neonatal_disorders'
    return 'other_infectious' if row['component'] == 'infectious' else 'other_non_infectious'


def build_neonatal_period():
    ages, period = N.CONFIG['neonatal_ages'], N.CONFIG['neonatal_period']
    sepsis, deaths = defaultdict(float), defaultdict(float)
    for r in N.read_csv('estimates_by_age.csv', N.ESTIMATES):
        if r['age_group'] in ages:
            # Each row counts towards its own age group and towards the 0-27 day total.
            for age in (r['age_group'], period):
                key = (r['location'], int(r['year']), age)
                sepsis[key + (part_of(r),)] += float(r['sepsis_deaths'])
                deaths[key] += float(r['deaths'])
    _, by_age = N.population()
    rows = []
    for location, year, age in sorted(deaths):
        pop = sum(by_age[(location, a, year)] for a in (ages if age == period else [age]))
        parts = [sepsis[(location, year, age, p)] for p in PARTS]
        total = sum(parts)
        # Sepsis-related shares from 2022 on are projections.
        rows.append([location, year, age, *parts, total, deaths[(location, year, age)], total / deaths[(location, year, age)],
                     pop, total / pop * 1e5, parts[0] / pop * 1e5, int(year >= N.CONFIG['first_projection_year'])])
    N.require(all(0 <= r[9] <= 1 for r in rows), 'Sepsis-related deaths exceed all deaths at a neonatal age')
    states, india = defaultdict(float), {}
    for r in rows:
        if r[0] == N.INDIA:
            india[(r[1], r[2])] = r[7]
        else:
            states[(r[1], r[2])] += r[7]
    checks = dict(states_to_india=N.ratio_range('States / India, sepsis-related neonatal deaths',
                                                [(states[k], v) for k, v in india.items()], 1e-6),
                  sepsis_related_within_all_deaths=len(rows))
    N.write_csv('neonatal_period.csv', HEADER, rows)
    report_rows = {r[1]: r for r in rows if r[0] == N.INDIA and r[2] == period}
    india_summary = {str(y): dict(sepsis_related=round(r[7]), neonatal_sepsis=round(r[3]),
                                  neonatal_sepsis_part=round(r[3] / r[7], 3), other_neonatal_disorders_part=round(r[4] / r[7], 3),
                                  other_infectious_part=round(r[5] / r[7], 3), share_of_neonatal_deaths=round(r[9], 3),
                                  rate_per_100000=round(r[11]), projection=bool(r[13])) for y, r in report_rows.items()}
    N.write_report('02_neonatal_period.json', __file__, dict(rows=len(rows), years=sorted(report_rows)), status='PASSED',
                   checks=checks, india_0_27_days=india_summary)
    last = india_summary[str(max(report_rows))]
    print(f'[02] Complete; {len(rows)} rows; India {max(report_rows)} (projected): {last["sepsis_related"]:,} sepsis-related '
          f'deaths in the first 28 days ({100 * last["share_of_neonatal_deaths"]:.1f}% of neonatal deaths), of which '
          f'{100 * last["neonatal_sepsis_part"]:.0f}% neonatal sepsis as underlying cause', flush=True)


if __name__ == '__main__':
    build_neonatal_period()

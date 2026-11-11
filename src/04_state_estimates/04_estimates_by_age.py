"""Estimate sepsis-related deaths and YLLs by state, age group and underlying cause in the GBD 2023 years with age detail."""
from collections import defaultdict

import estimates_common as E

HEADER = ['location', 'year', 'age_group', 'cause', 'component', 'deaths', 'ylls', 'sepsis_share', 'scaled_share',
          'sepsis_deaths', 'sepsis_ylls']
INDIA, DEATHS, YLLS = E.CONFIG['india'], E.CONFIG['deaths'], E.CONFIG['ylls']


def all_cause(measure, years):
    """Return all-cause, all-ages, both-sex values of one measure by location and year from the GBD 2023 all-cause download."""
    return {(r['location_name'], int(r['year'])): float(r['val']) for entry in E.request_files(['allcause'])
            for r in E.archive_rows(entry) if r['measure_name'] == measure and r['metric_name'] == 'Number'
            and r['age_name'] == E.CONFIG['all_ages'] and r['sex_name'] == 'Both' and int(r['year']) in years}


def build_estimates_by_age():
    causes = {c: r for c, r in E.cause_map('gbd2023').items() if r['component'] != E.NOT_USED}
    years = E.request_years(E.CONFIG['requests']['gbd2023_by_age'])
    values = E.results(E.CONFIG['requests']['gbd2023_by_age'], ('measure_name', 'location_name', 'age_name', 'cause_name', 'year'))
    locations = sorted({k[1] for k in values})
    table, factors = E.shares(), E.scaling_factors()
    rows = []
    for year in years:
        shares, k = E.shares_in(year, table), E.interpolate(factors, year)
        for location in locations:
            for age in E.AGES:
                for cause, row in sorted(causes.items()):
                    deaths = E.adjusted(values, cause, row['less'], lambda c: (DEATHS, location, age, c, year))
                    ylls = E.adjusted(values, cause, row['less'], lambda c: (YLLS, location, age, c, year))
                    # Every death from an infectious underlying cause counts as sepsis-related, as in IHME's totals.
                    if row['component'] == E.INFECTIOUS:
                        share = scaled = 1.0
                    elif row['component'] == E.NON_INFECTIOUS:
                        share = shares[(row['share_group'], E.BAND_OF[age])]
                        scaled = E.scaled_share(share, k)
                    else:
                        share = scaled = 0.0
                    rows.append([location, year, age, cause, row['component'], deaths, ylls, share, scaled,
                                 scaled * deaths, scaled * ylls])
    # The mapped causes, zero-share ones included, must account for all deaths and YLLs.
    checks = {}
    for column, measure in ((5, DEATHS), (6, YLLS)):
        totals = defaultdict(float)
        for r in rows:
            totals[(r[0], r[1])] += r[column]
        reference = all_cause(measure, years)
        checks[f'causes_to_all_cause_{column == 5 and "deaths" or "ylls"}'] = E.ratio_range(
            f'Mapped causes / all-cause {measure}', [(totals[k], reference[k]) for k in totals], E.TOL['identity'])
    E.require(all(0 <= r[8] <= 1 for r in rows), 'A scaled sepsis share lies outside 0-1')
    for column, name in ((9, 'sepsis_deaths'), (10, 'sepsis_ylls')):
        states, india = defaultdict(float), {}
        for r in rows:
            key = (r[1], r[2], r[3])
            if r[0] == INDIA:
                india[key] = r[column]
            else:
                states[key] += r[column]
        checks[f'states_to_india_{name}'] = E.ratio_range(f'States / India, {name}', [
            (states[k], v) for k, v in india.items() if v > 100], 1e-6)
    national = {}
    for year in years:
        part = [r for r in rows if r[0] == INDIA and r[1] == year]
        national[str(year)] = dict(
            infectious=round(sum(r[9] for r in part if r[4] == E.INFECTIOUS)),
            non_infectious=round(sum(r[9] for r in part if r[4] == E.NON_INFECTIOUS)),
            sepsis_deaths=round(sum(r[9] for r in part)), all_deaths=round(sum(r[5] for r in part)),
            sepsis_ylls=round(sum(r[10] for r in part)))
    E.write_csv('estimates_by_age.csv', HEADER, rows)
    summary = dict(locations=len(locations), years=years, causes=len(causes), rows=len(rows))
    E.write_report('04_estimates_by_age.json', __file__, summary, status='PASSED', checks=checks, india=national)
    print(f'[04] Complete; {len(rows):,} rows for {len(locations)} locations, {len(years)} years, 10 age groups and '
          f'{len(causes)} causes; India 2021: {national["2021"]["sepsis_deaths"]:,} sepsis-related deaths', flush=True)


if __name__ == '__main__':
    build_estimates_by_age()

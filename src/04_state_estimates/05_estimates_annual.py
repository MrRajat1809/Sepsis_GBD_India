"""Estimate sepsis-related deaths by state, sex, year and underlying cause, 1990-2023, from all-ages GBD 2023 deaths."""
from collections import defaultdict

import estimates_common as E

DETAIL = ['location', 'sex', 'year', 'cause', 'component', 'deaths', 'scaled_share', 'sepsis_deaths', 'projection']
SUMMARY = ['location', 'sex', 'year', 'deaths', 'infectious', 'non_infectious', 'sepsis_deaths', 'projection']
INDIA, DEATHS = E.CONFIG['india'], E.CONFIG['deaths']


def build_estimates_annual():
    causes = {c: r for c, r in E.cause_map('gbd2023').items() if r['component'] != E.NOT_USED}
    by_age = E.read_csv('estimates_by_age.csv')
    weights, fallback = E.count_spread(by_age, causes)
    age_years = sorted({int(r['year']) for r in by_age})
    E.require(age_years[0] <= E.YEARS[0] and age_years[-1] >= E.YEARS[-1], f'Age detail {age_years} does not span {E.YEARS}')
    needed = set(causes) | {c for r in causes.values() for c in filter(None, r['less'].split(';'))}
    deaths = E.results(E.CONFIG['requests']['gbd2023_annual'], ('location_name', 'sex_name', 'cause_name', 'year'),
                       measure=DEATHS, causes=needed)
    locations = sorted({k[0] for k in deaths})
    units = [l for l in locations if l != INDIA]
    table, factors = E.shares(), E.scaling_factors()
    detail, summary = [], []
    for year in E.YEARS:
        shares, k = E.shares_in(year, table), E.interpolate(factors, year)
        # Years after the last benchmark year hold its shares and k, and are flagged as projections.
        projection = int(year >= E.CONFIG['first_projection_year'])
        for sex in E.CONFIG['sexes']:
            national = defaultdict(lambda: [0.0, 0.0])
            for location in units:
                totals = defaultdict(float)
                for cause, row in sorted(causes.items()):
                    value = E.adjusted(deaths, cause, row['less'], lambda c: (location, sex, c, year))
                    if row['component'] == E.INFECTIOUS:
                        share = 1.0
                    elif row['component'] == E.NON_INFECTIOUS:
                        # All-ages share: the band shares weighted by how the cause's deaths in the state spread across
                        # bands, known in the years with age detail and interpolated between them.
                        w = E.spread_in(weights[(location, cause)], year)
                        share = sum(E.scaled_share(shares[(row['share_group'], b)], k) * w[b] for b in E.BANDS)
                    else:
                        share = 0.0
                    detail.append([location, sex, year, cause, row['component'], value, share, share * value, projection])
                    national[cause][0] += value
                    national[cause][1] += share * value
                    totals['deaths'] += value
                    totals[row['component']] += share * value
                summary.append([location, sex, year, totals['deaths'], totals[E.INFECTIOUS], totals[E.NON_INFECTIOUS],
                                totals[E.INFECTIOUS] + totals[E.NON_INFECTIOUS], projection])
            # India is the sum of its 31 subnational units, so the state figures always add up to the national one.
            totals = defaultdict(float)
            for cause, row in sorted(causes.items()):
                value, sepsis = national[cause]
                reported = E.adjusted(deaths, cause, row['less'], lambda c: (INDIA, sex, c, year))
                E.require(abs(value - reported) <= 1e-6 * max(reported, 1.0), f'{cause} {sex} {year}: units do not add up to India')
                detail.append([INDIA, sex, year, cause, row['component'], value, sepsis / value if value else 0.0, sepsis, projection])
                totals['deaths'] += value
                totals[row['component']] += sepsis
            summary.append([INDIA, sex, year, totals['deaths'], totals[E.INFECTIOUS], totals[E.NON_INFECTIOUS],
                            totals[E.INFECTIOUS] + totals[E.NON_INFECTIOUS], projection])
    checks = check(detail, summary, by_age, age_years)
    E.write_csv('estimates_annual.csv', DETAIL, detail)
    E.write_csv('sepsis_deaths_annual.csv', SUMMARY, summary)
    india = {str(r[2]): round(r[6]) for r in summary if r[0] == INDIA and r[1] == 'Both'}
    report = dict(locations=len(locations), years=f'{E.YEARS[0]}-{E.YEARS[-1]}', causes=len(causes), rows=len(detail))
    E.write_report('05_estimates_annual.json', __file__, report, status='PASSED', checks=checks,
                   age_spread_from_india=[list(f) for f in fallback], india_sepsis_deaths=india)
    print(f'[05] Complete; {len(detail):,} rows for {len(locations)} locations, 3 sexes and {len(E.YEARS)} years; '
          f'India {E.YEARS[-1]} (projected): {india[str(E.YEARS[-1])]:,} sepsis-related deaths', flush=True)


def check(detail, summary, by_age, age_years):
    """Check the shares, and the totals against all-cause deaths, the estimates by age and the sum of the sexes."""
    checks = {}
    outside = [r for r in detail if not 0 <= r[6] <= 1 + 1e-12]
    E.require(not outside, f'{len(outside)} all-ages shares lie outside 0-1, e.g. {outside[:2]}')
    allcause = {(r['location_name'], r['sex_name'], int(r['year'])): float(r['val']) for entry in E.request_files(['allcause'])
                for r in E.archive_rows(entry) if r['measure_name'] == DEATHS and r['metric_name'] == 'Number'
                and r['age_name'] == E.CONFIG['all_ages']}
    checks['causes_to_all_cause_deaths'] = E.ratio_range('Mapped causes / all-cause deaths', [
        (r[3], allcause[(r[0], r[1], r[2])]) for r in summary], E.TOL['identity'])
    # In years with age detail the band weights come from the by-age deaths, so the two stages must agree.
    by_age_total = defaultdict(float)
    for r in by_age:
        by_age_total[(r['location'], int(r['year']), r['cause'])] += float(r['sepsis_deaths'])
    checks['equals_by_age_estimates'] = E.ratio_range('Annual / by-age estimates in years with age detail', [
        (r[7], by_age_total[(r[0], r[2], r[3])]) for r in detail
        if r[1] == 'Both' and r[2] in age_years and by_age_total[(r[0], r[2], r[3])] > 1], 1e-9)
    both = {(r[0], r[2]): r[6] for r in summary if r[1] == 'Both'}
    sexes = defaultdict(float)
    for r in summary:
        if r[1] != 'Both':
            sexes[(r[0], r[2])] += r[6]
    checks['male_plus_female_to_both'] = E.ratio_range('Male + female / both sexes', [
        (v, both[k]) for k, v in sexes.items()], 1e-6)
    return checks


if __name__ == '__main__':
    build_estimates_annual()

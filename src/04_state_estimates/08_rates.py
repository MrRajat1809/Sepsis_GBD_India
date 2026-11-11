"""Crude, age-specific and age-standardised sepsis-related death rates by state, sex and year, and by underlying cause."""
import statistics
from collections import defaultdict

import estimates_common as E

ANNUAL = ['location', 'sex', 'year', 'population', 'sepsis_deaths', 'crude_rate', 'age_standardised_rate',
          'asr_infectious', 'asr_non_infectious', 'all_cause_asr', 'projection']
BY_AGE = ['location', 'year', 'age_group', 'population', 'sepsis_deaths', 'rate']
BY_CAUSE = ['location', 'year', 'cause', 'component', 'cause_asr', 'sepsis_share', 'sepsis_asr', 'projection']
INDIA, DEATHS = E.CONFIG['india'], E.CONFIG['deaths']


def all_cause(metric, age):
    """Return GBD 2023 all-cause deaths in one metric and age group, by location, sex and year."""
    return {(r['location_name'], r['sex_name'], int(r['year'])): float(r['val'])
            for entry in E.request_files(E.CONFIG['requests']['gbd2023_all_cause']) for r in E.archive_rows(entry)
            if r['measure_name'] == DEATHS and r['metric_name'] == metric and r['age_name'] == age}


def build_rates():
    causes = {c: r for c, r in E.cause_map('gbd2023').items() if r['component'] != E.NOT_USED}
    weights, population = E.standard_weights(), E.population_by_age()
    by_age = E.read_csv('estimates_by_age.csv')
    sepsis_by_age = defaultdict(float)
    for r in by_age:
        sepsis_by_age[(r['location'], int(r['year']), r['age_group'])] += float(r['sepsis_deaths'])
    spread, fallback = E.standardised_spread(by_age, causes, weights, population)
    age_rows = [[l, y, a, population[(l, a, y)], v, v / population[(l, a, y)] * 1e5] for (l, y, a), v in sorted(sepsis_by_age.items())]

    level3 = {c for c, r in causes.items() if r['cause_level'] == '3'}
    moved = {c for c, r in causes.items() if r['cause_level'] == '4'}
    # Built on IHME's own age-standardised death rate for each cause, which uses IHME's fine age groups.
    asr_requests = E.CONFIG['requests']['gbd2023_age_standardised']
    asr_key = ('location_name', 'sex_name', 'cause_name', 'year')
    asr = {**E.results(asr_requests[:1], asr_key, measure=DEATHS, causes=level3, metric='Rate'),
           **E.results(asr_requests[1:], asr_key, measure=DEATHS, causes=moved, metric='Rate')}
    all_cause_asr = all_cause('Rate', E.CONFIG['age_standardised'])
    crude_rate = all_cause('Rate', E.CONFIG['all_ages'])
    # Population by sex: all-cause deaths divided by the all-cause crude death rate.
    pop_sex = {k: v / crude_rate[k] * 1e5 for k, v in all_cause('Number', E.CONFIG['all_ages']).items()}
    sepsis = {(r['location'], r['sex'], int(r['year'])): float(r['sepsis_deaths']) for r in E.read_csv('sepsis_deaths_annual.csv')}
    locations = sorted({k[0] for k in sepsis})
    table, factors = E.shares(), E.scaling_factors()
    rows, cause_rows, cause_totals, shares_seen = [], [], {}, []
    for year in E.YEARS:
        shares, k = E.shares_in(year, table), E.interpolate(factors, year)
        for location in locations:
            for sex in E.CONFIG['sexes']:
                parts, total = defaultdict(float), 0.0
                for cause, row in causes.items():
                    value = E.adjusted(asr, cause, row['less'], lambda c: (location, sex, c, year))
                    total += value
                    share = 0.0
                    if row['component'] == E.INFECTIOUS:
                        share = 1.0
                        parts[E.INFECTIOUS] += value
                    elif row['component'] == E.NON_INFECTIOUS:
                        # Band shares weighted by each band's part of the cause's standardised rate (ten groups, GBD
                        # standard); only this share depends on the broad age groups.
                        w = E.spread_in(spread[(location, cause)], year)
                        share = sum(E.scaled_share(shares[(row['share_group'], b)], k) * w[b] for b in E.BANDS)
                        shares_seen.append(share)
                        parts[E.NON_INFECTIOUS] += share * value
                    # By cause for both sexes, so that each state's rate for a cause can be compared with India's.
                    if sex == 'Both':
                        cause_rows.append([location, year, cause, row['component'], value, share, share * value,
                                           int(year >= E.CONFIG['first_projection_year'])])
                cause_totals[(location, sex, year)] = total
                pop, deaths = pop_sex[(location, sex, year)], sepsis[(location, sex, year)]
                rows.append([location, sex, year, pop, deaths, deaths / pop * 1e5, parts[E.INFECTIOUS] + parts[E.NON_INFECTIOUS],
                             parts[E.INFECTIOUS], parts[E.NON_INFECTIOUS], all_cause_asr[(location, sex, year)],
                             int(year >= E.CONFIG['first_projection_year'])])
    checks = dict(
        causes_to_all_cause_asr=E.ratio_range('Mapped cause rates / all-cause age-standardised rate', [
            (cause_totals[k], all_cause_asr[k]) for k in cause_totals], 1e-9),
        standardised_shares_within_one=dict(n=len(shares_seen), min=min(shares_seen), max=max(shares_seen)))
    E.require(0 <= checks['standardised_shares_within_one']['min'] and checks['standardised_shares_within_one']['max'] <= 1 + 1e-12,
              'An age-standardised sepsis share lies outside 0-1')
    E.require(all(r[6] <= r[9] for r in rows), 'A sepsis-related rate exceeds the all-cause rate')
    by_cause_total = defaultdict(float)
    for r in cause_rows:
        by_cause_total[(r[0], r[1])] += r[6]
    checks['causes_to_sepsis_asr'] = E.ratio_range('Cause sepsis-related rates / age-standardised rate', [
        (by_cause_total[(r[0], r[2])], r[6]) for r in rows if r[1] == 'Both'], 1e-9)
    checks['broad_age_groups_vs_ihme'] = broad_group_check(weights, population, sepsis_by_age, rows)
    E.write_csv('rates_annual.csv', ANNUAL, rows)
    E.write_csv('rates_by_age.csv', BY_AGE, age_rows)
    E.write_csv('rates_by_cause.csv', BY_CAUSE, cause_rows)
    india = {str(r[2]): dict(crude=round(r[5], 1), age_standardised=round(r[6], 1)) for r in rows
             if r[0] == INDIA and r[1] == 'Both' and r[2] in (1990, 2000, 2010, 2019, 2021, 2023)}
    summary = dict(locations=len(locations), years=f'{E.YEARS[0]}-{E.YEARS[-1]}', rows=len(rows), age_rows=len(age_rows),
                   cause_rows=len(cause_rows))
    E.write_report('08_rates.json', __file__, summary, status='PASSED', checks=checks, india_per_100000=india,
                   standard_weights=weights, spread_from_india=[list(f) for f in fallback])
    print(f'[08] Complete; rates for {len(locations)} locations, 3 sexes and {len(E.YEARS)} years; India age-standardised '
          f'{india["1990"]["age_standardised"]} (1990), {india["2019"]["age_standardised"]} (2019), '
          f'{india["2023"]["age_standardised"]} (2023, projected) per 100,000', flush=True)


def broad_group_check(weights, population, sepsis_by_age, rows):
    """Return the ratios of age-standardised rates worked out directly from the ten groups to IHME's (all causes) and ours (sepsis)."""
    requests = E.CONFIG['requests']['gbd2023_population_by_age']
    rate = E.results(requests, ('location_name', 'age_name', 'year'), measure=DEATHS, metric='Rate')
    ours = {(r[0], r[2]): (r[6], r[9]) for r in rows if r[1] == 'Both'}
    all_cause_ratio, sepsis_ratio = [], []
    for (location, year), (sepsis_asr, ihme_asr) in ours.items():
        all_cause_ratio.append(sum(weights[a] * rate[(location, a, year)] for a in E.AGES) / ihme_asr)
        if (location, year, E.AGES[0]) in sepsis_by_age:
            direct = sum(weights[a] * sepsis_by_age[(location, year, a)] / population[(location, a, year)] * 1e5 for a in E.AGES)
            sepsis_ratio.append(direct / sepsis_asr)
    return dict(all_cause_direct_over_ihme=dict(n=len(all_cause_ratio), min=min(all_cause_ratio), median=statistics.median(all_cause_ratio),
                                                max=max(all_cause_ratio)),
                sepsis_direct_over_method=dict(n=len(sepsis_ratio), min=min(sepsis_ratio), median=statistics.median(sepsis_ratio),
                                               max=max(sepsis_ratio)))


if __name__ == '__main__':
    build_rates()

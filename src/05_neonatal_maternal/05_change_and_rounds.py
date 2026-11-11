"""Change since 1990 in every neonatal and maternal sepsis measure, including those per live birth, and GBD 2023 against
GBD 2021 for the same years."""
from collections import defaultdict

import neonatal_maternal_common as N

CHANGE = ['location', 'sex', 'measure', 'start', 'end', 'value_start', 'value_end', 'change', 'percent_change']
ROUNDS = ['location', 'measure', 'year', 'gbd2021', 'gbd2023', 'ratio']


def series():
    """Return {(location, sex, measure): {year: value}} for every neonatal and maternal measure."""
    out = defaultdict(dict)
    short = {N.NEONATAL['cause']: 'neonatal_sepsis', N.MATERNAL['cause']: 'maternal_sepsis'}
    for r in N.read_csv('underlying_annual.csv'):
        for column, suffix in (('deaths', 'deaths'), ('age_standardised_rate', 'asr'), ('share_of_parent', 'share_of_parent')):
            out[(r['location'], r['sex'], f'{short[r["cause"]]}_{suffix}')][int(r['year'])] = float(r[column])
    for r in N.read_csv('neonatal_period.csv'):
        if r['age_group'] == N.CONFIG['neonatal_period']:
            for column in ('sepsis_related', 'sepsis_related_rate', 'sepsis_related_share'):
                out[(r['location'], 'Both', f'neonatal_period_{column}')][int(r['year'])] = float(r[column])
    for r in N.read_csv('maternal_annual.csv'):
        for column in ('sepsis_related', 'sepsis_related_rate', 'sepsis_related_share'):
            out[(r['location'], r['sex'], f'maternal_{column}')][int(r['year'])] = float(r[column])
    for r in N.read_csv('rates_per_birth.csv'):
        for column in ('neonatal_sepsis_per_1000', 'neonatal_period_sepsis_related_per_1000', 'maternal_sepsis_per_100000',
                       'maternal_sepsis_related_per_100000'):
            if r[column] != '':
                sex = 'Female' if column.startswith('maternal') else 'Both'
                out[(r['location'], sex, f'{column}_live_births')][int(r['year'])] = float(r[column])
    return out


def round_comparison():
    """Return GBD 2021 against GBD 2023 for neonatal and maternal sepsis deaths (level 4) and sepsis-related deaths at 0-27 days."""
    key = ('location_name', 'age_name', 'cause_name', 'year')
    gbd2021 = N.results(N.CONFIG['requests']['gbd2021_level4'], key, causes={N.NEONATAL['cause'], N.MATERNAL['cause']},
                        ages={N.CONFIG['all_ages']})
    gbd2023 = {(r['location'], r['cause'], int(r['year'])): float(r['deaths']) for r in N.read_csv('underlying_annual.csv')
               if r['sex'] == 'Both'}
    short = {N.NEONATAL['cause']: 'neonatal_sepsis_deaths', N.MATERNAL['cause']: 'maternal_sepsis_deaths'}
    # The GBD 2021 level 4 download also holds Global, which is not compared.
    rows = [[l, short[c], y, v, gbd2023[(l, c, y)], gbd2023[(l, c, y)] / v if v else '']
            for (l, a, c, y), v in sorted(gbd2021.items()) if l != 'Global']
    period = defaultdict(lambda: [0.0, 0.0])
    # The GBD 2021-round sepsis-related estimates of state_estimates stage 03.
    for r in N.read_csv('gbd2021_benchmark.csv', N.ESTIMATES):
        if r['age_group'] in N.CONFIG['neonatal_ages']:
            period[(r['location'], int(r['year']))][0] += float(r['sepsis_deaths'])
    for r in N.read_csv('neonatal_period.csv'):
        if r['age_group'] == N.CONFIG['neonatal_period'] and (r['location'], int(r['year'])) in period:
            period[(r['location'], int(r['year']))][1] = float(r['sepsis_related'])
    rows += [[l, 'neonatal_period_sepsis_related', y, a, b, b / a] for (l, y), (a, b) in sorted(period.items())]
    N.require(all(r[3] > 0 and r[4] > 0 for r in rows), 'A round comparison value is missing')
    return rows


def build_change_and_rounds():
    data = series()
    rows = []
    for (location, sex, measure), points in sorted(data.items()):
        for start, end in N.CONFIG['change_periods']:
            if start in points and end in points:
                a, b = points[start], points[end]
                # Shares are proportions, so their change is a difference of proportions, not of percentages.
                rows.append([location, sex, measure, start, end, a, b, b - a, N.percent_change(a, b)])
    N.write_csv('change_since_1990.csv', CHANGE, rows)
    rounds = round_comparison()
    N.write_csv('round_comparison.csv', ROUNDS, rounds)
    last = N.CONFIG['change_periods'][-1]
    # India: both sexes for the neonatal measures, women for the maternal ones.
    india = {r[2]: dict(start=round(r[5], 3), end=round(r[6], 3), percent_change=round(r[8], 1)) for r in rows
             if r[0] == N.INDIA and r[1] in ('Both', 'Female') and (r[3], r[4]) == tuple(last)
             and (r[1] == 'Both') != r[2].startswith('maternal')}
    by_measure = defaultdict(list)
    for r in rounds:
        by_measure[(r[1], r[2])].append(r)
    round_summary = {f'{m} {y}': dict(india=next(r[5] for r in part if r[0] == N.INDIA),
                                      states_min=min(r[5] for r in part if r[0] != N.INDIA),
                                      states_max=max(r[5] for r in part if r[0] != N.INDIA))
                     for (m, y), part in sorted(by_measure.items())}
    N.write_report('05_change_and_rounds.json', __file__, dict(change_rows=len(rows), round_rows=len(rounds)), status='PASSED',
                   india_change=india, gbd2023_over_gbd2021=round_summary)
    print(f'[05] Complete; {len(rows):,} changes and {len(rounds)} round comparisons; India {last[0]}-{last[1]}: neonatal sepsis '
          f'deaths {india["neonatal_sepsis_deaths"]["percent_change"]:+.1f}%, maternal sepsis deaths '
          f'{india["maternal_sepsis_deaths"]["percent_change"]:+.1f}%', flush=True)


if __name__ == '__main__':
    build_change_and_rounds()

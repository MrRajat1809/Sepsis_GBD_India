"""Divide the change in sepsis-related deaths in each state into population growth, ageing and rate change (Das Gupta 1993),
and the rate change by underlying cause into the change in each cause's death rate and in its scaled sepsis share."""
from collections import defaultdict

import estimates_common as E

SUMMARY = ['location', 'start', 'end', 'deaths_start', 'deaths_end', 'change', 'population_growth', 'age_structure',
           'rate_change', 'rate_infectious', 'rate_non_infectious', 'rate_from_cause_mortality', 'rate_from_sepsis_shares']
BY_CAUSE = ['location', 'start', 'end', 'cause', 'component', 'rate_change', 'from_cause_mortality', 'from_sepsis_shares']


def weights(p1, p2, s1, s2, r1, r2):
    """Return Das Gupta's three-factor weights for the effects of P, s and r on the product P * s * r."""
    return ((s1 * r1 + s2 * r2) / 3 + (s1 * r2 + s2 * r1) / 6,
            (p1 * r1 + p2 * r2) / 3 + (p1 * r2 + p2 * r1) / 6,
            (p1 * s1 + p2 * s2) / 3 + (p1 * s2 + p2 * s1) / 6)


def decompose(location, start, end, population, by_age):
    """Return the summary row and the rows by cause that divide one location's change in deaths between two years."""
    # Deaths D = P * sum_a s_a * r_a: population P, share s_a of the population in age group a, sepsis-related death rate r_a.
    P = {y: sum(population[(location, a, y)] for a in E.AGES) for y in (start, end)}
    share = {(a, y): population[(location, a, y)] / P[y] for a in E.AGES for y in (start, end)}
    effects, causes = defaultdict(float), defaultdict(lambda: [0.0, 0.0])
    for age in E.AGES:
        pop = {y: population[(location, age, y)] for y in (start, end)}
        rows = {y: by_age[(location, y, age)] for y in (start, end)}
        rate = {y: sum(r['sepsis'] for r in rows[y].values()) / pop[y] for y in (start, end)}
        w_pop, w_age, w_rate = weights(P[start], P[end], share[(age, start)], share[(age, end)], rate[start], rate[end])
        effects['population_growth'] += w_pop * (P[end] - P[start])
        effects['age_structure'] += w_age * (share[(age, end)] - share[(age, start)])
        for cause in rows[start]:
            # Two-factor form of the same method for each cause's rate r = m * q: death rate m and scaled sepsis share q.
            a, b = rows[start][cause], rows[end][cause]
            m1, m2 = a['deaths'] / pop[start], b['deaths'] / pop[end]
            causes[(cause, a['component'])][0] += w_rate * (b['share'] + a['share']) / 2 * (m2 - m1)
            causes[(cause, a['component'])][1] += w_rate * (m1 + m2) / 2 * (b['share'] - a['share'])
    deaths = {y: sum(r['sepsis'] for a in E.AGES for r in by_age[(location, y, a)].values()) for y in (start, end)}
    effects['rate_change'] = sum(m + q for m, q in causes.values())
    total = effects['population_growth'] + effects['age_structure'] + effects['rate_change']
    E.require(abs(total - (deaths[end] - deaths[start])) <= 1e-6 * max(deaths.values()),
              f'{location} {start}-{end}: effects add up to {total:,.1f}, change is {deaths[end] - deaths[start]:,.1f}')
    summary = [location, start, end, deaths[start], deaths[end], deaths[end] - deaths[start], effects['population_growth'],
               effects['age_structure'], effects['rate_change'],
               sum(m + q for (c, k), (m, q) in causes.items() if k == E.INFECTIOUS),
               sum(m + q for (c, k), (m, q) in causes.items() if k == E.NON_INFECTIOUS),
               sum(m for m, q in causes.values()), sum(q for m, q in causes.values())]
    detail = [[location, start, end, c, k, m + q, m, q] for (c, k), (m, q) in sorted(causes.items())]
    return summary, detail


def build_decomposition():
    population = E.population_by_age()
    by_age = defaultdict(dict)
    for r in E.read_csv('estimates_by_age.csv'):
        by_age[(r['location'], int(r['year']), r['age_group'])][r['cause']] = dict(
            component=r['component'], deaths=float(r['deaths']), share=float(r['scaled_share']), sepsis=float(r['sepsis_deaths']))
    locations = sorted({k[0] for k in by_age})
    summary, detail = [], []
    for start, end in E.CONFIG['decomposition_periods']:
        E.require(all((l, start, a) in by_age and (l, end, a) in by_age for l in locations for a in E.AGES),
                  f'{start}-{end}: estimates by age are needed in both years')
        for location in locations:
            s, d = decompose(location, start, end, population, by_age)
            summary.append(s)
            detail.extend(d)
    E.write_csv('decomposition.csv', SUMMARY, summary)
    E.write_csv('decomposition_by_cause.csv', BY_CAUSE, detail)
    india = {}
    for r in summary:
        if r[0] == E.CONFIG['india']:
            leading = sorted((d for d in detail if d[0] == r[0] and d[1] == r[1] and d[2] == r[2]), key=lambda d: d[5])
            india[f'{r[1]}-{r[2]}'] = dict(
                **{h: round(v) for h, v in zip(SUMMARY[3:], r[3:])},
                percent_of_start={h: round(100 * v / r[3], 1) for h, v in zip(SUMMARY[5:], r[5:])},
                largest_falls={d[3]: round(d[5]) for d in leading[:5]}, largest_rises={d[3]: round(d[5]) for d in leading[::-1][:5]})
    report = dict(locations=len(locations), periods=E.CONFIG['decomposition_periods'], rows=len(summary), cause_rows=len(detail),
                  projected_end_years=[e for _, e in E.CONFIG['decomposition_periods'] if e >= E.CONFIG['first_projection_year']])
    E.write_report('07_decomposition.json', __file__, report, status='PASSED', checks=dict(effects_add_up_to_change=len(summary)),
                   india=india)
    first = india[f'{E.CONFIG["decomposition_periods"][-1][0]}-{E.CONFIG["decomposition_periods"][-1][1]}']
    print(f'[07] Complete; {len(summary)} decompositions; India {E.CONFIG["decomposition_periods"][-1][0]}-'
          f'{E.CONFIG["decomposition_periods"][-1][1]}: population {first["percent_of_start"]["population_growth"]:+.1f}%, '
          f'ageing {first["percent_of_start"]["age_structure"]:+.1f}%, rates {first["percent_of_start"]["rate_change"]:+.1f}% '
          f'of {first["deaths_start"]:,} deaths', flush=True)


if __name__ == '__main__':
    build_decomposition()

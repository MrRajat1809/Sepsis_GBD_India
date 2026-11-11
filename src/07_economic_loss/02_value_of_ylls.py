"""Income-based value of the years of life lost (YLLs) to sepsis-related deaths by state, in the years with age detail
within the 2011-12 base series of state product: discounted YLLs times per-capita NSDP of the year of death, at current
and constant prices, in rupees crore, without income growth, treatment costs or the value of health beyond income."""
import math
from collections import defaultdict

import economic_common as C

# No share of state output is given: with per-capita income as the value of a life-year it would equal the YLLs per
# person, an epidemiological measure rather than an economic one.
HEADER = ['unit', 'year', 'sepsis_ylls', 'sepsis_ylls_infectious', 'sepsis_ylls_non_infectious', 'all_ylls', 'sepsis_share_of_ylls',
          'population', 'sepsis_ylls_per_100000', 'discount_rate', 'sepsis_ylls_discounted', 'per_capita_nsdp_current', 'value_current_crore',
          'value_current_crore_undiscounted', 'per_capita_nsdp_constant', 'value_constant_crore', 'nsdp_current_crore',
          'income_coverage', 'projection']


def discounted(deaths, ylls, rate):
    """Return the discounted YLLs of deaths that each lose L = ylls / deaths years, lost evenly over time."""
    if deaths <= 0:
        return 0.0
    # L years lost evenly are worth (1 - (1 + r)^-L) / ln(1 + r) discounted years; applied to the mean L of a broad age
    # group, this slightly overstates the discounted value.
    return deaths * (1 - (1 + rate) ** -(ylls / deaths)) / math.log(1 + rate)


def build_value():
    years, rate = C.CONFIG['valuation_years'], C.CONFIG['discount_rate']
    ylls = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0, 0.0])
    # Sepsis-related YLLs of state_estimates stage 04: infectious causes in full, others times the scaled shares.
    for r in C.read_csv('estimates_by_age.csv', C.ESTIMATES):
        year = int(r['year'])
        if year in years:
            part = ylls[(r['location'], year)]
            part[0] += float(r['sepsis_ylls'])
            part[1 if r['component'] == 'infectious' else 2] += float(r['sepsis_ylls']) if r['component'] != 'zero_share' else 0.0
            part[3] += float(r['ylls'])
            part[4] += discounted(float(r['sepsis_deaths']), float(r['sepsis_ylls']), rate)
    C.require(all(abs(v[0] - v[1] - v[2]) <= 1e-6 * max(v[0], 1) for v in ylls.values()), 'YLL components do not add up')
    C.require(all(0 < v[4] < v[0] for v in ylls.values()), 'Discounted YLLs are not below undiscounted YLLs')
    population = {(r['location'], int(r['year'])): float(r['population']) for r in C.read_csv('rates_annual.csv', C.ESTIMATES)
                  if r['sex'] == 'Both'}
    income = {(r['unit'], int(r['year']), r['prices']): r for r in C.read_csv('income_by_unit.csv')}
    crore = C.CONFIG['rupees_per_crore']
    rows, totals = [], defaultdict(lambda: defaultdict(float))
    units = sorted({k[0] for k in ylls} - {C.INDIA})
    for year in years:
        for unit in units:
            s, inf, non, total, disc = ylls[(unit, year)]
            cur, con = income.get((unit, year, 'current')), income.get((unit, year, 'constant'))
            C.require(cur is not None, f'No state domestic product for {unit} {year}')
            value = disc * float(cur['per_capita_nsdp']) / crore
            undiscounted = s * float(cur['per_capita_nsdp']) / crore
            real = disc * float(con['per_capita_nsdp']) / crore if con else ''
            pop = population[(unit, year)]
            # Estimates from 2022 on rest on projected sepsis-related shares.
            rows.append([unit, year, s, inf, non, total, s / total, pop, s / pop * 1e5, rate, disc, float(cur['per_capita_nsdp']), value,
                         undiscounted, float(con['per_capita_nsdp']) if con else '', real, float(cur['nsdp_crore']),
                         cur['income_coverage'], int(year >= C.CONFIG['first_projection_year'])])
            t = totals[year]
            for key, v in (('s', s), ('inf', inf), ('non', non), ('total', total), ('pop', pop), ('disc', disc), ('value', value),
                           ('undiscounted', undiscounted), ('real', real or 0.0), ('nsdp', float(cur['nsdp_crore']))):
                t[key] += v
        t = totals[year]
        india_ylls = ylls[(C.INDIA, year)][0]
        C.require(abs(t['s'] / india_ylls - 1) <= 1e-6, f'{year}: units do not add up to India YLLs')
        # India is the sum of the units; its per-capita product is their average weighted by discounted YLLs.
        rows.append([C.INDIA, year, t['s'], t['inf'], t['non'], t['total'], t['s'] / t['total'], t['pop'], t['s'] / t['pop'] * 1e5,
                     rate, t['disc'], t['value'] * crore / t['disc'], t['value'], t['undiscounted'], t['real'] * crore / t['disc'],
                     t['real'], t['nsdp'], 'sum of the units', int(year >= C.CONFIG['first_projection_year'])])
    C.write_csv('value_of_ylls.csv', HEADER, rows)
    india = {str(r[1]): dict(sepsis_ylls=round(r[2]), share_of_all_ylls=round(r[6], 3), ylls_per_100000=round(r[8]),
                             sepsis_ylls_discounted=round(r[10]), value_current_crore=round(r[12]),
                             value_current_crore_undiscounted=round(r[13]), value_constant_crore=round(r[15]),
                             discounted_over_undiscounted=round(r[12] / r[13], 3), projection=bool(r[18]))
             for r in rows if r[0] == C.INDIA}
    per_100000 = {y: sorted((r[8], r[0]) for r in rows if r[1] == y and r[0] != C.INDIA) for y in years}
    summary = dict(rows=len(rows), years=years, discount_rate=rate)
    C.write_report('02_value_of_ylls.json', __file__, summary, status='PASSED', india=india,
                   ylls_per_100000={str(y): dict(lowest=s[:3], highest=s[-3:]) for y, s in per_100000.items()})
    i = india[str(years[1])]
    print(f'[02] Complete; India {years[1]}: {i["sepsis_ylls"]:,} sepsis-related YLLs worth Rs {i["value_current_crore"]:,} crore '
          f'at current prices, discounted at {100 * rate:g}% (Rs {i["value_current_crore_undiscounted"]:,} crore undiscounted)', flush=True)


if __name__ == '__main__':
    build_value()

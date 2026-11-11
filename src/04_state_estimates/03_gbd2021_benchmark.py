"""Solve the scaling factor k that brings India's non-infectious sepsis-related deaths to Table S8 in each benchmark year,
and estimate sepsis-related deaths by state in the GBD 2021 round, on which IHME's totals rest."""
from collections import defaultdict

import estimates_common as E

HEADER = ['location', 'age_group', 'year', 'infectious', 'non_infectious_unscaled', 'non_infectious', 'sepsis_deaths']
INDIA = E.CONFIG['india']


def components(deaths, causes, shares, location, age, year):
    """Return infectious deaths, and (share, deaths) of each non-infectious cause, for one location, age group and year."""
    infectious, pairs = 0.0, []
    for cause, row in causes.items():
        value = E.adjusted(deaths, cause, row['less'], lambda c: (location, age, c, year))
        if row['component'] == E.INFECTIOUS:
            infectious += value
        elif row['component'] == E.NON_INFECTIOUS:
            pairs.append((shares[(row['share_group'], E.BAND_OF[age], year)], value))
    return infectious, pairs


def scaled(pairs, k):
    """Return the non-infectious sepsis-related deaths with every share scaled by k and capped at 1."""
    return sum(E.scaled_share(share, k) * deaths for share, deaths in pairs)


def solve_k(pairs, target):
    """Return k such that the non-infectious deaths, with every scaled share capped at 1, equal the target."""
    low, high = 0.0, 10.0
    E.require(scaled(pairs, high) > target, 'Target cannot be reached with shares capped at 1')
    # The capped total never falls as k grows, so bisection converges on the target.
    for _ in range(200):
        middle = (low + high) / 2
        low, high = (middle, high) if scaled(pairs, middle) < target else (low, middle)
    return (low + high) / 2


def table_s8_india():
    """Return India's Table S8 death counts by year and cause group."""
    out = defaultdict(dict)
    for r in E.read_csv('table_s8.csv', E.APPENDIX):
        if r['location'] == INDIA and r['metric'] == 'Number':
            out[int(r['year'])][r['cause_group']] = r
    return out


def build_benchmark():
    causes = E.cause_map('gbd2021')
    shares = E.shares()
    deaths = E.results(E.CONFIG['requests']['gbd2021'], ('location_name', 'age_name', 'cause_name', 'year'),
                       measure=E.CONFIG['deaths'])
    locations = sorted({k[0] for k in deaths} - {E.CONFIG['global']})
    E.require(INDIA in locations and len(locations) == 32, f'Expected India and 31 subnational units, found {len(locations)}')
    estimates = {(l, a, y): components(deaths, causes, shares, l, a, y) for l in locations for a in E.AGES for y in E.BENCHMARKS}
    s8 = table_s8_india()
    factors, checks, capped = [], {}, {}
    for year in E.BENCHMARKS:
        pairs = [p for a in E.AGES for p in estimates[(INDIA, a, year)][1]]
        unscaled = sum(s * d for s, d in pairs)
        ihme = s8[year]['Non-infectious causes']
        k = solve_k(pairs, float(ihme['val']))
        # How much the cap at 1 matters: k without the cap, and India's deaths whose scaled share reaches it.
        capped[str(year)] = dict(k_without_cap=float(ihme['val']) / unscaled,
                                 india_deaths_at_cap=round(sum(d for s, d in pairs if s * k >= 1)))
        factors.append([year, float(ihme['val']), float(ihme['lower']), float(ihme['upper']), unscaled, k])
    k = {f[0]: f[-1] for f in factors}
    rows = []
    for (l, a, y), (infectious, pairs) in sorted(estimates.items()):
        non_infectious = scaled(pairs, k[y])
        rows.append([l, a, y, infectious, sum(s * d for s, d in pairs), non_infectious, infectious + non_infectious])
    for column, name in ((3, 'infectious'), (4, 'non_infectious_unscaled'), (5, 'non_infectious')):
        totals = defaultdict(float)
        for r in rows:
            if r[0] != INDIA:
                totals[(r[1], r[2])] += r[column]
        checks[f'states_to_india_{name}'] = E.ratio_range(f'GBD 2021 states / India, {name}', [
            (totals[(r[1], r[2])], r[column]) for r in rows if r[0] == INDIA and r[column] > 1], 1e-6)
    national = {}
    for year in E.BENCHMARKS:
        part = [r for r in rows if r[0] == INDIA and r[2] == year]
        infectious, non_infectious, total = (sum(r[c] for r in part) for c in (3, 5, 6))
        all_causes = float(s8[year]['All causes']['val'])
        ihme_infectious = all_causes - float(s8[year]['Non-infectious causes']['val'])
        E.require(abs(infectious / ihme_infectious - 1) <= E.TOL['relative'], f'India {year}: infectious {infectious:,.0f}')
        E.require(abs(non_infectious / float(s8[year]['Non-infectious causes']['val']) - 1) <= 1e-9,
                  f'India {year}: non-infectious {non_infectious:,.0f} not calibrated')
        national[str(year)] = dict(sepsis_deaths=round(total), ihme_all_causes=all_causes, ratio=total / all_causes,
                                   infectious_ratio=infectious / ihme_infectious)
    checks['india_vs_table_s8'] = national
    E.write_csv('gbd2021_benchmark.csv', HEADER, rows)
    E.write_csv('scaling_factors.csv', ['year', 'ihme_non_infectious', 'ihme_lower', 'ihme_upper', 'unscaled', 'k'], factors)
    summary = dict(locations=len(locations), rows=len(rows), k={str(y): v for y, v in k.items()})
    E.write_report('03_gbd2021_benchmark.json', __file__, summary, status='PASSED', checks=checks, shares_capped_at_one=capped)
    print('[03] Complete; k = ' + ', '.join(f'{v:.4f} ({y})' for y, v in k.items())
          + f'; India totals within {max(abs(v["ratio"] - 1) for v in national.values()):.2%} of Table S8', flush=True)


if __name__ == '__main__':
    build_benchmark()

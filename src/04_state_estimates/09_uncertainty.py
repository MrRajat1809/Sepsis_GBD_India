"""Uncertainty intervals for the annual estimates, India's deaths by cause and k, from independent log-normal draws of the
inputs; India's death counts take the relative width of their interval from a separate run on India's own GBD rows."""
import statistics
from collections import defaultdict

import numpy as np

import estimates_common as E

HEADER = ['location', 'sex', 'year', 'measure', 'val', 'lower', 'upper', 'projection']
SOURCES = {'infectious': 'sepsis_deaths_annual.csv', 'non_infectious': 'sepsis_deaths_annual.csv',
           'sepsis_deaths': 'sepsis_deaths_annual.csv', 'asr_infectious': 'rates_annual.csv',
           'asr_non_infectious': 'rates_annual.csv', 'age_standardised_rate': 'rates_annual.csv'}
# Count measures, whose intervals for India come from the national run.
COUNTS = ('infectious', 'non_infectious', 'sepsis_deaths')


def national_relative_bounds(inputs, point, spec):
    """Return India's bounds relative to the value from a run on its own GBD rows, and its deaths by cause in the cause years."""
    own, _ = E.run_engine(inputs, national=True, cause_years=spec['cause_years'])
    india = len(inputs['units'])
    check = {m: E.ratio_range(f'India from its own rows / sum of units, {m}',
                              list(zip(own[m][0, ..., 0].ravel(), point[m][india, ..., 0].ravel())), E.TOL['relative'])
             for m in COUNTS}
    draws, _ = E.run_engine(inputs, spec['draws'], np.random.default_rng(spec['national_seed']), national=True,
                            cause_years=spec['cause_years'])
    bounds = {m: np.percentile(draws[m][0], spec['percentiles'], axis=-1) / own[m][0, ..., 0] for m in COUNTS}
    # The crude rate is deaths over a fixed population, so it shares their relative bounds.
    bounds['crude_rate'] = bounds['sepsis_deaths']
    by_cause = {y: (own['by_cause'][y][:, 0], *np.percentile(draws['by_cause'][y], spec['percentiles'], axis=-1))
                for y in spec['cause_years']}
    return bounds, by_cause, check


def cause_intervals(inputs, by_cause):
    """Return India's sepsis-related deaths by cause in the cause years (stage 05), with the relative bounds of the national run."""
    main = {(int(r['year']), r['cause']): r for r in E.read_csv('estimates_annual.csv')
            if r['location'] == E.CONFIG['india'] and r['sex'] == 'Both' and int(r['year']) in by_cause}
    E.require({c for _, c in main} == set(inputs['names']), 'Causes of the national run differ from stage 05')
    rows, pairs = [], []
    for year, (own, low, high) in by_cause.items():
        for ci, cause in enumerate(inputs['names']):
            r = main[(year, cause)]
            val = float(r['sepsis_deaths'])
            relative = (low[ci] / own[ci], high[ci] / own[ci]) if own[ci] > 0 else (0.0, 0.0)
            rows.append([E.CONFIG['india'], year, cause, r['component'], val, val * relative[0], val * relative[1]])
            if val > 1:
                pairs.append((own[ci], val))
    return rows, E.ratio_range('India by cause from its own rows / stage 05', pairs, E.TOL['relative'])


def engine_matches_point(inputs, point, k):
    """Check that, with every input at its reported value, the engine reproduces stages 03, 05 and 08."""
    tables = {name: {(r['location'], r['sex'], int(r['year'])): r for r in E.read_csv(name)} for name in set(SOURCES.values())}
    places = inputs['units'] + [E.CONFIG['india']]
    pairs = defaultdict(list)
    for li, l in enumerate(places):
        for si, s in enumerate(inputs['sexes']):
            for ti, y in enumerate(inputs['years']):
                for m, name in SOURCES.items():
                    pairs[m].append((point[m][li, si, ti, 0], float(tables[name][(l, s, y)][m])))
    checks = {m: E.ratio_range(f'Engine at reported values / stages 05 and 08, {m}', p, 1e-9) for m, p in pairs.items()}
    factors = E.scaling_factors()
    checks['k'] = E.ratio_range('Engine k / stage 03', [(k[i, 0], factors[y]) for i, y in enumerate(E.BENCHMARKS)], 1e-9)
    return checks


def build_uncertainty():
    spec = E.CONFIG['uncertainty']
    inputs = E.engine_inputs()
    point, k_point = E.run_engine(inputs)
    checks = dict(engine_reproduces_point_estimates=engine_matches_point(inputs, point, k_point))
    # Each draw varies the GBD 2023 deaths and rates, the Table S10 counts behind the shares and the Table S8 totals behind k.
    # The draws are independent, ignoring correlations between causes, ages, years and states, so the intervals are approximate.
    draws, k = E.run_engine(inputs, spec['draws'], np.random.default_rng(spec['seed']))
    national, by_cause, checks['india_own_rows_reproduce_sum_of_units'] = national_relative_bounds(inputs, point, spec)
    cause_rows, checks['india_by_cause_reproduces_stage_05'] = cause_intervals(inputs, by_cause)
    population = {(r['location'], r['sex'], int(r['year'])): float(r['population']) for r in E.read_csv('rates_annual.csv')}
    places = inputs['units'] + [E.CONFIG['india']]
    india = len(inputs['units'])
    pop = np.array([[[population[(l, s, y)] for y in inputs['years']] for s in inputs['sexes']] for l in places])
    point['crude_rate'] = point['sepsis_deaths'] / pop[..., None] * 1e5
    draws['crude_rate'] = draws['sepsis_deaths'] / pop[..., None] * 1e5
    rows, outside = [], 0
    for m in (*E.MEASURES, 'crude_rate'):
        low, high = np.percentile(draws[m], spec['percentiles'], axis=-1)
        # Summed independent draws of 31 units would understate India's uncertainty; India's own GBD intervals carry the
        # correlation between states. India's age-standardised rates keep the main run's interval, from its own rates.
        if m in national:
            low[india], high[india] = point[m][india, ..., 0] * national[m][0], point[m][india, ..., 0] * national[m][1]
        for li, l in enumerate(places):
            for si, s in enumerate(inputs['sexes']):
                for ti, y in enumerate(inputs['years']):
                    val, lower, upper = point[m][li, si, ti, 0], low[li, si, ti], high[li, si, ti]
                    outside += val > 0 and not lower <= val <= upper
                    rows.append([l, s, y, m, val, lower, upper, int(y >= E.CONFIG['first_projection_year'])])
    E.require(not outside, f'{outside} point estimates lie outside their uncertainty interval')
    k_low, k_high = np.percentile(k, spec['percentiles'], axis=1)
    scaling = [[y, k_point[i, 0], k_low[i], k_high[i]] for i, y in enumerate(E.BENCHMARKS)]
    checks['point_estimates_inside_intervals'] = dict(n=len(rows), outside=0)
    E.write_csv('uncertainty_annual.csv', HEADER, rows)
    E.write_csv('uncertainty_scaling.csv', ['year', 'k', 'lower', 'upper'], scaling)
    E.write_csv('uncertainty_by_cause.csv', ['location', 'year', 'cause', 'component', 'val', 'lower', 'upper'], cause_rows)
    india = {f'{r[2]} {r[3]}': [round(v, 1) for v in r[4:7]] for r in rows if r[0] == E.CONFIG['india'] and r[1] == 'Both'
             and r[2] in (1990, 2019, 2021, 2023) and r[3] in ('sepsis_deaths', 'age_standardised_rate')}
    widths = sorted((r[6] - r[5]) / r[4] for r in rows if r[1] == 'Both' and r[2] == E.YEARS[-1] and r[3] == 'sepsis_deaths'
                    and r[0] != E.CONFIG['india'])
    summary = dict(draws=spec['draws'], seed=spec['seed'], national_seed=spec['national_seed'], rows=len(rows),
                   state_relative_width_2023=dict(min=widths[0], median=statistics.median(widths), max=widths[-1]))
    E.write_report('09_uncertainty.json', __file__, summary, status='PASSED', checks=checks, india_both_sexes=india,
                   k={str(r[0]): r[1:] for r in scaling})
    d2023 = india[f'{E.YEARS[-1]} sepsis_deaths']
    print(f'[09] Complete; {spec["draws"]} draws; India {E.YEARS[-1]}: {d2023[0]:,.0f} sepsis-related deaths '
          f'({d2023[1]:,.0f}-{d2023[2]:,.0f}); k 95% intervals ' + ', '.join(f'{lo:.3f}-{hi:.3f}' for _, _, lo, hi in scaling),
          flush=True)


if __name__ == '__main__':
    build_uncertainty()

"""Sensitivity analyses: no national scaling, shares from the nearest benchmark year, the GBD 2021 round, without COVID-19,
non-infectious shares that vary with each state's Healthcare Access and Quality (HAQ) Index, and other assumptions for the
projected years after 2021."""
import numpy as np

import estimates_common as E

HEADER = ['analysis', 'location', 'sex', 'year', 'measure', 'main', 'alternative', 'ratio']
MEASURES = ('non_infectious', 'sepsis_deaths', 'age_standardised_rate')
INDIA, GLOBAL = E.CONFIG['india'], E.CONFIG['global']


def compare(analysis, main, alternative, inputs, years):
    """Return rows comparing an alternative run with the main one for each place, sex and measure in the given years."""
    places = inputs['units'] + [INDIA]
    rows = []
    for li, l in enumerate(places):
        for si, s in enumerate(inputs['sexes']):
            for ti, y in enumerate(inputs['years']):
                if y in years:
                    for m in MEASURES:
                        a, b = main[m][li, si, ti, 0], alternative[m][li, si, ti, 0]
                        rows.append([analysis, l, s, y, m, a, b, b / a if a else ''])
    return rows


def ranks(values):
    """Return the rank of each value (0 for the smallest), for Spearman correlations; ties are not averaged."""
    order = np.argsort(np.argsort(values))
    return order.astype(float)


def round_comparison():
    """Analysis 3: the GBD 2021-round estimates against the GBD 2023 estimates, by state, in the benchmark years (stage 06)."""
    rows, summary = [], {}
    table = [r for r in E.read_csv('round_comparison.csv') if r['component'] in ('non_infectious', 'sepsis_deaths')]
    for r in table:
        rows.append(['gbd2021_round', r['location'], 'Both', int(r['year']), r['component'], float(r['gbd2023']),
                     float(r['gbd2021']), float(r['gbd2021']) / float(r['gbd2023'])])
    for year in E.BENCHMARKS:
        part = {r['location']: (float(r['gbd2023']), float(r['gbd2021'])) for r in table
                if int(r['year']) == year and r['component'] == 'sepsis_deaths'}
        units = sorted(l for l in part if l != INDIA)
        new, old = np.array([part[l][0] for l in units]), np.array([part[l][1] for l in units])
        share_new, share_old = new / part[INDIA][0], old / part[INDIA][1]
        change = sorted(zip(share_old - share_new, units))
        summary[str(year)] = dict(spearman_rank_correlation=float(np.corrcoef(ranks(new), ranks(old))[0, 1]),
                                  largest_share_lower_in_gbd2021=dict(location=change[0][1], points=100 * change[0][0]),
                                  largest_share_higher_in_gbd2021=dict(location=change[-1][1], points=100 * change[-1][0]))
    return rows, summary


def haq_paths(inputs, haq):
    """Return the HAQ of each unit and India in every year, and of each unit, India and the world in the benchmark years."""
    places = inputs['units'] + [INDIA]
    points = {p: {y: v for (l, y), v in haq.items() if l == p} for p in places + [GLOBAL]}
    E.require(all(points.values()), f'No HAQ values for {[p for p in points if not points[p]]}')
    # HAQ (GBD 2016 release) is interpolated between its years and held at 2016.
    annual = np.array([[E.interpolate(points[p], y) for y in inputs['years']] for p in places])
    benchmark = np.array([[E.interpolate(points[p], y) for y in E.BENCHMARKS] for p in places + [GLOBAL]])
    return annual, benchmark


def derived_slope(inputs, gap, search):
    """Solve the slope per HAQ point at which global shares moved by India's HAQ gap give India's Table S8 total without k."""
    def total(beta, i):
        """Return India's GBD 2021 non-infectious deaths in benchmark year i with the global shares moved by beta * gap."""
        groups, bands, deaths = inputs['pairs'][i]
        return float((np.minimum(1.0, E.shifted(inputs['f'][groups, bands, i], beta * gap[i])) * deaths).sum())

    target = inputs['target']
    per_year = []
    for i in range(len(E.BENCHMARKS)):
        low, high = search
        E.require((total(low, i) - target[i]) * (total(high, i) - target[i]) < 0,
                  'HAQ slope search range does not bracket the target')
        # The total rises with the slope when India's HAQ gap is positive and falls when it is negative.
        for _ in range(200):
            middle = (low + high) / 2
            low, high = (middle, high) if (total(middle, i) > target[i]) == (gap[i] < 0) else (low, middle)
        per_year.append((low + high) / 2)
    # One slope for all benchmark years: least squares on the log scale, by ternary search between the per-year slopes.
    loss = lambda beta: sum(np.log(total(beta, i) / target[i]) ** 2 for i in range(len(E.BENCHMARKS)))
    low, high = min(per_year), max(per_year)
    for _ in range(200):
        a, b = low + (high - low) / 3, high - (high - low) / 3
        low, high = (a, high) if loss(a) > loss(b) else (low, b)
    return (low + high) / 2, per_year


def haq_analysis(inputs, main, every_year):
    """Analysis 5: rows comparing each HAQ slope with the main estimates, and a summary of each slope."""
    spec = E.CONFIG['sensitivity']['haq']
    annual, benchmark = haq_paths(inputs, E.haq_index())
    india, world = len(inputs['units']), len(inputs['units']) + 1
    gap = benchmark[india] - benchmark[world]
    # The slope derived from India's departure from the global shares, and fixed odds ratios r per 10 HAQ points.
    beta, per_year = derived_slope(inputs, gap, spec['slope_search'])
    slopes = {'haq_derived': beta, **{f'haq_odds_ratio_{r}': float(np.log(r)) / spec['points'] for r in spec['odds_ratios']}}

    # Each place's shares move on the logit scale by b * (its HAQ - India's HAQ). k is solved again on the units' GBD 2021
    # deaths, so India's GBD 2021 total is unchanged and deaths are only redistributed between units.
    def shift(b):
        return dict(annual=b * (annual - annual[india]), benchmark=b * (benchmark[:india] - benchmark[india]))

    zero, _ = E.run_engine(inputs, shift=shift(0.0))
    checks = {m: E.ratio_range(f'HAQ engine with slope 0 / main, {m}',
                               [(a, b) for a, b in zip(zero[m].ravel(), main[m].ravel())], 1e-9) for m in MEASURES}
    rows, summary = [], {}
    for name, b in slopes.items():
        alternative, k = E.run_engine(inputs, shift=shift(b))
        part = compare(name, main, alternative, inputs, every_year)
        rows += part
        states = {y: sorted((r[7], r[1]) for r in part if r[1] != INDIA and r[2] == 'Both' and r[3] == y
                            and r[4] == 'sepsis_deaths') for y in (2021, E.YEARS[-1])}
        summary[name] = dict(
            slope_per_point=b, odds_ratio_per_10_points=float(np.exp(spec['points'] * b)),
            k={str(y): float(v) for y, v in zip(E.BENCHMARKS, k[:, 0])},
            india_sepsis_deaths=india_ratios(part, name, 'sepsis_deaths', {2021, E.YEARS[-1]}),
            states={str(y): dict(lowest=dict(location=s[0][1], ratio=s[0][0]), highest=dict(location=s[-1][1], ratio=s[-1][0]))
                    for y, s in states.items()})
    summary['haq_derived']['slope_by_benchmark_year'] = {str(y): v for y, v in zip(E.BENCHMARKS, per_year)}
    summary['haq_derived']['india_minus_world_haq'] = {str(y): float(v) for y, v in zip(E.BENCHMARKS, gap)}
    return rows, summary, checks


def projection_analysis(inputs, main):
    """Analysis 6: the projected years (2022 onwards) under other non-infectious shares than the 2021 shares and k of the main estimates."""
    spec = E.CONFIG['sensitivity']['projection']
    years = sorted(y for y in inputs['years'] if y >= E.CONFIG['first_projection_year'])
    same, _ = E.run_engine(inputs, projection=dict(factor=1.0))
    check = {m: E.ratio_range(f'Projection factor 1 / main, {m}', [(a, b) for a, b in zip(same[m].ravel(), main[m].ravel())], 1e-12)
             for m in MEASURES}
    interval = {(int(r['year']), r['measure']): (float(r['lower']), float(r['upper'])) for r in E.read_csv('uncertainty_annual.csv')
                if r['location'] == INDIA and r['sex'] == 'Both' and r['measure'] in ('sepsis_deaths', 'age_standardised_rate')}
    # Like k, a uniform factor moves the national level and redistributes only through each state's mix of non-infectious deaths.
    scenarios = {f'projection_shares_x{f}': dict(factor=f) for f in spec['share_factors']}
    # The shares and k of the last benchmark year before the pandemic differ from 2021's by cause and age.
    scenarios[f'projection_{spec["pre_pandemic_benchmark"]}_shares'] = dict(benchmark=spec['pre_pandemic_benchmark'])
    units, both = inputs['units'], inputs['sexes'].index('Both')
    rows, summary = [], {}
    for name, projection in scenarios.items():
        alternative, _ = E.run_engine(inputs, projection=projection)
        rows += compare(name, main, alternative, inputs, set(years))
        summary[name] = {}
        for year in years:
            ti = inputs['years'].index(year)
            pick = lambda result, m: result[m][:, both, ti, 0]
            # National effect: India's ratio to the main estimate, inside the main 95% interval or not. Effect on the
            # distribution: each state's share of India's deaths and the rankings of states, which ignore the national level.
            india = {m: float(pick(alternative, m)[-1] / pick(main, m)[-1]) for m in MEASURES}
            deaths_main, deaths_alt = pick(main, 'sepsis_deaths')[:-1], pick(alternative, 'sepsis_deaths')[:-1]
            ratio = deaths_alt / deaths_main
            share_change = 100 * (deaths_alt / deaths_alt.sum() - deaths_main / deaths_main.sum())
            asr_main, asr_alt = pick(main, 'age_standardised_rate')[:-1], pick(alternative, 'age_standardised_rate')[:-1]
            rank_main, rank_alt = ranks(asr_main), ranks(asr_alt)
            shifts = np.abs(rank_alt - rank_main)
            inside = {m: bool(interval[(year, m)][0] <= pick(alternative, m)[-1] <= interval[(year, m)][1])
                      for m in ('sepsis_deaths', 'age_standardised_rate')}
            summary[name][str(year)] = dict(
                india_ratio=india, india_inside_main_95_interval=inside,
                state_ratio=dict(lowest=dict(location=units[int(ratio.argmin())], ratio=float(ratio.min())),
                                 highest=dict(location=units[int(ratio.argmax())], ratio=float(ratio.max()))),
                largest_change_in_share_of_india_points=dict(location=units[int(np.abs(share_change).argmax())],
                                                             points=float(share_change[np.abs(share_change).argmax()])),
                spearman_deaths=float(np.corrcoef(ranks(deaths_main), ranks(deaths_alt))[0, 1]),
                spearman_age_standardised_rate=float(np.corrcoef(rank_main, rank_alt)[0, 1]),
                states_changing_rank_by_rate=int((shifts > 0).sum()), largest_rank_shift_by_rate=int(shifts.max()))
    last = str(years[-1])
    ti = inputs['years'].index(years[-1])
    non_infectious_share = float(main['non_infectious'][-1, both, ti, 0] / main['sepsis_deaths'][-1, both, ti, 0])
    summary['main_non_infectious_share_of_india_sepsis_deaths'] = {last: non_infectious_share}
    return rows, summary, check


def india_ratios(rows, analysis, measure, years):
    """Return India's ratio to the main estimate (both sexes) by year, for one analysis and measure."""
    return {str(r[3]): r[7] for r in rows if r[0] == analysis and r[1] == INDIA and r[2] == 'Both' and r[4] == measure
            and r[3] in years}


def build_sensitivity():
    inputs = E.engine_inputs()
    # Analyses 1, 2, 4, 5 and 6 rerun the engine with every input at its reported value; analysis 3 compares GBD rounds.
    main, _ = E.run_engine(inputs)
    spec = E.CONFIG['sensitivity']
    every_year = set(E.YEARS)
    covid_years = set(range(spec['covid_years'][0], spec['covid_years'][1] + 1))
    no_scaling, _ = E.run_engine(inputs, scale=False)
    nearest, _ = E.run_engine(inputs, schedule='nearest')
    no_covid, _ = E.run_engine(inputs, drop={spec['covid_cause']})
    rows = (compare('no_scaling', main, no_scaling, inputs, every_year)
            + compare('nearest_benchmark_shares', main, nearest, inputs, every_year)
            + compare('without_covid19', main, no_covid, inputs, covid_years))
    round_rows, round_summary = round_comparison()
    rows += round_rows
    haq_rows, haq_summary, haq_checks = haq_analysis(inputs, main, every_year)
    rows += haq_rows
    projection_rows, projection_summary, projection_check = projection_analysis(inputs, main)
    rows += projection_rows
    E.require(all(r[7] == '' or r[7] > 0 for r in rows), 'An alternative estimate is not positive')
    key_years = {1990, 2019, 2021, 2023}
    nearest_total = [r for r in rows if r[0] == 'nearest_benchmark_shares' and r[1] == INDIA and r[2] == 'Both'
                     and r[4] == 'sepsis_deaths']
    largest = max(nearest_total, key=lambda r: abs(r[7] - 1))
    states_2023 = [r[7] for r in rows if r[0] == 'no_scaling' and r[1] != INDIA and r[2] == 'Both' and r[3] == E.YEARS[-1]
                   and r[4] == 'sepsis_deaths']
    results = {
        '1_no_scaling': dict(india_non_infectious=india_ratios(rows, 'no_scaling', 'non_infectious', key_years),
                             india_sepsis_deaths=india_ratios(rows, 'no_scaling', 'sepsis_deaths', key_years),
                             states_sepsis_deaths_2023=dict(min=min(states_2023), max=max(states_2023))),
        '2_nearest_benchmark_shares': dict(largest_india_difference=dict(year=largest[3], ratio=largest[7]),
                                           note='Ties between two benchmark years take the earlier year'),
        '3_gbd2021_round': round_summary,
        '4_without_covid19': dict(india_sepsis_deaths=india_ratios(rows, 'without_covid19', 'sepsis_deaths', covid_years),
                                  india_age_standardised_rate=india_ratios(rows, 'without_covid19', 'age_standardised_rate',
                                                                           covid_years)),
        '5_haq_index': haq_summary,
        '6_projection': projection_summary}
    E.write_csv('sensitivity.csv', HEADER, rows)
    E.write_report('10_sensitivity.json', __file__, dict(rows=len(rows), analyses_run=6), status='PASSED', results=results,
                   checks=dict(haq_slope_zero_reproduces_main=haq_checks, projection_factor_one_reproduces_main=projection_check))
    covid = results['4_without_covid19']['india_sepsis_deaths']
    last = str(E.YEARS[-1])
    projected = ', '.join(f'{name.replace("projection_", "")} {s[last]["india_ratio"]["sepsis_deaths"]:.3f}'
                          for name, s in projection_summary.items() if name.startswith('projection_'))
    print(f'[10] Complete; {len(rows):,} comparisons. India without scaling: '
          f'{results["1_no_scaling"]["india_sepsis_deaths"]["2021"]:.3f} of the main estimate (2021); without COVID-19: '
          f'{covid["2021"]:.3f} (2021); HAQ odds ratio per 10 points derived as '
          f'{haq_summary["haq_derived"]["odds_ratio_per_10_points"]:.3f}; projected {last}: {projected}', flush=True)


if __name__ == '__main__':
    build_sensitivity()

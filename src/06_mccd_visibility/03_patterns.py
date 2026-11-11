"""How visibility relates to certification coverage and to ill-defined causes across units (Spearman correlations by
year), and its least-squares annual percentage change over the pre-pandemic trend years."""
import statistics

import visibility_common as V

PAIRS = [('visibility_share', 'certification_coverage'), ('visibility_share', 'ill_defined_share'),
         ('visibility_count', 'certification_coverage'), ('visibility_share_infectious', 'ill_defined_share'),
         ('visibility_share', 'visibility_share_infectious')]
# The count ratio is the share ratio times certification coverage times registration completeness (registered /
# estimated deaths), so the trends of these three explain that of the count ratio.
TRENDED = ['visibility_count', 'visibility_share', 'visibility_share_infectious', 'certification_coverage', 'registration_completeness',
           'ill_defined_share']
# The three India rows are left out of the comparisons across units.
SKIP = (V.INDIA, V.CONFIG['reporting_units'], V.CONFIG['fixed_panel'])
# India's trend is that of the fixed panel: the other two India rows change membership from year to year.
NO_TREND = (V.INDIA, V.CONFIG['reporting_units'])
PANEL = V.CONFIG['fixed_panel']


def build_patterns():
    rows = V.read_csv('visibility.csv')
    get = lambda r, k: float(r[k]) if r[k] != '' else None
    correlations = []
    for year in V.YEARS:
        part = [r for r in rows if int(r['year']) == year and r['unit'] not in SKIP and r['complete'] == '1']
        for a, b in PAIRS:
            pairs = [(get(r, a), get(r, b)) for r in part if get(r, a) is not None and get(r, b) is not None]
            rho = V.spearman([x for x, _ in pairs], [y for _, y in pairs]) if len(pairs) >= 5 else ''
            correlations.append([year, a, b, len(pairs), rho])
    # Trend years end before the pandemic: COVID-19 deaths count as sepsis-related in the estimates but are coded as COVID-19 in MCCD.
    first, last = V.CONFIG['trend_years']
    trends = []
    for unit in sorted({r['unit'] for r in rows} - set(NO_TREND)):
        part = [r for r in rows if r['unit'] == unit and first <= int(r['year']) <= last and r['complete'] == '1']
        for measure in TRENDED:
            points = [(int(r['year']), get(r, measure)) for r in part if get(r, measure)]
            ok = len(points) >= V.CONFIG['trend_minimum_years']
            trends.append([unit, measure, len(points), min(p[0] for p in points) if points else '', max(p[0] for p in points) if points else '',
                           V.log_slope([p[0] for p in points], [p[1] for p in points]) if ok else ''])
    V.write_csv('correlations_by_year.csv', ['year', 'measure', 'against', 'units', 'spearman'], correlations)
    V.write_csv('trends.csv', ['unit', 'measure', 'years', 'first_year', 'last_year', 'annual_percent_change'], trends)
    median = lambda v: statistics.median(v) if v else ''
    summary_correlations = {f'{a} ~ {b}': dict(median=median([c[4] for c in correlations if c[1] == a and c[2] == b and c[4] != '']),
                                               by_year={str(c[0]): c[4] for c in correlations
                                                        if c[1] == a and c[2] == b and c[0] in (2008, 2015, 2019, 2021)})
                            for a, b in PAIRS}
    trend_of = lambda unit, m: next(t[5] for t in trends if t[0] == unit and t[1] == m)
    share_trends = sorted((t[5], t[0]) for t in trends if t[1] == 'visibility_share' and t[5] != '' and t[0] not in SKIP)
    summary = dict(correlation_rows=len(correlations), trend_rows=len(trends), trend_years=f'{first}-{last}')
    V.require(all(trend_of(PANEL, m) != '' for m in TRENDED), f'{PANEL}: no trend over {first}-{last}')
    V.write_report('03_patterns.json', __file__, summary, status='PASSED', correlations=summary_correlations,
                   india_annual_percent_change=dict(basis=PANEL, **{m: trend_of(PANEL, m) for m in TRENDED}),
                   share_ratio_trends=dict(fastest_fall=share_trends[:3], fastest_rise=share_trends[-3:], units=len(share_trends)))
    india = trend_of(PANEL, 'visibility_share')
    print(f'[03] Complete; {len(correlations)} correlations and {len(trends)} trends; India (fixed set of units) share ratio {india:+.1f}% a year '
          f'({first}-{last}); median correlation with certification coverage '
          f'{summary_correlations["visibility_share ~ certification_coverage"]["median"]:.2f}', flush=True)


if __name__ == '__main__':
    build_patterns()

"""Visibility of sepsis in death certification by unit and year, 2008-2023: MCCD septicaemia deaths set against the
estimated sepsis-related deaths. MCCD tabulates the underlying cause only, while sepsis-related deaths include sepsis
anywhere in the causal chain, so the ratios describe how sepsis is recorded, not under-reporting."""
from collections import defaultdict

import visibility_common as V

HEADER = ['unit', 'year', 'complete', 'septicaemia', 'certified', 'infectious_A00_B99', 'ill_defined_R00_R99', 'registered',
          'sepsis_related', 'sepsis_lower', 'sepsis_upper', 'gbd_deaths', 'gbd_infectious', 'visibility_count',
          'visibility_count_lower', 'visibility_count_upper', 'visibility_share', 'visibility_count_infectious',
          'visibility_share_infectious', 'septicaemia_share_of_certified', 'sepsis_share_of_deaths', 'certification_coverage',
          'registration_completeness', 'ill_defined_share', 'projection']


def gbd_side():
    """Return GBD 2023 sepsis-related deaths (with interval), all deaths and infectious-cause deaths by comparison unit and year."""
    out = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0, 0.0])
    interval = {(r['location'], int(r['year'])): (float(r['lower']), float(r['upper'])) for r in V.read_csv('uncertainty_annual.csv', V.ESTIMATES)
                if r['sex'] == 'Both' and r['measure'] == 'sepsis_deaths'}
    for r in V.read_csv('sepsis_deaths_annual.csv', V.ESTIMATES):
        year = int(r['year'])
        if r['sex'] == 'Both' and year in V.YEARS:
            key = (V.unit_of(r['location'], year), year)
            low, high = interval[(r['location'], year)]
            for i, value in enumerate((float(r['sepsis_deaths']), low, high, float(r['deaths']), float(r['infectious']))):
                out[key][i] += value
    return out


def ratios(m, c, inf, ill, reg, t, t_low, t_high, d, i):
    """Return the count and share ratios for septicaemia and for A00-B99, then their components; '' where a figure is missing."""
    # Count ratio = septicaemia / sepsis-related deaths, its interval from the estimate's uncertainty only; share ratio =
    # septicaemia share of certified deaths / sepsis-related share of GBD deaths. A00-B99 is set against infectious causes.
    div = lambda a, b: a / b if a != '' and b not in ('', 0) else ''
    return [div(m, t), div(m, t_high), div(m, t_low), div(div(m, c), div(t, d)), div(inf, i), div(div(inf, c), div(i, d)),
            div(m, c), div(t, d), div(c, reg), div(reg, d), div(ill, c)]


def pooled(name, year, members):
    """Return one row adding up complete unit rows of a year, MCCD and GBD figures alike, with its ratios."""
    m, c, inf, ill = (sum(r[n] for r in members) for n in (3, 4, 5, 6))
    reg = sum(r[7] for r in members) if all(r[7] != '' for r in members) else ''
    t, t_low, t_high, d, i = (sum(r[n] for r in members) for n in range(8, 13))
    return [name, year, 1, m, c, inf, ill, reg, t, t_low, t_high, d, i, *ratios(m, c, inf, ill, reg, t, t_low, t_high, d, i),
            int(year >= V.CONFIG['first_projection_year'])]


def group(unit):
    """Return the panel group of a unit: Andhra Pradesh and Telangana are one group in every year, so the split does not break the panel."""
    return V.AP_TG['unit'] if unit in V.AP_TG['gbd_units'] else unit


def fixed_panel(unit_rows):
    """Return the groups whose units all reported completely in every trend year."""
    first, last = V.CONFIG['trend_years']
    complete = defaultdict(lambda: defaultdict(list))
    for r in unit_rows:
        complete[group(r[0])][r[1]].append(r[2])
    return sorted(g for g, years in complete.items() if all(years[y] and all(years[y]) for y in range(first, last + 1)))


def build_visibility():
    gbd = gbd_side()
    units = [r for r in V.read_csv('mccd_units.csv') if int(r['year']) in V.YEARS]
    value = lambda r, k: int(r[k]) if r[k] != '' else ''
    rows = []
    # India's row sets the all-India MCCD figures, which cover the reporting States/UTs only, against all of India's deaths.
    for r in units:
        year = int(r['year'])
        key = (r['unit'], year)
        V.require(key in gbd, f'No GBD estimates for {key}')
        t, t_low, t_high, d, i = gbd[key]
        m, c, inf, ill, reg = (value(r, k) for k in ('septicaemia', 'certified', 'infectious_A00_B99', 'ill_defined_R00_R99', 'registered'))
        # Estimates from 2022 on rest on projected sepsis-related shares.
        rows.append([r['unit'], year, int(r['complete']), m, c, inf, ill, reg, t, t_low, t_high, d, i,
                     *ratios(m, c, inf, ill, reg, t, t_low, t_high, d, i), int(year >= V.CONFIG['first_projection_year'])])
    unit_rows = [r for r in rows if r[0] != V.INDIA]
    # India as the sum of the units that reported completely in each year.
    for year in V.YEARS:
        rows.append(pooled(V.CONFIG['reporting_units'], year, [r for r in unit_rows if r[1] == year and r[2]]))
    # India as the sum of a fixed set of units, so that trends are not driven by States/UTs joining or leaving the reports.
    panel = fixed_panel(unit_rows)
    for year in V.YEARS:
        members = [r for r in unit_rows if r[1] == year and group(r[0]) in panel]
        if all(r[2] for r in members):
            rows.append(pooled(V.CONFIG['fixed_panel'], year, members))
    V.require(all(r[13] == '' or r[14] <= r[13] <= r[15] for r in rows), 'A count ratio lies outside its interval')
    V.write_csv('visibility.csv', HEADER, rows)
    pick = lambda unit, year: next(r for r in rows if r[0] == unit and r[1] == year)
    india = {str(y): dict(visibility_count=round(pick(V.INDIA, y)[13], 4), visibility_share=round(pick(V.INDIA, y)[16], 3),
                          complete_units_count=round(pick(V.CONFIG['reporting_units'], y)[13], 4),
                          complete_units_share=round(pick(V.CONFIG['reporting_units'], y)[16], 3),
                          certification_coverage=round(pick(V.INDIA, y)[21], 3) if pick(V.INDIA, y)[21] != '' else '')
             for y in (2008, 2013, 2019, 2021, 2023)}
    states_2021 = sorted((r[16], r[0]) for r in rows if r[1] == 2021 and r[2] and r[0] not in (V.INDIA, V.CONFIG['reporting_units'])
                         and r[16] != '')
    panel_rows = {r[1]: r for r in rows if r[0] == V.CONFIG['fixed_panel']}
    first, last = V.CONFIG['trend_years']
    summary = dict(rows=len(rows), years=f'{V.YEARS[0]}-{V.YEARS[-1]}')
    V.write_report('02_visibility.json', __file__, summary, status='PASSED', india=india,
                   fixed_panel=dict(groups=panel, years=sorted(panel_rows), share_of_india_gbd_deaths={
                       str(y): round(panel_rows[y][11] / pick(V.INDIA, y)[11], 3) for y in (first, last)}),
                   share_ratio_2021=dict(lowest=states_2021[:3], highest=states_2021[-3:]))
    print(f'[02] Complete; {len(rows)} unit-years; India 2021: {100 * india["2021"]["visibility_count"]:.1f}% of estimated sepsis-related '
          f'deaths appear as septicaemia; share ratio {india["2021"]["visibility_share"]:.2f}', flush=True)


if __name__ == '__main__':
    build_visibility()

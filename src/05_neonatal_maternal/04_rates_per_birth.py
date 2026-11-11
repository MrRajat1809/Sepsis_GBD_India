"""Neonatal sepsis per 1,000 and maternal sepsis per 100,000 live births by state and year. Births are derived from the
GBD 2023 population aged 0-6 days, so that numerator and denominator agree; births from the SRS crude birth rate (RBI
Handbook) times the GBD 2023 population are given for comparison."""
from collections import defaultdict

import neonatal_maternal_common as N

SPEC = N.CONFIG['births']
SRS = SPEC['srs']
HEADER = ['location', 'year', 'population', 'births', 'srs_birth_rate', 'srs_birth_rate_method', 'births_srs', 'births_srs_over_gbd',
          'neonatal_sepsis_per_1000', 'neonatal_sepsis_0_27_days_per_1000', 'neonatal_period_sepsis_related_per_1000',
          'maternal_sepsis_per_100000', 'maternal_sepsis_related_per_100000', 'projection']


def gbd_births(population):
    """Return {(location, year): (births from the 0-6 day group, births from the 7-27 day group)} implied by GBD 2023."""
    early, late = SPEC['early_neonatal_age'], SPEC['late_neonatal_age']
    deaths = N.results(N.CONFIG['requests']['population_by_age'], ('location_name', 'age_name', 'year'), ages={early, late})
    n1, n2 = (SPEC['age_group_days'][age] / SPEC['days_per_year'] for age in (early, late))
    # Population is person-years lived: P = n (B - (1 - a) D) at 0-6 days, with n the group's length in years, D its deaths
    # and a the fraction of the interval lived by those who die; at 7-27 days the 0-6 day deaths are also taken from B.
    a = SPEC['fraction_of_interval_lived_by_deaths']
    out = {}
    for (location, age, year), d1 in deaths.items():
        if age == early:
            d2 = deaths[(location, late, year)]
            out[(location, year)] = (population[(location, early, year)] / n1 + (1 - a) * d1,
                                     population[(location, late, year)] / n2 + d1 + (1 - a) * d2)
    return out


def birth_rates():
    """Return {state: {year: rate}} of the printed SRS birth rates, without markers and printed irregularities."""
    irregular = {(i['state'], i['year']) for i in N.RAW_CONFIG['srs_birth_rate']['printed_irregularities']}
    out = defaultdict(dict)
    for r in N.read_csv(SRS['srs_table'].split('/')[-1], N.ROOT / SRS['srs_table'].rsplit('/', 1)[0]):
        # A trailing '*' marks a State/UT reported together with another; its value is used as printed.
        value = r['printed'].rstrip(SRS['combined_marker'])
        if r['printed'] not in SRS['markers'] and (r['state'], int(r['year'])) not in irregular:
            out[r['state']][int(r['year'])] = float(value)
    return out


def rate_for(series, year):
    """Return (rate, method, kind of method) for one year: printed, linearly interpolated, or from the nearest printed year."""
    if year in series:
        return series[year], 'printed', 'printed'
    years = sorted(series)
    if year < years[0] or year > years[-1]:
        nearest = years[0] if year < years[0] else years[-1]
        return series[nearest], f'nearest printed year ({nearest})', 'nearest printed year'
    low, high = max(y for y in years if y < year), min(y for y in years if y > year)
    t = (year - low) / (high - low)
    return series[low] * (1 - t) + series[high] * t, f'interpolated ({low}-{high})', 'interpolated'


def unit_rate(rates, unit, year):
    """Return (rate, method, kind of method) for a GBD unit and year, borrowing a containing State/UT's rate where SRS has none."""
    # The members of Other Union Territories have very different birth rates and no population weights.
    if unit in SRS['not_estimated']:
        return '', 'not estimated', 'not estimated'
    # India takes the all-India rate, Jammu & Kashmir and Ladakh that of Jammu & Kashmir.
    state = SRS['national'] if unit == N.INDIA else SRS['unit_rate'].get(unit, unit)
    # Telangana up to 2013, and Chhattisgarh, Jharkhand and Uttarakhand up to 1998, take the rate of the state they were part of.
    parent = SRS['parent_rate'].get(unit)
    if parent and year <= parent['through']:
        rate, method, _ = rate_for(rates[parent['state']], year)
        return rate, f'{parent["state"]}, {method}', 'rate of the containing State/UT'
    N.require(state in rates, f'No SRS birth rates for {state}')
    return rate_for(rates[state], year)


def build_rates_per_birth():
    rates = birth_rates()
    # Ladakh's own SRS rates must be close to those of Jammu & Kashmir, which stand for the combined unit.
    check = SRS['unit_rate_check']
    own, other = rates[SRS['unit_rate'][check['unit']]], rates[check['other']]
    gaps = [abs(own[y] - other[y]) for y in other if y in own]
    N.require(gaps and max(gaps) <= check['max_difference'], f'{check["other"]} differs from {check["unit"]} rate by up to {max(gaps)}')
    population, by_age = N.population()
    births = gbd_births(by_age)
    late_check = N.ratio_range('Births from the 7-27 day group / from the 0-6 day group', [(b2, b1) for b1, b2 in births.values()],
                               SPEC['late_neonatal_check_tolerance'])
    underlying = {(r['location'], int(r['year']), r['cause']): float(r['deaths']) for r in N.read_csv('underlying_annual.csv')
                  if r['sex'] == 'Both'}
    period = {(r['location'], int(r['year'])): r for r in N.read_csv('neonatal_period.csv') if r['age_group'] == N.CONFIG['neonatal_period']}
    maternal = {(r['location'], int(r['year'])): float(r['sepsis_related']) for r in N.read_csv('maternal_annual.csv') if r['sex'] == 'Female'}
    locations = sorted({k[0] for k in underlying})
    rows, methods = [], defaultdict(int)
    for location in locations:
        for year in N.YEARS:
            rate, method, kind = unit_rate(rates, location, year)
            methods[kind] += 1
            pop, b = population[(location, 'Both', year)], births[(location, year)][0]
            srs = rate / 1000 * pop if rate != '' else ''
            per = lambda deaths, scale: deaths / b * scale
            # The 0-27 day sepsis-related measures exist only in the years with age detail.
            p = period.get((location, year))
            rows.append([location, year, pop, b, rate, method, srs, srs / b if srs != '' else '',
                         per(underlying[(location, year, N.NEONATAL['cause'])], 1000),
                         per(float(p['neonatal_sepsis']), 1000) if p else '', per(float(p['sepsis_related']), 1000) if p else '',
                         per(underlying[(location, year, N.MATERNAL['cause'])], 1e5), per(maternal[(location, year)], 1e5),
                         int(year >= N.CONFIG['first_projection_year'])])
    N.require(all(r[3] > 0 for r in rows), 'A unit has no live births')
    india_births = {r[1]: r[3] for r in rows if r[0] == N.INDIA}
    unit_births = defaultdict(float)
    for r in rows:
        if r[0] != N.INDIA:
            unit_births[r[1]] += r[3]
    units_check = N.ratio_range('Births of the units / of India', [(unit_births[y], india_births[y]) for y in N.YEARS], 1e-6)
    srs_ratio = [r[7] for r in rows if r[7] != '']
    N.write_csv('rates_per_birth.csv', HEADER, rows)
    pick = lambda y: next(r for r in rows if r[0] == N.INDIA and r[1] == y)
    india = {str(y): dict(births=round(pick(y)[3]), births_srs=round(pick(y)[6]), births_srs_over_gbd=round(pick(y)[7], 3),
                          neonatal_sepsis_per_1000=round(pick(y)[8], 2),
                          neonatal_period_sepsis_related_per_1000=round(pick(y)[10], 2) if pick(y)[10] != '' else '',
                          maternal_sepsis_per_100000=round(pick(y)[11], 1), maternal_sepsis_related_per_100000=round(pick(y)[12], 1))
             for y in (1990, 2000, 2010, 2019, 2021, 2023)}
    states = sorted((r[10], r[0]) for r in rows if r[1] == 2021 and r[0] != N.INDIA and r[10] != '')
    summary = dict(rows=len(rows), srs_births_not_estimated=list(SRS['not_estimated']))
    N.write_report('04_rates_per_birth.json', __file__, summary, status='PASSED', srs_birth_rate_methods=dict(methods),
                   checks=dict(late_neonatal_births=late_check, units_add_up_to_india=units_check,
                               srs_unit_rate_difference=dict(unit=check['unit'], other=check['other'], max=max(gaps))),
                   births_srs_over_gbd=dict(min=min(srs_ratio), max=max(srs_ratio)),
                   india=india, neonatal_period_sepsis_related_per_1000_2021=dict(lowest=states[:3], highest=states[-3:]))
    i2021 = india['2021']
    print(f'[04] Complete; {len(rows):,} rows; India 2021: {i2021["births"]:,} live births (SRS-based {i2021["births_srs"]:,}); '
          f'{i2021["neonatal_period_sepsis_related_per_1000"]} sepsis-related neonatal deaths per 1,000 live births; '
          f'{i2021["maternal_sepsis_related_per_100000"]} sepsis-related maternal deaths per 100,000', flush=True)


if __name__ == '__main__':
    build_rates_per_birth()

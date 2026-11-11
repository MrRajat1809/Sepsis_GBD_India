"""Compare GBD 2023 with the Sample Registration System by State/UT and year or three-year period: crude death rate,
infant mortality rate and maternal mortality ratio, as the ratio GBD / SRS."""
import statistics
from collections import defaultdict

import srs_common as S

HEADER = ['measure', 'srs_unit', 'period', 'gbd_units', 'srs', 'gbd', 'gbd_over_srs']


def srs_values():
    """Return {table: {(state, period): value}} of the printed SRS figures, without markers."""
    out = defaultdict(dict)
    for r in S.read_csv(S.ROOT / S.CONFIG['rbi_tables']):
        text = r['printed'].rstrip(S.CONFIG['combined_marker'])
        if r['printed'] not in S.CONFIG['markers']:
            out[r['table']][(r['state'], r['period'])] = float(text)
    return out


def gbd_inputs():
    """Return GBD 2023 all-cause deaths, population, deaths under one year, live births and maternal deaths by (unit, year)."""
    deaths = {(r['location'], int(r['year'])): float(r['deaths'])
              for r in S.read_csv(S.ROOT / S.CONFIG['estimates_directory'] / 'sepsis_deaths_annual.csv') if r['sex'] == 'Both'}
    population = {(r['location'], int(r['year'])): float(r['population'])
                  for r in S.read_csv(S.ROOT / S.CONFIG['estimates_directory'] / 'rates_annual.csv') if r['sex'] == 'Both'}
    infant = defaultdict(float)
    # Deaths under one year, from Request 5.
    for (location, age, year), v in S.gbd_by_age(S.CONFIG['population_request'], set(S.CONFIG['infant_ages'])).items():
        infant[(location, year)] += v
    # Live births implied by GBD 2023 (neonatal_maternal stage 04) and maternal deaths (stage 03): each GBD rate is GBD's own.
    nm = S.ROOT / S.CONFIG['neonatal_maternal_directory']
    births = {(r['location'], int(r['year'])): float(r['births']) for r in S.read_csv(nm / 'rates_per_birth.csv') if r['births'] != ''}
    maternal = {(r['location'], int(r['year'])): float(r['maternal_deaths']) for r in S.read_csv(nm / 'maternal_annual.csv')
                if r['sex'] == 'Female'}
    return dict(deaths=deaths, population=population, infant=infant, births=births, maternal=maternal)


def units_for(srs_unit, year, rules):
    """Return the GBD units of an SRS State/UT in a year: undivided Andhra Pradesh up to 2013, Jammu & Kashmir with Ladakh."""
    if srs_unit == S.CONFIG['srs_national']:
        return [S.INDIA]
    for rule in rules.get(srs_unit, []):
        if year <= rule['through']:
            return rule['units']
    return [srs_unit]


def annual_rows(srs, gbd, gbd_units):
    """Return the crude death rate and infant mortality rate rows, GBD against SRS, by State/UT and year."""
    rows = []
    for measure, spec in S.CONFIG['annual_measures'].items():
        for (state, year), value in sorted(srs[spec['table']].items()):
            # Small union territories, and Ladakh (counted with Jammu & Kashmir), are not compared.
            if state in S.CONFIG['not_compared']:
                continue
            units = units_for(state, int(year), S.CONFIG['srs_units'])
            S.require(set(units) <= gbd_units | {S.INDIA}, f'{measure}: no GBD unit for {state}')
            y = int(year)
            if measure == 'crude_death_rate':
                estimate = sum(gbd['deaths'][(u, y)] for u in units) / sum(gbd['population'][(u, y)] for u in units) * spec['per']
            else:
                if not all((u, y) in gbd['births'] for u in units):
                    continue
                estimate = sum(gbd['infant'][(u, y)] for u in units) / sum(gbd['births'][(u, y)] for u in units) * spec['per']
            rows.append([measure, state, y, '; '.join(units), value, estimate, estimate / value])
    return rows


def maternal_rows(srs, gbd, gbd_units):
    """Return the maternal mortality ratio rows: GBD maternal deaths over GBD live births in each three-year SRS period."""
    spec = S.CONFIG['maternal_measure']
    periods = S.RAW_CONFIG['rbi_tables']['tables'][spec['table']]['periods']
    rows = []
    for period in periods:
        start = int(period[:4])
        years = range(start, start + 3)
        listed = {s: v for (s, p), v in srs[spec['table']].items() if p == period}
        covered = set()
        groups = {}
        for state in listed:
            if state in (S.CONFIG['srs_national'], spec['others']):
                continue
            # In earlier periods SRS gives some states together with the states later formed from them.
            rules = S.CONFIG['maternal_groups'].get(state, [])
            units = next((r['units'] for r in rules if periods.index(period) <= periods.index(r['through_period'])), [state])
            groups[state] = units
            covered.update(units)
        # SRS 'Others' stands for every unit not listed separately.
        if spec['others'] in listed:
            groups[spec['others']] = sorted(gbd_units - covered)
        groups[S.CONFIG['srs_national']] = [S.INDIA]
        for state, units in sorted(groups.items()):
            S.require(set(units) <= gbd_units | {S.INDIA}, f'MMR {period}: no GBD unit for {state}')
            deaths = sum(gbd['maternal'][(u, y)] for u in units for y in years)
            births = sum(gbd['births'][(u, y)] for u in units for y in years)
            estimate = deaths / births * spec['per']
            rows.append(['maternal_mortality_ratio', state, period, '; '.join(units), listed[state], estimate, estimate / listed[state]])
    return rows


def summarise(rows):
    """Return, by measure and period, India's GBD / SRS ratio, the median state ratio and the rank correlation across states."""
    out = {}
    by = defaultdict(list)
    for r in rows:
        by[(r[0], r[2])].append(r)
    for (measure, period), part in sorted(by.items()):
        states = [r for r in part if r[1] != S.CONFIG['srs_national']]
        india = next((r[6] for r in part if r[1] == S.CONFIG['srs_national']), '')
        ratios = sorted(r[6] for r in states)
        out.setdefault(measure, {})[str(period)] = dict(
            india_gbd_over_srs=india, states=len(states), median_ratio=statistics.median(ratios) if ratios else '',
            rank_correlation=S.spearman([r[4] for r in states], [r[5] for r in states]) if len(states) >= 5 else '')
    return out


def build_comparison():
    srs, gbd = srs_values(), gbd_inputs()
    gbd_units = {u for u, _ in gbd['deaths']} - {S.INDIA}
    rows = annual_rows(srs, gbd, gbd_units) + maternal_rows(srs, gbd, gbd_units)
    S.require(all(r[5] > 0 for r in rows), 'A GBD value is not positive')
    S.write_csv('srs_comparison.csv', HEADER, rows)
    summary = summarise(rows)
    pick = {'crude_death_rate': ('2010', '2019', '2021'), 'infant_mortality_rate': ('2010', '2019', '2021'),
            'maternal_mortality_ratio': ('2010-12', '2017-19', '2019-21')}
    highlights = {m: {p: summary[m][p] for p in ps if p in summary[m]} for m, ps in pick.items()}
    S.write_report('01_srs_comparison.json', __file__, dict(rows=len(rows), measures=len(summary)), status='PASSED',
                   by_period=summary, highlights=highlights)
    h = highlights
    print(f'[01] Complete; {len(rows)} comparisons; India GBD/SRS 2019: crude death rate '
          f'{h["crude_death_rate"]["2019"]["india_gbd_over_srs"]:.2f}, infant mortality '
          f'{h["infant_mortality_rate"]["2019"]["india_gbd_over_srs"]:.2f}; maternal mortality 2017-19 '
          f'{h["maternal_mortality_ratio"]["2017-19"]["india_gbd_over_srs"]:.2f}', flush=True)


if __name__ == '__main__':
    build_comparison()

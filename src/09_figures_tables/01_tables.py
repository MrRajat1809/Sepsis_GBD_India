"""Write the paper's main (Table1-3) and supplementary (SuppTable1-8) tables as CSV and LaTeX from the analysis outputs."""
import json
import statistics
from collections import defaultdict

import figures_common as F

YEARS = F.CONFIG['years']['tables']
PROJECTION = F.CONFIG['projection_from']


def ordered(locations):
    return [F.INDIA] + sorted(l for l in locations if l != F.INDIA)


def year_label(y):
    return f'{y} (projected)' if y >= PROJECTION else str(y)


def deaths_and_rates():
    """Write Table1 (deaths) and Table2 (age-standardised rates) by state with 95% UIs; return the files and location count."""
    ui = {(r['location'], int(r['year']), r['measure']): r for r in F.read_csv('state_estimates', 'uncertainty_annual.csv')
          if r['sex'] == 'Both' and r['measure'] in ('sepsis_deaths', 'age_standardised_rate')}
    locations = ordered({k[0] for k in ui})
    tables = {}
    for measure, stem, caption, scale, unit in (
            ('sepsis_deaths', 'Table1', 'Sepsis-related deaths (thousands, 95% uncertainty interval) by state', 1000, 'thousands'),
            ('age_standardised_rate', 'Table2', 'Age-standardised sepsis-related death rate per 100,000 (95% uncertainty interval) by state',
             1, 'per 100,000')):
        rows = []
        for location in locations:
            cells = [F.with_interval(float(ui[(location, y, measure)]['val']), float(ui[(location, y, measure)]['lower']),
                                     float(ui[(location, y, measure)]['upper']), scale) for y in YEARS]
            change = 100 * (float(ui[(location, YEARS[-1], measure)]['val']) / float(ui[(location, YEARS[0], measure)]['val']) - 1)
            rows.append([location, *cells, f'{change:.1f}'])
        header = ['Location', *(year_label(y) for y in YEARS), f'Change {YEARS[0]}-{YEARS[-1]} (%)']
        tables.update(F.write_table(stem, caption, header, rows,
                                    note=f'Estimates for {PROJECTION} onwards hold the sepsis-related fractions and the national factor at '
                                         'their 2021 values. India is the sum '
                                         'of its 31 units; its intervals come from its own GBD estimates, which carry the correlation between '
                                         'states. State intervals ignore correlations between inputs and are approximate.'))
    return tables, len(locations)


def leading_causes():
    """Write SuppTable8: each state's leading underlying causes of sepsis-related deaths, with their share of its total."""
    year, top = F.CONFIG['years']['leading_causes'], F.CONFIG['leading_causes_top']
    by = defaultdict(list)
    for r in F.read_csv('state_estimates', 'estimates_annual.csv'):
        if r['sex'] == 'Both' and int(r['year']) == year and float(r['sepsis_deaths']) > 0:
            by[r['location']].append((float(r['sepsis_deaths']), r['cause']))
    rows = []
    for location in ordered(by):
        total = sum(v for v, _ in by[location])
        leading = sorted(by[location], reverse=True)[:top]
        rows.append([location, F.thousands(total), *(f'{c} ({100 * v / total:.1f}%)' for v, c in leading)])
    header = ['Location', 'Sepsis-related deaths (thousands)', *(f'Cause {i + 1} (share)' for i in range(top))]
    return F.write_table('SuppTable8', f'Leading underlying causes of sepsis-related deaths by state, {year}', header, rows,
                         note=f'{year} is the last year before the COVID-19 pandemic. Shares are of all sepsis-related deaths in the state.')


def neonatal_maternal():
    """Write Table3: neonatal and maternal sepsis deaths by state, as underlying causes and sepsis-related, and per live birth."""
    year = F.CONFIG['years']['neonatal_maternal'][-1]
    underlying = {(r['location'], r['sex'], r['cause']): r for r in F.read_csv('neonatal_maternal', 'underlying_annual.csv')
                  if int(r['year']) == year}
    period = {r['location']: r for r in F.read_csv('neonatal_maternal', 'neonatal_period.csv')
              if int(r['year']) == year and r['age_group'] == '0-27 days'}
    births = {r['location']: r for r in F.read_csv('neonatal_maternal', 'rates_per_birth.csv') if int(r['year']) == year}
    maternal = {r['location']: r for r in F.read_csv('neonatal_maternal', 'maternal_annual.csv') if int(r['year']) == year and r['sex'] == 'Female'}
    ns, ms = 'Neonatal sepsis and other neonatal infections', 'Maternal sepsis and other maternal infections'
    rate = lambda location, column, digits: f'{float(births[location][column]):.{digits}f}' if births[location][column] != '' else 'not estimated'
    rows = []
    for location in ordered(period):
        n, m = underlying[(location, 'Both', ns)], underlying[(location, 'Female', ms)]
        rows.append([location, F.with_interval(float(n['deaths']), float(n['deaths_lower']), float(n['deaths_upper']), 1, 0),
                     f'{float(period[location]["sepsis_related"]):,.0f}', rate(location, 'neonatal_period_sepsis_related_per_1000', 2),
                     F.with_interval(float(m['deaths']), float(m['deaths_lower']), float(m['deaths_upper']), 1, 0),
                     f'{float(maternal[location]["sepsis_related"]):,.0f}', rate(location, 'maternal_sepsis_related_per_100000', 1)])
    header = ['Location', 'Neonatal sepsis deaths (95% UI)', 'Sepsis-related deaths, first 28 days',
              'Per 1,000 live births', 'Maternal sepsis deaths (95% UI)', 'Sepsis-related maternal deaths', 'Per 100,000 live births']
    return F.write_table('Table3', f'Neonatal and maternal sepsis by state, {year}', header, rows,
                         note='Neonatal and maternal sepsis are underlying causes (GBD 2023). Sepsis-related deaths add the sepsis-related '
                              'fraction of other neonatal or maternal disorders and, in the first 28 days, other infections. Live births are '
                              'those implied by GBD 2023 (population and deaths in the first week of life).')


def sensitivity():
    """Write SuppTable1: deaths under each sensitivity analysis relative to the main estimates, for India and across states."""
    rows_in = F.read_csv('state_estimates', 'sensitivity.csv')
    names = {'no_scaling': 'No national factor (k = 1)', 'nearest_benchmark_shares': 'Fractions from the nearest benchmark year',
             'gbd2021_round': 'GBD 2021 round (benchmark years)', 'without_covid19': 'Without COVID-19',
             'haq_derived': 'Fractions varying with HAQ, derived slope',
             'haq_odds_ratio_0.75': 'Fractions varying with HAQ, odds ratio 0.75 per 10 points',
             'haq_odds_ratio_1.25': 'Fractions varying with HAQ, odds ratio 1.25 per 10 points',
             'projection_shares_x0.9': 'Projected years: non-infectious fractions 10% lower',
             'projection_shares_x1.1': 'Projected years: non-infectious fractions 10% higher',
             'projection_2019_shares': 'Projected years: pre-pandemic (2019) fractions and k'}
    rows = []
    for analysis, label in names.items():
        part = [r for r in rows_in if r['analysis'] == analysis and r['sex'] == 'Both' and r['measure'] == 'sepsis_deaths']
        for year in (2019, 2021, 2023):
            cells = [r for r in part if int(r['year']) == year]
            if not cells:
                continue
            india = next(float(r['ratio']) for r in cells if r['location'] == F.INDIA)
            states = [float(r['ratio']) for r in cells if r['location'] != F.INDIA]
            rows.append([label, year_label(year), f'{india:.3f}', f'{min(states):.3f}', f'{max(states):.3f}'])
    header = ['Analysis', 'Year', 'India (alternative / main)', 'States, lowest', 'States, highest']
    return F.write_table('SuppTable1', 'Sensitivity analyses: sepsis-related deaths relative to the main estimates', header, rows,
                         note='Ratios of the alternative estimate to the main estimate. The GBD 2021 round is compared in its benchmark years only. '
                              'The projected-year analyses change only 2022-2023, where the main estimates hold the 2021 fractions and k.')


def visibility():
    """Write SuppTable2: visibility of sepsis in death certification (MCCD) by state, 2019 and 2021."""
    india_row = F.CONFIG['visibility_rows']['india']
    rows_in = [r for r in F.read_csv('mccd_visibility', 'visibility.csv') if int(r['year']) in (2019, 2021)]
    pct = lambda v, d=1: f'{100 * float(v):.{d}f}' if v != '' else ''
    rows = []
    for location in [india_row] + sorted({r['unit'] for r in rows_in if not r['unit'].startswith(F.INDIA)}):
        for r in [r for r in rows_in if r['unit'] == location]:
            # A unit none of whose States/UTs reported has zeros in visibility.csv, which are not reported values.
            if r['complete'] != '1' and float(r['registered'] or 0) == 0:
                rows.append([location, r['year'], 'no', 'not reported', '', '', '', '', ''])
                continue
            rows.append([F.INDIA if location == india_row else location, r['year'], 'yes' if r['complete'] == '1' else 'no',
                         f'{int(r["septicaemia"]):,}' if r['septicaemia'] else '', pct(r['visibility_count'], 2),
                         f'{float(r["visibility_share"]):.3f}' if r['visibility_share'] else '', pct(r['certification_coverage']),
                         f'{float(r["registration_completeness"]):.2f}' if r['registration_completeness'] else '', pct(r['ill_defined_share'])])
    header = ['Location', 'Year', 'All member States/UTs reported', 'MCCD septicaemia deaths', 'Count ratio (%)', 'Share ratio',
              'Certification coverage (%)', 'Registered / estimated deaths', 'Ill-defined causes (% of certified)']
    return F.write_table('SuppTable2', 'Visibility of sepsis in death certification by state, 2019 and 2021', header, rows,
                         note='Count ratio: MCCD septicaemia deaths / estimated sepsis-related deaths. Share ratio: septicaemia share of certified '
                              'deaths / sepsis-related share of all deaths. Certification coverage: certified / registered deaths. India: the units '
                              'that reported. These ratios describe how often septicaemia is certified as the underlying cause, not under-reporting; '
                              'GBD treats septicaemia as an intermediate cause (a garbage code), so a higher ratio is not better certification. '
                              'Registration and MCCD count deaths where they occur and GBD where people lived: where registered deaths exceed '
                              'the estimate, the unit probably registers deaths of residents of other states.')


def economic():
    """Write SuppTable3: years of life lost to sepsis-related deaths and their value at per-capita NSDP."""
    rows_in = F.read_csv('economic_loss', 'value_of_ylls.csv')
    rows = []
    for location in ordered({r['unit'] for r in rows_in}):
        for r in [r for r in rows_in if r['unit'] == location]:
            year = int(r['year'])
            rows.append([location, f'{year}*' if year >= PROJECTION else str(year), f'{float(r["sepsis_ylls"]) / 1e6:.2f}',
                         f'{100 * float(r["sepsis_share_of_ylls"]):.1f}', f'{float(r["sepsis_ylls_per_100000"]):,.0f}',
                         f'{float(r["value_current_crore"]) / 1000:,.1f}', f'{float(r["value_current_crore_undiscounted"]) / 1000:,.1f}',
                         'partial' if r['income_coverage'].startswith('partial') else ''])
    rate = f'{100 * float(rows_in[0]["discount_rate"]):g}'
    header = ['Location', 'Year', 'Sepsis-related YLLs (millions)', 'Share of all YLLs (%)', 'YLLs per 100,000',
              f'Value at {rate}% discount (Rs thousand crore)', 'Value undiscounted (Rs thousand crore)', 'State accounts']
    return F.write_table('SuppTable3', 'Years of life lost to sepsis-related deaths and their value at per-capita NSDP', header, rows,
                         note=f'* Projected. Income-based valuation at current prices: each future year of life lost is discounted at {rate}% a year and valued '
                              'at the per-capita NSDP of the year of death, without income growth. Partial: Other Union Territories (members '
                              'outside the state accounts) and Jammu & Kashmir and Ladakh (Ladakh missing in some years).')


def srs():
    """Write SuppTable4: GBD 2023 compared with the Sample Registration System, for India and the median state."""
    rows_in = F.read_csv('srs_comparison', 'srs_comparison.csv')
    # Rank correlations across states come from the SRS comparison stage, for every year or period it compared.
    rho = json.loads((F.ROOT / F.CONFIG['directories']['srs_report'] / '01_srs_comparison.json').read_text(encoding='utf-8'))['by_period']
    rho = {m: {p: v['rank_correlation'] for p, v in periods.items()} for m, periods in rho.items()}
    names = {'crude_death_rate': 'Crude death rate (per 1,000)', 'infant_mortality_rate': 'Infant mortality rate (per 1,000 live births)',
             'maternal_mortality_ratio': 'Maternal mortality ratio (per 100,000 live births)'}
    rows = []
    for measure, label in names.items():
        part = [r for r in rows_in if r['measure'] == measure]
        periods = list(dict.fromkeys(r['period'] for r in part))
        # The annual measures keep selected years; the maternal mortality ratio keeps all its multi-year periods.
        if measure != 'maternal_mortality_ratio':
            periods = [p for p in periods if int(p) in (2004, 2010, 2015, 2019, 2021, 2023)]
        for period in periods:
            cells = [r for r in part if r['period'] == period]
            india = next(r for r in cells if r['srs_unit'] == 'ALL INDIA')
            ratios = sorted(float(r['gbd_over_srs']) for r in cells if r['srs_unit'] != 'ALL INDIA')
            rows.append([label, period, f'{float(india["srs"]):.1f}', f'{float(india["gbd"]):.1f}', f'{float(india["gbd_over_srs"]):.2f}',
                         f'{statistics.median(ratios):.2f}', f'{rho[measure][period]:.2f}' if rho[measure][period] != '' else '',
                         len(ratios)])
    # The table shows selected years of the annual measures; the note gives their range over every year.
    spans = {}
    for measure in ('crude_death_rate', 'infant_mortality_rate'):
        values = [v for v in rho[measure].values() if v != '']
        spans[measure] = f'{min(values):.2f}-{max(values):.2f}'
    years = sorted(int(p) for p in rho['crude_death_rate'])
    header = ['Measure', 'Year or period', 'SRS, India', 'GBD 2023, India', 'GBD / SRS, India', 'GBD / SRS, median of states',
              'Rank correlation of states', 'States']
    return F.write_table('SuppTable4', 'GBD 2023 compared with the Sample Registration System', header, rows,
                         note='GBD values use the live births implied by GBD 2023, so each is GBD\'s own rate; states are grouped as in SRS. '
                              'Rank correlation: Spearman, between the SRS and GBD values of the states. Over every year '
                              f'{years[0]}-{years[-1]} it was {spans["crude_death_rate"]} for the crude death rate and '
                              f'{spans["infant_mortality_rate"]} for the infant mortality rate.')


def decomposition():
    """Write SuppTable5: the change in sepsis-related deaths split into population growth, age structure and rate change."""
    start, end = F.CONFIG['years']['decomposition']
    rows_in = [r for r in F.read_csv('state_estimates', 'decomposition.csv') if int(r['start']) == start and int(r['end']) == end]
    pct = lambda r, k: f'{100 * float(r[k]) / float(r["deaths_start"]):.1f}'
    rows = [[r['location'], F.thousands(float(r['deaths_start'])), F.thousands(float(r['deaths_end'])), pct(r, 'change'),
             pct(r, 'population_growth'), pct(r, 'age_structure'), pct(r, 'rate_change'), pct(r, 'rate_infectious'),
             pct(r, 'rate_non_infectious')] for r in sorted(rows_in, key=lambda r: (r['location'] != F.INDIA, r['location']))]
    header = ['Location', f'Deaths {start} (thousands)', f'Deaths {end} (thousands)', 'Change (%)', 'Population growth (%)',
              'Age structure (%)', 'Rate change (%)', 'Rate change, infectious (%)', 'Rate change, non-infectious (%)']
    return F.write_table('SuppTable5', f'Decomposition of the change in sepsis-related deaths, {start}-{end}', header, rows,
                         note=f'Percentages of the {start} deaths (Das Gupta). {end} rests on projected fractions.')


def microbe_syndromes():
    """Write SuppTable6: India's infection-related deaths by infectious syndrome and antimicrobial resistance (IHME MICROBE)."""
    rows_in = F.read_csv('raw_data', 'microbe.csv')
    resistance = {(r['infectious_syndrome'], r['counterfactual']): r for r in rows_in if r['view'] == 'amr_by_resistance'}
    deaths = lambda r: F.with_interval(float(r['deaths']), float(r['deaths_lower']), float(r['deaths_upper']), 1000, 1)
    syndromes = sorted((r for r in rows_in if r['view'] == 'syndromes'), key=lambda r: -float(r['deaths']))
    rows = []
    for r in syndromes:
        cells = [deaths(resistance[(r['infectious_syndrome'], c)]) if (r['infectious_syndrome'], c) in resistance else 'not assessed'
                 for c in ('Associated', 'Attributable')]
        rows.append([r['infectious_syndrome'], deaths(r), f'{float(r["rate"]):.1f}', *cells])
    totals = [sum(float(r['deaths']) for r in syndromes)]
    totals += [sum(float(r['deaths']) for (s, c), r in resistance.items() if c == counterfactual)
               for counterfactual in ('Associated', 'Attributable')]
    rows.append(['All infectious syndromes', F.thousands(totals[0]), '', F.thousands(totals[1]), F.thousands(totals[2])])
    header = ['Infectious syndrome', 'Deaths (thousands, 95% UI)', 'Deaths per 100,000', 'Associated with resistance (thousands, 95% UI)',
              'Attributable to resistance (thousands, 95% UI)']
    return F.write_table('SuppTable6', 'Infection-related deaths by infectious syndrome and bacterial antimicrobial resistance, India, 2021', header,
                         rows, note='IHME MICROBE tool (GBD 2021), taken as published. Resistance is assessed for bacterial syndromes only; '
                                    'totals of intervals are not shown because they cannot be added.')


def microbe_pathogens():
    """Write SuppTable7: India's infection-related deaths by pathogen (IHME MICROBE)."""
    rows_in = sorted((r for r in F.read_csv('raw_data', 'microbe.csv') if r['view'] == 'pathogens'), key=lambda r: -float(r['deaths']))
    rows = [[r['pathogen'], r['pathogen_type'], F.with_interval(float(r['deaths']), float(r['deaths_lower']), float(r['deaths_upper']), 1000, 1),
             f'{float(r["rate"]):.2f}'] for r in rows_in]
    header = ['Pathogen', 'Type', 'Deaths (thousands, 95% UI)', 'Deaths per 100,000']
    return F.write_table('SuppTable7', 'Infection-related deaths by pathogen, India, 2021', header, rows,
                         note='IHME MICROBE tool (GBD 2021), all infectious syndromes, taken as published.')


def build_tables():
    files = {}
    main, locations = deaths_and_rates()
    files.update(main)
    for build in (leading_causes, neonatal_maternal, sensitivity, visibility, economic, srs, decomposition, microbe_syndromes, microbe_pathogens):
        files.update(build())
    inputs = [('state_estimates', f) for f in ('uncertainty_annual.csv', 'estimates_annual.csv', 'sensitivity.csv', 'decomposition.csv')]
    inputs += [('neonatal_maternal', f) for f in ('underlying_annual.csv', 'neonatal_period.csv', 'rates_per_birth.csv', 'maternal_annual.csv')]
    inputs += [('mccd_visibility', 'visibility.csv'), ('economic_loss', 'value_of_ylls.csv'), ('srs_comparison', 'srs_comparison.csv')]
    inputs += [('raw_data', 'microbe.csv'), ('srs_report', '01_srs_comparison.json')]
    F.write_report('01_tables.json', __file__, dict(tables=len(files) // 2, locations=locations), inputs=inputs, files=files)
    main_tables = sum(1 for f in files if f.startswith('Table') and f.endswith('.csv'))
    print(f'[01] Complete; {len(files) // 2} tables ({main_tables} main, {len(files) // 2 - main_tables} supplementary) as CSV and LaTeX',
          flush=True)


if __name__ == '__main__':
    build_tables()

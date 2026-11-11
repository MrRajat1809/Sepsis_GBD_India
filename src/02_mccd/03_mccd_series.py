"""Build the State/UT-year septicaemia series, 2008-2023, with certification coverage, from the extracted MCCD tables."""
import mccd_common as M

ALL = M.CONFIG['all_india']
FIELDS = ['year', 'state', 'septicaemia_total', 'septicaemia_male', 'septicaemia_female',
          'certified_infectious_A00-B99', 'certified_ill_defined_R00-R99', 'certified_all_causes',
          'registered_deaths', 'registered_source_report', 'pct_registered_deaths_certified',
          'pct_certified_deaths_septicaemia']


def build_series():
    t4 = {(int(r['year']), r['state'], r['sex'], r['cause']): int(r['certified_deaths'])
          for r in M.read_csv('table4_by_state.csv') if r['certified_deaths'] != ''}
    # Each report repeats the two previous years and occasionally corrects them, so the latest report is kept.
    registered = {}
    for r in M.read_csv('table1_coverage.csv'):
        if r['registered_deaths'] == '':
            continue
        key = (int(r['data_year']), r['state'])
        if key not in registered or int(r['report_year']) > registered[key][0]:
            registered[key] = (int(r['report_year']), int(float(r['registered_deaths'])))
    # India's registered deaths are those of the MCCD-reporting States/UTs, as in the reports' own coverage figures
    # (2019: 1,571,540 / 7,596,849 = 20.7%).
    alias = {ALL: M.CONFIG['india_mccd_reporting']}
    rows = []
    for year, state in sorted({(y, s) for (y, s, _, _) in t4}):
        get = lambda sex, cause: t4.get((year, state, sex, cause))
        septicaemia, certified = get('Total', 'septicaemia_A40-A41'), get('Total', 'all_causes')
        reg = registered.get((year, alias.get(state, state)))
        rows.append([year, state, septicaemia, get('Male', 'septicaemia_A40-A41'), get('Female', 'septicaemia_A40-A41'),
                     get('Total', 'infectious_parasitic_A00-B99'), get('Total', 'ill_defined_R00-R99'), certified,
                     reg[1] if reg else None, reg[0] if reg else None,
                     round(100 * certified / reg[1], 2) if reg and reg[1] and certified is not None else None,
                     round(100 * septicaemia / certified, 2) if certified else None])
    M.write_csv('septicaemia_state_year.csv', FIELDS, [['' if v is None else v for v in row] for row in rows])
    india = {r[0]: dict(septicaemia=r[2], certified=r[7], pct_certified=r[10], pct_septicaemia=r[11])
             for r in rows if r[1] == ALL}
    M.write_report('03_series.json', __file__, dict(state_years=len(rows), states=len({r[1] for r in rows})), india=india)
    print(f'[03] Complete; {len(rows):,} State/UT-years', flush=True)


if __name__ == '__main__':
    build_series()

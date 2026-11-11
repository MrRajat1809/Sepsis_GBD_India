"""Sum the MCCD States/UTs into the units compared with the GBD estimates, year by year: Jammu & Kashmir with Ladakh, the
smaller union territories as Other Union Territories, and Andhra Pradesh with Telangana up to the year of the split."""
from collections import defaultdict

import visibility_common as V

FIELDS = {'septicaemia': 'septicaemia_total', 'septicaemia_male': 'septicaemia_male', 'septicaemia_female': 'septicaemia_female',
          'infectious_A00_B99': 'certified_infectious_A00-B99', 'ill_defined_R00_R99': 'certified_ill_defined_R00-R99',
          'certified': 'certified_all_causes', 'registered': 'registered_deaths'}
HEADER = ['unit', 'year', 'members_expected', 'members_reporting', 'complete', *FIELDS]


def total(rows, column):
    """Return the sum of a column over member rows, or '' when any member has no value (as for registered deaths)."""
    values = [r[column] for r in rows]
    return '' if any(v == '' for v in values) else sum(int(float(v)) for v in values)


def build_units():
    series = V.read_csv('septicaemia_state_year.csv', V.MCCD)
    gbd_units = sorted({r['location'] for r in V.read_csv('sepsis_deaths_annual.csv', V.ESTIMATES)} - {V.INDIA})
    by_year = defaultdict(dict)
    for r in series:
        by_year[int(r['year'])][r['state']] = r
    rows, checks, ignored = [], {}, []
    for year in sorted(by_year):
        states, used, complete = by_year[year], set(), []
        for unit in sorted({V.unit_of(u, year) for u in gbd_units}):
            expected = V.members(unit, year)
            present = [states[m] for m in expected if m in states]
            used.update(m for m in expected if m in states)
            # A unit-year is complete when every member State/UT reported.
            complete.append(len(present) == len(expected))
            rows.append([unit, year, len(expected), len(present), int(complete[-1]), *(total(present, c) for c in FIELDS.values())])
        # India takes the all-India MCCD figures, which cover the reporting States/UTs only.
        india = states[V.CONFIG['mccd_india']]
        rows.append([V.INDIA, year, '', len(used), int(all(complete)), *(total([india], c) for c in FIELDS.values())])
        # Every MCCD State/UT must fall in a unit; only the configured all-zero rows may be left over.
        left = set(states) - used - {V.CONFIG['mccd_india']}
        for name in sorted(left):
            allowed = year in V.CONFIG['zero_rows_ignored'].get(name, [])
            V.require(allowed and all(states[name][c] in ('0', '') for c in FIELDS.values()),
                      f'{year}: MCCD State/UT {name} is not assigned to any unit')
            ignored.append(f'{name} {year}')
        # The units must add up exactly to the all-India figures (rows[-1]).
        part = [r for r in rows if r[1] == year and r[0] != V.INDIA]
        for column in ('septicaemia', 'certified', 'infectious_A00_B99', 'ill_defined_R00_R99'):
            i = HEADER.index(column)
            V.require(sum(r[i] for r in part if r[i] != '') == rows[-1][i], f'{year}: units do not add up to India for {column}')
    checks['units_add_up_to_india'] = len(by_year)
    V.write_csv('mccd_units.csv', HEADER, rows)
    incomplete = [f'{r[0]} {r[1]}' for r in rows if r[0] != V.INDIA and not r[4]]
    summary = dict(years=f'{min(by_year)}-{max(by_year)}', rows=len(rows), incomplete_unit_years=len(incomplete))
    V.write_report('01_mccd_units.json', __file__, summary, status='PASSED', checks=checks, incomplete=incomplete,
                   zero_rows_ignored=ignored)
    print(f'[01] Complete; {len(rows)} unit-years from {len(by_year)} MCCD reports; {len(incomplete)} unit-years with a '
          f'member State/UT not reporting', flush=True)


if __name__ == '__main__':
    build_units()

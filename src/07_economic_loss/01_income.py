"""Net state domestic product, total and per capita, by GBD unit and calendar year at current and constant prices, from
the financial-year figures of the RBI Handbook tables (National Statistical Office); India is the sum of the units."""
import economic_common as C

HEADER = ['unit', 'year', 'prices', 'per_capita_nsdp', 'nsdp_crore', 'implied_population', 'income_coverage', 'members_used']


def printed_values():
    """Return {(table, state, financial year): value} of the printed NSDP figures, without markers."""
    tables = {name for spec in C.CONFIG['prices'].values() for name in spec.values()}
    directory, filename = C.CONFIG['rbi_tables'].rsplit('/', 1)
    return {(r['table'], r['state'], r['period']): float(r['printed']) for r in C.read_csv(filename, C.ROOT / directory)
            if r['table'] in tables and r['printed'] not in C.CONFIG['markers']}


def rule_for(unit, fiscal):
    """Return the member rule of a unit for a financial year; a unit without rules is its own only member."""
    rules = C.CONFIG['unit_members'].get(unit, [{'from_fiscal': 0, 'to_fiscal': 9999, 'members': [unit]}])
    return next(r for r in rules if r['from_fiscal'] <= fiscal <= r['to_fiscal'])


def fiscal_value(values, prices, unit, fiscal):
    """Return (total in rupees lakh, implied population, coverage, members used) for one unit and financial year, or None."""
    spec, label = C.CONFIG['prices'][prices], C.fiscal_label(fiscal)
    rule = rule_for(unit, fiscal)
    found = [m for m in rule['members'] if (spec['total'], m, label) in values and (spec['per_capita'], m, label) in values]
    if not found:
        return None
    total = sum(values[(spec['total'], m, label)] for m in found)
    # Combined units add up the product and the implied population (product / per-capita product) of their members.
    population = sum(values[(spec['total'], m, label)] * C.CONFIG['rupees_per_lakh'] / values[(spec['per_capita'], m, label)]
                     for m in found)
    # Other Union Territories lack the members outside the state accounts; Ladakh has no constant-price figures from 2019-20.
    missing = [m for m in rule['members'] if m not in found] + rule.get('not_in_state_accounts', [])
    return total, population, 'complete' if not missing else 'partial, without ' + ', '.join(missing), found


def build_income():
    values = printed_values()
    units = sorted({r['location'] for r in C.read_csv('sepsis_deaths_annual.csv', C.ESTIMATES)} - {C.INDIA})
    states = {s for _, s, _ in values}
    single = [u for u in units if u not in C.CONFIG['unit_members']]
    C.require(set(single) <= states, f'Units missing from the state accounts: {sorted(set(single) - states)}')
    first, last = C.CONFIG['fiscal_years']
    # A calendar year takes a quarter of the financial year ending in it and three quarters of the one starting in it.
    w = C.CONFIG['calendar_weights']
    rows, partial, single = [], set(), set()
    for prices in C.CONFIG['prices']:
        for year in range(first + 1, last + 1):
            india_total = india_population = 0.0
            for unit in units:
                a, b = fiscal_value(values, prices, unit, year - 1), fiscal_value(values, prices, unit, year)
                if a is None and b is None:
                    continue
                if a is None or b is None:
                    # Only one of the two financial years is published: it is used alone and the coverage says so.
                    only, label = (b, C.fiscal_label(year)) if a is None else (a, C.fiscal_label(year - 1))
                    total, population = only[0], only[1]
                    coverage = (only[2] if only[2] != 'complete' else 'complete') + f'; financial year {label} only'
                    a = b = only
                else:
                    total = w['previous_fiscal'] * a[0] + w['same_fiscal'] * b[0]
                    population = w['previous_fiscal'] * a[1] + w['same_fiscal'] * b[1]
                    coverage = a[2] if a[2] != 'complete' else b[2]
                if coverage.startswith('partial'):
                    partial.add(f'{unit} ({prices})')
                if 'only' in coverage:
                    single.add(f'{unit} {year} ({prices})')
                members = sorted(set(a[3]) | set(b[3]))
                rows.append([unit, year, prices, total * C.CONFIG['rupees_per_lakh'] / population,
                             total * C.CONFIG['rupees_per_lakh'] / C.CONFIG['rupees_per_crore'], population, coverage, '; '.join(members)])
                india_total += total
                india_population += population
            rows.append([C.INDIA, year, prices, india_total * C.CONFIG['rupees_per_lakh'] / india_population,
                         india_total * C.CONFIG['rupees_per_lakh'] / C.CONFIG['rupees_per_crore'], india_population,
                         'sum of the units in the state accounts', ''])
    C.require(all(r[3] > 0 and r[4] > 0 for r in rows), 'A unit has no product')
    covered = {(r[0], r[1], r[2]) for r in rows}
    gaps = sorted(f'{u} {y} {p}' for u in units for y in range(first + 1, last + 1) for p in C.CONFIG['prices'] if (u, y, p) not in covered)
    C.write_csv('income_by_unit.csv', HEADER, rows)
    india = {f'{r[1]} {r[2]}': dict(per_capita_nsdp=round(r[3]), nsdp_crore=round(r[4])) for r in rows
             if r[0] == C.INDIA and r[1] in C.CONFIG['valuation_years']}
    summary = dict(rows=len(rows), years=f'{first + 1}-{last}')
    C.write_report('01_income.json', __file__, summary, status='PASSED', partial_coverage=sorted(partial), one_financial_year_only=sorted(single),
                   unit_years_without_product=gaps, india=india)
    current = india[f'{C.CONFIG["valuation_years"][-1]} current']
    print(f'[01] Complete; {len(rows)} unit-years; India {C.CONFIG["valuation_years"][-1]}: per-capita NSDP Rs '
          f'{current["per_capita_nsdp"]:,} at current prices; {len(gaps)} unit-years without product', flush=True)


if __name__ == '__main__':
    build_income()

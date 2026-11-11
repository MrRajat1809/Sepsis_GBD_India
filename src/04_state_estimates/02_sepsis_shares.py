"""Divide Table S10 sepsis-related deaths by GBD 2021 global deaths for each non-infectious cause, age band and benchmark year."""
from collections import defaultdict

import estimates_common as E

HEADER = ['share_group', 'age_band', 'year', 'sepsis_deaths', 'sepsis_lower', 'sepsis_upper', 'printed', 'global_deaths', 'share']


def half_unit(text):
    """Return half the last printed unit of a Table S10 count (printed to 3 significant figures)."""
    return 0.5 * 10 ** max(len(text) - 3, 0)


def build_shares():
    gbd2021 = E.cause_map('gbd2021')
    groups = {r['share_group']: r['less'] for r in gbd2021.values() if r['component'] == E.NON_INFECTIOUS}
    s10 = defaultdict(list)
    total = {}
    for r in E.read_csv('table_s10.csv', E.APPENDIX):
        if r['metric'] != 'Number':
            continue
        if r['cause_level'] == '3' and r['cause_type'] == 'Non-Infectious':
            s10[(r['cause'], r['age_group'], int(r['year']))].append(r)
        if r['cause'] == 'Non-infectious diseases':
            total[(r['age_group'], int(r['year']))] = r['val']
    deaths = E.results(E.CONFIG['requests']['gbd2021'], ('age_name', 'cause_name', 'year'), measure=E.CONFIG['deaths'],
                       locations={E.CONFIG['global']})
    rows, exceed, numerators = [], [], defaultdict(list)
    for group, less in sorted(groups.items()):
        names = E.CONFIG['share_pools'].get(group, [group])
        for band, ages in E.BANDS.items():
            for year in E.BENCHMARKS:
                printed = [r for n in names for r in s10.get((n, band, year), [])]
                value = sum(float(r['val']) for r in printed)
                denominator = sum(E.adjusted(deaths, group, less, lambda c: (a, c, year)) for a in ages)
                E.require(denominator > 0 or value == 0, f'{group} {band} {year}: sepsis deaths {value} without GBD 2021 deaths')
                # Sepsis-related deaths may exceed all deaths from the cause only by rounding and tolerance.
                allowed = sum(half_unit(r['val']) for r in printed) + E.TOL['relative'] * denominator + E.TOL['absolute_deaths']
                if value - denominator > allowed:
                    exceed.append((group, band, year, value, denominator))
                numerators[(band, year)].extend(r['val'] for r in printed)
                rows.append([group, band, year, value, sum(float(r['lower']) for r in printed),
                             sum(float(r['upper']) for r in printed), int(bool(printed)), denominator,
                             value / denominator if denominator > 0 else 0.0])
    E.require(not exceed, f'Table S10 deaths exceed GBD 2021 deaths: {exceed[:3]}')
    # The causes with shares must add up to Table S10's non-infectious total, so that no printed sepsis death is left out.
    gaps = {}
    for (band, year), parts in sorted(numerators.items()):
        gap = abs(sum(map(float, parts)) - float(total[(band, year)]))
        bound = sum(map(half_unit, parts)) + half_unit(total[(band, year)])
        E.require(gap <= bound, f'{band} {year}: shared causes add up to {sum(map(float, parts)):,.0f}, '
                  f'Table S10 non-infectious total {total[(band, year)]}')
        gaps[f'{band} {year}'] = gap / bound
    E.write_csv('sepsis_shares.csv', HEADER, rows)
    shares = [r[-1] for r in rows if r[6]]
    # A band without a Table S10 row has a share of 0; the report gives the global deaths in such bands.
    unprinted = defaultdict(float)
    for r in rows:
        if not r[6]:
            unprinted[r[2]] += r[7]
    summary = dict(share_groups=len(groups), rows=len(rows), largest_share=max(shares))
    E.write_report('02_sepsis_shares.json', __file__, summary, status='PASSED',
                   checks=dict(shares_within_one=dict(n=len(rows), exceed=0),
                               shared_causes_to_table_s10_total=dict(n=len(gaps), max_gap_over_bound=max(gaps.values()))),
                   global_deaths_in_bands_without_a_row={str(y): round(v) for y, v in sorted(unprinted.items())})
    print(f'[02] Complete; {len(rows):,} shares for {len(groups)} non-infectious causes, 7 age bands and '
          f'{len(E.BENCHMARKS)} years; largest {max(shares):.3f}', flush=True)


if __name__ == '__main__':
    build_shares()

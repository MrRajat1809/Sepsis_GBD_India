"""Compare the GBD 2023 estimates with the GBD 2021-round estimates by state in the benchmark years."""
from collections import defaultdict

import estimates_common as E

HEADER = ['location', 'year', 'component', 'gbd2021', 'gbd2023', 'ratio']
COMPONENTS = {'infectious': E.INFECTIOUS, 'non_infectious': E.NON_INFECTIOUS}


def compare_rounds():
    gbd2021 = defaultdict(float)
    for r in E.read_csv('gbd2021_benchmark.csv'):
        for column in (*COMPONENTS, 'sepsis_deaths'):
            gbd2021[(r['location'], int(r['year']), column)] += float(r[column])
    gbd2023 = defaultdict(float)
    for r in E.read_csv('estimates_by_age.csv'):
        if int(r['year']) in E.BENCHMARKS:
            for column, component in COMPONENTS.items():
                if r['component'] == component:
                    gbd2023[(r['location'], int(r['year']), column)] += float(r['sepsis_deaths'])
            gbd2023[(r['location'], int(r['year']), 'sepsis_deaths')] += float(r['sepsis_deaths'])
    E.require(set(gbd2021) == set(gbd2023), 'The two rounds cover different locations, years or components')
    rows = [[l, y, c, v, gbd2023[(l, y, c)], gbd2023[(l, y, c)] / v] for (l, y, c), v in sorted(gbd2021.items())]
    E.write_csv('round_comparison.csv', HEADER, rows)
    totals = [r for r in rows if r[2] == 'sepsis_deaths']
    india = {str(r[1]): dict(gbd2021=round(r[3]), gbd2023=round(r[4]), ratio=r[5]) for r in totals if r[0] == E.CONFIG['india']}
    ranges = {}
    for year in E.BENCHMARKS:
        part = sorted((r[5], r[0]) for r in totals if r[1] == year and r[0] != E.CONFIG['india'])
        ranges[str(year)] = dict(lowest=dict(location=part[0][1], ratio=part[0][0]), highest=dict(location=part[-1][1], ratio=part[-1][0]))
    E.write_report('06_round_comparison.json', __file__, dict(rows=len(rows)), status='PASSED', india=india,
                   state_ratio_range=ranges)
    print('[06] Complete; GBD 2023 / GBD 2021 sepsis-related deaths in India: '
          + ', '.join(f'{v["ratio"]:.3f} ({y})' for y, v in india.items()), flush=True)


if __name__ == '__main__':
    compare_rounds()

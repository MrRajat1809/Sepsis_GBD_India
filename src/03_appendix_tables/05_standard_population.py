"""Extract the GBD world population age standard (GBD 2021 demographics appendix, Table S14) as printed."""
import appendix_common as A

SPEC = A.CONFIG['tables']['S14']
HEADER = ['page', 'age_group', 'percent', 'rounded']


def extract_standard_population():
    records, layout = A.table_layout('S14')
    cell = {(r['age_group'], r['column']): r['val'] for r in records}
    groups = list(dict.fromkeys(r['age_group'] for r in records))
    A.require(groups == SPEC['age_groups'], f'Table S14: age groups {groups}')
    percents = [cell[(g, 'percent')] for g in groups]
    gap, bound = abs(sum(map(float, percents)) - 100), sum(map(A.half_unit, percents))
    A.require(gap <= bound + 1e-9, f'Table S14: percentages add up to {sum(map(float, percents)):.6f}')
    # Each percentage is printed twice: in full and rounded to 2 decimal places.
    mismatched = [g for g in groups if abs(round(float(cell[(g, 'percent')]), 2) - float(cell[(g, 'rounded')])) > 1e-9]
    A.require(not mismatched, f'Table S14: rounded column does not match the percentages for {mismatched}')
    page = {r['age_group']: r['page'] for r in records}
    A.write_csv('standard_population.csv', HEADER, [[page[g], g, cell[(g, 'percent')], cell[(g, 'rounded')]] for g in groups])
    checks = dict(sum_to_100=dict(gap=gap, rounding_bound=bound), rounded_column_matches=len(groups))
    A.write_report('05_standard_population.json', __file__, dict(age_groups=len(groups)), status='PASSED', layout=layout,
                   checks=checks)
    print(f'[05] Complete; Table S14: {len(groups)} age groups, percentages add up to {sum(map(float, percents)):.5f}',
          flush=True)


if __name__ == '__main__':
    extract_standard_population()

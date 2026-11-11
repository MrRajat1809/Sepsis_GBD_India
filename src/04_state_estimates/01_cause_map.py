"""Classify every cause in the GBD downloads as infectious, non-infectious with a Table S10 share, or without one."""
import csv
import io
import zipfile

import estimates_common as E

HEADER = ['round', 'cause', 'cause_level', 'parent', 'component', 'share_group', 'less']


def cause_hierarchy():
    """Return level 3 -> level 2 and level 4 -> level 3 parents from the GBD 2023 cause list (cause-of-death paper, Table S1)."""
    spec = E.RAW_CONFIG['cause_list']
    aliases = spec['name_aliases']
    parent3, parent4 = {}, {}
    with zipfile.ZipFile(E.raw_file(spec['path'])) as archive:
        member = next(i for i in archive.infolist() if spec['table'] in i.filename)
        with archive.open(member) as stream:
            reader = csv.reader(io.TextIOWrapper(stream, encoding='utf-8-sig', errors='replace', newline=''))
            # A title row and the column header come first; the causes follow in hierarchy order, each after its parent.
            next(reader), next(reader)
            level2 = level3 = None
            for row in reader:
                if len(row) < 2:
                    continue
                name, level = aliases.get(row[0].strip(), row[0].strip()), row[1].strip()
                if level == '2':
                    level2 = name
                elif level == '3':
                    level3, parent3[name] = name, level2
                elif level == '4':
                    parent4[name] = level3
    return parent3, parent4


def table_s10_causes():
    """Return the level 3 cause names of Table S10 by cause type."""
    out = {'Infectious': set(), 'Non-Infectious': set()}
    for r in E.read_csv('table_s10.csv', E.APPENDIX):
        if r['cause_level'] == '3':
            out[r['cause_type']].add(r['cause'])
    return out


def classify(cause, level, parent3, parent4, printed):
    """Return (parent, component, share_group, less) for one GBD cause."""
    # A level 4 cause is used only when moved out of its parent as infectious; otherwise it stays within the parent.
    if level == '4':
        if cause in E.MOVED:
            return parent4[cause], E.INFECTIOUS, '', ''
        E.require(cause in E.CONFIG['level4_not_used'], f'Level 4 cause without a rule: {cause}')
        return parent4[cause], E.NOT_USED, '', ''
    parent = parent3[cause]
    if cause in E.SETS['level2_children_excluded']:
        return parent, E.ZERO, '', ''
    if parent in E.SETS['level2'] or cause in E.SETS['level3']:
        return parent, E.INFECTIOUS, '', ''
    # A GBD 2023 cause that GBD 2021 reports within another cause (Electrocution) takes that cause's pooled share.
    group = E.CONFIG['gbd2023_causes_in_pools'].get(cause, cause)
    # A parent's deaths are counted less those of the level 4 causes moved out of it.
    less = ';'.join(sorted(child for child, p in E.MOVED.items() if p == cause))
    names = E.CONFIG['share_pools'].get(group, [group])
    if not printed & set(names):
        return parent, E.ZERO, '', less
    return parent, E.NON_INFECTIOUS, group, less


def build_cause_map():
    parent3, parent4 = cause_hierarchy()
    s10 = table_s10_causes()
    rounds = {'gbd2021': E.CONFIG['requests']['gbd2021'], 'gbd2023': E.CONFIG['requests']['gbd2023_by_age']}
    rows, checks = [], {}
    for gbd_round, requests in rounds.items():
        causes = E.cause_names(requests)
        levels = {c: '4' if c in parent4 else '3' for c in causes}
        unknown = sorted(c for c in causes if c not in parent3 and c not in parent4)
        E.require(not unknown, f'{gbd_round}: causes not in the GBD 2023 cause list: {unknown}')
        mapped = {c: classify(c, levels[c], parent3, parent4, s10['Non-Infectious']) for c in sorted(causes)}
        rows += [[gbd_round, c, levels[c], *mapped[c]] for c in sorted(causes)]
        components = {k: sorted(c for c, m in mapped.items() if m[1] == k) for k in (E.INFECTIOUS, E.NON_INFECTIOUS, E.ZERO, E.NOT_USED)}
        no_row = sorted(set(components[E.ZERO]) - set(E.SETS['level2_children_excluded']))
        E.require(no_row == sorted(E.CONFIG['no_table_s10_row']), f'{gbd_round}: causes without a Table S10 row: {no_row}')
        groups = {mapped[c][2] for c in components[E.NON_INFECTIOUS]}
        if gbd_round == 'gbd2021':
            E.require(groups <= causes, f'Share groups without GBD 2021 deaths: {sorted(groups - causes)}')
            level3 = {c for c in causes if levels[c] == '3'}
            infectious3 = set(components[E.INFECTIOUS]) & level3
            E.require(infectious3 == s10['Infectious'] & level3,
                      f'Infectious level 3 causes differ from Table S10: {sorted(infectious3 ^ (s10["Infectious"] & level3))}')
            used = {n for g in groups for n in E.CONFIG['share_pools'].get(g, [g])}
            E.require(used == s10['Non-Infectious'], f'Table S10 non-infectious causes not used: {sorted(s10["Non-Infectious"] - used)}')
        checks[gbd_round] = dict(causes=len(causes), by_component={k: len(v) for k, v in components.items()},
                                 zero_share_causes=components[E.ZERO], parents_less_moved={c: m[3] for c, m in mapped.items() if m[3]})
    E.require({r[1] for r in rows if r[0] == 'gbd2023'} - {r[1] for r in rows if r[0] == 'gbd2021'}
              == set(E.CONFIG['gbd2023_causes_in_pools']), 'GBD 2023 causes missing from GBD 2021 must be pooled')
    E.write_csv('cause_map.csv', HEADER, rows)
    E.write_report('01_cause_map.json', __file__, dict(rows=len(rows)), status='PASSED', checks=checks)
    print(f'[01] Complete; {len(rows)} causes mapped across GBD 2021 and GBD 2023', flush=True)


if __name__ == '__main__':
    build_cause_map()

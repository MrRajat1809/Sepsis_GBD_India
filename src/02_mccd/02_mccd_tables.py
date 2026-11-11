"""Extract Table 4 (certified deaths by State/UT, sex and cause) and Table 1 (registered and certified deaths) from the
MCCD report text and check their totals. Values are copied as printed; overflowed '#####' totals are filled from other printed values."""
import re

import mccd_common as M

ALL = M.CONFIG['all_india']
MERGED_DNH = M.CONFIG['merged_dnh']
STATES = [(s['name'], s['pattern']) for s in M.CONFIG['state_patterns']]
TABLE4_ROWS = [(r['cause'], r['pattern']) for r in M.CONFIG['table4_rows']]
SEX = M.CONFIG['sex_codes']


def pages(year):
    path = M.text_path(year)
    M.require(path.is_file(), f'Missing {path}; run 01_mccd_text.py first')
    return path.read_text(encoding='utf-8').split('\f')


def find_states(text, table1=False):
    """Return [(start, end, canonical name)] for State/UT names in a line, in reading order."""
    found, masked = [], text
    for name, pattern in STATES:
        # Table 4 has one India column ('All States'); Table 1 has the 'Total' rows instead.
        if name.startswith('India (') and (name == ALL) == table1:
            continue
        for m in re.finditer(pattern, masked, re.I):
            found.append((m.start(), m.end(), name))
            # Masking the match stops a merged name's parts (Daman & Diu) from matching again.
            masked = masked[:m.start()] + '#' * (m.end() - m.start()) + masked[m.end():]
    return sorted(found)


def tokens(text):
    """Split a line into cells at runs of two or more spaces and at single spaces next to a digit."""
    return [t for t in re.split(r'\s{2,}|\s(?=\d)|(?<=\d)\s', text.strip()) if t]


def sex_row(line):
    """Return (sex, values) for a Table 4 data line, or None if the line holds no data."""
    tk = tokens(line)
    pos = [i for i, t in enumerate(tk) if t in SEX]
    if len(pos) != 1:
        return None
    i = pos[0]
    # Values follow the sex code on the left-hand page and precede it on the right-hand page.
    values = tk[i + 1:] if i < len(tk) / 2 else tk[:i]
    if not values or not all(re.fullmatch(r'\d+|-+|#+', v) for v in values):
        return None
    # '-' is printed for nil; '#####' is a number that overflowed its cell, left missing here for fill_overflow.
    return tk[i], [0 if v.startswith('-') else None if v.startswith('#') else int(v) for v in values]


def block(lines, j):
    """Return the M/F/T values nearest the row label on line j, or None if no block lies within two lines of it."""
    parsed = [(k, *r) for k in range(max(0, j - 6), min(len(lines), j + 8)) for r in [sex_row(lines[k])] if r]
    best = None
    for a in range(len(parsed) - 2):
        (k1, s1, v1), (k2, s2, v2), (k3, s3, v3) = parsed[a:a + 3]
        if (s1, s2, s3) == ('M', 'F', 'T') and len(v1) == len(v2) == len(v3):
            distance = 0 if k1 <= j <= k3 else min(abs(k1 - j), abs(k3 - j))
            if best is None or distance < best[0]:
                best = (distance, {'M': v1, 'F': v2, 'T': v3})
    return best[1] if best and best[0] <= 2 else None


def table4(year, report_pages, notes):
    """Return {(year, State/UT, sex, cause): (value, page)} from the Table 4 pages of one report."""
    rows, in_table = {}, False
    for page_number, page in enumerate(report_pages, 1):
        lines = page.splitlines()
        title = ' '.join(lines[:2])
        if re.search(r'TABLE\s*4\b', title) or (in_table and 'NATIONAL LIST' in title):
            in_table = True
        elif re.search(r'TABLE\s*\d', title):
            in_table = False
        if not in_table:
            continue
        header = next((ln for ln in lines[1:8] if len(find_states(ln)) >= 5), None)
        if header is None:
            continue
        columns = [n for _, _, n in find_states(header)]
        for cause, pattern in TABLE4_ROWS:
            hits = [j for j, ln in enumerate(lines) if re.search(pattern, ln, re.I)]
            if not hits:
                continue
            found = block(lines, hits[0])
            if found is None:
                notes.append(f'{year} p{page_number} {cause}: no M/F/T block')
                continue
            if len(found['M']) != len(columns):
                notes.append(f'{year} p{page_number} {cause}: {len(found["M"])} values, {len(columns)} column headers')
                continue
            # A major-group label is repeated on its continuation pages; the first page with a row for a State/UT is kept.
            for sex, values in found.items():
                for state, value in zip(columns, values):
                    rows.setdefault((year, state, SEX[sex], cause), (value, page_number))
    return rows


def number(text):
    """Return a printed number without its thousands separators, or None if the cell is not a number."""
    text = text.replace(',', '')
    return float(text) if re.fullmatch(r'\d+(\.\d+)?', text) else None


def table1(year, report_pages, notes):
    """Return registered (left-hand page) and certified (right-hand page) deaths for the three data years in Table 1."""
    out = {}
    index = [i for i, p in enumerate(report_pages) if re.search(r'TABLE\s*[-:]?\s*1\s*[:\-]', ' '.join(p.splitlines()[:3]))]
    # In the 2008-2009 reports the right-hand page of Table 1 carries no table number.
    index = sorted(set(index) | {i + 1 for i in index if i + 1 < len(report_pages)})
    for i in index:
        lines = report_pages[i].splitlines()
        years = next((list(map(int, re.findall(r'\b(20\d\d)\b', ln))) for ln in lines
                      if len(re.findall(r'\b20\d\d\b', ln)) >= 6), None)
        if not years:
            continue
        data_years = years[:3]
        # Usually two pages: registered deaths, total and urban (6 cells); certified, % of registered and % of urban (9 cells).
        # The 2011 report has one page: registered, certified and % of registered (9 cells, no urban columns).
        one_page = len(years) == 9 and not re.search(r'URBAN', ' '.join(lines[:14]), re.I)
        left = len(years) == 6
        need = 6 if left else 9
        fields = ({0: 'registered_deaths'} if left else
                  {0: 'registered_deaths', 3: 'certified_deaths'} if one_page else {0: 'certified_deaths'})
        for k, line in enumerate(lines):
            states = find_states(line, table1=True)
            if len(states) != 1:
                continue
            a, b, name = states[0]
            # The merged UT's name wraps onto the next non-blank line, after a trailing 'and' on the right-hand page; its
            # values count as the merged UT only from merged_dnh_from_year.
            following = next((ln for ln in lines[k + 1:k + 3] if ln.strip()), '')
            if name == 'Dadra & Nagar Haveli' and (re.search(r'and\s+Daman', following) or re.fullmatch(r'\s*and\s*', line[b:])):
                name = 'DNH_ROW'
            # Cells sit on whichever side of the name holds the numbers; the serial number is on the other side or beside it.
            digits = lambda v: sum(bool(re.search(r'\d', x)) for x in v)
            before, after = tokens(line[:a]), tokens(line[b:])
            cells_after = digits(after) >= digits(before)
            values = [v for v in (after if cells_after else before) if v not in ('$', '*')]
            if digits(values) < 2:  # Headings, footnotes, wrapped name lines
                continue
            serial = 0 if cells_after else -1
            if len(values) == need + 1 and re.fullmatch(r'\d+', values[serial]):
                del values[serial]
            # Irregular rows are reported, not guessed; a left-hand row keeps its three totals when they are intact.
            if len(values) != need:
                side, label = 'left' if left else 'right', MERGED_DNH if name == 'DNH_ROW' else name
                if left and len(values) > 3 and all(re.fullmatch(r'\d+', v) for v in values[:3]):
                    notes.append(f'{year} Table 1 {side} {label}: {len(values)} cells {values}; kept the three totals')
                else:
                    notes.append(f'{year} Table 1 {side} {label}: {len(values)} cells {values}; not used')
                    continue
            for offset, field in fields.items():
                for data_year, value in zip(data_years, values[offset:offset + 3]):
                    state = name
                    if name == 'DNH_ROW':
                        state = MERGED_DNH if data_year >= M.CONFIG['merged_dnh_from_year'] else 'Dadra & Nagar Haveli'
                    out.setdefault((year, data_year, state), {})[field] = number(value)
    return out


def fill_overflow(t4, t1, notes):
    """Fill '#####' cells: an all-cause Total from the same report's Table 1, else a Total as Male + Female; others stay missing."""
    flags = {}
    for (year, state, sex, cause), value in sorted(t4.items()):
        if value is not None:
            continue
        key = (year, state, sex, cause)
        male, female = t4.get((year, state, 'Male', cause)), t4.get((year, state, 'Female', cause))
        certified = t1.get((year, year, state), {}).get('certified_deaths')
        if sex == 'Total' and cause == 'all_causes' and certified is not None:
            t4[key], flags[key] = int(certified), 'printed as ##### in Table 4; value from Table 1 of the same report'
        elif sex == 'Total' and male is not None and female is not None:
            t4[key], flags[key] = male + female, 'printed as ##### in Table 4; Male + Female'
        else:
            flags[key] = 'printed as ##### in Table 4; missing'
        notes.append(f'{year} {state} {sex} {cause}: {flags[key]} ({t4[key]})')
    return flags


def consistency(t4, pages_of, t1):
    """Compare the States/UTs with the all-India column, Male + Female with Total, and Table 1 with Table 4."""
    failures, gaps, table_mismatch = [], {}, {}
    for year in M.YEARS:
        for cause, _ in TABLE4_ROWS:
            for sex in SEX.values():
                total = t4.get((year, ALL, sex, cause))
                summed = sum(v or 0 for (y, s, x, c), v in t4.items() if y == year and x == sex and c == cause and s != ALL)
                if total != summed:
                    failures.append(dict(year=year, cause=cause, sex=sex, all_india=total, states_sum=summed,
                                         pages=sorted({p for (y, s, x, c), p in pages_of.items() if y == year and x == sex and c == cause})))
            gap = [(s, t - m - f) for (y, s, x, c), t in t4.items() if y == year and c == cause and x == 'Total' and s != ALL
                   for m in [t4.get((year, s, 'Male', cause))] for f in [t4.get((year, s, 'Female', cause))]
                   if None not in (t, m, f) and t != m + f]
            if gap:
                gaps[f'{year} {cause}'] = dict(gap)
        diff = [(s, r.get('certified_deaths'), t4.get((year, s, 'Total', 'all_causes')))
                for (ry, dy, s), r in t1.items() if ry == year and dy == year
                and t4.get((year, s, 'Total', 'all_causes')) is not None
                and r.get('certified_deaths') != t4.get((year, s, 'Total', 'all_causes'))]
        if diff:
            table_mismatch[str(year)] = diff
    return failures, gaps, table_mismatch


def extract_tables():
    t4, pages_of, t1, notes = {}, {}, {}, []
    for year in M.YEARS:
        report_pages = pages(year)
        rows = table4(year, report_pages, notes)
        t4.update({k: v for k, (v, _) in rows.items()})
        pages_of.update({k: p for k, (_, p) in rows.items()})
        t1.update(table1(year, report_pages, notes))
    flags = fill_overflow(t4, t1, notes)
    failures, gaps, table_mismatch = consistency(t4, pages_of, t1)
    M.require({k[0] for k in t4} == set(M.YEARS), 'Table 4 is missing a report year')
    M.write_csv('table4_by_state.csv', ['year', 'state', 'sex', 'cause', 'certified_deaths', 'pdf_page', 'note'],
                sorted((y, s, x, c, '' if v is None else v, pages_of[(y, s, x, c)], flags.get((y, s, x, c), ''))
                       for (y, s, x, c), v in t4.items()))
    M.write_csv('table1_coverage.csv', ['report_year', 'data_year', 'state', 'registered_deaths', 'certified_deaths'],
                [[ry, dy, s, r.get('registered_deaths', ''), r.get('certified_deaths', '')] for (ry, dy, s), r in sorted(t1.items())])
    summary = dict(table4_cells=len(t4), table4_missing=sum(v is None for v in t4.values()), table1_rows=len(t1),
                   states_sum_failures=len(failures), years_with_sex_gaps=len(gaps), years_table1_mismatch=len(table_mismatch))
    M.write_report('02_tables.json', __file__, summary, states_sum_failures=failures, total_minus_male_female=gaps,
                   table1_vs_table4=table_mismatch, notes_for_review=notes)
    M.require(not failures, 'States/UTs do not add up to the all-India column; see outputs/mccd/02_tables.json')
    print(f'[02] Complete; {len(t4):,} Table 4 cells and {len(t1):,} Table 1 rows; '
          f'{len(failures)} all-India sum differences; {len(notes)} notes in outputs/mccd/02_tables.json', flush=True)


if __name__ == '__main__':
    extract_tables()

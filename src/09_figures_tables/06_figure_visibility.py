"""Figure 5: sepsis on death certificates (MCCD) by state in 2019 (A), its trend in the units that reported every year (B)
and that trend split into the three factors of the count ratio (C), in the row layout and colours of Figure 4."""
import textwrap

import matplotlib.pyplot as plt
from matplotlib.ticker import FixedLocator, NullLocator

import figures_common as F

STEM = 'Fig5'
ROWS = F.CONFIG['visibility_rows']
FACTORS = (('registration_completeness', 'Registration completeness'), ('certification_coverage', 'Certification coverage'),
           ('visibility_share', 'Share ratio'))
COUNT = ('visibility_count', 'Count ratio')
# Sizes in inches.
ROW_H, RATIO_W, COVER_W, GAP, RIGHT_GAP = 0.122, 1.45, 0.95, 0.16, 0.62
TITLE_BAND, HEAD_BAND, FOOT = 0.34, 0.3, 0.3


def axis(fig, left, bottom, width, height):
    """Return transparent axes placed in inches, without top and right spines."""
    w, h = fig.get_figwidth(), fig.get_figheight()
    ax = fig.add_axes((left / w, bottom / h, width / w, height / h))
    ax.patch.set_visible(False)
    for side in ('top', 'right'):
        ax.spines[side].set_visible(False)
    return ax


def listing(names):
    """Return names as a list in running text: 'A', 'A and B', 'A, B, and C'."""
    return names[0] if len(names) == 1 else ', '.join(names[:-1]) + (',' if len(names) > 2 else '') + ' and ' + names[-1]


def build_visibility():
    F.style()
    year = F.CONFIG['years']['visibility']
    size, ink, secondary = F.CONFIG['font_size'] - 1.5, F.PALETTE['ink'], F.PALETTE['secondary']
    # Septicaemia in the infectious colour of Figures 2 and 4; context measures in its tint.
    red = F.PALETTE['two_group'][0]
    light = F.tint(red, F.CONFIG['tint'])
    rows = F.read_csv('mccd_visibility', 'visibility.csv')
    now = {r['unit']: r for r in rows if int(r['year']) == year}
    flag = F.CONFIG['registered_over_estimated_flag']
    # Units that did not report are left out; those that recorded no septicaemia deaths sort last.
    reporting = [u for u, r in now.items() if not u.startswith(F.INDIA) and r['complete'] == '1']
    units = sorted(reporting, key=lambda u: (-float(now[u]['visibility_count']), u))
    # Drawn hollow: registered deaths exceed GBD's estimate by more than the flag ratio. Registration and MCCD count deaths
    # where they occur and GBD where people lived, so these units probably include deaths of residents of other states.
    flagged = sorted(u for u in units if now[u]['registration_completeness'] and float(now[u]['registration_completeness']) > flag)
    listed = [ROWS['india']] + units
    name = lambda u: F.INDIA if u == ROWS['india'] else F.short_unit(u)

    width = F.CONFIG['width_full']
    probe = plt.figure(figsize=(width, 1))
    name_w = max(F.text_width(probe, name(u), size + 0.5) for u in listed)
    plt.close(probe)
    grid_h = len(listed) * ROW_H
    top = FOOT + grid_h
    height = round(TITLE_BAND + HEAD_BAND + grid_h + FOOT, 2)
    fig = plt.figure(figsize=(width, height))
    ratio_left = 0.04 + name_w + 0.08
    cover_left = ratio_left + RATIO_W + GAP
    right_left = cover_left + COVER_W + RIGHT_GAP
    F.row_bands(fig, len(listed), top, ROW_H, 0.04, cover_left + COVER_W + 0.04)
    data = []

    # A: count ratio (log scale) and certification coverage (certified / registered deaths, as in the MCCD reports) by unit
    ratio, cover = axis(fig, ratio_left, FOOT, RATIO_W, grid_h), axis(fig, cover_left, FOOT, COVER_W, grid_h)
    for ax in (ratio, cover):
        ax.set_ylim(len(listed), 0)
        ax.set_yticks([])
        ax.spines['left'].set_visible(False)
        ax.tick_params(axis='x', length=2, pad=1.5)
    ratio.set_xscale('log')
    ratio.set_xlim(0.08, 100)
    ratio.xaxis.set_major_locator(FixedLocator([0.1, 1, 10, 100]))
    ratio.xaxis.set_minor_locator(NullLocator())
    ratio.set_xticks([0.1, 1, 10, 100], ['0.1', '1', '10', '100'])
    ratio.grid(axis='x', color=F.PALETTE['grid'], linewidth=0.5)
    cover.set_xlim(0, 100)
    cover.set_xticks([0, 50, 100], ['0', '50', '100'])
    for ax in (ratio, cover):
        labels = ax.get_xticklabels()
        labels[0].set_ha('left')
        labels[-1].set_ha('right')
    cover.spines['left'].set_visible(True)
    cover.spines['left'].set_linewidth(0.6)
    india = now[ROWS['india']]
    ratio.axvline(100 * float(india['visibility_count']), color=secondary, linewidth=0.5, zorder=1)
    cover.axvline(100 * float(india['certification_coverage']), color=secondary, linewidth=0.5, zorder=3)
    for i, unit in enumerate(listed):
        r, y = now[unit], i + 0.5
        count, coverage = 100 * float(r['visibility_count']), 100 * float(r['certification_coverage'])
        hollow = unit in flagged
        ratio.text(-0.08 / RATIO_W, y, name(unit), transform=ratio.get_yaxis_transform(), ha='right', va='center', fontsize=size + 0.5, color=ink)
        if count > 0:
            ratio.plot([count], [y], marker='o', markersize=4.2, linestyle='none', markeredgewidth=0.9, zorder=4,
                       markerfacecolor=F.PALETTE['surface'] if hollow else red, markeredgecolor=red)
        F.hbar(cover, y, 0, coverage, 0.62, light)
        unit_name = F.INDIA if unit == ROWS['india'] else unit
        data += [['A', unit_name, year, 'visibility_count_percent', count, '', int(hollow)],
                 ['A', unit_name, year, 'certification_coverage_percent', coverage, '', int(hollow)]]
    for left, w, text in ((ratio_left, RATIO_W, 'Count ratio (%)'), (cover_left, COVER_W, 'Certification\ncoverage (%)')):
        fig.text((left + w / 2) / width, (top + 0.05) / height, text, ha='center', va='bottom', fontsize=size + 0.5, color=ink, linespacing=1.1)
    rho = next(float(r['spearman']) for r in F.read_csv('mccd_visibility', 'correlations_by_year.csv')
               if int(r['year']) == year and r['measure'] == 'visibility_count' and r['against'] == 'certification_coverage')

    # B: count ratio of the units that reported every year; years after the trend's end (COVID-19) shaded
    trend = sorted((r for r in rows if r['unit'] == ROWS['trend']), key=lambda r: int(r['year']))
    first, last = int(trend[0]['year']), int(trend[-1]['year'])
    changes = {r['measure']: r for r in F.read_csv('mccd_visibility', 'trends.csv') if r['unit'] == ROWS['trend']}
    end = max(int(changes[m]['last_year']) for m, _ in FACTORS + (COUNT,))
    right_w = width - 0.06 - right_left
    c_h = 1.15
    b_h = grid_h + HEAD_BAND - c_h - 0.72
    line = axis(fig, right_left, top + HEAD_BAND - b_h, right_w, b_h)
    years = [int(r['year']) for r in trend]
    values = [100 * float(r[COUNT[0]]) for r in trend]
    line.axvspan(end + 0.5, last + 0.5, color=F.PALETTE['neutral'], linewidth=0, zorder=0)
    line.plot(years, values, color=red, linewidth=1.5, marker='o', markersize=2.8, zorder=3)
    data += [['B', ROWS['trend'], y, 'visibility_count_percent', v, '', ''] for y, v in zip(years, values)]
    ceiling = int(max(values) * 1.3)
    line.set_ylim(0, max(values) * 1.3)
    line.set_xlim(first - 0.6, last + 0.6)
    line.set_xticks(range(first, last + 1, 3))
    line.set_yticks(range(0, ceiling + 1))
    line.grid(axis='y', color=F.PALETTE['grid'], linewidth=0.5)
    line.tick_params(axis='both', length=2, pad=1.5)
    line.set_ylabel('Count ratio (%)', fontsize=size + 0.5)
    line.text((end + 0.5 + last + 0.5) / 2, max(values) * 1.27, 'COVID-19', ha='center', va='top', fontsize=size, color=secondary)
    change = float(changes[COUNT[0]]['annual_percent_change'])

    # C: the annual change as a waterfall of the three factors whose product is the count ratio, so the steps add up to
    # about its change
    fall = axis(fig, right_left, FOOT, right_w, c_h)
    steps = [(m, label, float(changes[m]['annual_percent_change'])) for m, label in FACTORS]
    start, bars = 0.0, []
    for m, label, v in steps:
        bars.append((m, label, start, start + v, light))
        start += v
    bars.append((COUNT[0], COUNT[1], 0.0, change, red))
    fall.set_xlim(0, max(start, change) * 1.2)
    fall.set_ylim(len(bars) - 0.4, -0.6)
    for k, (m, label, a, b, colour) in enumerate(bars):
        F.hbar(fall, k, a, b, 0.58, colour)
        fall.annotate(f'{b - a:+.1f}', (b, k), xytext=(2.5, 0), textcoords='offset points', ha='left', va='center', fontsize=size, color=ink)
        if k < len(bars) - 1:
            fall.plot([b, b], [k + 0.29, k + 0.71], color=F.PALETTE['muted'], linewidth=0.5, zorder=1)
        data.append(['C', ROWS['trend'], f'{first}-{end}', m, b - a, a, ''])
    fall.set_yticks(range(len(bars)), [textwrap.fill(label, 14) for _, label, *_ in bars])
    fall.tick_params(axis='y', length=0, pad=3, labelsize=size + 0.5)
    fall.tick_params(axis='x', length=2, pad=1.5)
    fall.spines['left'].set_linewidth(0.6)
    fall.grid(axis='x', color=F.PALETTE['grid'], linewidth=0.5)

    # Letters and titles
    letter_y = 1 - 0.04 / height
    for letter, left, title, centre in (('A', 0.04, f'{year}', (ratio_left + cover_left + COVER_W) / 2),
                                        ('B', right_left - 0.42, f'{first}-{last}', right_left + right_w / 2)):
        fig.text(left / width, letter_y, letter, fontsize=F.CONFIG['map']['letter_size'], va='top')
        fig.text(centre / width, 1 - 0.1 / height, title, ha='center', va='top', fontsize=F.CONFIG['font_size'] + 0.5)
    c_top = FOOT + c_h
    fig.text((right_left - 0.42) / width, (c_top + 0.36) / height, 'C', fontsize=F.CONFIG['map']['letter_size'], va='top')
    fig.text((right_left + right_w / 2) / width, (c_top + 0.3) / height, f'Annual change, {first}-{end} (%)', ha='center', va='top',
             fontsize=F.CONFIG['font_size'] + 0.5)
    exported = F.save(fig, STEM)
    F.write_rows(f'{STEM}_data.csv', ['panel', 'unit', 'year', 'measure', 'value', 'start', 'hollow'], data)
    missing = sorted(u for u, r in now.items() if not u.startswith(F.INDIA) and r['complete'] != '1')
    none = sorted(u for u in units if float(now[u]['visibility_count']) == 0)
    shortened = '; '.join(f'{F.short_unit(u)}={u}' for u in units if F.short_unit(u) != u)
    caption = (f'(A) Count ratio: MCCD septicaemia deaths as a percentage of the estimated sepsis-related deaths, for each State/UT '
               f'group of the GBD units in {year}, on a logarithmic scale; certification coverage: certified as a percentage of '
               'registered deaths. The count ratio describes how often septicaemia is certified as the underlying cause, not '
               'under-reporting: under the ICD rules the underlying cause is the disease that led to sepsis, and GBD treats septicaemia '
               'as an intermediate cause (a garbage code), so a higher ratio is not better certification. India: the units that '
               'reported; vertical lines mark India\'s values. Open circles: registered deaths exceed GBD\'s estimated deaths by more '
               f'than {round(100 * (flag - 1))}%; MCCD counts deaths where they occur and GBD where people lived, so these units '
               'probably include deaths of residents of other states. ' +
               (f'No circle: no septicaemia deaths recorded ({listing(none)}). ' if none else '') +
               f'Rank correlation of the two measures across states: {rho:.2f}. Not shown: {listing(missing)} (did not report). '
               f'(B) The units that reported in every year {first}-{end} (Andhra Pradesh and Telangana as one); COVID-19 years '
               f'shaded. (C) Annual change in the count ratio, {first}-{end}, and in its three factors: registration completeness '
               '(registered / estimated deaths), certification coverage (certified / registered deaths), and the share ratio '
               '(septicaemia\'s share of certified deaths divided by the estimated sepsis-related share of all deaths). The count ratio '
               'is their product, so its annual change is about the sum of theirs. Trends end in '
               f'{end} because COVID-19 deaths count as sepsis-related in the estimates but are coded as COVID-19 in MCCD. Registered '
               f'deaths are not available for 2016. MCCD=Medical Certification of Cause of Death. {shortened}.')
    F.write_report('06_figure_visibility.json', __file__,
                   dict(figure=STEM, units=len(units), year=year, flagged=flagged, missing=missing, rank_correlation=rho,
                        annual_percent_change={m: float(changes[m]['annual_percent_change']) for m, _ in FACTORS + (COUNT,)}),
                   inputs=[('mccd_visibility', 'visibility.csv'), ('mccd_visibility', 'correlations_by_year.csv'),
                           ('mccd_visibility', 'trends.csv')], export=exported, caption_note=F.lancet_text(caption))
    print(f'[06] Complete; {STEM}: {len(units)} units in {year} (rank correlation {rho:.2f}); count ratio {change:+.1f}% a year '
          f'{first}-{end}', flush=True)


if __name__ == '__main__':
    build_visibility()

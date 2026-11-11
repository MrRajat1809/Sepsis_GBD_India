"""Figure 4: age-standardised sepsis-related death rates by state and underlying cause, 2019, as rows of bars (the bar
style of the GBD 2021 sepsis paper, the state-by-cause layout of the India State-Level Disease Burden Initiative)."""
import math
import textwrap

import matplotlib.pyplot as plt
from matplotlib.legend_handler import HandlerTuple
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

import figures_common as F

STEM = 'Fig4'
GROUPS = (('infectious', 'Infectious underlying causes'), ('non_infectious', 'Non-infectious underlying causes'))
PARTS = ('asr_infectious', 'asr_non_infectious')
TOTAL = 'age_standardised_rate'
# Sizes in inches, except BAR_H (a fraction of the row).
ROW_H, BAR_H, TOTAL_W, A_GAP, PANEL_GAP, GROUP_GAP = 0.142, 0.62, 1.25, 0.32, 0.1, 0.2
TITLE_BAND, GROUP_BAND, FOOT, NOTE = 0.34, 0.22, 0.66, 0.24


def nice_tick(top):
    """Return the largest of 1, 2, 2.5 and 5 times a power of ten that is at most top."""
    power = 10 ** math.floor(math.log10(top))
    return max(m * power for m in (1, 2, 2.5, 5) if m * power <= top)


def tick_text(value):
    return f'{value:,.0f}' if value >= 1 else f'{value:g}'


def bars_axis(fig, left, bottom, width, height, rows, top):
    """Return transparent axes placed in inches, one row per unit from the top, x from 0 to top."""
    ax = fig.add_axes((left / fig.get_figwidth(), bottom / fig.get_figheight(), width / fig.get_figwidth(), height / fig.get_figheight()))
    ax.patch.set_visible(False)
    ax.set_xlim(0, top)
    ax.set_ylim(rows, 0)
    ax.set_yticks([])
    for side in ('top', 'right'):
        ax.spines[side].set_visible(False)
    ax.spines['left'].set_linewidth(0.6)
    ax.tick_params(axis='x', length=2, pad=1.5)
    return ax


def build_state_causes():
    F.style()
    year, per = F.CONFIG['years']['state_causes'], F.CONFIG['state_causes_per_group']
    size, ink, secondary = F.CONFIG['font_size'] - 1.5, F.PALETTE['ink'], F.PALETTE['secondary']
    colour = dict(zip((g for g, _ in GROUPS), F.PALETTE['two_group']))
    deaths = {r['cause']: float(r['sepsis_deaths']) for r in F.read_csv('state_estimates', 'estimates_annual.csv')
              if r['location'] == F.INDIA and r['sex'] == 'Both' and int(r['year']) == year}
    by_cause = [r for r in F.read_csv('state_estimates', 'rates_by_cause.csv') if int(r['year']) == year]
    component = {r['cause']: r['component'] for r in by_cause}
    rates = {(r['location'], r['cause']): float(r['sepsis_asr']) for r in by_cause}
    totals = {r['location']: r for r in F.read_csv('state_estimates', 'rates_annual.csv') if r['sex'] == 'Both' and int(r['year']) == year}
    interval = {r['location']: r for r in F.read_csv('state_estimates', 'uncertainty_annual.csv')
                if r['sex'] == 'Both' and int(r['year']) == year and r['measure'] == TOTAL}
    # Rows: India, then the units by their age-standardised rate from all causes.
    units = sorted(set(totals) - {F.INDIA}, key=lambda u: -float(totals[u][TOTAL]))
    rows = [F.INDIA] + units
    leader = {(u, g): max((c for c in component if component[c] == g), key=lambda c: rates[(u, c)]) for u in rows for g, _ in GROUPS}
    # Causes: those leading their group in at least one unit, filled up to the configured number per group with India's
    # next leading causes, in India's order by deaths.
    columns = {}
    for g, _ in GROUPS:
        national = sorted((c for c in deaths if component.get(c) == g), key=lambda c: -deaths[c])
        chosen = {leader[(u, g)] for u in rows}
        chosen |= set([c for c in national if c not in chosen][:max(per - len(chosen), 0)])
        columns[g] = [c for c in national if c in chosen]
    causes = [c for g, _ in GROUPS for c in columns[g]]

    width = F.CONFIG['width_full']
    probe = plt.figure(figsize=(width, 1))
    name_w = max(F.text_width(probe, F.short_unit(u), size + 0.5) for u in rows)
    labels = {c: textwrap.fill(F.short_cause(c), 11, break_long_words=False) for c in causes}
    label_h = max(len(t.split('\n')) for t in labels.values()) * (size + 0.5) * 1.2 / 72
    plt.close(probe)
    grid_h = len(rows) * ROW_H
    height = round(TITLE_BAND + GROUP_BAND + label_h + 0.08 + grid_h + FOOT, 2)
    top = FOOT + grid_h
    fig = plt.figure(figsize=(width, height))
    a_left = 0.04 + name_w + 0.08
    b_left = a_left + TOTAL_W + A_GAP
    gaps = sum((len(columns[g]) - 1) * PANEL_GAP for g, _ in GROUPS) + GROUP_GAP
    panel_w = (width - 0.06 - b_left - gaps) / len(causes)
    F.row_bands(fig, len(rows), top, ROW_H, 0.04, width - 0.04)
    data = []

    # A: all-cause rate, split by type of underlying cause, with the interval of the total
    limit = max(float(interval[u]['upper']) for u in rows) * 1.17
    total = bars_axis(fig, a_left, FOOT, TOTAL_W, grid_h, len(rows), limit)
    step = nice_tick(limit / 2.2)
    total.set_xticks([step * k for k in range(int(limit // step) + 1)], [tick_text(step * k) for k in range(int(limit // step) + 1)])
    for i, unit in enumerate(rows):
        y, r, u = i + 0.5, totals[unit], interval[unit]
        total.text(-0.08 / TOTAL_W, y, F.short_unit(unit), transform=total.get_yaxis_transform(), ha='right', va='center',
                   fontsize=size + 0.5, color=ink)
        start = 0.0
        for k, ((g, _), measure) in enumerate(zip(GROUPS, PARTS)):
            value = float(r[measure])
            F.hbar(total, y, start, start + value, BAR_H, colour[g], rounded=k == len(PARTS) - 1)
            data.append(['A', unit, measure, value, '', '', ''])
            start += value
        low, high = float(u['lower']), float(u['upper'])
        total.plot([low, high], [y, y], color=ink, linewidth=0.55, solid_capstyle='butt', zorder=3)
        for end in (low, high):
            total.plot([end, end], [y - 0.2, y + 0.2], color=ink, linewidth=0.55, solid_capstyle='butt', zorder=3)
        total.annotate(f'{float(r[TOTAL]):.0f}', (high, y), xytext=(2, 0), textcoords='offset points', ha='left', va='center',
                       fontsize=size - 0.5, color=secondary)
        data.append(['A', unit, TOTAL, float(r[TOTAL]), low, high, ''])
    fig.text((a_left + TOTAL_W / 2) / width, (FOOT - NOTE) / height, 'Deaths per 100,000', ha='center', va='top', fontsize=size,
             color=secondary)

    # B: one bar chart per cause, on one scale per group, India's rate as a line; each unit's leading cause of the group in
    # the full colour, the others in a tint
    x = b_left
    for g, title in GROUPS:
        group_left = x
        group_top = max(rates[(u, c)] for u in rows for c in columns[g])
        tick = nice_tick(group_top)
        for cause in columns[g]:
            values = [rates[(u, cause)] for u in rows]
            ax = bars_axis(fig, x, FOOT, panel_w, grid_h, len(rows), group_top * 1.04)
            ax.set_xticks([0, tick], ['0', tick_text(tick)])
            for label, ha in zip(ax.get_xticklabels(), ('left', 'right')):
                label.set_ha(ha)
            ax.axvline(rates[(F.INDIA, cause)], color=secondary, linewidth=0.5, zorder=3)
            for i, unit in enumerate(rows):
                leading = leader[(unit, g)] == cause
                F.hbar(ax, i + 0.5, 0, values[i], BAR_H, colour[g] if leading else F.tint(colour[g], F.CONFIG['tint']))
                data.append(['B', unit, cause, values[i], '', '', int(leading)])
            fig.text((x + panel_w / 2) / width, (top + 0.06) / height, labels[cause], ha='center', va='bottom', fontsize=size + 0.5,
                     color=ink, linespacing=1.1)
            x += panel_w + PANEL_GAP
        group_right = x - PANEL_GAP
        rule = top + 0.06 + label_h + 0.06
        fig.lines.append(Line2D([group_left, group_right], [rule, rule], transform=fig.dpi_scale_trans, color=secondary, linewidth=0.6))
        fig.text((group_left + group_right) / 2 / width, (rule + 0.04) / height, title, ha='center', va='bottom', fontsize=size + 0.5,
                 color=secondary)
        x += GROUP_GAP - PANEL_GAP
    fig.text((b_left + (width - 0.06)) / 2 / width, (FOOT - NOTE) / height, 'Deaths per 100,000', ha='center', va='top', fontsize=size,
             color=secondary)

    # Letters, titles and keys
    letter_y = 1 - 0.04 / height
    for letter, left in (('A', 0.04), ('B', b_left - 0.12)):
        fig.text(left / width, letter_y, letter, fontsize=F.CONFIG['map']['letter_size'], va='top')
    fig.text((a_left + TOTAL_W / 2) / width, 1 - 0.1 / height, 'All causes', ha='center', va='top', fontsize=F.CONFIG['font_size'] + 0.5)
    fig.text((b_left + (width - 0.06)) / 2 / width, 1 - 0.1 / height, 'Leading underlying causes', ha='center', va='top',
             fontsize=F.CONFIG['font_size'] + 0.5)
    swatch = lambda c: Patch(facecolor=c, edgecolor='none')
    first = fig.legend(handles=[swatch(colour[g]) for g, _ in GROUPS] + [Line2D([], [], color=ink, linewidth=0.55, marker='|', markersize=4,
                                                                                markeredgewidth=0.55)],
                       labels=['Infectious causes', 'Non-infectious causes', '95% uncertainty interval'], loc='upper left',
                       bbox_to_anchor=(0.04 / width, (FOOT - NOTE - 0.2) / height), fontsize=size, ncols=3, handlelength=1.1, handleheight=0.75,
                       handletextpad=0.35, columnspacing=1.0, borderaxespad=0, borderpad=0)
    fig.add_artist(first)
    full = tuple(swatch(colour[g]) for g, _ in GROUPS)
    light = tuple(swatch(F.tint(colour[g], F.CONFIG['tint'])) for g, _ in GROUPS)
    fig.legend(handles=[full, light, Line2D([], [], color=secondary, linewidth=0.6)],
               labels=["The state's leading cause of the group", 'Other causes', "India's rate"], loc='upper right',
               bbox_to_anchor=((width - 0.06) / width, (FOOT - NOTE - 0.2) / height), fontsize=size, ncols=3, handlelength=1.6, handleheight=0.75,
               handletextpad=0.35, columnspacing=1.0, borderaxespad=0, borderpad=0, handler_map={tuple: HandlerTuple(ndivide=None, pad=0.15)})
    exported = F.save(fig, STEM)
    F.write_rows(f'{STEM}_data.csv', ['panel', 'unit', 'measure', 'value', 'lower', 'upper', 'leading'], data)
    spread = {g: max(float(totals[u][m]) for u in units) / min(float(totals[u][m]) for u in units) for (g, _), m in zip(GROUPS, PARTS)}
    shortened = sorted(F.short_unit(u) for u in rows if F.short_unit(u) != u)
    caption = (f'Age-standardised sepsis-related deaths per 100,000, {year}. (A) All causes, split into infectious and non-infectious '
               'underlying causes, with the 95% uncertainty interval of the total. (B) The underlying causes that lead their group in at '
               f'least one state, with India\'s next leading causes up to {per} per group; the causes of a group share one scale, and the '
               'line is India\'s rate. In each state the leading infectious and the leading non-infectious cause are drawn in the full colour. '
               f'States are ordered by their rate from all causes. Across states, the rate from infectious causes varies '
               f'{spread["infectious"]:.1f}-fold and that from non-infectious causes {spread["non_infectious"]:.1f}-fold. *Excluding '
               'neonatal sepsis, counted with the infectious causes. Rates by state and cause have no uncertainty intervals. ' +
               '; '.join(f'{F.short_unit(u)}={u}' for u in rows if F.short_unit(u) != u) + '.')
    F.write_report('05_figure_state_causes.json', __file__,
                   dict(figure=STEM, year=year, units=len(units), causes=causes, fold_range=spread, shortened_names=shortened),
                   inputs=[('state_estimates', 'estimates_annual.csv'), ('state_estimates', 'rates_by_cause.csv'),
                           ('state_estimates', 'rates_annual.csv'), ('state_estimates', 'uncertainty_annual.csv')],
                   export=exported, caption_note=F.lancet_text(caption))
    print(f'[05] Complete; {STEM}: {len(rows)} rows, all causes and {len(causes)} leading causes, {year}', flush=True)


if __name__ == '__main__':
    build_state_causes()

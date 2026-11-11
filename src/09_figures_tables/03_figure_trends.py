"""Figure 2: sepsis-related deaths in India, 1990-2023, by type of underlying cause (A) and by age in the years with age
detail (B infectious, C non-infectious), after Figure 3 of the GBD 2021 sepsis paper."""
from collections import defaultdict

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

import figures_common as F

STEM = 'Fig2'
COMPONENTS = (('infectious', 'Infectious underlying cause'), ('non_infectious', 'Non-infectious underlying cause'))


def build_trends():
    F.style()
    # India's intervals come from its own GBD rows.
    ui = {(r['measure'], int(r['year'])): r for r in F.read_csv('state_estimates', 'uncertainty_annual.csv')
          if r['location'] == F.INDIA and r['sex'] == 'Both' and r['measure'] in dict(COMPONENTS)}
    years = sorted({y for _, y in ui})
    groups = F.CONFIG['trend_age_groups']
    group_of = {age: g for g, ages in groups.items() for age in ages}
    by_age = defaultdict(float)
    for r in F.read_csv('state_estimates', 'estimates_by_age.csv'):
        if r['location'] == F.INDIA and r['component'] in dict(COMPONENTS):
            by_age[(r['component'], int(r['year']), group_of[r['age_group']])] += float(r['sepsis_deaths'])
    F.require({a for _, _, a in by_age} == set(groups), 'Age groups do not cover the estimates by age')
    age_years = sorted({y for _, y, _ in by_age})
    projection = F.CONFIG['projection_from']
    colours = dict(zip(dict(COMPONENTS), F.PALETTE['two_group']))
    fig = plt.figure(figsize=(F.CONFIG['width_full'], 6.2), layout='constrained')
    grid = fig.add_gridspec(2, 2, height_ratios=[1, 1.05])
    top, left, right = fig.add_subplot(grid[0, :]), fig.add_subplot(grid[1, 0]), fig.add_subplot(grid[1, 1])
    data = []

    # A: deaths by type of underlying cause, every year, with 95% uncertainty intervals. The projected years (sepsis
    # shares held at their 2021 values) are shaded here and starred in B and C.
    top.axvspan(projection - 0.5, years[-1] + 0.5, color=F.PALETTE['neutral'], linewidth=0, zorder=0)
    for component, label in COMPONENTS:
        val, low, high = ([float(ui[(component, y)][k]) / 1e6 for y in years] for k in ('val', 'lower', 'upper'))
        top.fill_between(years, low, high, color=colours[component], alpha=0.16, linewidth=0, zorder=1)
        top.plot(years, val, color=colours[component], linewidth=1.5, zorder=2)
        data += [['A', y, component, 'All ages', v, lo, hi] for y, v, lo, hi in zip(years, val, low, high)]
    infectious = {y: float(ui[('infectious', y)]['upper']) / 1e6 for y in years}
    # The COVID-19 label goes on the year whose upper bound stands furthest above the mean of its neighbours.
    peak = max(years[1:-1], key=lambda y: infectious[y] - (infectious[y - 1] + infectious[y + 1]) / 2)
    top.annotate('COVID-19', (peak, infectious[peak]), xytext=(0, 3), textcoords='offset points', ha='center', va='bottom',
                 fontsize=F.CONFIG['font_size'] - 1, color=F.PALETTE['secondary'])
    top.set_xlim(years[0] - 0.5, years[-1] + 0.5)
    top.set_ylim(0, None)
    top.set_ylabel('Deaths (millions)')
    top.grid(axis='y', color=F.PALETTE['grid'], linewidth=0.5)
    F.panel_title(top, 'A', 'Sepsis-related deaths by underlying cause, India')
    handles = [Line2D([], [], color=colours[c], linewidth=1.5, label=l) for c, l in COMPONENTS]
    handles += [Patch(facecolor=F.PALETTE['muted'], alpha=0.25, label='95% uncertainty interval'),
                Patch(facecolor=F.PALETTE['neutral'], label=f'Projected ({projection}-{years[-1]})')]
    top.legend(handles=handles, loc='upper right', ncol=2, handlelength=1.6, columnspacing=1.2)

    # B and C: deaths by age group in the years with age detail, as stacked bars
    fills = dict(zip(groups, F.PALETTE['pastel']))
    for ax, letter, (component, label) in ((left, 'B', COMPONENTS[0]), (right, 'C', COMPONENTS[1])):
        for x, year in enumerate(age_years):
            base = 0.0
            for group in groups:
                value = by_age[(component, year, group)] / 1e6
                ax.bar(x, value, bottom=base, width=0.68, color=fills[group], edgecolor=F.PALETTE['surface'], linewidth=0.7, zorder=2)
                data.append([letter, year, component, group, value, '', ''])
                base += value
        ax.set_xticks(range(len(age_years)), [f'{y}*' if y >= projection else str(y) for y in age_years])
        ax.set_xlim(-0.6, len(age_years) - 0.4)
        ax.grid(axis='y', color=F.PALETTE['grid'], linewidth=0.5)
        ax.tick_params(axis='x', length=0)
        ax.set_ylabel('Deaths (millions)')
        F.panel_title(ax, letter, label.replace(' underlying cause', ''))
    fig.legend(handles=[Patch(facecolor=fills[g], label=g) for g in groups], loc='outside lower center', ncol=len(groups),
               handlelength=1.1, columnspacing=1.2)
    exported = F.save(fig, STEM)
    F.write_rows(f'{STEM}_data.csv', ['panel', 'year', 'component', 'age_group', 'deaths_millions', 'lower', 'upper'], data)
    first, last = (sum(by_age[(c, y, g)] for c in dict(COMPONENTS) for g in groups) for y in (age_years[0], age_years[-1]))
    # The caption assumes the configured order: the first two age groups are under 5 years, the last is 70 and older.
    under_five = [g for g in groups if g in list(groups)[:2]]
    share = lambda y, gs: 100 * sum(by_age[(c, y, g)] for c in dict(COMPONENTS) for g in gs) / sum(by_age[(c, y, g)]
                                                                                                   for c in dict(COMPONENTS) for g in groups)
    oldest = list(groups)[-1:]
    caption = (f'India\'s intervals come from its own GBD estimates. B and C show the {len(age_years)} years with age detail; '
               f'*{projection} onwards rest on sepsis shares held at their 2021 values. Children under 5 years made up '
               f'{share(age_years[0], under_five):.0f}% of sepsis-related deaths in {age_years[0]} and {share(age_years[-1], under_five):.0f}% in '
               f'{age_years[-1]}; people aged 70 years and older {share(age_years[0], oldest):.0f}% and {share(age_years[-1], oldest):.0f}%. '
               'COVID-19 deaths count as infectious.')
    F.write_report('03_figure_trends.json', __file__, dict(figure=STEM, years=f'{years[0]}-{years[-1]}', age_years=age_years),
                   inputs=[('state_estimates', 'uncertainty_annual.csv'), ('state_estimates', 'estimates_by_age.csv')], export=exported,
                   caption_note=F.lancet_text(caption))
    print(f'[03] Complete; {STEM}: India {years[0]}-{years[-1]} by type of underlying cause; by age in {len(age_years)} years '
          f'({first / 1e6:.2f} to {last / 1e6:.2f} million deaths)', flush=True)


if __name__ == '__main__':
    build_trends()

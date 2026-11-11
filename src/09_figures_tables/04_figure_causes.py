"""Figure 3: leading infectious (A) and non-infectious (B) underlying causes of sepsis-related deaths in India in
1990, 2019 and 2021, ranked and joined across years as in Figure 1 of the GBD 2021 sepsis paper."""
import math

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

import figures_common as F

STEM = 'Fig3'
PANELS = (('A', 'infectious', 'Infectious underlying causes'), ('B', 'non_infectious', 'Non-infectious underlying causes'))
# Gap and header in rows; box gap and minimum line space in inches; minimum text size in points.
GAP_ROWS, HEADER_ROWS, BOX_GAP, MIN_LINE_SPACE, MIN_SIZE = 0.9, 2.9, 0.035, 0.3, 4.75
HEADERS = ('Leading causes, {year}', 'Deaths, thousands\n(95% UI), {year}')


def amount(value):
    """Return deaths in thousands to three significant figures."""
    v = value / 1000
    if v <= 0:
        return '0'
    digits = 2 - int(math.floor(math.log10(v)))
    v = round(v, digits)
    return f'{v:,.{max(digits, 0)}f}'


def value_text(v):
    return f'{amount(v[0])} ({amount(v[1])}–{amount(v[2])})'


def ranked(rows, years, top):
    """Return {year: {cause: rank}} by deaths, the causes listed in each year (leading, then others) and the values."""
    values = {(int(r['year']), r['cause']): (float(r['val']), float(r['lower']), float(r['upper'])) for r in rows}
    # A cause with no deaths in a year (COVID-19 before 2020) is not ranked or listed in that year.
    ranks = {y: {c: i + 1 for i, c in enumerate(sorted((c for (yy, c), v in values.items() if yy == y and v[0] > 0),
                                                       key=lambda c: (-values[(y, c)][0], c)))} for y in years}
    leading = set().union(*({c for c, k in ranks[y].items() if k <= top} for y in years))
    columns = {}
    for y in years:
        head = sorted((c for c, k in ranks[y].items() if k <= top), key=ranks[y].get)
        # Below the leading causes: those leading in another year, with their rank in this one.
        tail = sorted((c for c in leading - set(head) if c in ranks[y]), key=ranks[y].get)
        columns[y] = (head, tail)
    return ranks, columns, values


def layout(fig, blocks, years, width):
    """Return the text size, the box widths (from the longest labels) and the line space, stepping the size down until the lines fit."""
    size = F.CONFIG['font_size'] - 1.5
    while True:
        names = max(F.text_width(fig, f'{ranks[y][c]} {F.short_cause(c)}', size) for ranks, cols, _ in blocks.values()
                    for y in years for part in cols[y] for c in part)
        names = max(names, F.text_width(fig, HEADERS[0].format(year=years[0]), size))
        numbers = max([F.text_width(fig, value_text(values[(y, c)]), size) for _, cols, values in blocks.values()
                       for y in years for part in cols[y] for c in part] +
                      [F.text_width(fig, line, size) for line in HEADERS[1].format(year=years[0]).split('\n')])
        box, value = names + 0.1, numbers + 0.12
        space = (width - 0.04 - len(years) * (box + BOX_GAP + value)) / (len(years) - 1)
        if space >= MIN_LINE_SPACE:
            return size, box, value, space
        size -= 0.25
        F.require(size >= MIN_SIZE, 'Figure 3 does not fit the page width at a legible text size')


def build_causes():
    F.style()
    # The years of IHME's published sepsis estimates, so no value here is projected.
    years, top = F.CONFIG['years']['causes'], F.CONFIG['ranked_causes_top']
    rows = [r for r in F.read_csv('state_estimates', 'uncertainty_by_cause.csv') if int(r['year']) in years and r['location'] == F.INDIA]
    blocks = {component: ranked([r for r in rows if r['component'] == component], years, top) for _, component, _ in PANELS}
    width = F.CONFIG['width_full']
    probe = plt.figure(figsize=(width, 1))
    size, box, value, space = layout(probe, blocks, years, width)
    plt.close(probe)
    row_inches, title_inches = size / 72 * 1.95, 0.4
    heights = {c: HEADER_ROWS + top + GAP_ROWS + max(len(cols[y][1]) for y in years) for c, (_, cols, _) in blocks.items()}
    height = round(sum(h * row_inches + title_inches for h in heights.values()) + 0.1, 2)
    fig = plt.figure(figsize=(width, height))
    ink, line, fall = F.PALETTE['ink'], F.PALETTE['two_group'][1], F.PALETTE['muted']
    starts = [0.02 + i * (box + BOX_GAP + value + space) for i in range(len(years))]
    data, bottom = [], height - 0.05
    for letter, component, title in PANELS:
        ranks, columns, values = blocks[component]
        h = heights[component] * row_inches
        bottom -= h + title_inches
        ax = fig.add_axes((0, bottom / height, 1, h / height))
        ax.set_xlim(0, width)
        ax.set_ylim(heights[component] - HEADER_ROWS + 0.5, -HEADER_ROWS + 0.5)
        ax.axis('off')
        F.panel_title(ax, letter, title)
        position = {}
        for x0, y in zip(starts, years):
            ax.text(x0, -0.9, HEADERS[0].format(year=y), fontsize=size, color=ink, va='bottom')
            ax.text(x0 + box + BOX_GAP, -0.9, HEADERS[1].format(year=y), fontsize=size, color=ink, va='bottom', linespacing=1.15)
            head, tail = columns[y]
            # Two outlined boxes per cause: rank and name; deaths with the 95% UI, from India's own GBD estimates.
            for row, cause in [(i, c) for i, c in enumerate(head)] + [(top + GAP_ROWS + i, c) for i, c in enumerate(tail)]:
                v = values[(y, cause)]
                for left, w in ((x0, box), (x0 + box + BOX_GAP, value)):
                    ax.add_patch(Rectangle((left, row - 0.4), w, 0.8, facecolor=F.PALETTE['surface'], edgecolor=line, linewidth=0.55))
                ax.text(x0 + 0.05, row, f'{ranks[y][cause]} {F.short_cause(cause)}', fontsize=size, va='center', color=ink)
                ax.text(x0 + box + BOX_GAP + value / 2, row, value_text(v), fontsize=size, va='center', ha='center', color=ink)
                position[(y, cause)] = (x0, row)
                data.append([letter, y, ranks[y][cause], cause, v[0], v[1], v[2], 'leading' if row < top else 'other'])
        # Lines from one year's value box to the next year's name box, all solid (the journal asks for few dotted lines): box
        # colour where the rank rose or held, a contrasting colour where it fell.
        for first, second in zip(years, years[1:]):
            for cause in {c for (y, c) in position if y == first} & {c for (y, c) in position if y == second}:
                (x0, r0), (x1, r1) = position[(first, cause)], position[(second, cause)]
                colour = line if ranks[second][cause] <= ranks[first][cause] else fall
                ax.plot([x0 + box + BOX_GAP + value, x1], [r0, r1], color=colour, linewidth=0.6, solid_capstyle='butt')
    exported = F.save(fig, STEM)
    F.write_rows(f'{STEM}_data.csv', ['panel', 'year', 'rank', 'cause', 'deaths', 'lower', 'upper', 'listed'], data)
    shortened = sorted({F.short_cause(r[3]) for r in data} & set(F.CONFIG['short_causes'].values()))
    caption = (f'Leading {top} underlying causes of sepsis-related deaths in India, all ages, in {", ".join(map(str, years[:-1]))}, and '
               f'{years[-1]}: (A) infectious causes, (B) non-infectious causes. Causes are connected by lines between years; blue lines '
               'are ranked increases (or no change in rank) and grey lines are ranked decreases. Below each list are the causes that '
               'rank among the leading ones in another year. Deaths in thousands with 95% uncertainty intervals, from India\'s own GBD '
               'estimates (approximate). *Excluding the level 4 cause counted with the infectious causes (neonatal sepsis, maternal '
               'sepsis, or urinary tract infections). COPD=chronic obstructive pulmonary disease. UTI=urinary tract infections and '
               'interstitial nephritis. STIs=sexually transmitted infections.'
               + (' iNTS=invasive non-typhoidal Salmonella.' if 'iNTS' in shortened else ''))
    F.write_report('04_figure_causes.json', __file__, dict(figure=STEM, years=years, leading=top, font_size=size, shortened=shortened),
                   inputs=[('state_estimates', 'uncertainty_by_cause.csv')], export=exported, caption_note=F.lancet_text(caption))
    print(f'[04] Complete; {STEM}: leading {top} infectious and non-infectious causes, India, {", ".join(map(str, years))} '
          f'(text {size:g} pt, {space:.2f} in for the lines)', flush=True)


if __name__ == '__main__':
    build_causes()

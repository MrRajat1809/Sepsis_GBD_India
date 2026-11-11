"""Figure 1: age-standardised sepsis-related death rate by state in 1990 and 2023, as maps of India on one logarithmic
colour scale, on the Survey of India state layer drawn as supplied and rasterised in the PDF."""
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.cm import ScalarMappable
from matplotlib.collections import PatchCollection
from matplotlib.colors import LogNorm
from matplotlib.patches import PathPatch
from matplotlib.path import Path

import figures_common as F

STEM = 'Fig1'
MAP = F.CONFIG['map']


def boundary():
    """Return the boundary records (with their GBD units), the rings of each and the archive, as checked by 01_raw_data/08."""
    records = F.read_csv('raw_data', MAP['boundary'])
    sources = {(r['source_path'], r['source_layer'], r['source_sha256']) for r in records}
    F.require(len(sources) == 1, f'Boundary records name {len(sources)} sources')
    (source, layer, digest), = sources
    F.require(F.sha256(F.ROOT / F.CONFIG['directories']['raw'] / source) == digest, f'{source} differs from the file checked by 01_raw_data/08')
    shapes = F.read_polygons(F.ROOT / F.CONFIG['directories']['raw'] / source, f'{layer}.shp')
    F.require([int(r['record']) for r in records] == list(range(1, len(shapes) + 1)), 'Boundary records and shapes differ')
    F.require([sum(len(ring) for ring in shape) for shape in shapes] == [int(r['points']) for r in records], 'Boundary point counts differ')
    return records, shapes, source


def compound_path(rings):
    """Return the rings of one shape as a single path, each ring a closed subpath."""
    vertices = np.concatenate(rings)
    codes = np.full(len(vertices), Path.LINETO, dtype=Path.code_type)
    start = 0
    for ring in rings:
        codes[start], codes[start + len(ring) - 1] = Path.MOVETO, Path.CLOSEPOLY
        start += len(ring)
    return Path(vertices, codes)


def label_point(rings):
    """Return the centroid of the largest ring."""
    best = None
    for ring in rings:
        origin = ring[0]
        x0, y0 = (ring[:-1] - origin).T
        x1, y1 = (ring[1:] - origin).T
        cross = x0 * y1 - x1 * y0
        area = cross.sum() / 2
        if best is None or abs(area) > abs(best[0]):
            best = (area, origin + np.array([((x0 + x1) * cross).sum(), ((y0 + y1) * cross).sum()]) / (6 * area))
    return best[1]


def scale(values):
    """Return the scale's ends, the nearest series members at or beyond the lowest and highest value, and the ticks between."""
    # 1 and 1.5 times a power of two times the unit; for 100: 100, 150, 200, 300, 400, 600, 800, 1,200.
    series = sorted(m * 2 ** k * MAP['scale_unit'] for k in range(-6, 10) for m in (1, 1.5))
    low = max(s for s in series if s <= min(values))
    high = min(s for s in series if s >= max(values))
    return low, high, [s for s in series if low <= s <= high]


def fills(values, ramp, norm):
    """Return the fill of each value, checking that fills darken as the value rises."""
    fill = {key: F.to_hex(ramp(float(norm(value)))) for key, value in values.items()}
    ordered = [F.hex_to_oklch(fill[key])[0] for key in sorted(values, key=values.get)]
    F.require(all(b <= a + 1e-6 for a, b in zip(ordered, ordered[1:])), 'Fills do not darken as the rate rises')
    return fill


def extent(shapes):
    """Return the map limits: every ring and callout, with a margin."""
    km = 1000  # The layer is in metres, the configuration in kilometres
    corners = np.array([[ring.min(axis=0), ring.max(axis=0)] for shape in shapes for ring in shape]).reshape(-1, 2)
    corners = np.vstack([corners, km * np.array(list(MAP['callouts_km'].values()))])
    margin = km * MAP['margin_km']
    return (corners[:, 0].min() - margin, corners[:, 0].max() + margin), (corners[:, 1].min() - margin, corners[:, 1].max() + margin)


def layout(limits):
    """Return the figure, map axes and scale axes, sized so the maps fill their width at true aspect (inches in the configuration)."""
    (x0, x1), (y0, y1) = limits
    width, box = F.CONFIG['width_full'], MAP['layout']
    panel = (width - box['panel_gap'] - 2 * box['side_margin']) / 2
    height = panel * (y1 - y0) / (x1 - x0)
    total = box['title_band'] + height + box['scale_band']
    fig = plt.figure(figsize=(width, total))
    axes = [fig.add_axes(((box['side_margin'] + i * (panel + box['panel_gap'])) / width, box['scale_band'] / total, panel / width, height / total))
            for i in range(2)]
    scale_axis = fig.add_axes(((width - box['scale_length']) / 2 / width, (box['scale_band'] - box['scale_gap'] - box['scale_thickness']) / total,
                               box['scale_length'] / width, box['scale_thickness'] / total))
    return fig, axes, scale_axis


def map_panel(ax, records, shapes, fill, limits):
    """Draw one map: each State/UT in its unit's fill, with labels and callouts."""
    # Areas the layer marks as disputed between States belong to no GBD unit and take the missing-data grey.
    fills = [fill[r['gbd_unit']] if r['gbd_unit'] else F.PALETTE['missing'] for r in records]
    # The small islands (no_border) are edged in their own fill so a white border does not hide them.
    edges = [f if r['state_code'] in MAP['no_border'] else F.PALETTE['surface'] for r, f in zip(records, fills)]
    patches = [PathPatch(compound_path(shape)) for shape in shapes]
    # White borders over a thin grey ring keep the palest fills distinct from the page. Rasterised, so the PDF does not
    # carry the boundary vectors.
    ring = MAP['border_width'] + 2 * MAP['outline_width']
    ax.add_collection(PatchCollection(patches, facecolors=F.PALETTE['muted'], edgecolors=F.PALETTE['muted'], linewidths=ring, rasterized=True))
    ax.add_collection(PatchCollection(patches, facecolors=fills, edgecolors=edges, linewidths=MAP['border_width'], rasterized=True))
    size, km = F.CONFIG['font_size'] - 1.5, 1000
    for record, shape, colour in zip(records, shapes, fills):
        code = record['state_code']
        if not record['gbd_unit'] or code in MAP['unlabelled']:
            continue
        text = MAP['label_text'].get(code, MAP['abbreviations'][record['gbd_unit']])
        anchor = label_point(shape)
        # Units too small to see: a swatch and label beside the map, joined to the unit by a leader line.
        if code in MAP['callouts_km']:
            x, y = (km * v for v in MAP['callouts_km'][code])
            left = x < anchor[0]
            ax.plot([anchor[0], x], [anchor[1], y], color=F.PALETTE['secondary'], linewidth=MAP['leader_width'], solid_capstyle='butt', zorder=3)
            ax.plot([x], [y], marker='s', markersize=MAP['swatch_size'], markerfacecolor=colour, markeredgecolor=F.PALETTE['muted'],
                    markeredgewidth=MAP['outline_width'], linestyle='none', zorder=4)
            ax.annotate(text, (x, y), xytext=(-MAP['swatch_size'] if left else MAP['swatch_size'], 0), textcoords='offset points',
                        ha='right' if left else 'left', va='center', fontsize=size, color=F.PALETTE['ink'])
        else:
            x, y = (km * np.array(MAP['label_points_km'][code])) if code in MAP['label_points_km'] else anchor
            ax.text(x, y, text, ha='center', va='center', fontsize=size, color=F.text_on(colour))
    ax.set_xlim(*limits[0])
    ax.set_ylim(*limits[1])
    ax.set_aspect('equal')
    ax.axis('off')


def colourbar(fig, scale_axis, ramp, norm, ticks):
    bar = fig.colorbar(ScalarMappable(norm=norm, cmap=ramp), cax=scale_axis, orientation='horizontal')
    bar.outline.set_visible(False)
    bar.solids.set_rasterized(True)
    bar.minorticks_off()
    bar.set_ticks(ticks, labels=[f'{t:,.0f}' for t in ticks])
    bar.ax.tick_params(length=2.5, width=0.6, labelsize=F.CONFIG['font_size'] - 1, colors=F.PALETTE['secondary'])
    bar.set_label('Sepsis-related deaths per 100,000, age-standardised (logarithmic scale)', color=F.PALETTE['secondary'],
                  fontsize=F.CONFIG['font_size'] - 0.5)


def build_map():
    F.style()
    plt.rcParams['path.simplify'] = False  # Boundaries drawn as supplied: every vertex
    year, base = F.CONFIG['years']['map'], F.CONFIG['years']['map_base']
    rates = {(r['location'], int(r['year'])): float(r['age_standardised_rate']) for r in F.read_csv('state_estimates', 'rates_annual.csv')
             if r['sex'] == 'Both' and int(r['year']) in (year, base)}
    records, shapes, source = boundary()
    units = sorted({r['gbd_unit'] for r in records} - {''})
    disputed = sum(not r['gbd_unit'] for r in records)
    F.require(set(units) == {l for l, _ in rates} - {F.INDIA}, 'The boundary units differ from the GBD units')
    F.require(set(MAP['abbreviations']) == set(units), 'Abbreviations do not cover the GBD units exactly')
    codes = {r['state_code'] for r in records}
    configured = set(MAP['callouts_km']) | set(MAP['label_points_km']) | set(MAP['unlabelled']) | set(MAP['no_border']) | set(MAP['label_text'])
    F.require(configured <= codes, f'Unknown States/UTs in the map configuration: {sorted(configured - codes)}')
    F.require(not set(MAP['callouts_km']) & set(MAP['label_points_km']), 'A State/UT has both a callout and a label point')
    labelled = {r['gbd_unit'] for r in records if r['gbd_unit'] and r['state_code'] not in MAP['unlabelled']}
    F.require(labelled == set(units), f'GBD units without a label: {sorted(set(units) - labelled)}')
    panels = (('a', 'A', base, f'{base}'), ('b', 'B', year, f'{year} (projected)'))
    values = {(y, u): rates[(u, y)] for _, _, y, _ in panels for u in units}
    low, high, ticks = scale(values.values())
    # One cream-to-crimson scale for both panels, so the change since 1990 reads as a shift in colour. Logarithmic: rates
    # span a tenfold range and fell proportionally, so equal steps along the bar are equal ratios.
    ramp, norm = F.colormap('heat', F.PALETTE['heat']), LogNorm(low, high)
    fill = fills(values, ramp, norm)
    limits = extent(shapes)
    fig, axes, scale_axis = layout(limits)
    for ax, (_, letter, y, title) in zip(axes, panels):
        map_panel(ax, records, shapes, {u: fill[(y, u)] for u in units}, limits)
        ax.set_title(letter, loc='left', fontsize=MAP['letter_size'])
        ax.set_title(title, loc='center')
    colourbar(fig, scale_axis, ramp, norm, ticks)
    exported = F.save(fig, STEM)
    measure = 'age_standardised_rate_per_100000'
    data = [[panel, u, MAP['abbreviations'][u], y, measure, values[(y, u)], fill[(y, u)]] for panel, _, y, _ in panels for u in units]
    F.write_rows(f'{STEM}_data.csv', ['panel', 'unit', 'abbreviation', 'year', 'measure', 'value', 'fill'], data)
    india = {y: rates[(F.INDIA, y)] for y in (base, year)}
    caption = (f'Both panels share one colour scale, logarithmic so that equal steps are equal ratios. India: {india[base]:.0f} per '
               f'100,000 in {base} and {india[year]:.0f} in {year}, a fall of {100 * (1 - india[year] / india[base]):.0f}%. JK and LA '
               '(Jammu and Kashmir, and Ladakh) are one GBD unit, as are the Other Union Territories (UTs: Andaman and Nicobar Islands, '
               'Chandigarh, Dadra and Nagar Haveli and Daman and Diu, Lakshadweep, and Puducherry); each shares one colour. Areas '
               'shown by the Survey of India as disputed between States are grey. Rates for '
               f'{year} rest on sepsis shares held at their 2021 values. State boundaries: {MAP["boundary_citation"]}')
    F.write_report('02_figure_map.json', __file__, dict(figure=STEM, units=len(units), states_uts=len(records) - disputed, disputed=disputed),
                   inputs=[('state_estimates', 'rates_annual.csv'), ('raw_data', MAP['boundary']), ('raw', source)],
                   export=exported, caption_note=F.lancet_text(caption),
                   scale=dict(low=low, high=high, ticks=ticks, logarithmic=True, ramp=F.PALETTE['heat']))
    print(f'[02] Complete; {STEM}: maps of {len(records) - disputed} States/UTs in {len(units)} GBD units, {base} and {year} on one '
          f'logarithmic scale ({low:,.0f}-{high:,.0f} per 100,000)', flush=True)


if __name__ == '__main__':
    build_map()

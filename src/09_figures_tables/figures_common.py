"""Style, colours, inputs, boundaries, figure and table export, and stage reports shared by the figure and table stages."""
import csv
import hashlib
import json
import math
import re
import struct
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.text import Text
from matplotlib.ticker import Formatter

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CONFIG_PATH = HERE / 'figures_config.json'
CONFIG = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
OUT = ROOT / 'outputs/figures_tables'
PALETTE = CONFIG['palette']
INDIA = CONFIG['india']


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read_csv(group, filename):
    """Return the rows of an input CSV, located by its directory group in the configuration, as dicts."""
    with (ROOT / CONFIG['directories'][group] / filename).open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


def write_report(filename, script, summary, inputs=(), **details):
    """Write a stage's JSON report (hashes of the script, configuration and inputs, summary and details) and return it."""
    OUT.mkdir(parents=True, exist_ok=True)
    report = dict(config_version=CONFIG['version'], generated_at_utc=datetime.now(timezone.utc).isoformat(),
                  script_sha256=sha256(script), figures_config_sha256=sha256(CONFIG_PATH),
                  inputs={f'{g}/{f}': sha256(ROOT / CONFIG['directories'][g] / f) for g, f in inputs}, summary=summary, **details)
    pending = OUT / (filename + '.tmp')
    pending.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    pending.replace(OUT / filename)
    return report


def number(value):
    """Return a float to six significant figures; other values unchanged."""
    return f'{value:.6g}' if isinstance(value, float) else value


def write_rows(filename, header, rows):
    """Write rows as a CSV in the output folder, floats to six significant figures, and return its path."""
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / filename
    pending = path.with_name(path.name + '.tmp')
    with pending.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        writer.writerows([number(v) for v in row] for row in rows)
    pending.replace(path)
    return path


# Colour ------------------------------------------------------------------------------------------------------------

def _to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _to_srgb(c):
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def hex_to_oklch(hex_colour):
    """Return the OKLCH lightness, chroma and hue (radians) of a hex colour."""
    r, g, b = (_to_linear(int(hex_colour[i:i + 2], 16) / 255) for i in (1, 3, 5))
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    L = 0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s
    a = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s
    bb = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s
    return L, math.hypot(a, bb), math.atan2(bb, a)


def oklch_to_hex(L, C, h):
    """Return the sRGB hex of an OKLCH colour, reducing chroma until it is inside the sRGB gamut."""
    for _ in range(60):
        a, b = C * math.cos(h), C * math.sin(h)
        l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
        m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
        s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
        rgb = (4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
               -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
               -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s)
        if all(-1e-9 <= c <= 1 + 1e-9 for c in rgb):
            return '#' + ''.join(f'{round(255 * _to_srgb(min(max(c, 0.0), 1.0))):02x}' for c in rgb)
        C *= 0.95
    raise ValueError('Colour out of gamut')


def second_ramp():
    """Return the second sequential ramp: the blue ramp's lightness steps carried to the second hue (computed, not chosen)."""
    blue = [hex_to_oklch(c) for c in PALETTE['sequential_blue']]
    anchor_blue = hex_to_oklch(PALETTE['categorical'][0])
    L0, C0, h0 = hex_to_oklch(PALETTE['second_sequential_hue'])
    return [oklch_to_hex(L, C * C0 / anchor_blue[1], h0) for L, C, _ in blue]


def tint(hex_colour, amount):
    """Return the colour mixed with the surface: amount 0 keeps it, 1 gives the surface."""
    a, b = (int(hex_colour[i:i + 2], 16) for i in (1, 3, 5)), (int(PALETTE['surface'][i:i + 2], 16) for i in (1, 3, 5))
    return '#' + ''.join(f'{round(x + (y - x) * amount):02x}' for x, y in zip(a, b))


def colormap(name, steps):
    return LinearSegmentedColormap.from_list(name, steps)


def text_width(fig, text, size):
    """Return the width in inches of a line of text at the given size."""
    t = fig.text(0, 0, text, fontsize=size)
    width = t.get_window_extent(fig.canvas.get_renderer()).width / fig.dpi
    t.remove()
    return width


def text_on(fill_hex):
    """Return ink or white for a label set inside a coloured fill, by the fill's lightness."""
    return PALETTE['ink'] if hex_to_oklch(fill_hex)[0] > 0.62 else '#ffffff'


def contrast(first_hex, second_hex):
    """Return the WCAG contrast ratio of two colours."""
    def luminance(h):
        r, g, b = (_to_linear(int(h[i:i + 2], 16) / 255) for i in (1, 3, 5))
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    high, low = sorted((luminance(first_hex), luminance(second_hex)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def to_hex(rgba):
    return '#' + ''.join(f'{round(255 * c):02x}' for c in rgba[:3])


# Boundaries ----------------------------------------------------------------------------------------------------------

def read_polygons(path, member):
    """Return the rings of every record of one .shp member of a zip archive, in record order, as arrays of (x, y)."""
    with zipfile.ZipFile(path) as archive:
        require(member in archive.namelist(), f'{Path(path).name}: no member {member}')
        data = archive.read(member)
    # Only parsed here; stage 01_raw_data/08 checks the file. Records follow the 100-byte file header; each record header
    # gives the content length in 16-bit words (big-endian), and the polygon content is little-endian.
    records, position = [], 100
    while position < len(data):
        length = 2 * struct.unpack('>i', data[position + 4:position + 8])[0]
        body = data[position + 8:position + 8 + length]
        parts, points = struct.unpack('<ii', body[36:44])
        starts = list(struct.unpack(f'<{parts}i', body[44:44 + 4 * parts])) + [points]
        xy = np.frombuffer(body, dtype='<f8', count=2 * points, offset=44 + 4 * parts).reshape(-1, 2)
        records.append([xy[a:b] for a, b in zip(starts, starts[1:])])
        position += 8 + length
    return records


# Figures -------------------------------------------------------------------------------------------------------------

def lancet_text(text):
    """Return text in the journal's number style: midline decimal points and en rules in ranges."""
    return re.sub(r'(?<=\d)-(?=\d)', '–', re.sub(r'(?<=\d)\.(?=\d)', '·', text))


class LancetFormatter(Formatter):
    """Tick formatter that passes another formatter's labels through lancet_text."""

    def __init__(self, inner):
        self.inner = inner

    def __call__(self, x, pos=None):
        return lancet_text(self.inner(x, pos))

    def format_ticks(self, values):
        return [lancet_text(t) for t in self.inner.format_ticks(values)]

    def get_offset(self):
        return lancet_text(self.inner.get_offset())


def style():
    """Set the matplotlib defaults shared by every figure."""
    plt.rcParams.update({
        'font.family': CONFIG['font_family'], 'font.size': CONFIG['font_size'], 'axes.titlesize': CONFIG['font_size'] + 0.5,
        'axes.labelsize': CONFIG['font_size'], 'xtick.labelsize': CONFIG['font_size'] - 0.5, 'ytick.labelsize': CONFIG['font_size'] - 0.5,
        'legend.fontsize': CONFIG['font_size'] - 0.5, 'text.color': PALETTE['ink'], 'axes.labelcolor': PALETTE['secondary'],
        'axes.edgecolor': PALETTE['baseline'], 'xtick.color': PALETTE['secondary'], 'ytick.color': PALETTE['secondary'],
        'axes.linewidth': 0.6, 'axes.spines.top': False, 'axes.spines.right': False, 'axes.axisbelow': True,
        'axes.grid': False, 'grid.color': PALETTE['grid'], 'grid.linestyle': '-', 'grid.linewidth': 0.5,
        'axes.facecolor': PALETTE['surface'], 'figure.facecolor': PALETTE['surface'], 'savefig.facecolor': PALETTE['surface'],
        'xtick.major.size': 2.5, 'ytick.major.size': 0, 'xtick.major.width': 0.6, 'lines.linewidth': 1.4,
        'lines.solid_capstyle': 'round', 'lines.solid_joinstyle': 'round', 'legend.frameon': False,
        'pdf.fonttype': 42, 'ps.fonttype': 42, 'svg.hashsalt': 'sepsis', 'axes.titlelocation': 'left',
        'axes.titlecolor': PALETTE['ink'], 'axes.formatter.useoffset': False})


def save(fig, stem):
    """Check a figure (no bold text, no overlapping titles or legends, nothing off the canvas) and export it as PDF and PNG,
    with every number in the journal's style (the data files keep plain decimals)."""
    for axis in fig.axes:
        for side in (axis.xaxis, axis.yaxis):
            side.set_major_formatter(LancetFormatter(side.get_major_formatter()))
            side.set_minor_formatter(LancetFormatter(side.get_minor_formatter()))
    for text in fig.findobj(Text):
        require(text.get_fontweight() in ('normal', 'regular', 400), f'{stem}: bold text')
        text.set_text(lancet_text(text.get_text()))
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    labels = [t for ax in fig.axes for t in (ax.title, ax._left_title, ax._right_title) if t.get_text()]
    labels += list(fig.legends) + [ax.get_legend() for ax in fig.axes if ax.get_legend()]
    boxes = [label.get_window_extent(renderer) for label in labels]
    for i, first in enumerate(boxes):
        for second in boxes[i + 1:]:
            require(not first.overlaps(second), f'{stem}: titles or legends overlap')
    for axis in fig.axes:
        box = axis.get_tightbbox(renderer)
        if box is not None:
            require(box.x0 >= -2 and box.y0 >= -2 and box.x1 <= fig.bbox.width + 2 and box.y1 <= fig.bbox.height + 2,
                    f'{stem}: labels extend beyond the canvas')
    OUT.mkdir(parents=True, exist_ok=True)
    records = {}
    # No creation date or producer, so a rerun writes identical files.
    for extension, metadata in (('pdf', {'CreationDate': None, 'Producer': None}), ('png', {'Software': None})):
        path = OUT / f'{stem}.{extension}'
        pending = path.with_name(path.name + '.tmp')
        fig.savefig(pending, format=extension, dpi=CONFIG['dpi'], metadata=metadata)
        pending.replace(path)
        records[path.name] = dict(sha256=sha256(path), bytes=path.stat().st_size)
    width, height = fig.get_size_inches()
    plt.close(fig)
    return dict(files=records, width_inches=round(float(width), 3), height_inches=round(float(height), 3))


def hbar(ax, y, start, end, height, colour, rounded=True, radius_points=1.2, gap_points=0.6):
    """Draw a horizontal bar from start to end with a surface-coloured gap around it; when rounded, only the end is rounded."""
    from matplotlib.patches import FancyBboxPatch, Rectangle
    left, right = sorted((start, end))
    width = right - left
    if width <= 0:
        return
    bottom = y - height / 2
    if not rounded:
        ax.add_patch(Rectangle((left, bottom), width, height, facecolor=colour, edgecolor=PALETTE['surface'],
                               linewidth=gap_points, zorder=2.2))
        return
    # The radius is converted from points to data units, so the axis limits must be set first.
    (x0, y0), (x1, y1) = ax.transData.transform((0, 0)), ax.transData.transform((1, 1))
    per_point = ax.figure.dpi / 72
    rx, ry = radius_points * per_point / abs(x1 - x0), radius_points * per_point / abs(y1 - y0)
    if width <= 2 * rx:
        ax.add_patch(Rectangle((left, bottom), width, height, facecolor=colour, edgecolor=PALETTE['surface'],
                               linewidth=gap_points, zorder=2.0))
        return
    ax.add_patch(FancyBboxPatch((left, bottom), width, height, boxstyle=f'round,pad=0,rounding_size={rx}',
                                mutation_aspect=ry / rx, facecolor=colour, edgecolor=PALETTE['surface'], linewidth=gap_points,
                                zorder=2.0))
    # A square patch over the start side leaves only the end rounded.
    square_left = start if end > start else end + rx
    ax.add_patch(Rectangle((square_left, bottom), width - rx, height, facecolor=colour, edgecolor='none', zorder=2.1))


def panel_title(ax, letter, title=''):
    """Title a panel in the authors' style (as in Figure 1): a large letter at the top left and a centred title."""
    ax.set_title(letter, loc='left', fontsize=CONFIG['map']['letter_size'])
    if title:
        ax.set_title(title, loc='center')


def short_cause(cause):
    return CONFIG['short_causes'].get(cause, cause)


def short_unit(unit):
    return CONFIG['short_units'].get(unit, unit)


def row_bands(fig, rows, top, row_height, left, right):
    """Draw light bands behind every second row below India's, and a rule under India's row; inches from the bottom left."""
    from matplotlib.lines import Line2D
    from matplotlib.patches import Rectangle
    # The bands sit behind the axes, so axes drawn over them need a transparent background.
    for i in range(2, rows, 2):
        fig.patches.append(Rectangle((left, top - (i + 1) * row_height), right - left, row_height, transform=fig.dpi_scale_trans,
                                     facecolor=PALETTE['band'], edgecolor='none', zorder=-1))
    fig.lines.append(Line2D([left, right], [top - row_height] * 2, transform=fig.dpi_scale_trans, color=PALETTE['ink'], linewidth=0.6,
                            solid_capstyle='butt', zorder=5))


def clean_axis(ax, grid='x'):
    """Add a light grid along one axis (none if grid is empty), with no ticks when the grid is along x."""
    if grid:
        ax.grid(axis=grid, color=PALETTE['grid'], linewidth=0.5)
    ax.tick_params(axis='both', length=0 if grid == 'x' else 2.5)


# Tables --------------------------------------------------------------------------------------------------------------

def tex_escape(text):
    return str(text).replace('\\', r'\textbackslash{}').replace('&', r'\&').replace('%', r'\%').replace('_', r'\_').replace('#', r'\#')


def write_table(stem, caption, header, rows, note=''):
    """Write a table as CSV and as a LaTeX longtable (booktabs) for the manuscript, and return the hashes of both."""
    write_rows(f'{stem}.csv', header, rows)
    columns = 'l' + 'r' * (len(header) - 1)
    lines = [r'\begin{longtable}{@{}' + columns + r'@{}}', r'\caption{' + tex_escape(caption) + r'}\\', r'\toprule',
             ' & '.join(tex_escape(h) for h in header) + r' \\', r'\midrule', r'\endhead']
    lines += [' & '.join(tex_escape(number(v)) for v in row) + r' \\' for row in rows]
    lines += [r'\bottomrule']
    if note:
        lines += [r'\multicolumn{' + str(len(header)) + r'}{@{}p{\linewidth}@{}}{\footnotesize ' + tex_escape(note) + r'}\\']
    lines += [r'\end{longtable}']
    path = OUT / f'{stem}.tex'
    pending = path.with_name(path.name + '.tmp')
    pending.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    pending.replace(path)
    return {f'{stem}.csv': sha256(OUT / f'{stem}.csv'), f'{stem}.tex': sha256(path)}


def thousands(value, digits=1):
    return f'{value / 1000:,.{digits}f}'


def with_interval(val, low, high, scale=1.0, digits=1):
    """Return 'value (low-high)', each divided by scale."""
    return f'{val / scale:,.{digits}f} ({low / scale:,.{digits}f}-{high / scale:,.{digits}f})'

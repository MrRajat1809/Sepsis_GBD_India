"""Check the state boundary layer of the Survey of India administrative boundary database (OVSF/1M/7) and write its
attribute table, with each State/UT's GBD unit, to data/processed/raw_data/state_boundary.csv. The geometry is not
copied: the figure stage reads it from the registered archive."""
import csv
import math
import struct
import zipfile

import raw_common as R

SPEC = R.CONFIG['state_boundary']


def shp_header(data):
    """Return the file code, length in bytes (stored in 16-bit words), version, shape type and box of a .shp or .shx."""
    code, = struct.unpack('>i', data[:4])
    length, = struct.unpack('>i', data[24:28])
    version, shape_type = struct.unpack('<ii', data[28:36])
    return code, 2 * length, version, shape_type, struct.unpack('<4d', data[36:68])


def same_box(first, second):
    """Return whether two bounding boxes agree to within the rounding of the file's writer."""
    return all(abs(a - b) <= SPEC['bounding_box_tolerance_m'] for a, b in zip(first, second))


def read_dbf(data):
    """Return the attribute records of a dBASE III .dbf, after checking its fields."""
    version, = struct.unpack('<B', data[:1])
    count, header, length = struct.unpack('<IHH', data[4:12])
    fields, offset = [], 32
    while data[offset] != 0x0D:
        raw = data[offset:offset + 32]
        fields.append([raw[:11].split(b'\0')[0].decode('ascii'), chr(raw[11]), raw[16], raw[17]])
        offset += 32
    R.require(version == 3 and offset + 1 == header, f'Unexpected .dbf header (version {version})')
    R.require(fields == SPEC['fields'], f'.dbf fields {fields}')
    records = []
    for i in range(count):
        raw = data[header + i * length:header + (i + 1) * length]
        R.require(raw[:1] == b' ', f'.dbf record {i + 1} is marked deleted')
        values, position = {}, 1
        for name, _, width, _ in fields:
            values[name] = raw[position:position + width].decode('ascii').strip()
            position += width
        records.append(values)
    return records


def ring_measures(points):
    """Return the signed area (positive when counter-clockwise) and the length of a closed ring of (x, y) points."""
    area = length = 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        area += x0 * y1 - x1 * y0
        length += math.hypot(x1 - x0, y1 - y0)
    return area / 2, length


def read_shapes(shp, shx, count):
    """Return each record's box, parts, holes, points, area and perimeter, checking its offset against the .shx and its box."""
    R.require(len(shx) == 100 + 8 * count, f'.shx has {(len(shx) - 100) // 8} records, the .dbf {count}')
    shapes, position = [], 100
    for number in range(1, count + 1):
        offset, length = (2 * v for v in struct.unpack('>ii', shx[100 + 8 * (number - 1):108 + 8 * (number - 1)]))
        found, content = struct.unpack('>ii', shp[position:position + 8])
        R.require(offset == position and found == number and 2 * content == length, f'.shp record {number}: offset or length differs from the .shx')
        body = shp[position + 8:position + 8 + length]
        shape_type, = struct.unpack('<i', body[:4])
        R.require(shape_type == SPEC['shape_type'], f'.shp record {number}: shape type {shape_type}')
        box = struct.unpack('<4d', body[4:36])
        parts, count_points = struct.unpack('<ii', body[36:44])
        starts = struct.unpack(f'<{parts}i', body[44:44 + 4 * parts])
        flat = struct.unpack(f'<{2 * count_points}d', body[44 + 4 * parts:44 + 4 * parts + 16 * count_points])
        R.require(44 + 4 * parts + 16 * count_points == length, f'.shp record {number}: content length')
        points = list(zip(flat[0::2], flat[1::2]))
        xs, ys = flat[0::2], flat[1::2]
        R.require(same_box(box, (min(xs), min(ys), max(xs), max(ys))), f'.shp record {number}: bounding box differs from its points')
        area = perimeter = 0.0
        holes = 0
        for start, end in zip(starts, list(starts[1:]) + [count_points]):
            ring = points[start:end]
            R.require(len(ring) >= 4 and ring[0] == ring[-1], f'.shp record {number}: ring at {start} is not closed')
            signed, length_ring = ring_measures(ring)
            # Shapefile outer rings run clockwise and holes counter-clockwise, so -signed adds outers and removes holes.
            holes += signed > 0
            area -= signed
            perimeter += length_ring
        shapes.append(dict(box=box, parts=parts, holes=holes, points=count_points, area=area, perimeter=perimeter))
        position += 8 + length
    R.require(position == len(shp), '.shp has data after its last record')
    return shapes


def gbd2023_units():
    """Return India and its subnational units as named in the GBD 2023 all-cause download."""
    return {r['location_name'] for entry in R.files_for('allcause') for r in R.results_rows(R.RAW / entry['path'])}


def check_state_boundary():
    path = R.RAW / SPEC['path']
    entry = next(f for f in R.CONFIG['files'] if f['path'] == SPEC['path'])
    digest = R.sha256(path)
    R.require(digest == entry['sha256'], f'{SPEC["path"]} differs from its registered checksum')
    with zipfile.ZipFile(path) as archive:
        R.require(sorted(archive.namelist()) == SPEC['members'], f'{SPEC["path"]}: members {archive.namelist()}')
        layer = {name.rsplit('.', 1)[1].lower(): name for name in SPEC['members'] if name.rsplit('.', 1)[0] == SPEC['layer']}
        member = {extension: archive.read(layer[extension]) for extension in ('cpg', 'prj', 'dbf', 'shp', 'shx')}
    R.require(member['cpg'].decode('ascii') == SPEC['encoding'], f'Unexpected encoding: {member["cpg"]!r}')
    R.require(member['prj'].decode('ascii') == SPEC['projection'], f'Unexpected projection: {member["prj"][:80]}')
    records = read_dbf(member['dbf'])
    header = shp_header(member['shp'])
    # 9994 and 1000 are the fixed file code and version of every shapefile.
    R.require(header[:4] == (9994, len(member['shp']), 1000, SPEC['shape_type']), f'.shp header {header[:4]}')
    R.require(shp_header(member['shx'])[2:] == header[2:] and shp_header(member['shx'])[1] == len(member['shx']), '.shx header differs from the .shp')
    shapes = read_shapes(member['shp'], member['shx'], len(records))
    boxes = [s['box'] for s in shapes]
    R.require(same_box(header[4], (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))),
              '.shp bounding box differs from its records')
    units, tolerance, rows = SPEC['units'], SPEC['geometry_tolerance'], []
    code_of = {name: code for code, (name, _) in units.items()}
    names = [r['STATE'] for r in records]
    # Besides the States/UTs the layer holds areas marked as disputed between States; they belong to no GBD unit.
    R.require(sorted(names) == sorted(list(code_of) + SPEC['disputed']) and len(set(names)) == len(names), f'States/UTs {sorted(names)}')
    perimeter_differs = []
    for number, (record, shape) in enumerate(zip(records, shapes), start=1):
        name = record['STATE']
        code = code_of.get(name, '')
        unit = units[code][1] if code else ''
        R.require(record['OBJECTID'] == str(number), f'{name}: OBJECTID {record["OBJECTID"]}')
        stored = float(record['Shape_Area'])
        R.require(abs(shape['area'] / stored - 1) <= tolerance, f'{name}: area computed {shape["area"]:.1f}, stored {stored:.1f}')
        # A few records, listed in the configuration, store a perimeter shorter than their rings; their areas still match.
        if abs(shape['perimeter'] / float(record['Shape_Leng']) - 1) > tolerance:
            perimeter_differs.append(name)
        rows.append([number, code, name, unit, shape['parts'], shape['holes'], shape['points'], f'{shape["area"] / 1e6:.3f}',
                     SPEC['path'], SPEC['layer'], digest])
    R.require(sorted(perimeter_differs) == SPEC['perimeter_differs'], f'Stored perimeters differ for {sorted(perimeter_differs)}')
    gbd = gbd2023_units() - {SPEC['national']}
    mapped = {u for _, u in units.values()}
    R.require(mapped == gbd, f'States/UTs map onto different units from GBD 2023: {sorted(mapped ^ gbd)}')
    out = R.ROOT / 'data/processed/raw_data' / 'state_boundary.csv'
    out.parent.mkdir(parents=True, exist_ok=True)
    pending = out.with_name(out.name + '.tmp')
    with pending.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream)
        writer.writerow(['record', 'state_code', 'state_name', 'gbd_unit', 'parts', 'holes', 'points', 'projected_area_km2',
                         'source_path', 'source_layer', 'source_sha256'])
        writer.writerows(rows)
    pending.replace(out)
    area_ratios = [s['area'] / float(r['Shape_Area']) for r, s in zip(records, shapes)]
    perimeter_ratios = {r['STATE']: s['perimeter'] / float(r['Shape_Leng']) for r, s in zip(records, shapes) if r['STATE'] in perimeter_differs}
    summary = dict(records=len(records), states_uts=len(units), disputed=len(SPEC['disputed']), gbd_units=len(mapped),
                   parts=sum(s['parts'] for s in shapes), holes=sum(s['holes'] for s in shapes), points=sum(s['points'] for s in shapes),
                   projected_area_km2=round(sum(s['area'] for s in shapes) / 1e6))
    R.write_report('08_state_boundary_qc.json', __file__, summary, status='PASSED',
                   checks=dict(area_ratio_range=[min(area_ratios), max(area_ratios)], perimeter_ratios_listed=perimeter_ratios,
                               bounding_box_m=list(header[4])))
    print(f'[08] Complete; {len(units)} States/UTs and {len(SPEC["disputed"])} disputed areas ({summary["points"]:,} points); '
          f'States/UTs map onto {len(mapped)} GBD units; projected area {summary["projected_area_km2"]:,} km2', flush=True)


if __name__ == '__main__':
    check_state_boundary()

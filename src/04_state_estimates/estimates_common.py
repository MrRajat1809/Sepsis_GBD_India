"""Shared paths, readers, cause map, shares, interpolation and reports for the state estimate stages, and the engine that
recomputes the annual estimates under drawn inputs or other assumptions (stages 09 and 10)."""
import csv
import hashlib
import io
import json
import math
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CONFIG_PATH = HERE / 'estimates_config.json'
CONFIG = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
CAUSES_PATH = ROOT / 'src/common/gbd_causes.json'
CAUSES = json.loads(CAUSES_PATH.read_text(encoding='utf-8'))
RAW_CONFIG = json.loads((ROOT / CONFIG['raw_config']).read_text(encoding='utf-8'))
RAW = ROOT / CONFIG['raw_directory']
APPENDIX = ROOT / CONFIG['appendix_directory']
WORK = ROOT / 'data/processed/state_estimates'
OUT = ROOT / 'outputs/state_estimates'
TOL = CONFIG['tolerances']
AGES = CAUSES['age_groups']
BANDS = CAUSES['sepsis_age_bands']
BAND_OF = {age: band for band, ages in BANDS.items() for age in ages}
SETS = CAUSES['infectious_underlying_causes']
# Level 4 causes counted on their own, moved out of their level 3 parent: {cause: parent}.
MOVED = {cause: CAUSES['level4_causes'][cause] for cause in SETS['level4']}
BENCHMARKS = CONFIG['benchmark_years']
YEARS = range(CONFIG['series_years'][0], CONFIG['series_years'][1] + 1)
# Components of a cause in the cause map of stage 01.
INFECTIOUS, NON_INFECTIOUS, ZERO, NOT_USED = 'infectious', 'non_infectious', 'zero_share', 'not_used'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write_report(filename, script, summary, **details):
    OUT.mkdir(parents=True, exist_ok=True)
    report = dict(config_version=CONFIG['version'], generated_at_utc=datetime.now(timezone.utc).isoformat(),
                  script_sha256=sha256(script), estimates_config_sha256=sha256(CONFIG_PATH),
                  common_sha256={p.name: sha256(p) for p in sorted((ROOT / 'src/common').glob('*.json'))},
                  summary=summary, **details)
    pending = OUT / (filename + '.tmp')
    pending.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    pending.replace(OUT / filename)
    return report


def number(value):
    """Return a value as written to CSV: floats with 12 significant digits, anything else unchanged."""
    return f'{value:.12g}' if isinstance(value, float) else value


def write_csv(filename, header, rows):
    WORK.mkdir(parents=True, exist_ok=True)
    path = WORK / filename
    pending = path.with_name(path.name + '.tmp')
    with pending.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        writer.writerows([number(v) for v in row] for row in rows)
    pending.replace(path)
    return path


def read_csv(filename, directory=WORK):
    with (directory / filename).open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


def raw_file(path):
    """Return the full path of a file registered in raw_config.json, after checking it against its registered SHA-256."""
    entry = next((f for f in RAW_CONFIG['files'] if f['path'] == path), None)
    require(entry is not None, f'{path} is not registered in {CONFIG["raw_config"]}')
    full = RAW / path
    require(full.is_file() and sha256(full) == entry['sha256'], f'{full} is missing or differs from its registered checksum')
    return full


def request_files(requests):
    """Return the registered raw files of the given Results Tool requests."""
    files = [f for f in RAW_CONFIG['files'] if f['request'] in requests]
    require(files, f'No registered files for {requests}')
    return files


def request_years(requests):
    """Return every year covered by the files of the given requests, whose 'years' read like '1990-1996' or '1990, 2019, 2021'."""
    years = set()
    for entry in request_files(requests):
        for part in entry['years'].split(','):
            low, _, high = part.strip().partition('-')
            years.update(range(int(low), int(high or low) + 1))
    return sorted(years)


def archive_rows(entry):
    """Yield the rows of the CSV in one registered Results Tool archive."""
    with zipfile.ZipFile(raw_file(entry['path'])) as archive:
        member = next(m for m in archive.namelist() if m.lower().endswith('.csv'))
        with archive.open(member) as stream:
            yield from csv.DictReader(io.TextIOWrapper(stream, encoding='utf-8-sig', newline=''))


def cause_names(requests):
    return {r['cause_name'] for entry in request_files(requests) for r in archive_rows(entry)}


def results(requests, key_fields, measure=None, locations=None, causes=None, metric='Number', interval=False):
    """Return {key: value} of one metric in registered Results Tool archives, with optional filters; (val, lower, upper) if interval."""
    values = {}
    for entry in request_files(requests):
        for r in archive_rows(entry):
            if (r['metric_name'] != metric or (measure and r['measure_name'] != measure)
                    or (locations and r['location_name'] not in locations) or (causes and r['cause_name'] not in causes)):
                continue
            key = tuple(int(r[f]) if f == 'year' else r[f] for f in key_fields)
            require(key not in values, f'{entry["path"]}: duplicate {key}')
            values[key] = (float(r['val']), float(r['lower']), float(r['upper'])) if interval else float(r['val'])
    require(values, f'No values read from {requests}')
    return values


def haq_index():
    """Return {(location, year): HAQ Index} for India, its units (GBD 2023 names) and the world, from the GBD 2016 release."""
    spec = RAW_CONFIG['haq']
    aliases, keep = spec['name_aliases'], {spec['national'], spec['global']}
    values = {}
    with zipfile.ZipFile(raw_file(spec['path'])) as archive:
        # The archive also holds a codebook CSV.
        member = next(m for m in archive.namelist() if m.lower().endswith('.csv') and 'CODEBOOK' not in m.upper())
        with archive.open(member) as stream:
            for r in csv.DictReader(io.TextIOWrapper(stream, encoding='utf-8-sig', newline='')):
                if r['indicator_id'] == spec['index_indicator_id'] and (r['location_name'] in keep or r['parent_location'] == spec['national']):
                    values[(aliases.get(r['location_name'], r['location_name']), int(r['year_id']))] = float(r['val'])
    return values


def population_by_age():
    """Return population by location, age group and year: GBD 2023 all-cause deaths divided by the all-cause death rate."""
    requests = CONFIG['requests']['gbd2023_population_by_age']
    key = ('location_name', 'age_name', 'year')
    number = results(requests, key, measure=CONFIG['deaths'])
    rate = results(requests, key, measure=CONFIG['deaths'], metric='Rate')
    return {k: number[k] / rate[k] * 1e5 for k in number if k[1] in AGES}


def standard_weights():
    """Return the weight of each of the ten age groups: its share of the GBD world population age standard."""
    printed = {r['age_group']: float(r['percent']) for r in read_csv('standard_population.csv', APPENDIX)}
    groups = CONFIG['standard_population_groups']
    used = [g for parts in groups.values() for g in parts]
    require(sorted(used) == sorted(printed) and list(groups) == AGES, 'Standard population groups do not match')
    return {a: sum(printed[g] for g in parts) / sum(printed.values()) for a, parts in groups.items()}


def count_spread(by_age, causes):
    """Return the spread of each non-infectious cause's deaths across age bands, from the estimates by age of stage 04."""
    deaths = defaultdict(float)
    for r in by_age:
        if causes[r['cause']]['component'] == NON_INFECTIOUS:
            deaths[(r['location'], r['cause'], int(r['year']), BAND_OF[r['age_group']])] += float(r['deaths'])
    return band_spread(deaths, CONFIG['india'])


def standardised_spread(by_age, causes, weights, population):
    """Return the spread of each non-infectious cause's age-standardised death rate across age bands (ten groups, GBD standard)."""
    amounts = defaultdict(float)
    for r in by_age:
        if causes[r['cause']]['component'] == NON_INFECTIOUS:
            location, year, age = r['location'], int(r['year']), r['age_group']
            amounts[(location, r['cause'], year, BAND_OF[age])] += weights[age] * float(r['deaths']) / population[(location, age, year)]
    return band_spread(amounts, CONFIG['india'])


def cause_map(gbd_round):
    """Return {cause: row} of the cause map written by stage 01, for 'gbd2021' or 'gbd2023'."""
    rows = {r['cause']: r for r in read_csv('cause_map.csv') if r['round'] == gbd_round}
    require(rows, f'No causes mapped for {gbd_round}')
    return rows


def adjusted(values, cause, less, key):
    """Return a cause's deaths, YLLs or rate less those of the level 4 causes moved out of it; key(cause) gives the lookup key."""
    value = values.get(key(cause), 0.0)
    # The parent's reported figure includes the moved causes, which are counted on their own.
    for child in filter(None, less.split(';')):
        value -= values.get(key(child), 0.0)
    return value


def shares():
    """Return {(share_group, age_band, year): share} for the benchmark years, from stage 02."""
    return {(r['share_group'], r['age_band'], int(r['year'])): float(r['share']) for r in read_csv('sepsis_shares.csv')}


def scaled_share(share, k):
    """Return a non-infectious share scaled by k and capped at 1, since no more than all deaths from a cause can be sepsis-related."""
    return min(1.0, k * share)


def scaling_factors():
    """Return the scaling factor k by benchmark year, from stage 03."""
    return {int(r['year']): float(r['k']) for r in read_csv('scaling_factors.csv')}


def interpolate(points, year):
    """Return the value in a year, interpolated linearly between {year: value} points and held at the last one after it."""
    years = sorted(points)
    require(years[0] <= year, f'{year} is before the first point {years[0]}')
    if year >= years[-1]:
        return points[years[-1]]
    low = max(y for y in years if y <= year)
    high = min(y for y in years if y > year)
    t = (year - low) / (high - low)
    return points[low] * (1 - t) + points[high] * t


def shares_in(year, table):
    """Return the shares in any year: interpolated between the benchmark years and held at the last one."""
    groups = defaultdict(dict)
    for (group, band, y), value in table.items():
        groups[(group, band)][y] = value
    return {key: interpolate(points, year) for key, points in groups.items()}


def band_spread(amounts, fallback):
    """Return {(location, cause): {year: {band: weight}}} from {(location, cause, year, band): amount}, and the cases that used the fallback."""
    totals = defaultdict(float)
    for (location, cause, year, band), value in amounts.items():
        totals[(location, cause, year)] += value
    spread, used = defaultdict(dict), []
    for (location, cause, year), total in totals.items():
        source = location
        # A location with nothing for a cause in a year takes the fallback location's spread.
        if total <= 0:
            source = fallback
            used.append((location, cause, year))
            require(totals[(fallback, cause, year)] > 0, f'{cause} {year}: nothing by age in {fallback} either')
        spread[(location, cause)][year] = {b: amounts.get((source, cause, year, b), 0.0) / totals[(source, cause, year)]
                                           for b in BANDS}
    return spread, used


def spread_in(points, year):
    """Return the band spread in any year within the years with age detail, interpolated linearly between them."""
    if year in points:
        return points[year]
    low = max(y for y in points if y < year)
    high = min(y for y in points if y > year)
    t = (year - low) / (high - low)
    return {b: points[low][b] * (1 - t) + points[high][b] * t for b in BANDS}


def ratio_range(name, pairs, tolerance):
    """Require every (value, reference) pair with a non-zero reference to agree within the tolerance; return the ratio range."""
    ratios = [v / r for v, r in pairs if r]
    require(ratios, f'{name}: nothing to compare')
    low, high = min(ratios), max(ratios)
    require(abs(low - 1) <= tolerance and abs(high - 1) <= tolerance, f'{name}: ratios {low:.12f}-{high:.12f}')
    return dict(n=len(ratios), min=low, max=high)


# 97.5th percentile of the standard normal: a 95% interval spans 2 * Z95 = 3.92 standard deviations.
Z95 = 1.959963984540054
# Arrays returned by run_engine, each [location, sex, year, draw].
MEASURES = ('infectious', 'non_infectious', 'sepsis_deaths', 'asr_infectious', 'asr_non_infectious', 'age_standardised_rate')


def log_sigma(val, lower, upper):
    """Return the log-scale spread of a log-normal with mean val and standard deviation (upper - lower) / 3.92."""
    # The mean is the reported value, as IHME reports the mean of its draws. Matching the mean and standard deviation, rather
    # than fitting the interval on the log scale, keeps a lower bound near zero from implying an implausibly heavy upper tail.
    if val <= 0 or upper <= lower:
        return 0.0
    return math.sqrt(math.log(1 + ((upper - lower) / (2 * Z95 * val)) ** 2))


def scatter(point, sigma, rng, draws):
    """Return draws (on a new last axis) of log-normal inputs with mean point and log-scale spread sigma; point itself if rng is None."""
    if rng is None:
        return np.repeat(point[..., None], draws, axis=-1)
    z = rng.standard_normal(point.shape + (draws,))
    # Subtracting sigma^2 / 2 keeps the mean of the draws at point.
    return point[..., None] * np.exp(sigma[..., None] * z - sigma[..., None] ** 2 / 2)


def engine_inputs():
    """Return the arrays from which run_engine recomputes the annual estimates, each input with the log-scale spread of its interval."""
    causes = {c: r for c, r in cause_map('gbd2023').items() if r['component'] != NOT_USED}
    names = sorted(causes)
    code = {INFECTIOUS: 0, NON_INFECTIOUS: 1, ZERO: 2}
    component = np.array([code[causes[c]['component']] for c in names])
    # Shares as [share group, band, benchmark year], each varying with the interval of the Table S10 sepsis count behind it.
    table = read_csv('sepsis_shares.csv')
    groups, bands = sorted({r['share_group'] for r in table}), list(BANDS)
    gi, bi = {g: i for i, g in enumerate(groups)}, {b: i for i, b in enumerate(bands)}
    yi = {y: i for i, y in enumerate(BENCHMARKS)}
    f = np.zeros((len(groups), len(bands), len(BENCHMARKS)))
    f_sigma = np.zeros(f.shape)
    for r in table:
        key = (gi[r['share_group']], bi[r['age_band']], yi[int(r['year'])])
        f[key] = float(r['share'])
        f_sigma[key] = log_sigma(float(r['sepsis_deaths']), float(r['sepsis_lower']), float(r['sepsis_upper']))
    # Share group 0 is a placeholder for causes without a share group; run_engine sets their shares to 1 or 0.
    group_of = np.array([gi[causes[c]['share_group']] if causes[c]['component'] == NON_INFECTIOUS else 0 for c in names])

    # k reproduces India's Table S8 non-infectious total in each benchmark year from India's GBD 2021 deaths (stage 03);
    # pairs holds those deaths as (share group, band, deaths) arrays.
    factors = read_csv('scaling_factors.csv')
    target = np.array([float(r['ihme_non_infectious']) for r in factors])
    target_sigma = np.array([log_sigma(float(r['ihme_non_infectious']), float(r['ihme_lower']), float(r['ihme_upper']))
                             for r in factors])
    gbd2021 = cause_map('gbd2021')
    r6 = results(CONFIG['requests']['gbd2021'], ('age_name', 'cause_name', 'year'), measure=CONFIG['deaths'],
                 locations={CONFIG['india']})
    pairs = []
    for year in BENCHMARKS:
        rows = [(gi[r['share_group']], bi[BAND_OF[a]], adjusted(r6, c, r['less'], lambda x: (a, x, year)))
                for c, r in sorted(gbd2021.items()) if r['component'] == NON_INFECTIOUS for a in AGES]
        pairs.append(tuple(np.array(v) for v in zip(*rows)))

    by_age = read_csv('estimates_by_age.csv')
    locations = sorted({r['location'] for r in by_age})
    units = [l for l in locations if l != CONFIG['india']]
    # The same deaths by unit, for solving k when each unit's shares are shifted (HAQ analysis, stage 10).
    r6_units = results(CONFIG['requests']['gbd2021'], ('location_name', 'age_name', 'cause_name', 'year'),
                       measure=CONFIG['deaths'], locations=set(units))
    require({k[0] for k in r6_units} == set(units), 'GBD 2021 units differ from GBD 2023 units')
    unit_pairs = []
    for year in BENCHMARKS:
        rows = [(ui, gi[r['share_group']], bi[BAND_OF[a]], adjusted(r6_units, c, r['less'], lambda x: (u, a, x, year)))
                for ui, u in enumerate(units) for c, r in sorted(gbd2021.items()) if r['component'] == NON_INFECTIOUS for a in AGES]
        unit_pairs.append(tuple(np.array(v) for v in zip(*rows)))
    sexes, years = CONFIG['sexes'], list(YEARS)
    level3 = set(names) - set(MOVED)
    key_fields = ('location_name', 'sex_name', 'cause_name', 'year')

    def cells(parts, places, metric):
        """Return each cause's values as [place, sex, cause, year], parents less their moved level 4 causes, and their log-scale spreads."""
        values = {}
        for requests, wanted in parts:
            values.update(results(requests, key_fields, measure=CONFIG['deaths'], causes=wanted, metric=metric, interval=True))
        val = {k: v[0] for k, v in values.items()}
        point = np.zeros((len(places), len(sexes), len(names), len(years)))
        sigma = np.zeros(point.shape)
        for li, l in enumerate(places):
            for si, s in enumerate(sexes):
                for ci, c in enumerate(names):
                    for ti, y in enumerate(years):
                        point[li, si, ci, ti] = adjusted(val, c, causes[c]['less'], lambda x: (l, s, x, y))
                        # A parent less its moved causes takes the spread of the parent's own interval.
                        sigma[li, si, ci, ti] = log_sigma(*values.get((l, s, c, y), (0.0, 0.0, 0.0)))
        return point, sigma

    # India last: the units' deaths for the main run, and India's own rows for the national run that sets India's interval.
    deaths, deaths_sigma = cells([(CONFIG['requests']['gbd2023_annual'], level3 | set(MOVED))], units + [CONFIG['india']], 'Number')
    # The age-standardised rates of the moved level 4 causes are in a separate request.
    rate_requests = CONFIG['requests']['gbd2023_age_standardised']
    asr, asr_sigma = cells([(rate_requests[:1], level3), (rate_requests[1:], set(MOVED))], locations, 'Rate')

    def spread_array(points, places):
        """Return band spreads as [place, cause, band, year]; zero for causes without a spread (infectious, zero share)."""
        out = np.zeros((len(places), len(names), len(bands), len(years)))
        for li, l in enumerate(places):
            for ci, c in enumerate(names):
                if (l, c) in points:
                    for ti, y in enumerate(years):
                        w = spread_in(points[(l, c)], y)
                        out[li, ci, :, ti] = [w[b] for b in bands]
        return out

    count_points, _ = count_spread(by_age, causes)
    standard_points, _ = standardised_spread(by_age, causes, standard_weights(), population_by_age())
    return dict(names=names, component=component, group_of=group_of, f=f, f_sigma=f_sigma, target=target,
                target_sigma=target_sigma, pairs=pairs, unit_pairs=unit_pairs, units=units, locations=locations, sexes=sexes, years=years,
                deaths=deaths[:-1], deaths_sigma=deaths_sigma[:-1], asr=asr, asr_sigma=asr_sigma,
                national_deaths=deaths[-1:], national_deaths_sigma=deaths_sigma[-1:],
                count_spread=spread_array(count_points, units), national_spread=spread_array(count_points, [CONFIG['india']]),
                standard_spread=spread_array(standard_points, locations))


def benchmark_at(values, year, schedule):
    """Return the values in one year along the first (benchmark) axis: interpolated and held after the last, or the 'nearest'."""
    if schedule == 'nearest':
        # A tie between two benchmark years goes to the earlier one.
        return values[min(range(len(BENCHMARKS)), key=lambda i: (abs(BENCHMARKS[i] - year), BENCHMARKS[i]))]
    if year >= BENCHMARKS[-1]:
        return values[-1]
    high = next(i for i, y in enumerate(BENCHMARKS) if y > year)
    t = (year - BENCHMARKS[high - 1]) / (BENCHMARKS[high] - BENCHMARKS[high - 1])
    return values[high - 1] * (1 - t) + values[high] * t


def shifted(f, shift):
    """Return shares moved on the logit scale, logit^-1(logit(f) + shift); a share of 0 stays 0."""
    with np.errstate(divide='ignore'):
        return 1.0 / (1.0 + np.exp(-(np.log(f) - np.log1p(-f) + shift)))


def solve_k_draws(pairs, f, target, unit_shift=None):
    """Solve k for each draw so that India's capped non-infectious deaths in the GBD 2021 round equal the target, as stage 03 does."""
    if unit_shift is None:
        groups, bands, deaths = pairs
        share = f[groups, bands]
    else:
        # Pairs by unit, with each unit's shares moved first by its logit shift.
        units, groups, bands, deaths = pairs
        share = shifted(f[groups, bands], unit_shift[units][:, None])
    # Bisection on 0-10, as in stage 03, for every draw at once.
    low, high = np.zeros(target.shape), np.full(target.shape, 10.0)
    for _ in range(200):
        middle = (low + high) / 2
        below = (np.minimum(1.0, middle * share) * deaths[:, None]).sum(axis=0) < target
        low, high = np.where(below, middle, low), np.where(below, high, middle)
    return (low + high) / 2


def run_engine(inputs, draws=1, rng=None, schedule='interpolate', scale=True, drop=(), shift=None, projection=None, national=False,
               cause_years=()):
    """Return annual totals by location (the 31 units, then India), sex, year and draw, and k by benchmark year and draw."""
    I = inputs
    require(not (national and shift is not None), 'The national run takes no shift')
    # Shares as [benchmark year, share group, band, draw].
    f_draws = np.moveaxis(scatter(I['f'], I['f_sigma'], rng, draws), 2, 0)
    if scale:
        # k is solved again in every draw. With a shift ('benchmark' is [31 units, benchmark year]) it is solved on the units'
        # GBD 2021 deaths with shifted shares, so that India's GBD 2021 total is unchanged.
        target = scatter(I['target'], I['target_sigma'], rng, draws)
        k = np.stack([solve_k_draws(I['pairs'][i], f_draws[i], target[i]) if shift is None else
                      solve_k_draws(I['unit_pairs'][i], f_draws[i], target[i], shift['benchmark'][:, i])
                      for i in range(len(BENCHMARKS))])
    else:
        k = np.ones((len(BENCHMARKS), draws))
    keep = np.array([c not in drop for c in I['names']])
    infectious, non_infectious = (I['component'] == 0) & keep, (I['component'] == 1) & keep
    if national:
        # India alone (location 0), from its own GBD rows and age spread; only the deaths are built.
        deaths, deaths_sigma, spread = I['national_deaths'], I['national_deaths_sigma'], I['national_spread']
    else:
        deaths, deaths_sigma, spread = I['deaths'], I['deaths_sigma'], I['count_spread']
    units, places = len(deaths), len(I['locations'])
    india = I['locations'].index(CONFIG['india'])
    # Rates come in sorted location order; order arranges them like the deaths: the units, then India.
    order = [i for i in range(places) if i != india] + [india]
    out = {m: np.zeros((units + 1, len(I['sexes']), len(I['years']), draws)) for m in MEASURES}
    for ti, year in enumerate(I['years']):
        k_year, f_year = benchmark_at(k, year, schedule), benchmark_at(f_draws, year, schedule)
        if projection is not None and year >= CONFIG['first_projection_year']:
            # 'benchmark' takes that year's shares and k instead of the last benchmark year's; 'factor' scales shares before the cap.
            if 'benchmark' in projection:
                bi = BENCHMARKS.index(projection['benchmark'])
                k_year, f_year = k[bi], f_draws[bi]
            f_year = f_year * projection.get('factor', 1.0)
        if shift is None:
            # Capped scaled shares by cause, band and draw, weighted by each place's age spread of deaths and of the standardised rate.
            q = np.minimum(1.0, k_year[None, None, :] * f_year)[I['group_of']]
            share = np.einsum('cbn,ucb->ucn', q, spread[:, :, :, ti])
            standard = np.einsum('cbn,lcb->lcn', q, I['standard_spread'][:, :, :, ti])[order]
        else:
            # shift['annual'] is [31 units + India, year]; each place's shares are moved before scaling and the cap.
            q = np.minimum(1.0, k_year * shifted(f_year[None], shift['annual'][:, ti, None, None, None]))[:, I['group_of']]
            share = np.einsum('ucbn,ucb->ucn', q[:units], I['count_spread'][:, :, :, ti])
            standard = np.einsum('lcbn,lcb->lcn', q, I['standard_spread'][order][:, :, :, ti])
        # Infectious causes count in full; zero-share and dropped causes not at all.
        for array in (share, standard):
            array[:, I['component'] == 0] = 1.0
            array[:, (I['component'] == 2) | ~keep] = 0.0
        for si in range(len(I['sexes'])):
            sepsis = share * scatter(deaths[:, si, :, ti], deaths_sigma[:, si, :, ti], rng, draws)
            out['infectious'][:units, si, ti] = sepsis[:, infectious].sum(axis=1)
            out['non_infectious'][:units, si, ti] = sepsis[:, non_infectious].sum(axis=1)
            if national:
                # out['by_cause'][year]: India's sepsis-related deaths by cause and draw, both sexes.
                if year in cause_years and I['sexes'][si] == 'Both':
                    out.setdefault('by_cause', {})[year] = sepsis[0] * keep[:, None]
                continue
            # Age-standardised rates as in stage 08: India's from its own rates, not from its units.
            standardised = standard * scatter(I['asr'][order, si, :, ti], I['asr_sigma'][order, si, :, ti], rng, draws)
            out['asr_infectious'][:, si, ti] = standardised[:, infectious].sum(axis=1)
            out['asr_non_infectious'][:, si, ti] = standardised[:, non_infectious].sum(axis=1)
    # Deaths as in stage 05: India's are the sum of its units.
    for m in ('infectious', 'non_infectious'):
        out[m][units] = out[m][:units].sum(axis=0)
    out['sepsis_deaths'] = out['infectious'] + out['non_infectious']
    out['age_standardised_rate'] = out['asr_infectious'] + out['asr_non_infectious']
    return out, k

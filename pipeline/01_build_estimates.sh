#!/usr/bin/env bash
# Build the estimates in dependency order, then the results page data.
set -Eeuo pipefail
shopt -s nullglob

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="${PYTHON:-python}"
export PYTHONDONTWRITEBYTECODE=1
LOG=outputs/logs/build_estimates.log
FROM=""
CLEAN=0
EXPORT_ONLY=0
NO_EXPORT=0
DRY_RUN=0
CHECK_ONLY=0

usage() {
  cat <<'HELP'
Usage: bash pipeline/01_build_estimates.sh [options]

Run inside the project image, from the project root:
  docker build -t sepsis_gbd_env:1.0.0 docker
  docker run --rm -v "$PWD":/workspace -w /workspace sepsis_gbd_env:1.0.0 \
      bash pipeline/01_build_estimates.sh --check-only
  docker run --rm -v "$PWD":/workspace -w /workspace sepsis_gbd_env:1.0.0 \
      bash pipeline/01_build_estimates.sh --clean
In the running JupyterLab container: docker exec sepsis_gbd bash pipeline/01_build_estimates.sh [options]

  --check-only        Check Python, packages, pdftotext, configurations, stage scripts and raw files; write nothing
  --clean             Delete what the pipeline writes (data/processed/, outputs/ except logs/ and
                      data/raw/MANIFEST.csv), then build everything from the raw files
  --from GROUP[:NN]   Resume at a group or one of its stages, e.g. state_estimates or mccd:02 (inclusive);
                      a failed build prints the value to resume with
  --export-only       Rebuild only the results page data (release/data.js, release/data/units/) from completed stages
  --no-export         Run the stages without rebuilding the results page data
  --dry-run           Print the commands without running or writing anything
  -h, --help          Show this help
Order: raw_data (01-08), mccd (01-03), appendix_tables (01-05), state_estimates (01-10),
       neonatal_maternal (01-05), mccd_visibility (01-03), economic_loss (01-02), srs_comparison (01),
       figures_tables (01-07, the last its quality control), then the page export (release/build_data.py).
A copy without release/ runs every stage and skips the page export.
Exactly these scripts run: a group whose numbered scripts are not 01 to its last number stops the build.
A numbered folder under src/ that Git ignores (a line /src/NN_name/ in .gitignore or .git/info/exclude) is not
a stage group: it is never checked or run.
--from runs the remaining sequence; the preceding stages must already be complete and match the
current code and configuration.

Required raw files: every file registered in src/01_raw_data/raw_config.json, under data/raw/.
New downloads go to data/raw/_incoming/ until they are checked and registered.
The MCCD stages need xpdf pdftotext 4.x (for -table), which the image builds.

Outputs: data/raw/MANIFEST.csv; data/processed/<group>/; check reports in outputs/<group>/;
figures and tables in outputs/figures_tables/; release/data.js and release/data/units/ for the results page,
when release/ is present.
Execution logs append to outputs/logs/build_estimates.log.
HELP
}

need_value() { [[ $# -ge 2 && -n "$2" && "$2" != --* ]] || { echo "Missing value for $1" >&2; exit 2; }; }
while (($#)); do
  case "$1" in
    --from) need_value "$@"; FROM="$2"; shift 2 ;;
    --clean) CLEAN=1; shift ;;
    --export-only) EXPORT_ONLY=1; shift ;;
    --no-export) NO_EXPORT=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --check-only) CHECK_ONLY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done
if (( EXPORT_ONLY && NO_EXPORT )); then echo 'Choose either --export-only or --no-export.' >&2; exit 2; fi
if (( CHECK_ONLY && DRY_RUN )); then echo 'Choose either --check-only or --dry-run.' >&2; exit 2; fi
if (( EXPORT_ONLY )) && [[ -n "$FROM" ]]; then echo '--from cannot be used with --export-only.' >&2; exit 2; fi
if (( CLEAN )) && { [[ -n "$FROM" ]] || (( EXPORT_ONLY || CHECK_ONLY )); }; then
  echo '--clean runs a full build; it cannot be used with --from, --export-only or --check-only.' >&2; exit 2
fi

# Stage groups and their script counts
NAMES=(raw_data mccd appendix_tables state_estimates neonatal_maternal mccd_visibility economic_loss srs_comparison figures_tables)
SCRIPTS=(8 3 5 10 5 3 2 1 7)
FOLDERS=()
for i in "${!NAMES[@]}"; do
  folder="src/$(printf '%02d' $((i + 1)))_${NAMES[$i]}"
  [[ -d "$folder" ]] || { echo "Missing stage group $folder" >&2; exit 2; }
  position=0
  for script in "$folder"/[0-9][0-9]_*.py; do
    position=$((position + 1))
    name="$(basename "$script")"
    if [[ "${name:0:2}" != "$(printf '%02d' "$position")" ]]; then
      echo "$folder holds $name where stage $(printf '%02d' "$position") belongs: remove the stray copy or renumber" >&2; exit 2
    fi
  done
  if (( position != SCRIPTS[i] )); then
    echo "$folder must hold stages 01 to $(printf '%02d' "${SCRIPTS[$i]}"); found $position" >&2; exit 2
  fi
  FOLDERS+=("$folder")
done
IGNORED="$(cat .gitignore .git/info/exclude 2>/dev/null | tr -d '\r' || true)"
for folder in src/[0-9][0-9]_*/; do
  grep -qxF "/$folder" <<< "$IGNORED" && continue  # ignored by Git: not a stage group
  [[ " ${FOLDERS[*]} " == *" ${folder%/} "* ]] || { echo "Unknown stage group ${folder%/}: add it to NAMES and SCRIPTS" >&2; exit 2; }
done

# Resume point
FROM_GROUP="${FROM%%:*}"
FROM_STAGE=01
[[ -z "$FROM" ]] && FROM_GROUP=raw_data
[[ "$FROM" == *:* ]] && FROM_STAGE="${FROM##*:}"
FROM_INDEX=-1
for i in "${!NAMES[@]}"; do [[ "${NAMES[$i]}" == "$FROM_GROUP" ]] && FROM_INDEX=$i; done
if (( FROM_INDEX < 0 )) || [[ ! "$FROM_STAGE" =~ ^[0-9]{2}$ ]] || (( 10#$FROM_STAGE < 1 || 10#$FROM_STAGE > SCRIPTS[FROM_INDEX] )); then
  echo "Invalid --from: $FROM; use GROUP or GROUP:NN with GROUP one of: ${NAMES[*]}" >&2; exit 2
fi
NEEDS_PDFTOTEXT=0
(( ! EXPORT_ONLY && FROM_INDEX <= 1 )) && NEEDS_PDFTOTEXT=1
EXPORT=$(( ! NO_EXPORT ))
SKIP_EXPORT=0
if [[ ! -f release/build_data.py ]]; then
  if (( EXPORT_ONLY )); then
    echo '--export-only rebuilds the results page data, but this copy has no release/build_data.py.' >&2; exit 2
  fi
  if (( EXPORT )); then EXPORT=0; SKIP_EXPORT=1; fi
fi

CURRENT=""
run() {
  printf '[RUN]'; printf ' %q' "$@"; printf '\n'
  CURRENT="$*"
  if (( ! DRY_RUN )); then "$@"; fi
}
failed() {
  local code=$? resume="rerun the same command"
  if [[ "$CURRENT" =~ src/[0-9]{2}_([a-z_]+)/([0-9]{2})_ ]]; then
    resume="resume with --from ${BASH_REMATCH[1]}:${BASH_REMATCH[2]}"
  elif [[ "$CURRENT" == *release/build_data.py* ]]; then
    resume="resume with --export-only"
  fi
  echo "[BUILD FAILED] $(date -u +%Y-%m-%dT%H:%M:%SZ) while running: ${CURRENT:-the preflight} (exit $code); fix the cause and ${resume}; see $LOG" >&2
}
trap failed ERR

# Preflight
if (( SKIP_EXPORT )); then
  echo '[SKIP] No release/ folder in this copy: every stage runs, and the results page export is skipped.'
fi
if (( ! DRY_RUN )); then
  command -v "$PY" >/dev/null 2>&1 || { echo "Python interpreter not found: $PY" >&2; exit 2; }
  "$PY" - "$NEEDS_PDFTOTEXT" <<'PY'
import importlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

if sys.version_info < (3, 10):
    raise SystemExit('Python 3.10 or newer is required.')
needs_pdftotext = sys.argv[1] == '1'
root, errors = Path.cwd().resolve(), []
local = set()
for ignore in (root / '.gitignore', root / '.git' / 'info' / 'exclude'):
    if ignore.is_file():
        local |= set(ignore.read_text(encoding='utf-8').splitlines())
groups = [f for f in sorted(root.glob('src/[0-9][0-9]_*')) if f'/src/{f.name}/' not in local]
for path in sorted(root.glob('src/common/*.json')) + [c for g in groups for c in sorted(g.glob('*_config.json'))]:
    try:
        json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        errors.append(f'Configuration {path.relative_to(root)}: {error}')
for folder in groups:
    if len(list(folder.glob('*_config.json'))) != 1:
        errors.append(f'{folder.name}: exactly one *_config.json is required')
try:
    config = json.loads((root / 'src/01_raw_data/raw_config.json').read_text(encoding='utf-8'))
    raw = root / config['raw_directory']
    errors.extend(f'Missing raw file: {raw / f["path"]}' for f in config['files'] if not (raw / f['path']).is_file())
    registered = {f['path'] for f in config['files']}
    pending = [p['path'] for p in config['pending'] if p['path'] not in registered]
    if pending:
        print(f'[PENDING] {len(pending)} downloads not yet registered; checks that need them are skipped')
except (OSError, ValueError, KeyError) as error:
    errors.append(f'Raw file register src/01_raw_data/raw_config.json: {error}')
for name in ('numpy', 'matplotlib', 'openpyxl', 'pymupdf', 'PIL'):
    try:
        module = importlib.import_module(name)
        print(f'[DEPENDENCY] {name} {getattr(module, "__version__", "available")}')
    except ImportError as error:
        errors.append(f'{name}: {error}; install with python -m pip install -r docker/requirements.txt')
if needs_pdftotext:
    tool = shutil.which('pdftotext')
    if tool is None:
        errors.append('pdftotext not found; install xpdf tools 4.x (see docker/Dockerfile)')
    else:
        result = subprocess.run([tool, '-v'], capture_output=True, text=True)
        found = re.search(r'pdftotext version (\d+)\.(\d+)', result.stdout + result.stderr)
        if not found or int(found.group(1)) < 4:
            errors.append(f'{tool} is not xpdf pdftotext 4.x; -table is unavailable')
        else:
            print(f'[DEPENDENCY] pdftotext {found.group(1)}.{found.group(2)} {tool}')
if errors:
    raise SystemExit('[PREFLIGHT FAILED]\n' + '\n'.join('- ' + error for error in errors))
print('[PREFLIGHT PASS] Python, packages, tools, configurations, stage scripts and raw files checked; no stages executed.')
PY
fi
if (( CHECK_ONLY )); then exit 0; fi

# Log
if (( ! DRY_RUN )); then
  mkdir -p outputs/logs
  exec 3>&1 4>&2
  exec > >(tee -a "$LOG") 2>&1
  LOGGER=$!
  trap 'exec 1>&3 2>&4; wait "$LOGGER"' EXIT
  printf '\n[BUILD] %s; root=%s; python=%s; from=%s; clean=%s; export=%s\n' \
    "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$ROOT" "$PY" "${FROM:-start}" "$CLEAN" "$EXPORT"
fi

# Clean
if (( CLEAN )); then
  for path in data/processed outputs/* data/raw/MANIFEST.csv; do
    if [[ -e "$path" && "$path" != outputs/logs ]]; then run rm -rf -- "$path"; fi
  done
fi

# Stages
if (( ! EXPORT_ONLY )); then
  for i in "${!NAMES[@]}"; do
    (( i < FROM_INDEX )) && continue
    for script in "${FOLDERS[$i]}"/[0-9][0-9]_*.py; do
      name="$(basename "$script")"
      (( i == FROM_INDEX && 10#${name:0:2} < 10#$FROM_STAGE )) && continue
      run "$PY" -u "$script"
    done
  done
fi

# Export
if (( EXPORT )); then
  run "$PY" -u release/build_data.py
fi

if (( DRY_RUN )); then
  echo '[DRY RUN] No scripts executed.'
else
  printf '[DONE] %s in %dm %02ds\n' "$( (( EXPORT_ONLY )) && echo 'Page data rebuilt' || echo 'All stages complete')" $((SECONDS / 60)) $((SECONDS % 60))
fi

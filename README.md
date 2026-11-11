# Sepsis-related deaths in the states of India, 1990–2023, and their recording on death certificates: a modelling study

India has no state-level estimates of sepsis-related mortality, because its cause-of-death statistics assign each death to one underlying cause; the only estimate is a national total, 4.33 million deaths in 2021. This study estimates sepsis-related deaths for each of India's 31 states and union territories, 1990–2023, by year, sex, age and underlying cause, and compares them with septicaemia on death certificates. This repository holds the pipeline that checks every input, builds the estimates with their uncertainty and sensitivity analyses, and draws the figures and tables.

## Overview

Deaths from infectious underlying causes count in full. Deaths from each non-infectious cause are multiplied by the global fraction that involves sepsis, scaled to India's national total. The study also covers neonatal and maternal sepsis, and the years of life lost and their economic value. The inputs are listed below.

| Source | Version | Contents |
| --- | --- | --- |
| GBD Results Tool | GBD 2023 | Deaths and YLLs by cause, state, sex and age, 1990–2023 |
| GBD Results Tool | GBD 2021 | Deaths by cause and age, Global, India and states, 1990, 2019, 2021 |
| GBD 2021 sepsis study | Lancet Glob Health 2025, appendix 1 | Cause classification (S3), India totals (S8), global sepsis deaths by cause and age (S10) |
| GBD 2021 demographics paper | Appendix 1 | GBD world population age standard (S14) |
| GBD 2023 causes-of-death paper | Supplementary tables | Cause hierarchy |
| IHME MICROBE tool | GBD 2021 | India, 2021: deaths by infectious syndrome, pathogen and resistance |
| GBD 2016 HAQ Index | GHDx | Healthcare Access and Quality Index by state, 1990–2016 |
| MCCD annual reports | 2008–2023 | Certified deaths by State/UT, sex and cause; certification coverage |
| RBI Handbook of Statistics on Indian States | 2017 and 2024–25 | SRS birth, death and infant mortality rates, maternal mortality ratios, net state domestic product |
| Survey of India | OVSF/1M/7 | State boundaries for the map |

All inputs are public and aggregated. No individual records are used.

## Repository Structure

```text
Sepsis_GBD_India/
├── src/
│   ├── 01_raw_data/            # Checksums and consistency checks of every download
│   ├── 02_mccd/                # Death certification reports: text, tables and State/UT series
│   ├── 03_appendix_tables/     # Tables S8, S10 and S14 read from the published appendix PDFs
│   ├── 04_state_estimates/     # State estimates, rates, uncertainty and sensitivity analyses
│   ├── 05_neonatal_maternal/   # Neonatal and maternal sepsis, rates per live birth
│   ├── 06_mccd_visibility/     # Sepsis on death certificates against the estimates
│   ├── 07_economic_loss/       # Value of years of life lost
│   ├── 08_srs_comparison/      # Mortality estimates against the Sample Registration System
│   ├── 09_figures_tables/      # Figures and tables of the paper, with their checks
│   └── common/                 # Cause sets, level 4 parents and age groups
├── pipeline/
│   └── 01_build_estimates.sh   # Run all stages in dependency order
├── docker/                     # Dockerfile, optional Compose service and pinned dependencies
├── LICENSE
└── README.md
```

`data/` and `outputs/` are local working directories excluded from Git. Each stage folder holds numbered scripts, one JSON configuration and one module of shared helpers.

## Workflow

1. **Raw data:** verify every file against its registered SHA-256, check each GBD download against its request, and check the files against each other: causes add up to all causes, ages to all ages and states to India.
2. **Death certification:** convert the 16 MCCD reports to text with `pdftotext -table` and extract certified deaths by State/UT, sex and cause, and certification coverage.
3. **Published tables:** read Tables S8 and S10 of the sepsis analysis (India's national totals; global sepsis-related deaths by cause and age band) and Table S14 of the demographics paper (the world standard population) from the appendix PDFs with PyMuPDF, and check each table against its own arithmetic.
4. **State estimates:** constrain the global fractions to India's national total with one scaling factor per benchmark year (1.02 in 1990 and 1.03 in 2019 and 2021), with every scaled fraction capped at one, and apply them to deaths and YLLs by state, age, sex, cause and year from the GBD 2023 estimates. Then build the annual series, age-standardised rates and a decomposition of change since 1990. Uncertainty intervals come from 1,000 log-normal draws of the inputs, with the scaling factor solved again in each draw. Six sensitivity analyses test no scaling factor, fractions held at the nearest benchmark year, an earlier release of the cause-of-death estimates (GBD 2021), the exclusion of COVID-19, other fractions for 2022–2023, and fractions that vary with each state's Healthcare Access and Quality Index.
5. **Neonatal and maternal sepsis:** neonatal and maternal sepsis as underlying causes and all sepsis-related deaths in these groups, with rates per live birth based on the births implied by GBD 2023.
6. **Death certificates:** compare septicaemia in the MCCD reports with the estimated sepsis-related deaths by state, 2008–2023, alongside certification coverage and registration completeness.
7. **Economic loss:** value the sepsis-related years of life lost at per-capita net state domestic product, discounted at 3%.
8. **Comparison with SRS:** compare GBD 2023 death, infant and maternal mortality rates with the Sample Registration System.
9. **Figures and tables:** 5 figures and 11 tables, each plotted or tabulated value read back against its source.

Each stage writes a JSON report with the checksums of its script and configuration and stops the build when a check fails.

## Rebuilding the Estimates

```bash
git clone https://github.com/MrRajat1809/Sepsis_GBD_India.git
cd Sepsis_GBD_India
docker build -t sepsis_gbd_env:1.0.0 docker
docker run --rm -it -v "$PWD":/workspace -w /workspace sepsis_gbd_env:1.0.0 bash
```

The image has Python 3.13.1 with pinned packages and builds xpdf `pdftotext` 4.00 from source for the death certification stages.

The source files are not redistributed. Download them to `data/raw/`: `src/01_raw_data/raw_config.json` lists every file with its source, its SHA-256 and, for the GBD Results Tool, the exact request. GBD downloads need a free IHME account, and the Survey of India layer needs registration on its Online Maps Portal.

```text
data/raw/
├── gbd2023/{results_tool,cod_paper_supplement}/
├── gbd2021/{results_tool,sepsis_paper,demographics_paper}/
├── gbd2016/haq_index/
├── microbe/
├── mccd/mccd_report_<year>.pdf
├── rbi/handbook/
└── soi/admin_boundary/
```

Then, inside the container:

```bash
bash pipeline/01_build_estimates.sh --check-only   # check the packages, pdftotext, configurations, stage scripts and raw files
bash pipeline/01_build_estimates.sh --clean        # build all 44 stages from the raw files
```

A clean build takes about seven minutes. The build stops on failure, prints the value to resume with, and appends to `outputs/logs/build_estimates.log`.

| Task | Command |
| --- | --- |
| Resume from the death certification tables | `bash pipeline/01_build_estimates.sh --from mccd:02` |
| Rebuild from the state estimates onwards | `bash pipeline/01_build_estimates.sh --from state_estimates` |
| Rebuild the figures and tables | `bash pipeline/01_build_estimates.sh --from figures_tables` |
| List the steps without running anything | `bash pipeline/01_build_estimates.sh --dry-run` |
| List all options | `bash pipeline/01_build_estimates.sh --help` |

`--from` runs the selected stage and all later ones; earlier stages must already be complete and match the current code and configuration.

## Outputs

| Location | Contents |
| --- | --- |
| `data/raw/MANIFEST.csv` | Every raw file with its source, contents, size and SHA-256 |
| `data/processed/<group>/` | The tables of each stage group as CSV |
| `outputs/<group>/` | The JSON report of every stage: checks, summaries and checksums |
| `outputs/figures_tables/` | Fig1–Fig5 as PDF and PNG with their data, Table1–Table3 and SuppTable1–SuppTable8 as CSV and LaTeX, and a manifest with caption notes |
| `outputs/logs/` | Build log |

## Study Design and Interpretation

- **Fractions:** the fraction of each non-infectious cause's deaths that involve sepsis is published only for the world as a whole. The scaling factor sets only the national level; the distribution of deaths between states, ages, sexes and causes, and their course over time, follow from each state's own mortality by cause and age. Because the fractions do not differ between states, the estimates are not a measure of sepsis care. The published fractions come mainly from high-income countries, so they may understate sepsis in India, and they cover only three years, both sexes combined, and seven broad age bands.
- **Infectious causes:** counting every infectious death as sepsis-related overcounts, because not all of these deaths involve sepsis: a death from diarrheal disease, for example, can follow dehydration and fluid loss. Deaths from infectious causes are best read as upper limits. The overcount changes the size of the estimates more than the comparison between states: with no deaths from diarrheal diseases counted, the four states with the highest rates in 2019 and the ratio between Chhattisgarh and Kerala stay the same. Deaths from non-infectious causes count only when sepsis was recorded, and records often miss sepsis, so they are probably undercounted. This difference in counting is part of the reason infectious causes account for most of the gap between states, and the overall direction of error is not known.
- **Years:** fractions and scaling factors are interpolated linearly between the benchmark years 1990, 2019 and 2021, and held at their 2021 values for 2022 and 2023, which are reported as projections.
- **Rounds:** the fractions come from the GBD 2021 round and the deaths from GBD 2023; a sensitivity analysis uses the earlier release.
- **Uncertainty:** state intervals treat the inputs as independent, so they are probably too narrow. India's intervals take their width from its national estimates.
- **Inputs:** the estimates are modelled, and so are their inputs: state deaths by cause are not direct counts, because medical certification reaches about a fifth of deaths.
- **Death certificates:** the form has lines for the chain of causes, but the MCCD reports tabulate one underlying cause. MCCD covers a minority of deaths, mostly in hospital, and counts deaths where they occur. Under ICD rules septicaemia is seldom the underlying cause. The comparison describes recording, not under-reporting: across states, recorded septicaemia rises with certification coverage and falls as the estimated rate rises. The count ratio should not be used to rank states: people who travel for treatment raise it where they die and lower it where they live.
- **Economic value:** an income-based measure that leaves out treatment costs, and sepsis-related does not mean preventable, so it does not show what prevention would save. Undiscounted, it is 1.7–1.9 times larger.

## Technologies

| Component | Libraries |
| --- | --- |
| Data processing | Python standard library, NumPy |
| PDF extraction | xpdf `pdftotext` 4.00, PyMuPDF |
| Spreadsheets | openpyxl |
| Figures and maps | Matplotlib, Pillow |
| Environment and execution | Docker, Bash |

## Data Availability

Downloaded and generated data are not stored in this repository, and the source files are not redistributed.

GBD data are used under IHME's Free-of-Charge Non-Commercial User Agreement. Source: Institute for Health Metrics and Evaluation. Used with permission. All rights reserved. Cite the GBD data as given in each Results Tool archive. MCCD reports are public documents of the Office of the Registrar General, India. State boundaries: Survey of India, Department of Science and Technology, Government of India, Administrative Boundary Database, 1:1 million (OVSF/1M/7).

## License

The source code is distributed under the [MIT License](LICENSE). The documentation is licensed under [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/). Numbers from the GBD remain subject to IHME's non-commercial terms.

## Use of Generative AI

Generative AI (Claude, Anthropic) was used to assist with writing and reviewing code and documentation. The author directed the work, made the methodological decisions, checked the results, and takes responsibility for the content of this repository.

## Contact

**Authors:** Priyanshu Kumar, Garima Singh, Shubemaan Kaur, Satakshi Sri  
**Contact:** Priyanshu Kumar, Chandigarh University  
**Repository:** [MrRajat1809/Sepsis_GBD_India](https://github.com/MrRajat1809/Sepsis_GBD_India)

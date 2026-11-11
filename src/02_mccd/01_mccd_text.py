"""Convert each annual MCCD report to page-separated text, data/processed/mccd/report_<year>.txt, with pdftotext -table."""
import re
import shutil
import subprocess

import mccd_common as M


def pdftotext_version(command):
    result = subprocess.run([command, '-v'], capture_output=True, text=True)
    found = re.search(r'pdftotext version (\S+)', result.stdout + result.stderr)
    M.require(found, f'{command} did not report a version; xpdf pdftotext 4.x is required for -table')
    return found.group(1)


def convert_reports():
    tool = M.CONFIG['pdftotext']
    M.require(shutil.which(tool['command']), f'{tool["command"]} not found; install xpdf tools (see docker/Dockerfile)')
    version = pdftotext_version(tool['command'])
    M.WORK.mkdir(parents=True, exist_ok=True)
    pages = {}
    for year in M.YEARS:
        pdf, text = M.RAW / f'mccd_report_{year}.pdf', M.text_path(year)
        M.require(pdf.is_file(), f'Missing MCCD report: {pdf}')
        pending = text.with_name(text.name + '.tmp')
        subprocess.run([tool['command'], *tool['arguments'], str(pdf), str(pending)], check=True)
        pending.replace(text)
        pages[year] = text.read_text(encoding='utf-8').count('\f')
    M.write_report('01_text.json', __file__, dict(reports=len(pages), pages=pages),
                   pdftotext_version=version, reference_version=tool['reference_version'],
                   text_sha256={y: M.sha256(M.text_path(y)) for y in M.YEARS})
    note = '' if version == tool['reference_version'] else f' (reference run used {tool["reference_version"]})'
    print(f'[01] Complete; {len(pages)} MCCD reports converted with pdftotext {version}{note}', flush=True)


if __name__ == '__main__':
    convert_reports()

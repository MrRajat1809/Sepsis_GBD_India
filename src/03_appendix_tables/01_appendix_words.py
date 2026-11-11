"""Write the position of every word, as read by PyMuPDF, on the appendix pages that hold the configured tables."""
from collections import Counter, defaultdict

import pymupdf

import appendix_common as A


def extract_words():
    pages = defaultdict(set)
    for spec in A.CONFIG['tables'].values():
        pages[spec['document']].update(range(spec['pages'][0], spec['pages'][1] + 1))
    rows, documents = [], {}
    for name, path in sorted(A.CONFIG['documents'].items()):
        pdf = A.raw_file(path)
        documents[name] = dict(pdf=path, sha256=A.sha256(pdf), pages=sorted(pages[name]))
        with pymupdf.open(pdf) as document:
            for number in sorted(pages[name]):
                for x0, y0, x1, y1, text, block, line, word in document[number - 1].get_text('words'):
                    rows.append([name, number, block, line, word, f'{x0:.2f}', f'{y0:.2f}', f'{x1:.2f}', f'{y1:.2f}', text])
    path = A.write_csv(A.WORDS, A.WORD_FIELDS, rows)
    per_page = Counter(f'{r[0]} {r[1]}' for r in rows)
    empty = [f'{d} {p}' for d, numbers in pages.items() for p in numbers if not per_page[f'{d} {p}']]
    A.require(not empty, f'No words found on pages {empty}')
    # Word and block positions can change between PyMuPDF versions, so the report records the version used.
    version, reference = pymupdf.__version__, A.CONFIG['pymupdf_reference_version']
    total_pages = sum(len(v) for v in pages.values())
    A.write_report('01_words.json', __file__, dict(documents=len(documents), pages=total_pages, words=len(rows)),
                   pymupdf_version=version, reference_version=reference, documents=documents,
                   words_per_page=dict(per_page), words_sha256=A.sha256(path))
    note = '' if version == reference else f' (reference run used {reference})'
    print(f'[01] Complete; {len(rows):,} words from {total_pages} pages of {len(documents)} appendices with PyMuPDF '
          f'{version}{note}', flush=True)


if __name__ == '__main__':
    extract_words()

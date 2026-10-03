"""Parse the EU GPAI Code of Practice Model Documentation Form (DOCX) into targets/eu_form.yaml.

Usage: uv run python -m pipeline.parse_eu_form path/to/form.docx
Download: https://ec.europa.eu/newsroom/dae/redirection/document/118118

Each item records its section, label, description, recommended length, and the intended
audience(s) from the crosses in the AIO / NCA / DP columns. Rows with a blank label are
continuations of the item above (typically a more precise version for the AI Office and a
range for others); they inherit the label and get a `part` number.
"""
import re, sys, zipfile
import yaml
from lxml import etree

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
BOX = {'☒': True, '☐': False}

def text(el):
    return re.sub(r'\s+', ' ', ''.join(t.text or '' for t in el.iter(W + 't'))).strip()

def cells(tr):
    out = []
    for ch in tr:  # cells may be wrapped in content controls (w:sdt)
        if ch.tag == W + 'tc':
            out.append(ch)
        elif ch.tag == W + 'sdt':
            out += list(ch.iter(W + 'tc'))
    return out

# Split items: the AI Office gets a precise value, others a range or order of magnitude.
# Checked against the pinned DOCX on 2026-09-30.
PRECISION = {
    'total_model_size': 'exact', 'total_model_size_2': 'range',
    'number_of_data_points': 'range', 'number_of_data_points_2': 'exact',
    'training_time': 'range', 'training_time_2': 'exact',
    'amount_of_computation_used_for_training': 'range',
    'amount_of_computation_used_for_training_2': 'exact',
}

# Items whose parse was checked by hand against the DOCX XML.
REVIEWED = {
    'output_modalities_modalities': 'stacked checkboxes read top=modalities: AIO, NCA, DP all ticked (checked 2026-09-30)',
    'output_modalities_maximum_size': 'stacked checkboxes read bottom=maximum size: DP only ticked (checked 2026-09-30)',
}


def slug(s):
    return re.sub(r'[^a-z0-9]+', '_', s.lower()).strip('_')[:50]

def parse(path):
    xml = etree.fromstring(zipfile.ZipFile(path).read('word/document.xml'))
    items, section, last_label, part, seen = [], None, None, 1, set()
    pending = []  # text of rows without audience boxes: option lists and part descriptions

    def flush():
        # Rows between items belong to the item above (e.g. the rest of a checkbox list)
        if pending and items:
            for extra in pending:
                if extra not in items[-1]['description']:
                    items[-1]['description'] = (items[-1]['description'] + ' ' + extra).strip()
        pending.clear()

    for tr in xml.iter(W + 'tr'):
        if tr.find('.//' + W + 'tbl') is not None:
            continue
        txt = [text(c) for c in cells(tr)]
        if 'AIO' in txt and 'DPs' in txt:
            flush()
            section = txt[0] or section
            continue
        # Row whose audience cells hold two stacked checkbox pairs (e.g. output modalities)
        pairs = [t for t in txt if len(t) == 2 and all(ch in BOX for ch in t)]
        if len(pairs) == 3:
            flush()
            label = txt[0].split(':')[0]
            for k, sub in enumerate(['modalities', 'maximum size']):
                items.append(dict(section=section, item=f'{label} ({sub})',
                    description=txt[0], recommended_length=None,
                    audience=dict(zip(['AIO', 'NCA', 'DP'], [BOX[p[k]] for p in pairs])),
                    needs_review='audience read from stacked checkboxes; confirm against the form'))
            last_label, part = label, 1
            continue
        idx = [i for i, t in enumerate(txt) if t in BOX][:3]
        if len(idx) < 3:
            extra = ' '.join(t for t in txt if len(t) > 2)  # len > 2 drops stray fragments like 'bu'
            if extra:
                pending.append(extra)
            continue
        label = txt[0].rstrip(':').replace('forthe', 'for the')
        desc = ' '.join(t for t in txt[1:idx[0]] if t)
        desc = re.sub(r'Click (or tap )?(here )?to (add|enter) (text|a date)\.\s*', '', desc).strip()
        if not desc and not label:
            continue
        if label:
            last_label, part = label, 1
        else:
            label, part = last_label, part + 1
        key = (section, label, desc)
        if key in seen:
            continue
        seen.add(key)
        if part > 1 and pending:
            # A description row directly above a continuation row describes that part
            desc = ' '.join(pending + [desc]).strip()
            pending.clear()
        else:
            flush()
        m = re.search(r'\[Recommended ([^\]]+)\]', desc)
        item = dict(section=section, item=label, description=desc,
                    recommended_length=m.group(1) if m else None,
                    audience=dict(zip(['AIO', 'NCA', 'DP'], [BOX[txt[i]] for i in idx])))
        if part > 1:
            item['part'] = part
        items.append(item)
    flush()
    prev = None
    for it in items:
        if it['item'].startswith('For each selected modality'):
            it['item'] = 'Input modalities (maximum size)'
        if it['item'] == 'Measurement methodology' and prev:
            it['id'] = prev + '_methodology'
        else:
            it['id'] = slug(it['item']) + (f"_{it['part']}" if it.get('part') else '')
            prev = it['id']
        it['public'] = False  # the form routes nothing to the public; DP = downstream providers only
        if it['id'] in PRECISION:
            it['precision'] = PRECISION[it['id']]
        if it['id'] in REVIEWED:
            it.pop('needs_review', None)
            it['review_note'] = REVIEWED[it['id']]
    return items

if __name__ == '__main__':
    items = parse(sys.argv[1])
    doc = dict(
        source='EU GPAI Code of Practice, Transparency chapter: Model Documentation Form (DOCX)',
        source_url='https://ec.europa.eu/newsroom/dae/redirection/document/118118',
        audience_key=dict(AIO='AI Office (on request)', NCA='national competent authorities (via AIO request)',
                          DP='downstream providers (proactively)'),
        generated_by='pipeline/parse_eu_form.py — automated parse; spot-check against the form before relying on it',
        items=[{k: it[k] for k in ['id', 'section', 'item', 'part', 'description', 'recommended_length',
                'audience', 'precision', 'public', 'needs_review', 'review_note'] if k in it} for it in items])
    with open('targets/eu_form.yaml', 'w') as f:
        yaml.safe_dump(doc, f, sort_keys=False, allow_unicode=True, width=100)
    print(f'{len(items)} items written to targets/eu_form.yaml')

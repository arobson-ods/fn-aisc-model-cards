"""Draw the article graphics from the report outputs.

Usage: uv run python -m pipeline.graphics
Reads out/eu/all.csv, out/headline.json, out/matrix_schema.csv, out/lineage.csv,
data/extracted/*.json and data/raw/_upstream/chains.json.
Writes docs/graphics/{eu_items,fact_sources,schema_fields,lineage}.svg and PNGs at 2x
(PNGs need ImageMagick's `magick`; skipped if it isn't installed).

Static SVGs on their own light surface, so they read the same on any article page.
Palette: the dataviz reference palette (blue, orange, aqua), validated for CVD and contrast.
"""
import json, shutil, statistics, subprocess
from collections import Counter
from html import escape

import pandas as pd

from .common import OUT, RAW, ROOT, load_yaml

GFX = ROOT / 'docs' / 'graphics'
W = 960
SURFACE, INK, INK2, MUTED, GRID, BASE = '#fcfcfb', '#0b0b0b', '#52514e', '#898781', '#e1e0d9', '#c3c2b7'
BLUE, ORANGE, AQUA, NEUTRAL, BLUE_WASH = '#2a78d6', '#eb6834', '#1baf7a', '#c3c2b7', '#cde2fb'
FONT = "system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
SOURCE = 'Source: 14 open-weight model cards on Hugging Face, retrieved September 2026.'


def text(x, y, s, size=14, fill=INK, weight=400, anchor='start', style=''):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" font-weight="{weight}" '
            f'text-anchor="{anchor}"{f" font-style={chr(34)}{style}{chr(34)}" if style else ""}>{escape(s)}</text>')


def bar(x, y, w, h, fill, r=4, tip=''):
    """Horizontal bar, square at the baseline, rounded data end."""
    r = min(r, w / 2, h / 2)
    d = (f'M{x:.1f},{y:.1f} h{w - r:.1f} a{r},{r} 0 0 1 {r},{r} v{h - 2 * r:.1f} '
         f'a{r},{r} 0 0 1 -{r},{r} h-{w - r:.1f} z')
    t = f'<title>{escape(tip)}</title>' if tip else ''
    return f'<path d="{d}" fill="{fill}">{t}</path>'


def svg(height, body, title, desc):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{height}" viewBox="0 0 {W} {height}" '
            f'role="img" aria-labelledby="t d" font-family="{FONT}">\n'
            f'<title id="t">{escape(title)}</title><desc id="d">{escape(desc)}</desc>\n'
            f'<rect width="{W}" height="{height}" fill="{SURFACE}"/>\n' + '\n'.join(body) + '\n</svg>\n')


def header(title, subtitle):
    return [text(32, 48, title, 24, INK, 700), text(32, 76, subtitle, 15, INK2)]


# ---- 1. EU form items answered, by section

SECTION_LABELS = {
    'Methods of distribution and licenses': 'Distribution and licences',
    'Model properties': 'Model properties',
    'Use': 'Intended use',
    'Training process': 'Training process',
    'General information': 'General information',
    'Information on the data used for training': 'Training data',
    'Computational resources (during training)': 'Compute used in training',
    'Energy consumption (during training and inference)': 'Energy use',
}


def section_label(name):
    return next((v for k, v in SECTION_LABELS.items() if name.startswith(k)), name)


def eu_items():
    e = pd.read_csv(OUT / 'eu' / 'all.csv')
    e['ans'] = e.status.eq('answered')
    per_model = e.groupby('model').ans.sum()
    n_items = e.item.nunique()
    med = statistics.median(per_model)
    sec = (e.groupby('section', sort=False)
           .agg(items=('item', 'nunique'), share=('ans', 'mean'),
                dp=('DP', 'any'))
           .sort_values('share', ascending=False))
    # sections where no item goes to downstream providers: the form sends them only to regulators
    reg_only = [s for s, d in e.groupby('section') if not d.DP.any()]

    body = header('Public model cards answer just over half of the EU form',
                  'Items on the EU Model Documentation Form that public model cards answer')
    body += [text(32, 140, f'{med:.0f} of {n_items}', 52, INK, 700),
             text(250, 116, 'items answered by the typical card', 17, INK, 600),
             text(250, 140, f'Median of 14 cards. The fewest was {per_model.min()}, the most {per_model.max()} (Llama).', 15, INK2)]
    top, row, lx, bx, bw, bh = 200, 40, 300, 316, 460, 20
    body.append(text(32, top - 16, 'Share of items answered across all 14 cards, by section of the form', 14, INK2, 600))
    rows = list(sec.itertuples())
    for i, s in enumerate(rows):
        y = top + i * row
        label = section_label(s.Index)
        body.append(text(lx, y + 15, label, 15, INK, 400, 'end'))
        body.append(text(lx, y + 32, f'{s.items} items', 12, MUTED, 400, 'end'))
        body.append(f'<rect x="{bx}" y="{y + 2}" width="{bw}" height="{bh}" fill="{GRID}" opacity="0.45"/>')
        w = max(bw * s.share, 2)
        body.append(bar(bx, y + 2, w, bh, BLUE, tip=f'{label}: {s.share:.0%} of answers'))
        body.append(text(bx + w + 8, y + 17, f'{s.share:.0%}', 15, INK, 600))
        if s.Index in reg_only:
            body.append(text(bx + w + 56, y + 17, 'Sent only to regulators', 14, INK2, 400, style='italic'))
    axis_y = top + len(rows) * row + 4
    body.append(f'<line x1="{bx}" y1="{top - 2}" x2="{bx}" y2="{axis_y}" stroke="{BASE}"/>')
    for p in (0, .5, 1):
        body.append(text(bx + bw * p, axis_y + 18, f'{p:.0%}', 12, MUTED, 400, 'middle'))
    h = axis_y + 84
    body.append(text(32, h - 34, SOURCE + ' An item counts as answered if anything public on the card answers it,', 12, MUTED))
    body.append(text(32, h - 18, 'including details Hugging Face supplies such as the commit hash, so the figure is generous.', 12, MUTED))
    desc = (f'The typical card answers {med:.0f} of {n_items} items. By section: '
            + '; '.join(f'{section_label(s.Index)} {s.share:.0%}' for s in rows)
            + '. The form sends training-process, compute and energy items only to regulators.')
    return svg(h, body, 'Public model cards answer just over half of the EU form', desc), sec, med, n_items


# ---- 2. where disclosed facts come from

SOURCES = [  # key, label, examples, colour
    ('card_metadata', "The lab's own card metadata", 'licence, base model, languages, task', BLUE),
    ('hub_api', 'Generated by Hugging Face', 'parameter count, commit, access terms, derivation type', ORANGE),
    ('repo_config', "The repository's config.json", 'context length, precision', AQUA),
    ('prose', 'Written in the README text', 'training method, limitations, intended use', NEUTRAL),
]


def fact_sources():
    c = Counter()
    for p in sorted((ROOT / 'data' / 'extracted').glob('*.json')):
        for r in json.loads(p.read_text()):
            if r['status'] == 'structured':
                c[r['source_type']] += 1
            elif r['status'] == 'prose':
                c['prose'] += 1
    total = sum(c.values())
    shares = {k: c[k] / total for k, *_ in SOURCES}
    mr = 1 - shares['prose']

    body = header('Most of what model cards disclose is prose, not data',
                  f'Where the {total} facts disclosed by 14 model cards come from')
    x0, bw, y, bh, gap = 32, W - 64, 150, 32, 2
    x = x0
    segs = []
    for i, (k, label, ex, col) in enumerate(SOURCES):
        w = bw * shares[k] - (gap if i < len(SOURCES) - 1 else 0)
        last = i == len(SOURCES) - 1
        body.append(bar(x, y, w, bh, col, r=4 if last else 0, tip=f'{label}: {shares[k]:.0%}'))
        if w > 40:
            body.append(text(x + w / 2, y + 21, f'{shares[k]:.0%}', 15, INK, 700, 'middle'))
        segs.append((x, w))
        x += w + gap
    # bracket over the machine-readable part
    xe = segs[2][0] + segs[2][1]
    body.append(f'<path d="M{x0},{y - 8} v-8 h{xe - x0:.1f} v8" fill="none" stroke="{INK2}" stroke-width="1.5"/>')
    body.append(text(x0, y - 24, f'Machine-readable: {mr:.0%}', 14, INK, 600))
    body.append(f'<path d="M{segs[3][0]:.1f},{y - 8} v-8 h{segs[3][1]:.1f} v8" fill="none" stroke="{INK2}" stroke-width="1.5"/>')
    body.append(text(segs[3][0] + segs[3][1], y - 24, f'Prose only: {shares["prose"]:.0%}', 14, INK, 600, 'end'))
    ly = y + bh + 44
    for i, (k, label, ex, col) in enumerate(SOURCES):
        yy = ly + i * 34
        body.append(f'<rect x="{x0}" y="{yy - 12}" width="14" height="14" rx="3" fill="{col}"/>')
        body.append(text(x0 + 26, yy, f'{shares[k]:.0%}', 15, INK, 700))
        body.append(text(x0 + 70, yy, label, 15, INK, 600))
        body.append(text(x0 + 330, yy, f'e.g. {ex}', 14, INK2))
    ny = ly + len(SOURCES) * 34 + 18
    body.append(text(x0, ny, f'Less than a fifth comes from metadata the lab itself declared. Generated values can be wrong:', 14, INK))
    body.append(text(x0, ny + 20, 'Hugging Face tags one fine-tune as an adapter, though it ships full merged weights.', 14, INK))
    h = ny + 62
    body.append(text(32, h - 18, SOURCE + ' Shares are of all facts disclosed, pooled across the 14 cards.', 12, MUTED))
    desc = ('; '.join(f'{label} {shares[k]:.0%}' for k, label, *_ in SOURCES)
            + f'. Machine-readable in total: {mr:.0%}.')
    return svg(h, body, 'Most of what model cards disclose is prose, not data', desc), c, total


# ---- 3. which facts the standards have a field for

SCHEMA_FACTS = [
    ('license', 'Licence'), ('base_model', 'Base model'), ('training_datasets', 'Training datasets'),
    ('limitations', 'Limitations'), ('training_energy', 'Training energy'),
    ('max_input_size', 'Context length'), ('input_modalities', 'Input types (text, image…)'),
    ('param_count', 'Parameter count'), ('knowledge_cutoff', 'Knowledge cutoff date'),
    ('training_compute', 'Training compute'), ('training_time', 'Training time'),
    ('training_hardware', 'Training hardware'), ('languages', 'Languages'),
    ('base_model_relation', 'How it was derived (fine-tune, quantised…)'),
]


def chip(cx, y, kind):
    if kind == 'field':
        return (f'<rect x="{cx - 60}" y="{y - 17}" width="120" height="24" rx="12" fill="{BLUE_WASH}"/>'
                + text(cx, y, 'Field', 14, INK, 600, 'middle'))
    label = 'Free text only' if kind == 'escape_hatch' else 'Nowhere'
    return (f'<rect x="{cx - 60}" y="{y - 17}" width="120" height="24" rx="12" fill="none" '
            f'stroke="{MUTED}" stroke-dasharray="3 3"/>' + text(cx, y, label, 14, INK2, 400, 'middle'))


def schema_fields():
    m = pd.read_csv(OUT / 'matrix_schema.csv').set_index('fact_id')
    rows = [(fid, label, m.loc[fid, 'spdx'], m.loc[fid, 'cdx']) for fid, label in SCHEMA_FACTS]
    n_field = lambda r: (r[2] == 'field') + (r[3] == 'field')
    groups = [('Both standards have a field', 2), ('Only one has a field', 1), ('Neither has a field', 0)]

    body = header('The standards have no field for some basic facts',
                  'Can each AI bill-of-materials standard hold the fact in a field of its own?')
    c1, c2, y = 520, 720, 128
    body += [text(c1, y, 'SPDX 3.0.1', 15, INK, 700, 'middle'), text(c2, y, 'CycloneDX 1.7', 15, INK, 700, 'middle')]
    y += 22
    for gname, n in groups:
        grp = [r for r in rows if n_field(r) == n]
        if not grp:
            continue
        y += 40
        body.append(text(32, y, gname, 13, MUTED, 700))
        body.append(f'<line x1="32" y1="{y + 8}" x2="{W - 32}" y2="{y + 8}" stroke="{GRID}"/>')
        y += 10
        for fid, label, s, c in grp:
            y += 34
            body += [text(32, y, label, 15, INK), chip(c1, y, s), chip(c2, y, c)]
    y += 44
    body.append(text(32, y, 'Free text only: the fact can go in a comment or a generic name–value list. The document stays valid,', 14, INK2))
    body.append(text(32, y + 20, 'but no tool can rely on finding it there. This holds even for OLMo, the most open model in the sample.', 14, INK2))
    h = y + 62
    body.append(text(32, h - 18, 'Source: SPDX 3.0.1 AI and Dataset profiles; CycloneDX 1.7 ML-BOM model card. Mapping in targets/facts.yaml.', 12, MUTED))
    desc = '; '.join(f'{label}: SPDX {s}, CycloneDX {c}' for _, label, s, c in rows)
    return svg(h, body, 'The standards have no field for some basic facts', desc.replace('escape_hatch', 'free text only')), rows


# ---- 4. lineage chains

def declares(model_key):
    recs = json.loads((ROOT / 'data' / 'extracted' / f'{model_key}.json').read_text())
    r = next(r for r in recs if r['fact_id'] == 'training_datasets')
    return r['status'] == 'structured' and r.get('source_type') == 'card_metadata'


def lanes(root, nodes):
    """Tree layout: first child stays in its parent's lane, later children open new lanes."""
    kids = {}
    for n in nodes:
        kids.setdefault(n['parent'], []).append(n)
    out, nxt = [], [0]

    def walk(repo, depth, lane, has_data):
        out.append(dict(repo=repo, depth=depth, lane=lane, data=has_data))
        for i, k in enumerate(kids.get(repo, [])):
            if i:
                nxt[0] += 1
            walk(k['repo_id'], depth + 1, nxt[0] if i else lane, bool(k['datasets']))
    walk(root['repo_id'], 0, 0, root['data'])
    return out, nxt[0] + 1


def lineage():
    models = {m['key']: m for m in load_yaml(ROOT / 'models.yaml')['models']}
    chains = json.loads((RAW / '_upstream' / 'chains.json').read_text())
    keyed = [(k, v) for k, v in chains.items() if v]
    trees = []
    for k, nodes in keyed:
        root = dict(repo_id=models[k]['repo_id'], data=declares(k))
        layout, n_lanes = lanes(root, nodes)
        trees.append((k, layout, n_lanes, any(n['data'] for n in layout)))
    trees.sort(key=lambda t: (not t[3], list(chains).index(t[0])))
    without = sum(not t[3] for t in trees)

    x0, step, lane_h = 190, 168, 48
    body = header('The training-data trail goes cold at the base model',
                  'Each row follows a published model back through the parent models its card declares')
    ly = 112
    body.append(f'<circle cx="38" cy="{ly - 5}" r="6" fill="{BLUE}"/>')
    body.append(text(52, ly, "Card metadata lists the model's training datasets", 14, INK))
    body.append(f'<circle cx="420" cy="{ly - 5}" r="5.25" fill="{SURFACE}" stroke="{MUTED}" stroke-width="1.5"/>')
    body.append(text(434, ly, 'Lists none', 14, INK))
    body.append(text(x0 - 7, ly + 36, 'Published model', 13, MUTED, 700))
    body.append(text(x0 + step - 7, ly + 36, 'Declared parent models →', 13, MUTED, 700))
    y = ly + 50
    groups = [(True, 'Training datasets declared somewhere in the chain'),
              (False, f'No training datasets declared anywhere in the chain: {without} of {len(trees)} chains')]
    for has, gname in groups:
        y += 24
        body.append(text(32, y, gname, 13, INK, 700))
        body.append(f'<line x1="32" y1="{y + 8}" x2="{W - 32}" y2="{y + 8}" stroke="{GRID}"/>')
        y += 14
        for k, layout, n_lanes, any_data in [t for t in trees if t[3] == has]:
            m = models[k]
            top = y + 34
            body.append(text(32, top + 5, m['family'], 14, INK, 600))
            body.append(text(32, top + 22, {'control': 'control model', 'major': 'major family', 'lineage': 'derived model'}[m['role']], 12, MUTED))
            pos = {n['repo']: (x0 + n['depth'] * step, top + n['lane'] * lane_h) for n in layout}
            parent = {n['repo_id']: n['parent'] for n in chains[k]}
            for n in layout:  # links first, so nodes paint on top
                if n['repo'] in parent:
                    (px, py), (cx, cy) = pos[parent[n['repo']]], pos[n['repo']]
                    d = f'M{px + 8},{py} H{cx - 30} Q{cx - 18},{py} {cx - 18},{py + 12} V{cy - 12} Q{cx - 18},{cy} {cx - 8},{cy}' \
                        if cy != py else f'M{px + 8},{py} H{cx - 8}'
                    body.append(f'<path d="{d}" fill="none" stroke="{BASE}" stroke-width="2" stroke-linecap="round"/>')
            for n in layout:
                cx, cy = pos[n['repo']]
                tip = f'<title>{escape(n["repo"])}: {"lists" if n["data"] else "lists no"} training datasets</title>'
                body.append(f'<circle cx="{cx}" cy="{cy}" r="6" fill="{BLUE}" stroke="{SURFACE}" stroke-width="2">{tip}</circle>'
                            if n['data'] else
                            f'<circle cx="{cx}" cy="{cy}" r="5.25" fill="{SURFACE}" stroke="{MUTED}" stroke-width="1.5">{tip}</circle>')
                above = n['depth'] % 2 == 0
                body.append(text(cx - 7, cy - 12 if above else cy + 21, n['repo'].split('/')[1], 11, INK2))
            y = top + (n_lanes - 1) * lane_h + 28
    y += 36
    body.append(text(32, y, 'SPDX, CycloneDX and the EU form can all record "derived from", but none can say how', 14, INK2))
    body.append(text(32, y + 20, '(fine-tuned, quantised, merged or adapted). Mistral, Qwen and DeepSeek declare no parent and are not shown.', 14, INK2))
    h = y + 62
    body.append(text(32, h - 18, SOURCE + ' "Lists" means the card\'s machine-readable datasets field, not its prose.', 12, MUTED))
    desc = '; '.join(f"{models[k]['family']}: " + ' → '.join(f"{n['repo'].split('/')[1]} ({'datasets' if n['data'] else 'none'})" for n in layout)
                     for k, layout, *_ in trees)
    return svg(h, body, 'The training-data trail goes cold at the base model', desc), trees


def main():
    GFX.mkdir(parents=True, exist_ok=True)
    out = {
        'eu_items': eu_items()[0],
        'fact_sources': fact_sources()[0],
        'schema_fields': schema_fields()[0],
        'lineage': lineage()[0],
    }
    magick = shutil.which('magick')
    for name, s in out.items():
        path = GFX / f'{name}.svg'
        path.write_text(s)
        if magick:
            subprocess.run([magick, '-density', '192', '-background', 'none', str(path), str(GFX / f'{name}.png')], check=True)
        print('wrote', path.relative_to(ROOT))


if __name__ == '__main__':
    main()

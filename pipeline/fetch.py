"""Fetch and cache HF API metadata, README and config.json for every model in models.yaml.

Usage: uv run python -m pipeline.fetch [--refresh]

Writes data/raw/{key}/{api.json, README.md, config.json, source.json} and updates models.yaml
with retrieval dates and gating. For lineage cases, the declared base models are fetched one hop
up into data/raw/_upstream/ so the lineage report can check what the base card declares.

Gated repos serve their API metadata but return 401 for the raw README without a token. The
same card is rendered on the public model page, so we fall back to that and record
readme_source: rendered_html. No mirrors are substituted.
"""
import json, re, sys

import lxml.html
import yaml

from .common import RAW, ROOT, cached_get, load_yaml

HF = 'https://huggingface.co'
MAX_HOPS = 6
BLOCK = {'p', 'div', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'tr', 'pre', 'br', 'table', 'ul', 'ol'}


def html_card_text(html):
    """Plain text of the rendered model card, keeping headings and table rows on their own lines."""
    root = lxml.html.fromstring(html)
    nodes = root.xpath('//*[contains(concat(" ", @class, " "), " model-card-content ")]')
    if not nodes:
        return None
    card = nodes[0]
    for el in card.iter():
        if el.tag in ('td', 'th'):
            el.tail = ' | ' + (el.tail or '')
        elif el.tag in BLOCK:
            el.tail = '\n' + (el.tail or '')
        if el.tag in ('h1', 'h2', 'h3', 'h4'):
            el.text = '#' * int(el.tag[1]) + ' ' + (el.text or '').strip()
        href = el.get('href') if el.tag == 'a' else None
        if href and not href.startswith('#'):
            # keep the link target, as the raw markdown would: "here (https://...)"
            url = href if re.match(r'https?://', href) else 'https://huggingface.co' + href
            if url != el.text_content().strip():
                el.tail = f' ({url})' + (el.tail or '')
    text = card.text_content()
    text = re.sub(r'[ \t]+', ' ', text)
    return re.sub(r'\n\s*\n+', '\n\n', text).strip() + '\n'


def fetch_repo(repo_id, outdir):
    outdir.mkdir(parents=True, exist_ok=True)
    api = cached_get(f'{HF}/api/models/{repo_id}')
    if api['status'] != 200:
        raise SystemExit(f'{repo_id}: API returned {api["status"]}')
    meta = json.loads(api['body'])
    (outdir / 'api.json').write_text(json.dumps(meta, indent=1, ensure_ascii=False))
    sha = meta.get('sha')
    # Pin README/config to the commit the API reported, so the three files are consistent
    rev = sha or 'main'
    readme_url = f'{HF}/{repo_id}/raw/{rev}/README.md'
    readme = cached_get(readme_url)
    src = dict(repo_id=repo_id, sha=sha, api_url=api['url'], retrieved_at=api['retrieved_at'],
               gated=meta.get('gated') or False, readme_status=readme['status'])
    if readme['status'] == 200:
        text, src['readme_source'], src['readme_url'] = readme['body'], 'raw', readme_url
    else:
        page = cached_get(f'{HF}/{repo_id}')
        text = html_card_text(page['body']) if page['status'] == 200 else None
        src['readme_source'] = 'rendered_html' if text else 'unavailable'
        src['readme_url'] = page['url']
    if text:
        (outdir / 'README.md').write_text(text)
    if any(s.get('rfilename') == 'config.json' for s in meta.get('siblings', [])):
        cfg = cached_get(f'{HF}/{repo_id}/raw/{rev}/config.json')
        if cfg['status'] == 200:
            (outdir / 'config.json').write_text(cfg['body'])
            src['config_url'] = cfg['url']
        else:
            src['config_status'] = cfg['status']
    (outdir / 'source.json').write_text(json.dumps(src, indent=1))
    return meta, src


def base_models(meta):
    b = (meta.get('cardData') or {}).get('base_model') or []
    return [b] if isinstance(b, str) else list(b)


def follow(repo_id, meta, seen):
    """Chain of upstream records, depth-first along declared base models."""
    out = []
    for up in base_models(meta):
        node = dict(repo_id=up, parent=repo_id, depth=len(seen))
        if up in seen or len(seen) > MAX_HOPS:
            node['stopped'] = 'cycle' if up in seen else 'max_hops'
            out.append(node)
            continue
        try:
            up_meta, src = fetch_repo(up, RAW / '_upstream' / up.replace('/', '__'))
        except SystemExit as e:
            node['error'] = str(e)
            out.append(node)
            continue
        card = up_meta.get('cardData') or {}
        node.update(gated=src['gated'], readme_source=src['readme_source'], license=card.get('license'),
                    datasets=card.get('datasets'), base_model=base_models(up_meta))
        out.append(node)
        out += follow(up, up_meta, seen | {up})
    return out


def main():
    if '--refresh' in sys.argv:
        raise SystemExit('--refresh: delete data/raw/http/ entries for the models to re-fetch')
    cfg = load_yaml(ROOT / 'models.yaml')
    chains = {}
    for m in cfg['models']:
        meta, src = fetch_repo(m['repo_id'], RAW / m['key'])
        m.update(retrieved_at=src['retrieved_at'], sha=src['sha'], gated=src['gated'],
                 readme_source=src['readme_source'])
        chains[m['key']] = follow(m['repo_id'], meta, {m['repo_id']})
        if base_models(meta):
            m['base_models'] = base_models(meta)
        print(f"{m['key']:16} {src['readme_source']:13} gated={src['gated']} "
              f"upstream={[n['repo_id'] for n in chains[m['key']]]}")
    (RAW / '_upstream').mkdir(parents=True, exist_ok=True)
    (RAW / '_upstream' / 'chains.json').write_text(json.dumps(chains, indent=1))
    with open(ROOT / 'models.yaml', 'w') as f:
        f.write('# Selected models. Chosen 2026-09-30 as the latest general-purpose release in each family\n'
                '# (HF API, sort=createdAt), preferring the flagship instruct model over derived repos.\n'
                '# retrieved_at, sha, gated, readme_source, base_models are written by pipeline.fetch.\n')
        yaml.safe_dump(cfg, f, sort_keys=False, allow_unicode=True)


if __name__ == '__main__':
    main()

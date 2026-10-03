"""Download and pin the target schemas into targets/schemas/ (one-off; re-run only to re-pin).

Usage: uv run python -m pipeline.pin_schemas
"""
import hashlib
from pathlib import Path

import httpx
import yaml

from .common import SCHEMAS, now_iso

CDX_TAG = '1.7.2'
CDX_BASE = f'https://raw.githubusercontent.com/CycloneDX/specification/{CDX_TAG}/schema/'

PINS = {
    'spdx-3.0.1/spdx-json-schema.json': 'https://spdx.org/schema/3.0.1/spdx-json-schema.json',
    'spdx-3.0.1/spdx-context.jsonld': 'https://spdx.org/rdf/3.0.1/spdx-context.jsonld',
    'spdx-3.0.1/spdx-model.ttl': 'https://spdx.org/rdf/3.0.1/spdx-model.ttl',
    **{f'cyclonedx-{CDX_TAG}/{n}': CDX_BASE + n for n in [
        'bom-1.7.schema.json', 'spdx.schema.json', 'jsf-0.82.schema.json',
        'cryptography-defs.schema.json']},
    'eu-gpai-cop/model_documentation_form.docx':
        'https://ec.europa.eu/newsroom/dae/redirection/document/118118',
}


def main():
    pins = []
    for rel, url in PINS.items():
        path = SCHEMAS / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        r = httpx.get(url, follow_redirects=True, timeout=120,
                      headers={'User-Agent': 'model-cards-research/0.1'})
        r.raise_for_status()
        path.write_bytes(r.content)
        pins.append(dict(file=rel, url=url, final_url=str(r.url), retrieved_at=now_iso(),
                         sha256=hashlib.sha256(r.content).hexdigest(), bytes=len(r.content)))
        print(f'{rel}: {len(r.content)} bytes')
    (SCHEMAS / 'PINS.yaml').write_text(yaml.safe_dump(dict(pins=pins), sort_keys=False))


if __name__ == '__main__':
    main()

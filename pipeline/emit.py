"""Emit SPDX, CycloneDX and EU-form documents for every model, validate them, log placement.

Usage: uv run python -m pipeline.emit [--no-shacl]
Writes out/spdx/{key}.spdx3.json, out/cdx/{key}.cdx.json, out/eu/{key}.yaml, out/eu/all.csv,
out/placement.csv. Exits 1 if any SPDX or CycloneDX document fails validation.
"""
import json, sys

import pandas as pd
import yaml

from . import emit_cdx, emit_eu, emit_spdx
from .common import OUT, RAW, TARGETS, load_yaml
from .emit_common import load_inputs, load_records
from .validate import validate_cdx, validate_spdx


def main():
    shacl = '--no-shacl' not in sys.argv
    facts, models = load_inputs()
    eu_items = load_yaml(TARGETS / 'eu_form.yaml')['items']
    for d in ('spdx', 'cdx', 'eu'):
        (OUT / d).mkdir(parents=True, exist_ok=True)
    placement, eu_rows, failures = [], [], 0
    for m in models:
        key = m['key']
        recs = load_records(key)
        api = json.loads((RAW / key / 'api.json').read_text())

        spdx, rows = emit_spdx.build(m, recs, facts, api)
        placement += rows
        (OUT / 'spdx' / f'{key}.spdx3.json').write_text(json.dumps(spdx, indent=1, ensure_ascii=False))
        spdx_errs = validate_spdx(spdx, shacl=shacl)

        cdx, rows = emit_cdx.build(m, recs, facts, api)
        placement += rows
        (OUT / 'cdx' / f'{key}.cdx.json').write_text(json.dumps(cdx, indent=1, ensure_ascii=False))
        cdx_errs = validate_cdx(cdx)

        eu, rows = emit_eu.build(m, recs, facts, eu_items)
        placement += rows
        with open(OUT / 'eu' / f'{key}.yaml', 'w') as f:
            yaml.safe_dump(eu, f, sort_keys=False, allow_unicode=True, width=100)
        for it in eu['items']:
            eu_rows.append(dict(model=key, item=it['id'], section=it['section'], status=it['status'],
                                AIO=it['audience']['AIO'], NCA=it['audience']['NCA'], DP=it['audience']['DP'],
                                precision=it['precision'],
                                value=' | '.join(a['value'] for a in it['answers'])))

        for label, errs in (('spdx', spdx_errs), ('cdx', cdx_errs)):
            for e in errs[:10]:
                print(f'  {key} {label} INVALID: {e[:300]}')
            failures += bool(errs)
        print(f"{key:16} spdx {'ok' if not spdx_errs else 'INVALID'}  cdx {'ok' if not cdx_errs else 'INVALID'}")
    pd.DataFrame(eu_rows).to_csv(OUT / 'eu' / 'all.csv', index=False)
    pd.DataFrame(placement).to_csv(OUT / 'placement.csv', index=False)
    if failures:
        sys.exit(f'{failures} documents failed validation')


if __name__ == '__main__':
    main()

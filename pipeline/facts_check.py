"""Consistency checks for targets/facts.yaml against eu_form.yaml and the pinned schemas.

Usage: uv run python -m pipeline.facts_check   (exit 1 on problems; also run by tests)
"""
import json, re, sys

from .common import SCHEMAS, TARGETS, load_yaml

KINDS = {'field', 'escape_hatch', 'none'}
GROUPS = ['identity', 'licensing', 'architecture', 'training_data', 'training_process', 'energy',
          'use', 'evaluation', 'safety', 'lineage', 'distribution']
SOURCE = re.compile(r'^(card|api|config|tags|derived):\S+$')
DERIVED = {'pipeline_input_modalities', 'pipeline_output_modalities', 'model_index_datasets',
           'base_model_relation_tags', 'hub_url'}


def spdx_names():
    s = json.loads((SCHEMAS / 'spdx-3.0.1' / 'spdx-json-schema.json').read_text())
    defs = s['$defs']
    props = set()
    for d in defs.values():
        for part in d.get('allOf', []) + [d]:
            props |= set(part.get('properties', {}))
    rels = set(defs['prop_Relationship_relationshipType']['enum'])
    types = {k for k in defs if not k.startswith('prop_')}
    return props, rels, types


def cdx_names():
    c = json.loads((SCHEMAS / 'cyclonedx-1.7.2' / 'bom-1.7.schema.json').read_text())
    names = set()

    def walk(o):
        if isinstance(o, dict):
            names.update(o.get('properties', {}))
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(c)
    return names


def check():
    facts = load_yaml(TARGETS / 'facts.yaml')['facts']
    eu = {i['id'] for i in load_yaml(TARGETS / 'eu_form.yaml')['items']}
    sp_props, sp_rels, sp_types = spdx_names()
    cdx = cdx_names()
    errs, covered, ids = [], set(), set()
    for f in facts:
        fid = f['id']
        if fid in ids:
            errs.append(f'{fid}: duplicate id')
        ids.add(fid)
        if f.get('group') not in GROUPS:
            errs.append(f'{fid}: unknown group {f.get("group")}')
        for s in f['hf'].get('structured', []):
            if not SOURCE.match(s):
                errs.append(f'{fid}: bad structured source {s!r}')
            elif s.startswith('derived:') and s.split(':', 1)[1] not in DERIVED:
                errs.append(f'{fid}: unknown derived source {s!r}')
        for tgt in ('spdx', 'cdx'):
            t = f[tgt]
            if t['kind'] not in KINDS:
                errs.append(f'{fid}.{tgt}: bad kind {t["kind"]}')
            if (t['kind'] == 'none') != (t.get('path') is None):
                errs.append(f'{fid}.{tgt}: path must be null iff kind is none')
            path = t.get('path') or ''
            if tgt == 'spdx':
                for name in re.findall(r'\b((?:ai|dataset|software|simplelicensing)_[A-Za-z]+)', path):
                    if name not in sp_props and name not in sp_types:
                        errs.append(f'{fid}.spdx: {name} not in SPDX 3.0.1 schema')
                for rel in re.findall(r'Relationship\((\w+)\)', path):
                    if rel not in sp_rels:
                        errs.append(f'{fid}.spdx: relationship {rel} not in SPDX 3.0.1')
            else:
                for name in re.findall(r'(?:^|\.)([A-Za-z-]+)(?=[\[.]|$| )', path.split(' ')[0]):
                    if name not in cdx:
                        errs.append(f'{fid}.cdx: {name} not in CycloneDX 1.7 schema')
        if f.get('eu'):
            for item in f['eu']['items']:
                if item not in eu:
                    errs.append(f'{fid}.eu: unknown EU item {item}')
                covered.add(item)
    for item in sorted(eu - covered):
        errs.append(f'EU item {item} not covered by any fact')
    return facts, errs


def main():
    facts, errs = check()
    for e in errs:
        print('ERROR', e)
    print(f'{len(facts)} facts, {len(errs)} problems')
    sys.exit(1 if errs else 0)


if __name__ == '__main__':
    main()

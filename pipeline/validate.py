"""Offline validation against the pinned schemas in targets/schemas/.

SPDX 3.0.1: JSON schema + SHACL shapes from spdx-model.ttl (the spec requires both). The
JSON-LD @context URL is resolved to the pinned local copy, so nothing is fetched.
CycloneDX 1.7.2: JSON schema (draft-07) with its three sibling schemas in a local registry.
"""
import copy, json
from functools import lru_cache

import jsonschema
from referencing import Registry, Resource

from .common import SCHEMAS

SPDX_DIR = SCHEMAS / 'spdx-3.0.1'
CDX_DIR = SCHEMAS / 'cyclonedx-1.7.2'


@lru_cache
def _spdx_validator():
    schema = json.loads((SPDX_DIR / 'spdx-json-schema.json').read_text())
    return jsonschema.Draft202012Validator(schema)


@lru_cache
def _spdx_shapes():
    import rdflib
    return rdflib.Graph().parse(SPDX_DIR / 'spdx-model.ttl', format='turtle')


@lru_cache
def _spdx_context():
    return json.loads((SPDX_DIR / 'spdx-context.jsonld').read_text())['@context']


def validate_spdx(doc, shacl=True):
    errors = [f'schema: {e.json_path}: {e.message[:300]}' for e in _spdx_validator().iter_errors(doc)]
    if shacl:
        import pyshacl, rdflib
        local = copy.deepcopy(doc)
        local['@context'] = _spdx_context()
        g = rdflib.Graph().parse(data=json.dumps(local), format='json-ld')
        ok, _, text = pyshacl.validate(g, shacl_graph=_spdx_shapes(), ont_graph=_spdx_shapes(),
                                       inference='none', abort_on_first=False, allow_warnings=True)
        if not ok:
            errors += ['shacl: ' + b.strip() for b in text.split('Constraint Violation')[1:]]
    return errors


@lru_cache
def _cdx_validator():
    registry = Registry()
    for name in ['spdx.schema.json', 'jsf-0.82.schema.json', 'cryptography-defs.schema.json']:
        s = json.loads((CDX_DIR / name).read_text())
        res = Resource.from_contents(s, default_specification=jsonschema.Draft7Validator.META_SCHEMA and
                                     __import__('referencing.jsonschema').jsonschema.DRAFT7)
        registry = registry.with_resource(name, res)
        if '$id' in s:
            registry = registry.with_resource(s['$id'], res)
    schema = json.loads((CDX_DIR / 'bom-1.7.schema.json').read_text())
    # relative $refs resolve against the schema's $id base
    base = schema['$id'].rsplit('/', 1)[0] + '/'
    for name in ['spdx.schema.json', 'jsf-0.82.schema.json', 'cryptography-defs.schema.json']:
        registry = registry.with_resource(base + name, registry[name])
    return jsonschema.Draft7Validator(schema, registry=registry,
                                      format_checker=jsonschema.Draft7Validator.FORMAT_CHECKER)


def validate_cdx(doc):
    return [f'schema: {e.json_path}: {e.message[:300]}' for e in _cdx_validator().iter_errors(doc)]

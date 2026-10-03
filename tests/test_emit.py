"""Emitters: synthetic records exercising every field handler must validate; so must the
documents built from the cached cards."""
import json

import pytest

from pipeline import emit_cdx, emit_eu, emit_spdx
from pipeline.common import EXTRACTED, RAW, TARGETS, load_yaml
from pipeline.emit_common import load_inputs, load_records, parse_date, parse_energy_kwh
from pipeline.validate import validate_cdx, validate_spdx

FACTS, MODELS = load_inputs()
MODEL = dict(key='synthetic', repo_id='org/model-7b', retrieved_at='2026-09-30T10:00:00+00:00')
API = {'id': 'org/model-7b', 'sha': 'b' * 40, 'author': 'org', 'createdAt': '2026-01-01T00:00:00.000Z'}

SPECIAL = {
    'model_name': 'org/model-7b', 'model_authenticity': 'b' * 40, 'release_date': 'April 5, 2025',
    'license': 'apache-2.0', 'training_datasets': ['org/data-a', 'org/data-b'],
    'eval_datasets': ['MMLU'], 'data_modality': 'text and images', 'training_energy': '1.2 MWh',
    'input_modalities': ['text', 'image'], 'output_modalities': ['text'], 'base_model': ['org/base-7b'],
    'base_model_relation': ['finetune'], 'download_location': 'https://huggingface.co/org/model-7b',
    'max_input_size': 32768, 'carbon_emissions': '12 tCO2eq',
    'eval_results': [{'name': 'm', 'results': [{'dataset': {'name': 'MMLU'},
                                                'metrics': [{'type': 'accuracy', 'value': 71.2}]}]}],
}


def synthetic(status_for=lambda f: 'prose'):
    recs = {}
    for f in FACTS:
        v = SPECIAL.get(f['id'], f'Stated value for {f["id"]}.')
        st = 'structured' if not isinstance(v, str) or f['id'] in ('license', 'model_name') else status_for(f)
        recs[f['id']] = dict(fact_id=f['id'], status=st, value=v, quote='q', source_url='u',
                             source_type='card', evidence=[dict(path='card:license', value=v)])
    return recs


def outcomes(rows):
    return {r['fact_id']: r['outcome'] for r in rows}


def test_spdx_all_facts_validates_and_logs_every_fact():
    doc, rows = emit_spdx.build(MODEL, synthetic(), FACTS, API)
    assert validate_spdx(doc) == []
    out = outcomes(rows)
    assert set(out) == {f['id'] for f in FACTS}
    assert out['personal_data'] == 'unplaceable'  # prose into a yes/no enum
    assert out['autonomy'] == 'unplaceable'
    assert out['training_energy'] == 'placed'
    assert out['param_count'] == 'escape_hatch'
    pkg = next(e for e in doc['@graph'] if e.get('spdxId', '').endswith('#model'))
    assert pkg['releaseTime'] == '2025-04-05T00:00:00Z'
    rels = {e['relationshipType'] for e in doc['@graph'] if e['type'] == 'Relationship'}
    assert {'trainedOn', 'testedOn', 'descendantOf', 'dependsOn', 'hasDeclaredLicense',
            'hasConcludedLicense'} <= rels


def test_spdx_nothing_disclosed_still_validates():
    recs = {f['id']: dict(fact_id=f['id'], status='not_stated', value=None) for f in FACTS}
    doc, rows = emit_spdx.build(MODEL, recs, FACTS, API)
    assert validate_spdx(doc) == []
    pkg = next(e for e in doc['@graph'] if e.get('spdxId', '').endswith('#model'))
    assert 'repo creation time' in pkg['comment']


def test_cdx_all_facts_validates():
    doc, rows = emit_cdx.build(MODEL, synthetic(), FACTS, API)
    assert validate_cdx(doc) == []
    out = outcomes(rows)
    assert out['training_energy'] == 'unplaceable'  # requires energy provider details
    assert out['training_method'] == 'unplaceable'  # approach.type enum
    assert out['base_model'] == 'placed'
    assert doc['components'][0]['pedigree']['ancestors'][0]['name'] == 'org/base-7b'


def test_eu_fill_covers_every_item():
    items = load_yaml(TARGETS / 'eu_form.yaml')['items']
    doc, _ = emit_eu.build(MODEL | {'retrieved_at': 'x'}, synthetic(), FACTS, items)
    assert len(doc['items']) == len(items)
    assert all(it['status'] == 'answered' for it in doc['items'])


def test_parsers():
    assert parse_date('2025-04-05') == '2025-04-05T00:00:00Z'
    assert parse_date('sometime in spring') is None
    assert parse_energy_kwh('about 1.2 MWh of electricity') == pytest.approx(1200)
    assert parse_energy_kwh('3,500 kWh') == pytest.approx(3500)
    assert parse_energy_kwh('lots') is None


@pytest.mark.skipif(not any(EXTRACTED.glob('*.json')), reason='no extracted records cached')
@pytest.mark.parametrize('m', MODELS, ids=lambda m: m['key'])
def test_cached_models_validate(m):
    api = json.loads((RAW / m['key'] / 'api.json').read_text())
    recs = load_records(m['key'])
    assert validate_spdx(emit_spdx.build(m, recs, FACTS, api)[0]) == []
    assert validate_cdx(emit_cdx.build(m, recs, FACTS, api)[0]) == []

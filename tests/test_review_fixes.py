"""Regression tests for the code-review findings of 2026-10-03."""
import json
from types import SimpleNamespace

import pytest

from pipeline import emit_cdx, emit_spdx, extract
from pipeline.common import CacheMiss
from pipeline.validate import validate_cdx, validate_spdx
from tests.test_emit import API, FACTS, MODEL, synthetic

FACT = {'id': 'training_energy', 'description': 'd', 'hf': {}}


def test_cached_error_is_not_served(tmp_path, monkeypatch):
    monkeypatch.setattr(extract, 'LLM_CACHE', tmp_path)
    readme = 'card text'
    path = tmp_path / 'm' / f"training_energy__{extract.PROMPT_VERSION}.json"
    path.parent.mkdir()
    import hashlib
    path.write_text(json.dumps(dict(model=extract.MODEL, readme_sha256=hashlib.sha256(readme.encode()).hexdigest(),
                                    answer=dict(status='error', error='timeout'))))
    with pytest.raises(CacheMiss):  # OFFLINE in tests: a retry is attempted, not the cached error
        extract.ask('m', 'org/m', readme, FACT)


@pytest.mark.parametrize('resp', [
    SimpleNamespace(stop_reason='max_tokens', content=[SimpleNamespace(type='text', text='{"status": "sta')]),
    SimpleNamespace(stop_reason='end_turn', content=[]),
    SimpleNamespace(stop_reason='end_turn', content=[SimpleNamespace(type='text', text='not json')]),
])
def test_bad_sdk_response_becomes_error_answer(resp, monkeypatch):
    resp.model, resp.usage = extract.MODEL, SimpleNamespace(to_dict=lambda: {})
    fake = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=lambda **k: resp)))
    monkeypatch.setattr(extract, 'client', lambda: fake)
    answer, _ = extract.ask_sdk('system', 'user')
    assert answer['status'] == 'error'


def test_large_energy_is_a_plain_decimal():
    recs = synthetic()
    recs['training_energy']['value'] = '2.5 GWh'
    doc, _ = emit_spdx.build(MODEL, recs, FACTS, API)
    pkg = next(e for e in doc['@graph'] if e.get('spdxId', '').endswith('#model'))
    q = pkg['ai_energyConsumption']['ai_trainingEnergyConsumption'][0]['ai_energyQuantity']
    assert q == '2500000'
    assert validate_spdx(doc) == []
    assert emit_spdx.decimal_text(1234567.0) == '1234567'


def test_ai_limitation_escape_lands_in_ai_limitation():
    doc, rows = emit_spdx.build(MODEL, synthetic(), FACTS, API)
    pkg = next(e for e in doc['@graph'] if e.get('spdxId', '').endswith('#model'))
    assert 'bias_fairness_evaluation:' in pkg['ai_limitation']
    assert 'bias_fairness_evaluation:' not in pkg.get('comment', '')


def test_eval_dataset_sharing_a_training_name_is_kept():
    recs = synthetic()
    recs['training_datasets']['value'] = ['MMLU']
    recs['eval_datasets']['value'] = ['MMLU']
    doc, _ = emit_cdx.build(MODEL, recs, FACTS, API)
    roles = [c for c in doc['components'] if c.get('name') == 'MMLU']
    assert len(roles) == 2
    assert any(p['value'] == 'evaluation' for c in roles for p in c.get('properties', []))
    assert validate_cdx(doc) == []


def test_distribution_channels_logged_as_escape_hatch():
    doc, rows = emit_cdx.build(MODEL, synthetic(), FACTS, API)
    row = next(r for r in rows if r['fact_id'] == 'distribution_channels')
    assert row['outcome'] == 'escape_hatch'
    assert any(p['name'].endswith('distribution_channels') for p in doc['components'][0]['properties'])


# ---- follow-ups from the human mini review (2026-10-03)

def test_html_card_text_keeps_link_targets():
    from pipeline.fetch import html_card_text
    html = ('<div class="model-card-content"><h2><a href="#x">#</a>Energy</h2>'
            '<p>Method can be found <a href="https://arxiv.org/pdf/2204.05149">here</a>. '
            'See <a href="/org/model">/org/model</a> and <a href="https://a.b/c">https://a.b/c</a>.</p></div>')
    text = html_card_text(html)
    assert 'found here (https://arxiv.org/pdf/2204.05149).' in text
    assert '(https://huggingface.co/org/model)' in text
    assert '(https://a.b/c)' not in text  # link text already is the URL
    assert '(#x)' not in text


def test_custom_licence_headline_names_the_licence():
    from tests.test_extract import CTX, fact
    r = extract.pass1(fact('license', 'card:license', 'card:license_name', 'card:license_link'), CTX)
    assert r['value'] == 'org-licence (other)'
    assert r['evidence'][0]['value'] == 'other'  # raw metadata kept as evidence


def test_card_body_strips_front_matter():
    assert extract.card_body('---\nlicense: mit\n---\n# Card\nText') == '# Card\nText'
    assert extract.card_body('# No front matter') == '# No front matter'


def test_prose_check_verifies_quotes_before_trusting_agreement():
    body = '# Card\nSupports image, video and multi-image understanding.\n'
    rec = dict(repo_id='r', check_version='m1', answer=dict(
        status='stated', value='text, image, video', agreement='adds', section='Card',
        quotes=['Supports image, video and multi-image understanding.']))
    assert extract.prose_check(rec, body)['agreement'] == 'adds'
    rec['answer']['quotes'] = ['Supports audio input.']
    out = extract.prose_check(rec, body)
    assert out['status'] == 'rejected_quote' and out['agreement'] == 'unverified'

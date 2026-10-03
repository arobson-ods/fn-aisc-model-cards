import pytest

from pipeline import facts_check
from pipeline.report import classify


def test_facts_yaml_consistent():
    facts, errs = facts_check.check()
    assert errs == []
    assert 40 <= len(facts) <= 70


@pytest.mark.parametrize('status,kind,target,audience,expected', [
    # schema gap wins regardless of disclosure
    ('prose', 'none', 'spdx', {}, ('schema', False)),
    ('not_stated', 'escape_hatch', 'cdx', {}, ('schema', True)),
    ('structured', 'none', 'eu', {}, ('schema', False)),
    # audience: EU, not stated, no DP cross
    ('not_stated', 'field', 'eu', {'AIO': True, 'NCA': True, 'DP': False}, ('audience', False)),
    ('rejected_quote', 'field', 'eu', {'AIO': True, 'NCA': False, 'DP': False}, ('audience', False)),
    # disclosure: EU item addressed to downstream providers, or a BOM target
    ('not_stated', 'field', 'eu', {'AIO': True, 'NCA': True, 'DP': True}, ('disclosure', False)),
    ('not_stated', 'field', 'spdx', {}, ('disclosure', False)),
    # structure: prose where a BOM field exists; EU is a document so prose is fine
    ('prose', 'field', 'cdx', {}, ('structure', False)),
    ('prose', 'field', 'eu', {'DP': True}, (None, False)),
    # no gap
    ('structured', 'field', 'spdx', {}, (None, False)),
    ('pending', 'field', 'spdx', {}, ('pending', False)),
])
def test_classify(status, kind, target, audience, expected):
    assert classify(status, kind, target, audience) == expected

"""Automated second-model check of the spot-check sample, plus a small human sample.

  uv run python -m pipeline.autocheck          # judge every row of out/spotcheck.csv; write
                                               # out/autocheck.csv and out/spotcheck_mini.csv
  uv run python -m pipeline.autocheck --score  # after a human fills spotcheck_mini.csv

A different model (CHECK_MODEL) re-reads the card and grades each extracted record:
  prose       are the quotes about this model, and is the value fully supported by them?
  structured  does the metadata value answer the fact's definition?
  not_stated  is the fact really absent from the card?
This is an automated consistency check, NOT a human spot-check; report it as such.
The mini sample is every row the checker did not pass (up to 10) plus random passes, 15 in all,
for a person to grade, so the checker's reliability is measured too.
"""
import hashlib, json, random, sys
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from .common import OFFLINE, OUT, RAW, CacheMiss
from .extract import ask_cli

CHECK_MODEL = 'claude-opus-5-5'
CHECK_VERSION = 'c1'
CACHE = RAW / 'llm_check'
MINI_SIZE, MINI_FLAGGED = 15, 10
SEED = 20260930

SYSTEM = """You audit facts that another system extracted from an AI model card. Be strict and literal. Use only the card text below; never use outside knowledge.

<model_card>
{readme}
</model_card>"""

USER = {
    'prose': """Fact definition: {what}
Extracted value: {value}
Quotes given as evidence (separated by [...]): {quote}

Grade the extraction:
- "y": the quotes are about this model and support every claim in the value, and the value answers the fact definition.
- "partial": mostly right, but the value adds claims the quotes don't support, drops an important qualifier, or only partly answers the definition.
- "n": wrong, unsupported, about a different model, or does not answer the definition.""",
    'structured': """Fact definition: {what}
Value taken from the model's structured metadata ({quote}): {value}

Grade: "y" if this value is a correct answer to the fact definition for this model; "partial" if it is related but only a weak or indirect answer; "n" if it does not answer the definition or conflicts with the card text.""",
    'not_stated': """Fact definition: {what}
The extractor answered that the card does NOT state this fact.

Search the whole card. Grade "y" if the card really does not state it; "n" if it does (quote the passage in your reason); "partial" if the card only hints at it or states it for a different model.""",
}

SCHEMA = {'type': 'object', 'additionalProperties': False,
          'required': ['verdict', 'reason'],
          'properties': {'verdict': {'type': 'string', 'enum': ['y', 'partial', 'n']},
                         'reason': {'type': 'string'}}}


def judge(row):
    readme = (RAW / row['model'] / 'README.md').read_text()
    user = USER[row['status']].format(what=row['what_to_find'], value=row['value'], quote=row['quote'])
    h = hashlib.sha256((readme + user).encode()).hexdigest()[:16]
    path = CACHE / row['model'] / f"{row['fact_id']}__{CHECK_VERSION}.json"
    if path.exists():
        rec = json.loads(path.read_text())
        if rec['input_sha'] == h and rec['answer'].get('status') != 'error':
            return rec
    if OFFLINE:
        raise CacheMiss(str(path))
    answer, meta = ask_cli(SYSTEM.format(readme=readme), user, schema=SCHEMA, model=CHECK_MODEL)
    rec = dict(model=CHECK_MODEL, check_version=CHECK_VERSION, input_sha=h, request_user=user,
               answer=answer, **meta)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec, indent=1, ensure_ascii=False))
    return rec


def pts(v):
    return {'y': 1.0, 'partial': 0.5}.get(v, 0.0)


def main():
    if '--score' in sys.argv:
        return score()
    df = pd.read_csv(OUT / 'spotcheck.csv', dtype=str).fillna('')
    with ThreadPoolExecutor(6) as ex:
        recs = list(ex.map(judge, df.to_dict('records')))
    df['auto_verdict'] = [r['answer'].get('verdict', 'error') for r in recs]
    df['auto_reason'] = [r['answer'].get('reason') or r['answer'].get('error', '') for r in recs]
    df.to_csv(OUT / 'autocheck.csv', index=False)

    ok = df[df.auto_verdict.isin(['y', 'partial', 'n'])]
    summary = dict(kind='automated second-model check, not human-verified', checker=CHECK_MODEL,
                   rows=len(df), graded=len(ok), accuracy=round(ok.auto_verdict.map(pts).mean(), 3),
                   counts=ok.auto_verdict.value_counts().to_dict(),
                   by_status=ok.groupby('status').auto_verdict.apply(lambda s: round(s.map(pts).mean(), 3)).to_dict(),
                   by_model=ok.groupby('model').auto_verdict.apply(lambda s: round(s.map(pts).mean(), 3)).to_dict())
    (OUT / 'autocheck_summary.json').write_text(json.dumps(summary, indent=1))

    rng = random.Random(SEED)
    flagged = df[df.auto_verdict != 'y'].index.tolist()
    passed = df[df.auto_verdict == 'y'].index.tolist()
    pick = rng.sample(flagged, min(MINI_FLAGGED, len(flagged)))
    pick += rng.sample(passed, min(MINI_SIZE - len(pick), len(passed)))
    mini = df.loc[sorted(pick)].copy()
    mini['correct'], mini['notes'] = '', ''
    # columns to fill first; long text last so it can't push them off screen
    mini = mini[['correct', 'notes', 'model', 'fact_id', 'status', 'auto_verdict', 'source_url',
                 'what_to_find', 'value', 'auto_reason', 'quote']]
    mini_path = OUT / 'spotcheck_mini.csv'
    if mini_path.exists() and pd.read_csv(mini_path, dtype=str)['correct'].notna().any():
        print(f'{mini_path} already has reviews; not overwritten')
    else:
        mini.to_csv(mini_path, index=False)
    print(json.dumps(summary, indent=1))
    print(f'\nHuman sample: {len(mini)} rows in {mini_path} '
          f'({min(MINI_FLAGGED, len(flagged))} the checker flagged, the rest random passes).')


def score():
    mini = pd.read_csv(OUT / 'spotcheck_mini.csv', dtype=str).fillna('')
    mini['correct'] = mini['correct'].str.strip().str.lower()
    done = mini[mini.correct.isin(['y', 'partial', 'n'])]
    if done.empty:
        sys.exit('spotcheck_mini.csv has no reviewed rows yet')
    auto = json.loads((OUT / 'autocheck_summary.json').read_text())
    summary = dict(auto,
                   human_reviewed=len(done),
                   human_accuracy_on_mini=round(done.correct.map(pts).mean(), 3),
                   checker_agreement_with_human=round((done.correct == done.auto_verdict).mean(), 3),
                   note='The mini sample over-represents rows the checker flagged, so human_accuracy_on_mini '
                        'is not an estimate of overall accuracy. Use it to judge the checker.')
    (OUT / 'autocheck_summary.json').write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    main()

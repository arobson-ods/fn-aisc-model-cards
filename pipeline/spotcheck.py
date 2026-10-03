"""Human spot-check of extraction.

  uv run python -m pipeline.spotcheck          # write out/spotcheck.csv sample, then stop
  uv run python -m pipeline.spotcheck --score  # after review: compute accuracy

Sample: seeded, stratified by model: at least 20% of each model's disclosed records
(structured + prose) and 10% of its not_stated records (to catch misses), minimum 1 each.
Reviewers fill `correct` with y / n / partial, checking value and quote against source_url.
For not_stated rows, `correct` = y means the card really does not state the fact.
"""
import json, math, random, sys

import pandas as pd

from .common import EXTRACTED, OUT, TARGETS, load_yaml

SEED = 20260930
COLS = ['model', 'fact_id', 'what_to_find', 'status', 'source_type', 'value', 'quote', 'section', 'source_url',
        'correct', 'notes']


def sample():
    rng = random.Random(SEED)
    desc = {f['id']: f['description'] for f in load_yaml(TARGETS / 'facts.yaml')['facts']}
    rows = []
    for path in sorted(EXTRACTED.glob('*.json')):
        recs = json.loads(path.read_text())
        disclosed = [r for r in recs if r['status'] in ('structured', 'prose')]
        missing = [r for r in recs if r['status'] == 'not_stated']
        for pool, share in ((disclosed, 0.2), (missing, 0.1)):
            if pool:
                rows += [dict(r, what_to_find=desc[r['fact_id']])
                         for r in rng.sample(pool, max(1, math.ceil(len(pool) * share)))]
    df = pd.DataFrame([{c: (json.dumps(r.get(c), ensure_ascii=False) if isinstance(r.get(c), (list, dict))
                            else r.get(c)) for c in COLS} for r in rows])
    df['correct'], df['notes'] = '', ''
    return df[COLS]


def score(df):
    df = df.copy()
    df['correct'] = df['correct'].fillna('').astype(str).str.strip().str.lower()
    done = df[df['correct'] != '']
    if done.empty:
        sys.exit('out/spotcheck.csv has no reviewed rows yet')
    ok = lambda s: {'y': 1.0, 'partial': 0.5}.get(s, 0.0)
    done = done.assign(score=done['correct'].map(ok))
    summary = dict(reviewed=len(done), of=len(df), accuracy=round(done['score'].mean(), 3),
                   by_status=done.groupby('status')['score'].mean().round(3).to_dict(),
                   by_model=done.groupby('model')['score'].mean().round(3).to_dict(),
                   counts=done['correct'].value_counts().to_dict())
    (OUT / 'spotcheck_summary.json').write_text(json.dumps(summary, indent=1))
    return summary


def main():
    path = OUT / 'spotcheck.csv'
    if '--score' in sys.argv:
        print(json.dumps(score(pd.read_csv(path, dtype=str)), indent=1))
        return
    if path.exists() and pd.read_csv(path, dtype=str)['correct'].notna().any() and '--force' not in sys.argv:
        sys.exit('out/spotcheck.csv already has reviews; use --score, or --force to resample')
    OUT.mkdir(exist_ok=True)
    df = sample()
    df.to_csv(path, index=False)
    print(f'{len(df)} rows written to {path}. Review them (correct = y / n / partial), '
          f'then run: uv run python -m pipeline.spotcheck --score')


if __name__ == '__main__':
    main()

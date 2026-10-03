"""Extract facts from cached model cards into data/extracted/{key}.json.

Usage: uv run python -m pipeline.extract [--models olmo,llama] [--pass1-only]

Pass 1 (deterministic): the hf.structured sources in targets/facts.yaml, read from the cached
HF API response, card YAML (cardData) and config.json.
Pass 2 (LLM): for each fact pass 1 did not find (and hf.prose is not false), ask Claude for
{status, value, quote, section} from the README text only. Quotes are checked against the cached
README; a value whose quote is not found is rejected (status rejected_quote), never repaired.
LLM responses are cached under data/raw/llm/{key}/{fact}__{PROMPT_VERSION}.json.
"""
import argparse, hashlib, json, os, re, subprocess, tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .common import (EXTRACTED, OFFLINE, RAW, ROOT, TARGETS, CacheMiss, load_dotenv, load_yaml,
                     quote_in_source)

MODEL = 'claude-sonnet-5-5'
PROMPT_VERSION = 'v4'  # v2: several quotes per value; v3: value limited to what the quotes say;
                       # v4: related information or a statement of absence is not_stated
LLM_CACHE = RAW / 'llm'

SOURCE_TYPE = {'card': 'card_metadata', 'tags': 'card_metadata', 'api': 'hub_api',
               'config': 'repo_config', 'derived': None}

# HF pipeline_tag -> (input modalities, output modalities). Only tags whose modalities are
# fixed by definition; any-to-any and unknown tags give nothing.
PIPELINE_MODALITIES = {
    'text-generation': (['text'], ['text']),
    'image-text-to-text': (['text', 'image'], ['text']),
    'automatic-speech-recognition': (['audio'], ['text']),
    'text-to-image': (['text'], ['image']),
    'image-feature-extraction': (['image'], ['embedding']),
}
RELATIONS = ('finetune', 'quantized', 'merge', 'adapter')


def dig(obj, path):
    for part in path.split('.'):
        if isinstance(obj, dict) and part in obj:
            obj = obj[part]
        else:
            return None
    return obj


def empty(v):
    return v is None or v == '' or v == [] or v == {}


def derived(name, ctx):
    """Deterministic lookups (see facts.yaml `derived:` sources). Returns (value, source_type)."""
    api, card = ctx['api'], ctx['card']
    tag = card.get('pipeline_tag') or api.get('pipeline_tag')
    if name in ('pipeline_input_modalities', 'pipeline_output_modalities'):
        io = PIPELINE_MODALITIES.get(tag)
        src = 'card_metadata' if card.get('pipeline_tag') else 'hub_api'
        return (io[0 if name.endswith('input_modalities') else 1] if io else None), src
    if name == 'model_index_datasets':
        mi = card.get('model-index') or api.get('model-index') or []
        names = sorted({r.get('dataset', {}).get('name') or r.get('dataset', {}).get('type')
                        for m in mi for r in m.get('results', []) if r.get('dataset')} - {None})
        return names or None, 'card_metadata'
    if name == 'base_model_relation_tags':
        rels = sorted({t.split(':')[1] for t in api.get('tags', [])
                       if t.startswith('base_model:') and t.split(':')[1] in RELATIONS})
        return rels or None, 'hub_api'
    if name == 'hub_url':
        return f"https://huggingface.co/{api['id']}", 'hub_api'
    raise KeyError(name)


def resolve(src, ctx):
    """Resolve one hf.structured source. Returns (value, source_type, path) or None."""
    kind, spec = src.split(':', 1)
    if kind == 'derived':
        v, st = derived(spec, ctx)
        return None if empty(v) else (v, st, src)
    if kind == 'tags':
        vals = [t[len(spec) + 1:] if t != spec else t for t in ctx['api'].get('tags', [])
                if t == spec or t.startswith(spec + ':')]
        return (vals, SOURCE_TYPE[kind], src) if vals else None
    base = {'card': ctx['card'], 'api': ctx['api'], 'config': ctx['config']}[kind]
    for alt in spec.split('|'):
        v = dig(base, alt)
        if not empty(v):
            if alt == 'transformers_version':
                v = f'transformers {v}'  # the key names the library; keep it in the value
            return v, SOURCE_TYPE[kind], f'{kind}:{alt}'
    return None


def pass1(fact, ctx):
    hits = [h for h in (resolve(s, ctx) for s in fact['hf'].get('structured', [])) if h]
    if not hits:
        return None
    value, st, path = hits[0]
    if fact['id'] == 'license' and value == 'other':
        # HF convention for a custom licence: 'other' plus license_name; show the name
        name = next((v for v, _, p in hits if p == 'card:license_name'), None)
        value = f'{name} (other)' if name else value
    url = ctx['src']['config_url'] if st == 'repo_config' else ctx['src']['api_url']
    return dict(status='structured', value=value, source_type=st, source_url=url,
                quote=f'{path} = {json.dumps(value, ensure_ascii=False)[:300]}', section=path,
                evidence=[dict(path=p, value=v, source_type=t) for v, t, p in hits],
                quote_check='structured', pass_=1)


# ---------------------------------------------------------------- pass 2

SYSTEM = """You extract facts from an AI model card for a research comparison of model documentation standards.

Rules:
- Use ONLY the model card text below. Never use outside or general knowledge about the model, its lab or its family, and never infer or estimate a value that the card does not state.
- If the card does not state the fact, answer status "not_stated". "Not stated" is a valid and important answer; prefer it over a guess.
- Related information is not the fact. If the card gives only something adjacent (for example GPU hours or hardware power when asked for energy in kWh/MWh, or a hardware list when asked for training time), or says the fact is not reported, answer "not_stated". Never put a description of what is missing in the value.
- If the fact is stated, give the value concisely, as the card states it (keep numbers and units exactly).
- quotes: 1-8 passages copied verbatim from the card. Each passage is one contiguous stretch of text (a sentence or two, a list item, or one table row). Do not paraphrase, join separate passages into one, or add ellipses. Code checks every quote character by character, and rejects the value if any quote is not found.
- The value must contain ONLY claims that appear in the quotes. Every name, number, version and qualifier in the value must be readable in at least one quote. Check this before answering.
- If the fact has more parts than the quotes can cover (long lists of benchmarks, deployment options, training stages), give a shorter value covering only the quoted parts. A shorter value that the quotes fully support is better than a complete value that they only partly support.
- section is the heading of the card section containing the first quote ("" if none).
- Facts about a different model (e.g. a base model or sibling model mentioned in the card) count only if the card says they apply to this model.

<model_card repo="{repo_id}">
{readme}
</model_card>"""

USER = """Fact: {fact_id}
What to find: {description}
Card sections that often contain it: {hints}

Answer with status, value, quotes and section."""

SCHEMA = {
    'type': 'object',
    'properties': {
        'status': {'type': 'string', 'enum': ['stated', 'not_stated']},
        'value': {'type': 'string'},
        'quotes': {'type': 'array', 'items': {'type': 'string'}},
        'section': {'type': 'string'},
    },
    'required': ['status', 'value', 'quotes', 'section'],
    'additionalProperties': False,
}

_client = None


def client():
    global _client
    if _client is None:
        import anthropic
        load_dotenv()
        _client = anthropic.Anthropic()
    return _client


def backend():
    """'sdk' when an API key is available, else 'cli' (Claude Code in headless mode, which
    uses the logged-in Claude subscription). Override with LLM_BACKEND=sdk|cli."""
    load_dotenv()
    if os.environ.get('LLM_BACKEND'):
        return os.environ['LLM_BACKEND']
    return 'sdk' if os.environ.get('ANTHROPIC_API_KEY') else 'cli'


def ask_sdk(system, user, schema=None):
    resp = client().beta.messages.create(
        model=MODEL, max_tokens=4000,
        betas=['server-side-fallback-2026-07-01'], fallbacks='default',
        system=[{'type': 'text', 'text': system, 'cache_control': {'type': 'ephemeral'}}],
        messages=[{'role': 'user', 'content': user}],
        output_config={'effort': 'medium', 'format': {'type': 'json_schema', 'schema': schema or SCHEMA}},
    )
    text = next((b.text for b in resp.content if b.type == 'text'), None)
    try:
        if resp.stop_reason in ('refusal', 'max_tokens') or text is None:
            raise ValueError(resp.stop_reason or 'no text block')
        answer = json.loads(text)
    except ValueError as e:  # json.JSONDecodeError is a ValueError
        answer = dict(status='error', value='', quotes=[], section='', error=str(e)[:200])
    return answer, dict(backend='sdk', served_by=resp.model, stop_reason=resp.stop_reason,
                        usage=resp.usage.to_dict())


CLI_CWD = Path(tempfile.gettempdir()) / 'model-cards-llm'  # empty dir: no CLAUDE.md picked up


def ask_cli(system, user, retries=2, schema=None, model=None):
    """Headless Claude Code: no tools, no settings/hooks, no session saved, schema-validated output."""
    CLI_CWD.mkdir(exist_ok=True)
    cmd = ['claude', '-p', '--model', model or MODEL, '--tools', '', '--setting-sources', '',
           '--no-session-persistence', '--output-format', 'json',
           '--system-prompt', system, '--json-schema', json.dumps(schema or SCHEMA)]
    for attempt in range(retries + 1):
        proc = subprocess.run(cmd, input=user, capture_output=True, text=True, cwd=CLI_CWD, timeout=600)
        try:
            out = json.loads(proc.stdout)
        except json.JSONDecodeError:
            out = {'is_error': True, 'result': (proc.stdout + proc.stderr)[-500:]}
        if not out.get('is_error') and out.get('structured_output'):
            break
    else:
        return (dict(status='error', error=str(out.get('result'))[:500]), dict(backend='cli'))
    return out['structured_output'], dict(
        backend='cli', served_by=sorted(out.get('modelUsage', {})), stop_reason=out.get('subtype'),
        usage={k: v for k, v in (out.get('usage') or {}).items() if isinstance(v, (int, float))},
        cost_usd_list_price=out.get('total_cost_usd'), duration_ms=out.get('duration_ms'))


def ask(key, repo_id, readme, fact):
    """One LLM call per (model, fact, prompt version), cached on disk."""
    path = LLM_CACHE / key / f"{fact['id']}__{PROMPT_VERSION}.json"
    readme_sha = hashlib.sha256(readme.encode()).hexdigest()
    if path.exists():
        rec = json.loads(path.read_text())
        if (rec['readme_sha256'] == readme_sha and rec['model'] == MODEL
                and rec['answer'].get('status') != 'error'):
            return rec
    if OFFLINE:
        raise CacheMiss(str(path))
    system = SYSTEM.format(repo_id=repo_id, readme=readme)
    user = USER.format(fact_id=fact['id'], description=fact['description'],
                       hints=', '.join(fact['hf'].get('prose_hint') or []) or '(any)')
    call = ask_sdk if backend() == 'sdk' else ask_cli
    answer, meta = call(system, user)
    rec = dict(model=MODEL, prompt_version=PROMPT_VERSION, repo_id=repo_id, fact_id=fact['id'],
               readme_sha256=readme_sha, request_user=user, answer=answer, **meta)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec, indent=1, ensure_ascii=False))
    return rec


def pass2(fact, ctx, rec):
    a = rec['answer']
    base = dict(source_type='card', source_url=ctx['src']['readme_url'], pass_=2,
                llm_cache=f"data/raw/llm/{ctx['key']}/{fact['id']}__{PROMPT_VERSION}.json")
    if a['status'] == 'error':
        return dict(base, status='llm_error', value=None, quote=None, section=None)
    if a['status'] == 'not_stated' or not a['value'].strip():
        return dict(base, status='not_stated', value=None, quote=None, section=None)
    quotes = [q for q in a.get('quotes', []) if q.strip()]
    checks = [quote_in_source(q, ctx['readme']) for q in quotes]
    ok = bool(quotes) and all(checks)
    check = ('exact' if all(c == 'exact' for c in checks) else 'normalised') if ok else 'not_found'
    return dict(base, status='prose' if ok else 'rejected_quote', value=a['value'],
                quote=' [...] '.join(quotes), quotes=quotes, section=a['section'], quote_check=check,
                failed_quotes=[q for q, c in zip(quotes, checks) if not c] or None)


# ---------------------------------------------------------------- metadata vs prose

CHECK_VERSION = 'm1'  # prompt version of the metadata-vs-prose check

CHECK_USER = """Fact: {fact_id}
What to find: {description}
The card's machine-readable metadata gives: {meta}

Read only the card's TEXT (the model card above has no YAML front matter; ignore any code samples' arguments as statements of fact). Answer:
- status: "stated" if the text states this fact for this model, else "not_stated".
- value: what the text states, containing only claims the quotes support ("" if not stated).
- quotes: 1-8 passages copied verbatim from the text that support the value ([] if not stated).
- agreement: "agrees" if the text says the same as the metadata; "adds" if it is consistent but says more (for example an extra item); "conflicts" if it contradicts the metadata; "not_stated" if the text does not state the fact.
- section: heading of the section containing the first quote ("" if none)."""

CHECK_SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'required': ['status', 'value', 'quotes', 'agreement', 'section'],
    'properties': {
        'status': {'type': 'string', 'enum': ['stated', 'not_stated']},
        'value': {'type': 'string'},
        'quotes': {'type': 'array', 'items': {'type': 'string'}},
        'agreement': {'type': 'string', 'enum': ['agrees', 'adds', 'conflicts', 'not_stated']},
        'section': {'type': 'string'},
    },
}


def card_body(readme):
    """README without its YAML front matter, so metadata can't be quoted as prose."""
    m = re.match(r'---\n.*?\n---\n', readme, re.S)
    return readme[m.end():] if m else readme


def ask_check(key, repo_id, body, fact, meta_value):
    """Does the card text agree with the metadata value? Cached per (model, fact, CHECK_VERSION)."""
    meta = json.dumps(meta_value, ensure_ascii=False)[:500]
    user = CHECK_USER.format(fact_id=fact['id'], description=fact['description'], meta=meta)
    sha = hashlib.sha256((body + user).encode()).hexdigest()
    path = LLM_CACHE / key / f"{fact['id']}__{CHECK_VERSION}.json"
    if path.exists():
        rec = json.loads(path.read_text())
        if rec['input_sha256'] == sha and rec['model'] == MODEL and rec['answer'].get('status') != 'error':
            return rec
    if OFFLINE:
        raise CacheMiss(str(path))
    system = SYSTEM.format(repo_id=repo_id, readme=body)
    if backend() == 'sdk':
        answer, meta_ = ask_sdk(system, user, schema=CHECK_SCHEMA)
    else:
        answer, meta_ = ask_cli(system, user, schema=CHECK_SCHEMA)
    rec = dict(model=MODEL, check_version=CHECK_VERSION, repo_id=repo_id, fact_id=fact['id'],
               input_sha256=sha, request_user=user, answer=answer, **meta_)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec, indent=1, ensure_ascii=False))
    return rec


def prose_check(rec, body):
    """Verified summary of the check; quotes must be in the card body or the agreement is void."""
    a = rec['answer']
    if a.get('status') == 'error':
        return dict(status='llm_error')
    if a['status'] == 'not_stated' or a['agreement'] == 'not_stated':
        return dict(status='not_stated', agreement='not_stated')
    quotes = [q for q in a.get('quotes', []) if q.strip()]
    checks = [quote_in_source(q, body) for q in quotes]
    ok = bool(quotes) and all(checks)
    return dict(status='prose' if ok else 'rejected_quote', value=a['value'], quotes=quotes,
                agreement=a['agreement'] if ok else 'unverified', section=a['section'],
                failed_quotes=[q for q, c in zip(quotes, checks) if not c] or None,
                check_version=rec['check_version'])


# ---------------------------------------------------------------- driver

def load_ctx(m):
    d = RAW / m['key']
    api = json.loads((d / 'api.json').read_text())
    return dict(key=m['key'], api=api, card=api.get('cardData') or {},
                config=json.loads((d / 'config.json').read_text()) if (d / 'config.json').exists() else {},
                readme=(d / 'README.md').read_text() if (d / 'README.md').exists() else None,
                src=json.loads((d / 'source.json').read_text()))


def extract_model(m, facts, pass1_only=False, workers=8):
    ctx = load_ctx(m)
    records, todo = {}, []
    for f in facts:
        r = pass1(f, ctx)
        if r:
            records[f['id']] = r
        elif f['hf'].get('prose', True) is False or not ctx['readme']:
            records[f['id']] = dict(status='not_stated', value=None, quote=None, section=None,
                                    source_type=None, source_url=None, pass_=1,
                                    note=None if ctx['readme'] else 'README unavailable')
        else:
            todo.append(f)
    if not pass1_only:
        with ThreadPoolExecutor(workers) as ex:
            recs = list(ex.map(lambda f: ask(m['key'], m['repo_id'], ctx['readme'], f), todo))
        for f, rec in zip(todo, recs):
            records[f['id']] = pass2(f, ctx, rec)
        # metadata answered these: check the card text agrees (Molmo2 video, Phi context length)
        body = card_body(ctx['readme']) if ctx['readme'] else None
        checks = [f for f in facts if body and records[f['id']]['status'] == 'structured'
                  and f['hf'].get('prose', True) is not False]
        with ThreadPoolExecutor(workers) as ex:
            recs = list(ex.map(lambda f: ask_check(m['key'], m['repo_id'], body, f,
                                                   records[f['id']]['value']), checks))
        for f, rec in zip(checks, recs):
            records[f['id']]['prose_check'] = prose_check(rec, body)
    out = []
    for f in facts:
        r = records.get(f['id'])
        if r is None:  # pass1-only run: prose facts left pending
            r = dict(status='pending', value=None, quote=None, section=None, source_type=None,
                     source_url=None, pass_=None)
        r = {'model': m['key'], 'repo_id': m['repo_id'], 'fact_id': f['id'],
             'retrieved_at': ctx['src']['retrieved_at'], **r}
        r['pass'] = r.pop('pass_')
        out.append(r)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--models', help='comma-separated keys (default: all)')
    ap.add_argument('--pass1-only', action='store_true')
    args = ap.parse_args()
    facts = load_yaml(TARGETS / 'facts.yaml')['facts']
    models = load_yaml(ROOT / 'models.yaml')['models']
    if args.models:
        models = [m for m in models if m['key'] in args.models.split(',')]
    EXTRACTED.mkdir(parents=True, exist_ok=True)
    for m in models:
        recs = extract_model(m, facts, args.pass1_only)
        (EXTRACTED / f"{m['key']}.json").write_text(json.dumps(recs, indent=1, ensure_ascii=False))
        counts = {}
        for r in recs:
            counts[r['status']] = counts.get(r['status'], 0) + 1
        print(f"{m['key']:16} {counts}")


if __name__ == '__main__':
    main()

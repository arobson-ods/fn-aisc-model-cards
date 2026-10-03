"""Shared helpers: paths, cached HTTP, quote verification."""
import datetime as dt
import hashlib, json, os, re, unicodedata
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / 'data' / 'raw'
HTTP_CACHE = RAW / 'http'
EXTRACTED = ROOT / 'data' / 'extracted'
TARGETS = ROOT / 'targets'
SCHEMAS = TARGETS / 'schemas'
OUT = ROOT / 'out'

# Set OFFLINE=1 (tests do) to forbid network access: a cache miss raises instead of fetching.
OFFLINE = os.environ.get('OFFLINE') == '1'


def load_dotenv():
    """Read KEY=VALUE lines from ROOT/.env (git-ignored) into os.environ, without overriding."""
    path = ROOT / '.env'
    if path.exists():
        for line in path.read_text().splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class CacheMiss(RuntimeError):
    pass


def now_iso():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f)


def cached_get(url, *, binary=False, headers=None, refresh=False):
    """GET a URL, caching the response under data/raw/http/. Returns the cache record:
    {url, status, retrieved_at, headers, body} (body is text, or a path for binary)."""
    key = hashlib.sha256(url.encode()).hexdigest()[:24]
    meta = HTTP_CACHE / f'{key}.json'
    if meta.exists() and not refresh:
        return json.loads(meta.read_text())
    if OFFLINE:
        raise CacheMiss(url)
    HTTP_CACHE.mkdir(parents=True, exist_ok=True)
    r = httpx.get(url, headers=headers or {}, follow_redirects=True, timeout=60)
    rec = dict(url=url, status=r.status_code, retrieved_at=now_iso(),
               headers={k: v for k, v in r.headers.items()
                        if k.lower() in ('content-type', 'etag', 'last-modified', 'x-repo-commit')})
    if binary:
        blob = HTTP_CACHE / f'{key}.bin'
        blob.write_bytes(r.content)
        rec['body'] = str(blob.relative_to(ROOT))
    else:
        rec['body'] = r.text
    meta.write_text(json.dumps(rec, indent=1, ensure_ascii=False))
    return rec


_QUOTES = str.maketrans({'‘': "'", '’': "'", '“': '"', '”': '"', '–': '-', '—': '-', ' ': ' '})


def normalise_ws(s):
    """Normalise whitespace, unicode form and typographic quotes/dashes for quote matching."""
    s = unicodedata.normalize('NFKC', s).translate(_QUOTES)
    return re.sub(r'\s+', ' ', s).strip()


def _strip_md(s):
    return re.sub(r'[*_`|]+', '', s)


def quote_in_source(quote, source):
    """Return 'exact', 'normalised' or None. Normalised allows whitespace/typography and
    markdown emphasis/table-pipe differences, never changed words."""
    if not quote or not quote.strip():
        return None
    if quote in source:
        return 'exact'
    q, s = normalise_ws(quote), normalise_ws(source)
    if q in s:
        return 'normalised'
    if normalise_ws(_strip_md(q)) in normalise_ws(_strip_md(source)):
        return 'normalised'
    return None

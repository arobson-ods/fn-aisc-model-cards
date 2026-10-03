# Model cards vs model-description standards

A Field Work experiment on AI supply chains: we extract what 14 open-weight model cards on Hugging Face disclose into three model-description targets. For each fact that fails to reach a target, we classify the cause as schema, disclosure, audience or structure. See `CLAUDE.md` for the method and rules.

This is a probe of the standards and of disclosure practice. It is not a compliance assessment of any model.

**Disclaimer:** This was a 2-3 hour experiment with heavy reliance on Claude. Results should be treated as provisional. This was a learning exercise not a finished work of analysis. 

## Pinned versions

| Target | Version | Files (`targets/schemas/`, sha256 in `PINS.yaml`) | Retrieved |
|---|---|---|---|
| SPDX | 3.0.1 (AI and Dataset profiles) | `spdx-json-schema.json`, `spdx-context.jsonld`, `spdx-model.ttl` (OWL and SHACL) | 2026-09-30 |
| CycloneDX | 1.7.2 (`specVersion` 1.7) | `bom-1.7.schema.json` plus `spdx`, `jsf-0.82` and `cryptography-defs` sibling schemas | 2026-09-30 |
| EU GPAI Code of Practice | Transparency chapter, Model Documentation Form (July 2025) | `model_documentation_form.docx`, parsed into `targets/eu_form.yaml` | 2026-09-30 |

The EU form has **no official machine-readable schema**. `out/eu/` is our own YAML/CSV rendering of it: one entry per form item, keeping the AIO/NCA/DP audience flags.

## Layout

```
models.yaml            14 models: repo IDs, commit SHAs, retrieval dates, gating, base models
targets/facts.yaml     61 facts: HF sources, and SPDX / CycloneDX / EU form paths (field | escape_hatch | none)
targets/eu_form.yaml   45 EU form items with audience flags and precision (exact | range)
data/raw/              cached HTTP (http/), per-model api.json / README.md / config.json, _upstream/ chains, llm/
data/extracted/        per-model fact records with evidence
out/                   spdx/ cdx/ eu/, matrix_disclosure.csv, matrix_schema.csv, gaps.csv, lineage.csv,
                       placement.csv, metadata_vs_prose.csv, headline.json, spotcheck.csv,
                       autocheck.csv, spotcheck_mini.csv (human review), archive_v3/ (previous run)
```

## Commands

```
uv run python -m pipeline.fetch        # HF API + README + config.json, and base-model chains, all cached
uv run python -m pipeline.extract      # pass 1 (structured) + pass 2 (LLM, cached); --pass1-only to skip the LLM
uv run python -m pipeline.spotcheck    # writes out/spotcheck.csv for human review, then stops
uv run python -m pipeline.autocheck     # second-model check of the sample + 15-row human sample
uv run python -m pipeline.autocheck --score   # after a human fills out/spotcheck_mini.csv
uv run python -m pipeline.emit         # SPDX + CycloneDX (validated offline) + EU form fills
uv run python -m pipeline.report       # matrices, gaps, lineage, headline numbers
uv run pytest                          # offline; network access fails the tests
```

Set `OFFLINE=1` to rebuild from cache only; a cache miss is then an error. Two consecutive offline rebuilds produce identical output.

Pass 2 uses the Anthropic SDK when `ANTHROPIC_API_KEY` is set, in the environment or in a git-ignored `.env` file. Otherwise it runs Claude Code headless (`claude -p`, no tools, no settings, structured output) on the logged-in Claude subscription. The current cache was built that way. Set `LLM_BACKEND=sdk|cli` to force one or the other. Both backends use `claude-sonnet-5-5` with prompt version `v4` (and `m1` for the metadata-vs-prose check), and each cached response records the backend, model and prompt version.

One-off helpers:
- `pipeline.pin_schemas` re-downloads the pinned files.
- `pipeline.parse_eu_form <docx>` re-parses the form.
- `pipeline.facts_check` checks `facts.yaml` against the form and the schemas.

## Notes on method

- **Evidence:**
  - Pass-1 values cite the API field path they came from. Each is tagged `card_metadata` (card YAML), `hub_api` (computed by the Hub, e.g. the parameter count from safetensors) or `repo_config` (`config.json`).
  - Pass-2 values carry a verbatim quote, which is checked against the cached README. A value whose quote doesn't match gets `rejected_quote` and is never repaired.
- **Gated repos:** without a token, `meta-llama/Llama-4-Scout-17B-16E-Instruct` returns its API metadata but a 401 for the raw README. The same card is rendered on the public model page, so we use that text (`readme_source: rendered_html` in `models.yaml`). No mirrors are used.
- **SPDX required properties:** where the card doesn't state them, Hub values stand in and the element's `comment` says so. Repo creation time stands in for `releaseTime`, and the HF account name for `suppliedBy`. The concluded licence is always NOASSERTION.
- **Validation:** SPDX documents are checked against the JSON schema and the SHACL shapes, using the pinned context. For an extra online check you can run `spdx3-validate`, which downloads the SPDX model.
- **Prior art (to cross-check during the human review of `facts.yaml`, not yet done):**
  - the OWASP AIBOM Generator's `src/models/field_registry.json` (Apache-2.0), for HF field aliases and CycloneDX paths;
  - Notre Dame CRANE's SPDX 3.0 `AIPackage` ↔ model card table, for README section hints.

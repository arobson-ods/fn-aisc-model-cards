# Model cards vs model-description standards

## What this project is

An experiment for a "Field Work" session on AI supply chains. The session asks:
*how well can AI supply chains be described with the standards and data that already exist,
and what would be needed to describe them properly — which organisations would have to share
what, with whom, in what form?*

We answer that for the **digital layer**: take the public model cards of 10–15 open-weight
models, extract what they disclose into three model-description targets, and measure what each
target can hold, what labs actually publish, and what only regulators get to see.

The three targets:

1. **SPDX 3.0 AI profile** (`AIPackage`, plus the Dataset profile) — an AI bill of materials.
2. **CycloneDX ML-BOM** (`modelCard` on a machine-learning-model component) — the other
   main AI bill-of-materials format.
3. **EU Model Documentation Form** — the template in the Transparency chapter of the EU
   General-Purpose AI Code of Practice (July 2025), used to meet AI Act Art. 53(1)(a)–(b).

This is a probe of the standards and of disclosure practice, not a compliance assessment of any
lab. Do not describe any model as compliant or non-compliant.

## The core analytical idea (keep this central)

Every fact that fails to reach a target is classified by **cause**:

- **Schema gap** — the target standard has no place for the fact.
- **Disclosure gap** — the standard has a place, but the lab doesn't publish the fact.
- **Audience gap** — the EU form asks for the fact but routes it to the AI Office, national
  authorities or downstream providers rather than the public. Not missing by accident:
  withheld by design. The form marks every item with crosses for AIO (AI Office, on request),
  NCA (national authorities, via the AI Office) and DP (downstream providers, proactively).
  **No item is addressed to the public.** Several items are split: a precise value for the
  AI Office and only a range for others (e.g. parameter count, training compute, training time).
- **Structure gap** — the fact is published, but only as prose or in a PDF, not in the card's
  machine-readable metadata.

**Control model:** include one maximally open model (AI2's OLMo family publishes weights,
data, code and logs). Anything a target still can't hold for OLMo is a schema gap, not a
disclosure gap. This mirrors the owner-issued control record in the sister project
(Epoch → UNTP).

**Supply chain angle:** the digital layer is a chain — training data → base model →
fine-tune → deployment. Test lineage explicitly: include 2–3 fine-tunes whose card declares a
`base_model`, and check whether each target can express "derived from", "trained on" and
"evaluated on" relationships (SPDX 3 relationship types; CycloneDX pedigree / dependencies).
Lineage is expected to be the weakest area and is the most interesting finding.

## Rules

- **Every extracted value carries evidence**: the source URL and a verbatim quote from it.
  Code checks that the quote appears in the cached source text; values whose quote doesn't
  match are rejected, not repaired.
- **The LLM extracts; it never fills gaps.** "Not stated" is a valid and important answer.
  Never infer parameter counts, training compute, dataset sizes or licences from general
  knowledge.
- **Human spot-check** a random sample (at least 20% of extracted values, stratified by model)
  and report extraction accuracy. This number goes on the slide.
- **No compliance judgments.** Many open-source models are exempt from parts of the AI Act
  transparency obligations unless they pose systemic risk; exemption status is out of scope.
  We compare disclosures to the form as a yardstick, nothing more.
- **Pin versions** of SPDX, CycloneDX and the EU form; write them in `README.md`.
- **Reproducible**: one command rebuilds everything from cached sources. Cache all HTTP and LLM
  responses; tests never hit the network.
- Record the retrieval date for every model card — cards change.

## Sources

| Source | Use | Notes |
|---|---|---|
| Hugging Face Hub API: `https://huggingface.co/api/models/{repo_id}` | Card metadata (YAML front matter as `cardData`, tags, licence, `base_model`) | Also fetch the raw README: `https://huggingface.co/{repo_id}/raw/main/README.md`. Some repos are gated; use an `HF_TOKEN` env var if needed and note which were gated. |
| Linked technical reports (arXiv / lab PDFs) | Optional secondary source | Only for the control model and only if time allows. Tag every value with `source_type: card | report`. |
| SPDX 3.0.1 spec: `https://spdx.github.io/spdx-spec/v3.0.1/` | AI and Dataset profiles, relationship types, JSON-LD serialisation | `AIPackage` properties include autonomyType, domain, energyConsumption, hyperparameter, informationAboutApplication, informationAboutTraining, limitation, metric, modelDataPreprocessing, modelExplainability, safetyRiskAssessment, standardCompliance, typeOfModel, useSensitivePersonalInformation. Profile conformance requires declared and concluded licence relationships. |
| CycloneDX spec (1.6 or later) | ML-BOM `modelCard` | Use the official JSON schema; `cyclonedx-python-lib` can help. |
| EU GPAI Code of Practice — Transparency chapter and Model Documentation Form | Third target | DOCX: `https://ec.europa.eu/newsroom/dae/redirection/document/118118`. Already parsed into `targets/eu_form.yaml` (45 items with audience flags) by `pipeline/parse_eu_form.py`. Items flagged `needs_review` must be checked against the form. |
| Foundation Model Transparency Index 2025 (Stanford CRFM) | Cross-check | If its indicator data is downloadable, compare our disclosure findings for overlapping models. Differences are findings, not errors. |

**Prior art — review before building, reuse where sensible:**
- OWASP GenAI Security Project's **AIBOM Generator** (Hugging Face Space) converts HF model
  cards to CycloneDX AI-BOMs and publishes a field mapping including SPDX alignment.
- Notre Dame CRANE lab's `sbom-analysis` site maps SPDX 3.0 `AIPackage` fields to HF model
  card fields.

Our novelty is the three-way comparison including the EU form, the gap-cause classification,
the control model and the lineage test — not HF → CycloneDX conversion itself.

## Model selection (10–15)

Take the latest release in each family at the time of running; record exact repo IDs and
retrieval dates in `models.yaml`. Aim for a spread of labs, sizes and openness:

- **Control:** OLMo (AI2).
- **Major open-weight families:** Llama (Meta), Gemma (Google), Mistral, Qwen (Alibaba),
  DeepSeek, Phi (Microsoft), a Hugging Face SmolLM, Falcon (TII), IBM Granite.
- **Lineage cases:** 2–3 popular fine-tunes or quantisations whose card declares `base_model`.
- **Stretch:** 2–3 closed frontier models from their published system/model cards (PDF). These
  have no HF metadata, so they only enter the EU-form comparison.

## Method

### 1. Build the canonical fact list (`targets/facts.yaml`)

The comparison frame. One entry per fact, ~40–60 facts, drawn from the union of the EU form,
SPDX AI/Dataset profiles and CycloneDX `modelCard`. Group by: identity & provider, licensing,
architecture & size, training data, training process & compute, energy, intended use &
limitations, evaluation, safety, lineage/dependencies, distribution.

Each fact records: `id`, `description`, `group`, and for each target the field path (or `null`
= schema gap), plus for the EU form the intended audience(s).

### 2. Extract (`pipeline/extract.py`)

- **Pass 1, deterministic:** parse YAML front matter and HF API fields (licence, base_model,
  datasets, language, tags, model-index eval results).
- **Pass 2, LLM:** for each fact not found in pass 1, ask the model to return
  `{value | "not stated", quote, section}` from the README text only. Validate quotes by exact
  or whitespace-normalised substring match.
- Output: `data/extracted/{model}.json` — one record per model × fact with `status`
  (`structured` / `prose` / `not_stated`), value, quote, source.

### 3. Emit targets (`pipeline/emit_spdx.py`, `emit_cdx.py`, `emit_eu.py`)

- SPDX 3 JSON-LD document per model; validate against the official schema/SHACL shapes.
- CycloneDX JSON per model; validate against the official schema.
- EU form: a filled YAML/CSV per model (no official machine-readable schema exists; say so).
- Log every fact that couldn't be placed, with its gap cause.

### 4. Classify and report (`pipeline/report.py`)

- **Matrix A — disclosure:** model × fact → structured / prose / not stated.
- **Matrix B — schema coverage:** fact × target → field / no field.
- **Gap table:** every (model, fact, target) failure with its cause.
- **Lineage table:** for each lineage case, which upstream links are declared and which targets
  can express them.
- Headline numbers: share of EU-form facts publicly disclosed (median across models); share
  of disclosed facts that are machine-readable; schema gaps remaining for the control model;
  extraction accuracy from the spot-check.

## Deliverables

```
models.yaml               selected models, repo IDs, retrieval dates, gated?
targets/                  facts.yaml, eu_form.yaml, pinned schemas
data/raw/                 cached API responses, READMEs, LLM responses
data/extracted/           per-model fact records with evidence
out/spdx/  out/cdx/  out/eu/   emitted documents (all validating where a schema exists)
out/matrix_disclosure.csv  out/matrix_schema.csv  out/gaps.csv  out/lineage.csv
out/spotcheck.csv         human review sample and accuracy
docs/findings.md          one page: gaps by cause, lineage, what would be needed
```

Python 3.11+, `uv`, `httpx`, `pyyaml`, `pandas`, `jsonschema`, `cyclonedx-python-lib`,
`pytest`. For LLM calls use the Anthropic SDK with an `ANTHROPIC_API_KEY` env var; cache
responses keyed by (model, fact, prompt version).

Target commands:

```
uv run python -m pipeline.fetch
uv run python -m pipeline.extract
uv run python -m pipeline.spotcheck    # writes sample for human review; stops
uv run python -m pipeline.emit
uv run python -m pipeline.report
uv run pytest
```

## Plan

**Day 1 AM (≈3.5h)**
- Review the prior art (30 min); decide what to reuse.
- Obtain and pin the EU form, SPDX 3.0.1 and CycloneDX versions.
- Spot-check `targets/eu_form.yaml` against the form (≈20 min): every `needs_review` item plus
  ~10 random items' audience flags. Re-run `pipeline/parse_eu_form.py` if the form has been updated.
- Build `facts.yaml` with field paths for all three targets. AI assistance helps most here;
  a human checks every mapping.

**Day 1 PM (≈3.5h)**
- Fix `models.yaml`; fetch and cache cards and metadata.
- Pass 1 extraction; then pass 2 on 2–3 models, tune the prompt, then run on all.
- Generate the spot-check sample.

**Day 2 AM (≈3.5h)**
- Human spot-check (≈1h); fix systematic extraction errors, re-run.
- Emit SPDX and CycloneDX documents; get them validating. Emit EU form fills.

**Day 2 PM (≈3.5h)**
- Classify gaps; run the control-model comparison; build the lineage table.
- Report, `findings.md`, one presentation slide.

**Cut-down version for a 2-hour session:** hand-build `facts.yaml` for ~20 facts, extract for
3 models (control + two others) manually with AI help, fill Matrix A and B by hand.

## Definition of done

- Every model has extracted fact records, each disclosed value with a verified quote.
- SPDX and CycloneDX documents validate for every model.
- Every fact appears in Matrix B with a field path or an explicit schema gap for each target.
- Every failure in `gaps.csv` has one of the four causes.
- Spot-check completed and accuracy reported.
- Control-model and lineage results written up in `findings.md`.
- The pipeline rebuilds from cache with the commands above.

## Expected sceptical objections (address in findings)

- *"Model cards aren't meant to be complete regulatory documents."* True — that's why the
  audience gap exists. The finding is the size and shape of the public/regulator divide.
- *"LLM extraction is unreliable."* Hence quote verification and the spot-check accuracy.
- *"Open models are exempt from much of this."* Out of scope; we use the form as a yardstick,
  not a test of compliance.
- *"This is product documentation, not a supply chain."* The lineage test is the answer: can any
  standard carry the chain from training data to deployed model?

## Stretch goals (only after done)

- Add closed frontier models from their system cards (EU-form comparison only).
- Cross-check disclosure findings against FMTI 2025 indicators.
- Build a lineage graph across all models from HF `base_model` declarations and render it.
- Link training datasets named in cards to Hugging Face dataset cards and test the SPDX
  Dataset profile.

## Context

- Sister project: Epoch AI data centres → UNTP Digital Facility Records (physical/control
  layers). Together the two cover all three layers in the session brief; keep the gap-cause
  approach parallel so results are comparable.

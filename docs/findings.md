# Findings: how well do model-description standards carry what model cards say?

*14 Hugging Face model cards retrieved 2026-09-30, mapped onto three targets: SPDX 3.0.1 (AI and Dataset profiles), CycloneDX 1.7.2 (ML-BOM) and the EU GPAI Code of Practice Model Documentation Form (July 2025). We use 61 canonical facts. This is a probe of the standards and of disclosure practice, not a compliance assessment. Numbers come from `out/headline.json` and `out/gaps.csv`.*

## What the 61 facts are

We built a list of 61 facts by combining what the three formats ask for: the EU Model Documentation Form, SPDX 3.0.1 and CycloneDX 1.7. We added a few things model cards commonly publish but no format has a field for, such as knowledge cutoff and languages. This is a common frame for comparing the formats, not a proposal for what an AI bill of materials should contain.

- **It is anchored to existing standards, not to need.** Things none of the formats asks for, and cards rarely mention, are not in the list. Examples: the tokenizer, per-dataset licences and consent, safety filters shipped with a deployment, file-level hashes, and who hosts inference.
- **Every fact counts equally.** Parameter count weighs the same as explainability, so percentages are shares of this list, not of what matters most.
- **The list leans towards the EU form.** 45 of the 61 facts map onto the form's 45 items, though not one to one (some facts fill an exact and a range item, and some items draw on two facts), and 21 facts are asked for only by the form.

The EU-form figures below count the form's 45 items. Everything else counts the 61 facts.

## Headline numbers

- **58%** of EU form items can be answered from the public card (median across models; range 18 to 37 of 45 items). The figure is generous: Hub-supplied data such as the commit hash and repo URL count as answers.
- **44%** of disclosed facts are machine-readable (median). Only **17%** come from the lab's own card metadata. The rest are computed by Hugging Face (parameter count, commit) or read from `config.json`. Everything else is prose.
- **Every SPDX and CycloneDX document validates**, but the fields they fill are thin. Of the disclosed facts, 202 (SPDX) and 196 (CycloneDX) could only go into free-form escape hatches or nowhere.
- **Extraction accuracy: 88.7%** on an automated second-model check of 146 sampled values (prompt v4). Claude Opus 5.5 checked Claude Sonnet 5.5's extractions: 115 correct, 29 partial, 2 wrong. Both "wrong" rows are cases where card metadata contradicts the card's own text, not extraction slips (see Lineage and point 2 of "What would be needed"). A human reviewed 15 of the rows (10 the checker had flagged) and agreed with the checker on 10. In all 5 disagreements the checker said `partial` where the human said `y`, never the reverse, so the automated figure is if anything conservative. These figures were measured before two later fixes (keeping link URLs in Llama's card text, which re-extracted Llama's prose facts; and a metadata-vs-prose check). This is not a full human spot-check. On the previous run (prompt v3) the check scored 90.8%, and a human agreed with it on all 15 rows reviewed. In addition, code checks every quote (857 quotes behind 268 prose values): 1 value was rejected because a quoted table row didn't match the card, and none was repaired.

## Gaps by cause

| Target | Schema | Disclosure | Audience | Structure |
|---|---|---|---|---|
| SPDX 3.0.1 | 406 (93% escape hatch) | 173 | n/a | 164 |
| CycloneDX 1.7.2 | 462 (97% escape hatch) | 111 | n/a | 146 |
| EU form | 224 | 104 | 167 | n/a |

Each cell counts (model × fact) failures; there are 14 models × 61 facts per target.

- **Schema gaps dominate.** SPDX defines no field for 29 of the 61 facts and CycloneDX none for 33:
  - neither has a field for parameter count, knowledge cutoff, training compute, training time or hardware, required hardware, or languages;
  - SPDX has none for modalities;
  - CycloneDX has none for context length or hyperparameters.

  Almost all of these can still be pushed into generic bags (SPDX `comment`, CycloneDX `properties`). That keeps the BOM valid, but no consumer can rely on the result.
- **Machine-readable metadata and the card's own text don't always agree.** Of the 156 facts answered from metadata, we had Claude read the card text for the same fact, with verified quotes. The text agrees in 48 and adds detail in 43 (e.g. Molmo2's text adds video input). It is silent in 61, and conflicts in 4: Phi's context length (32,768 in `config.json`, 16,384 in the card) and required software; Gemma's parameter count (31.27B computed by Hugging Face from the weights, "30.7B" in the card); and TwIL-LM3's derivation type. None of the conflicts involve the lab's own card YAML. They all come from values the platform computes or infers, or from repository config files (`out/metadata_vs_prose.csv`). The BOMs use the metadata value; the EU form fill shows both where they differ.
- **Hugging Face's own vocabulary has gaps too.** Molmo2's `pipeline_tag` is `image-text-to-text` because there is no tag for "image-and-video-text-to-text". So its machine-readable metadata omits video input, which the card's text states.
- **Some fields exist but can't take what cards publish.** CycloneDX `energyConsumptions` requires an energy provider, an energy source and the energy delivered, which no card gives, so Llama's disclosed emissions have nowhere valid to go. Enumerated fields (CycloneDX `approach.type`; SPDX `safetyRiskAssessment`, `autonomyType`, `hasSensitivePersonalInformation`) can't take prose without a human classifying it.
- **The EU form has no items for evaluation, safety testing, limitations or a list of training datasets.** Evaluation and safety sit in the Safety & Security chapter, which only applies to models with systemic risk, and the dataset list sits in the separate public training-data summary. So the facts cards publish most readily (benchmarks, limitations) are the ones the form doesn't ask for.
- **Audience gaps are where the public/regulator divide shows.**
  - Where the form addresses downstream providers, 72% of its items can be answered publicly. For items addressed only to regulators, 41% can.
  - By section: distribution and licences 99%, model properties 86%, computational resources 10%, energy 2%.
  - Training compute (FLOPs), inference compute and training energy appear in **no** card. Llama gives GPU hours and emissions, but no energy figure. These are exactly the items the form routes to the AI Office, or gives other audiences only as a range.
- **Structure gaps:** facts published only in prose where the BOM has a field (about 145 to 165 per format). The usual cases are training method, intended uses, limitations and data curation.

## Control model (OLMo)

- **OLMo is the most open model, but its card is not the most complete.** Its card states 31 facts, against 49 for Llama, 43 for Phi and 40 for Gemma. Its openness lives in linked data, code and reports, and in `datasets:` metadata all the way up its chain.
- Even for OLMo, facts it does disclose have no field:
  - in SPDX: parameter count, modalities, task, knowledge cutoff, languages, data scope, acceptable use policy, derivation type;
  - in CycloneDX: parameter count, context length, knowledge cutoff, languages, derivation type.

  These are pure schema gaps, and more disclosure from labs would not close them.

## Lineage

- **Every target can name a base model:** SPDX `descendantOf`, CycloneDX `pedigree.ancestors` and the EU form's model-dependencies item. **None can say how a model was derived** (fine-tune, quantisation, merge or adapter). Hugging Face records this in tags, but SPDX and CycloneDX can only hold it as a comment.
- **Training-data links break early in the chain.** We followed each card's declared `base_model` chain (up to 4 hops).
  - Only the OLMo chains declare training datasets at every step down to the base.
  - The Llama, Gemma, Phi, SmolLM, Falcon, Granite and TwIL chains end at a base model whose card metadata declares no dataset. "Declares" means machine-readable `datasets:` metadata; some cards point to data in prose. For example, SmolLM3 links a collection of its pretraining datasets and embeds its EU public training-data summary, but as an interactive iframe that no standard or extractor can read.
  - Molmo2 declares its own fine-tuning data, but its language backbone (Qwen3-8B) declares none.
- **The machine-readable derivation type can be a platform guess, and wrong.** TwIL-LM3's card declares no `base_model_relation`. Hugging Face inferred one and tagged it as an *adapter* on SmolLM3, probably from its `lora` tag. But the repo ships full merged weights (`model.safetensors`, no adapter config), and the card says it is a LoRA fine-tune merged into the base. So the only machine-readable record of how this model was derived is the platform's inference, and it is wrong.
- **Gated upstream:** Llama's metadata is public but its README needs a login. We used the rendered public page instead.
- **Evaluation data:** SPDX has `testedOn`. CycloneDX's `modelParameters.datasets` mixes training and evaluation data without saying which is which. The EU form has nothing.

## What would be needed

1. **Standards (schema gaps):** first-class fields for parameter count, context and output limits, modalities, knowledge cutoff, and training compute, time and hardware, all with units. An explicit derivation type on lineage relationships. CycloneDX: allow an energy or emissions figure without energy-provider details.
2. **Hugging Face and labs (structure gaps):** model-card metadata keys for the facts most often published only as prose: training tokens, cutoff, compute and energy, training stages, data provenance categories. Metadata should also agree with the prose. Phi's `config.json` gives a 32,768-token context; its card says 16,384. TwIL-LM3 is tagged (by Hugging Face's inference) as an adapter but ships merged weights. Gemma's computed parameter count (31.27B) differs from its card (30.7B). Any metadata that a platform derives automatically should be checked against what the lab states.
3. **Labs (disclosure gaps):** a `datasets:` entry at every link of the chain, especially on base models.
4. **Regulators (audience gaps):** decide which Model Documentation Form items, or the range versions of them, could be public. Today no item is addressed to the public, so compute, energy and data-curation facts reach only the AI Office and downstream providers. The form also has no official machine-readable schema; publishing one would let it be emitted and checked like SPDX and CycloneDX.

## Expected objections

- *"Model cards aren't regulatory documents."* Agreed. That is why the audience gap is counted separately, and its size and shape (compute and energy almost never public) are the finding.
- *"LLM extraction is unreliable."* Every value carries verbatim quotes that code checks against the cached card. An independent model check scored 88.7%. A human reviewing 15 rows agreed with it on 10, and was more lenient in every disagreement (on the previous run: 90.8%, 15 of 15 agreement). The limitation is that there was no full human spot-check.
- *"Open models are exempt."* Out of scope. We use the form as a yardstick, not a test.
- *"This is product documentation, not a supply chain."* The lineage test is the answer: the standards can name the parent but not how the child was made, and the chain to training data breaks at the first closed base model.

## Caveats

- 14 cards, one day's snapshot.
- Some mappings are judgment calls (`targets/facts.yaml`, where 10 BOM mappings are marked `fit: coarse`), and the mapping has not had a full human review.
- The EU-item share counts an item as answered if any mapped fact is disclosed, and Hub-supplied values count.
- Extraction used Claude Sonnet 5.5 through Claude Code in headless mode (prompt v4). Responses are cached, so the pipeline rebuilds offline.

# skillpingjia 📊

> An evidence-based quality scorer for [Agent Skills](https://agentskills.io). Hard gates + a 7-dimension 100-point rubric + static collector + regression evals — with a strict rule: **every score must cite evidence, no vibes-based grading.**

`skillpingjia` (评价 = "price-tag review") evaluates any Agent Skill folder (`SKILL.md` + optional `scripts/`, `references/`, `evals/`) and outputs a report that tells you **what to fix first**, not just a number.

The SKILL.md instructions and scoring rubrics are written in Chinese (with English trigger phrases); this README gives the English overview.

## Why

Most skill "reviews" are a model eyeballing a markdown file and shrugging. skillpingjia enforces three things industry reviews keep skipping:

1. **Hard gates with veto power** — missing frontmatter, a 500+ line SKILL.md, or a broken separation of duties fails the skill outright, regardless of how nice the prose reads.
2. **Evidence or it didn't happen** — every sub-score must cite a line number, section name, file existence, or a real dry-run result. Any perfect score must explain "why not 0.5" or it auto-drops to 0.5.
3. **Real-incident regression tests** — the eval suite includes fixtures extracted from actual production skill failures (IR type drift between modules, silent-failure fallback branches). If the scorer can't catch them, the scorer itself is broken.

## Quick start

Requires Python ≥ 3.9. **Zero third-party dependencies** (stdlib only; `pyyaml` optional).

```bash
# 1. Collect machine-readable evidence from a target skill
python3 scripts/score.py /path/to/some-skill > bundle.json

# 2. (recommended) Trimmed output for daily reviews
python3 scripts/score.py /path/to/some-skill --summary > bundle.json

# 3. Run the scorer's own regression suite (7 cases)
python3 evals/runner.py
```

Then hand `bundle.json` to any LLM-as-judge together with the rubric in `SKILL.md` (section "七维评分细则") and ask for the report using the template in "输出报告模板". The judge grades; `score.py` never auto-decides.

## Scoring model

**Layer 1 — hard gates (one-vote veto):**

| Gate | Rule |
|---|---|
| H1 | YAML frontmatter with `name` + `description` |
| H2 | SKILL.md under 500 lines |
| H3 | description ≤ 1024 chars |
| H4 | Separation of duties (model = brain / scripts = hands / references = textbook) not severely violated |

**Layer 2 — seven dimensions (100 pts, sub-items graded 0 / 0.5 / 1 with cited evidence):**

Trigger design 20 · Process discipline 15 · Structural soundness 20 · Output contract 15 · Guardrails 10 · Config boundary 5 · Evaluation closure 15

**Key design stance: clues ≠ assertions.** `score.py` collects ~20 evidence families (executable dry-runs, IR closure gaps, silent-failure patterns, fallback blind spots, package-engineering artifacts…) but only the judge decides. Absent fancy artifacts (contracts, signatures, disclosure cards) never cost points — big-company packaging standards must not crush a personal skill.

## What's in the box

```
SKILL.md                      # judge instructions + rubric (zh)
scripts/score.py              # static evidence collector (~1800 lines, stdlib only)
scripts/llm_score.py          # pure-function score aggregation (LLM call injected by caller)
scripts/regression.py         # baseline deviation checker
evals/runner.py               # 7-case regression suite (pytest-style, no deps)
evals/cases/                  # fixtures incl. real-incident regression cases
references/scoring_rubrics.md # 0/0.5/1 anchors per sub-item (anti judge-drift)
references/playbook_snapshot.md # theory base, bundled so the skill is self-contained
examples/score_evals.md       # self-test recipes
CHANGELOG.md                  # full evolution history w/ trigger reasons
```

## Philosophy

- **Scores guide priorities, they don't punish.** A 40/100 with a precise fix list beats a vague 90.
- **The scorer eats its own dogfood**: skillpingjia scores itself in CI (`evals/cases/normal` targets itself).
- **Everything learned from incidents goes into the rubric** — see CHANGELOG; each version lists the real failure that triggered it.

## License

Apache-2.0. See `LICENSE`.

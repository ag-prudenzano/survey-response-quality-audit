# Survey Response Quality Audit

## Overview

This simulated case study audits an online survey dataset for common response-quality problems. The analysis uses transparent, reproducible Python rules to identify incomplete responses, unusually fast completions, straight-lining, failed attention checks, invalid values, logical inconsistencies, duplicate-like submissions, and low-quality open-ended text.

The raw dataset contains **1,250 responses**, including **1,200 completed responses** and **50 partial responses**.

## Approach

The audit applies eight respondent-level quality checks:

1. **Partial responses** — responses not marked complete or with progress below 100%.
2. **Speeding** — completed surveys below one-third of the median completed survey duration.
3. **Straight-lining** — the same answer across all eight items in the main 1–7 rating grid.
4. **Attention-check failure** — a response other than the instructed value of 3.
5. **Invalid values** — ages, NPS scores, or 1–7 ratings outside their permitted ranges.
6. **Logical inconsistencies** — contradictions between eligibility, recency, routing, and related answers.
7. **Duplicate-like submissions** — repeated browser fingerprints combined with identical substantive answer patterns.
8. **Low-quality open text** — blank, nonsensical, extremely short, numeric-only, or repetitive responses.

The median duration among completed responses was **532.0 seconds**. The resulting speeder threshold was **177.3 seconds**.

## Results

**272 responses (21.8%)** received at least one QC flag. Of these, **177** were recommended for manual review and **95** were recommended for exclusion under the pre-specified decision rules.

| QC check | Responses flagged | Share of all responses |
|---|---:|---:|
| Partial | 50 | 4.0% |
| Speeder | 55 | 4.4% |
| Straightliner | 53 | 4.2% |
| Attention Fail | 44 | 3.5% |
| Invalid Value | 7 | 0.6% |
| Logic Error | 36 | 2.9% |
| Duplicate Like | 18 | 1.4% |
| Low Quality Open Text | 32 | 2.6% |

A single behavioural warning is not treated as sufficient evidence for automatic exclusion. Partial responses, invalid values, and duplicate-like submissions are treated as hard failures; otherwise, at least two behavioural indicators are required for an exclusion recommendation.

## Figures

### Completion duration

![Survey completion duration](figures/completion_duration_distribution.png)

The dashed line marks the data-derived speeder threshold used in the audit.

### Quality flags

![Survey quality flags](figures/quality_flag_counts.png)

This figure compares the number of responses identified by each QC rule.

## Ground-truth evaluation

The simulation ground truth was loaded only after the QC rules had been applied. It was not used to construct or tune the rules.

| Metric | Result |
|---|---:|
| True positives | 260 |
| False positives | 12 |
| False negatives | 0 |
| True negatives | 978 |
| Precision | 0.956 |
| Recall | 1.000 |
| Specificity | 0.988 |
| Accuracy | 0.990 |

These metrics show how closely the transparent audit rules recover the deliberately injected quality problems in the simulated data. False positives are possible because some legitimate responses can naturally look suspicious, so individual behavioural signals should not automatically be treated as proof of poor quality.

## Outputs

Running `python analysis.py` creates or replaces the following files:

- `report.md` — this report.
- `outputs/quality_flags.csv` — respondent-level QC indicators and recommendations.
- `outputs/quality_summary.csv` — summary counts and thresholds.
- `outputs/ground_truth_evaluation.csv` — validation metrics when the simulation ground-truth file is available.
- `figures/completion_duration_distribution.png` — completion-time distribution.
- `figures/quality_flag_counts.png` — counts for each QC flag.

## Reproducibility

The analysis is run from the repository root with:

```bash
pip install -r requirements.txt
python analysis.py
```

Before the analysis starts, the script fetches the remote repository and checks whether the local Codespace is behind its remote branch. If it is behind, the script stops without replacing any analysis outputs and asks you to run `git pull --ff-only` first.

`report.md` is deliberately overwritten on every successful run so the repository contains one current report rather than a series of duplicate report files.

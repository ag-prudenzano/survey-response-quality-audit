# Survey Response Quality Audit

## Study context

This simulated case study is set within a hypothetical UK online survey about restaurant-delivery usage and experience. The target population is adults aged **18–74** who ordered restaurant delivery within the previous **3 months**, with simulated fieldwork running from **6–20 July 2026**.

The dataset contains **1,250 captured responses**, including **1,200 completed responses** and **50 partial responses**. Fictional delivery-service names are used only to make the scenario realistic; the purpose of the case study is to assess survey response quality rather than draw conclusions about the restaurant-delivery market.

## Audit objective

The objective is to identify responses that may not be sufficiently reliable for analysis using transparent, reproducible rules based on completion status, paradata, response patterns, routing consistency, duplicate-like metadata and open-text quality.

Each respondent receives individual QC flags, followed by a recommendation for manual review or exclusion.

## Quality checks

The audit applies eight respondent-level quality checks:

1. **Partial responses** — surveys not marked complete or with progress below 100%.
2. **Speeding** — completed surveys below one-third of the median completed survey duration.
3. **Straight-lining** — the same response across all eight items in the main 1–7 rating grid.
4. **Attention-check failure** — respondents who do not select the instructed answer on the embedded attention check.
5. **Invalid values** — age, NPS, or 1–7 rating variables outside their permitted ranges.
6. **Logical inconsistencies** — contradictions across eligibility, recency, routing, support-contact, and related survey answers.
7. **Duplicate-like submissions** — repeated browser fingerprints combined with identical substantive answer patterns.
8. **Low-quality open text** — blank, nonsensical, extremely short, numeric-only, or repetitive open-ended responses.

The median duration among completed responses was **532.0 seconds**. The resulting speeder threshold was **177.3 seconds**.

## Findings

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

## Decision logic

A single behavioural warning is not treated as sufficient evidence for automatic exclusion. Partial responses, invalid values, and duplicate-like submissions are treated as hard failures; otherwise, at least two behavioural indicators are required for an exclusion recommendation.

This keeps the decision rule auditable and avoids treating a single suspicious pattern as definitive evidence of poor response quality.

## Figures

### Completion duration

![Survey completion duration](figures/completion_duration_distribution.png)

The dashed line marks the data-derived speeder threshold used in the audit.

### Quality flags

![Survey quality flags](figures/quality_flag_counts.png)

This figure compares the number of responses identified by each QC rule.

## Project files

Running `python analysis.py` creates or replaces the following files:

- [`report.md`](report.md) — this report.
- [`outputs/quality_flags.csv`](outputs/quality_flags.csv) — respondent-level QC indicators and recommendations.
- [`outputs/quality_summary.csv`](outputs/quality_summary.csv) — summary counts and thresholds.
- [`figures/completion_duration_distribution.png`](figures/completion_duration_distribution.png) — completion-time distribution.
- [`figures/quality_flag_counts.png`](figures/quality_flag_counts.png) — counts for each QC flag.

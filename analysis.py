from pathlib import Path
import re
import subprocess

try:
    import numpy as np
    import pandas as pd
    import matplotlib.pyplot as plt
except ImportError as exc:
    raise SystemExit(
        "Missing Python packages. Install pandas, numpy and matplotlib, then run "
        "the script again. Example: pip install -r requirements.txt"
    ) from exc


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "outputs"
FIGURE_DIR = ROOT / "figures"
REPORT_FILE = ROOT / "report.md"
RAW_FILE = DATA_DIR / "survey_response_quality_audit_raw.csv"

GRID_COLUMNS = [
    "q7_delivery_speed",
    "q7_order_accuracy",
    "q7_food_quality",
    "q7_value_for_money",
    "q7_app_ease",
    "q7_service_selection",
    "q7_customer_support",
    "q7_promotions",
]

RATING_1_TO_7_COLUMNS = [
    "q4_overall_satisfaction",
    "q5_likelihood_reorder",
    *GRID_COLUMNS,
    "q8_attention_check",
    "q9_delivery_fee_reasonableness",
    "q14_support_resolution",
]

SUBSTANTIVE_DUPLICATE_COLUMNS = [
    "age",
    "age_band",
    "gender",
    "region",
    "urbanicity",
    "employment_status",
    "household_income",
    "children_u18",
    "s1_ordered_delivery_3m",
    "q1_orders_past_30d",
    "q2_last_order",
    "q3_primary_service",
    "q4_overall_satisfaction",
    "q5_likelihood_reorder",
    "q6_nps",
    *GRID_COLUMNS,
    "q8_attention_check",
    "q9_delivery_fee_reasonableness",
    "q10_last_order_spend_gbp",
    "q11_problem_last_order",
    "q12_problem_type",
    "q13_contacted_support",
    "q14_support_resolution",
    "q15_subscription_member",
    "q16_open_end",
]

LOW_QUALITY_OPEN_TEXT = {
    "n/a",
    "na",
    "none",
    "none none none",
    "idk",
    "test",
    "x",
    "...",
    "blah blah",
    "qwerty",
    "asdfgh",
}

FIGURE_BACKGROUND = "#000000"
FIGURE_TEXT = "#f6f6f6"
FIGURE_MUTED = "#a3a3a3"
FIGURE_LINE = "#393939"
FIGURE_BAR = "#686868"
FIGURE_ACCENT = "#64d2ff"


def run_git(*args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise SystemExit(
            "Git is not available in this environment. Run the analysis from a "
            "GitHub Codespace or another Git checkout."
        ) from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "Unknown Git error").strip()
        raise SystemExit(f"Git command failed: git {' '.join(args)}\n{detail}") from exc


def check_repository_up_to_date() -> None:
    inside_work_tree = run_git("rev-parse", "--is-inside-work-tree").stdout.strip()
    if inside_work_tree.lower() != "true":
        raise SystemExit("This script must be run from inside a Git repository.")

    print("Checking repository status against GitHub...")
    run_git("fetch", "origin")

    branch = run_git("branch", "--show-current").stdout.strip()
    remote_ref = f"origin/{branch}" if branch else "origin/main"
    remote_exists = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", remote_ref],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).returncode == 0

    if not remote_exists:
        remote_ref = "origin/main"
        run_git("rev-parse", "--verify", remote_ref)

    comparison = run_git("rev-list", "--left-right", "--count", f"HEAD...{remote_ref}")
    try:
        local_only, remote_only = [int(value) for value in comparison.stdout.split()]
    except (TypeError, ValueError) as exc:
        raise SystemExit(
            "Could not determine whether the local repository is up to date."
        ) from exc

    if remote_only > 0:
        status = (
            f"Your Codespace is {remote_only} commit(s) behind {remote_ref}.\n"
            "The analysis has stopped before creating or replacing any output files.\n\n"
            "Run:\n\n"
            "    git pull --ff-only\n\n"
            "Then run:\n\n"
            "    python analysis.py"
        )
        if local_only > 0:
            status += (
                "\n\nYour local branch also contains commits that are not on the remote. "
                "If `git pull --ff-only` cannot complete, review your Git history "
                "before continuing."
            )
        raise SystemExit(status)

    print(f"Repository is up to date with {remote_ref}.")


def save_generated_files_to_repository() -> None:
    generated_paths = ["report.md", "outputs", "figures"]
    run_git("add", "--", *generated_paths)

    staged = subprocess.run(
        ["git", "diff", "--cached", "--quiet", "--", *generated_paths],
        cwd=ROOT,
    ).returncode

    if staged == 0:
        print("No generated changes to commit.")
        return
    if staged != 1:
        raise SystemExit("Could not determine whether generated files changed.")

    run_git(
        "commit",
        "-m",
        "Update survey response quality audit results",
        "--",
        *generated_paths,
    )

    branch = run_git("branch", "--show-current").stdout.strip()
    if not branch:
        raise SystemExit("Cannot automatically push from a detached Git HEAD.")

    run_git("push", "origin", branch)
    print(f"Generated files committed and pushed to origin/{branch}.")


def load_raw_data() -> pd.DataFrame:
    if not RAW_FILE.exists():
        raise FileNotFoundError(
            f"Raw data file not found: {RAW_FILE}\n"
            "Check that the CSV is inside the repository's data/ folder."
        )

    df = pd.read_csv(RAW_FILE)
    for column in ["start_time_bst", "end_time_bst"]:
        if column in df.columns:
            df[column] = pd.to_datetime(df[column], errors="coerce", utc=True)
    return df


def validate_required_columns(df: pd.DataFrame) -> None:
    required = {
        "response_id",
        "survey_status",
        "progress_pct",
        "duration_sec",
        "browser_fingerprint",
        "age",
        "age_band",
        "s1_ordered_delivery_3m",
        "q1_orders_past_30d",
        "q2_last_order",
        "q6_nps",
        "q8_attention_check",
        "q11_problem_last_order",
        "q12_problem_type",
        "q13_contacted_support",
        "q14_support_resolution",
        "q16_open_end",
        *GRID_COLUMNS,
    }

    missing = sorted(required.difference(df.columns))
    if missing:
        raise ValueError("Missing required columns: " + ", ".join(missing))


def age_band_from_age(age: float) -> str | None:
    if pd.isna(age):
        return None
    age = int(age)
    if 18 <= age <= 24:
        return "18-24"
    if 25 <= age <= 34:
        return "25-34"
    if 35 <= age <= 44:
        return "35-44"
    if 45 <= age <= 54:
        return "45-54"
    if 55 <= age <= 64:
        return "55-64"
    if 65 <= age <= 74:
        return "65-74"
    return None


def open_text_is_low_quality(value: object) -> bool:
    if pd.isna(value):
        return True

    text = str(value).strip().lower()
    if not text or text in LOW_QUALITY_OPEN_TEXT:
        return True

    compact = re.sub(r"\s+", "", text)
    letters = re.sub(r"[^a-z]", "", text)
    if len(compact) < 3 or not letters:
        return True
    if len(set(letters)) <= 2 and len(letters) >= 5:
        return True

    tokens = re.findall(r"[a-z]+", text)
    return len(tokens) >= 3 and len(set(tokens)) == 1


def build_quality_flags(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float]]:
    flags = pd.DataFrame(index=df.index)
    flags["response_id"] = df["response_id"]

    flags["flag_partial"] = (
        df["survey_status"].astype(str).str.lower().ne("complete")
        | pd.to_numeric(df["progress_pct"], errors="coerce").lt(100)
    )

    duration = pd.to_numeric(df["duration_sec"], errors="coerce")
    complete_mask = ~flags["flag_partial"] & duration.notna()
    median_complete_duration = float(duration.loc[complete_mask].median())
    speeder_threshold = median_complete_duration / 3.0
    flags["flag_speeder"] = complete_mask & duration.lt(speeder_threshold)

    grid = df[GRID_COLUMNS].apply(pd.to_numeric, errors="coerce")
    flags["flag_straightliner"] = (
        ~flags["flag_partial"]
        & grid.notna().sum(axis=1).eq(len(GRID_COLUMNS))
        & grid.nunique(axis=1, dropna=True).eq(1)
    )

    attention = pd.to_numeric(df["q8_attention_check"], errors="coerce")
    flags["flag_attention_fail"] = (
        ~flags["flag_partial"] & attention.notna() & attention.ne(3)
    )

    age = pd.to_numeric(df["age"], errors="coerce")
    nps = pd.to_numeric(df["q6_nps"], errors="coerce")
    rating_invalid = pd.Series(False, index=df.index)
    for column in RATING_1_TO_7_COLUMNS:
        values = pd.to_numeric(df[column], errors="coerce")
        rating_invalid |= values.notna() & ~values.between(1, 7)

    flags["flag_invalid_value"] = (
        (age.notna() & ~age.between(18, 74))
        | (nps.notna() & ~nps.between(0, 10))
        | rating_invalid
    )

    expected_age_band = age.map(age_band_from_age)
    age_band_mismatch = expected_age_band.notna() & df["age_band"].ne(expected_age_band)
    screener_recency_conflict = (
        df["s1_ordered_delivery_3m"].eq("Yes")
        & df["q2_last_order"].eq("More than 3 months ago")
    )
    zero_orders_recent_order = (
        df["q1_orders_past_30d"].astype(str).eq("0")
        & df["q2_last_order"].isin(["Today", "Past week"])
    )
    problem_no_but_routed_answer = (
        df["q11_problem_last_order"].eq("No")
        & (
            df["q12_problem_type"].notna()
            | df["q13_contacted_support"].notna()
            | df["q14_support_resolution"].notna()
        )
    )
    support_contact_conflict = (
        df["q13_contacted_support"].eq("Yes")
        & ~df["q11_problem_last_order"].eq("Yes")
    )
    resolution_without_contact = (
        df["q14_support_resolution"].notna()
        & ~df["q13_contacted_support"].eq("Yes")
    )

    flags["flag_logic_error"] = (
        age_band_mismatch
        | screener_recency_conflict
        | zero_orders_recent_order
        | problem_no_but_routed_answer
        | support_contact_conflict
        | resolution_without_contact
    )

    duplicate_frame = df[SUBSTANTIVE_DUPLICATE_COLUMNS].fillna("<MISSING>").astype(str)
    answer_signature = pd.util.hash_pandas_object(duplicate_frame, index=False).astype(str)
    duplicate_key = (
        df["browser_fingerprint"].fillna("<MISSING>").astype(str)
        + "|"
        + answer_signature
    )

    ordering = pd.DataFrame(
        {
            "key": duplicate_key,
            "start": df["start_time_bst"],
            "row_number": np.arange(len(df)),
        },
        index=df.index,
    ).sort_values(["key", "start", "row_number"], na_position="last")
    ordering["rank_within_key"] = ordering.groupby("key").cumcount()
    flags["flag_duplicate_like"] = ordering["rank_within_key"].reindex(df.index).gt(0)

    flags["flag_low_quality_open_text"] = (
        ~flags["flag_partial"] & df["q16_open_end"].map(open_text_is_low_quality)
    )

    flag_columns = [
        "flag_partial",
        "flag_speeder",
        "flag_straightliner",
        "flag_attention_fail",
        "flag_invalid_value",
        "flag_logic_error",
        "flag_duplicate_like",
        "flag_low_quality_open_text",
    ]
    flags["total_flags"] = flags[flag_columns].sum(axis=1).astype(int)
    flags["qc_flagged"] = flags["total_flags"].gt(0)

    hard_fail = (
        flags["flag_partial"]
        | flags["flag_invalid_value"]
        | flags["flag_duplicate_like"]
    )
    behavioural_columns = [
        "flag_speeder",
        "flag_straightliner",
        "flag_attention_fail",
        "flag_logic_error",
        "flag_low_quality_open_text",
    ]
    flags["behavioural_flag_count"] = flags[behavioural_columns].sum(axis=1).astype(int)
    flags["recommended_exclude"] = hard_fail | flags["behavioural_flag_count"].ge(2)
    flags["recommended_review"] = flags["qc_flagged"] & ~flags["recommended_exclude"]

    return flags, {
        "median_complete_duration_sec": median_complete_duration,
        "speeder_threshold_sec": speeder_threshold,
    }


def create_quality_summary(
    df: pd.DataFrame, flags: pd.DataFrame, thresholds: dict[str, float]
) -> pd.DataFrame:
    rows = [
        {"metric": "Total responses", "value": len(df)},
        {"metric": "Completed responses", "value": int((df["survey_status"] == "Complete").sum())},
        {"metric": "Responses with at least one QC flag", "value": int(flags["qc_flagged"].sum())},
        {"metric": "Recommended for review", "value": int(flags["recommended_review"].sum())},
        {"metric": "Recommended for exclusion", "value": int(flags["recommended_exclude"].sum())},
        {"metric": "Median completed duration (sec)", "value": round(thresholds["median_complete_duration_sec"], 1)},
        {"metric": "Speeder threshold (sec)", "value": round(thresholds["speeder_threshold_sec"], 1)},
    ]

    for column in [c for c in flags.columns if c.startswith("flag_")]:
        label = column.removeprefix("flag_").replace("_", " ").title()
        rows.append({"metric": f"Flag: {label}", "value": int(flags[column].sum())})

    return pd.DataFrame(rows)


def style_figure_axis(ax: plt.Axes, grid_axis: str) -> None:
    ax.figure.patch.set_facecolor(FIGURE_BACKGROUND)
    ax.set_facecolor(FIGURE_BACKGROUND)
    ax.tick_params(colors=FIGURE_MUTED, labelsize=9.5, length=0, pad=7)
    ax.xaxis.label.set_color(FIGURE_MUTED)
    ax.yaxis.label.set_color(FIGURE_MUTED)
    ax.title.set_color(FIGURE_TEXT)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.grid(axis=grid_axis, color=FIGURE_LINE, linewidth=0.8, alpha=0.6)
    ax.set_axisbelow(True)


def create_figures(df: pd.DataFrame, flags: pd.DataFrame, thresholds: dict[str, float]) -> None:
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)

    with plt.rc_context({"font.family": "sans-serif", "font.size": 10}):
        duration = pd.to_numeric(df["duration_sec"], errors="coerce")
        completed = duration[df["survey_status"].eq("Complete")].dropna()

        fig, ax = plt.subplots(figsize=(9.6, 5.6))
        style_figure_axis(ax, "y")
        ax.hist(
            completed,
            bins=35,
            color=FIGURE_BAR,
            edgecolor=FIGURE_BACKGROUND,
            linewidth=0.7,
        )
        ax.axvline(
            thresholds["speeder_threshold_sec"],
            color=FIGURE_ACCENT,
            linestyle=(0, (4, 4)),
            linewidth=1.6,
            label=f"Speeder threshold  {thresholds['speeder_threshold_sec']:.1f}s",
        )
        ax.set_title(
            "Survey completion duration",
            loc="left",
            pad=18,
            fontsize=16,
            fontweight=400,
        )
        ax.set_xlabel("Duration (seconds)", labelpad=12)
        ax.set_ylabel("Completed responses", labelpad=12)
        legend = ax.legend(frameon=False, loc="upper right", fontsize=9.5)
        for text in legend.get_texts():
            text.set_color(FIGURE_MUTED)
        fig.tight_layout(pad=1.6)
        fig.savefig(
            FIGURE_DIR / "completion_duration_distribution.png",
            dpi=200,
            facecolor=FIGURE_BACKGROUND,
            bbox_inches="tight",
        )
        plt.close(fig)

        flag_columns = [c for c in flags.columns if c.startswith("flag_")]
        counts = flags[flag_columns].sum().sort_values()
        labels = [
            c.removeprefix("flag_").replace("_", " ").title()
            for c in counts.index
        ]

        fig, ax = plt.subplots(figsize=(9.6, 5.6))
        style_figure_axis(ax, "x")
        bars = ax.barh(labels, counts.values, height=0.58, color=FIGURE_BAR)
        maximum = max(float(counts.max()), 1.0)
        ax.set_xlim(0, maximum * 1.16)
        ax.set_title(
            "Survey quality flags",
            loc="left",
            pad=18,
            fontsize=16,
            fontweight=400,
        )
        ax.set_xlabel("Responses flagged", labelpad=12)
        ax.set_ylabel("")
        for bar, value in zip(bars, counts.values):
            ax.text(
                bar.get_width() + maximum * 0.025,
                bar.get_y() + bar.get_height() / 2,
                f"{int(value):,}",
                va="center",
                ha="left",
                color=FIGURE_TEXT,
                fontsize=9.5,
            )
        fig.tight_layout(pad=1.6)
        fig.savefig(
            FIGURE_DIR / "quality_flag_counts.png",
            dpi=200,
            facecolor=FIGURE_BACKGROUND,
            bbox_inches="tight",
        )
        plt.close(fig)


def generate_report(
    df: pd.DataFrame,
    flags: pd.DataFrame,
    thresholds: dict[str, float],
) -> None:
    total = len(df)
    completed = int((df["survey_status"] == "Complete").sum())
    partial = int(flags["flag_partial"].sum())
    flagged = int(flags["qc_flagged"].sum())
    review = int(flags["recommended_review"].sum())
    exclude = int(flags["recommended_exclude"].sum())

    flag_rows = []
    for column in [c for c in flags.columns if c.startswith("flag_")]:
        label = column.removeprefix("flag_").replace("_", " ").title()
        count = int(flags[column].sum())
        percentage = (count / total * 100) if total else 0.0
        flag_rows.append(f"| {label} | {count:,} | {percentage:.1f}% |")

    report = f"""# Survey Response Quality Audit

## Study context

This simulated case study is set within a hypothetical UK online survey about restaurant-delivery usage and experience. The target population is adults aged **18–74** who ordered restaurant delivery within the previous **3 months**, with simulated fieldwork running from **6–20 July 2026**.

The dataset contains **{total:,} captured responses**, including **{completed:,} completed responses** and **{partial:,} partial responses**. Fictional delivery-service names are used only to make the scenario realistic; the purpose of the case study is to assess survey response quality rather than draw conclusions about the restaurant-delivery market.

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

The median duration among completed responses was **{thresholds['median_complete_duration_sec']:.1f} seconds**. The resulting speeder threshold was **{thresholds['speeder_threshold_sec']:.1f} seconds**.

## Findings

**{flagged:,} responses ({(flagged / total * 100 if total else 0):.1f}%)** received at least one QC flag. Of these, **{review:,}** were recommended for manual review and **{exclude:,}** were recommended for exclusion under the pre-specified decision rules.

| QC check | Responses flagged | Share of all responses |
|---|---:|---:|
{chr(10).join(flag_rows)}

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
"""

    REPORT_FILE.write_text(report.strip() + "\n", encoding="utf-8")


def main() -> None:
    check_repository_up_to_date()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df = load_raw_data()
    validate_required_columns(df)
    flags, thresholds = build_quality_flags(df)
    summary = create_quality_summary(df, flags, thresholds)

    flags.to_csv(OUTPUT_DIR / "quality_flags.csv", index=False)
    summary.to_csv(OUTPUT_DIR / "quality_summary.csv", index=False)
    create_figures(df, flags, thresholds)
    generate_report(df, flags, thresholds)

    print("Survey Response Quality Audit")
    print("=" * 34)
    print(f"Responses loaded: {len(df):,}")
    print(
        "Speeder threshold: "
        f"{thresholds['speeder_threshold_sec']:.1f} seconds "
        "(one-third of completed-response median)"
    )
    print(f"Responses with at least one QC flag: {int(flags['qc_flagged'].sum()):,}")
    print(f"Recommended for review: {int(flags['recommended_review'].sum()):,}")
    print(f"Recommended for exclusion: {int(flags['recommended_exclude'].sum()):,}")
    print(f"\nReport written to: {REPORT_FILE.relative_to(ROOT)}")
    print(f"Outputs saved to: {OUTPUT_DIR.relative_to(ROOT)}/")
    print(f"Figures saved to: {FIGURE_DIR.relative_to(ROOT)}/")

    save_generated_files_to_repository()


if __name__ == "__main__":
    main()
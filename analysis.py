"""Survey Response Quality Audit

Portfolio case study using a simulated online survey dataset.

The script audits survey responses for common data-quality problems without
using the simulation ground truth to define the rules. Ground truth is loaded
only at the end, if available, to evaluate how well the audit detected the
injected issues.

Run from the repository root with:

    python analysis.py

Outputs are written to ./outputs and figures to ./figures.
"""

from __future__ import annotations

from pathlib import Path
import re

try:
    import numpy as np
    import pandas as pd
    import matplotlib.pyplot as plt
except ImportError as exc:
    raise SystemExit(
        "Missing Python packages. Install pandas, numpy and matplotlib, then run "
        "the script again. Example: pip install pandas numpy matplotlib"
    ) from exc


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "outputs"
FIGURE_DIR = ROOT / "figures"

RAW_FILE = DATA_DIR / "survey_response_quality_audit_raw.csv"
GROUND_TRUTH_FILE = DATA_DIR / "survey_response_quality_audit_simulation_ground_truth.csv"

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


def load_raw_data() -> pd.DataFrame:
    """Load the raw survey file and parse timestamps."""
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
    """Fail early if important variables are missing from the raw file."""
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
    """Return the expected survey age band for a numeric age."""
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
    """Apply simple, transparent heuristics to an open-ended response."""
    if pd.isna(value):
        return True

    text = str(value).strip().lower()
    if not text:
        return True
    if text in LOW_QUALITY_OPEN_TEXT:
        return True

    compact = re.sub(r"\s+", "", text)
    letters = re.sub(r"[^a-z]", "", text)

    # Very short answers, numeric-only strings and repeated-character strings.
    if len(compact) < 3:
        return True
    if not letters:
        return True
    if len(set(letters)) <= 2 and len(letters) >= 5:
        return True

    # Repeated token such as "none none none" or "word word word".
    tokens = re.findall(r"[a-z]+", text)
    if len(tokens) >= 3 and len(set(tokens)) == 1:
        return True

    return False


def build_quality_flags(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float]]:
    """Create respondent-level QC indicators using pre-specified audit rules."""
    flags = pd.DataFrame(index=df.index)
    flags["response_id"] = df["response_id"]

    # 1. Partial / incomplete responses.
    flags["flag_partial"] = (
        df["survey_status"].astype(str).str.lower().ne("complete")
        | pd.to_numeric(df["progress_pct"], errors="coerce").lt(100)
    )

    # 2. Speeding. Use one-third of the median duration among completed responses.
    duration = pd.to_numeric(df["duration_sec"], errors="coerce")
    complete_mask = ~flags["flag_partial"] & duration.notna()
    median_complete_duration = float(duration.loc[complete_mask].median())
    speeder_threshold = median_complete_duration / 3.0
    flags["flag_speeder"] = complete_mask & duration.lt(speeder_threshold)

    # 3. Straight-lining across the eight 1-7 rating-grid items.
    grid = df[GRID_COLUMNS].apply(pd.to_numeric, errors="coerce")
    grid_answer_count = grid.notna().sum(axis=1)
    grid_unique_count = grid.nunique(axis=1, dropna=True)
    flags["flag_straightliner"] = (
        ~flags["flag_partial"]
        & grid_answer_count.eq(len(GRID_COLUMNS))
        & grid_unique_count.eq(1)
    )

    # 4. Instructional attention check. Correct answer is 3.
    attention = pd.to_numeric(df["q8_attention_check"], errors="coerce")
    flags["flag_attention_fail"] = (
        ~flags["flag_partial"] & attention.notna() & attention.ne(3)
    )

    # 5. Invalid or out-of-range values.
    age = pd.to_numeric(df["age"], errors="coerce")
    nps = pd.to_numeric(df["q6_nps"], errors="coerce")

    rating_invalid = pd.Series(False, index=df.index)
    for column in RATING_1_TO_7_COLUMNS:
        values = pd.to_numeric(df[column], errors="coerce")
        # Missing routed values are allowed; only non-missing values are range-checked.
        rating_invalid |= values.notna() & ~values.between(1, 7)

    flags["flag_invalid_value"] = (
        (age.notna() & ~age.between(18, 74))
        | (nps.notna() & ~nps.between(0, 10))
        | rating_invalid
    )

    # 6. Logical consistency checks.
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

    # 7. Duplicate-like submissions.
    # A later response is flagged when it repeats a fingerprint and the same
    # substantive answer pattern. The earliest matching response is retained as
    # the presumed original rather than automatically flagging the whole group.
    duplicate_frame = df[SUBSTANTIVE_DUPLICATE_COLUMNS].copy()
    duplicate_frame = duplicate_frame.fillna("<MISSING>").astype(str)
    answer_signature = pd.util.hash_pandas_object(
        duplicate_frame, index=False
    ).astype(str)

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
    )
    ordering = ordering.sort_values(["key", "start", "row_number"], na_position="last")
    ordering["rank_within_key"] = ordering.groupby("key").cumcount()
    flags["flag_duplicate_like"] = ordering["rank_within_key"].reindex(df.index).gt(0)

    # 8. Low-quality open-ended text. Only evaluate completed responses.
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

    # Hard failures are structural or clearly invalid. Behavioural indicators
    # are treated more cautiously: two or more are required for auto-exclusion.
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

    thresholds = {
        "median_complete_duration_sec": median_complete_duration,
        "speeder_threshold_sec": speeder_threshold,
    }
    return flags, thresholds


def create_quality_summary(
    df: pd.DataFrame, flags: pd.DataFrame, thresholds: dict[str, float]
) -> pd.DataFrame:
    """Create a compact summary table for the audit."""
    flag_columns = [c for c in flags.columns if c.startswith("flag_")]

    rows = [
        {"metric": "Total responses", "value": len(df)},
        {"metric": "Completed responses", "value": int((df["survey_status"] == "Complete").sum())},
        {"metric": "Responses with at least one QC flag", "value": int(flags["qc_flagged"].sum())},
        {"metric": "Recommended for review", "value": int(flags["recommended_review"].sum())},
        {"metric": "Recommended for exclusion", "value": int(flags["recommended_exclude"].sum())},
        {"metric": "Median completed duration (sec)", "value": round(thresholds["median_complete_duration_sec"], 1)},
        {"metric": "Speeder threshold (sec)", "value": round(thresholds["speeder_threshold_sec"], 1)},
    ]

    for column in flag_columns:
        label = column.removeprefix("flag_").replace("_", " ").title()
        rows.append({"metric": f"Flag: {label}", "value": int(flags[column].sum())})

    return pd.DataFrame(rows)


def evaluate_against_ground_truth(flags: pd.DataFrame) -> pd.DataFrame | None:
    """Evaluate the completed audit against simulation labels, if present.

    Ground truth is deliberately loaded only here, after all QC rules have been
    calculated, so it cannot influence rule construction.
    """
    if not GROUND_TRUTH_FILE.exists():
        return None

    truth = pd.read_csv(GROUND_TRUTH_FILE)
    required = {"response_id", "expected_high_quality_complete"}
    if not required.issubset(truth.columns):
        return None

    evaluation = flags.merge(
        truth[["response_id", "expected_high_quality_complete"]],
        on="response_id",
        how="inner",
    )

    actual_issue = evaluation["expected_high_quality_complete"].eq("No")
    predicted_issue = evaluation["qc_flagged"]

    tp = int((actual_issue & predicted_issue).sum())
    fp = int((~actual_issue & predicted_issue).sum())
    fn = int((actual_issue & ~predicted_issue).sum())
    tn = int((~actual_issue & ~predicted_issue).sum())

    precision = tp / (tp + fp) if (tp + fp) else np.nan
    recall = tp / (tp + fn) if (tp + fn) else np.nan
    specificity = tn / (tn + fp) if (tn + fp) else np.nan
    accuracy = (tp + tn) / (tp + fp + fn + tn) if len(evaluation) else np.nan

    return pd.DataFrame(
        [
            {"metric": "True positives", "value": tp},
            {"metric": "False positives", "value": fp},
            {"metric": "False negatives", "value": fn},
            {"metric": "True negatives", "value": tn},
            {"metric": "Precision", "value": round(precision, 3)},
            {"metric": "Recall", "value": round(recall, 3)},
            {"metric": "Specificity", "value": round(specificity, 3)},
            {"metric": "Accuracy", "value": round(accuracy, 3)},
        ]
    )


def create_figures(df: pd.DataFrame, flags: pd.DataFrame, thresholds: dict[str, float]) -> None:
    """Create two simple portfolio-ready figures."""
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)

    # Survey duration distribution.
    duration = pd.to_numeric(df["duration_sec"], errors="coerce")
    completed = duration[df["survey_status"].eq("Complete")].dropna()

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(completed, bins=35)
    ax.axvline(
        thresholds["speeder_threshold_sec"],
        linestyle="--",
        linewidth=1.5,
        label=f"Speeder threshold: {thresholds['speeder_threshold_sec']:.0f}s",
    )
    ax.set_title("Survey completion duration")
    ax.set_xlabel("Duration (seconds)")
    ax.set_ylabel("Number of completed responses")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "completion_duration_distribution.png", dpi=180)
    plt.close(fig)

    # QC flag counts.
    flag_columns = [c for c in flags.columns if c.startswith("flag_")]
    counts = flags[flag_columns].sum().sort_values()
    labels = [c.removeprefix("flag_").replace("_", " ").title() for c in counts.index]

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.barh(labels, counts.values)
    ax.set_title("Survey quality flags")
    ax.set_xlabel("Number of responses flagged")
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "quality_flag_counts.png", dpi=180)
    plt.close(fig)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df = load_raw_data()
    validate_required_columns(df)

    flags, thresholds = build_quality_flags(df)
    summary = create_quality_summary(df, flags, thresholds)

    flags.to_csv(OUTPUT_DIR / "quality_flags.csv", index=False)
    summary.to_csv(OUTPUT_DIR / "quality_summary.csv", index=False)

    evaluation = evaluate_against_ground_truth(flags)
    if evaluation is not None:
        evaluation.to_csv(OUTPUT_DIR / "ground_truth_evaluation.csv", index=False)

    create_figures(df, flags, thresholds)

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
    print(f"\nOutputs saved to: {OUTPUT_DIR.relative_to(ROOT)}/")
    print(f"Figures saved to: {FIGURE_DIR.relative_to(ROOT)}/")

    if evaluation is not None:
        print("\nGround-truth evaluation")
        for _, row in evaluation.iterrows():
            print(f"{row['metric']}: {row['value']}")


if __name__ == "__main__":
    main()

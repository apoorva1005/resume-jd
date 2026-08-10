import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from app.config import settings
from app.db import close_client, feedback, matches
from app.services.scoring import FEATURE_ORDER


MIN_ROWS = 20
GOOD_SCORE_THRESHOLD = 0.6


async def load_training_data() -> tuple[list[list[float]], list[int]]:
    """
    Build the training dataset from user feedback and match results.

    A label of 1 means the match was considered good, while 0 means
    it was considered bad. If a corrected score is available, use it
    instead of the user's simple thumbs-up/thumbs-down rating.
    """
    features = []
    labels = []
    skipped = 0

    async for feedback_row in feedback().find({}):
        match = await matches().find_one(
            {"_id": feedback_row["match_id"]}
        )

        if match is None:
            skipped += 1
            continue

        values = {
            "cosine_score": match.get("cosine_score"),
            "cross_encoder_score": match.get("cross_encoder_score"),
            **match.get("features", {}),
        }

        # Ignore old matches that don't contain all the features
        # required by the current ranking model.
        if any(values.get(name) is None for name in FEATURE_ORDER):
            skipped += 1
            continue

        corrected_score = feedback_row.get("corrected_score")

        if corrected_score is not None:
            label = int(corrected_score >= GOOD_SCORE_THRESHOLD)
        else:
            label = int(feedback_row["user_rating"] > 0)

        features.append(
            [float(values[name]) for name in FEATURE_ORDER]
        )
        labels.append(label)

    if skipped:
        print(f"Skipped {skipped} feedback row(s) with missing data.")

    return features, labels


def train_model(
    features: list[list[float]],
    labels: list[int],
):
    X = np.array(features)
    y = np.array(labels)

    # The features are on different scales, so standardise them
    # before fitting the logistic regression model.
    model = make_pipeline(
        StandardScaler(),
        LogisticRegression(
            C=0.5,
            class_weight="balanced",
            max_iter=1000,
        ),
    )

    # Use up to five folds, but don't create more folds than
    # the number of examples available for the smaller class.
    class_counts = np.bincount(y)
    folds = min(5, class_counts.min())

    if folds >= 2:
        scores = cross_val_score(
            model,
            X,
            y,
            cv=folds,
            scoring="roc_auc",
        )

        print(
            f"Cross-validated ROC-AUC: "
            f"{scores.mean():.3f} (+/- {scores.std():.3f})"
        )
    else:
        print(
            "Not enough examples from both classes "
            "for cross-validation; skipping."
        )

    model.fit(X, y)
    return model


def show_feature_weights(model) -> None:
    """Print the learned importance of each ranking feature."""

    coefficients = model.named_steps["logisticregression"].coef_[0]

    print("\nLearned feature weights:")

    weights = zip(FEATURE_ORDER, coefficients)

    for name, weight in sorted(
        weights,
        key=lambda item: abs(item[1]),
        reverse=True,
    ):
        print(f"  {name:22} {weight:+.3f}")


async def main() -> None:
    try:
        features, labels = await load_training_data()
    finally:
        await close_client()

    print(f"Loaded {len(features)} labelled example(s).")

    if len(features) < MIN_ROWS:
        print(
            f"At least {MIN_ROWS} examples are needed to train the model. "
            "Collect more feedback first; the API will continue using "
            "the existing weighted scoring method."
        )
        return

    good_matches = sum(labels)
    bad_matches = len(labels) - good_matches

    print(f"  {good_matches} good / {bad_matches} bad")

    # Logistic regression needs examples from both classes.
    if good_matches == 0 or bad_matches == 0:
        print(
            "All feedback belongs to the same class. "
            "There is nothing useful to learn yet."
        )
        return

    model = train_model(features, labels)
    show_feature_weights(model)

    model_path = Path(settings.ranker_path)
    model_path.parent.mkdir(parents=True, exist_ok=True)

    joblib.dump(model, model_path)

    print(f"\nModel saved to {model_path}.")
    print("The API will use it the next time it performs matching.")


if __name__ == "__main__":
    asyncio.run(main())
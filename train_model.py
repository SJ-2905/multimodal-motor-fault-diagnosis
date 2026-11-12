"""Train a Random Forest motor-fault demo model from reproducible synthetic data."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

ROOT = Path(__file__).resolve().parent
FEATURES = ["Vibration RMS (g)", "Voltage (V)", "Current (A)", "Temperature (°C)"]
LABELS = ["Normal", "Mechanical anomaly", "Electrical anomaly", "Thermal anomaly"]

def generate_synthetic_dataset(n_per_class=2000, seed=20261112):
    rng = np.random.default_rng(seed)
    rows = []
    for label in LABELS:
        severity = rng.uniform(0.0, 1.0, n_per_class)
        if label == "Normal":
            vib = 0.16 + 0.10*severity + rng.normal(0, 0.055, n_per_class)
            voltage = 12.0 + rng.normal(0, 0.55, n_per_class)
            current = 0.62 + 0.25*severity + 0.18*(vib-0.21) + rng.normal(0, 0.12, n_per_class)
            temp = 30.0 + 8.0*severity + 1.8*current + rng.normal(0, 3.0, n_per_class)
        elif label == "Mechanical anomaly":
            vib = 0.38 + 0.62*severity + rng.normal(0, 0.16, n_per_class)
            voltage = 12.0 + rng.normal(0, 0.65, n_per_class)
            current = 0.78 + 0.40*severity + 0.22*vib + rng.normal(0, 0.18, n_per_class)
            temp = 32.0 + 10.0*severity + 2.0*current + rng.normal(0, 4.0, n_per_class)
        elif label == "Electrical anomaly":
            direction = rng.choice([-1.0, 1.0], n_per_class)
            voltage = 12.0 + direction*(1.2 + 2.0*severity) + rng.normal(0, 0.55, n_per_class)
            vib = 0.18 + 0.20*severity + rng.normal(0, 0.09, n_per_class)
            current = 0.70 + 0.55*severity + 0.16*np.abs(voltage-12.0) + rng.normal(0, 0.22, n_per_class)
            temp = 32.0 + 12.0*severity + 1.5*current + rng.normal(0, 4.5, n_per_class)
        else:
            temp = 44.0 + 22.0*severity + rng.normal(0, 5.0, n_per_class)
            vib = 0.20 + 0.22*severity + rng.normal(0, 0.09, n_per_class)
            voltage = 12.0 + rng.normal(0, 0.65, n_per_class)
            current = 0.70 + 0.35*severity + rng.normal(0, 0.17, n_per_class)
        block = np.column_stack([vib, voltage, current, temp])
        block[:, 0] = np.clip(block[:, 0], 0.01, 2.5)
        block[:, 1] = np.clip(block[:, 1], 4.0, 24.0)
        block[:, 2] = np.clip(block[:, 2], 0.01, 8.0)
        block[:, 3] = np.clip(block[:, 3], 15.0, 100.0)
        frame = pd.DataFrame(block, columns=FEATURES)
        frame["Fault class"] = label
        rows.append(frame)
    return pd.concat(rows, ignore_index=True).sample(frac=1, random_state=seed).reset_index(drop=True)

def main():
    data_dir, model_dir, report_dir = ROOT/"data", ROOT/"models", ROOT/"reports"
    for folder in (data_dir, model_dir, report_dir):
        folder.mkdir(exist_ok=True)
    data = generate_synthetic_dataset()
    data.to_csv(data_dir/"synthetic_motor_fault_dataset.csv", index=False)
    X, y = data[FEATURES], data["Fault class"]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )
    clf = RandomForestClassifier(
        n_estimators=350, max_features="sqrt", min_samples_leaf=2,
        class_weight="balanced", random_state=42, n_jobs=-1
    )
    clf.fit(X_train, y_train)
    predictions = clf.predict(X_test)
    score = accuracy_score(y_test, predictions)
    joblib.dump(clf, model_dir/"motor_fault_random_forest.joblib")
    report = classification_report(y_test, predictions, labels=LABELS, output_dict=True, zero_division=0)
    cm = confusion_matrix(y_test, predictions, labels=LABELS)
    metrics = {
        "model": "RandomForestClassifier", "random_seed": 42, "dataset_seed": 20261112,
        "rows_total": int(len(data)), "rows_train": int(len(X_train)), "rows_test": int(len(X_test)),
        "features": FEATURES, "classes": LABELS, "synthetic_holdout_accuracy": float(score),
        "classification_report": report, "confusion_matrix_labels": LABELS,
        "confusion_matrix": cm.tolist(),
        "warning": "Synthetic holdout metrics only; not real-world motor fault accuracy."
    }
    (report_dir/"training_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    pd.DataFrame(cm, index=LABELS, columns=LABELS).to_csv(report_dir/"confusion_matrix.csv")
    (report_dir/"classification_report.txt").write_text(
        classification_report(y_test, predictions, labels=LABELS, zero_division=0), encoding="utf-8"
    )
    print(f"Rows: {len(data)} | Train: {len(X_train)} | Test: {len(X_test)}")
    print(f"Synthetic holdout accuracy: {score:.3%}")
    print(classification_report(y_test, predictions, labels=LABELS, zero_division=0))
    print("Saved model to models/motor_fault_random_forest.joblib")

if __name__ == "__main__":
    main()

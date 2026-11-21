"""Train the IsolationForest anomaly model on normal windows; evaluate on held-out sessions + abnormal file."""
import sys, os as _o
sys.path.insert(0, _o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))))
import json
import math
import os
import random
from collections import defaultdict

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest

from ml.common import ART, SEED, now, p, write_metrics
from ml.features import NAMES, decision, session_windows, window_features


def load(path):
    by = defaultdict(list)
    for l in open(path, encoding="utf-8"):
        e = json.loads(l)
        by[e["session_id"]].append(e)
    return by


def windows(by, ids):
    X, y, sc = [], [], []
    for sid in ids:
        for e, w in session_windows(sorted(by[sid], key=lambda e: e["ts"])):
            X.append(window_features(w))
            y.append(int(e["label"] == "abnormal"))
            sc.append(e["scenario"])
    return np.array(X), np.array(y), sc


def fit(X, contamination):
    return IsolationForest(n_estimators=200, contamination=contamination, random_state=SEED).fit(X)


def train():
    normal = load(p("data", "generated", "traces", "normal.jsonl"))
    abn = load(p("data", "generated", "traces", "abnormal.jsonl"))
    ids = sorted(normal)
    random.Random(SEED).shuffle(ids)
    cut = int(0.8 * len(ids))
    tr_ids, te_ids = ids[:cut], ids[cut:]
    Xtr, _, _ = windows(normal, tr_ids)
    # contamination: largest candidate whose false-positive rate on 25% of train sessions (held out of the fit) is <= 3%
    sub = int(0.75 * len(tr_ids))
    Xa, Xv = windows(normal, tr_ids[:sub])[0], windows(normal, tr_ids[sub:])[0]
    cont = 0.005
    for c in (0.005, 0.01, 0.02, 0.03, 0.05):
        if (fit(Xa, c).decision_function(Xv) < 0).mean() <= 0.03:
            cont = c
    model = fit(Xtr, cont)
    # k: a training window at the 1st-percentile decision value scores 0.9
    q = float(np.percentile(model.decision_function(Xtr), 1))
    k = math.log(9) / abs(q) if q < 0 else 50.0
    os.makedirs(ART, exist_ok=True)
    const = {i: float(Xtr[0, i]) for i in range(Xtr.shape[1]) if Xtr[:, i].min() == Xtr[:, i].max()}
    art = {"model": model, "k": k, "threshold": 0.5, "features": NAMES, "const": const}
    joblib.dump(art, os.path.join(ART, "anomaly.joblib"))

    Xn, yn, _ = windows(normal, te_ids)
    Xb, yb, sb = windows(abn, sorted(abn))
    X, y, sc = np.vstack([Xn, Xb]), np.concatenate([yn, yb]), ["normal"] * len(yn) + sb
    pred = (decision(art, X) < 0).astype(int)  # score >= 0.5 <=> decision <= 0
    tp = int(((pred == 1) & (y == 1)).sum())
    pr, rc = tp / max(pred.sum(), 1), tp / max(y.sum(), 1)
    by = {s: {"recall": round(float(pred[(np.array(sc) == s) & (y == 1)].mean()), 4),
              "n": int(((np.array(sc) == s) & (y == 1)).sum())}
          for s in sorted(set(sb) - {"normal"})}
    res = {"precision": round(pr, 4), "recall": round(rc, 4), "f1": round(2 * pr * rc / (pr + rc), 4) if tp else 0.0,
           "n_test_normal": int((y == 0).sum()), "n_test_abnormal": int(y.sum()),
           "false_positive_rate_normal": round(float(pred[y == 0].mean()), 4),
           "by_scenario": by, "contamination": cont, "k": round(k, 4), "threshold": 0.5, "seed": SEED,
           "generated_at": now()}
    write_metrics("anomaly", res)
    return res


if __name__ == "__main__":
    print(json.dumps(train(), indent=2))

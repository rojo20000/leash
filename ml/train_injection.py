"""Train the prompt-injection classifier on corpus split=train, evaluate on split=test."""
import sys, os as _o
sys.path.insert(0, _o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))))
import json
import os
import re

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_score, recall_score
from sklearn.pipeline import FeatureUnion, Pipeline

from ml.common import ART, SEED, normalize, now, p, write_metrics


def build():
    feats = FeatureUnion([
        ("word", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, lowercase=True)),
        ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, lowercase=True)),
    ])
    return Pipeline([("tfidf", feats), ("lr", LogisticRegression(C=10.0, max_iter=1000, random_state=SEED))])


def train():
    rows = [json.loads(l) for l in open(p("data", "corpus", "corpus.jsonl"), encoding="utf-8")]
    for r in rows:
        r["text"] = normalize(r["text"])  # same form ml.api.injection_score gives the model
    tr = [r for r in rows if r["split"] == "train"]
    te = [r for r in rows if r["split"] == "test"]
    # Also train on single benign sentences (train split only) so short benign requests are not scored as injections.
    sents = sorted({s.strip() for r in tr if r["label"] == 0 for s in re.split(r"(?<=[.!?])\s+", r["text"]) if len(s) > 15})
    pipe = build().fit([r["text"] for r in tr] + sents, [r["label"] for r in tr] + [0] * len(sents))
    os.makedirs(ART, exist_ok=True)
    joblib.dump({"pipeline": pipe, "threshold": 0.5}, os.path.join(ART, "injection.joblib"))
    pred = (pipe.predict_proba([r["text"] for r in te])[:, 1] >= 0.5).astype(int)
    y = [r["label"] for r in te]
    pr, rc = precision_score(y, pred), recall_score(y, pred)
    hn = [i for i, r in enumerate(te) if r["hard_negative"]]
    hn_fp = int(sum(pred[i] for i in hn))
    res = {"precision": round(pr, 4), "recall": round(rc, 4), "f1": round(2 * pr * rc / (pr + rc), 4),
           "n_train": len(tr), "n_test": len(te), "n_test_hard_negative": len(hn),
           "hard_negative_false_positives": hn_fp, "threshold": 0.5, "seed": SEED, "generated_at": now()}
    write_metrics("injection", res)
    return res


if __name__ == "__main__":
    r = train()
    print(json.dumps(r, indent=2))
    print(f"hard negatives: {r['n_test_hard_negative']} in test, {r['hard_negative_false_positives']} false positives "
          f"(precision on hard-negative subset has no positives; FP rate {r['hard_negative_false_positives']}/{r['n_test_hard_negative']})")

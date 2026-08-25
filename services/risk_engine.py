import numpy as np
import pickle

import os

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
db_path = os.path.join(BASE_DIR, "fraud.db")

def get_connection():
    import sqlite3
    return sqlite3.connect(db_path, check_same_thread=False)

model = pickle.load(open(os.path.join(BASE_DIR, "fraud_model.pkl"), "rb"))
rf_model = pickle.load(open(os.path.join(BASE_DIR, "rf_model.pkl"), "rb"))
iso_model = pickle.load(open(os.path.join(BASE_DIR, "iso_model.pkl"), "rb"))
scaler = pickle.load(open(os.path.join(BASE_DIR, "scaler.pkl"), "rb"))

initialized = False

def compute_risk(amount, user):
    if amount < 100:
        return {
            "risk": "LOW",
            "risk_score": 0.2,
            "reason": "Very low transaction amount; no additional risk signal was triggered.",
            "factors": ["Transaction amount is below ₹100."],
        }

    if amount < 500:
        return {
            "risk": "LOW",
            "risk_score": 0.3,
            "reason": "Low transaction amount; the risk engine keeps the score in the low-risk range.",
            "factors": ["Transaction amount is below ₹500."],
        }

    import sqlite3
    from datetime import datetime
    import numpy as np

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT amount, time FROM transactions
        WHERE sender=? ORDER BY id DESC LIMIT 10
    """, (user,))
    
    rows = cursor.fetchall()
    conn.close()

    amounts = [r[0] for r in rows]

    # -------- REAL FEATURES --------
    avg = sum(amounts)/len(amounts) if amounts else amount
    max_amt = max(amounts) if amounts else amount
    freq = len(amounts)
    deviation = amount - avg
    ratio = amount / (avg + 1)

    # time gap
    if rows:
        last_time = datetime.strptime(rows[0][1], "%Y-%m-%d %H:%M:%S")
        time_gap = (datetime.now() - last_time).seconds
    else:
        time_gap = 9999

    # -------- FEATURE VECTOR --------
    features = np.array([[amount, avg, max_amt, deviation, ratio, freq, time_gap]])

# -------- PAD TO 30 FEATURES --------
    full_features = np.zeros((1, 30))
    full_features[0][:7] = features

# -------- SCALE (IMPORTANT) --------
    features = scaler.transform(full_features)

    if amount > 3 * avg and amount > 1000:
        return {
            "risk": "HIGH",
            "risk_score": 0.9,
            "reason": "The transaction is substantially larger than the user's recent transaction pattern.",
            "factors": [
                f"Amount ₹{amount:,.0f} is more than 3× the recent average of ₹{avg:,.0f}.",
                "The amount-deviation rule triggered a HIGH-risk decision.",
            ],
        }
    
    if amount >= 15000 and ratio > 2:
        return {
            "risk": "HIGH",
            "risk_score": 0.85,
            "reason": "A high-value transaction is significantly above the recent spending baseline.",
            "factors": [
                f"Transaction amount is ₹{amount:,.0f}.",
                f"Amount is about {ratio:.1f}× the recent average.",
            ],
        }
    
    # -------- ML + ANOMALY --------
    prob = model.predict_proba(features)[0][1]
    anomaly = iso_model.decision_function(features)[0]
    anomaly_score = 1 - (anomaly + 1) / 2
    anomaly_score = max(0,min(anomaly_score, 1))

    # -------- FINAL SCORE --------
    score = 0.4 * prob + 0.3 * anomaly_score + 0.3 * min(1,amount/(avg+1))

    # behavior boost
    if amount > 2 * avg:
        score += 0.15
    
    if amount > 5 * avg:
        score += 0.25

    if freq >= 3 and time_gap < 60:
        score += 0.25

    score = float(max(0, min(score, 1)))

    if amount < 2000:
        score = min(score, 0.65)

    if amount >= 8000 and score < 0.6:
        medium_score = max(score, 0.4)
        return {
            "risk": "MEDIUM",
            "risk_score": medium_score,
            "reason": "The transaction is high-value enough to require additional verification, even though the combined score is below the HIGH threshold.",
            "factors": [
                f"Transaction amount is ₹{amount:,.0f}.",
                f"Combined ML/anomaly/behavior score is {medium_score:.1%}.",
            ],
        }

    # -------- RISK --------
    if score < 0.4:
        risk = "LOW"
    elif score < 0.7:
        risk = "MEDIUM"
    else:
        risk = "HIGH"

    factors = [
        f"Combined risk score: {score:.1%}.",
        f"Recent average transaction: ₹{avg:,.0f}.",
        f"Recent transaction count considered: {freq}.",
    ]
    if amount > 2 * avg:
        factors.append("Amount is more than 2× the recent average, adding a behavioral risk boost.")
    if freq >= 3 and time_gap < 60:
        factors.append("Multiple recent transactions occurred within a short time window.")

    reason = {
        "LOW": "The combined ML, anomaly and behavioral signals remain in the low-risk range.",
        "MEDIUM": "The combined ML, anomaly and behavioral signals indicate elevated risk and require additional verification.",
        "HIGH": "The combined ML, anomaly and behavioral signals indicate a high-risk transaction that should be strongly verified or blocked.",
    }[risk]

    return {"risk": risk, "risk_score": score, "reason": reason, "factors": factors}


def update_model(amount, user, label):
    import sqlite3
    import numpy as np

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT amount FROM transactions
        WHERE sender=? ORDER BY id DESC LIMIT 10
    """, (user,))
    
    rows = cursor.fetchall()
    conn.close()

    amounts = [r[0] for r in rows]

    avg = sum(amounts)/len(amounts) if amounts else amount
    deviation = amount - avg
    ratio = amount / (avg + 1)

    features = np.array([[amount, avg, max(amounts) if amounts else amount, deviation, ratio, len(amounts), 0]])

# pad to 30
    full_features = np.zeros((1, 30))
    full_features[0][:7] = features

# scale
    features = scaler.transform(full_features)

    model.partial_fit(features, [label], classes=[0,1])

    pickle.dump(model, open(os.path.join(BASE_DIR, "fraud_model.pkl"), "wb"))
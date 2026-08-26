import os
import pickle
import secrets
import sqlite3
import time
from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

from services.risk_engine import compute_risk

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "fraud.db")
DEMO_USERNAME = "demo_user"
DEMO_PASSWORD = "PayGuard@123"
DEMO_PIN = "123456"
DEMO_PET = "tommy"
DEMO_CARD = "123"
OTP_LIMIT = 3
OTP_SECONDS = 180

st.set_page_config(
    page_title="PayGuard | UPI Fraud Detection",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)


def load_pickle(name):
    with open(os.path.join(BASE_DIR, name), "rb") as f:
        return pickle.load(f)


@st.cache_resource
def load_artifacts():
    return {
        "metrics": load_pickle("metrics.pkl"),
        "rf": load_pickle("rf_model.pkl"),
        "sgd": load_pickle("fraud_model.pkl"),
        "iso": load_pickle("iso_model.pkl"),
    }


def ensure_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender TEXT,
            receiver TEXT,
            amount REAL,
            fraud INTEGER,
            risk TEXT,
            drift INTEGER DEFAULT 0,
            risk_score REAL,
            time TEXT,
            status TEXT,
            reason TEXT
        )
        """
    )
    # Upgrade older copies of the database that do not have reason.
    columns = {row[1] for row in conn.execute("PRAGMA table_info(transactions)").fetchall()}
    if "reason" not in columns:
        conn.execute("ALTER TABLE transactions ADD COLUMN reason TEXT")
    conn.commit()
    conn.close()


def read_transactions():
    ensure_db()
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM transactions ORDER BY id DESC", conn)
    conn.close()
    return df


def save_transaction(amount, receiver, result, status, reason, auth_method="PIN"):
    risk = result.get("risk", "Unknown")
    score = result.get("risk_score", 0)

    full_reason = reason

    conn = sqlite3.connect(DB_PATH)

    cursor = conn.execute(
        """
        INSERT INTO transactions
        (sender, receiver, amount, fraud, risk, drift, risk_score, time, status, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "demo_user",
            receiver,
            float(amount),
            1 if status == "Fraud" else 0,
            risk,
            0,
            score,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            status,
            full_reason,
        ),
    )

    transaction_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return transaction_id

def logout():
    """Log out the current demo user and clear the active payment flow."""
    reset_flow()
    st.session_state.pop("logged_in", None)
    st.session_state.pop("username", None)


def show_login():
    """Render the PayGuard demo login page."""

    st.markdown(
        """
        <div class="hero">
            <h1>🛡️ PayGuard</h1>
            <p>Secure UPI Fraud Detection & Risk-Based Authentication</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    left, center, right = st.columns([1, 1.2, 1])

    with center:
        st.subheader("🔐 Sign in to PayGuard")
        st.caption("Use the public demo account to explore the application.")

        username = st.text_input(
            "Username",
            placeholder="Enter demo username"
        )

        password = st.text_input(
            "Password",
            type="password",
            placeholder="Enter demo password"
        )

        if st.button(
            "Login",
            type="primary",
            use_container_width=True
        ):
            if (
                username.strip() == DEMO_USERNAME
                and password == DEMO_PASSWORD
            ):
                st.session_state.logged_in = True
                st.session_state.username = DEMO_USERNAME

                st.success(
                    "Login successful! Welcome to PayGuard."
                )

                time.sleep(0.5)
                st.rerun()

            else:
                st.error("Invalid username or password.")

        with st.expander("Demo credentials"):
            st.write(
                "These credentials are for this portfolio "
                "demonstration only."
            )

            st.code(
                "Username: demo_user\n"
                "Password: PayGuard@123"
            )

        st.info(
            "This is a simulated payment application. "
            "No real banking credentials or real UPI payments are used."
        )
def reset_flow():
    for key in [
        "stage", "amount", "receiver", "risk_result", "auth_method",
        "otp_attempts", "otp_expires", "generated_otp", "pin", "otp", "pet", "card",
        "completed",
    ]:
        st.session_state.pop(key, None)


def start_flow():
    st.session_state.stage = "pin"
    st.session_state.completed = False
    st.session_state.pin = ""
    st.session_state.otp = ""
    st.session_state.pet = ""
    st.session_state.card = ""


def generate_otp():
    """Generate a cryptographically secure random 6-digit demo OTP."""
    return f"{secrets.randbelow(1_000_000):06d}"


def begin_otp(stage, reset_attempts=True):
    st.session_state.stage = stage
    if reset_attempts or "otp_attempts" not in st.session_state:
        st.session_state.otp_attempts = OTP_LIMIT
    st.session_state.otp_expires = time.time() + OTP_SECONDS
    st.session_state.generated_otp = generate_otp()
    st.session_state.otp = ""


def finish_transaction(status, reason, auth_method):
    result = st.session_state.risk_result

    transaction_id = save_transaction(
        st.session_state.amount,
        st.session_state.receiver,
        result,
        status,
        reason,
        auth_method,
    )

    st.session_state.completed = True
    st.session_state.final_status = status
    st.session_state.final_reason = reason
    st.session_state.transaction_id = transaction_id
    st.session_state.stage = "complete"


ensure_db()
artifacts = load_artifacts()

st.markdown(
    """
    <style>
    .block-container {padding-top: 2rem; padding-bottom: 2rem;}
    .hero {padding: 1.2rem 0 1rem 0;}
    .hero h1 {margin-bottom: .2rem;}
    .hero p {font-size: 1.05rem; opacity: .78;}
    .risk-card {padding: 1.2rem; border-radius: 14px; border: 1px solid rgba(128,128,128,.25);}
    </style>
    """,
    unsafe_allow_html=True,
)
# ---------------------------------------------------------------------------
# Authentication gate
# ---------------------------------------------------------------------------

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    show_login()
    st.stop()

st.sidebar.title("🛡️ PayGuard")
st.sidebar.caption("UPI Fraud Detection Demo")

st.sidebar.success(
    f"Logged in as: {st.session_state.get('username', DEMO_USERNAME)}"
)

if st.sidebar.button(
    "Logout",
    use_container_width=True
):
    logout()
    st.rerun()

st.sidebar.divider()
page = st.sidebar.radio(
    "Navigation",
    ["Overview", "Fraud Prediction", "Live Dashboard", "Model Analysis"],
)
st.sidebar.divider()
st.sidebar.caption("Portfolio demonstration only. No real UPI payments are processed.")

if page == "Overview":
    st.markdown(
        """
        <div class="hero">
        <h1>🛡️ PayGuard</h1>
        <p>Continuous real-time UPI fraud detection using machine learning, adaptive risk scoring and risk-based authentication.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("ML Models", "3")
    c2.metric("Risk Levels", "3")
    c3.metric("Authentication", "Risk-based")
    c4.metric("Interface", "Streamlit")

    st.subheader("End-to-end transaction flow")
    cols = st.columns(5)
    steps = [
        ("1", "Transaction", "Enter a simulated UPI transaction."),
        ("2", "PIN", "Verify the demo transaction PIN."),
        ("3", "Risk Engine", "Combine behavioral rules, ML probability and anomaly scoring."),
        ("4", "Authentication", "LOW → approve, MEDIUM → OTP, HIGH → OTP + security questions."),
        ("5", "Monitoring", "Store the decision, reason and risk score in the dashboard."),
    ]
    for col, (num, title, text) in zip(cols, steps):
        with col:
            st.markdown(f"### {num}. {title}")
            st.write(text)

    st.subheader("Technology")
    st.write("Python · Scikit-learn · Random Forest · SGD Classifier · Isolation Forest · FastAPI · Streamlit · SQLite")

    with st.expander("Demo credentials"):
        st.write("These are public demo credentials only; they are not real banking credentials.")
        st.code("PIN: 123456\nOTP: generated randomly for each verification/resend\nPet name: tommy\nLast 3 card digits: 123")
        st.caption("For this portfolio demo, the generated OTP is shown on-screen instead of being sent by SMS.")

    st.info(
        "The deployed interface is a simulation for demonstrating fraud-detection logic. "
        "It does not connect to a bank, UPI network, SMS provider, or real payment account."
    )

elif page == "Fraud Prediction":
    st.title("🔍 Fraud Prediction")
    st.caption("Simulate a UPI payment and follow the complete risk-based authentication flow.")

    # New transaction setup
    if "stage" not in st.session_state or st.session_state.stage == "complete":
        if st.session_state.get("completed"):
            status = st.session_state.final_status
            reason = st.session_state.final_reason
            if status == "Success":
                # Payment Success Screen
                transaction_id = st.session_state.get(
                    "transaction_id",
                    "N/A"
                )
                st.markdown(
                    """
                    <style>
                    .payment-success {
                        text-align: center;
                        padding: 35px 20px;
                        border-radius: 20px;
                        background: linear-gradient(180deg, #f0fff7 0%, #ffffff 100%);
                        border: 1px solid #d8f5e5;
                        margin-top: 20px;
                    }

                    .success-icon {
                        width: 80px;
                        height: 80px;
                        margin: 0 auto 18px auto;
                        border-radius: 50%;
                        background: #20c77a;
                        color: white;
                        font-size: 48px;
                        line-height: 80px;
                        font-weight: bold;
                        box-shadow: 0 8px 25px rgba(32, 199, 122, 0.25);
                    }

                    .success-title {
                        font-size: 30px;
                        font-weight: 700;
                        color: #1f2937;
                        margin-bottom: 8px;
                    }

                    .success-subtitle {
                        font-size: 16px;
                        color: #6b7280;
                        margin-bottom: 25px;
                    }

                    .payment-card {
                        max-width: 500px;
                        margin: 0 auto;
                        padding: 22px;
                        background: white;
                        border-radius: 16px;
                        border: 1px solid #e5e7eb;
                        box-shadow: 0 5px 20px rgba(0, 0, 0, 0.06);
                    }

                    .merchant-name {
                        font-size: 21px;
                        font-weight: 650;
                        color: #111827;
                        margin-bottom: 15px;
                    }

                    .amount {
                        font-size: 34px;
                        font-weight: 750;
                        color: #111827;
                        margin-bottom: 18px;
                    }

                    .payment-detail {
                        display: flex;
                        justify-content: space-between;
                        padding: 10px 0;
                        border-bottom: 1px solid #f0f0f0;
                        font-size: 14px;
                    }

                    .detail-label {
                        color: #6b7280;
                    }

                    .detail-value {
                        color: #111827;
                        font-weight: 600;
                    }
                    </style>
                    """,
                    unsafe_allow_html=True
                )

                st.html(
                    f"""
                    <style>
                    .payment-success {{
                        text-align: center;
                        padding: 35px 20px;
                        border-radius: 20px;
                        background: linear-gradient(
                            180deg,
                            #f0fff7 0%,
                            #ffffff 100%
                        );
                        border: 1px solid #d8f5e5;
                        margin-top: 20px;
                        font-family: Arial, sans-serif;
                    }}

                    .success-icon {{
                        width: 85px;
                        height: 85px;
                        margin: 0 auto 18px auto;
                        border-radius: 50%;
                        background: #20c77a;
                        color: white;
                        font-size: 52px;
                        line-height: 85px;
                        font-weight: bold;
                        box-shadow: 0 8px 25px rgba(32, 199, 122, 0.25);
                    }}

                    .success-title {{
                        font-size: 30px;
                        font-weight: 700;
                        color: #1f2937;
                        margin-bottom: 8px;
                    }}

                    .success-subtitle {{
                        font-size: 16px;
                        color: #6b7280;
                        margin-bottom: 25px;
                    }}

                    .payment-card {{
                        max-width: 520px;
                        margin: 0 auto;
                        padding: 25px;
                        background: white;
                        border-radius: 18px;
                        border: 1px solid #e5e7eb;
                        box-shadow: 0 5px 20px rgba(0, 0, 0, 0.06);
                    }}

                    .merchant-name {{
                        font-size: 21px;
                        font-weight: 650;
                        color: #111827;
                        margin-bottom: 12px;
                    }}

                    .amount {{
                        font-size: 36px;
                        font-weight: 750;
                        color: #111827;
                        margin-bottom: 20px;
                    }}

                    .payment-detail {{
                        display: flex;
                        justify-content: space-between;
                        padding: 11px 0;
                        border-bottom: 1px solid #f0f0f0;
                        font-size: 14px;
                    }}

                    .detail-label {{
                        color: #6b7280;
                    }}

                    .detail-value {{
                        color: #111827;
                        font-weight: 600;
                    }}
                    </style>

                    <div class="payment-success">

                        <div class="success-icon">
                            ✓
                        </div>

                        <div class="success-title">
                            Payment Successful
                        </div>

                        <div class="success-subtitle">
                            Your payment has been completed successfully
                        </div>

                        <div class="payment-card">

                            <div class="merchant-name">
                                🏪 {st.session_state.receiver}
                            </div>

                            <div class="amount">
                                ₹{st.session_state.amount:,.2f}
                            </div>

                            <div class="payment-detail">
                                <span class="detail-label">
                                    Status
                                </span>
                                <span class="detail-value">
                                    ✓ Successful
                                </span>
                            </div>

                            <div class="payment-detail">
                                <span class="detail-label">
                                    Payment Method
                                </span>
                                <span class="detail-value">
                                    UPI
                                </span>
                            </div>

                            <div class="payment-detail">
                                <span class="detail-label">
                                    Transaction ID
                                </span>
                                <span class="detail-value">
                                    PG{int(transaction_id):06d}
                                </span>
                            </div>

                        </div>

                    </div>
                    """
                )
            else:
                # Transaction Failed Screen
                transaction_id = st.session_state.get(
                        "transaction_id",
                        "N/A"
                )

                st.html(
                    f"""
                    <style>
                    .payment-failed {{
                        text-align: center;
                        padding: 35px 20px;
                        border-radius: 20px;
                        background: linear-gradient(
                            180deg,
                            #fff5f5 0%,
                            #ffffff 100%
                        );
                        border: 1px solid #ffd9d9;
                        margin-top: 20px;
                        font-family: Arial, sans-serif;
                    }}

                    .failed-icon {{
                        width: 85px;
                        height: 85px;
                        margin: 0 auto 18px auto;
                        border-radius: 50%;
                        background: #ef4444;
                        color: white;
                        font-size: 48px;
                        line-height: 85px;
                        font-weight: bold;
                        box-shadow: 0 8px 25px rgba(239, 68, 68, 0.25);
                    }}

                    .failed-title {{
                        font-size: 30px;
                        font-weight: 700;
                        color: #1f2937;
                        margin-bottom: 8px;
                    }}

                    .failed-subtitle {{
                        font-size: 16px;
                        color: #6b7280;
                        margin-bottom: 25px;
                    }}

                    .failed-card {{
                        max-width: 520px;
                        margin: 0 auto;
                        padding: 25px;
                        background: white;
                        border-radius: 18px;
                        border: 1px solid #e5e7eb;
                        box-shadow: 0 5px 20px rgba(0, 0, 0, 0.06);
                    }}

                    .merchant-name {{
                        font-size: 21px;
                        font-weight: 650;
                        color: #111827;
                        margin-bottom: 12px;
                    }}

                    .amount {{
                        font-size: 36px;
                        font-weight: 750;
                        color: #111827;
                        margin-bottom: 20px;
                    }}

                    .payment-detail {{
                        display: flex;
                        justify-content: space-between;
                        padding: 11px 0;
                        border-bottom: 1px solid #f0f0f0;
                        font-size: 14px;
                    }}

                    .detail-label {{
                        color: #6b7280;
                    }}

                    .detail-value {{
                        color: #111827;
                        font-weight: 600;
                    }}
                    </style>

                    <div class="payment-failed">

                        <div class="failed-icon">
                            ✕
                        </div>

                        <div class="failed-title">
                            Transaction Failed
                        </div>

                        <div class="failed-subtitle">
                            Your payment could not be completed
                        </div>

                        <div class="failed-card">

                            <div class="merchant-name">
                                🏪 {st.session_state.receiver}
                            </div>

                            <div class="amount">
                                ₹{st.session_state.amount:,.2f}
                            </div>

                            <div class="payment-detail">
                                <span class="detail-label">
                                    Status
                                </span>
                                <span class="detail-value">
                                    ✕ Failed
                                </span>
                            </div>

                            <div class="payment-detail">
                                <span class="detail-label">
                                    Payment Method
                                </span>
                                <span class="detail-value">
                                    UPI
                                </span>
                            </div>

                            <div class="payment-detail">
                                <span class="detail-label">
                                    Transaction ID
                                </span>
                                <span class="detail-value">
                                    PG{int(transaction_id):06d}
                                </span>
                            </div>

                        </div>

                    </div>
                    """
                )
            st.divider()
            if st.button("Start New Transaction", type="primary"):
                reset_flow()
                st.rerun()
        else:
            left, right = st.columns([1, 1])
            with left:
                amount = st.number_input("Transaction amount (₹)", min_value=1.0, value=2500.0, step=100.0)
                receiver = st.text_input("Receiver / Merchant", value="demo_merchant")
                if st.button("Continue to PIN", type="primary", use_container_width=True):
                    st.session_state.amount = float(amount)
                    st.session_state.receiver = receiver.strip() or "demo_merchant"
                    start_flow()
                    st.rerun()
            with right:
                st.info(
                    "The demo first verifies a PIN, then uses the ML risk result to choose the appropriate authentication path."
                )
        st.stop()

    stage = st.session_state.stage

    if stage == "pin":
        st.subheader("🔐 Step 1 — PIN Verification")
        st.write(f"Paying **₹{st.session_state.amount:,.2f}** to **{st.session_state.receiver}**")
        pin = st.text_input("Enter 6-digit demo PIN", type="password", max_chars=6)
        st.caption("Demo PIN: 123456")
        if st.button("Verify PIN", type="primary"):
            if pin != DEMO_PIN:
                result = {"risk": "HIGH", "risk_score": 0.90}
                st.session_state.risk_result = result
                finish_transaction("Fraud", "Wrong PIN", "PIN")
                st.rerun()
            st.session_state.stage = "analyze"
            st.rerun()
        st.stop()

    if stage == "analyze":
        st.subheader("🧠 Step 2 — Fraud Risk Analysis")
        with st.spinner("Analyzing transaction risk..."):
            try:
                result = compute_risk(float(st.session_state.amount), "demo_user")
            except Exception as exc:
                st.error(f"Prediction failed: {exc}")
                st.stop()
        st.session_state.risk_result = result
        st.session_state.stage = "risk"
        st.rerun()

    result = st.session_state.risk_result
    risk = result.get("risk", "UNKNOWN")
    score = float(result.get("risk_score", 0.0))
    pct = score * 100
    reason = result.get("reason", "Risk score generated by the project's risk engine.")
    factors = result.get("factors", [])

    if stage == "risk":
        st.subheader("🚦 Step 3 — Risk Decision")
        a, b = st.columns([1, 1])
        with a:
            st.metric("Risk Score", f"{pct:.1f}%")
            st.progress(min(max(score, 0.0), 1.0))
            if risk == "LOW":
                st.success("🟢 LOW RISK")
            elif risk == "MEDIUM":
                st.warning("🟠 MEDIUM RISK")
            else:
                st.error("🔴 HIGH RISK")
        with b:
            st.markdown("**Why was this transaction classified this way?**")
            st.write(reason)
            if factors:
                for factor in factors:
                    st.write(f"• {factor}")

        st.divider()
        if risk == "LOW":
            st.success("No additional verification is required for this demo transaction.")
            if st.button("Approve Transaction", type="primary"):
                finish_transaction("Success", "Low predicted risk; transaction approved.", "PIN only")
                st.rerun()
        elif risk == "MEDIUM":
            st.warning("Additional verification required: OTP")
            if st.button("Continue to OTP", type="primary"):
                begin_otp("otp_medium")
                st.rerun()
        else:
            st.error("Additional verification required: OTP + security questions")
            if st.button("Continue to High-Risk Verification", type="primary"):
                begin_otp("otp_high")
                st.rerun()
        st.stop()

    if stage in ("otp_medium", "otp_high"):
        remaining = max(0, int(st.session_state.otp_expires - time.time()))
        if remaining <= 0:
            finish_transaction("Fraud", "OTP verification expired.", "OTP")
            st.rerun()

        st.subheader("📱 Step 4 — OTP Verification")
        m1, m2 = st.columns(2)
        m1.metric("Time remaining", f"{remaining // 60}:{remaining % 60:02d}")
        m2.metric("Attempts remaining", st.session_state.otp_attempts)
        st.success(
            f"📱 Demo OTP generated: **{st.session_state.generated_otp}**"
        )
        st.caption(
            "A new 6-digit OTP is generated for every verification flow and every resend. "
            "In production, this would be delivered through an SMS/email provider."
        )
        otp = st.text_input("Enter OTP", type="password", max_chars=6)

        verify_col, resend_col = st.columns(2)
        with verify_col:
            verify_clicked = st.button("Verify OTP", type="primary", use_container_width=True)
        with resend_col:
            resend_clicked = st.button("↻ Resend OTP", use_container_width=True)

        if resend_clicked:
            begin_otp(stage, reset_attempts=False)
            st.success("A new OTP has been generated.")
            st.rerun()

        if verify_clicked:
            if otp == st.session_state.generated_otp:
                if stage == "otp_medium":
                    finish_transaction(
                        "Success",
                        "Medium-risk transaction verified successfully with OTP.",
                        "PIN + OTP",
                    )
                    st.rerun()
                else:
                    st.session_state.stage = "security"
                    st.rerun()
            else:
                st.session_state.otp_attempts -= 1
                if st.session_state.otp_attempts <= 0:
                    finish_transaction("Fraud", "OTP Attempts Exceeded", "PIN + OTP")
                    st.rerun()
                st.error(f"Wrong OTP. Attempts left: {st.session_state.otp_attempts}")
        st.caption("3 attempts are allowed and each OTP expires after 180 seconds.")
        time.sleep(1)
        st.rerun()

    if stage == "security":
        st.subheader("🛡️ Step 5 — High-Risk Security Verification")
        st.warning("This transaction has a HIGH risk score. OTP has been verified; complete both security checks.")
        pet = st.text_input("What is your pet name?", value="")
        card = st.text_input("Enter last 3 digits of your card", max_chars=3)
        st.caption("Demo answers: pet name = tommy · last 3 digits = 123")

        if st.button("Verify Security Questions", type="primary"):
            if pet.strip().lower() != DEMO_PET or card.strip() != DEMO_CARD:
                finish_transaction(
                    "Fraud",
                    "High-risk transaction blocked because security verification failed.",
                    "PIN + OTP + Security Questions",
                )
                st.rerun()
            finish_transaction(
                "Success",
                "High-risk transaction verified successfully with OTP and security questions.",
                "PIN + OTP + Security Questions",
            )
            st.rerun()
        st.stop()

elif page == "Live Dashboard":
    st.title("📊 Live Dashboard")
    df = read_transactions()

    if df.empty:
        st.info("No transactions have been recorded yet. Use Fraud Prediction to create demo transactions.")
    else:
        total = len(df)
        fraud = int((df["fraud"] == 1).sum())
        safe = int((df["fraud"] == 0).sum())
        fraud_rate = fraud / total * 100 if total else 0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Transactions", total)
        c2.metric("Approved", safe)
        c3.metric("Flagged", fraud)
        c4.metric("Fraud Rate", f"{fraud_rate:.1f}%")

        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            risk_counts = df["risk"].fillna("Unknown").value_counts().reset_index()
            risk_counts.columns = ["Risk", "Count"]
            st.plotly_chart(
                px.pie(risk_counts, names="Risk", values="Count", title="Risk Distribution"),
                use_container_width=True,
            )
        with col2:
            st.plotly_chart(
                px.histogram(df, x="amount", nbins=25, title="Transaction Amount Distribution"),
                use_container_width=True,
            )

        st.subheader("Recent Transactions")
        display_cols = [
            c for c in ["time", "receiver", "amount", "risk", "risk_score", "status", "reason"]
            if c in df.columns
        ]
        st.dataframe(df[display_cols].head(50), use_container_width=True, hide_index=True)

elif page == "Model Analysis":
    st.title("🤖 Model Analysis")
    metrics = artifacts["metrics"]

    rows = []
    for name, values in metrics.items():
        rows.append(
            {
                "Model": name,
                "Accuracy": values.get("accuracy", 0),
                "Precision": values.get("precision", 0),
                "Recall": values.get("recall", 0),
                "F1 Score": values.get("f1", 0),
            }
        )
    metrics_df = pd.DataFrame(rows)

    st.subheader("Training-set evaluation stored with the project")
    st.dataframe(
        metrics_df.style.format({c: "{:.2%}" for c in ["Accuracy", "Precision", "Recall", "F1 Score"]}),
        use_container_width=True,
        hide_index=True,
    )

    chart_df = metrics_df.melt(id_vars="Model", var_name="Metric", value_name="Score")
    st.plotly_chart(
        px.bar(
            chart_df,
            x="Metric",
            y="Score",
            color="Model",
            barmode="group",
            range_y=[0, 1],
            title="Model Metrics",
        ),
        use_container_width=True,
    )

    st.subheader("Models in the project")
    a, b, c = st.columns(3)
    a.markdown("**SGD Classifier**\n\nProbabilistic baseline used by the risk engine.")
    b.markdown("**Random Forest**\n\nTree-based supervised model trained for fraud classification.")
    c.markdown("**Isolation Forest**\n\nUnsupervised anomaly detector used as part of risk scoring.")

    st.warning(
        "Important: the project's original training data is the Kaggle credit-card fraud dataset, "
        "while the application presents the workflow as a UPI transaction simulation. "
        "The demo should therefore be described as a proof-of-concept rather than a production UPI fraud model."
    )

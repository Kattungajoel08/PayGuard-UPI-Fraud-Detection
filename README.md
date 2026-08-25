# PayGuard — UPI Fraud Detection

Streamlit portfolio demo for a continuous UPI fraud-detection proof of concept.

## Features
- Random 6-digit OTP generated for every verification/resend
- 3 OTP attempts with 180-second expiry
- Transaction risk prediction
- LOW / MEDIUM / HIGH risk classification
- Risk score visualization
- Transaction history dashboard
- SGD Classifier, Random Forest and Isolation Forest analysis
- SQLite-backed demo transaction history

## Run locally

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

> This is a simulation/proof of concept. It does not process real UPI payments.

## Important model note

The original training pipeline uses the Kaggle credit-card fraud dataset and a 30-feature input schema. The application adapts the project's existing behavioral risk-engine logic for the UPI simulation. It should therefore be presented as a fraud-detection proof of concept, not as a production banking model.

### Demo authentication
- PIN: `123456`
- OTP: generated randomly at runtime and displayed on-screen for the demo
- Pet name: `tommy`
- Last 3 card digits: `123`

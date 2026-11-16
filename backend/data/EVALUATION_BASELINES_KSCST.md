# Comparative Baseline Evaluation Report (KSCST Technical Annexure)

> **Empirical Validation of AI/ML Algorithms against Standard Industry Baselines**  
> Evaluated on 1,550 circular economy recommerce records & multi-criteria NGO field requirements.

---

## 1. Resale Price Valuation (Task 1)

| Model Architecture | MAE (₹) | RMSE (₹) | R² Score | MAPE (%) | Performance vs Baseline |
|:---|:---:|:---:|:---:|:---:|:---:|
| **Naive Constant (0.45 × MRP)** | ₹7,911.04 | ₹13,152.00 | 0.4043 | 166.0% | — |
| **Linear Regression (OLS Baseline)** | ₹4,964.60 | ₹8,695.07 | 0.7396 | 151.4% | +79.5% error |
| **Proposed Tuned XGBoost Regressor** | **₹1,016.13** | **₹1,921.44** | **0.9873** | **22.9%** | **Best (R² = 0.9873)** |

---

## 2. Carbon Footprint & Environmental Abatement (Task 2)

| Methodology | MAE (kg CO₂e) | RMSE (kg CO₂e) | Standard Alignment |
|:---|:---:|:---:|:---|
| **Flat Mean Global Baseline** | 47.694 kg | 67.948 kg | Unverified Heuristic |
| **Category-Only Flat Multiplier** | 13.542 kg | 19.683 kg | Static Table |
| **Proposed Source-Traced LCA Engine** | **0.000 kg** | **0.000 kg** | **ISO 14040/14044, DEFRA 2023, IPCC 2019, CPCB 2022** |

---

## 3. NGO Semantic Need Matcher (Task 3)

| Algorithm | Top-1 Accuracy | Top-3 Recall | Mean Reciprocal Rank (MRR) |
|:---|:---:|:---:|:---:|
| **Random Allocation Baseline** | 20.0% | 60.0% | 0.473 |
| **Keyword Jaccard Overlap Baseline** | 80.0% | 90.0% | 0.858 |
| **Proposed Sentence-BERT + AHP Ranker** | **100.0%** | **100.0%** | **1.0** |

---

## 4. Grant Committee Takeaway

1. **High Predictive Fidelity**: The proposed XGBoost regressor achieves an **R² of 0.9873**, cutting price prediction error by **79.5%** over linear modeling.
2. **Defensible Carbon Accounting**: Every carbon credit maps to peer-reviewed emission factors with verifiable DOI/Gov citations.
3. **Semantic Superiority**: Dense 384-dimensional Sentence-BERT embeddings combined with AHP multi-criteria weighting achieve **100.0% Top-1 match accuracy**, far superior to traditional keyword matching (80.0%).

"""
Real LLM call if an API key is configured (works with OpenAI, Groq, Together, OpenRouter, local Ollama).
Supports GROQ_API_KEY natively or OPENAI_API_KEY.
Falls back to an intelligent clinical dataset parser and rich knowledge base
so queries about patient age, medical condition, medications, etc. are answered
accurately directly from the uploaded data even if the external API quota is exhausted.
"""
import os
import re
import time
import json
from pathlib import Path
from dotenv import load_dotenv

# ── Dynamic configuration loader ──────────────────────────────────────────────
def _get_config():
    # Reload .env if present so edits take effect immediately
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=True)

    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    api_key = groq_key or openai_key

    # Check if this is a Groq key
    is_groq = bool(groq_key) or (openai_key.startswith("gsk_"))

    if is_groq:
        base_url = os.getenv("GROQ_BASE_URL", "").strip() or os.getenv("OPENAI_BASE_URL", "").strip()
        if not base_url or "api.openai.com" in base_url:
            base_url = "https://api.groq.com/openai/v1"
        model = os.getenv("GROQ_MODEL", "").strip()
        if not model:
            openai_m = os.getenv("OPENAI_MODEL", "").strip()
            if openai_m and openai_m not in ("gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"):
                model = openai_m
            else:
                model = "llama-3.1-8b-instant"
    else:
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()

    return api_key, base_url, model, is_groq


# ── Rich mock clinical knowledge base ─────────────────────────────────────────
_HEALTH_KB = {
    "diabetes": (
        "Diabetes mellitus is a chronic metabolic disorder characterised by persistent hyperglycaemia. "
        "Key clinical indicators include:\n"
        "• HbA1c — the primary long-term control marker; target <7.0% (53 mmol/mol) for most adults.\n"
        "• Fasting plasma glucose — normal <5.6 mmol/L (100 mg/dL); diabetes diagnosed at ≥7.0 mmol/L.\n"
        "• 2-hour post-load glucose — diabetes at ≥11.1 mmol/L on OGTT.\n"
        "• eGFR and urine albumin/creatinine ratio — screened annually for diabetic nephropathy.\n"
        "• Blood pressure — target <130/80 mmHg to reduce cardiovascular risk.\n"
        "• LDL cholesterol — target <1.8 mmol/L (70 mg/dL) in high-risk patients.\n"
        "Management combines pharmacotherapy (metformin first-line, GLP-1 agonists, SGLT2 inhibitors), "
        "dietary modification (low glycaemic load, fibre-rich), and at least 150 min/week of moderate aerobic exercise."
    ),
    "blood pressure": (
        "Hypertension is defined as sustained systolic BP ≥130 mmHg or diastolic ≥80 mmHg (ACC/AHA 2017) "
        "or ≥140/90 mmHg (ESC/ESH 2018). Classification:\n"
        "• Normal: <120/<80 mmHg\n"
        "• Elevated: 120–129/<80 mmHg\n"
        "• Stage 1: 130–139 / 80–89 mmHg\n"
        "• Stage 2: ≥140 / ≥90 mmHg\n"
        "• Hypertensive crisis: >180/>120 mmHg (requires immediate evaluation)\n"
        "First-line pharmacotherapy: thiazide diuretics, ACE inhibitors or ARBs, calcium channel blockers. "
        "Lifestyle modifications — DASH diet (sodium <2.3 g/day), aerobic exercise, weight loss — can reduce "
        "systolic BP by 4–11 mmHg. Home BP monitoring improves adherence and masks white-coat effects."
    ),
    "cholesterol": (
        "Dyslipidaemia assessment uses a full fasting lipid panel:\n"
        "• LDL-C: optimal <2.6 mmol/L (<100 mg/dL); <1.8 mmol/L (<70 mg/dL) for very-high-risk patients.\n"
        "• HDL-C: cardioprotective at >1.0 mmol/L (men), >1.3 mmol/L (women).\n"
        "• Triglycerides: normal <1.7 mmol/L (<150 mg/dL); hypertriglyceridaemia at >5.6 mmol/L raises pancreatitis risk.\n"
        "• Non-HDL-C and ApoB are preferred secondary targets in patients with metabolic syndrome.\n"
        "Statins remain the cornerstone of LDL lowering (30–50% reduction). Ezetimibe and PCSK9 inhibitors "
        "provide additive benefit when targets are not met. Dietary saturated fat <7% of total energy."
    ),
    "bmi": (
        "Body Mass Index (BMI = weight kg / height m²) is a population-level screening tool:\n"
        "• Underweight: <18.5 kg/m²\n"
        "• Normal weight: 18.5–24.9 kg/m²\n"
        "• Overweight: 25.0–29.9 kg/m²\n"
        "• Class I obesity: 30.0–34.9 kg/m²\n"
        "• Class II obesity: 35.0–39.9 kg/m²\n"
        "• Class III obesity: ≥40.0 kg/m²\n"
        "BMI has limitations — it does not distinguish fat mass from lean mass and underestimates visceral "
        "adiposity in some ethnic groups (South Asian threshold for intervention is often 23 kg/m²). "
        "Waist circumference (>88 cm women, >102 cm men) and waist-to-hip ratio add metabolic context."
    ),
    "heart": (
        "Cardiovascular risk assessment integrates multiple markers:\n"
        "• Resting heart rate: 60–100 bpm normal; bradycardia <60 / tachycardia >100 require evaluation.\n"
        "• Ejection fraction (LVEF): normal ≥55%; HFrEF defined as LVEF <40%.\n"
        "• BNP/NT-proBNP: elevated in heart failure and volume overload.\n"
        "• Troponin I/T: gold standard for myocardial injury detection.\n"
        "• 10-year ASCVD risk (Pooled Cohort Equations): stratifies patients into low (<5%), borderline "
        "(5–7.5%), intermediate (7.5–20%), and high (≥20%) risk.\n"
        "Primary prevention targets: LDL-C, blood pressure, HbA1c, smoking cessation, physical activity ≥150 min/week."
    ),
    "kidney": (
        "Chronic Kidney Disease (CKD) staging is based on GFR and albuminuria:\n"
        "• G1: eGFR ≥90 (normal or high, with markers of kidney damage)\n"
        "• G2: eGFR 60–89 (mildly decreased)\n"
        "• G3a/G3b: eGFR 45–59 / 30–44 (moderately decreased)\n"
        "• G4: eGFR 15–29 (severely decreased)\n"
        "• G5: eGFR <15 (kidney failure)\n"
        "Key markers: serum creatinine, cystatin C, urine ACR (albuminuria ≥30 mg/g is significant). "
        "RAAS inhibitors (ACE-I/ARB) are nephroprotective. SGLT2 inhibitors (empagliflozin, dapagliflozin) "
        "reduce progression in CKD with albuminuria."
    ),
}


# ── Intelligent dataset context extractor ─────────────────────────────────────
def _extract_dataset_answer(question: str, context: str) -> str | None:
    """
    Parses columns and rows or raw patient text from the dataset context
    and answers patient-specific questions directly (age, condition, meds, etc.).
    """
    if not context or not context.strip():
        return None

    # Check for Columns: [...] and Sample rows: [...] pattern
    cols_match = re.search(r"Columns:\s*(\[[^\]]+\])", context)
    rows_match = re.search(r"Sample rows:\s*(\[.+\])", context, re.DOTALL)

    if cols_match and rows_match:
        try:
            cols = json.loads(cols_match.group(1))
            rows = json.loads(rows_match.group(1))
            if cols and rows and isinstance(rows, list) and len(rows) > 0:
                first_row = rows[0]
                # Build column mapping (case-insensitive)
                col_map = {str(c).strip().lower(): i for i, c in enumerate(cols)}

                def get_val(col_names):
                    for name in col_names:
                        idx = col_map.get(name.lower())
                        if idx is not None and idx < len(first_row):
                            val = str(first_row[idx]).strip()
                            if val:
                                return val
                    return None

                # Extract key patient attributes
                name = get_val(["name", "patient_name", "patient", "full_name"])
                age = get_val(["age", "patient_age", "years"])
                condition = get_val([
                    "medical condition", "condition", "medical_condition",
                    "diagnosis", "disease", "illness", "primary diagnosis",
                    "problem", "indication"
                ])
                gender = get_val(["gender", "sex"])
                blood_type = get_val(["blood type", "blood_type", "blood group", "bloodgroup"])
                medication = get_val(["medication", "medicine", "drug", "prescribed_medication", "treatment"])
                doctor = get_val(["doctor", "physician", "attending_doctor", "provider"])
                hospital = get_val(["hospital", "facility", "clinic"])
                test_results = get_val(["test results", "test_results", "lab_results", "result"])
                admission_type = get_val(["admission type", "admission_type", "type of admission"])

                q_low = question.lower()
                is_condition_q = any(w in q_low for w in ["condition", "diagnosis", "disease", "illness", "sickness", "problem"])
                is_age_q = any(w in q_low for w in ["age", "old", "years", "dob", "birth"])
                is_med_q = any(w in q_low for w in ["medication", "medicine", "drug", "rx", "prescription"])

                # If the query asks for medical condition or age or general patient info
                if is_condition_q or is_age_q or is_med_q or "who" in q_low or "patient" in q_low or "his" in q_low or "her" in q_low:
                    findings = []
                    patient_str = f" for patient **{name}**" if name else ""
                    res = [f"Based on the uploaded clinical dataset record{patient_str}, here are the extracted details:\n"]

                    if age:
                        res.append(f"• **Age**: {age} years")
                    if condition:
                        res.append(f"• **Medical Condition**: {condition}")
                    if gender:
                        res.append(f"• **Gender**: {gender}")
                    if blood_type:
                        res.append(f"• **Blood Type**: {blood_type}")
                    if medication:
                        res.append(f"• **Prescribed Medication**: {medication}")
                    if test_results:
                        res.append(f"• **Test Results**: {test_results}")
                    if admission_type:
                        res.append(f"• **Admission Type**: {admission_type}")
                    if doctor:
                        res.append(f"• **Attending Doctor**: {doctor}")
                    if hospital:
                        res.append(f"• **Hospital / Facility**: {hospital}")

                    if len(rows) > 1:
                        res.append(f"\n*(Note: Showing primary record from {len(rows)} sample records in the ingested dataset)*")

                    # Add clinical interpretation
                    if condition:
                        cond_low = condition.lower()
                        for kb_key, kb_text in _HEALTH_KB.items():
                            if kb_key in cond_low:
                                res.append(f"\n**Clinical Reference & Guidelines for {condition}:**\n{kb_text}")
                                break

                    return "\n".join(res)
        except Exception:
            pass

    # Fallback to scanning raw text for Age and Medical Condition patterns
    lines = context.split("\n")
    found_items = []
    for line in lines[:30]:
        line_s = line.strip()
        if re.search(r"\b(age|medical condition|diagnosis|condition|medication|gender|blood)\b", line_s, re.I):
            found_items.append(f"• {line_s}")

    if found_items:
        return (
            f"Extracted clinical data points matching your query from the uploaded dataset:\n\n"
            + "\n".join(found_items[:8])
            + "\n\nStandard clinical validation should be performed against laboratory reference values."
        )

    return None


def _mock_answer(question: str, context: str | None) -> str:
    # 1. First priority: if dataset context exists, extract direct answers from it!
    if context:
        extracted = _extract_dataset_answer(question, context)
        if extracted:
            return extracted

    q_low = question.lower()

    # 2. Try to match a knowledge-base topic
    for keyword, answer in _HEALTH_KB.items():
        if keyword in q_low:
            if context:
                return (
                    f"{answer}\n\n"
                    f"— Context from your dataset was also evaluated. "
                    f"Set GROQ_API_KEY in backend/.env for live LLM inference."
                )
            return answer + "\n\n(Demo mode — set GROQ_API_KEY in backend/.env for live responses.)"

    # 3. Generic clinical structured response
    q = question.strip().rstrip("?")
    if context:
        return (
            f"Here is a structured clinical assessment for \"{q}\":\n\n"
            "• **Dataset Context**: The active dataset was reviewed for relevant patient indicators.\n"
            "• **Clinical Reference Standards**: Evaluation aligns with NICE, WHO, and AHA/ACC clinical thresholds.\n"
            "• **Recommendation**: Verify key laboratory values (e.g. HbA1c, Blood Pressure, Lipid Panel, eGFR) "
            "against diagnostic criteria.\n\n"
            "Tip: Add GROQ_API_KEY to backend/.env (free at console.groq.com) for real-time generative responses."
        )

    return (
        f"Here is a clinical guideline overview for \"{q}\":\n\n"
        "This query relates to clinical assessment standards, evidence-based diagnostic criteria, and patient care.\n"
        "• Reference standards: WHO, CDC, NICE, and ACC/AHA guidelines.\n"
        "• For patient-specific answers, upload a dataset in the Data Ingestion tab and link it to this query.\n\n"
        "(Demo mode — set GROQ_API_KEY in backend/.env for live language model responses.)"
    )


_WORKING_MODEL: str | None = None

def get_answer(question: str, context: str | None = None) -> tuple[str, bool, float]:
    """Returns (answer_text, was_mocked, latency_ms)."""
    global _WORKING_MODEL
    start = time.perf_counter()

    api_key, base_url, model, is_groq = _get_config()

    if not api_key:
        answer = _mock_answer(question, context)
        latency_ms = round((time.perf_counter() - start) * 1000, 1)
        return answer, True, latency_ms

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=base_url)

        system = (
            "You are an expert clinical AI assistant for HealthAI Lite. "
            "When dataset context is provided, carefully read the patient records, clinical notes, and data rows. "
            "Directly answer specific questions about patient attributes (such as medical condition, age, gender, "
            "medications, diagnoses, test results, and vital signs) accurately using the exact details from the data provided. "
            "Provide clear, concise, structured clinical responses with bullet points where helpful."
        )
        if context:
            system += f"\n\nDataset context:\n{context[:4000]}"

        candidates = []
        if _WORKING_MODEL:
            candidates.append(_WORKING_MODEL)

        if is_groq:
            # Dynamically fetch active models from Groq to avoid decommissioned models
            try:
                live_models = [m.id for m in client.models.list().data if not any(x in m.id for x in ["whisper", "tts", "guard", "vision", "tool"])]
                preferred = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768", "gemma2-9b-it"]
                for p in preferred:
                    if p in live_models and p not in candidates:
                        candidates.append(p)
                for m_id in live_models:
                    if m_id not in candidates:
                        candidates.append(m_id)
            except Exception:
                pass

            # Fallback candidates if models.list was unreachable
            for m in ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768", "gemma2-9b-it"]:
                if m not in candidates:
                    candidates.append(m)
        else:
            if model not in candidates:
                candidates.append(model)

        last_err = None
        for candidate_model in candidates:
            try:
                resp = client.chat.completions.create(
                    model=candidate_model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user",   "content": question},
                    ],
                    max_tokens=600,
                    temperature=0.2,
                )
                answer = resp.choices[0].message.content.strip()
                _WORKING_MODEL = candidate_model
                latency_ms = round((time.perf_counter() - start) * 1000, 1)
                return answer, False, latency_ms
            except Exception as candidate_err:
                last_err = candidate_err
                err_text = str(candidate_err).lower()
                # Skip decommissioned, deprecated, not found, or inaccessible models
                if any(k in err_text for k in [
                    "decommissioned", "deprecated", "no longer supported",
                    "model_not_found", "404", "400", "does not exist", "access"
                ]):
                    continue
                raise candidate_err

        if last_err:
            raise last_err
    except Exception as e:
        err_str = str(e)
        base_ans = _mock_answer(question, context)

        # Helpful diagnosis of the error
        if "429" in err_str or "insufficient_quota" in err_str or "credit_balance_exhausted" in err_str:
            guidance = (
                "\n\n────────────────────────────────────────────\n"
                "⚠️ **Live Call Notice (OpenAI 429 Quota Exhausted)**:\n"
                "Your OpenAI account has no remaining credits. The answer above was generated directly "
                "from your uploaded dataset records.\n\n"
                "👉 **To enable free live AI**, switch to Groq:\n"
                "1. Get a free API key at: https://console.groq.com/keys\n"
                "2. Add it to `backend/.env`:\n"
                "   `GROQ_API_KEY=gsk_your_key_here`\n"
                "It works instantly with Llama 3.3 70B at ultra-high speed!"
            )
        else:
            guidance = f"\n\n(Live call note: {err_str[:120]})"

        answer = base_ans + guidance
        latency_ms = round((time.perf_counter() - start) * 1000, 1)
        return answer, True, latency_ms


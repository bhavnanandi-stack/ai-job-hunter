import streamlit as st
import json
from anthropic import Anthropic
from datetime import datetime
from sqlalchemy import create_engine, text

# ==========================================
# PAGE CONFIG
# ==========================================
st.set_page_config(page_title="AI Job Hunter", page_icon="🎯", layout="centered")

# Retrieve secrets
CLAUDE_API_KEY = st.secrets.get("CLAUDE_API_KEY", "")
DATABASE_URL = st.secrets.get("DATABASE_URL", "")

# ==========================================
# DATABASE ENGINE (pg8000 - Python 3.12 safe)
# ==========================================
DATABASE_URL = st.secrets.get("DATABASE_URL", "")
CLAUDE_API_KEY = st.secrets.get("CLAUDE_API_KEY", "")

def get_engine():
    db_url = DATABASE_URL.replace("postgresql://", "postgresql+pg8000://")
    return create_engine(db_url)

def init_db():
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                profile_text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sent_jobs (
                id SERIAL PRIMARY KEY,
                user_email TEXT,
                job_id TEXT,
                title TEXT,
                company TEXT,
                date_sent TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.commit()
        return True
    except Exception as e:
        st.error(f"❌ Database connection error: {e}")
        return False

# ==========================================
# RESUME PARSER (CLAUDE AI)
# ==========================================
def parse_resume_with_claude(resume_text):
    """Uses Claude to extract email and format the profile."""
    client = Anthropic(api_key=CLAUDE_API_KEY)

    prompt = f"""
    You are an AI assistant. I will provide a candidate's raw resume.
    Your task is to:
    1. Find and extract the candidate's email address.
    2. Summarize their resume into a clean "Recruiter Profile" (Skills, Experience, Goals).

    Raw Resume:
    {resume_text}

    Return ONLY a JSON object exactly like this (no markdown, no extra text):
    {{
        "email": "extracted_email@example.com",
        "profile": "Cleaned up profile summary here..."
    }}
    """

    try:
        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )

        text_response = response.content[0].text.strip()
        if "```json" in text_response:
            text_response = text_response.split("```json")[1].split("```")[0]
        elif "```" in text_response:
            text_response = text_response.split("```")[1].split("```")[0]

        return json.loads(text_response)
    except Exception as e:
        return {"error": str(e)}

# ==========================================
# USER INTERFACE
# ==========================================
st.title("🎯 AI Job Hunter")
st.markdown("**Your Personal AI Recruiter** — Works 24/7 in the Cloud")
st.markdown("Paste your resume below. Our AI extracts your profile and emails you high-match remote jobs every morning!")

st.divider()

# Safety checks
if not DATABASE_URL:
    st.error("❌ Database not configured. Please set DATABASE_URL in Render secrets.")
    st.stop()

if not CLAUDE_API_KEY:
    st.error("❌ Claude API key not set. Please add CLAUDE_API_KEY to Render secrets.")
    st.stop()

if not init_db():
    st.error("❌ Could not connect to database. Check your DATABASE_URL.")
    st.stop()

# Resume input
resume_input = st.text_area(
    "📄 Paste your Resume or LinkedIn Profile here:",
    height=300,
    placeholder="Copy-paste your resume text, LinkedIn profile, or any career info here..."
)

submit_btn = st.button("🚀 Start Hunting Jobs for Me", use_container_width=True, type="primary")

if submit_btn:
    if len(resume_input) < 100:
        st.error("❌ Please paste a longer resume (minimum 100 characters) so our AI can understand your profile.")
    else:
        with st.spinner("🧠 AI is analyzing your resume and extracting your email..."):
            parsed_data = parse_resume_with_claude(resume_input)

            if "error" in parsed_data:
                st.error(f"❌ Failed to parse resume: {parsed_data['error']}")

            elif not parsed_data.get("email") or "@" not in parsed_data.get("email", ""):
                st.error("❌ Could not find an email address in your resume. Please include your email in the text.")

            else:
                user_email = parsed_data["email"]
                user_profile = parsed_data["profile"]

                # Save to Neon Database
                try:
                    engine = get_engine()
                    with engine.connect() as conn:
                        conn.execute(
                            text("""
                                INSERT INTO users (email, profile_text)
                                VALUES (:email, :profile)
                                ON CONFLICT (email) DO UPDATE
                                SET profile_text = EXCLUDED.profile_text,
                                    created_at = CURRENT_TIMESTAMP
                            """),
                            {"email": user_email, "profile": user_profile}
                        )
                        conn.commit()

                    st.success("✅ Profile saved successfully!")
                    st.info(f"📧 We found your email: **{user_email}**")
                    st.markdown("""
                    ### 🎉 You're all set! Here's what happens next:
                    1. Every morning at **9:00 AM IST**, our AI scans the internet for remote jobs
                    2. Claude evaluates each job against **your specific skills and experience**
                    3. Only jobs with **80%+ match score** are sent to you
                    4. You get a beautiful email with top job recommendations and direct apply links
                    """)

                except Exception as e:
                    st.error(f"❌ Database error: {e}")

st.divider()
st.caption("🤖 Powered by Claude AI | Runs 24/7 in the cloud | Free forever")

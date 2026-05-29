import os
import json
import streamlit as st
from anthropic import Anthropic
from sqlalchemy import create_engine, text

# ------------------------------------------
# PAGE CONFIG
# ------------------------------------------
st.set_page_config(
    page_title="AI Job Hunter",
    page_icon="🎯",
    layout="centered"
)

# ------------------------------------------
# LOAD SECRETS
# ------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL") or st.secrets.get("DATABASE_URL", "")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY") or st.secrets.get("CLAUDE_API_KEY", "")

# ------------------------------------------
# DATABASE HELPERS
# ------------------------------------------

def get_engine():
    db_url = DATABASE_URL.replace("postgresql://", "postgresql+pg8000://")
    return create_engine(db_url)

def init_db():
    sql_users = (
        "CREATE TABLE IF NOT EXISTS users ("
        "id SERIAL PRIMARY KEY, "
        "email TEXT UNIQUE NOT NULL, "
        "profile_text TEXT NOT NULL, "
        "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
        ")"
    )
    sql_sent = (
        "CREATE TABLE IF NOT EXISTS sent_jobs ("
        "id SERIAL PRIMARY KEY, "
        "user_email TEXT, "
        "job_id TEXT, "
        "title TEXT, "
        "company TEXT, "
        "date_sent TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
        ")"
    )
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text(sql_users))
            conn.execute(text(sql_sent))
            conn.commit()
        return True
    except Exception as e:
        st.error(f"Database error: {e}")
        return False

def save_user(email, profile):
    sql = (
        "INSERT INTO users (email, profile_text) "
        "VALUES (:email, :profile) "
        "ON CONFLICT (email) DO UPDATE "
        "SET profile_text = EXCLUDED.profile_text, "
        "created_at = CURRENT_TIMESTAMP"
    )
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text(sql), {"email": email, "profile": profile})
            conn.commit()
        return True, None
    except Exception as e:
        return False, str(e)

# ------------------------------------------
# CLAUDE RESUME PARSER
# ------------------------------------------

def parse_resume(resume_text):
    prompt = (
        "You are an AI assistant. Read the resume below and do two things:\n"
        "1. Extract the candidate email address.\n"
        "2. Write a short recruiter-style profile summary.\n\n"
        "Resume:\n" + resume_text + "\n\n"
        "Return ONLY valid JSON like this (no markdown):\n"
        '{"email": "user@example.com", "profile": "Summary here"}'
    )
    try:
        client = Anthropic(api_key=CLAUDE_API_KEY)
        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        output = response.content[0].text.strip()
        if "```json" in output:
            output = output.split("```json")[1].split("```")[0].strip()
        elif "```" in output:
            output = output.split("```")[1].split("```")[0].strip()
        return json.loads(output)
    except Exception as e:
        return {"error": str(e)}

# ------------------------------------------
# UI
# ------------------------------------------

st.title("🎯 AI Job Hunter")
st.markdown("Paste your resume below. The AI will extract your profile and email you matching remote jobs every morning.")
st.divider()

if not DATABASE_URL:
    st.error("DATABASE_URL is missing. Add it in Render Environment Variables.")
    st.stop()

if not CLAUDE_API_KEY:
    st.error("CLAUDE_API_KEY is missing. Add it in Render Environment Variables.")
    st.stop()

if not init_db():
    st.stop()

resume_input = st.text_area(
    "📄 Paste your Resume here",
    height=300,
    placeholder="Make sure your email address is included in the resume text..."
)

if st.button("🚀 Start Hunting Jobs for Me", use_container_width=True):
    if len(resume_input.strip()) < 100:
        st.error("Please paste a longer resume (minimum 100 characters).")
    else:
        with st.spinner("🧠 Analyzing your resume with Claude AI..."):
            result = parse_resume(resume_input)

        if "error" in result:
            st.error("Parsing failed: " + result["error"])

        else:
            email = result.get("email", "").strip()
            profile = result.get("profile", "").strip()

            if not email or "@" not in email:
                st.error("Could not find a valid email in your resume. Please include your email.")

            elif not profile:
                st.error("Could not generate a profile summary. Please try again.")

            else:
                ok, err = save_user(email, profile)
                if ok:
                    st.success("✅ Profile saved successfully!")
                    st.info("📧 Email detected: **" + email + "**")
                    st.markdown(
                        "**What happens next:**\n"
                        "- Every morning our AI scans the web for remote jobs\n"
                        "- Claude scores each job against your profile\n"
                        "- Only 80%+ matches are emailed to you\n"
                        "- Check your inbox tomorrow morning!"
                    )
                else:
                    st.error("Could not save to database: " + str(err))

st.divider()
st.caption("🤖 Powered by Claude AI | Runs 24/7 | Free to use")

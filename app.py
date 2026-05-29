import streamlit as st
import psycopg2
import json
import os
from anthropic import Anthropic
from datetime import datetime

# ==========================================
# PAGE CONFIG
# ==========================================
st.set_page_config(page_title="AI Job Hunter", page_icon="🎯", layout="centered")

# Retrieve secrets
CLAUDE_API_KEY = st.secrets.get("CLAUDE_API_KEY", "")
DATABASE_URL = st.secrets.get("DATABASE_URL", "")

# ==========================================
# DATABASE SETUP
# ==========================================
def init_db():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        c = conn.cursor()
        # Create Users table
        c.execute('''CREATE TABLE IF NOT EXISTS users (
                        id SERIAL PRIMARY KEY,
                        email TEXT UNIQUE NOT NULL,
                        profile_text TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )''')
        # Create Sent Jobs table
        c.execute('''CREATE TABLE IF NOT EXISTS sent_jobs (
                        id SERIAL PRIMARY KEY,
                        user_email TEXT,
                        job_id TEXT,
                        title TEXT,
                        company TEXT,
                        date_sent TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )''')
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Database connection error: {e}")
        return False

# ==========================================
# RESUME PARSER (CLAUDE AI)
# ==========================================
def parse_resume_with_claude(resume_text):
    """Uses Claude to extract the email and format the profile."""
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
        
        # Clean and parse JSON
        text = response.content[0].text.strip()
        if "```json" in text: 
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text: 
            text = text.split("```")[1].split("```")[0]
        
        return json.loads(text)
    except Exception as e:
        return {"error": str(e)}

# ==========================================
# USER INTERFACE
# ==========================================
st.title("🎯 AI Job Hunter")
st.markdown("**Your Personal AI Recruiter** — Works 24/7 in the Cloud")
st.markdown("Paste your resume below. Our AI will analyze your profile and email you high-match remote jobs every morning!")

st.divider()

# Check if database is working
if not DATABASE_URL:
    st.error("❌ Database not configured. Please set DATABASE_URL in Render secrets.")
    st.stop()

if not CLAUDE_API_KEY:
    st.error("❌ Claude API key not set. Please add CLAUDE_API_KEY to Render secrets.")
    st.stop()

if not init_db():
    st.error("❌ Could not connect to database.")
    st.stop()

# Resume input
resume_input = st.text_area("📄 Paste your Resume or LinkedIn Profile here:", height=300, placeholder="Copy-paste your resume text, LinkedIn profile, or any career info...")

col1, col2 = st.columns(2)

with col1:
    submit_btn = st.button("🚀 Start Hunting Jobs for Me", use_container_width=True, type="primary")

with col2:
    st.button("ℹ️ How It Works", use_container_width=True)

if submit_btn:
    if len(resume_input) < 100:
        st.error("❌ Please paste a longer resume so our AI can understand your profile. (Minimum 100 characters)")
    else:
        with st.spinner("🧠 AI is analyzing your resume and extracting your email..."):
            parsed_data = parse_resume_with_claude(resume_input)
            
            if "error" in parsed_data:
                st.error(f"❌ Failed to parse resume: {parsed_data['error']}")
            elif not parsed_data.get("email") or "@" not in parsed_data.get("email", ""):
                st.error("❌ Could not find an email address in your resume. Please include your email in the resume text.")
            else:
                user_email = parsed_data["email"]
                user_profile = parsed_data["profile"]
                
                # Save to Database
                try:
                    conn = psycopg2.connect(DATABASE_URL)
                    c = conn.cursor()
                    # Insert or update user
                    c.execute("""
                        INSERT INTO users (email, profile_text) 
                        VALUES (%s, %s)
                        ON CONFLICT (email) DO UPDATE 
                        SET profile_text = EXCLUDED.profile_text,
                            created_at = CURRENT_TIMESTAMP
                    """, (user_email, user_profile))
                    conn.commit()
                    conn.close()
                    
                    st.success("✅ Success! Your profile has been saved!")
                    st.info(f"📧 **Email:** {user_email}\n\n🎯 **Your AI Recruiter is now active!** You will receive your first job matches tomorrow morning at 9:00 AM.")
                    st.markdown("""
                    ### What Happens Next:
                    1. Our system searches the internet for remote jobs matching your profile
                    2. Claude AI evaluates each job against YOUR specific skills and experience
                    3. We send you ONLY high-match opportunities (80%+ relevance)
                    4. You get a daily email with top job recommendations
                    """)
                except psycopg2.IntegrityError:
                    st.warning(f"⚠️ This email ({user_email}) is already registered! We've updated your profile.")
                except Exception as e:
                    st.error(f"❌ Database error: {e}")

st.divider()
st.caption("🤖 Powered by Claude AI | Runs 24/7 in the cloud | Fully Automated")

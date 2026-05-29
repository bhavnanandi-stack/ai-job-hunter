import os
import json
import requests
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from anthropic import Anthropic
from datetime import datetime
from sqlalchemy import create_engine, text

# ==========================================
# ENVIRONMENT VARIABLES
# ==========================================
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_APP_PASSWORD = os.getenv("SENDER_APP_PASSWORD")
DATABASE_URL = os.getenv("DATABASE_URL")

print("=" * 60)
print("🚀 AI JOB SEARCH WORKFLOW STARTED")
print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 60)

# ==========================================
# DATABASE ENGINE (pg8000 - Python 3.12 safe)
# ==========================================
def get_engine():
    """Create SQLAlchemy engine using pg8000 driver."""
    db_url = DATABASE_URL.replace("postgresql://", "postgresql+pg8000://")
    return create_engine(db_url)

def init_db(engine):
    """Create tables if they don't exist."""
    with engine.connect() as conn:
        conn.execute(text('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                profile_text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        '''))
        conn.execute(text('''
            CREATE TABLE IF NOT EXISTS sent_jobs (
                id SERIAL PRIMARY KEY,
                user_email TEXT,
                job_id TEXT,
                title TEXT,
                company TEXT,
                date_sent TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        '''))
        conn.commit()

def is_job_sent(conn, user_email, job_id):
    """Check if this job was already sent to this user."""
    result = conn.execute(
        text("SELECT 1 FROM sent_jobs WHERE user_email = :email AND job_id = :job_id"),
        {"email": user_email, "job_id": job_id}
    )
    return result.fetchone() is not None

def record_job_sent(conn, user_email, job_id, title, company):
    """Record that this job was sent to this user."""
    conn.execute(
        text("INSERT INTO sent_jobs (user_email, job_id, title, company) VALUES (:email, :job_id, :title, :company)"),
        {"email": user_email, "job_id": job_id, "title": title, "company": company}
    )
    conn.commit()

# ==========================================
# FETCH JOBS FROM INTERNET
# ==========================================
def fetch_jobs():
    """Fetch remote jobs from multiple free APIs."""
    print("\n🔍 Fetching jobs from internet...")
    jobs = []

    # Source 1: Remotive API
    try:
        url = "https://remotive.com/api/remote-jobs"
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            data = response.json()
            for job in data.get('jobs', [])[:15]:
                jobs.append({
                    "id": f"remotive_{job['id']}",
                    "title": job["title"],
                    "company": job["company_name"],
                    "location": job.get("candidate_required_location", "Worldwide"),
                    "url": job["url"],
                    "description": job.get("description", "")[:1500],
                    "source": "Remotive"
                })
            print(f"  ✅ Remotive: {len([j for j in jobs if j['source'] == 'Remotive'])} jobs")
    except Exception as e:
        print(f"  ⚠️ Remotive error: {e}")

    # Source 2: JustRemote API
    try:
        url = "https://api.justremote.co/jobs?query=product"
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            data = response.json()
            for job in data.get('jobs', [])[:5]:
                jobs.append({
                    "id": f"justremote_{job['id']}",
                    "title": job["title"],
                    "company": job["company"]["name"],
                    "location": job.get("location", "Worldwide"),
                    "url": job["links"]["website"],
                    "description": job.get("description", "")[:1500],
                    "source": "JustRemote"
                })
            print(f"  ✅ JustRemote: {len([j for j in jobs if j['source'] == 'JustRemote'])} jobs")
    except Exception as e:
        print(f"  ⚠️ JustRemote error: {e}")

    print(f"\n✅ Total jobs fetched: {len(jobs)}")
    return jobs

# ==========================================
# EVALUATE JOB WITH CLAUDE
# ==========================================
def evaluate_job(job, user_profile):
    """Claude evaluates the job against a specific user's profile."""
    client = Anthropic(api_key=CLAUDE_API_KEY)

    prompt = f"""
You are an elite executive recruiter. Evaluate this job against this candidate.

CANDIDATE PROFILE:
{user_profile}

JOB DETAILS:
- Title: {job['title']}
- Company: {job['company']}
- Location: {job['location']}
- Description: {job['description']}

Return ONLY JSON (no markdown, no extra text):
{{
    "match_score": <0-100>,
    "why": "<1-2 sentence explanation of why this is or isn't a good fit>"
}}
"""

    try:
        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )

        text_response = response.content[0].text.strip()
        if "```json" in text_response:
            text_response = text_response.split("```json")[1].split("```")[0]
        elif "```" in text_response:
            text_response = text_response.split("```")[1].split("```")[0]

        return json.loads(text_response)
    except Exception as e:
        print(f"  ⚠️ Claude error: {e}")
        return {"match_score": 0, "why": "Evaluation failed"}

# ==========================================
# SEND EMAIL
# ==========================================
def send_email(user_email, jobs):
    """Send personalized email to user with matched jobs."""
    if not jobs:
        return

    jobs = sorted(jobs, key=lambda x: x.get('match_score', 0), reverse=True)

    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"🎯 Your AI Recruiter: {len(jobs)} High-Match Jobs Today"
    msg['From'] = SENDER_EMAIL
    msg['To'] = user_email

    html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; color: #333; background: #f5f5f5; }}
            .container {{ max-width: 700px; margin: 0 auto; padding: 20px; background: white; border-radius: 8px; }}
            .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; text-align: center; }}
            .job-card {{ border: 1px solid #ddd; padding: 15px; margin-bottom: 15px; border-radius: 5px; background: #f9f9f9; }}
            .job-title {{ font-size: 16px; font-weight: bold; color: #2c3e50; margin: 0 0 5px 0; }}
            .company {{ color: #667eea; font-size: 14px; font-weight: bold; }}
            .match-score {{ display: inline-block; background: #4caf50; color: white; padding: 4px 8px; border-radius: 3px; font-weight: bold; font-size: 12px; margin: 10px 0; }}
            .apply-btn {{ display: inline-block; background: #667eea; color: white; padding: 8px 15px; text-decoration: none; border-radius: 4px; margin-top: 10px; font-size: 13px; }}
            .footer {{ text-align: center; color: #999; font-size: 12px; margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2 style="margin:0;">🎯 Your AI Recruiter Report</h2>
                <p style="margin:5px 0 0 0;">Found {len(jobs)} high-match jobs for you today!</p>
                <p style="font-size:12px; margin:5px 0 0 0;">{datetime.now().strftime('%B %d, %Y')}</p>
            </div>
    """

    for idx, job in enumerate(jobs, 1):
        score = job.get('match_score', 0)
        html += f"""
        <div class="job-card">
            <p class="job-title">#{idx}. {job['title']}</p>
            <p class="company">{job['company']} • {job['location']}</p>
            <p><span class="match-score">{int(score)}% Match</span></p>
            <p style="font-size:13px;"><strong>Why it matches:</strong> {job.get('why', 'N/A')}</p>
            <a href="{job['url']}" class="apply-btn">→ View & Apply</a>
        </div>
        """

    html += """
            <div class="footer">
                <p>Your AI Recruiter works 24/7 to find you the best remote opportunities.</p>
                <p>Next report: Tomorrow morning at 9:00 AM IST</p>
            </div>
        </div>
    </body>
    </html>
    """

    msg.attach(MIMEText(html, 'html'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_APP_PASSWORD)
        server.send_message(msg)
        server.quit()
        print(f"  ✅ Email sent to {user_email}")
    except Exception as e:
        print(f"  ❌ Failed to send email to {user_email}: {e}")

# ==========================================
# MAIN WORKFLOW
# ==========================================
def process_all_users():
    """Main workflow: fetch jobs, evaluate, and send emails."""

    # Connect to database
    try:
        engine = get_engine()
        init_db(engine)
        print("✅ Database connected")
    except Exception as e:
        print(f"❌ Database error: {e}")
        return

    with engine.connect() as conn:

        # Get all registered users
        result = conn.execute(text("SELECT email, profile_text FROM users ORDER BY created_at DESC"))
        users = result.fetchall()

        if not users:
            print("\n⚠️ No users registered yet. Exiting.")
            return

        print(f"\n👥 Found {len(users)} registered user(s)")

        # Fetch fresh jobs from the internet
        all_jobs = fetch_jobs()

        if not all_jobs:
            print("❌ No jobs found. Exiting.")
            return

        # Process each user individually
        for user_email, user_profile in users:
            print(f"\n📧 Processing: {user_email}")
            matched_jobs = []

            for job in all_jobs:

                # Skip if already sent to this user
                if is_job_sent(conn, user_email, job['id']):
                    continue

                # Evaluate with Claude
                eval_result = evaluate_job(job, user_profile)
                score = eval_result.get("match_score", 0)

                if score >= 80:
                    job['match_score'] = score
                    job['why'] = eval_result.get('why', '')
                    matched_jobs.append(job)

                    # Record in database
                    record_job_sent(conn, user_email, job['id'], job['title'], job['company'])
                    print(f"    ✅ Match ({score}%): {job['title']} @ {job['company']}")
                else:
                    print(f"    ⏭️  Skip ({score}%): {job['title']}")

            # Send email
            if matched_jobs:
                send_email(user_email, matched_jobs)
            else:
                print(f"    ℹ️  No high-match jobs for {user_email} today")

    print("\n" + "=" * 60)
    print("✅ WORKFLOW COMPLETE")
    print("=" * 60)

# ==========================================
# RUN
# ==========================================
if __name__ == "__main__":
    process_all_users()

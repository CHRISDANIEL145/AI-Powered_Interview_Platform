import os
import json
import uuid
import re
from datetime import datetime
from io import BytesIO

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

import google.generativeai as genai
from PyPDF2 import PdfReader

try:
    from docx import Document as DocxDocument
    DOCX_AVAILABLE = True
except Exception:
    DOCX_AVAILABLE = False

# --------------------------------------------------------------------------------------
# Robust Flask Configuration for your Project Structure
# --------------------------------------------------------------------------------------

# Get the absolute path to the project's root directory (one level up from this file)
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# Define the path to your frontend's 'public' directory
frontend_public_path = os.path.join(project_root, 'frontend', 'public')

# Configure Flask to serve static files from the frontend's public folder
app = Flask(__name__, static_folder=frontend_public_path, static_url_path='')

CORS(app)

# --------------------------------------------------------------------------------------
# Gemini Configuration
# --------------------------------------------------------------------------------------
load_dotenv()

API_KEY = (
    os.getenv("GEMINI_API_KEY")
    or os.getenv("GOOGLE_API_KEY")
)

if not API_KEY or API_KEY.strip() == "":
    raise ValueError(
        "No Gemini API key found. Set GOOGLE_API_KEY or GEMINI_API_KEY "
        "in your environment or .env file."
    )

genai.configure(api_key=API_KEY)
print("✅ Gemini configured (key from {}{})".format(
    "GEMINI_API_KEY" if os.getenv("GEMINI_API_KEY") else "GOOGLE_API_KEY",
    ""
))

# --------------------------------------------------------------------------------------
# In-memory session state
# --------------------------------------------------------------------------------------
sessions = {}

def get_or_create_session(session_id):
    if session_id not in sessions:
        sessions[session_id] = {
            "candidate_profile": None,
            "interview_questions": [],
            "interview_responses": [],
            "interview_start_time": None,
            "interview_end_time": None,
        }
    return sessions[session_id]

# --------------------------------------------------------------------------------------
# Models
# --------------------------------------------------------------------------------------
try:
    resume_analyzer_model = genai.GenerativeModel("gemini-1.5-flash")
    question_generator_model = genai.GenerativeModel("gemini-1.5-flash")
    response_evaluator_model = genai.GenerativeModel("gemini-1.5-flash")
    assessment_generator_model = genai.GenerativeModel("gemini-1.5-flash")
    print("✅ Gemini models loaded successfully.")
except Exception as e:
    print(f"❌ Error loading Gemini models: {e}")

# --------------------------------------------------------------------------------------
# Utilities: File Extraction & Gemini API Calls
# --------------------------------------------------------------------------------------
def extract_text_from_pdf(file_obj) -> str:
    text = ""
    try:
        reader = PdfReader(file_obj)
        for page in reader.pages:
            text += page.extract_text() or ""
    except Exception as e:
        print(f"Error extracting text from PDF: {e}")
    return text.strip()

def extract_text_from_docx(file_obj) -> str:
    if not DOCX_AVAILABLE:
        return ""
    try:
        if not isinstance(file_obj, BytesIO):
            file_bytes = file_obj.read()
            file_obj = BytesIO(file_bytes)
        doc = DocxDocument(file_obj)
        paras = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
        return "\n".join(paras).strip()
    except Exception as e:
        print(f"Error extracting text from DOCX: {e}")
        return ""

def extract_text_smart(uploaded_file) -> str:
    filename = (uploaded_file.filename or "").lower()
    if filename.endswith(".pdf"):
        return extract_text_from_pdf(uploaded_file)
    if filename.endswith(".docx"):
        return extract_text_from_docx(uploaded_file)
    raise ValueError("Unsupported file type. Please upload a PDF or DOCX.")

def generate_content_with_gemini(model, prompt: str, retries=3, **kwargs):
    attempt = 0
    while attempt < retries:
        try:
            safety_settings = [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ]
            generation_config = {"response_mime_type": "application/json"}
            print(f"DEBUG: Calling Gemini API (Attempt {attempt + 1}/{retries})...")
            resp = model.generate_content(
                prompt,
                safety_settings=safety_settings,
                generation_config=generation_config,
                **kwargs
            )
            if resp and getattr(resp, "text", None):
                json.loads(resp.text)
                print("DEBUG: Successfully received and parsed JSON from Gemini.")
                return resp.text
            print(f"DEBUG: Empty Gemini response (Attempt {attempt + 1}/{retries}).")
            attempt += 1
        except Exception as e:
            print(f"DEBUG: Error on attempt {attempt + 1}/{retries}: {e}")
            attempt += 1
            if attempt >= retries:
                print("DEBUG: Max retries reached. Returning None.")
                return None
    return None

def extract_json_from_gemini_response(text: str):
    if not text:
        return None
    m = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return text.strip()

# --------------------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------------------
@app.route("/")
def serve_index():
    return app.send_static_file('index.html')

@app.route("/upload_resume", methods=["POST"])
def upload_resume():
    session_id = request.headers.get("X-User-Session-Id", str(uuid.uuid4()))
    session = get_or_create_session(session_id)
    if "resume" not in request.files:
        return jsonify({"error": "No resume file provided"}), 400
    file = request.files["resume"]
    if not file or file.filename == "":
        return jsonify({"error": "No selected file"}), 400
    try:
        resume_content = extract_text_smart(file)
    except ValueError as ext_err:
        return jsonify({"error": str(ext_err)}), 400
    except Exception as e:
        print(f"DEBUG: extraction error: {e}")
        return jsonify({"error": "Failed to read the file. Try a PDF or DOCX."}), 400
    if not resume_content:
        return jsonify({"error": "Could not extract text. Ensure the PDF/DOCX contains selectable text."}), 400
    prompt = f"""
Analyze the following resume text and extract the candidate's name, email, total years of
experience (e.g., "5 years"), a list of key skills, and an inferred primary job role.

Return **only JSON** with keys:
- name (string)
- email (string)
- experience (string)
- key_skills (array of strings)
- inferred_position (string)

Resume Text:
---
{resume_content}
---
"""
    try:
        ai_text = generate_content_with_gemini(resume_analyzer_model, prompt)
        if not ai_text:
            return jsonify({"error": "AI failed to parse resume or returned empty response."}), 500
        cleaned = extract_json_from_gemini_response(ai_text)
        if not cleaned:
            raise ValueError("Failed to extract JSON from Gemini response for resume analysis.")
        profile = json.loads(cleaned)
        ks = profile.get("key_skills")
        if isinstance(ks, str):
            profile["key_skills"] = [s.strip() for s in ks.split(",") if s.strip()]
        elif not isinstance(ks, list):
            profile["key_skills"] = []
        session["candidate_profile"] = profile
        return jsonify({"message": "Resume processed successfully", "candidate_profile": profile, "session_id": session_id}), 200
    except Exception as e:
        print(f"DEBUG: Error in /upload_resume: {e}")
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

@app.route("/setup_interview", methods=["POST"])
def setup_interview():
    session_id = request.headers.get("X-User-Session-Id")
    if not session_id or session_id not in sessions:
        return jsonify({"error": "Invalid or missing session ID"}), 400
    session = sessions[session_id]
    data = request.get_json(silent=True) or {}
    position_role = data.get("position_role")
    if not position_role or not session.get("candidate_profile"):
        return jsonify({"error": "Position role and candidate profile are required"}), 400
    
    candidate_profile = session["candidate_profile"]
    session["candidate_profile"]["position"] = position_role
    skills = ", ".join(candidate_profile.get("key_skills", []))
    experience = candidate_profile.get("experience", "N/A")
    candidate_name = candidate_profile.get("name", "Candidate")
    
    prompt = f"""
Generate 15 interview questions for a candidate named {candidate_name}
applying for '{position_role}'. The candidate has {experience} and these skills: {skills}.

Include: 10 technical, 3 soft skills, and 2 communication questions.

Return **only a JSON array**. Each item must have: "id", "question", and "tags".
"""
    try:
        ai_text = generate_content_with_gemini(question_generator_model, prompt)
        if not ai_text:
            return jsonify({"error": "AI failed to generate questions."}), 500
        questions = json.loads(extract_json_from_gemini_response(ai_text))
        session["interview_questions"] = questions
        session["interview_responses"] = []
        session["interview_start_time"] = datetime.now().isoformat()
        return jsonify({"message": "Interview questions generated", "questions": questions}), 200
    except Exception as e:
        print(f"DEBUG: Error in /setup_interview: {e}")
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

@app.route("/submit_answer", methods=["POST"])
def submit_answer():
    session_id = request.headers.get("X-User-Session-Id")
    if not session_id or session_id not in sessions:
        return jsonify({"error": "Invalid or missing session ID"}), 400
    session = sessions[session_id]
    data = request.get_json(silent=True) or {}
    question_id = data.get("question_id")
    response_text = data.get("response_text")
    if not question_id or not response_text:
        return jsonify({"error": "Question ID and response text are required"}), 400
    question_obj = next((q for q in session["interview_questions"] if q.get("id") == question_id), None)
    if not question_obj:
        return jsonify({"error": "Question not found"}), 404
    
    prompt = f"""
Evaluate the candidate's response. Return **only JSON** with:
"technicalScore" (0-100), "communicationScore" (0-100), "relevanceScore" (0-100), "feedback" (string).

Question: "{question_obj.get('question')}"
Response: "{response_text}"
"""
    try:
        ai_text = generate_content_with_gemini(response_evaluator_model, prompt)
        if not ai_text:
            return jsonify({"error": "AI failed to evaluate response."}), 500
        evaluation = json.loads(extract_json_from_gemini_response(ai_text))
        overall_q_score = (evaluation.get("technicalScore", 0) + evaluation.get("communicationScore", 0) + evaluation.get("relevanceScore", 0)) / 3
        evaluation["score"] = round(overall_q_score)
        session["interview_responses"].append({
            "question_id": question_id, "question": question_obj.get("question"),
            "tags": question_obj.get("tags", []), "response": response_text,
            "duration": data.get("duration"), "evaluation": evaluation
        })
        return jsonify({"message": "Answer evaluated", "evaluation": evaluation}), 200
    except Exception as e:
        print(f"DEBUG: Error in /submit_answer: {e}")
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

@app.route("/get_assessment", methods=["GET"])
def get_assessment():
    session_id = request.headers.get("X-User-Session-Id")
    if not session_id or session_id not in sessions:
        return jsonify({"error": "Invalid or missing session ID"}), 400
    
    session = sessions[session_id]
    if not session["interview_responses"]:
        return jsonify({"error": "No interview responses to assess"}), 400
    
    session["interview_end_time"] = datetime.now().isoformat()
    interview_summary = []
    total_duration_seconds = 0
    for r in session["interview_responses"]:
        interview_summary.append(
            f'Q: {r["question"]}\nA: {r["response"]}\n'
            f'Eval: Tech: {r["evaluation"]["technicalScore"]}, Comm: {r["evaluation"]["communicationScore"]}, Rel: {r["evaluation"]["relevanceScore"]}.\n'
            f'Feedback: {r["evaluation"]["feedback"]}'
        )
        try:
            mm, ss = map(int, (r.get("duration") or "0:0").split(":"))
            total_duration_seconds += mm * 60 + ss
        except Exception: pass
    
    total_minutes = total_duration_seconds // 60
    total_seconds = total_duration_seconds % 60
    interview_duration_str = f"{total_minutes}m {total_seconds}s"
    
    # Pre-join the summary to avoid backslash in f-string expression
    interview_summary_text = "\n\n".join(interview_summary)
    
    prompt = f"""
Generate a comprehensive interview assessment based on the provided profile and Q&A summary.

Return **only JSON** with: "overallScore" (0-100), "recommendation" (string),
"interviewDuration" (string), "detailedScores" (object with "technicalSkills",
"communication", "softSkills"), "detailedQuestionAnalysis" (array of objects),
"keyStrengths" (array of strings), "areasForImprovement" (array of strings).

Profile: {json.dumps(session["candidate_profile"], indent=2)}
Interview Q&A:
---
{interview_summary_text}
---
"""
    try:
        ai_text = generate_content_with_gemini(assessment_generator_model, prompt)
        if not ai_text:
            return jsonify({"error": "AI failed to generate assessment."}), 500
        
        assessment = json.loads(extract_json_from_gemini_response(ai_text))
        assessment["interviewDuration"] = interview_duration_str
        session["interview_assessment"] = assessment
        
        return jsonify({"message": "Assessment generated", "assessment": assessment}), 200
    except Exception as e:
        print(f"DEBUG: Error in /get_assessment: {e}")
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5500))
    print(f"✅ Flask app running on http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, debug=True)
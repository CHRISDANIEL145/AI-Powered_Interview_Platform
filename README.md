# AI-Powered_Interview_Platform

<img width="203" height="260" alt="image" src="https://github.com/user-attachments/assets/e96d82fc-7532-4113-b69b-3c0e3f813555" />

backend/.env
      /app.py
      /requirements.txt


AI-Powered Interview Platform (IntervuAI Pro):
IntervuAI Pro is a sophisticated, end-to-end web application designed to automate and enhance the technical interview process using state-of-the-art AI. The platform streamlines the entire workflow, from initial resume screening to generating a final, comprehensive candidate assessment.

By leveraging the high-speed Groq AI cloud, the application provides real-time, intelligent analysis, helping hiring managers make faster, more informed, and less biased decisions.

Key Features & Workflow
Intelligent Resume Parsing: Users begin by uploading a candidate's resume (PDF). The backend uses PyPDF2 to extract the text and sends it to the gemma-7b-it model on Groq to instantly parse and understand the candidate's skills, experience, and inferred job role.

Dynamic & Tailored Question Generation: Based on the analyzed resume profile and a specific job title provided by the user, the AI generates a unique set of technical, soft-skill, and communication questions tailored to the candidate and the role.

Real-time Answer Evaluation: As the candidate submits answers to each question, the application sends the question-and-answer pair to the AI for immediate evaluation. The AI returns a detailed breakdown, including scores for technical accuracy, communication clarity, and relevance.

Comprehensive Final Assessment: Once the interview is complete, the backend compiles the entire session—candidate profile, all questions, answers, and individual evaluations—and sends it to the Groq AI for a final, holistic analysis.

Actionable Reporting: The AI generates a detailed final report that includes an overall score, a hiring recommendation (e.g., "Highly Recommended"), key strengths, areas for improvement, and a question-by-question breakdown. This report can be viewed on the platform and exported as a PDF.

Technology Stack
Frontend: A clean, single-page application built with HTML, Tailwind CSS, and vanilla JavaScript.

Backend: A robust server built with Flask (Python).

AI Engine: Powered by the Groq API for ultra-low-latency responses from the gemma-7b-it large language model.

Core Libraries: PyPDF2 for PDF text extraction and jsPDF for client-side report generation.

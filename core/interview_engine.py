import json
import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

# Use the latest flash model for fast conversational responses
MODEL_NAME = 'gemini-3.8-flash' 
USE_MOCK_DATA = False

def get_category_prompt(category):
    prompts = {
        "technical": "Focus strictly on technical skills, frameworks, architecture, and past project implementations.",
        "dsa": "Focus strictly on Data Structures, Algorithms, time/space complexity, and problem-solving logic.",
        "subjective": "Focus on core theoretical knowledge, industry standards, and situational awareness in their field.",
        "personality": "Focus strictly on behavioral questions, culture fit, conflict resolution, and leadership (e.g., STAR method).",
        "mixed": "Provide a balanced mix of technical, behavioral, and problem-solving questions."
    }
    return prompts.get(category, prompts["mixed"])

def generate_interview_questions(resume_text, job_description, num_questions=5, category="mixed"):
    """Mode 1: Generates a static list of questions based on a specific category."""
    if USE_MOCK_DATA:
        return [{"question": f"Sample {category} question?", "advice": "Sample advice"}] * num_questions

    category_focus = get_category_prompt(category)

    prompt = f"""
    You are an expert technical recruiter. Compare the candidate's resume to the target Job Description. 
    Generate exactly {num_questions} mock interview questions tailored to their experience.
    
    CRITICAL INSTRUCTION: {category_focus}
    
    The output MUST be a valid JSON array of objects following this structure:
    {{
        "question": "The specific interview question",
        "advice": "Brief advice on how the candidate should answer"
    }}

    Job Description: {job_description[:3000]}
    Candidate Resume: {resume_text[:5000]}
    """

    try:
        model = genai.GenerativeModel(MODEL_NAME) 
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(response_mime_type="application/json")
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"Error generating list: {e}")
        return None

def start_interactive_session(resume_text, job_description, category="mixed"):
    """Mode 2 (Init): Generates the opening question and system prompt for the chat."""
    category_focus = get_category_prompt(category)
    
    system_instruction = f"""
    You are an expert interviewer conducting a live, one-on-one interview.
    CRITICAL INSTRUCTION: {category_focus}
    
    Context:
    Job Description: {job_description[:2000]}
    Candidate Resume: {resume_text[:3000]}
    
    Rules:
    1. Ask ONLY ONE question at a time.
    2. Wait for the candidate's response before asking the next question.
    3. If their answer is weak, gently guide them or ask a follow-up probing question.
    4. Maintain a professional, conversational tone.
    """
    
    try:
        model = genai.GenerativeModel(MODEL_NAME, system_instruction=system_instruction)
        chat = model.start_chat(history=[])
        response = chat.send_message("Introduce yourself briefly as the AI interviewer and ask your first question based on my resume.")
        
        # We return the initial history so it can be saved in the database
        history = [
            {"role": "user", "parts": ["Introduce yourself briefly as the AI interviewer and ask your first question based on my resume."]},
            {"role": "model", "parts": [response.text]}
        ]
        return response.text, history, system_instruction
    except Exception as e:
        print(f"Error starting chat: {e}")
        return None, None, None

def continue_interactive_session(system_instruction, history_data, user_message):
    """Mode 2 (Ongoing): Rebuilds the chat from DB history and gets the next response."""
    try:
        model = genai.GenerativeModel(MODEL_NAME, system_instruction=system_instruction)
        
        # Reconstruct the history format required by the Gemini SDK
        formatted_history = []
        for msg in history_data:
            formatted_history.append({
                "role": msg["role"],
                "parts": msg["parts"]
            })
            
        chat = model.start_chat(history=formatted_history)
        response = chat.send_message(user_message)
        
        # Append the new interaction to the history
        history_data.append({"role": "user", "parts": [user_message]})
        history_data.append({"role": "model", "parts": [response.text]})
        
        return response.text, history_data
    except Exception as e:
        print(f"Error continuing chat: {e}")
        return None, None
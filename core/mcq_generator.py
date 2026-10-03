import json
import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

def generate_mcqs(text, num_questions):
    max_chars = 15000 
    truncated_text = text[:max_chars]

    prompt = f"""
    You are an expert educational evaluator. Based ONLY on the following text, generate a multiple-choice test consisting of exactly {num_questions} questions. 
    
    The output MUST be a valid JSON array of objects. 
    Each object must strictly follow this structure:
    {{
        "question": "The question text",
        "options": ["Option A", "Option B", "Option C", "Option D"],
        "correct_answer": "The exact string of the correct option",
        "explanation": "A brief explanation of why the answer is correct based on the text"
    }}

    Text to evaluate:
    {truncated_text}
    """

    try:
        # Updated to the latest stable Flash model
        model = genai.GenerativeModel('gemini-3.8-flash')
        
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json"
            )
        )
        
        questions_list = json.loads(response.text)
        return questions_list

    except Exception as e:
        print(f"Error generating MCQs with Gemini: {e}")
        return None
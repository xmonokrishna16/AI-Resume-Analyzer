import spacy
import re

# Load the English NLP model
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    import spacy.cli
    spacy.cli.download("en_core_web_sm")
    nlp = spacy.load("en_core_web_sm")

TECH_SKILLS = {
    'c', 'c++', 'python', 'javascript', 'html', 'css', 'java', 'sql',
    'flask', 'mysql', 'sqlite', 'react', 'node.js', 'django', 'api',
    'canva', 'capcut', 'git', 'github', 'aws', 'docker',
    'data structures', 'algorithms', 'cybersecurity'
}

# Standard academic keywords
EDUCATION_KEYWORDS = {
    'b.tech', 'btech', 'bsc', 'b.sc', 'bachelor', 'master', 
    'm.tech', 'msc', 'phd', 'diploma', 'computer science', 
    'information technology', 'engineering'
}

def extract_skills(text):
    """Extracts technical skills."""
    if not text:
        return []
    doc = nlp(text.lower())
    extracted = set()
    for token in doc:
        if token.text in TECH_SKILLS:
            extracted.add(token.text)
    for chunk in doc.noun_chunks:
        chunk_text = chunk.text.strip()
        if chunk_text in TECH_SKILLS:
            extracted.add(chunk_text)
    return list(extracted)

def extract_education(text):
    """Identifies education degrees and majors."""
    if not text:
        return []
    
    extracted_edu = set()
    text_lower = text.lower()
    
    # 1. Regex for common formatting (e.g., B.Tech, M.Sc)
    if re.search(r'\bb\.?tech\b', text_lower):
        extracted_edu.add('B.Tech')
    if re.search(r'\bcomputer science\b', text_lower):
        extracted_edu.add('Computer Science')
        
    # 2. SpaCy token matching for other keywords
    doc = nlp(text_lower)
    for token in doc:
        if token.text in EDUCATION_KEYWORDS and token.text not in ['b.tech', 'btech', 'computer science']:
            extracted_edu.add(token.text.title())
            
    return list(extracted_edu)

def extract_experience(text):
    """Extracts years of experience using Regex patterns."""
    if not text:
        return "Not Specified"
    
    # Looks for patterns like "3 years of experience" or "5+ yrs experience"
    pattern = r'(\d+)\+?\s*(years?|yrs?)\s*(of\s*)?experience'
    match = re.search(pattern, text.lower())
    
    if match:
        return f"{match.group(1)} Years"
    
    return "Entry Level / Not Specified"
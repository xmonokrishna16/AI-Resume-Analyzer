import spacy

# Load the English NLP model. If it's missing, download it automatically.
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    import spacy.cli
    print("Downloading spaCy language model...")
    spacy.cli.download("en_core_web_sm")
    nlp = spacy.load("en_core_web_sm")

# A baseline knowledge dictionary of technical skills. 
# We include specific ones from your resume to test the extraction.
TECH_SKILLS = {
    'c', 'c++', 'python', 'javascript', 'html', 'css', 'java', 'sql',
    'flask', 'mysql', 'sqlite', 'react', 'node.js', 'django', 'api',
    'canva', 'capcut', 'git', 'github', 'aws', 'docker',
    'data structures', 'algorithms', 'cybersecurity'
}

def extract_skills(text):
    """
    Uses NLP to find technical skills inside a raw block of text.
    """
    if not text:
        return []

    doc = nlp(text.lower())
    extracted = set()

    # 1. Check individual word tokens against our database
    for token in doc:
        if token.text in TECH_SKILLS:
            extracted.add(token.text)

    # 2. Check multi-word phrases (e.g., "data structures")
    for chunk in doc.noun_chunks:
        chunk_text = chunk.text.strip()
        if chunk_text in TECH_SKILLS:
            extracted.add(chunk_text)

    return list(extracted)

# --- Quick Test Block ---
if __name__ == "__main__":
    # We will use a snippet from your actual parser output to test it!
    sample_parsed_text = "skills demonstratingcoresoftwaredesignandsecurityprinciplesforproduction readiness. certification aiforall awards languagesandframework c c++ python javascript flask html css toolsandsoftware mysql sqlite datavisualizationtools canva capcut hardskills softwaredesign end to endsystemdeployment"

    print("Analyzing text with AI...")
    found_skills = extract_skills(sample_parsed_text)
    
    print("\n--- EXTRACTED SKILLS ---")
    for skill in found_skills:
        print(f"✅ {skill}")
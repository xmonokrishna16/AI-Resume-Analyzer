import pdfplumber
import docx
import re
import os

def extract_text_from_pdf(file_path):
    """Extracts text from a PDF file."""
    text = ""
    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return clean_text(text)
    except Exception as e:
        print(f"Error reading PDF: {e}")
        return ""

def extract_text_from_docx(file_path):
    """Extracts text from a Word document (.docx)."""
    try:
        doc = docx.Document(file_path)
        text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
        return clean_text(text)
    except Exception as e:
        print(f"Error reading DOCX: {e}")
        return ""

def clean_text(raw_text):
    """
    Cleans the raw text to improve NLP accuracy.
    Removes special characters but keeps +, #, and . for skills like C++, C#, Node.js
    """
    if not raw_text:
        return ""
    
    # 1. Replace non-alphanumeric characters with a space (keep essential tech symbols)
    cleaned_text = re.sub(r'[^a-zA-Z0-9\s\.\+#]', ' ', raw_text)
    
    # 2. Replace multiple spaces or newlines with a single space
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
    
    # 3. Convert everything to lowercase for uniform matching
    return cleaned_text.lower()

# --- Quick Test Block ---
if __name__ == "__main__":
    test_file = "test_resume.pdf" # We will put a fake resume here to test
    
    if os.path.exists(test_file):
        print("Extracting text...\n")
        extracted = extract_text_from_pdf(test_file)
        print("--- CLEANED TEXT OUTPUT ---")
        print(extracted)
    else:
        print(f"⚠️ Please place a file named '{test_file}' in the root folder to test.")
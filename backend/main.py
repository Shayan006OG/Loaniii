import re
import pytesseract
from PIL import Image
import cv2
import tempfile
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
import logging
from datetime import datetime

# Path to tesseract executable
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

app = FastAPI()

# Allow frontend requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Strict Regex patterns
aadhaar_pattern = re.compile(r"^\d{4}\s\d{4}\s\d{4}$")   # Aadhaar strictly "XXXX XXXX XXXX"
pan_pattern = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")     # PAN strictly "ABCDE1234F"
apaar_pattern = re.compile(r"^\d{12}$")                  # APAAR strictly "123456789012"

# Enhanced patterns for APAAR document details extraction
name_patterns = [
    re.compile(r"(?:name|full name|नाम|फुल नेम)[:;\s]*([a-zA-Z\s]+)", re.IGNORECASE),
    re.compile(r"^([A-Z][a-z]+\s[A-Z][a-z]+)$"),  # First Last format
    re.compile(r"^([A-Z][a-z]+\s[A-Z][a-z]+\s[A-Z][a-z]+)$"),  # First Middle Last format
]

# Date of birth patterns (instead of age)
dob_patterns = [
    re.compile(r"(?:date of birth|dob|जन्म तिथि|जन्म की तारीख)[:;\s]*([0-9]{1,2}[/\-\.][0-9]{1,2}[/\-\.][0-9]{4})", re.IGNORECASE),
    re.compile(r"(?:dob|जन्म)[:;\s]*([0-9]{1,2}[/\-\.][0-9]{1,2}[/\-\.][0-9]{4})", re.IGNORECASE),
    re.compile(r"\b([0-9]{1,2}[/\-\.][0-9]{1,2}[/\-\.][0-9]{4})\b"),
    re.compile(r"\b([0-9]{4}[/\-\.][0-9]{1,2}[/\-\.][0-9]{1,2})\b"),  # YYYY-MM-DD format
]

gender_patterns = [
    re.compile(r"(?:gender|लिंग|जेंडर)[:;\s]*(male|female|transgender|m|f|t|पुरुष|महिला|स्त्री|ट्रांसजेंडर)", re.IGNORECASE),
    re.compile(r"\b(male|female|transgender|m|f|t)\b", re.IGNORECASE),
]

def format_date_to_dd_mm_yyyy(date_str):
    """Convert various date formats to DD/MM/YYYY format"""
    date_formats = [
        '%d/%m/%Y', '%d-%m-%Y', '%d.%m.%Y',
        '%m/%d/%Y', '%m-%d-%Y', '%m.%d.%Y',
        '%Y/%m/%d', '%Y-%m-%d', '%Y.%m.%d',
        '%d/%m/%y', '%d-%m-%y', '%d.%m.%y',  # 2-digit year
    ]
    
    for fmt in date_formats:
        try:
            date_obj = datetime.strptime(date_str, fmt)
            # Convert to DD/MM/YYYY format with leading zeros
            return date_obj.strftime('%d/%m/%Y')
        except ValueError:
            continue
    
    # If we can't parse it, try to extract components manually
    parts = re.split(r'[/\-\.]', date_str)
    if len(parts) == 3:
        day, month, year = parts
        
        # Ensure year is 4 digits
        if len(year) == 2:
            year = f"20{year}"  # Assuming 21st century
        
        # Ensure day and month are 2 digits
        day = day.zfill(2)
        month = month.zfill(2)
        
        # Validate the date components
        try:
            datetime.strptime(f"{day}/{month}/{year}", '%d/%m/%Y')
            return f"{day}/{month}/{year}"
        except ValueError:
            pass
    
    return date_str  # Return as-is if cannot parse

def extract_apaar_details(text):
    """Enhanced function to extract details from APAAR document text"""
    details = {}
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    # Try to extract name using multiple patterns
    for pattern in name_patterns:
        name_match = pattern.search(text)
        if name_match:
            potential_name = name_match.group(1).strip()
            # Basic validation - name should have at least two words and reasonable length
            if len(potential_name.split()) >= 2 and 4 <= len(potential_name) <= 50:
                details['name'] = potential_name
                break
    
    # If no name found with patterns, try line-by-line analysis for APAAR
    if 'name' not in details:
        for i, line in enumerate(lines):
            # Look for lines that might contain a name (mixed case, reasonable length)
            if (any(keyword in line.lower() for keyword in ['name', 'नाम']) or 
                (60 > len(line) > 8 and re.match(r'^[A-Za-z\s]+$', line) and 
                 sum(1 for c in line if c.isupper()) >= 2)):
                details['name'] = line
                break
    
    # Try to extract date of birth (instead of age)
    for pattern in dob_patterns:
        dob_match = pattern.search(text)
        if dob_match:
            dob_str = dob_match.group(1).strip()
            details['dob'] = format_date_to_dd_mm_yyyy(dob_str)
            break
    
    # If no DOB found with patterns, look for date-like patterns in the text
    if 'dob' not in details:
        # Look for common date formats with 4-digit year
        date_matches = re.findall(r'\b(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{4})\b', text)
        for date_str in date_matches:
            # Simple validation - check if it looks like a date
            if any(sep in date_str for sep in ['/', '-', '.']):
                details['dob'] = format_date_to_dd_mm_yyyy(date_str)
                break
    
    # Try to extract gender
    for pattern in gender_patterns:
        gender_match = pattern.search(text)
        if gender_match:
            gender = gender_match.group(1).lower()
            if gender in ['male', 'm', 'पुरुष']:
                details['gender'] = 'Male'
            elif gender in ['female', 'f', 'महिला', 'स्त्री']:
                details['gender'] = 'Female'
            else:
                details['gender'] = 'Other'
            break
    
    # If no gender found with patterns, look for gender keywords in context
    if 'gender' not in details:
        for i, line in enumerate(lines):
            lower_line = line.lower()
            if any(keyword in lower_line for keyword in ['male', 'female', 'transgender', 'पुरुष', 'महिला']):
                if 'male' in lower_line or 'पुरुष' in lower_line:
                    details['gender'] = 'Male'
                elif 'female' in lower_line or 'महिला' in lower_line or 'स्त्री' in lower_line:
                    details['gender'] = 'Female'
                break
    
    return details

def extract_aadhaar_details(text):
    """Extract only name, DOB and gender from Aadhaar card text"""
    details = {}
    
    # Try to extract name
    for pattern in name_patterns:
        name_match = pattern.search(text)
        if name_match:
            details['name'] = name_match.group(1).strip()
            break
    
    # Try to extract date of birth
    for pattern in dob_patterns:
        dob_match = pattern.search(text)
        if dob_match:
            dob_str = dob_match.group(1).strip()
            details['dob'] = format_date_to_dd_mm_yyyy(dob_str)
            break
    
    # Try to extract gender
    for pattern in gender_patterns:
        gender_match = pattern.search(text)
        if gender_match:
            gender = gender_match.group(1).lower()
            if gender in ['male', 'm', 'पुरुष']:
                details['gender'] = 'Male'
            elif gender in ['female', 'f', 'महिला', 'स्त्री']:
                details['gender'] = 'Female'
            else:
                details['gender'] = 'Other'
            break
    
    return details

def extract_details(text, doc_type):
    """Extract details from document text based on document type"""
    if doc_type.lower() == "apaar":
        return extract_apaar_details(text)
    elif doc_type.lower() == "aadhaar":
        return extract_aadhaar_details(text)
    elif doc_type.lower() == "pan":
        # Return empty details for PAN cards
        return {}
    
    # For unknown document types, return empty details
    return {}

@app.post("/verify")
async def verify_document(file: UploadFile = File(...), doc_type: str = Form(...), user_input: str = Form(...)):
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        # Preprocess image for better OCR
        img = cv2.imread(tmp_path)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Apply additional preprocessing for better OCR results
        # 1. Noise reduction
        denoised = cv2.fastNlMeansDenoising(gray)
        
        # 2. Thresholding to get binary image
        _, thresh = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # 3. Morphological operations to remove noise
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        morph = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
        
        # Extract text from preprocessed image
        text = pytesseract.image_to_string(morph)
        
        logging.info(f"OCR Text Extracted:\n{text}")
        
        # Extract only potential ID candidates (lines without extra text)
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        
        # Extract details from the document based on type
        details = extract_details(text, doc_type)
        
        # Aadhaar Verification
        if doc_type.lower() == "aadhaar":
            for line in lines:
                # Remove spaces for comparison with user input
                clean_line = line.replace(" ", "")
                clean_user_input = user_input.replace(" ", "")
                
                if aadhaar_pattern.match(line) and clean_line == clean_user_input:
                    return {
                        "status": "Verified", 
                        "feedback": f"Valid Aadhaar detected: {line}",
                        "details": details
                    }
            return {"status": "Rejected", "feedback": "No valid Aadhaar number detected or mismatch with input"}

        # PAN Verification
        elif doc_type.lower() == "pan":
            for line in lines:
                if pan_pattern.match(line) and line == user_input:
                    return {
                        "status": "Verified", 
                        "feedback": f"Valid PAN detected: {line}",
                        "details": details  # Will be empty for PAN cards
                    }
            return {"status": "Rejected", "feedback": "No valid PAN number detected or mismatch with input"}

        # APAAR Verification
        elif doc_type.lower() == "apaar":
            for line in lines:
                # Remove any non-digit characters for APAAR
                digits_only = re.sub(r'\D', '', line)
                if apaar_pattern.match(digits_only) and digits_only == user_input:
                    return {
                        "status": "Verified", 
                        "feedback": f"Valid APAAR ID detected: {digits_only}",
                        "details": details
                    }
            return {"status": "Rejected", "feedback": "No valid APAAR ID detected or mismatch with input"}

        else:
            return {"status": "Rejected", "feedback": "Unknown document type"}

    except Exception as e:
        logging.error(f"Error verifying document: {e}")
        return {"status": "Rejected", "feedback": f"Server error: {str(e)}"}
import re


def normalize_serial(raw_serial):
    """
    Normalize serial number:
    1. Trim whitespace
    2. Convert to uppercase
    3. Strip trailing punctuation (. , ; :) and whitespace
    """
    if not raw_serial:
        return ''
    
    # Trim
    normalized = raw_serial.strip()
    
    # Uppercase
    normalized = normalized.upper()
    
    # Strip trailing punctuation and whitespace
    normalized = re.sub(r'[\s.,;:]+$', '', normalized)
    
    return normalized


def validate_shred_row(payload):
    """
    Validate shred log row and return list of validation errors.
    Returns empty list if valid.
    """
    errors = []
    
    # Check for missing serial
    serial = payload.get('Serial Number') or payload.get('serial_number') or payload.get('Serial') or ''
    if not serial.strip():
        errors.append('Missing serial number')
    
    # Add more validation rules as needed
    
    return errors


def validate_removal_row(payload):
    """
    Validate drive removal row and return list of validation errors.
    Returns empty list if valid.
    """
    errors = []
    
    # Check for missing drive serial
    drive_serial = (payload.get('Drive Serial Number') or 
                   payload.get('drive_serial') or 
                   payload.get('Drive Serial') or '')
    if not drive_serial.strip():
        errors.append('Missing drive serial number')
    
    # Check if computer serial looks like a URL
    computer_serial = (payload.get('Computer Serial Number') or 
                      payload.get('computer_serial') or 
                      payload.get('Computer Serial') or '')
    if computer_serial and ('http://' in computer_serial.lower() or 
                           'https://' in computer_serial.lower() or
                           'www.' in computer_serial.lower()):
        errors.append('Computer serial appears to be a URL')
    
    return errors

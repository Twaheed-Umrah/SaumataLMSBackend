import base64
import os
from pathlib import Path
from django.conf import settings

def get_logo_base64():
    """
    PRODUCTION-READY: Get logo from media folder as base64
    Simple, reliable, works everywhere
    """
    # Primary path - media folder
    media_logo_path = settings.MEDIA_ROOT / 'hajjumrahlogo.png'
    
    # Check if logo exists in media
    if media_logo_path.exists():
        try:
            with open(media_logo_path, 'rb') as image_file:
                return base64.b64encode(image_file.read()).decode()
        except Exception as e:
            print(f"Error loading logo from media: {e}")
    
    # Secondary fallback - try templates folder
    templates_path = settings.BASE_DIR / 'templates' / 'images' / 'hajjumrahlogo.png'
    if templates_path.exists():
        try:
            with open(templates_path, 'rb') as image_file:
                return base64.b64encode(image_file.read()).decode()
        except Exception:
            pass
    
    # Final fallback - transparent pixel (never fails)
    return "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="


def get_signature_base64():
    """Load signature image from media folder"""
    signature_path = settings.MEDIA_ROOT / 'shuaibsirsignature-r.png'
    if signature_path.exists():
        try:
            with open(signature_path, 'rb') as image_file:
                return base64.b64encode(image_file.read()).decode()
        except Exception:
            pass
    return ""

def get_stamp_base64():
    """Load stamp image from media folder"""
    stamp_path = settings.MEDIA_ROOT / 'stampofhajjumrahlogo.png'
    if stamp_path.exists():
        try:
            with open(stamp_path, 'rb') as image_file:
                return base64.b64encode(image_file.read()).decode()
        except Exception:
            pass
    return ""

def get_company_context():
    """Returns all company info including images"""
    return {
        'logo_base64': get_logo_base64(),  # Your existing function
        'signature_base64': get_signature_base64(),
        'stamp_base64': get_stamp_base64(),
        'company_name': 'Hajj Umrah Service',
        'company_phone': '+91 92119 48377',
        'company_email': 'hajjumrahservice00@gmail.com',
        'company_website': 'www.hajumrahservice.com'
    }
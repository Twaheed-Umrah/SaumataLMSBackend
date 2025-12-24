import pandas as pd
from django.utils import timezone

def validate_excel_file(file):
    """
    Validate uploaded Excel file
    """
    try:
        # Read the Excel file
        df = pd.read_excel(file)
        
        # Convert column names to lowercase for easier matching
        columns_lower = [col.strip().lower() for col in df.columns]
        
        # Check for required columns (allow variations)
        required_mappings = {
            'name': ['name', 'full name', 'fullname', 'full_name', 'contact name'],
            'phone': ['phone', 'phone number', 'phonenumber', 'mobile', 'mobile number', 
                     'contact', 'contact number', 'phone_number']
        }
        
        found_columns = {}
        
        # Check for name column
        for name_variation in required_mappings['name']:
            if name_variation in columns_lower:
                found_columns['name'] = df.columns[columns_lower.index(name_variation)]
                break
        
        # Check for phone column
        for phone_variation in required_mappings['phone']:
            if phone_variation in columns_lower:
                found_columns['phone'] = df.columns[columns_lower.index(phone_variation)]
                break
        
        # If required columns not found, check if they exist with different casing
        if 'name' not in found_columns:
            for col in df.columns:
                if any(keyword in col.lower() for keyword in ['name', 'full']):
                    found_columns['name'] = col
                    break
        
        if 'phone' not in found_columns:
            for col in df.columns:
                if any(keyword in col.lower() for keyword in ['phone', 'mobile', 'contact', 'number']):
                    found_columns['phone'] = col
                    break
        
        # Final check
        if not found_columns.get('name'):
            return False, "Missing required column: name (or similar like 'Full name')"
        
        if not found_columns.get('phone'):
            return False, "Missing required column: phone (or similar like 'Phone number', 'Mobile')"
        
        # Check if file has data
        if df.empty:
            return False, "Excel file is empty"
        
        return True, found_columns
        
    except Exception as e:
        return False, f"Error reading file: {str(e)}"


def parse_excel_leads(file, column_mapping=None):
    """
    Parse Excel file and extract lead data
    """
    try:
        df = pd.read_excel(file)
        
        # Use provided mapping or auto-detect
        if column_mapping:
            mapping = column_mapping
        else:
            # Auto-detect columns
            is_valid, mapping_or_error = validate_excel_file(file)
            if not is_valid:
                return [], mapping_or_error
            mapping = mapping_or_error
        
        leads_data = []
        
        for index, row in df.iterrows():
            # Skip empty rows
            if pd.isna(row[mapping['name']]) and pd.isna(row[mapping['phone']]):
                continue
            
            # Clean phone number
            phone = str(row[mapping['phone']]) if not pd.isna(row[mapping['phone']]) else ''
            # Remove non-numeric characters and spaces
            phone = ''.join(filter(str.isdigit, phone))
            # Remove country code (91) if present
            if phone.startswith('91') and len(phone) == 12:
                phone = phone[2:]
            elif len(phone) > 10:
                phone = phone[-10:]  # Take last 10 digits
            
            lead_data = {
                'name': str(row[mapping['name']]) if not pd.isna(row[mapping['name']]) else '',
                'phone': phone,
                'email': str(row.get(mapping.get('email', ''), '')) if mapping.get('email') and not pd.isna(row.get(mapping['email'], '')) else '',
                'company': str(row.get(mapping.get('company', ''), '')) if mapping.get('company') and not pd.isna(row.get(mapping['company'], '')) else '',
                'city': str(row.get(mapping.get('city', ''), '')) if mapping.get('city') and not pd.isna(row.get(mapping['city'], '')) else '',
                'state': str(row.get(mapping.get('state', ''), '')) if mapping.get('state') and not pd.isna(row.get(mapping['state'], '')) else '',
                'notes': ''
            }
            
            # Only add if we have at least name and phone
            if lead_data['name'].strip() and lead_data['phone'].strip():
                leads_data.append(lead_data)
        
        return leads_data, None
        
    except Exception as e:
        return [], f"Error parsing Excel file: {str(e)}"
    
def create_sample_excel():
    """
    Create a sample Excel template for lead upload
    """
    sample_data = {
        'name': ['John Doe', 'Jane Smith'],
        'email': ['john@example.com', 'jane@example.com'],
        'phone': ['9876543210', '9876543211'],
        'company': ['ABC Corp', 'XYZ Ltd'],
        'city': ['Delhi', 'Mumbai'],
        'state': ['Delhi', 'Maharashtra'],
        'notes': ['Interested in franchise', 'Looking for package']
    }
    
    df = pd.DataFrame(sample_data)
    return df
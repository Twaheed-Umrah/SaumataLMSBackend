from django.db import transaction
from django.utils import timezone
from apps.accounts.models import User
from .models import Lead, LeadActivity
from utils.constants import UserRole, LeadType, LeadStatus
from utils.excel import parse_excel_leads


class LeadDistributionService:
    @staticmethod
    def get_callers_by_type(lead_type):
        """
        Get active callers based on lead type
        """
        if lead_type == LeadType.FRANCHISE:
            role = UserRole.FRANCHISE_CALLER
        elif lead_type == LeadType.PACKAGE:
            role = UserRole.PACKAGE_CALLER
        else:
            role = UserRole.FRANCHISE_CALLER
        
        return User.objects.filter(role=role, is_active=True).order_by('id')
    @staticmethod
    def distribute_leads(leads_data, lead_type, uploaded_by, column_mapping=None):
        """
        Distribute leads equally among callers
        """
        callers = LeadDistributionService.get_callers_by_type(lead_type)
        
        if not callers.exists():
            return None, f"No active {lead_type} callers found"
        
        # Create leads and distribute
        created_leads = []
        caller_index = 0
        total_callers = callers.count()
        
        with transaction.atomic():
            for lead_data in leads_data:
                # Validate required fields
                if not lead_data.get('name') or not lead_data.get('phone'):
                    continue  # Skip invalid leads
                
                # Clean phone number
                phone = lead_data['phone']
                if not phone:
                    continue
                
                # Remove non-numeric characters
                phone = ''.join(filter(str.isdigit, phone))
                
                # Remove country code if present
                if phone.startswith('91') and len(phone) == 12:
                    phone = phone[2:]
                elif len(phone) > 10:
                    phone = phone[-10:]  # Take last 10 digits
                
                # Validate phone number (Indian mobile numbers)
                if len(phone) != 10 or not phone.startswith(('6', '7', '8', '9')):
                    continue  # Skip invalid phone numbers
                
                # Assign to caller in round-robin fashion
                assigned_caller = callers[caller_index % total_callers]
                
                # Check for duplicate phone numbers
                existing_lead = Lead.objects.filter(phone=phone).first()
                if existing_lead:
                    continue  # Skip duplicates
                
                # Create lead
                lead = Lead.objects.create(
                    name=lead_data['name'].strip(),
                    email=lead_data.get('email', '').strip() or None,
                    phone=phone,
                    company=lead_data.get('company', '').strip() or None,
                    city=lead_data.get('city', '').strip() or None,
                    state=lead_data.get('state', '').strip() or None,
                    notes=lead_data.get('notes', '').strip() or None,
                    lead_type=lead_type,
                    status=LeadStatus.NEW,
                    assigned_to=assigned_caller,
                    uploaded_by=uploaded_by
                )
                
                # Log activity
                LeadActivity.objects.create(
                    lead=lead,
                    user=uploaded_by,
                    activity_type='NOTE',
                    description=f'Lead uploaded and assigned to {assigned_caller.get_full_name()}'
                )
                
                created_leads.append(lead)
                caller_index += 1
        
        return created_leads, None

class LeadConversionService:
    """
    Service for converting leads between types
    """

    @staticmethod
    def convert_lead(lead, new_type, converted_by, notes='', assigned_to=None):
        """
        Convert lead from one type to another
        """
        if lead.lead_type == new_type:
            return None, "Lead is already of this type"

        # If assigned_to is not provided, assign automatically
        if assigned_to is None:
            callers = LeadDistributionService.get_callers_by_type(new_type)
            if not callers.exists():
                return None, f"No active {new_type} callers found"
            assigned_to = callers.first()

        with transaction.atomic():
            # Save original type
            lead.original_type = lead.lead_type

            # Update lead
            lead.lead_type = new_type
            lead.assigned_to = assigned_to
            lead.converted_by = converted_by
            lead.converted_at = timezone.now()
            lead.save()

            # Log conversion activity
            LeadActivity.objects.create(
                lead=lead,
                user=converted_by,
                activity_type='CONVERSION',
                description=f'Lead converted from {lead.original_type} to {new_type}. {notes}',
                old_status=lead.original_type,
                new_status=new_type
            )

        return lead, None

class LeadActivityService:
    """
    Service for logging lead activities
    """
    
    @staticmethod
    def log_activity(lead, user, activity_type, description, old_status=None, new_status=None):
        """
        Log an activity for a lead
        """
        return LeadActivity.objects.create(
            lead=lead,
            user=user,
            activity_type=activity_type,
            description=description,
            old_status=old_status,
            new_status=new_status
        )
    
    @staticmethod
    def log_status_change(lead, user, old_status, new_status, notes=''):
        """
        Log status change activity
        """
        description = f'Status changed from {old_status} to {new_status}'
        if notes:
            description += f'. Notes: {notes}'
        
        return LeadActivityService.log_activity(
            lead=lead,
            user=user,
            activity_type='STATUS_CHANGE',
            description=description,
            old_status=old_status,
            new_status=new_status
        )
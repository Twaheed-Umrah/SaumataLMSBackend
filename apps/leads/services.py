from datetime import datetime, time
from django.db import transaction
from django.utils import timezone
from apps.accounts.models import User
from .models import Lead, LeadActivity
from utils.constants import UserRole, LeadType, LeadStatus
from utils.excel import parse_excel_leads


class LeadDistributionService:
    @staticmethod
    def get_callers_by_type(lead_type, include_non_present=False):
        """
        Get active callers based on lead type
        Args:
            lead_type: FRANCHISE or PACKAGE
            include_non_present: If True, include all callers regardless of is_present status
                                If False, only include callers with is_present=True (default)
        """
        if lead_type == LeadType.FRANCHISE:
            role = UserRole.FRANCHISE_CALLER
        elif lead_type == LeadType.PACKAGE:
            role = UserRole.PACKAGE_CALLER
        else:
            role = UserRole.FRANCHISE_CALLER
        
        queryset = User.objects.filter(role=role, is_active=True)
        
        # 🔥 Only include callers who are present (unless explicitly overridden)
        if not include_non_present:
            queryset = queryset.filter(is_present=True)
        
        return queryset.order_by('id')
    
    @staticmethod
    def distribute_leads(leads_data, lead_type, uploaded_by, column_mapping=None):
        """
        Distribute leads equally among present callers
        """
        # 🔥 Get only present callers for auto distribution
        callers = LeadDistributionService.get_callers_by_type(lead_type, include_non_present=False)
        
        if not callers.exists():
            # Try to get all callers to show error message
            all_callers = LeadDistributionService.get_callers_by_type(lead_type, include_non_present=True)
            if all_callers.exists():
                non_present_callers = all_callers.filter(is_present=False)
                return None, f"No active and present {lead_type} callers found. {non_present_callers.count()} caller(s) are marked as not present."
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
                    description=f'Lead auto-distributed and assigned to {assigned_caller.get_full_name()}'
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
    
# In services.py, add this class
class LeadManualUploadService:
    """
    Service for manually uploading leads and assigning to specific caller
    """
    
    @staticmethod
    def upload_and_assign(file, lead_type, assigned_to, uploaded_by, column_mapping=None):
        """
        Upload leads from file and assign to specific caller
        """
        # Parse Excel file
        leads_data, error = parse_excel_leads(file, column_mapping)
        if error:
            return None, error
        
        if not leads_data:
            return [], "No valid leads found in the file"
        
        created_leads = []
        failed_leads = []
        
        with transaction.atomic():
            for idx, lead_data in enumerate(leads_data):
                # Validate required fields
                if not lead_data.get('name') or not lead_data.get('phone'):
                    failed_leads.append({
                        'row': idx + 2,  # +2 because Excel is 1-indexed and header row
                        'data': lead_data,
                        'reason': 'Missing name or phone'
                    })
                    continue
                
                # Clean phone number
                phone = lead_data['phone']
                if not phone:
                    failed_leads.append({
                        'row': idx + 2,
                        'data': lead_data,
                        'reason': 'Empty phone number'
                    })
                    continue
                
                # Remove non-numeric characters
                phone = ''.join(filter(str.isdigit, str(phone)))
                
                # Remove country code if present
                if phone.startswith('91') and len(phone) == 12:
                    phone = phone[2:]
                elif len(phone) > 10:
                    phone = phone[-10:]  # Take last 10 digits
                
                # Validate phone number (Indian mobile numbers)
                if len(phone) != 10 or not phone.startswith(('6', '7', '8', '9')):
                    failed_leads.append({
                        'row': idx + 2,
                        'data': lead_data,
                        'reason': f'Invalid phone number: {lead_data["phone"]}'
                    })
                    continue
                
                # Check for duplicate phone numbers
                existing_lead = Lead.objects.filter(phone=phone).first()
                if existing_lead:
                    failed_leads.append({
                        'row': idx + 2,
                        'data': lead_data,
                        'reason': f'Duplicate phone number: {phone}'
                    })
                    continue
                
                try:
                    # Create lead
                    lead = Lead.objects.create(
                        name=lead_data.get('name', '').strip(),
                        email=lead_data.get('email', '').strip() or None,
                        phone=phone,
                        company=lead_data.get('company', '').strip() or None,
                        city=lead_data.get('city', '').strip() or None,
                        state=lead_data.get('state', '').strip() or None,
                        notes=lead_data.get('notes', '').strip() or None,
                        lead_type=lead_type,
                        status=LeadStatus.NEW,
                        assigned_to=assigned_to,
                        uploaded_by=uploaded_by
                    )
                    
                    # Log activity
                    LeadActivity.objects.create(
                        lead=lead,
                        user=uploaded_by,
                        activity_type='NOTE',
                        description=f'Lead manually uploaded and assigned to {assigned_to.get_full_name()}'
                    )
                    
                    created_leads.append(lead)
                    
                except Exception as e:
                    failed_leads.append({
                        'row': idx + 2,
                        'data': lead_data,
                        'reason': f'Error creating lead: {str(e)}'
                    })
        
        return {
            'created_leads': created_leads,
            'failed_leads': failed_leads,
            'total_rows': len(leads_data),
            'successful': len(created_leads),
            'failed': len(failed_leads)
        }, None
    

# Add to services.py

class LeadPullService:
    """
    Service for pulling leads from callers
    """
    @staticmethod
    def pull_leads_by_ids(lead_ids, pulled_by, pull_reason=''):
        """
        Pull specific leads by IDs - MOVES them to PulledLead table
        """
        from .models import Lead, PulledLead, LeadActivity
        
        pulled_leads = []
        failed_leads = []
        deleted_leads = []  # Track deleted leads
        
        with transaction.atomic():
            for lead_id in lead_ids:
                try:
                    lead = Lead.objects.get(id=lead_id)
                    
                    # Check if already pulled and not exported
                    existing_pulled = PulledLead.objects.filter(
                        phone=lead.phone,
                        pulled_from=lead.assigned_to,
                        exported=False
                    ).exists()
                    
                    if existing_pulled:
                        failed_leads.append({
                            'lead_id': lead_id,
                            'reason': 'Lead already pulled and not exported'
                        })
                        continue
                    
                    # Check if lead is assigned
                    if not lead.assigned_to:
                        failed_leads.append({
                            'lead_id': lead_id,
                            'reason': 'Lead is not assigned'
                        })
                        continue
                    
                    # 🟢 CRITICAL CHANGE: Create pulled lead record BEFORE deleting original
                    pulled_lead = PulledLead.objects.create(
                        original_lead_id=lead.id,  # Store original ID before deletion
                        name=lead.name,
                        email=lead.email,
                        phone=lead.phone,
                        company=lead.company,
                        city=lead.city,
                        state=lead.state,
                        notes=lead.notes,
                        original_lead_type=lead.lead_type,
                        original_status=lead.status,
                        pulled_by=pulled_by,
                        pulled_from=lead.assigned_to,
                        pull_reason=pull_reason,
                        filter_criteria={
                            'method': 'by_ids',
                            'lead_ids': [lead_id],
                            'deleted_from_lead_table': True  # Flag that this was moved, not copied
                        }
                    )
                    
                    # 🟢 CRITICAL CHANGE: Store lead data before deletion for activity log
                    lead_data_before_delete = {
                        'id': lead.id,
                        'name': lead.name,
                        'phone': lead.phone,
                        'status': lead.status,
                        'lead_type': lead.lead_type,
                        'assigned_to': lead.assigned_to.get_full_name() if lead.assigned_to else None
                    }
                    
                    # 🟢 CRITICAL CHANGE: DELETE from Lead table
                    lead.delete()
                    deleted_leads.append(lead_data_before_delete)
                    
                    # Log activity (we can't log on original lead anymore, but log in PulledLead notes)
                    pulled_lead.notes = f"{pulled_lead.notes}\n\n--- PULL LOG ---\nLead MOVED (not copied) from Lead table.\nOriginal Lead ID: {lead_data_before_delete['id']}\nPulled by: {pulled_by.get_full_name()}\nReason: {pull_reason}\nDate: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    pulled_lead.save()
                    
                    pulled_leads.append(pulled_lead)
                    
                except Lead.DoesNotExist:
                    failed_leads.append({
                        'lead_id': lead_id,
                        'reason': 'Lead not found'
                    })
                except Exception as e:
                    failed_leads.append({
                        'lead_id': lead_id,
                        'reason': str(e)
                    })
        
        return pulled_leads, failed_leads, deleted_leads
    
    @staticmethod
    def pull_leads_by_filters(filters, pulled_by):
        """
        Pull leads using advanced filters - MOVES them to PulledLead table
        """
        from .models import Lead, PulledLead
        from django.db.models import Q
        
        # Build query
        query = Q()
        
        # Filter by caller(s)
        if 'caller_id' in filters:
            query &= Q(assigned_to__id=filters['caller_id'])
        elif 'caller_ids' in filters and filters['caller_ids']:
            query &= Q(assigned_to__id__in=filters['caller_ids'])
        
        # Filter by date range
        if 'from_date' in filters and filters['from_date']:
            from_datetime = timezone.make_aware(
                datetime.combine(filters['from_date'], time.min)
            )
            query &= Q(created_at__gte=from_datetime)
        
        if 'to_date' in filters and filters['to_date']:
            to_datetime = timezone.make_aware(
                datetime.combine(filters['to_date'], time.max)
            )
            query &= Q(created_at__lte=to_datetime)
        
        # Filter by lead type
        if 'lead_type' in filters and filters['lead_type']:
            query &= Q(lead_type=filters['lead_type'])
        
        # Filter by status
        if 'status' in filters and filters['status']:
            query &= Q(status=filters['status'])
        elif 'statuses' in filters and filters['statuses']:
            query &= Q(status__in=filters['statuses'])
        
        # Get leads
        limit = filters.get('limit', 300)
        leads = Lead.objects.filter(query).order_by('-created_at')[:limit]
        
        if not leads:
            return [], [], []
        
        # Pull (MOVE) the leads
        pulled_leads = []
        failed_leads = []
        deleted_leads = []
        
        with transaction.atomic():
            for lead in leads:
                try:
                    # Check if already pulled and not exported
                    existing_pulled = PulledLead.objects.filter(
                        phone=lead.phone,
                        pulled_from=lead.assigned_to,
                        exported=False
                    ).exists()
                    
                    if existing_pulled:
                        continue
                    
                    # 🟢 CRITICAL CHANGE: Create pulled lead record
                    pulled_lead = PulledLead.objects.create(
                        original_lead_id=lead.id,  # Store original ID
                        name=lead.name,
                        email=lead.email,
                        phone=lead.phone,
                        company=lead.company,
                        city=lead.city,
                        state=lead.state,
                        notes=lead.notes,
                        original_lead_type=lead.lead_type,
                        original_status=lead.status,
                        pulled_by=pulled_by,
                        pulled_from=lead.assigned_to,
                        pull_reason=filters.get('pull_reason', ''),
                        filter_criteria={
                            **filters,
                            'deleted_from_lead_table': True,
                            'original_lead_id': lead.id
                        }
                    )
                    
                    # 🟢 CRITICAL CHANGE: Store data before deletion
                    lead_data_before_delete = {
                        'id': lead.id,
                        'name': lead.name,
                        'phone': lead.phone
                    }
                    
                    # 🟢 CRITICAL CHANGE: DELETE from Lead table
                    lead.delete()
                    deleted_leads.append(lead_data_before_delete)
                    
                    # Update notes with pull log
                    pulled_lead.notes = f"{pulled_lead.notes}\n\n--- PULL LOG ---\nLead MOVED from Lead table.\nOriginal Lead ID: {lead_data_before_delete['id']}\nPulled using filters\nDate: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    pulled_lead.save()
                    
                    pulled_leads.append(pulled_lead)
                    
                except Exception as e:
                    failed_leads.append({
                        'lead_id': lead.id,
                        'reason': str(e)
                    })
        
        return pulled_leads, failed_leads, deleted_leads

    @staticmethod
    def get_pulled_leads_queryset(user):
        """
        Get queryset based on user role
        """
        from .models import PulledLead
        
        queryset = PulledLead.objects.all()
        
        if user.role == UserRole.SUPER_ADMIN:
            return queryset
        
        if user.role in [UserRole.TEAM_LEADER, UserRole.LEAD_DISTRIBUTER]:
            return queryset.filter(pulled_by=user)
        
        return queryset.none()
    
    @staticmethod
    def export_pulled_leads_to_excel(pulled_lead_ids=None, filters=None):
        import pandas as pd
        from io import BytesIO
        from django.utils import timezone
        from django.db.models import Q
        from .models import PulledLead
    
        query = Q()
    
        # -------- selected leads --------
        if pulled_lead_ids:
            query &= Q(id__in=pulled_lead_ids)
    
        # -------- FIXED lead_type field --------
        if filters.get("lead_type"):
            query &= Q(original_lead_type=filters["lead_type"])
    
        # -------- date filters --------
        if filters.get("from_date"):
            query &= Q(created_at__date__gte=filters["from_date"])
    
        if filters.get("to_date"):
            query &= Q(created_at__date__lte=filters["to_date"])
    
        # -------- caller filter --------
        if filters.get("caller_id"):
            query &= Q(pulled_by_id=filters["caller_id"])
    
        pulled_leads = PulledLead.objects.filter(query)
    
        # ❌ NO DATA
        if not pulled_leads.exists():
            return None, "No lead found to export"
    
        # ✅ Excel data
        data = [{
            "Name": l.name,
            "Email": l.email or "",
            "Phone": l.phone,
            "Company": l.company or "",
            "City": l.city or "",
            "State": l.state or "",
        } for l in pulled_leads]
    
        df = pd.DataFrame(data)
    
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Pulled Leads")
    
        output.seek(0)

        # ✅ ALWAYS update exported status when Excel is generated
        pulled_leads.update(
            exported=True,
            exported_at=timezone.now()
        )
    
        return output, None


    @staticmethod
    def get_pulled_leads_for_upload(pulled_lead_ids):
        """
        Get pulled leads data for uploading
        """
        from .models import PulledLead
        
        pulled_leads = PulledLead.objects.filter(
            id__in=pulled_lead_ids,
            exported=True  # Only exported leads can be uploaded
        )
        
        # Convert to upload format
        upload_data = []
        for lead in pulled_leads:
            upload_data.append({
                'name': lead.name,
                'email': lead.email,
                'phone': lead.phone,
                'company': lead.company,
                'city': lead.city,
                'state': lead.state,
                'notes': lead.notes,
            })
        
        return upload_data
    
    @staticmethod
    def get_lead_pull_statistics(user):
        """
        Get statistics about pulled leads
        """
        from .models import PulledLead
        from django.db.models import Count, Q
        
        queryset = LeadPullService.get_pulled_leads_queryset(user)
        
        # FIXED: Use different names for aggregate results
        stats = queryset.aggregate(
            total_pulled_count=Count('id'),  # Changed from total_pulled
            exported_count=Count('id', filter=Q(exported=True)),  # Changed from exported
            not_exported_count=Count('id', filter=Q(exported=False)),  # Changed from not_exported
            total_franchise_leads=Count('id', filter=Q(original_lead_type='FRANCHISE')),
            total_package_leads=Count('id', filter=Q(original_lead_type='PACKAGE')),
        )
        
        # Group by status
        status_stats = list(
            queryset.values('original_status')
            .annotate(count=Count('id'))
            .order_by('-count')
        )
        
        # Group by lead type
        type_stats = list(
            queryset.values('original_lead_type')
            .annotate(count=Count('id'))
            .order_by('-count')
        )
        
        # Group by caller
        caller_stats = list(
            queryset.values(
                'pulled_from__first_name', 
                'pulled_from__last_name'
            )
            .annotate(count=Count('id'))
            .order_by('-count')[:10]
        )
        
        return {
            'overall': {
                'total': stats['total_pulled_count'],
                'exported': stats['exported_count'],
                'not_exported': stats['not_exported_count'],
                'total_franchise_leads': stats['total_franchise_leads'],
                'total_package_leads': stats['total_package_leads'],
            },
            'by_status': status_stats,
            'by_lead_type': type_stats,
            'by_caller': caller_stats,
        }


class LeadTransferService:
    """
    Service for MOVING leads from PulledLeads to Lead table
    """
    
    @staticmethod
    def transfer_pulled_leads(pulled_lead_ids, assigned_to, transferred_by, notes=''):
        """
        MOVE leads from PulledLeads to Lead table (DELETE from PulledLeads)
        """
        from .models import Lead, PulledLead
        
        transferred_leads = []
        failed_transfers = []
        
        with transaction.atomic():
            for pulled_lead_id in pulled_lead_ids:
                try:
                    # Get pulled lead
                    pulled_lead = PulledLead.objects.get(id=pulled_lead_id)
                    
                    # Check if lead already exists in Lead table (duplicate phone)
                    existing_lead = Lead.objects.filter(phone=pulled_lead.phone).first()
                    if existing_lead:
                        failed_transfers.append({
                            'pulled_lead_id': pulled_lead_id,
                            'phone': pulled_lead.phone,
                            'reason': 'Lead with this phone already exists in Lead table'
                        })
                        continue
                    
                    # Create lead in Lead table
                    lead = Lead.objects.create(
                        name=pulled_lead.name,
                        email=pulled_lead.email,
                        phone=pulled_lead.phone,
                        company=pulled_lead.company,
                        city=pulled_lead.city,
                        state=pulled_lead.state,
                        notes=f"{pulled_lead.notes or ''}\n\n--- TRANSFERRED FROM PULLED LEADS ---\nOriginal PulledLead ID: {pulled_lead_id}\nOriginal Status: {pulled_lead.original_status}\nTransferred by: {transferred_by.get_full_name()}\nDate: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}\nNotes: {notes}",
                        lead_type=pulled_lead.original_lead_type,
                        status=LeadStatus.NEW,  # Reset to NEW
                        assigned_to=assigned_to,
                        uploaded_by=transferred_by
                    )
                    
                    # Log activity
                    LeadActivity.objects.create(
                        lead=lead,
                        user=transferred_by,
                        activity_type='TRANSFER',
                        description=f'Lead transferred from PulledLeads database. Originally pulled from: {pulled_lead.pulled_from.get_full_name() if pulled_lead.pulled_from else "Unknown"}. Assigned to: {assigned_to.get_full_name()}.'
                    )
                    
                    # 🟢 CRITICAL: DELETE from PulledLeads table
                    pulled_lead.delete()
                    
                    transferred_leads.append({
                        'new_lead_id': lead.id,
                        'original_pulled_lead_id': pulled_lead_id,
                        'name': lead.name,
                        'phone': lead.phone,
                        'assigned_to': assigned_to.get_full_name(),
                        'lead_type': lead.lead_type,
                        'status': lead.status
                    })
                    
                except PulledLead.DoesNotExist:
                    failed_transfers.append({
                        'pulled_lead_id': pulled_lead_id,
                        'reason': 'Pulled lead not found'
                    })
                except Exception as e:
                    failed_transfers.append({
                        'pulled_lead_id': pulled_lead_id,
                        'reason': str(e)
                    })
        
        return transferred_leads, failed_transfers
    
    @staticmethod
    def transfer_by_filters(filters, assigned_to, transferred_by, notes=''):
        """
        Transfer leads from PulledLeads using filters
        """
        from .models import PulledLead, Lead
        from django.db.models import Q
        
        # Build query
        query = Q()
        
        # Filter by date
        if 'from_date' in filters and filters['from_date']:
            from_datetime = timezone.make_aware(
                datetime.combine(filters['from_date'], time.min)
            )
            query &= Q(created_at__gte=from_datetime)
        
        if 'to_date' in filters and filters['to_date']:
            to_datetime = timezone.make_aware(
                datetime.combine(filters['to_date'], time.max)
            )
            query &= Q(created_at__lte=to_datetime)
        
        # Filter by status
        if 'status' in filters and filters['status']:
            query &= Q(original_status=filters['status'])
        
        # Filter by lead type
        if 'lead_type' in filters and filters['lead_type']:
            query &= Q(original_lead_type=filters['lead_type'])
        
        # Filter by exported status (optional)
        if 'exported' in filters:
            query &= Q(exported=filters['exported'])
        
        # Get pulled leads
        limit = filters.get('limit', 100)
        pulled_leads = PulledLead.objects.filter(query).order_by('-created_at')[:limit]
        
        if not pulled_leads.exists():
            return [], [], "No leads found matching the criteria"
        
        # Transfer leads
        transferred_leads = []
        failed_transfers = []
        
        with transaction.atomic():
            for pulled_lead in pulled_leads:
                try:
                    # Check for duplicates
                    if Lead.objects.filter(phone=pulled_lead.phone).exists():
                        failed_transfers.append({
                            'pulled_lead_id': pulled_lead.id,
                            'phone': pulled_lead.phone,
                            'reason': 'Duplicate phone in Lead table'
                        })
                        continue
                    
                    # Create in Lead table
                    lead = Lead.objects.create(
                        name=pulled_lead.name,
                        email=pulled_lead.email,
                        phone=pulled_lead.phone,
                        company=pulled_lead.company,
                        city=pulled_lead.city,
                        state=pulled_lead.state,
                        notes=f"{pulled_lead.notes or ''}\n\n--- TRANSFERRED FROM PULLED LEADS ---\nFilter-based transfer\nTransferred by: {transferred_by.get_full_name()}\nDate: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}\nNotes: {notes}",
                        lead_type=pulled_lead.original_lead_type,
                        status=LeadStatus.NEW,
                        assigned_to=assigned_to,
                        uploaded_by=transferred_by
                    )
                    
                    # Log activity
                    LeadActivity.objects.create(
                        lead=lead,
                        user=transferred_by,
                        activity_type='TRANSFER',
                        description=f'Lead transferred from PulledLeads using filters. Originally from: {pulled_lead.pulled_from.get_full_name() if pulled_lead.pulled_from else "Unknown"}'
                    )
                    
                    # Delete from PulledLeads
                    pulled_lead.delete()
                    
                    transferred_leads.append({
                        'new_lead_id': lead.id,
                        'original_pulled_lead_id': pulled_lead.id,
                        'name': lead.name,
                        'phone': lead.phone
                    })
                    
                except Exception as e:
                    failed_transfers.append({
                        'pulled_lead_id': pulled_lead.id,
                        'reason': str(e)
                    })
        
        return transferred_leads, failed_transfers, None
    
    @staticmethod
    def preview_transfer_by_filters(filters, assigned_to):
        """
        Preview which leads will be transferred
        """
        from .models import PulledLead, Lead
        from django.db.models import Q
        
        # Build query (same as transfer_by_filters)
        query = Q()
        
        if 'from_date' in filters and filters['from_date']:
            from_datetime = timezone.make_aware(
                datetime.combine(filters['from_date'], time.min)
            )
            query &= Q(created_at__gte=from_datetime)
        
        if 'to_date' in filters and filters['to_date']:
            to_datetime = timezone.make_aware(
                datetime.combine(filters['to_date'], time.max)
            )
            query &= Q(created_at__lte=to_datetime)
        
        if 'status' in filters and filters['status']:
            query &= Q(original_status=filters['status'])
        
        if 'lead_type' in filters and filters['lead_type']:
            query &= Q(original_lead_type=filters['lead_type'])
        
        if 'exported' in filters:
            query &= Q(exported=filters['exported'])
        
        limit = filters.get('limit', 100)
        pulled_leads = PulledLead.objects.filter(query).order_by('-created_at')[:limit]
        
        preview_data = []
        for pulled_lead in pulled_leads:
            # Check if can be transferred
            can_transfer = not Lead.objects.filter(phone=pulled_lead.phone).exists()
            
            preview_data.append({
                'id': pulled_lead.id,
                'name': pulled_lead.name,
                'phone': pulled_lead.phone,
                'email': pulled_lead.email,
                'original_lead_type': pulled_lead.original_lead_type,
                'original_status': pulled_lead.original_status,
                'exported': pulled_lead.exported,
                'pulled_from': pulled_lead.pulled_from.get_full_name() if pulled_lead.pulled_from else None,
                'created_at': pulled_lead.created_at,
                'can_transfer': can_transfer,
                'duplicate_reason': 'Phone exists in Lead table' if not can_transfer else None
            })
        
        return preview_data
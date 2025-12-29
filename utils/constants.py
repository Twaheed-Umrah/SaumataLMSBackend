"""
Constants used throughout the application
"""

# User Roles
class UserRole:
    LEAD_DISTRIBUTER='LEAD_DISTRIBUTER'
    FRANCHISE_CALLER = 'FRANCHISE_CALLER'
    PACKAGE_CALLER = 'PACKAGE_CALLER'
    TEAM_LEADER = 'TEAM_LEADER'
    SUPER_ADMIN = 'SUPER_ADMIN'
    
    CHOICES = [
        (LEAD_DISTRIBUTER,'LEAD_DISTRIBUTER'),
        (FRANCHISE_CALLER, 'Franchise Caller'),
        (PACKAGE_CALLER, 'Package Caller'),
        (TEAM_LEADER, 'Team Leader'),
        (SUPER_ADMIN, 'Super Admin'),
    ]

# Lead Types
class LeadType:
    FRANCHISE = 'FRANCHISE'
    PACKAGE = 'PACKAGE'
    
    CHOICES = [
        (FRANCHISE, 'Franchise'),
        (PACKAGE, 'Package'),
    ]

# Lead Status
class LeadStatus:
    NEW = 'NEW'
    CONTACTED = 'CONTACTED'
    INTERESTED = 'INTERESTED'
    NOT_INTERESTED = 'NOT_INTERESTED'
    FOLLOW_UP = 'FOLLOW_UP'
    CONVERTED = 'CONVERTED'
    LOST = 'LOST'
    
    CHOICES = [
        (NEW, 'New'),
        (CONTACTED, 'Contacted'),
        (INTERESTED, 'Interested'),
        (NOT_INTERESTED, 'Not Interested'),
        (FOLLOW_UP, 'Follow Up'),
        (CONVERTED, 'Converted'),
        (LOST, 'Lost'),
    ]

# Payment Status
class PaymentStatus:
    PENDING = 'PENDING'
    PARTIAL = 'PARTIAL'
    COMPLETED = 'COMPLETED'
    REFUNDED = 'REFUNDED'
    
    CHOICES = [
        (PENDING, 'Pending'),
        (PARTIAL, 'Partial'),
        (COMPLETED, 'Completed'),
        (REFUNDED, 'Refunded'),
    ]

# Delivery Item Status
class DeliveryStatus:
    PENDING = 'PENDING'
    IN_PROGRESS = 'IN_PROGRESS'
    COMPLETED = 'COMPLETED'
    
    CHOICES = [
        (PENDING, 'Pending'),
        (IN_PROGRESS, 'In Progress'),
        (COMPLETED, 'Completed'),
    ]

# Delivery Items
class DeliveryItem:
    WEBSITE = 'WEBSITE'
    LOGO = 'LOGO'
    SOCIAL_MEDIA = 'SOCIAL_MEDIA'
    MARKETING_MATERIAL = 'MARKETING_MATERIAL'
    OTHER = 'OTHER'
    
    CHOICES = [
        (WEBSITE, 'Website'),
        (LOGO, 'Logo'),
        (SOCIAL_MEDIA, 'Social Media Accounts'),
        (MARKETING_MATERIAL, 'Marketing Material'),
        (OTHER, 'Other Custom Services'),
    ]
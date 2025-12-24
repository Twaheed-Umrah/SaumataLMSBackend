# utils/pagination.py
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework import status


class CustomPageNumberPagination(PageNumberPagination):
    """
    Custom pagination class that works with your success_response format
    """
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100
    
    def get_paginated_response(self, data, message="Success"):
        """
        Override to return your custom success_response format
        """
        from utils.response import success_response
        
        response_data = {
            'results': data,
            'count': self.page.paginator.count,
            'total_pages': self.page.paginator.num_pages,
            'current_page': self.page.number,
            'has_next': self.page.has_next(),
            'has_previous': self.page.has_previous(),
            'next_page': self.get_next_link(),
            'previous_page': self.get_previous_link(),
            'page_size': self.get_page_size(self.request)
        }
        
        return success_response(response_data, message)
    
    def get_paginated_response_schema(self, schema):
        """
        Schema for OpenAPI documentation
        """
        return {
            'type': 'object',
            'properties': {
                'success': {'type': 'boolean', 'example': True},
                'message': {'type': 'string', 'example': 'Success'},
                'data': {
                    'type': 'object',
                    'properties': {
                        'results': schema,
                        'count': {'type': 'integer', 'example': 100},
                        'total_pages': {'type': 'integer', 'example': 5},
                        'current_page': {'type': 'integer', 'example': 1},
                        'has_next': {'type': 'boolean', 'example': True},
                        'has_previous': {'type': 'boolean', 'example': False},
                        'next_page': {'type': 'string', 'nullable': True},
                        'previous_page': {'type': 'string', 'nullable': True},
                        'page_size': {'type': 'integer', 'example': 20}
                    }
                }
            }
        }
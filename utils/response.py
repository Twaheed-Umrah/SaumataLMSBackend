from rest_framework.response import Response
from rest_framework import status


def success_response(data=None, message="Success", status_code=status.HTTP_200_OK):
    """
    Standard success response format
    """
    return Response({
        'success': True,
        'message': message,
        'data': data
    }, status=status_code)


def error_response(message="Error occurred", errors=None, status_code=status.HTTP_400_BAD_REQUEST):
    """
    Standard error response format
    """
    return Response({
        'success': False,
        'message': message,
        'errors': errors
    }, status=status_code)


def created_response(data=None, message="Created successfully"):
    """
    Standard created response
    """
    return success_response(data, message, status.HTTP_201_CREATED)


def deleted_response(message="Deleted successfully"):
    """
    Standard deleted response
    """
    return success_response(message=message, status_code=status.HTTP_204_NO_CONTENT)
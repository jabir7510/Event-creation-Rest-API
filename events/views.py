from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from .models import Event
from .serializers import EventSerializer, RegisterSerializer
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.utils import timezone
from dateutil import rrule
from datetime import timedelta
from django.shortcuts import render
class RegisterView(APIView):
    permission_classes = [AllowAny]
        
    def post(self, request):
        username = request.data.get('username')
        email = request.data.get('email')

        if User.objects.filter(username=username).exists():
            return Response({"detail": "Username already exists."}, status=status.HTTP_400_BAD_REQUEST)
        
        if User.objects.filter(email=email).exists():
            return Response({"detail": "Email already registered."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response({
                "message": "User registered successfully",
                "user": RegisterSerializer(user).data
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        username = request.data.get('username')
        password = request.data.get('password')

        if not username or not password:
            return Response({"detail": "Username and password are required."}, status=status.HTTP_400_BAD_REQUEST)

        user = authenticate(username=username, password=password)
        
        if user:
            refresh = RefreshToken.for_user(user)
            return Response({
                'access': str(refresh.access_token),
                'refresh': str(refresh),
            })
        return Response({"detail": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)


class EventView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """List user's events for next 30 days"""
        user = request.user
        queryset = Event.objects.filter(owner=user)
        thirty_days_later = timezone.now() + timedelta(days=30)
        
        result = self.initialize_result()
        self.process_events(queryset, result, thirty_days_later)

        return Response(result, status=status.HTTP_200_OK)

    def initialize_result(self):
        """Initialize the result dictionary with the next 30 days"""
        result = {}
        current_date = timezone.now().date()
        for i in range(30):
            date = current_date + timedelta(days=i)
            result[date.strftime('%Y-%m-%d')] = []
        return result

    def process_events(self, queryset, result, thirty_days_later):
        """Process each event and add it to the result dictionary"""
        for event in queryset:
            if event.recurrence == 'NONE':
                self.process_non_recurring_event(event, result, thirty_days_later)
            else:
                self.process_recurring_event(event, result, thirty_days_later)

    def process_non_recurring_event(self, event, result, thirty_days_later):
        """Process a non-recurring event"""
        if event.start_datetime.date() <= thirty_days_later.date():
            date_str = event.start_datetime.date().strftime('%Y-%m-%d')
            if date_str in result:
                result[date_str].append({
                    'id': event.id,
                    'title': event.title,
                    'start_datetime': event.start_datetime.isoformat(),
                    'duration': event.duration
                })

    def process_recurring_event(self, event, result, thirty_days_later):
        """Process a recurring event"""
        rule = {
            'DAILY': rrule.DAILY,
            'WEEKLY': rrule.WEEKLY
        }[event.recurrence]
        
        dates = rrule.rrule(
            rule,
            dtstart=event.start_datetime,
            until=min(event.recurrence_end, thirty_days_later)
        )
        
        for date in dates:
            date_str = date.date().strftime('%Y-%m-%d')
            if date_str in result:
                result[date_str].append({
                    'id': event.id,
                    'title': event.title,
                    'start_datetime': date.isoformat(),
                    'duration': event.duration
                })

    def post(self, request):
        """Create a new event"""
        serializer = EventSerializer(data=request.data)
        if serializer.is_valid():
            user = request.user
            start_datetime = serializer.validated_data['start_datetime']
            recurrence = serializer.validated_data['recurrence']
            recurrence_end = serializer.validated_data.get('recurrence_end') 

            error_response = self.validate_recurrence(recurrence, recurrence_end, start_datetime)
            if error_response:
                return error_response

            error_response = self.check_event_overlap(user, start_datetime, recurrence, recurrence_end)
            if error_response:
                return error_response

            event = serializer.save(owner=user)
            self.send_event_email(event, user)

            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def validate_recurrence(self, recurrence, recurrence_end, start_datetime):
        if recurrence == 'NONE':
            if recurrence_end is not None:
                return Response(
                    {"error": "Recurrence end date should not be provided when recurrence is NONE"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:  # DAILY or WEEKLY
            if recurrence_end is None:
                return Response(
                    {"error": "Recurrence end date is required for DAILY or WEEKLY recurrence"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if recurrence_end.date() <= start_datetime.date():
                return Response(
                    {"error": "Recurrence end date must be after the start date"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        return None

    def check_event_overlap(self, user, start_datetime, recurrence, recurrence_end):
        existing_events = Event.objects.filter(owner=user)
        if recurrence == 'NONE':
            if existing_events.filter(start_datetime=start_datetime).exists():
                return Response(
                    {"error": "You already have an event scheduled at this exact date and time"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            rule = {
                'DAILY': rrule.DAILY,
                'WEEKLY': rrule.WEEKLY
            }[recurrence]
            
            dates = rrule.rrule(
                rule,
                dtstart=start_datetime,
                until=recurrence_end
            )
            
            for date in dates:
                if existing_events.filter(start_datetime=date).exists():
                    return Response(
                        {"error": f"You already have an event scheduled at {date}"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
        return None

    def send_event_email(self, event, user):
        send_mail(
            f'New Event: {event.title}',
            f'Event scheduled for {event.start_datetime}. Duration: {event.duration} minutes',
            'jabir.a@webandcrafts.in', #give the mail
            [user.email],
            fail_silently=False,
        )

class EventDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        """Delete an event"""
        try:
            event = Event.objects.get(pk=pk, owner=request.user)
            event.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Event.DoesNotExist:
            return Response(
                {"error": "Event not found or you don't have permission"},
                status=status.HTTP_404_NOT_FOUND
            )
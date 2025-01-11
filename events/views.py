import random
from datetime import datetime

from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from supabase import Client, create_client

# Supabase 클라이언트 설정
supabase: Client = create_client(
    settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY
)


def process_event_response(event):
    event["num_started"] = len(event["started_user_ids"])
    event["num_completed"] = len(event["completed_user_ids"])


@api_view(["GET"])
@permission_classes([AllowAny])
def events_list(request):
    events = supabase.table("events").select("*").execute()

    events = [
        event
        for event in events.data
        if datetime.fromisoformat(event["expiry"]) > datetime.now()
        and len(event["completed_user_ids"]) < event["max_users"]
    ]

    images = (
        supabase.table("images")
        .select("*")
        .in_("event_id", [event["id"] for event in events])
        .execute()
    )

    for event in events:
        # find the first image for the event
        for image in images.data:
            if image["event_id"] == event["id"]:
                event["thumbnail_url"] = image["image_url"]
                break

        process_event_response(event)

    return Response(events, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([AllowAny])
def events_create(request):
    data = request.data

    data["author_id"] = "12b2ac5e-98f6-44be-b790-1305293b52bd"  # replace for testing

    data["answer_key"] = "".join([str(random.randint(0, 9)) for _ in range(4)])

    # TODO: 이미지

    event = supabase.table("events").insert(data).execute().data[0]

    process_event_response(event)

    return Response(event, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([AllowAny])
def events_detail(request, event_id):
    event = (
        supabase.table("events").select("*").eq("id", event_id).single().execute().data
    )

    if not event:
        return Response(
            {"error": f"Event with id {event_id} not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    images = supabase.table("images").select("*").eq("event_id", event_id).execute()

    event["image_urls"] = [image["url"] for image in images.data]

    process_event_response(event)
    return Response(event, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([AllowAny])
def events_join(request, event_id):
    user_id = "12b2ac5e-98f6-44be-b790-1305293b52bd"
    event = (
        supabase.table("events").select("*").eq("id", event_id).single().execute().data
    )

    # TODO: check expiry & max_users

    # append user to started_user_ids
    event = (
        supabase.table("events")
        .update({"started_user_ids": event["started_user_ids"] + [user_id]})
        .eq("id", event_id)
        .execute()
        .data[0]
    )

    process_event_response(event)
    return Response(event, status=status.HTTP_200_OK)


def events_complete(request, event_id):
    user_id = request.user.user_id
    event = (
        supabase.table("events").select("*").eq("id", event_id).single().execute().data
    )

    if request.data["answer_key"] != event["answer_key"]:
        return Response(
            {"error": "Incorrect answer key"}, status=status.HTTP_400_BAD_REQUEST
        )

    # append user to completed_user_ids
    event = (
        supabase.table("events")
        .update({"completed_user_ids": event["completed_user_ids"] + [user_id]})
        .eq("id", event_id)
        .execute()
    )

    process_event_response(event)
    return Response(event, status=status.HTTP_200_OK)

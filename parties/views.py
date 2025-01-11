from datetime import datetime

from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from supabase import Client, create_client

supabase: Client = create_client(
    settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY
)

PARTY_STATE_MAP = {
    0: "RECRUITING",
    1: "ONGOING",
    2: "COMPLETED",
}


def process_party_response(party):
    party["num_participants"] = len(party["participant_ids"]) + 1
    party["state"] = PARTY_STATE_MAP[party["state"]]


@api_view(["GET"])
@permission_classes([AllowAny])
def parties_detail(request, party_id):
    party = (
        supabase.table("parties").select("*").eq("id", party_id).single().execute().data
    )

    if not party:
        return Response({"error": "Party not found"}, status=status.HTTP_404_NOT_FOUND)

    process_party_response(party)

    return Response(party, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([AllowAny])
def parties_list(request):
    parties = supabase.table("parties").select("*").neq("state", 2).execute().data
    map(
        process_party_response,
        parties,
    )

    return Response(parties, status=status.HTTP_200_OK)


# TODO: Handle image uploads
@api_view(["POST"])
@permission_classes([AllowAny])
def parties_create(request):
    party = request.data

    party["organizer_id"] = "12b2ac5e-98f6-44be-b790-1305293b52bd"

    party = supabase.table("parties").insert(party).execute().data[0]
    process_party_response(party)

    return Response(party, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([AllowAny])
def parties_join(request, party_id):
    user_id = "12b2ac5e-98f6-44be-b790-1305293b52bd"

    party = (
        supabase.table("parties").select("*").eq("id", party_id).single().execute().data
    )

    if not party:
        return Response({"error": "Party not found"}, status=status.HTTP_404_NOT_FOUND)

    if party["state"] != 0:
        return Response(
            {"error": "Party is not recruiting"}, status=status.HTTP_400_BAD_REQUEST
        )

    if party["max_users"] <= len(party["participant_ids"]) + 1:
        return Response({"error": "Party is full"}, status=status.HTTP_400_BAD_REQUEST)

    if user_id in party["participant_ids"] or user_id == party["organizer_id"]:
        return Response(
            {"error": "User already joined"}, status=status.HTTP_400_BAD_REQUEST
        )

    party["participant_ids"].append(user_id)

    party = supabase.table("parties").update(party).eq("id", party_id).execute().data[0]
    process_party_response(party)

    return Response(party, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([AllowAny])
def parties_start(request, party_id):
    user_id = "12b2ac5e-98f6-44be-b790-1305293b52bd"

    party = (
        supabase.table("parties").select("*").eq("id", party_id).single().execute().data
    )
    if not party:
        return Response({"error": "Party not found"}, status=status.HTTP_404_NOT_FOUND)

    if party["organizer_id"] != user_id:
        return Response(
            {"error": "Only organizer can start party"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if party["state"] != 0:
        return Response(
            {"error": "Party is not recruiting"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    party["state"] = 1
    party["started_at"] = datetime.now().isoformat()

    party = supabase.table("parties").update(party).eq("id", party_id).execute().data[0]
    process_party_response(party)

    return Response(party, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([AllowAny])
def parties_end(request, party_id):
    user_id = "12b2ac5e-98f6-44be-b790-1305293b52bd"

    party = (
        supabase.table("parties").select("*").eq("id", party_id).single().execute().data
    )
    if not party:
        return Response({"error": "Party not found"}, status=status.HTTP_404_NOT_FOUND)

    if party["organizer_id"] != user_id:
        return Response(
            {"error": "Only organizer can end party"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if party["state"] != 1:
        return Response(
            {"error": "Party is not ongoing"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    party["state"] = 2
    party["completed_at"] = datetime.now().isoformat()

    party = supabase.table("parties").update(party).eq("id", party_id).execute().data[0]
    process_party_response(party)

    return Response(party, status=status.HTTP_200_OK)

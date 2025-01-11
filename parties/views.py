import uuid
from datetime import datetime

from django.conf import settings
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, MultiPartParser
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
    parties = (
        supabase.table("parties")
        .select("*")
        .neq("state", 2)
        .order("created_at", desc=True)
        .execute()
        .data
    )
    map(
        process_party_response,
        parties,
    )

    return Response(parties, status=status.HTTP_200_OK)


PARKING_SPOTS = [
    [37, 129],
    [288, 336],
    [177, 365],
    [15, 421],
    [156, 163],
    [141, 432],
    [274, 247],
    [144, 321],
    [171, 426],
    [251, 350],
    [268, 437],
    [327, 245],
    [31, 224],
    [13, 268],
    [334, 429],
    [175, 209],
    [56, 187],
    [221, 325],
    [184, 129],
    [341, 338],
    [234, 453],
    [6, 294],
    [286, 424],
    [323, 409],
    [193, 342],
    [128, 237],
    [158, 294],
    [196, 393],
    [194, 187],
    [58, 442],
    [339, 287],
    [117, 423],
    [311, 142],
    [7, 396],
    [216, 419],
    [33, 279],
    [299, 87],
    [303, 425],
    [280, 145],
    [26, 451],
]


@swagger_auto_schema(
    method="post",
    consumes=["multipart/form-data"],
    manual_parameters=[
        openapi.Parameter(
            "images",
            in_=openapi.IN_FORM,
            type=openapi.TYPE_ARRAY,
            items=openapi.Items(type=openapi.TYPE_FILE, format=openapi.FORMAT_BINARY),
            description="Multiple image files (optional)",
            required=False,
        ),
        openapi.Parameter(
            "x_coordinate",
            in_=openapi.IN_FORM,
            type=openapi.TYPE_NUMBER,
            description="위도",
            required=True,
        ),
        openapi.Parameter(
            "y_coordinate",
            in_=openapi.IN_FORM,
            type=openapi.TYPE_NUMBER,
            description="경도",
            required=True,
        ),
    ],
)
@api_view(["POST"])
@permission_classes([AllowAny])
@parser_classes([MultiPartParser, FormParser])
def parties_create(request):
    party = {
        "title": request.data.get("title"),
        "description": request.data.get("description"),
        "max_users": request.data.get("max_users"),
        "coordinates": [
            float(request.data.get("x_coordinate")),
            float(request.data.get("y_coordinate")),
        ],
    }
    if "images" in party:
        del party["images"]

    party["parking_spot"] = min(
        PARKING_SPOTS,
        key=lambda spot: (spot[0] - party["coordinates"][0]) ** 2
        + (spot[1] - party["coordinates"][1]) ** 2,
    )

    party["organizer_id"] = "12b2ac5e-98f6-44be-b790-1305293b52bd"

    party = supabase.table("parties").insert(party).execute().data[0]

    images = request.FILES.getlist("images")

    for image in images:
        file_extension = image.name.split(".")[-1].lower()

        # 파일 데이터를 읽어서 bytes로 변환
        file_content = image.read()

        # event.id를 사용하여 파일명 생성 (원본 확장자 유지)
        image_id = str(uuid.uuid4())
        file_path = f"{image_id}.{file_extension}"
        upload_response = supabase.storage.from_("images").upload(
            file_path, file_content
        )

        if not upload_response.path:
            return Response(
                {"error": "Failed to upload image"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # 이미지 테이블에 정보 저장 (URL 구성 수정)
        public_url = (
            f"{settings.SUPABASE_URL}/storage/v1/object/public/images/{file_path}"
        )
        supabase.table("images").insert(
            {"id": image_id, "party_id": party["id"], "url": public_url}
        ).execute()

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


# TODO: Upload image
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


@api_view(["GET"])
@permission_classes([AllowAny])
def parties_my(request):
    user_id = "12b2ac5e-98f6-44be-b790-1305293b52bd"

    parties = (
        supabase.table("parties")
        .select("*")
        .or_(
            "organizer_id.eq." + user_id + "," + "participant_ids.cs.{" + user_id + "}",
        )
        .order("created_at", desc=True)
        .execute()
        .data
    )

    map(
        process_party_response,
        parties,
    )

    return Response(parties, status=status.HTTP_200_OK)

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
    0: "RECRUITING",  # 모집 중
    1: "COMPLETED",  # 완료
}


def process_party_response(party):
    party["num_participants"] = len(party["participant_ids"]) + 1
    party["state"] = PARTY_STATE_MAP[party["state"]]


@swagger_auto_schema(
    method="get",
    operation_description="특정 파티의 상세 정보를 조회합니다",
    responses={
        200: openapi.Response(
            description="성공",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "id": openapi.Schema(type=openapi.TYPE_STRING),
                    "title": openapi.Schema(type=openapi.TYPE_STRING),
                    "organizer_nickname": openapi.Schema(type=openapi.TYPE_STRING),
                    "description": openapi.Schema(type=openapi.TYPE_STRING),
                    "destination": openapi.Schema(type=openapi.TYPE_STRING),
                    "created_at": openapi.Schema(
                        type=openapi.TYPE_STRING, format="date-time"
                    ),
                    "participants_nicknames": openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(type=openapi.TYPE_OBJECT),
                    ),
                    "num_participants": openapi.Schema(type=openapi.TYPE_INTEGER),
                    "remaining_num": openapi.Schema(type=openapi.TYPE_INTEGER),
                    "coordinates": openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(type=openapi.TYPE_NUMBER),
                    ),
                    "parking_spot": openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(type=openapi.TYPE_NUMBER),
                    ),
                    "state": openapi.Schema(type=openapi.TYPE_INTEGER),
                    "is_organizer": openapi.Schema(type=openapi.TYPE_BOOLEAN),
                },
            ),
        ),
        404: openapi.Response(description="파티를 찾을 수 없음"),
        400: openapi.Response(description="잘못된 요청"),
    },
)
@api_view(["GET"])
@permission_classes([AllowAny])  # 일단 모두 허용, 나중에 권한필요로 변경
def parties_detail(request, party_id):
    try:
        # user_id = request.user.id
        user_id = "12b2ac5e-98f6-44be-b790-1305293b52bd"

        # 파티 정보 조회
        party_response = (
            supabase.table("parties").select("*").eq("id", party_id).execute()
        )
        if not party_response.data:
            return Response(
                {"error": "Party not found"}, status=status.HTTP_404_NOT_FOUND
            )
        party = party_response.data[0]

        # 주최자 닉네임 조회
        organizer_response = (
            supabase.table("users")
            .select("nickname")
            .eq("user_id", party["organizer_id"])
            .execute()
        )
        if not organizer_response.data:
            return Response(
                {"error": "Organizer not found"}, status=status.HTTP_404_NOT_FOUND
            )
        organizer_nickname = organizer_response.data[0]["nickname"]

        # 참가자들의 상태 정보 구성
        participants_status = {}
        if party["participant_ids"]:
            # 모든 참가자의 닉네임 한 번에 조회
            participants_data = (
                supabase.table("users")
                .select("user_id, nickname")
                .in_("user_id", party["participant_ids"])
                .execute()
                .data
            )

            # 참가자별 상태 정보 구성
            for participant in participants_data:
                participants_status[participant["user_id"]] = {
                    "nickname": participant["nickname"],
                    "status": participant["user_id"] in (party.get("omy_ids") or []),
                }

        # 이미지 url
        image_response = (
            supabase.table("images").select("*").eq("party_id", party["id"]).execute()
        )
        image_url = image_response.data[0]["url"] if image_response.data else None

        # 분기1: is_organizer면 1) participants_status의 본인 id에 해당하는 status가 true면 "운행 종료" 2) false면 "출발하기"
        # 분기2: is_organized면 1) participants_status에 본인 id가 없으면 "참가하기"
        # 2) 있으면 본인 id에 해당하는 status가 true면 "운행 종료" 3) false면 "출발하기"
        reconstructed_data = {
            "id": party["id"],
            "created_at": party["created_at"],
            "title": party["title"],
            "organizer_name": organizer_nickname,
            "is_organizer": party["organizer_id"] == user_id,
            "description": party["description"],
            "destination": party["destination"],
            "meet_at": party["meet_at"],
            "participants_status": participants_status,
            "image_url": image_url,
            "num_participants": len(party["participant_ids"]),
            "remaining_num": party["max_users"] - len(party["participant_ids"]),
            "coordinates": party["coordinates"],
            "parking_spot": party["parking_spot"],
            "state": PARTY_STATE_MAP[party["state"]],
        }

        return Response(reconstructed_data, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@swagger_auto_schema(
    method="get",
    operation_description="모집 중인 파티 목록을 조회합니다",
    responses={
        200: openapi.Response(
            description="성공",
            schema=openapi.Schema(
                type=openapi.TYPE_ARRAY,
                items=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "id": openapi.Schema(type=openapi.TYPE_STRING),
                        "created_at": openapi.Schema(
                            type=openapi.TYPE_STRING, format="date-time"
                        ),
                        "title": openapi.Schema(type=openapi.TYPE_STRING),
                        "destination": openapi.Schema(type=openapi.TYPE_STRING),
                        "num_participants": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "remaining_num": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "coordinates": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(type=openapi.TYPE_NUMBER),
                        ),
                    },
                ),
            ),
        ),
        400: openapi.Response(description="잘못된 요청"),
    },
)
@api_view(["GET"])
@permission_classes([AllowAny])
def parties_list(request):
    try:
        parties = (
            supabase.table("parties")
            .select("*")
            .eq("state", 0)
            .order("meet_at", desc=False)
            .execute()
            .data
        )

        if not parties:
            return Response([], status=status.HTTP_200_OK)

        reconstructed_data = []
        for party in parties:
            data = {
                "id": party["id"],
                "created_at": party["created_at"],
                "title": party["title"],
                "destination": party["destination"],
                "meet_at": party["meet_at"],
                "num_participants": len(party["participant_ids"]),
                "remaining_num": party["max_users"] - len(party["participant_ids"]),
                "coordinates": party["coordinates"],
                "parking_spot": party["parking_spot"],
            }
            reconstructed_data.append(data)

        images = supabase.table("images").select("*").execute().data
        # 이미지 추가
        for party in parties:
            for image in images:
                if image["party_id"] == party["id"]:
                    data["image_url"] = image["url"]
                    break

        return Response(reconstructed_data, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


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
    method="POST",
    tags=["parties"],
    operation_summary="파티 생성",
    operation_description="새로운 파티를 생성합니다.",
    consumes=["multipart/form-data"],
    manual_parameters=[
        openapi.Parameter(
            "title",
            in_=openapi.IN_FORM,
            type=openapi.TYPE_STRING,
            description="파티 제목",
            required=True,
        ),
        openapi.Parameter(
            "description",
            in_=openapi.IN_FORM,
            type=openapi.TYPE_STRING,
            description="파티 설명",
            required=True,
        ),
        openapi.Parameter(
            "max_users",
            in_=openapi.IN_FORM,
            type=openapi.TYPE_INTEGER,
            description="최대 참여 인원",
            required=True,
        ),
        openapi.Parameter(
            "destination",
            in_=openapi.IN_FORM,
            type=openapi.TYPE_STRING,
            description="목적지",
            required=True,
        ),
        openapi.Parameter(
            "meet_at",
            in_=openapi.IN_FORM,
            type=openapi.TYPE_STRING,
            description="만남 시간 (YYYY-MM-DDTHH:mm:ss 형식)",
            required=True,
        ),
        openapi.Parameter(
            "image",
            in_=openapi.IN_FORM,
            type=openapi.TYPE_FILE,
            description="파티 이미지",
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
    responses={
        201: openapi.Response(
            description="생성 성공",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "id": openapi.Schema(type=openapi.TYPE_STRING),
                    "created_at": openapi.Schema(type=openapi.TYPE_STRING),
                    "title": openapi.Schema(type=openapi.TYPE_STRING),
                    "description": openapi.Schema(type=openapi.TYPE_STRING),
                    "destination": openapi.Schema(type=openapi.TYPE_STRING),
                    "meet_at": openapi.Schema(type=openapi.TYPE_STRING),
                    "max_users": openapi.Schema(type=openapi.TYPE_INTEGER),
                    "coordinates": openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(type=openapi.TYPE_NUMBER),
                        description="[위도, 경도] 형식의 좌표",
                    ),
                    "parking_spot": openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(type=openapi.TYPE_NUMBER),
                        description="[위도, 경도] 형식의 주차 좌표",
                    ),
                },
            ),
        ),
        500: openapi.Response(
            description="서버 오류",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={"error": openapi.Schema(type=openapi.TYPE_STRING)},
            ),
        ),
    },
)
@api_view(["POST"])
@permission_classes([AllowAny])  # 일단 모두 허용, 나중에 권한필요로 변경
@parser_classes([MultiPartParser, FormParser])
def parties_create(request):
    try:
        party = {
            "title": request.data.get("title"),
            "description": request.data.get("description"),
            "max_users": request.data.get("max_users"),
            "coordinates": [
                float(request.data.get("x_coordinate")),
                float(request.data.get("y_coordinate")),
            ],
            "destination": request.data.get("destination"),
            "meet_at": request.data.get("meet_at"),
        }

        # party["organizer_id"] = request.user.id
        party["organizer_id"] = "12b2ac5e-98f6-44be-b790-1305293b52bd"
        party["parking_spot"] = min(
            PARKING_SPOTS,
            key=lambda spot: (spot[0] - party["coordinates"][0]) ** 2
            + (spot[1] - party["coordinates"][1]) ** 2,
        )

        # 파티 생성
        party = supabase.table("parties").insert(party).execute().data[0]

        # 이미지 처리
        image_file = request.FILES.get("image")
        if image_file:
            # 파일 확장자 추출
            file_extension = image_file.name.split(".")[-1].lower()

            # 파일 데이터를 bytes로 변환
            file_content = image_file.read()

            # 이미지 ID 생성 및 파일 경로 설정
            image_id = str(uuid.uuid4())
            file_path = f"{image_id}.{file_extension}"

            # Storage에 이미지 업로드
            supabase.storage.from_("images").upload(file_path, file_content)

            # 이미지 URL 생성
            public_url = (
                f"{settings.SUPABASE_URL}/storage/v1/object/public/images/{file_path}"
            )

            # images 테이블에 정보 저장
            supabase.table("images").insert(
                {"id": image_id, "party_id": party["id"], "url": public_url}
            ).execute()

        return Response(party, status=status.HTTP_201_CREATED)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


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

import uuid

import cv2
import numpy as np
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
# @permission_classes([AllowAny])
def parties_detail(request, party_id):
    try:
        user_id = request.user.user_id
        # user_id = "12b2ac5e-98f6-44be-b790-1305293b52bd"

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
        participants_status = []
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
                participants_status.append(
                    {
                        "id": participant["user_id"],
                        "nickname": participant["nickname"],
                        "status": participant["user_id"]
                        in (party.get("omw_ids") or []),
                    }
                )

        if user_id in party["finished_ids"]:
            party["available_action"] = "PHOTO"
        elif party["state"] == 1:
            party["available_action"] = (
                "PHOTO" if user_id == party["organizer_id"] else "FINISHED"
            )
        elif [p for p in participants_status if p["status"] and p["id"] == user_id]:
            party["available_action"] = "END_RIDE"
        elif (
            user_id not in party["participant_ids"] and user_id != party["organizer_id"]
        ):
            party["available_action"] = "JOIN"
        else:
            party["available_action"] = "START_RIDE"

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
            "available_action": party["available_action"],
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
# @permission_classes([AllowAny])
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

        # 해당하는 parties의 이미지 조회
        images = (
            supabase.table("images")
            .select("*")
            .in_("party_id", [party["id"] for party in parties])
            .execute()
        )

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

            # 이미지 추가
            for image in images.data:
                if image["party_id"] == party["id"]:
                    data["image_url"] = image["url"]
                    break

            reconstructed_data.append(data)

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


def apply_frame(
    uploaded_image,
):
    """
    Places overlay image on top of the background image, respecting transparency

    Parameters:
    uploaded_image: Django UploadedFile from request.FILES
    overlay_path: Path to PNG overlay with transparency
    """
    overlay_path = "./public/gcoo_frame.png"

    # Convert Django uploaded file to numpy array
    image_bytes = uploaded_image.read()
    uploaded_image.seek(0)
    nparr = np.frombuffer(image_bytes, np.uint8)
    background = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    # Load overlay (PNG with transparency)
    overlay = cv2.imread(overlay_path, cv2.IMREAD_UNCHANGED)

    # Resize overlay to match background dimensions
    overlay_resized = cv2.resize(overlay, (background.shape[1], background.shape[0]))

    # Create mask from alpha channel
    alpha_channel = overlay_resized[:, :, 3] / 255.0
    alpha_3_channel = np.stack([alpha_channel, alpha_channel, alpha_channel], axis=2)

    # Combine images
    foreground = overlay_resized[:, :, :3]
    result = background * (1 - alpha_3_channel) + foreground * alpha_3_channel

    # Save result
    _, buffer = cv2.imencode(".png", result)
    return buffer.tobytes()


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
            "organizer_id",
            in_=openapi.IN_FORM,
            type=openapi.TYPE_STRING,
            description="주최자 UUID",
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
@permission_classes([AllowAny])
@parser_classes([MultiPartParser, FormParser])
def parties_create(request):
    try:
        party = {
            "title": request.data.get("title"),
            "description": request.data.get("description"),
            "max_users": request.data.get("max_users"),
            "organizer_id": request.data.get("organizer_id"),
            "coordinates": [
                float(request.data.get("x_coordinate")),
                float(request.data.get("y_coordinate")),
            ],
            "destination": request.data.get("destination"),
            "meet_at": request.data.get("meet_at"),
        }

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


@swagger_auto_schema(
    method="POST",
    operation_description="특정 파티에 참가합니다",
    responses={
        200: openapi.Response(
            description="성공",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "msg": openapi.Schema(
                        type=openapi.TYPE_STRING, description="성공 메시지"
                    )
                },
            ),
        ),
        400: openapi.Response(
            description="잘못된 요청",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "error": openapi.Schema(
                        type=openapi.TYPE_STRING, description="에러 메시지"
                    )
                },
            ),
        ),
        404: openapi.Response(
            description="파티를 찾을 수 없음",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "error": openapi.Schema(
                        type=openapi.TYPE_STRING, description="에러 메시지"
                    )
                },
            ),
        ),
    },
)
@api_view(["POST"])
# @permission_classes([AllowAny])
def parties_join(request, party_id):
    try:
        user_id = request.user.user_id
        # user_id = "56f9b4f6-327d-4138-b820-2d2cf54a3425"

        party = (
            supabase.table("parties")
            .select("*")
            .eq("id", party_id)
            .single()
            .execute()
            .data
        )

        if not party:
            return Response(
                {"error": "Party not found"}, status=status.HTTP_404_NOT_FOUND
            )

        if party["state"] != 0:
            return Response(
                {"error": "Party is not recruiting"}, status=status.HTTP_400_BAD_REQUEST
            )

        if party["max_users"] <= len(party["participant_ids"]):
            return Response(
                {"error": "Party is full"}, status=status.HTTP_400_BAD_REQUEST
            )

        if user_id in party["participant_ids"] or user_id == party["organizer_id"]:
            return Response(
                {"error": "User already joined"}, status=status.HTTP_400_BAD_REQUEST
            )

        party["participant_ids"].append(user_id)

        party = (
            supabase.table("parties").update(party).eq("id", party_id).execute().data[0]
        )

        return Response(
            {"msg": f"User {user_id} joined party {party_id}"},
            status=status.HTTP_200_OK,
        )
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@swagger_auto_schema(
    method="POST",
    operation_description="파티 운행을 시작합니다 (참가자가 출발했음을 표시)",
    responses={
        200: openapi.Response(
            description="성공",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "msg": openapi.Schema(
                        type=openapi.TYPE_STRING, description="성공 메시지"
                    )
                },
            ),
        ),
        400: openapi.Response(
            description="잘못된 요청",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "error": openapi.Schema(
                        type=openapi.TYPE_STRING, description="에러 메시지"
                    )
                },
            ),
        ),
        404: openapi.Response(
            description="파티를 찾을 수 없음",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "error": openapi.Schema(
                        type=openapi.TYPE_STRING, description="에러 메시지"
                    )
                },
            ),
        ),
    },
)
@api_view(["POST"])
# @permission_classes([AllowAny])
def parties_start(request, party_id):
    try:
        user_id = request.user.user_id
        # user_id = "56f9b4f6-327d-4138-b820-2d2cf54a3425"

        party = (
            supabase.table("parties")
            .select("*")
            .eq("id", party_id)
            .single()
            .execute()
            .data
        )

        if not party:
            return Response(
                {"error": "Party not found"}, status=status.HTTP_404_NOT_FOUND
            )

        if party["state"] == 1:
            return Response(
                {"error": "Party is already finished"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        party["omw_ids"].append(user_id)
        party = (
            supabase.table("parties").update(party).eq("id", party_id).execute().data[0]
        )

        return Response(
            {"msg": f"User {user_id} started party {party_id}"},
            status=status.HTTP_200_OK,
        )
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@swagger_auto_schema(
    method="POST",
    tags=["parties"],
    operation_summary="파티 종료",
    operation_description="파티를 종료하고 기념 사진을 업로드합니다.",
    consumes=["multipart/form-data"],
    manual_parameters=[
        openapi.Parameter(
            "image",
            in_=openapi.IN_FORM,
            type=openapi.TYPE_FILE,
            description="파티 기념 사진",
            required=True,
        ),
    ],
    responses={
        200: openapi.Response(
            description="종료 성공",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "url": openapi.Schema(
                        type=openapi.TYPE_STRING, description="업로드된 이미지 URL"
                    ),
                },
            ),
        ),
        400: openapi.Response(
            description="잘못된 요청",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "error": openapi.Schema(
                        type=openapi.TYPE_STRING, description="에러 메시지"
                    )
                },
            ),
        ),
        404: openapi.Response(
            description="파티를 찾을 수 없음",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "error": openapi.Schema(
                        type=openapi.TYPE_STRING, description="에러 메시지"
                    )
                },
            ),
        ),
        500: openapi.Response(
            description="서버 오류",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "error": openapi.Schema(
                        type=openapi.TYPE_STRING, description="에러 메시지"
                    )
                },
            ),
        ),
    },
)
@api_view(["POST"])
# @permission_classes([AllowAny])
@parser_classes([MultiPartParser, FormParser])
def parties_end(request, party_id):
    try:
        user_id = request.user.user_id
        # user_id = "12b2ac5e-98f6-44be-b790-1305293b52bd"

        party = (
            supabase.table("parties")
            .select("*")
            .eq("id", party_id)
            .single()
            .execute()
            .data
        )

        if not party:
            return Response(
                {"error": "Party not found"}, status=status.HTTP_404_NOT_FOUND
            )

        if party["organizer_id"] != user_id:
            return Response(
                {"error": "Only organizer can end party"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if party["state"] != 0:
            return Response(
                {"error": "Party is already finished"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        image = request.FILES.get("image")
        file_extension = image.name.split(".")[-1].lower()
        image_bytes = apply_frame(request.FILES.get("image"))
        image_id = str(uuid.uuid4())
        file_path = f"{image_id}.{file_extension}"
        upload_response = supabase.storage.from_("images").upload(
            file_path, image_bytes
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

        for omw_id in party["omw_ids"]:
            user = (
                supabase.table("users")
                .select("*")
                .eq("user_id", omw_id)
                .execute()
                .data[0]
            )
            supabase.table("users").update(
                {"level": user["level"] + 5, "num_parties": user["num_parties"] + 1}
            ).eq("user_id", omw_id).execute()

        # 파티 상태 변경
        party["state"] = 1
        party = (
            supabase.table("parties").update(party).eq("id", party_id).execute().data[0]
        )

        return Response({"url": public_url}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
# @permission_classes([AllowAny])
def parties_endride(request, party_id):
    try:
        user_id = request.user.user_id

        party = (
            supabase.table("parties")
            .select("*")
            .eq("id", party_id)
            .single()
            .execute()
            .data
        )

        if user_id in party["omw_ids"]:
            party["omw_ids"].remove(user_id)
            party["finished_ids"].append(user_id)
        party = (
            supabase.table("parties").update(party).eq("id", party_id).execute().data[0]
        )
        process_party_response(party)

        return Response(party, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@swagger_auto_schema(
    method="GET",
    tags=["parties"],
    operation_summary="내 파티 목록 조회",
    operation_description="참여했거나 주최한 파티 목록을 조회합니다.",
    responses={
        200: openapi.Response(
            description="성공",
            schema=openapi.Schema(
                type=openapi.TYPE_ARRAY,
                items=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "id": openapi.Schema(type=openapi.TYPE_STRING),
                        "created_at": openapi.Schema(type=openapi.TYPE_STRING),
                        "title": openapi.Schema(type=openapi.TYPE_STRING),
                        "destination": openapi.Schema(type=openapi.TYPE_STRING),
                        "meet_at": openapi.Schema(type=openapi.TYPE_STRING),
                        "num_participants": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "remaining_num": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "coordinates": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(type=openapi.TYPE_NUMBER),
                        ),
                        "state": openapi.Schema(type=openapi.TYPE_STRING),
                    },
                ),
            ),
        ),
        400: openapi.Response(description="잘못된 요청"),
    },
)
@api_view(["GET"])
# @permission_classes([AllowAny])
def parties_my(request):
    try:
        user_id = request.user.user_id
        # user_id = "12b2ac5e-98f6-44be-b790-1305293b52bd"

        parties = (
            supabase.table("parties")
            .select("*")
            .or_(f"organizer_id.eq.{user_id},participant_ids.cs.{{{user_id}}}")
            .order("created_at", desc=True)
            .execute()
            .data
        )

        if not parties:
            return Response([], status=status.HTTP_200_OK)

        # 이미지 데이터 조회
        images = (
            supabase.table("images")
            .select("*")
            .in_("party_id", [party["id"] for party in parties])
            .execute()
            .data
        )

        # reconstruct response
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
                "state": PARTY_STATE_MAP[party["state"]],
            }

            # 이미지 URL 추가
            for image in images:
                if image["party_id"] == party["id"]:
                    data["image_url"] = image["url"]
                    break

            reconstructed_data.append(data)

        return Response(reconstructed_data, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

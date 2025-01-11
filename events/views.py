import random
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

# Supabase 클라이언트 설정
supabase: Client = create_client(
    settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY
)


@swagger_auto_schema(
    method="GET",
    tags=["events"],
    operation_summary="이벤트 목록 조회",
    operation_description="만료되지 않은 모든 이벤트의 목록을 조회합니다.",
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
                        "host_name": openapi.Schema(type=openapi.TYPE_STRING),
                        "destination": openapi.Schema(type=openapi.TYPE_STRING),
                        "expiry": openapi.Schema(
                            type=openapi.TYPE_STRING, format="date-time"
                        ),
                        "num_started": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "num_completed": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "remaining_num": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "thumbnail_url": openapi.Schema(type=openapi.TYPE_STRING),
                        "coordinates": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(type=openapi.TYPE_NUMBER),
                            description="[위도, 경도] 형식의 좌표",
                        ),
                    },
                ),
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
@api_view(["GET"])
@permission_classes([AllowAny])  # 일단 모두 허용, 나중에 권한필요로 변경
def events_list(request):
    try:
        events = (
            supabase.table("events").select("*").order("expiry", desc=False).execute()
        )

        # 만료되지 않은 이벤트만 가져온다
        events = [
            event
            for event in events.data
            if datetime.fromisoformat(event["expiry"]) > datetime.now()
        ]

        # 해당하는 이벤트의 이미지를 가져온다
        images = (
            supabase.table("images")
            .select("*")
            .in_("event_id", [event["id"] for event in events])
            .execute()
        )

        # reconstruct response
        reconstructed_data = []
        for event in events:
            data = {
                "id": event["id"],
                "created_at": event["created_at"],
                "title": event["title"],
                "host_name": event["host_name"],
                "destination": event["destination"],
                "expiry": event["expiry"],
                "num_started": len(event["started_user_ids"]),
                "num_completed": len(event["completed_user_ids"]),
                "remaining_num": event["max_users"]
                - len(event["started_user_ids"])
                - len(event["completed_user_ids"]),
                "coordinates": event["coordinates"],
            }

            # 이미지 추가
            for image in images.data:
                if image["event_id"] == event["id"]:
                    data["image_url"] = image["url"]
                    break

            reconstructed_data.append(data)

        return Response(reconstructed_data, status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"이벤트 목록 조회 중 오류가 발생했습니다: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@swagger_auto_schema(
    method="POST",
    tags=["events"],
    operation_summary="이벤트 생성",
    operation_description="새로운 이벤트를 생성합니다.",
    consumes=["multipart/form-data"],
    manual_parameters=[
        openapi.Parameter(
            "title",
            in_=openapi.IN_FORM,
            type=openapi.TYPE_STRING,
            description="이벤트 제목",
            required=True,
        ),
        openapi.Parameter(
            "description",
            in_=openapi.IN_FORM,
            type=openapi.TYPE_STRING,
            description="이벤트 설명",
            required=True,
        ),
        openapi.Parameter(
            "host_name",
            in_=openapi.IN_FORM,
            type=openapi.TYPE_STRING,
            description="호스트 이름",
            required=True,
        ),
        openapi.Parameter(
            "destination",
            in_=openapi.IN_FORM,
            type=openapi.TYPE_STRING,
            description="이벤트 장소",
            required=True,
        ),
        openapi.Parameter(
            "expiry",
            in_=openapi.IN_FORM,
            type=openapi.TYPE_STRING,
            description="이벤트 마감 시간 (YYYY-MM-DDTHH:mm:ss 형식)",
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
            "image",
            in_=openapi.IN_FORM,
            type=openapi.TYPE_FILE,
            description="이벤트 이미지",
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
                    "host_name": openapi.Schema(type=openapi.TYPE_STRING),
                    "destination": openapi.Schema(type=openapi.TYPE_STRING),
                    "expiry": openapi.Schema(type=openapi.TYPE_STRING),
                    "max_users": openapi.Schema(type=openapi.TYPE_INTEGER),
                    "coordinates": openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(type=openapi.TYPE_NUMBER),
                        description="[위도, 경도] 형식의 좌표",
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
def events_create(request):
    try:
        data = {
            "created_at": datetime.now().isoformat(),
            "title": request.data.get("title"),
            "description": request.data.get("description"),
            "answer_key": "".join([str(random.randint(0, 9)) for _ in range(4)]),
            "started_user_ids": [],
            "completed_user_ids": [],
            "expiry": datetime.fromisoformat(request.data.get("expiry")).isoformat(),
            "host_name": request.data.get("host_name"),
            "destination": request.data.get("destination"),
            "max_users": int(request.data.get("max_users")),
            "coordinates": [
                float(request.data.get("x_coordinate")),
                float(request.data.get("y_coordinate")),
            ],
        }

        event = supabase.table("events").insert(data).execute().data[0]

        image_file = request.FILES.get("image")
        if image_file:
            # 원본 파일의 확장자 추출
            file_extension = image_file.name.split(".")[-1].lower()

            # 파일 데이터를 읽어서 bytes로 변환
            file_content = image_file.read()

            # event.id를 사용하여 파일명 생성 (원본 확장자 유지)
            image_id = str(uuid.uuid4())
            file_path = f"{image_id}.{file_extension}"
            supabase.storage.from_("images").upload(file_path, file_content)

            # 이미지 테이블에 정보 저장 (URL 구성 수정)
            public_url = (
                f"{settings.SUPABASE_URL}/storage/v1/object/public/images/{file_path}"
            )
            supabase.table("images").insert(
                {"id": image_id, "event_id": event["id"], "url": public_url}
            ).execute()

        return Response(event, status=status.HTTP_201_CREATED)
    except Exception as e:
        return Response(
            {"error": f"이벤트 생성 중 오류가 발생했습니다: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@swagger_auto_schema(
    method="GET",
    tags=["events"],
    operation_summary="이벤트 상세 조회",
    operation_description="특정 이벤트의 상세 정보를 조회합니다.",
    responses={
        200: openapi.Response(
            description="성공",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "id": openapi.Schema(type=openapi.TYPE_STRING),
                    "image_urls": openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(type=openapi.TYPE_STRING),
                    ),
                    "num_started": openapi.Schema(type=openapi.TYPE_INTEGER),
                    "num_completed": openapi.Schema(type=openapi.TYPE_INTEGER),
                    "coordinates": openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(type=openapi.TYPE_NUMBER),
                        description="[위도, 경도] 형식의 좌표",
                    ),
                },
            ),
        ),
        404: openapi.Response(
            description="이벤트를 찾을 수 없음",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={"error": openapi.Schema(type=openapi.TYPE_STRING)},
            ),
        ),
    },
)
@api_view(["GET"])
@permission_classes([AllowAny])  # 일단 모두 허용, 나중에 권한필요로 변경
def events_detail(request, event_id):
    try:
        # user_id = request.user.user_id
        user_id = "6534d0b9-694e-4458-a98f-cfa63f5ae8a6"

        event = (
            supabase.table("events")
            .select("*")
            .eq("id", event_id)
            .single()
            .execute()
            .data
        )

        if not event:
            return Response(
                {"error": f"Event with id {event_id} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        images = supabase.table("images").select("*").eq("event_id", event_id).execute()

        # 이미지가 있는 경우에만 URL 설정
        image_url = images.data[0]["url"] if images.data else None

        user_status = ""
        if user_id in event["started_user_ids"]:
            user_status = "started"
        elif user_id in event["completed_user_ids"]:
            user_status = "completed"
        else:
            user_status = "not_started"

        # reconstruct response
        result = {
            "id": event["id"],
            "host_name": event["host_name"],
            "destination": event["destination"],
            "title": event["title"],
            "description": event["description"],
            "image_url": image_url,
            "expiry": event["expiry"],
            "num_started": len(event["started_user_ids"]),
            "num_completed": len(event["completed_user_ids"]),
            "remaining_num": event["max_users"]
            - len(event["started_user_ids"])
            - len(event["completed_user_ids"]),
            "coordinates": event["coordinates"],
            "status": user_status,  # started, completed, not_started
        }

        return Response(result, status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"이벤트 상세 조회 중 오류가 발생했습니다: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@swagger_auto_schema(
    method="POST",
    tags=["events"],
    operation_summary="이벤트 참여",
    operation_description="특정 이벤트에 참여합니다.",
    responses={
        200: openapi.Response(
            description="성공",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "id": openapi.Schema(type=openapi.TYPE_STRING),
                    "started_user_ids": openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(type=openapi.TYPE_STRING),
                    ),
                },
            ),
        )
    },
)
@api_view(["POST"])
@permission_classes([AllowAny])  # 일단 모두 허용, 나중에 권한필요로 변경
def events_join(request, event_id):
    try:
        # user_id = request.user.user_id
        user_id = "56f9b4f6-327d-4138-b820-2d2cf54a3425"
        event = (
            supabase.table("events")
            .select("*")
            .eq("id", event_id)
            .single()
            .execute()
            .data
        )

        # append to started_user_ids
        event = (
            supabase.table("events")
            .update({"started_user_ids": event["started_user_ids"] + [user_id]})
            .eq("id", event_id)
            .execute()
            .data
        )

        return Response(
            {"msg": f"{user_id} joined {event_id}"}, status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {"error": f"이벤트 참여 중 오류가 발생했습니다: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@swagger_auto_schema(
    method="POST",
    tags=["events"],
    operation_summary="이벤트 완료",
    operation_description="정답을 제출하여 이벤트를 완료합니다.",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=["answer_key"],
        properties={
            "answer_key": openapi.Schema(type=openapi.TYPE_STRING),
        },
    ),
    responses={
        200: openapi.Response(
            description="성공",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "id": openapi.Schema(type=openapi.TYPE_STRING),
                    "completed_user_ids": openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(type=openapi.TYPE_STRING),
                    ),
                },
            ),
        ),
        400: openapi.Response(
            description="잘못된 답안",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={"error": openapi.Schema(type=openapi.TYPE_STRING)},
            ),
        ),
    },
)
@api_view(["POST"])
@permission_classes([AllowAny])  # 일단 모두 허용, 나중에 권한필요로 변경
def events_complete(request, event_id):
    try:
        # user_id = request.user.user_id
        user_id = "56f9b4f6-327d-4138-b820-2d2cf54a3425"
        event = (
            supabase.table("events")
            .select("*")
            .eq("id", event_id)
            .single()
            .execute()
            .data
        )

        if not event:
            return Response(
                {"error": f"Event with id {event_id} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if request.data["answer_key"] != event["answer_key"]:
            return Response(
                {"error": "Incorrect answer key"}, status=status.HTTP_400_BAD_REQUEST
            )

        # remove user from started_user_ids
        supabase.table("events").update(
            {
                "started_user_ids": [
                    user_id
                    for user_id in event["started_user_ids"]
                    if user_id != user_id
                ]
            }
        ).eq("id", event_id).execute().data
        # append user to completed_user_ids
        supabase.table("events").update(
            {"completed_user_ids": event["completed_user_ids"] + [user_id]}
        ).eq("id", event_id).execute().data

        # level 업데이트 (기존 user level의 +5)
        user = (
            supabase.table("users")
            .select("*")
            .eq("user_id", user_id)
            .single()
            .execute()
            .data
        )
        supabase.table("users").update({"level": user["level"] + 5}).eq(
            "user_id", user_id
        ).execute().data

        return Response(
            {"msg": f"{user_id} completed {event_id}"}, status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {"error": f"이벤트 완료 중 오류가 발생했습니다: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
@permission_classes([AllowAny])  # 일단 모두 허용, 나중에 권한필요로 변경
def events_my(request):
    try:
        # user_id = request.user.user_id
        user_id = "56f9b4f6-327d-4138-b820-2d2cf54a3425"

        events = (
            supabase.table("events")
            .select("*")
            .or_(
                f"started_user_ids.cs.{{{user_id}}},completed_user_ids.cs.{{{user_id}}}"
            )
            .order("expiry", desc=False)
            .execute()
            .data
        )

        # reconstruct response
        reconstructed_data = []
        for event in events:
            data = {
                "id": event["id"],
                "created_at": event["created_at"],
                "title": event["title"],
                "host_name": event["host_name"],
                "destination": event["destination"],
                "expiry": event["expiry"],
                "num_started": len(event["started_user_ids"]),
                "num_completed": len(event["completed_user_ids"]),
                "remaining_num": event["max_users"]
                - len(event["started_user_ids"])
                - len(event["completed_user_ids"]),
                "coordinates": event["coordinates"],
            }
            reconstructed_data.append(data)
        events = reconstructed_data

        return Response(events, status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"이벤트 조회 중 오류가 발생했습니다: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

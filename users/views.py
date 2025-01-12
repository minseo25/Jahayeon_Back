from django.conf import settings
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.decorators import api_view  # , permission_classes

# from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from supabase import Client, create_client

# Supabase 클라이언트 설정
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)


@swagger_auto_schema(
    methods=["GET"],
    tags=["users"],
    operation_summary="사용자 프로필 조회",
    operation_description="사용자의 프로필 정보(닉네임, 레벨, 코인, 뱃지)를 조회합니다.",
    responses={
        200: openapi.Response(
            description="성공",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "nickname": openapi.Schema(
                        type=openapi.TYPE_STRING, description="사용자 닉네임"
                    ),
                    "level": openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description="레벨 이름 (초보 라이더, 중급 라이더, 고급 라이더, 스피드 레이서)",
                    ),
                    "coins": openapi.Schema(
                        type=openapi.TYPE_INTEGER, description="보유 코인"
                    ),
                    "badges": openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            "첫 미션": openapi.Schema(type=openapi.TYPE_BOOLEAN),
                            "첫 파티": openapi.Schema(type=openapi.TYPE_BOOLEAN),
                            "당신은 지쿠인싸": openapi.Schema(
                                type=openapi.TYPE_BOOLEAN
                            ),
                            "당신은 프로미션수행러": openapi.Schema(
                                type=openapi.TYPE_BOOLEAN
                            ),
                        },
                        description="획득한 뱃지 목록",
                    ),
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
@swagger_auto_schema(
    methods=["PATCH"],
    tags=["users"],
    operation_summary="사용자 닉네임 수정",
    operation_description="사용자의 닉네임을 수정합니다.",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=["nickname"],
        properties={
            "nickname": openapi.Schema(
                type=openapi.TYPE_STRING, description="변경할 닉네임"
            ),
        },
    ),
    responses={
        200: openapi.Response(
            description="성공",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "message": openapi.Schema(
                        type=openapi.TYPE_STRING, description="성공 메시지"
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
@api_view(["GET", "PATCH"])
# @permission_classes([AllowAny])
def user_profile(request):
    if request.method == "GET":
        try:
            user_id = request.user.user_id
            # user_id = "12b2ac5e-98f6-44be-b790-1305293b52bd"
            user_data = (
                supabase.table("users").select("*").eq("user_id", user_id).execute()
            )
            if not user_data.data:
                raise Exception("사용자 정보를 찾을 수 없습니다.")

            # 레벨에 따라 레벨 이름 다르게 설정
            level = user_data.data[0]["level"]
            if level <= 10:
                level_name = "초보 라이더"
            elif level <= 50:
                level_name = "중급 라이더"
            elif level <= 100:
                level_name = "고급 라이더"
            else:
                level_name = "스피드 레이서"

            reconstructed_data = {
                "nickname": user_data.data[0]["nickname"],
                "level": level_name,
                "coins": user_data.data[0]["coins"],
                "badges": {
                    "첫 미션": user_data.data[0]["num_events"] >= 1,
                    "첫 파티": user_data.data[0]["num_parties"] >= 1,
                    "당신은 지쿠인싸": user_data.data[0]["num_parties"] >= 10,
                    "당신은 프로미션수행러": user_data.data[0]["num_events"] >= 10,
                },
            }
            return Response(reconstructed_data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {"error": f"프로필 조회 중 오류가 발생했습니다: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    elif request.method == "PATCH":
        try:
            user_id = request.user.user_id
            # user_id = "12b2ac5e-98f6-44be-b790-1305293b52bd"
            nickname = request.data.get("nickname")

            user_exists = (
                supabase.table("users").select("*").eq("user_id", user_id).execute()
            )
            if not user_exists.data:
                return Response(
                    {"error": "사용자를 찾을 수 없습니다."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # 3. 업데이트 실행
            result = (
                supabase.table("users")
                .update({"nickname": nickname})
                .eq("user_id", user_id)
                .execute()
            )

            if not result.data:
                raise Exception("닉네임 업데이트에 실패했습니다.")

            return Response(
                {"message": "닉네임이 수정되었습니다."}, status=status.HTTP_200_OK
            )
        except Exception as e:
            error_details = getattr(e, "details", str(e))
            return Response(
                {"error": f"닉네임 수정 중 오류가 발생했습니다: {error_details}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@swagger_auto_schema(
    method="GET",
    tags=["users"],
    operation_summary="사용자 활동 기록 조회",
    operation_description="사용자가 참여한 파티와 이벤트의 기록을 조회합니다.",
    responses={
        200: openapi.Response(
            description="성공",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "events": openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(type=openapi.TYPE_STRING),
                        description="참여한 이벤트 ID 목록",
                    ),
                    "parties": openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(type=openapi.TYPE_STRING),
                        description="참여한 파티 ID 목록",
                    ),
                    "total_count": openapi.Schema(
                        type=openapi.TYPE_INTEGER, description="전체 참여 횟수"
                    ),
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
@api_view(["GET"])
# @permission_classes([AllowAny])
def user_history(request):
    try:
        user_id = request.user.user_id
        # user_id = "12b2ac5e-98f6-44be-b790-1305293b52bd"

        # parties에 참여한 경우
        parties = (
            supabase.table("parties")
            .select("*")
            .or_(
                "organizer_id.eq."
                + user_id
                + ","
                + "participant_ids.cs.{"
                + user_id
                + "}",
            )
            .order("created_at", desc=True)
            .execute()
        )

        # events를 참여 완료한 경우
        events = (
            supabase.table("events")
            .select("id, created_at")
            .contains("completed_user_ids", "{" + user_id + "}")
            .order("created_at", desc=True)
            .execute()
        )

        parties_id = [party["id"] for party in parties.data]
        events_id = [event["id"] for event in events.data]

        reconstructed_data = {
            "events": events_id,
            "parties": parties_id,
            "total_count": len(events_id) + len(parties_id),
        }
        return Response(reconstructed_data, status=status.HTTP_200_OK)

    except Exception as e:
        return Response(
            {"error": f"기록 조회 중 오류가 발생했습니다: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

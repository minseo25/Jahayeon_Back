import re
import uuid

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.shortcuts import redirect
from django.utils import timezone
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from supabase import Client, create_client

# Supabase 클라이언트 설정
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)


# 일반 로그인 - 비밀번호 검증
def is_password_valid(password):
    if len(password) < 8:
        return False
    if not re.search("[a-zA-Z]", password):
        return False
    if not re.search("[0-9]", password):
        return False
    if not re.search('[!@#$%^&*(),.?":{}|<>]', password):
        return False
    return True


@swagger_auto_schema(
    method="get",
    operation_id="google_login",
    operation_description="구글 로그인",
    responses={
        302: openapi.Response(
            description="구글 인증 페이지로 리디렉션",
            headers={
                "Location": {"type": openapi.TYPE_STRING, "description": "리디렉션 URL"}
            },
        )
    },
)
@api_view(["GET"])
@permission_classes([AllowAny])
def google_login(request):
    # Supabase OAuth URL 생성
    # google을 provider로 지정하고, google 인증 후 사용자가 돌아올 redirect_uri를 지정
    redirect_uri = (
        f"{settings.FRONTEND_URL}/callback/google"  # 프론트엔드에서 지정한 콜백 URL
    )

    auth_url = f"{settings.SUPABASE_URL}/auth/v1/authorize?provider=google&redirect_to={redirect_uri}"
    return redirect(auth_url)


@swagger_auto_schema(
    method="post",
    operation_id="google_callback",
    operation_description="구글 로그인 콜백",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            "access_token": openapi.Schema(
                type=openapi.TYPE_STRING, description="구글 액세스 토큰"
            ),
        },
    ),
    responses={
        200: openapi.Response(description="로그인 성공"),
        400: openapi.Response(description="엑세스 토큰 부재"),
        500: openapi.Response(description="서버 오류"),
    },
)
@api_view(["POST"])
@permission_classes([AllowAny])
def google_callback(request):
    access_token = request.data.get("access_token")

    if not access_token:
        return Response(
            {"error": "구글 로그인 중 오류가 발생했습니다."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # 받아온 토큰으로 사용자 정보 조회
    try:
        user_data = supabase.auth.get_user(access_token)
        user_id = user_data.user.id

        # 이미 등록된 사용자인지 검색
        existing_user = (
            supabase.table("users")
            .select("*")
            .eq("user_id", user_id)
            .eq("oauth_provider", "google")
            .execute()
        )

        if not existing_user.data:
            # 새 사용자인 경우 DB에 추가
            email = user_data.user.email
            dummy_password = str(uuid.uuid4())  # 임의의 비밀번호 생성
            hashed_password = make_password(dummy_password)

            user_info = {
                "user_id": user_id,
                "email": email,
                "password": hashed_password,
                "oauth_provider": "google",
                "created_at": timezone.now().isoformat(),
                "level": 0,
                "nickname": "익명의 지바이크" + str(uuid.uuid4())[:4],
                "coins": 0,
                "num_events": 0,
                "num_parties": 0,
            }
            result = supabase.table("users").insert(user_info).execute()
            user_id = result.data[0]["user_id"]
        else:
            user_id = existing_user.data[0]["user_id"]

        # JWT 토큰 생성, for_user 메서드 사용하지 않고 수동으로 정보 추가
        refresh = RefreshToken()
        refresh["user_id"] = user_id
        refresh.set_exp(lifetime=settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"])
        access_token = refresh.access_token
        access_token.set_exp(lifetime=settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"])

        response_data = {
            "message": "로그인 되었습니다.",
            "access_token": str(access_token),
            "refresh_token": str(refresh),
        }
        return Response(response_data, status=status.HTTP_200_OK)
    except Exception:
        return Response(
            {"error": "로그인 중 오류가 발생했습니다"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@swagger_auto_schema(
    method="post",
    operation_id="token_refresh",
    operation_description="토큰 갱신",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            "refresh_token": openapi.Schema(
                type=openapi.TYPE_STRING, description="리프레시 토큰"
            ),
        },
    ),
    responses={
        200: openapi.Response(description="토큰 갱신 성공"),
        400: openapi.Response(description="리프레시 토큰 부재"),
        401: openapi.Response(description="유효하지 않거나 만료된 토큰"),
    },
)
@api_view(["POST"])
@permission_classes([AllowAny])
def token_refresh(request):
    refresh_token = request.data.get("refresh_token")
    if not refresh_token:
        return Response(
            {"error": "리프레시 토큰이 제공되지 않았습니다."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        # verify() 메서드는 RefreshToken이 instantiate될 때 자동으로 호출 (default=True)
        refresh = RefreshToken(refresh_token)
        access_token = refresh.access_token
        access_token.set_exp(lifetime=settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"])

        response_data = {
            "message": "토큰이 갱신되었습니다",
            "access_token": str(access_token),
        }
        return Response(response_data, status=status.HTTP_200_OK)
    except TokenError:
        return Response(
            {"error": "유효하지 않거나 만료된 토큰입니다."},
            status=status.HTTP_401_UNAUTHORIZED,
        )


@swagger_auto_schema(
    method="post",
    operation_id="register",
    operation_description="회원가입",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            "email": openapi.Schema(type=openapi.TYPE_STRING, description="이메일"),
            "password": openapi.Schema(
                type=openapi.TYPE_STRING, description="비밀번호"
            ),
            "full_name": openapi.Schema(type=openapi.TYPE_STRING, description="이름"),
        },
    ),
    responses={
        201: openapi.Response(description="회원가입 성공"),
        400: openapi.Response(
            description="이메일 또는 비밀번호 부재/부적절한 비밀번호/이미 등록된 이메일"
        ),
        500: openapi.Response(description="서버 오류"),
    },
)
@api_view(["POST"])
@permission_classes([AllowAny])
def register(request):
    try:
        email = request.data.get("email")
        password = request.data.get("password")
        full_name = request.data.get("full_name")

        # 필수 입력 항목 검사
        if not email or not password:
            return Response(
                {"error": "이메일과 비밀번호는 필수 입력 항목입니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not is_password_valid(password):
            return Response(
                {
                    "error": "비밀번호는 8자 이상, 영문, 숫자, 특수문자를 포함해야 합니다."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # unique 항목인 이메일 중복 검사
        existing_user = supabase.table("users").select("*").eq("email", email).execute()
        if existing_user.data:
            return Response(
                {"error": "이미 등록된 이메일입니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 중복되지 않는 uuid 생성
        while True:
            user_id = str(uuid.uuid4())
            existing_user = (
                supabase.table("users").select("*").eq("user_id", user_id).execute()
            )
            if not existing_user.data:
                break

        hashed_password = make_password(password)
        user_info = {
            "user_id": user_id,
            "email": email,
            "password": hashed_password,
            "oauth_provider": "local",
            "full_name": full_name,
            "created_at": timezone.now().isoformat(),
        }

        # 사용자 정보 저장
        result = supabase.table("users").insert(user_info).execute()

        if result.data:
            # JWT 토큰 생성, for_user 메서드 사용하지 않고 수동으로 정보 추가
            refresh = RefreshToken()
            refresh["user_id"] = user_id
            refresh.set_exp(lifetime=settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"])
            access_token = refresh.access_token
            access_token.set_exp(lifetime=settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"])

            response_data = {
                "message": "회원가입 되었습니다.",
                "access_token": str(access_token),
                "refresh_token": str(refresh),
            }
            return Response(response_data, status=status.HTTP_201_CREATED)
        else:
            return Response(
                {"error": "회원가입 실패"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    except Exception:
        return Response(
            {"error": "회원가입 중 오류가 발생했습니다"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@swagger_auto_schema(
    method="post",
    operation_id="login",
    operation_description="로그인",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            "email": openapi.Schema(type=openapi.TYPE_STRING, description="이메일"),
            "password": openapi.Schema(
                type=openapi.TYPE_STRING, description="비밀번호"
            ),
        },
    ),
    responses={
        200: openapi.Response(description="로그인 성공"),
        400: openapi.Response(
            description="이메일 또는 비밀번호 부재/비밀번호 불일치/존재하지 않는 계정"
        ),
        500: openapi.Response(description="서버 오류"),
    },
)
@api_view(["POST"])
@permission_classes([AllowAny])
def login(request):
    try:
        email = request.data.get("email")
        password = request.data.get("password")

        if not email or not password:
            return Response(
                {"error": "이메일과 비밀번호는 필수 입력 항목입니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user_data = supabase.table("users").select("*").eq("email", email).execute()

        if not user_data.data:
            return Response(
                {"error": "존재하지 않는 계정입니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = user_data.data[0]
        if not check_password(password, user["password"]):
            return Response(
                {"error": "비밀번호가 일치하지 않습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # JWT 토큰 생성, for_user 메서드 사용하지 않고 수동으로 정보 추가
        refresh = RefreshToken()
        refresh["user_id"] = user["user_id"]
        refresh.set_exp(lifetime=settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"])
        access_token = refresh.access_token
        access_token.set_exp(lifetime=settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"])

        response_data = {
            "message": "로그인 되었습니다.",
            "access_token": str(access_token),
            "refresh_token": str(refresh),
        }
        return Response(response_data, status=status.HTTP_200_OK)
    except Exception:
        return Response(
            {"error": "로그인 중 오류가 발생했습니다"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@swagger_auto_schema(
    method="post",
    operation_id="logout",
    operation_description="로그아웃",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            "refresh_token": openapi.Schema(
                type=openapi.TYPE_STRING, description="리프레시 토큰"
            ),
        },
    ),
    responses={
        200: openapi.Response(description="로그아웃 성공"),
        400: openapi.Response(description="리프레시 토큰 부재"),
        500: openapi.Response(description="서버 오류"),
    },
)
@api_view(["POST"])
def logout(request):
    try:
        refresh_token = request.data.get("refresh_token")
        if not refresh_token:
            return Response(
                {
                    "error": "로그아웃 중 오류가 발생했습니다.",
                    "detail": "refresh_token이 없습니다.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 토큰을 블랙리스트에 등록함으로써 무효화
        refresh = RefreshToken(refresh_token)
        refresh.blacklist()

        return Response(
            {
                "message": "로그아웃 되었습니다.",
            },
            status=status.HTTP_200_OK,
        )

    except Exception:
        return Response(
            {"error": "로그아웃 중 오류가 발생했습니다"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# access token과 refresh token의 만료 여부는 백엔드에서 확인함
# 로그인 상태를 확인하기 위해 인증이 필요한 엔드포인트에 요청을 보내어 확인함, 응답에 따라 프론트엔드에서 로그인 상태를 업데이트함
@swagger_auto_schema(
    method="get",
    operation_id="user_info",
    operation_description="사용자 정보 조회",
    responses={
        200: openapi.Response(description="사용자 정보 조회 성공"),
        401: openapi.Response(description="인증 실패"),
    },
)
@api_view(["GET"])
def user_info(request):
    try:
        user = request.user
        return Response(
            {
                "email": user.email,
                "full_name": user.full_name,
                "oauth_provider": user.oauth_provider,
            },
            status=status.HTTP_200_OK,
        )
    except Exception:
        return Response(
            {"error": "사용자 정보 조회 중 오류가 발생했습니다"},
            status=status.HTTP_401_UNAUTHORIZED,
        )

import base64

import google.generativeai as genai
from django.conf import settings
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from openai import OpenAI
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

# API 클라이언트 초기화
openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
genai.configure(api_key=settings.GOOGLE_API_KEY)


def generate_response(provider, prompt, image_file=None, model_name=None):
    """API를 사용하여 응답 생성"""
    try:
        if provider == "openai":
            if image_file:
                base64_image = base64.b64encode(image_file.read()).decode("utf-8")
                response = openai_client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{base64_image}",
                                    },
                                },
                            ],
                        }
                    ],
                    max_tokens=1000,
                )
            else:
                response = openai_client.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.7,
                    max_tokens=1000,
                )
            return response.choices[0].message.content
        elif provider == "google":
            if image_file:
                base64_image = base64.b64encode(image_file.read()).decode("utf-8")
                model = genai.GenerativeModel(model_name=model_name)
                response = model.generate_content(
                    [{"mime_type": "image/jpeg", "data": base64_image}, prompt]
                )
            else:
                model = genai.GenerativeModel(model_name=model_name)
                response = model.generate_content(prompt)
            return response.text
        return None
    except Exception as e:
        print(f"{provider} API 응답 생성 중 오류 발생: {e}")
        return None


@swagger_auto_schema(
    method="post",
    operation_description="OpenAI 모델을 사용하여 텍스트 및 이미지 파일(optional)을 업로드합니다.",
    consumes=["multipart/form-data"],
    manual_parameters=[
        openapi.Parameter(
            "text",
            in_=openapi.IN_FORM,
            type=openapi.TYPE_STRING,
            description="텍스트 입력",
            required=True,
        ),
        openapi.Parameter(
            "image",
            in_=openapi.IN_FORM,
            type=openapi.TYPE_FILE,
            description="이미지 파일 (optional)",
            required=False,
        ),
    ],
    responses={
        200: openapi.Response(
            "응답",
            openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "response": openapi.Schema(
                        type=openapi.TYPE_STRING, description="생성된 응답"
                    ),
                },
            ),
        ),
        500: openapi.Response(description="서버 오류"),
    },
)
@api_view(["POST"])
@permission_classes(
    [AllowAny]
)  # 일단 모든 사용자가 사용할 수 있도록 설정, 추후 제거 예정
@parser_classes([MultiPartParser, FormParser])
def gpt_generate(request):
    try:
        text = request.data.get("text")
        image_file = request.FILES.get("image")  # 이미지 파일 객체
        model_name = "gpt-4o-mini"
        provider = "openai"

        result = generate_response(
            provider, text, image_file=image_file, model_name=model_name
        )
        return Response({"response": result}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"GPT 요청 처리 중 오류가 발생했습니다: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@swagger_auto_schema(
    method="post",
    operation_description="Google 모델을 사용하여 텍스트 및 이미지(optional)를 기반으로 응답을 생성합니다.",
    consumes=["multipart/form-data"],
    manual_parameters=[
        openapi.Parameter(
            "text",
            in_=openapi.IN_FORM,
            type=openapi.TYPE_STRING,
            description="텍스트 입력",
            required=True,
        ),
        openapi.Parameter(
            "image",
            in_=openapi.IN_FORM,
            type=openapi.TYPE_FILE,
            description="이미지 파일 (optional)",
            required=False,
        ),
    ],
    responses={
        200: openapi.Response(
            "응답",
            openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "response": openapi.Schema(
                        type=openapi.TYPE_STRING, description="생성된 응답"
                    ),
                },
            ),
        ),
        500: openapi.Response(description="서버 오류"),
    },
)
@api_view(["POST"])
@permission_classes(
    [AllowAny]
)  # 일단 모든 사용자가 사용할 수 있도록 설정, 추후 제거 예정
@parser_classes([MultiPartParser, FormParser])
def gemini_generate(request):
    try:
        text = request.data.get("text")
        image_file = request.FILES.get("image")  # 이미지 파일 객체
        model_name = "gemini-2.0-flash-exp"
        provider = "google"

        result = generate_response(
            provider, text, image_file=image_file, model_name=model_name
        )
        return Response({"response": result}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": f"Gemini 요청 처리 중 오류가 발생했습니다: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

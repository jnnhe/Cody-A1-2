import argparse
import json
import os
import sys
from dotenv import load_dotenv
from google import genai
from google.genai import types
import requests

# .env 파일 로드
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
KAKAO_REST_API_KEY = os.getenv("KAKAO_REST_API_KEY")

if not GEMINI_API_KEY or not KAKAO_REST_API_KEY:
  print("❌ 오류: .env 파일에 API 키가 설정되지 않았습니다.")
  sys.exit(1)

client = genai.Client(api_key=GEMINI_API_KEY)


def get_travel_itinerary(travel_date: str, errors: list):
  """Gemini API를 이용해 날짜별 상세 여행 코스를 JSON 형태로 추천받습니다."""
  prompt = f"""
    여행 날짜: {travel_date}
    이 날짜에 여행하기 좋은 국내 도시 한 곳을 추천하고, 아래 최소 JSON 스키마 형식에 맞춰서만 응답해 주세요. 다른 마크다운이나 일반 텍스트 설명 없이 오직 JSON 객체 형태로만 출력해 주세요.

    반드시 지켜야 할 JSON 스키마:
    {{
      "recommended_city": "string (예: 제주, 강릉)",
      "weather": "string (해당 시기 일반적 날씨 요약)",
      "events": ["행사/축제 후보 1", "행사/축제 후보 2"],
      "reason": "string (추천 근거 2~4문장)"
    }}
    """

  for attempt in range(2):
    try:
      response = client.models.generate_content(
          model="gemini-3.6-flash",
          contents=prompt,
      )
      raw_text = response.text.strip()
      if raw_text.startswith("```json"):
        raw_text = raw_text[7:]
      if raw_text.endswith("```"):
        raw_text = raw_text[:-3]

      data = json.loads(raw_text.strip())
      return data
    except Exception as e:
      if attempt == 0:
        errors.append(f"Gemini JSON 파싱 1차 실패, 재시도 중: {e}")
        prompt += "\n주의: 반드시 유효한 JSON 형식만 출력하세요."
      else:
        errors.append(f"Gemini JSON 파싱 최종 실패: {e}")
        return {
            "recommended_city": "제주",
            "weather": "정보 없음",
            "events": ["정보 없음"],
            "reason": (
                "LLM 응답 파싱 실패로 인해 기본 도시(제주)로 대체되었습니다."
            ),
        }


def search_kakao_place(query: str, errors: list):
  """Kakao Local API를 이용해 특정 키워드의 장소를 검색합니다."""
  url = "https://dapi.kakao.com/v2/local/search/keyword.json"
  api_key = KAKAO_REST_API_KEY.strip()
  headers = {"Authorization": f"KakaoAK {api_key}"}
  params = {"query": query, "size": 3}

  try:
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    data = response.json()
    documents = data.get("documents", [])
    if not documents:
      errors.append(f"Kakao 검색 결과 없음: '{query}'")
    return documents
  except requests.exceptions.HTTPError as http_err:
    status_code = (
        http_err.response.status_code if http_err.response else "알 수 없음"
    )
    if status_code in [401, 403]:
      errors.append(
          f"Kakao API 인증/권한 오류 ({status_code}) - 키 또는 도메인/서비스 설정"
          f" 점검 필요: {query}"
      )
    else:
      errors.append(f"Kakao API HTTP 오류 ({status_code}): {query}")
    return []
  except Exception as e:
    errors.append(f"Kakao API 요청 중 네트워크/기타 오류 ({query}): {e}")
    return []


def main():
  parser = argparse.ArgumentParser(description="AI 구조화된 여행 플래너")
  parser.add_argument(
      "-date", type=str, required=True, help="여행 날짜 (예: 2026-09-08)"
  )
  args = parser.parse_args()

  runtime_errors = []

  print(f"[1/3] '{args.date}' 기준 맞춤형 여행 일정 데이터 수집 중 (Gemini)...")
  itinerary_data = get_travel_itinerary(args.date, runtime_errors)

  city = itinerary_data.get("recommended_city", "제주")
  weather = itinerary_data.get("weather", "정보 없음")
  events = itinerary_data.get("events", [])
  reason = itinerary_data.get("reason", "정보 없음")

  print(f" - 선정된 도시: {city}\n")

  print(f"[2/3] '{city}' 주요 장소 및 맛집 정보 매칭 중 (Kakao)...")
  morning_places = search_kakao_place(f"{city} 관광지", runtime_errors)
  lunch_places = search_kakao_place(f"{city} 맛집", runtime_errors)
  dinner_places = search_kakao_place(f"{city} 저녁 맛집", runtime_errors)

  markdown_content = f"# ✈️ AI 맞춤 여행 계획서 ({args.date})\n\n"
  markdown_content += "## 📌 여행지 개요 및 추천 근거\n"
  markdown_content += f"- **추천 도시**: {city}\n"
  markdown_content += f"- **예상 날씨**: {weather}\n"
  markdown_content += (
      f"- **지역 행사/축제**: {', '.join(events) if events else '없음'}\n"
  )
  markdown_content += f"- **추천 근거**: {reason}\n\n"
  markdown_content += "---\n\n"

  markdown_content += f"## 🗺️ 카카오 연동 실시간 추천 장소 ({city})\n\n"

  markdown_content += "### ☀️ 오전 추천 관광지\n"
  if morning_places:
    for p in morning_places:
      name = p.get("place_name")
      addr = p.get("road_address_name") or p.get("address_name")
      phone = p.get("phone", "번호 없음")
      markdown_content += f"- **{name}** | 주소: {addr} | 연락처: {phone}\n"
  else:
    markdown_content += "- 데이터 없음\n"

  markdown_content += "\n### 🍽️ 추천 점심 맛집\n"
  if lunch_places:
    for p in lunch_places:
      name = p.get("place_name")
      addr = p.get("road_address_name") or p.get("address_name")
      phone = p.get("phone", "번호 없음")
      markdown_content += f"- **{name}** | 주소: {addr} | 연락처: {phone}\n"
  else:
    markdown_content += "- 데이터 없음\n"

  markdown_content += "\n### 🌙 추천 저녁 맛집\n"
  if dinner_places:
    for p in dinner_places:
      name = p.get("place_name")
      addr = p.get("road_address_name") or p.get("address_name")
      phone = p.get("phone", "번호 없음")
      markdown_content += f"- **{name}** | 주소: {addr} | 연락처: {phone}\n"
  else:
    markdown_content += "- 데이터 없음\n"

  # 에러가 있을 때만 마크다운에 에러 섹션 추가
  if runtime_errors:
    markdown_content += "\n---\n\n"
    markdown_content += "## ⚠️ 실행 중 발생한 오류 요약 (Errors)\n"
    for err in runtime_errors:
      markdown_content += f"- {err}\n"

  filename = f"travel_plan_{args.date}.md"
  with open(filename, "w", encoding="utf-8") as f:
    f.write(markdown_content)

  print(f"\n[3/3] 🎉 여행 계획서가 '{filename}' 파일로 성공적으로 생성되었습니다!")
  if runtime_errors:
    print(
        f"⚠️ 실행 중 {len(runtime_errors)}개의 경고/오류가 발생했으나 리포트"
        " 생성이 완료되었습니다."
    )
  else:
    print("✨ 어떠한 오류도 없이 완벽하게 실행되었습니다!")


if __name__ == "__main__":
  main()
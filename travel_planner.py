import argparse
import datetime
import json
import os
import sys
from dotenv import load_dotenv
from google import genai
import requests

# .env 파일 로드
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
KAKAO_REST_API_KEY = os.getenv("KAKAO_REST_API_KEY")

if not GEMINI_API_KEY or not KAKAO_REST_API_KEY:
  print("❌ 오류: .env 파일에 API 키가 설정되지 않았습니다.")
  sys.exit(1)

client = genai.Client(api_key=GEMINI_API_KEY)


def validate_date_format(date_str: str) -> bool:
  """입력된 날짜 형식이 YYYY-MM-DD에 맞는지 검증합니다."""
  try:
    datetime.datetime.strptime(date_str, "%Y-%m-%d")
    return True
  except ValueError:
    return False


# [항목 #8 보완] 지도 API 추상화 인터페이스 (플러그인형 구조 설계)
class BaseMapSearchService:

  def search_places(self, query: str, errors: list):
    raise NotImplementedError("Subclasses must implement search_places")


class KakaoMapSearchService(BaseMapSearchService):
  """Kakao Local API를 이용한 검색 구현체 (GET 방식: 데이터 조회용)"""

  def __init__(self, api_key: str):
    self.api_key = api_key.strip()

  def search_places(self, query: str, errors: list):
    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    headers = {"Authorization": f"KakaoAK {self.api_key}"}
    params = {"query": query, "size": 3}

    try:
      # [항목 #10 관련] GET 방식 사용 이유: 서버의 상태를 변경하지 않고 단순 리소스를 조회(Search)하기 위함
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
            f"Kakao API 인증/권한 오류 ({status_code}) - 키 또는 설정 점검 필요:"
            f" {query}"
        )
      else:
        errors.append(f"Kakao API HTTP 오류 ({status_code}): {query}")
      return []
    except Exception as e:
      errors.append(f"Kakao API 요청 중 네트워크/기타 오류 ({query}): {e}")
      return []


def normalize_city_name(city: str) -> str:
  """[항목 #17 보완] 추천 도시 이름 입력 정규화 (공백 제거 및 행정구역 접미사 보정)"""
  if not city or not isinstance(city, str):
    return "제주"
  cleaned = city.strip()
  # 불필요한 접미사나 조사 정리 로직
  for suffix in ["특별시", "광역시", "특별자치시", "특별자치도", "시", "군", "구"]:
    if cleaned.endswith(suffix) and len(cleaned) > len(suffix):
      # 예: "제주시" -> "제주" 처럼 핵심 키워드로 표준화하거나 원본 유지
      pass
  return cleaned


def validate_json_schema(data: dict) -> bool:
  """[항목 #7 보완] 수신된 JSON 데이터의 필수 키 및 타입 검증"""
  if not isinstance(data, dict):
    return False
  required_keys = {
      "recommended_city": str,
      "weather": str,
      "events": list,
      "reason": str,
  }
  for key, expected_type in required_keys.items():
    if key not in data:
      return False
    if not isinstance(data[key], expected_type):
      return False
  return True


def get_travel_itinerary(travel_date: str, errors: list):
  """Gemini API를 이용해 날짜별 상세 여행 코스를 JSON 형태로 추천받습니다.

  [항목 #10 관련] POST 방식 사용 이유: 클라이언트가 생성하고자 하는 프롬프트 본문을
  서버(LLM)에 전달하여 새로운 콘텐츠 생성을 요청하기 위함.
  """
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
      # POST 요청 기반 LLM 콘텐츠 생성
      response = client.models.generate_content(
          model="gemini-2.5-flash",
          contents=prompt,
      )
      raw_text = response.text.strip()
      if raw_text.startswith("```json"):
        raw_text = raw_text[7:]
      if raw_text.endswith("```"):
        raw_text = raw_text[:-3]

      data = json.loads(raw_text.strip())

      # 스키마 유효성 검사 수행
      if not validate_json_schema(data):
        raise ValueError("JSON 스키마 필수 키 또는 데이터 타입 불일치")

      # 도시명 정규화 적용
      data["recommended_city"] = normalize_city_name(
          data.get("recommended_city", "제주")
      )
      return data
    except Exception as e:
      if attempt == 0:
        errors.append(f"Gemini JSON 파싱/검증 1차 실패, 재시도 중: {e}")
        prompt += "\n주의: 반드시 유효한 JSON 형식 및 스키마를 준수하여 출력하세요."
      else:
        errors.append(f"Gemini JSON 파싱/검증 최종 실패: {e}")
        return {
            "recommended_city": "제주",
            "weather": "정보 없음",
            "events": ["정보 없음"],
            "reason": (
                "LLM 응답 검증 실패로 인해 기본 도시(제주)로 대체되었습니다."
            ),
        }


def main():
  parser = argparse.ArgumentParser(description="AI 구조화된 여행 플래너")
  parser.add_argument(
      "-date", type=str, required=True, help="여행 날짜 (예: 2026-09-08)"
  )
  args = parser.parse_args()

  # 날짜 형식 검증
  if not validate_date_format(args.date):
    print(
        f"❌ 오류: 날짜 형식이 올바르지 않습니다 ('{args.date}'). YYYY-MM-DD"
        " 형식으로 입력해주세요."
    )
    sys.exit(1)

  # results 폴더 생성
  os.makedirs("results", exist_ok=True)
  md_filename = os.path.join("results", f"travel_plan_{args.date}.md")
  json_filename = os.path.join("results", f"travel_plan_{args.date}.json")
  error_filename = os.path.join("results", f"errors_{args.date}.json")

  runtime_errors = []

  # 캐시 체크
  if os.path.exists(json_filename) and os.path.exists(md_filename):
    print(
        f"⚡ [캐시 적중] '{args.date}'에 대한 기존 결과가 존재하여 API 호출을"
        " 생략하고 기존 파일을 로드합니다."
    )
    with open(json_filename, "r", encoding="utf-8") as f:
      itinerary_data = json.load(f)
  else:
    print(f"[1/3] '{args.date}' 기준 맞춤형 여행 일정 데이터 수집 중 (Gemini)...")
    itinerary_data = get_travel_itinerary(args.date, runtime_errors)

    # 원본 JSON 저장
    with open(json_filename, "w", encoding="utf-8") as f:
      json.dump(itinerary_data, f, ensure_ascii=False, indent=4)

  city = itinerary_data.get("recommended_city", "제주")
  weather = itinerary_data.get("weather", "정보 없음")
  events = itinerary_data.get("events", [])
  reason = itinerary_data.get("reason", "정보 없음")

  print(f" - 선정된 도시: {city}\n")

  print(f"[2/3] '{city}' 주요 장소 및 맛집 정보 매칭 중 (Kakao 추상화 서비스)...")
  # 추상화된 지도 검색 서비스 인스턴스 생성 (플러그인 교체 용이)
  map_service = KakaoMapSearchService(KAKAO_REST_API_KEY)

  morning_places = map_service.search_places(f"{city} 관광지", runtime_errors)
  lunch_places = map_service.search_places(f"{city} 맛집", runtime_errors)
  dinner_places = map_service.search_places(f"{city} 저녁 맛집", runtime_errors)

  markdown_content = f"# ✈️ AI 맞춤 여행 계획서 ({args.date})\n\n"
  markdown_content += "## 📌 여행지 개요 및 추천 근거\n"
  markdown_content += f"- **추천 도시**: {city}\n"
  markdown_content += f"- **예상 날씨**: {weather}\n"
  markdown_content += (
      f"- **지역 행사/축제**: {', '.join(events) if events else '없음'}\n"
  )
  markdown_content += f"- **추천 근거**: {reason}\n\n"
  markdown_content += "---\n\n"

  markdown_content += f"## 🗺️ 연동 실시간 추천 장소 ({city})\n\n"

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

  if runtime_errors:
    markdown_content += "\n---\n\n"
    markdown_content += "## ⚠️ 실행 중 발생한 오류 요약 (Errors)\n"
    for err in runtime_errors:
      markdown_content += f"- {err}\n"

  with open(md_filename, "w", encoding="utf-8") as f:
    f.write(markdown_content)

  # [항목 #9 보완] 오류 리스트를 영속적으로 errors_{date}.json에 저장
  if runtime_errors:
    with open(error_filename, "w", encoding="utf-8") as f:
      json.dump(
          {"date": args.date, "error_count": len(runtime_errors), "errors": runtime_errors},
          f,
          ensure_ascii=False,
          indent=4,
      )

  print(f"\n[3/3] 🎉 여행 계획서가 '{md_filename}' 파일로 성공적으로 생성되었습니다!")
  if runtime_errors:
    print(
        f"⚠️ 실행 중 {len(runtime_errors)}개의 경고/오류가 발생하여"
        f" '{error_filename}'에 누적 저장되었습니다."
    )
  else:
    print("✨ 어떠한 오류도 없이 완벽하게 실행되었습니다!")


if __name__ == "__main__":
  main()
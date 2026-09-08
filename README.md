# ✈️ AI 기반 구조화된 여행 플래너 (AI Travel Planner)

Gemini API와 Kakao Local API를 결합하여 특정 날짜에 최적화된 맞춤형 여행 코스를 자동 생성하고 Markdown 및 JSON 리포트로 저장하는 파이썬 기반 자동화 툴입니다.

---

## 🏗️ 시스템 아키텍처 및 데이터 흐름 (Workflow)
1. **입력 (Input)**: CLI 인자(`-date YYYY-MM-DD`)를 통해 여행 날짜를 전달받고 날짜 정규화 검증을 거칩니다.
2. **캐시 확인 (Cache Check)**: `results/` 폴더 내에 동일 날짜 데이터가 존재하는지 확인하여 불필요한 API 호출을 최적화합니다.
3. **LLM 처리 (Gemini API / POST)**: 지정된 날짜에 적합한 도시와 여행 정보를 구조화된 JSON 형태로 요청합니다. (후처리 및 구조화된 데이터 처리를 위해 JSON 강제 출력 스키마 적용)
4. **장소 연동 (Kakao Local API / GET)**: LLM이 추천한 도시 이름을 바탕으로 카카오 키워드 검색 API를 호출하여 실시간 관광지 및 맛집 정보를 매칭합니다.
5. **결과 출력 (Output Storage)**: 원본 JSON 데이터와 가독성이 높은 Markdown 리포트를 `results/` 디렉토리에 안전하게 저장합니다.

---

## 🔒 환경 변수 및 보안 관리 (.env)
- 본 프로젝트는 API 키의 소스 코드 내 하드코딩을 방지하기 위해 `python-dotenv`를 사용합니다.
- `.env` 파일 내부에 `GEMINI_API_KEY`와 `KAKAO_REST_API_KEY`를 보관하며, `.gitignore` 설정을 통해 원격 저장소(GitHub) 유출을 원천 차단합니다.

---

## 🚀 사용 방법 (Usage)

1. 의존성 패키지 설치:
   ```bash
   pip install google-genai requests python-dotenv
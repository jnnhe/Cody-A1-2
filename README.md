# ✈️ AI 기반 구조화된 여행 플래너 (AI Travel Planner)

Gemini API와 Kakao Local API를 결합하여 특정 날짜에 최적화된 맞춤형 여행 코스를 자동 생성하고 Markdown 및 JSON 리포트로 저장하는 파이썬 기반 자동화 툴입니다.

---

## 🏗️ 시스템 아키텍처 및 데이터 흐름 (Workflow)
1. **입력 및 검증 (Input & Validation)**: CLI 인자(`-date YYYY-MM-DD`)를 통해 여행 날짜를 전달받고 날짜 정규화 검증을 거칩니다.
2. **캐시 확인 (Cache Check)**: `results/` 폴더 내에 동일 날짜 데이터가 존재하는지 확인하여 불필요한 API 호출을 최적화합니다.
3. **LLM 처리 및 스키마 검증 (Gemini API / POST)**: 
   - 지정된 날짜에 적합한 도시와 정보를 구조화된 JSON 형태로 요청합니다.
   - 수신된 JSON 데이터에 대해 `validate_json_schema()`를 통해 필수 키 및 타입 정합성을 검증합니다.
   - 도시명 입력 정규화(`normalize_city_name`)를 거쳐 표준화합니다.
4. **지도 API 추상화 레이어 (Kakao API / GET)**: 
   - `BaseMapSearchService` 인터페이스와 `KakaoMapSearchService` 구현체를 통해 플러그인형 구조로 설계되어 향후 네이버 지도나 구글 맵으로 쉽게 교체할 수 있습니다.
5. **결과 및 오류 영속 저장 (Output & Error Storage)**: 
   - 원본 JSON 데이터는 `results/travel_plan_{date}.json`, 최종 리포트는 `results/travel_plan_{date}.md`로 저장합니다.
   - 런타임 에러 발생 시 `results/errors_{date}.json`에 영속적으로 누적 저장합니다.

---

## 🌐 HTTP 메서드 (GET / POST) 사용 이유
- **GET 방식 (Kakao Local API)**: 서버의 상태를 변경하지 않고, 키워드 검색을 통해 단순 데이터를 조회(Search)하기 위해 사용합니다.
- **POST 방식 (Gemini API)**: 클라이언트가 생성할 프롬프트 본문과 복잡한 요청 바디를 서버에 전송하여 새로운 구조화된 텍스트 및 JSON 콘텐츠 생성을 요청하기 위해 사용합니다.

---

## 🔒 환경 변수 및 보안 관리 (.env)
- 본 프로젝트는 API 키의 소스 코드 내 하드코딩을 방지하기 위해 `python-dotenv`를 사용합니다.
- `.env` 파일 내부에 `GEMINI_API_KEY`와 `KAKAO_REST_API_KEY`를 보관하며, `.gitignore` 설정을 통해 원격 저장소(GitHub) 유출을 원천 차단합니다.
- **운영 환경 권장사항**: CI/CD 파이프라인(GitHub Actions 등) 구축 시 소스 코드 대신 **GitHub Secrets**에 키를 등록하여 안전하게 주입해야 합니다.

---

## 🛠️ 디버깅 및 트러블슈팅 체크리스트 (401/403 오류 대응)
1. **API 키 유효성**: `.env` 파일에 키가 공백 없이 정확히 입력되었는지 확인 (`load_dotenv()` 로드 상태 점검).
2. **Kakao API 설정**: 카카오 개발자 콘솔에서 해당 REST API 키가 활성화되어 있는지, 허용된 도메인/IP 설정이 올바른지 점검.
3. **요청 헤더 확인**: `Authorization: KakaoAK {API_KEY}` 형식의 헤더가 정상적으로 전달되는지 로그를 통해 확인.

---

## 🚀 사용 방법 (Usage)

1. 의존성 패키지 설치:
   ```bash
   pip install google-genai requests python-dotenv
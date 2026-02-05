# GitHub Actions 설정 가이드

이 문서는 Paper Digest AI Agent를 GitHub Actions에서 자동으로 실행하기 위한 설정 방법을 설명합니다.

## 목차

1. [사전 요구사항](#사전-요구사항)
2. [GitHub Secrets 설정](#github-secrets-설정)
3. [워크플로우 설정](#워크플로우-설정)
4. [수동 실행 방법](#수동-실행-방법)
5. [자동 스케줄 실행](#자동-스케줄-실행)
6. [문제 해결](#문제-해결)

---

## 사전 요구사항

- GitHub 계정
- 이 저장소를 Fork하거나 Clone한 본인의 GitHub 저장소
- 이메일 주소 (PubMed API 접근용)

---

## GitHub Secrets 설정

GitHub Actions에서 실행하려면 반드시 **Secrets**를 설정해야 합니다.

### 필수 Secret

| Secret 이름 | 설명 | 필수 여부 |
|------------|------|----------|
| `PUBMED_EMAIL` | PubMed API 접근 및 Unpaywall API용 이메일 | **필수** |

### 선택적 Secrets (클라우드 LLM 사용 시)

기본적으로 GitHub Actions는 **Ollama**를 자동 설치하여 사용합니다.
클라우드 LLM API를 사용하고 싶다면 아래 시크릿을 설정하세요.

| Secret 이름 | 설명 | 필수 여부 |
|------------|------|----------|
| `ANTHROPIC_API_KEY` | Claude API 키 | 선택 |
| `OPENAI_API_KEY` | OpenAI API 키 | 선택 |
| `GOOGLE_API_KEY` | Google Gemini API 키 | 선택 |

### Secret 설정 방법

1. GitHub 저장소 페이지로 이동합니다.

2. 상단 메뉴에서 **Settings** 클릭

   ![Settings](https://docs.github.com/assets/images/help/repository/repo-actions-settings.png)

3. 왼쪽 사이드바에서 **Secrets and variables** → **Actions** 클릭

4. **New repository secret** 버튼 클릭

5. Secret 정보 입력:
   - **Name**: `PUBMED_EMAIL`
   - **Secret**: 본인 이메일 주소 (예: `myemail@example.com`)

6. **Add secret** 버튼 클릭

7. 설정 완료 확인:
   ```
   Repository secrets
   ├── PUBMED_EMAIL ✓
   └── (선택적) ANTHROPIC_API_KEY, OPENAI_API_KEY, GOOGLE_API_KEY
   ```

---

## 워크플로우 설정

### 기본 설정

워크플로우 파일은 `.github/workflows/paper_scraper.yml`에 위치합니다.

### LLM 설정

GitHub Actions에서는 **Ollama**가 자동으로 설치되어 사용됩니다.

- 모델: `llama3.1:8b` (약 4GB)
- 첫 실행 시 모델 다운로드에 5-10분 소요
- 이후 실행에서는 캐시된 모델 사용 (빠름)

### config.yaml 설정

`config/config.yaml` 파일에서 LLM 설정이 다음과 같이 되어 있어야 합니다:

```yaml
ai:
  llm_provider: ollama  # GitHub Actions에서 Ollama 사용
  ollama:
    model: llama3.1:8b
    base_url: http://localhost:11434
    max_tokens: 4096
```

---

## 수동 실행 방법

### GitHub에서 직접 실행

1. GitHub 저장소 페이지로 이동

2. **Actions** 탭 클릭

3. 왼쪽에서 **Paper Digest** 워크플로우 선택

4. **Run workflow** 버튼 클릭

5. 옵션 설정 (선택사항):
   - **Maximum papers to process**: 처리할 최대 논문 수 (기본: 5)
   - **Days to look back**: 검색할 기간 (기본: 7일)

6. **Run workflow** 버튼 클릭하여 실행

### 실행 결과 확인

1. **Actions** 탭에서 실행 중인 워크플로우 클릭

2. 각 단계별 로그 확인 가능

3. 완료 후 **Artifacts** 섹션에서 결과물 다운로드:
   - `paper-digest-report`: PDF 리포트
   - `paper-digest-html`: HTML 리포트
   - `obsidian-notes`: Obsidian 마크다운 노트

---

## 자동 스케줄 실행

기본적으로 **매주 수요일 오전 9시 (한국 시간)**에 자동 실행됩니다.

### 스케줄 변경 방법

`.github/workflows/paper_scraper.yml` 파일의 `cron` 설정을 수정하세요:

```yaml
on:
  schedule:
    # 매주 수요일 오전 9시 (한국 시간) = UTC 0시
    - cron: '0 0 * * 3'
```

### Cron 표현식 예시

| 표현식 | 설명 |
|--------|------|
| `0 0 * * 3` | 매주 수요일 오전 9시 (KST) |
| `0 0 * * 1,3,5` | 월, 수, 금 오전 9시 (KST) |
| `0 0 * * *` | 매일 오전 9시 (KST) |
| `0 0 1 * *` | 매월 1일 오전 9시 (KST) |

> **참고**: GitHub Actions의 cron은 UTC 기준입니다. 한국 시간(KST)은 UTC+9입니다.

---

## 문제 해결

### 1. "PUBMED_EMAIL secret is required" 에러

```
❌ ERROR: PUBMED_EMAIL secret is required but not set!
```

**해결 방법**: [GitHub Secrets 설정](#github-secrets-설정) 섹션을 참고하여 `PUBMED_EMAIL` 시크릿을 설정하세요.

### 2. Ollama 모델 다운로드 실패

```
Error: failed to pull model
```

**해결 방법**:
- GitHub Actions 재실행 (일시적인 네트워크 문제일 수 있음)
- 더 작은 모델 사용 (`llama3.2:3b` 등)

### 3. 실행 시간 초과 (Timeout)

GitHub Actions 무료 플랜은 작업당 최대 6시간입니다.

**해결 방법**:
- `max_papers` 값을 줄이세요 (예: 3개)
- 더 작은 모델 사용

### 4. "No papers found" 메시지

**원인**: 검색 조건에 맞는 새로운 논문이 없음

**해결 방법**:
- `days_lookback` 값을 늘리세요
- `config/config.yaml`에서 키워드나 저널 목록 확인

### 5. PDF 생성 실패

```
PDF generation failed (using HTML)
```

**원인**: WeasyPrint 의존성 문제

**해결 방법**: HTML 리포트는 정상 생성되므로 HTML 파일 사용

---

## 로컬 실행 vs GitHub Actions

| 항목 | 로컬 실행 | GitHub Actions |
|------|----------|----------------|
| Ollama 설치 | 수동 설치 필요 | 자동 설치 |
| 모델 다운로드 | 최초 1회 | 매 실행 (캐시 사용) |
| 실행 속도 | 빠름 (GPU 사용 가능) | 느림 (CPU만 사용) |
| 비용 | 무료 (본인 PC) | 무료 (월 2000분 제한) |
| 자동화 | cron 설정 필요 | 기본 제공 |

---

## 추가 정보

- **저장소**: [GitHub Repository](https://github.com/4to1stfloor/ai-research-curator)
- **이슈 리포트**: [GitHub Issues](https://github.com/4to1stfloor/ai-research-curator/issues)

---

## 변경 이력

| 날짜 | 변경 내용 |
|------|----------|
| 2025-01-27 | Ollama 자동 설치 기능 추가 |
| 2025-01-27 | 최초 문서 작성 |

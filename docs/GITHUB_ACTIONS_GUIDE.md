# AI Research Curator - 사용 가이드

최신 생명과학/AI 논문을 자동으로 검색하고, AI로 한국어 요약을 생성하는 도구입니다.
GitHub Actions를 통해 **서버나 PC 없이도** 자동으로 실행됩니다.

---

## 전체 흐름

```
1. 이 저장소를 Fork
2. Secret 1개 설정 (이메일)
3. 끝! 매주 자동 실행 → 결과물 다운로드
```

---

## 1단계: 저장소 Fork

1. 이 저장소 페이지 상단의 **Fork** 버튼 클릭
2. 본인의 GitHub 계정으로 Fork 완료

> Fork하면 GitHub Actions 워크플로우가 함께 복사됩니다.

---

## 2단계: Secret 설정 (필수)

Fork한 저장소에서 **딱 1개**의 Secret만 설정하면 됩니다.

### 설정 방법

1. Fork한 저장소 페이지에서 **Settings** 탭 클릭
2. 왼쪽 메뉴에서 **Secrets and variables** → **Actions** 클릭
3. **New repository secret** 버튼 클릭
4. 아래 내용 입력:
   - **Name**: `PUBMED_EMAIL`
   - **Secret**: 본인 이메일 주소 (예: `myemail@gmail.com`)
5. **Add secret** 클릭

> PubMed API 접근에 이메일이 필요합니다. 어떤 이메일이든 상관없습니다.

---

## 3단계: 실행하기

### 자동 실행 (기본 설정)

설정 완료 후, **매주 수요일 오전 9시 (한국 시간)**에 자동 실행됩니다.
아무것도 안 해도 됩니다.

### 수동 실행 (바로 테스트하고 싶을 때)

1. Fork한 저장소에서 **Actions** 탭 클릭
2. 왼쪽에서 **Paper Digest** 선택
3. **Run workflow** 버튼 클릭
4. 옵션 설정 (선택):
   - **Maximum papers to process**: 처리할 논문 수 (기본 5, 줄이면 더 빠름)
   - **Days to look back**: 검색 기간 (기본 7일)
5. **Run workflow** 클릭

> GitHub Actions CPU에서 Ollama가 실행되므로 논문 5편 기준 약 1~2시간 소요됩니다.

---

## 4단계: 결과물 다운로드

1. **Actions** 탭에서 완료된 워크플로우 클릭
2. 페이지 하단 **Artifacts** 섹션에서 다운로드:

| 파일명 | 내용 | 설명 |
|--------|------|------|
| `paper-digest-html` | HTML 리포트 | 브라우저에서 바로 열어서 볼 수 있음 |
| `paper-digest-report` | PDF 리포트 | 인쇄/공유용 |
| `obsidian-notes` | Obsidian 마크다운 | Obsidian 앱 사용자용 노트 |

### 결과물에 포함되는 내용

- 논문별 한국어 요약 (핵심 발견, 방법론, 의의)
- Abstract 영한 대조 번역
- 논문 Figure 이미지 및 한국어 해설
- 연구 흐름 다이어그램 (Mermaid)

---

## AI 백엔드 (자동 감지)

기본 설정(`llm_provider: auto`)에서 사용 가능한 AI를 자동으로 감지합니다:

| 우선순위 | 백엔드 | 조건 | API 키 필요 |
|---------|--------|------|------------|
| 1순위 | **Claude CLI** | `claude` 명령어 설치됨 (Claude 구독자) | 불필요 |
| 2순위 | **Claude API** | `ANTHROPIC_API_KEY` 환경변수 | 필요 |
| 3순위 | **Gemini API** | `GOOGLE_API_KEY` 환경변수 | 필요 |
| 4순위 | **OpenAI API** | `OPENAI_API_KEY` 환경변수 | 필요 |
| 5순위 | **Ollama** | Ollama 서버 실행 중 | 불필요 |

**Claude 구독자**: Claude Code가 설치되어 있으면 API 키 없이 자동으로 Claude를 사용합니다.
**API 키 없는 사용자**: Ollama가 자동으로 사용됩니다 (GitHub Actions에서도 자동 설치).

---

## 검색 키워드 커스터마이징

기본 검색 키워드를 본인의 연구 분야에 맞게 변경할 수 있습니다.

`config/config.yaml` 파일을 수정하세요:

```yaml
search:
  keywords:
    # 본인의 연구 분야 키워드로 변경
    - single-cell RNA-seq
    - spatial transcriptomics
    - cancer genomics
    - CRISPR screen
    # 원하는 키워드 추가...

  journals:
    # 검색할 저널 목록
    - Nature
    - Science
    - Cell
    # 원하는 저널 추가...

  max_papers: 5          # 처리할 최대 논문 수
  days_lookback: 7       # 최근 며칠간의 논문 검색
```

---

## 자동 실행 스케줄 변경

`.github/workflows/paper_scraper.yml` 파일에서 `cron` 설정을 수정하세요:

```yaml
on:
  schedule:
    - cron: '0 0 * * 3'  # 매주 수요일 오전 9시 (KST)
```

| 예시 | 설명 |
|------|------|
| `0 0 * * 3` | 매주 수요일 오전 9시 (KST) |
| `0 0 * * 1,3,5` | 월, 수, 금 오전 9시 (KST) |
| `0 0 * * *` | 매일 오전 9시 (KST) |
| `0 0 1 * *` | 매월 1일 오전 9시 (KST) |

> GitHub Actions의 cron은 UTC 기준입니다. 한국 시간(KST) = UTC + 9시간.

---

## 로컬에서 실행하기 (선택사항)

GitHub Actions 대신 본인 PC에서 직접 실행할 수도 있습니다. GPU가 있으면 훨씬 빠릅니다.

### 1. Ollama 설치

```bash
# macOS / Linux
curl -fsSL https://ollama.com/install.sh | sh

# 모델 다운로드
ollama pull llama3.1:8b
```

### 2. 프로젝트 설치

```bash
git clone https://github.com/본인계정/ai-research-curator.git
cd ai-research-curator
pip install -r requirements.txt
```

### 3. 환경변수 설정

`.env` 파일을 생성하세요:

```bash
PUBMED_EMAIL=myemail@gmail.com
```

### 4. 실행

```bash
python -m src.main --config config/config.yaml --max-papers 5 --days 7
```

결과물은 `output/` 폴더에 저장됩니다:
- `output/reports/` - HTML, PDF 리포트
- `output/obsidian/` - Obsidian 마크다운 노트

### 로컬 vs GitHub Actions 비교

| 항목 | 로컬 실행 | GitHub Actions |
|------|----------|----------------|
| 설치 | Ollama 직접 설치 | 자동 설치 |
| 속도 | 빠름 (GPU 사용 시) | 느림 (CPU만 사용, 1~2시간) |
| 비용 | 전기세 | 무료 (월 2,000분 제한) |
| 자동화 | 직접 cron 설정 | 기본 제공 |
| 결과 저장 | `output/` 폴더 | Artifacts 다운로드 |

---

## 문제 해결

### "PUBMED_EMAIL secret is required" 에러

→ [2단계: Secret 설정](#2단계-secret-설정-필수)을 완료하세요.

### 'Paper' object has no attribute 'article_type' 에러

→ 저장소가 최신 버전인지 확인하세요. Fork한 저장소에서 **Sync fork** 버튼을 눌러 업데이트하세요.

### 실행 시간이 너무 오래 걸림

→ `max_papers` 값을 줄이세요 (예: 3). 논문 1편당 약 15~25분 소요됩니다.

### "No papers found" 메시지

→ `days_lookback` 값을 늘리거나, `config/config.yaml`에서 키워드를 확인하세요.

### Ollama 모델 다운로드 실패

→ GitHub Actions를 재실행하세요. 일시적인 네트워크 문제일 수 있습니다.

### PDF 생성 실패

→ HTML 리포트는 정상 생성되므로 HTML 파일을 사용하세요.

---

## FAQ

**Q: 비용이 드나요?**
A: GitHub Actions 무료 플랜 (월 2,000분)으로 충분합니다. 주 1회 실행 기준 약 월 480분 사용.

**Q: API 키가 필요한가요?**
A: 아닙니다. Claude Code 구독자는 자동으로 Claude를 사용합니다. 구독이 없어도 Ollama가 자동 설치되어 실행됩니다.

**Q: 검색 분야를 바꿀 수 있나요?**
A: `config/config.yaml`에서 키워드와 저널 목록을 자유롭게 수정할 수 있습니다.

**Q: Obsidian이 뭔가요?**
A: 마크다운 기반 노트 앱입니다. Obsidian을 사용하지 않는다면 HTML 리포트만 사용하면 됩니다.

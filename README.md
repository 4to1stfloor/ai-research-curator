# Paper Digest AI Agent

생물정보학/AI 분야의 최신 논문을 자동으로 수집, 요약, 번역하는 AI 에이전트입니다.

## 주요 기능

- **논문 검색**: PubMed, RSS 피드에서 키워드/저널 기반 검색
- **중복 방지**: 이전에 처리한 논문 자동 제외
- **AI 요약**: Claude/OpenAI/Gemini/Ollama로 논문 핵심 내용 한국어 요약
- **Abstract 번역**: 영어-한국어 라인바이라인 번역 (영어 공부용)
- **Figure 추출**: PMC, 저널 페이지, PDF에서 Figure 자동 추출
- **Figure 해설**: AI가 각 Figure의 핵심 내용 설명
- **다이어그램 생성**: 연구 흐름 Mermaid 다이어그램 자동 생성
- **HTML/PDF 리포트**: 보기 좋은 리포트 생성
- **Obsidian 연동**: 노트앱에 자동 정리

## 빠른 시작 (로컬 실행)

### 1. 설치

```bash
# Clone
git clone https://github.com/YOUR_USERNAME/paper-digest.git
cd paper-digest

# Python 환경 (3.10+)
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt
```

### 2. API 키 설정

`.env.example`을 `.env`로 복사하고 API 키 입력:

```bash
cp .env.example .env
```

```env
# 필수: 이메일 (PubMed API + Unpaywall Open Access PDF 다운로드)
PUBMED_EMAIL=your_email@example.com

# LLM 선택 (하나 이상 필요)
ANTHROPIC_API_KEY=your_claude_api_key    # Claude
OPENAI_API_KEY=your_openai_api_key       # OpenAI
GOOGLE_API_KEY=your_gemini_api_key       # Gemini (요약 + 이미지 생성)

# 또는 로컬 LLM 사용 (API 키 불필요)
# Ollama 설치 후 config.yaml에서 llm_provider: ollama 설정
```

### 3. 설정 커스터마이즈

`config/config.yaml` 수정:

```yaml
search:
  journals:
    - Cell
    - Nature
    - Science
    - Nature Communications
  keywords:
    - single-cell RNA-seq
    - spatial transcriptomics
    - machine learning
  max_papers: 5
  days_lookback: 7
  open_access_only: true  # Open Access 논문만 처리

ai:
  llm_provider: ollama  # claude, openai, gemini, ollama 중 선택

  # Ollama (로컬 LLM, 무료)
  ollama:
    model: llama3.1:8b
    base_url: http://localhost:11434
```

### 4. 실행

```bash
# 기본 실행
python -m src.main

# 옵션
python -m src.main --max-papers 3 --days 14

# 검색만 (dry run)
python -m src.main --dry-run
```

## GitHub Actions로 자동화 (서버 없이 자동 실행)

GitHub Actions를 사용하면 **내 컴퓨터를 켜지 않아도** 매주 자동으로 논문을 수집합니다.

### Step 1: 저장소 Fork

1. 이 저장소 페이지에서 우측 상단 **"Fork"** 버튼 클릭
2. 내 GitHub 계정에 복사됨

### Step 2: Secrets 설정 (API 키 등록)

1. Fork한 저장소로 이동
2. **Settings** 탭 클릭
3. 좌측 메뉴: **Secrets and variables** > **Actions**
4. **"New repository secret"** 클릭
5. 아래 키들 추가:

| Name | 설명 | 필수 |
|------|------|------|
| `PUBMED_EMAIL` | 내 이메일 주소 | **필수** |
| `GOOGLE_API_KEY` | Gemini API 키 (요약용) | 필수 |
| `ANTHROPIC_API_KEY` | Claude API 키 | 선택 |
| `OPENAI_API_KEY` | OpenAI API 키 | 선택 |

### Step 3: Actions 활성화

1. **Actions** 탭 클릭
2. **"I understand my workflows, go ahead and enable them"** 클릭

### Step 4: 실행

**방법 A) 자동 실행**
- 매주 수요일 오전 9시(한국시간)에 자동 실행

**방법 B) 수동 실행**
1. **Actions** 탭 클릭
2. 좌측 **"Paper Digest"** 클릭
3. **"Run workflow"** 버튼 클릭
4. 옵션 설정 후 **"Run workflow"** 확인

### Step 5: 결과 다운로드

1. Actions 탭에서 실행 완료 확인 (녹색 체크 ✓)
2. 해당 실행 클릭
3. 하단 **"Artifacts"** 에서 다운로드:
   - `paper-digest-html` - HTML 보고서
   - `paper-digest-report` - PDF 보고서
   - `obsidian-notes` - Obsidian 노트

```
┌─────────────────────────────────────────────────────┐
│  GitHub 서버 (무료)                                  │
│                                                     │
│  매주 수요일 자동 실행 or 버튼 클릭                    │
│         ↓                                           │
│  ┌─────────────────┐                                │
│  │ 1. 코드 다운로드  │                                │
│  │ 2. Python 설치   │                                │
│  │ 3. 논문 검색     │                                │
│  │ 4. AI 요약      │                                │
│  │ 5. 보고서 생성   │                                │
│  └─────────────────┘                                │
│         ↓                                           │
│  📦 Artifacts (결과물 다운로드)                       │
└─────────────────────────────────────────────────────┘
```

## Figure 추출 방식

논문에서 Figure를 자동으로 추출합니다. 다음 순서로 시도합니다:

1. **PMC (PubMed Central)** - DOI로 PMCID 자동 조회, 가장 안정적
2. **DOI 해석** - Publisher 페이지에서 직접 추출
3. **저널별 전용 로직** - PLOS, eLife 등 Open Access 저널
4. **PDF 추출** - 다운로드된 PDF에서 PyMuPDF로 이미지 추출

> **참고**: Nature, Science, Cell 등 대형 출판사는 봇 차단이 있어 PMC에 등록된 논문만 Figure 추출이 가능합니다.

## 출력 예시

### HTML/PDF 리포트
- `output/reports/paper_digest_20240108.html`
- `output/reports/paper_digest_20240108.pdf`

### Obsidian 노트
```
output/obsidian/
├── papers/
│   ├── Single_cell_analysis_of_tumor.md
│   └── Deep_learning_for_cancer.md
├── digests/
│   └── digest_20240108.md
└── figures/
    └── 10.1234_paper_id/
        ├── fig_1.png
        └── fig_2.png
```

## 프로젝트 구조

```
paper-digest/
├── config/
│   └── config.yaml          # 설정 파일
├── src/
│   ├── search/              # 논문 검색 (PubMed, RSS)
│   ├── paper/               # PDF 다운로드, Figure 추출
│   ├── ai/                  # LLM 요약, 번역, 다이어그램
│   ├── output/              # HTML, PDF, Obsidian 출력
│   ├── storage/             # 논문 이력 관리
│   └── main.py              # 메인 파이프라인
├── data/
│   └── paper_history.json   # 처리된 논문 이력
├── output/
│   ├── reports/             # HTML/PDF 리포트
│   └── obsidian/            # Obsidian 마크다운
└── .github/workflows/       # GitHub Actions
```

## 지원 저널

### RSS 피드 지원 (Figure 추출 가능)
- **Nature 계열**: Nature, Nature Methods, Nature Biotechnology, Nature Communications 등
- **Science 계열**: Science, Science Advances
- **Cell Press**: Cell, Cancer Cell, Cell Systems 등
- **Open Access**: eLife, PLOS Biology, PLOS Computational Biology, Genome Biology 등

### PubMed 검색
- 모든 PubMed 인덱싱 저널

## FAQ

### Q: PDF/Figure가 다운로드 안됩니다
A: Open Access 논문만 자동 다운로드됩니다. `PUBMED_EMAIL`이 설정되어 있는지 확인하세요. 이 이메일은 Unpaywall API를 통해 Open Access PDF를 찾는 데 사용됩니다.

### Q: 로컬 LLM을 사용하고 싶습니다
A: Ollama를 설치하고 `config.yaml`에서 설정하세요:
```bash
# Ollama 설치
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.1:8b
```
```yaml
# config.yaml
ai:
  llm_provider: ollama
  ollama:
    model: llama3.1:8b
```

### Q: 요약 품질을 높이고 싶습니다
A: Claude Opus나 GPT-4를 사용하세요:
```yaml
ai:
  llm_provider: claude
  claude:
    model: claude-opus-4-20250514
```

### Q: Obsidian 연동은 어떻게 하나요?
A: `output/obsidian` 폴더를 Obsidian vault에 복사하거나, `config.yaml`에서 vault_path를 직접 지정하세요.

### Q: GitHub Actions가 실패합니다
A: Repository Secrets에 `PUBMED_EMAIL`이 설정되어 있는지 확인하세요. 이 값은 필수입니다.

## 향후 계획

- [ ] 기관 인증 (NCC, 서울대) 지원
- [ ] 이메일/Slack 알림
- [ ] 웹 대시보드
- [ ] 더 많은 저널 RSS 지원

## License

MIT License

## Contributing

Issues와 PR 환영합니다!

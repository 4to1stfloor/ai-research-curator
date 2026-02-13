# AI Research Curator

생물정보학/AI 분야의 최신 논문을 자동으로 수집, 요약, 번역하는 AI 에이전트입니다.

## 주요 기능

- **논문 검색**: PubMed, RSS 피드에서 키워드/저널 기반 검색
- **중복 방지**: DOI + PMID + 제목 기반 다중 키 중복 제거
- **AI 요약**: Claude CLI / Claude / OpenAI / Gemini / Ollama로 논문 핵심 내용 한국어 요약
- **Abstract 번역**: 영어-한국어 라인바이라인 번역 (영어 공부용)
- **Figure 추출**: PMC, 저널 페이지, PDF에서 Figure 자동 추출
- **Figure 해설**: AI가 각 Figure의 핵심 내용 설명
- **다이어그램 생성**: 연구 흐름 Mermaid 다이어그램 자동 생성
- **HTML/PDF 리포트**: 보기 좋은 리포트 생성
- **Obsidian 연동**: 노트앱에 자동 정리

## 빠른 시작

### 방법 1: 원라인 설치 (권장)

```bash
curl -fsSL https://raw.githubusercontent.com/4to1stfloor/ai-research-curator/main/install.sh | bash
```

이 명령어 하나로:
1. `~/.ai-research-curator/`에 자동 설치
2. Python 패키지 설치
3. AI 백엔드 자동 감지 (Claude CLI → API Key → Ollama)
4. PubMed 이메일 설정
5. 실행 방식 선택 (crontab 자동 / GitHub Actions / 수동)

이미 설치된 경우 같은 명령어로 업데이트됩니다.

### 방법 2: 수동 설치

```bash
# Clone
git clone https://github.com/4to1stfloor/ai-research-curator.git
cd ai-research-curator

# Setup 실행 (대화형)
bash setup.sh
```

### 방법 3: 직접 설정

```bash
git clone https://github.com/4to1stfloor/ai-research-curator.git
cd ai-research-curator

# Python 환경 (3.10+)
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt
```

## AI 백엔드 설정

이 도구는 `auto` 모드(기본값)에서 사용 가능한 AI를 자동으로 감지합니다:

| 우선순위 | 백엔드 | 설정 방법 | 비용 |
|---------|--------|----------|------|
| 1 | **Claude CLI** | `claude` 명령어 설치 (Claude 구독 필요) | 구독료 포함 |
| 2 | **API Key** | `.env`에 `ANTHROPIC_API_KEY` 등 설정 | API 사용량 |
| 3 | **Ollama** | `ollama serve` 실행 + 모델 다운로드 | 무료 |

### Claude CLI (가장 권장)

Claude 구독자라면 API 키 없이 사용 가능:
```bash
# Claude Code 설치 후 자동 감지됨
# https://docs.anthropic.com/en/docs/claude-code
```

### API Key 방식

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
GOOGLE_API_KEY=your_gemini_api_key       # Gemini
```

### Ollama (로컬 LLM, 무료)

```bash
# Ollama 설치
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.1:8b
```

## 설정 커스터마이즈

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
  # auto (권장): Claude CLI → API Key → Ollama 순서로 자동 감지
  llm_provider: auto
```

## 실행

```bash
# 기본 실행
python -m src.main

# 옵션
python -m src.main --max-papers 3 --days 14

# 검색만 (dry run)
python -m src.main --dry-run
```

## 자동화

### 로컬 자동 실행 (crontab)

```bash
# 설치 (매주 수요일 오전 9시 실행)
bash scripts/setup_cron.sh install

# 상태 확인
bash scripts/setup_cron.sh status

# 제거
bash scripts/setup_cron.sh remove
```

### GitHub Actions (서버 없이 자동 실행)

GitHub Actions를 사용하면 **내 컴퓨터를 켜지 않아도** 매주 자동으로 논문을 수집합니다.

#### Step 1: 저장소 Fork

1. 이 저장소 페이지에서 우측 상단 **"Fork"** 버튼 클릭
2. 내 GitHub 계정에 복사됨

#### Step 2: Secrets 설정 (API 키 등록)

1. Fork한 저장소로 이동
2. **Settings** → **Secrets and variables** → **Actions**
3. **"New repository secret"** 클릭 후 아래 키 추가:

| Name | 설명 | 필수 |
|------|------|------|
| `PUBMED_EMAIL` | 내 이메일 주소 | **필수** |
| `GOOGLE_API_KEY` | Gemini API 키 (요약용) | 필수 |
| `ANTHROPIC_API_KEY` | Claude API 키 | 선택 |
| `OPENAI_API_KEY` | OpenAI API 키 | 선택 |

#### Step 3: Actions 활성화

1. **Actions** 탭 → **"I understand my workflows, go ahead and enable them"** 클릭

#### Step 4: 실행

- **자동**: 매주 수요일 오전 9시(한국시간)
- **수동**: Actions 탭 → **"Paper Digest"** → **"Run workflow"**

#### Step 5: 결과 다운로드

실행 완료 후 **Artifacts**에서 다운로드:
- `paper-digest-html` - HTML 보고서
- `paper-digest-report` - PDF 보고서
- `obsidian-notes` - Obsidian 노트

## Figure 추출 방식

논문에서 Figure를 자동으로 추출합니다:

1. **PMC (PubMed Central)** - DOI로 PMCID 자동 조회, 가장 안정적
2. **DOI 해석** - Publisher 페이지에서 직접 추출
3. **저널별 전용 로직** - PLOS, eLife 등 Open Access 저널
4. **PDF 추출** - 다운로드된 PDF에서 PyMuPDF로 이미지 추출

> **참고**: Nature, Science, Cell 등 대형 출판사는 봇 차단이 있어 PMC에 등록된 논문만 Figure 추출이 가능합니다.

## 출력 예시

### HTML/PDF 리포트
- `output/reports/paper_digest_20260213.html`
- `output/reports/paper_digest_20260213.pdf`

### Obsidian 노트
```
output/obsidian/
├── papers/
│   ├── VMAT2_dysfunction_impairs_vesicular.md
│   └── Single_cell_atlas_of_AML.md
├── digests/
│   └── digest_20260213.md
└── figures/
    └── 10.1234_paper_id/
        ├── fig_1.jpg
        └── fig_2.jpg
```

## 프로젝트 구조

```
ai-research-curator/
├── install.sh                # 원라인 설치 스크립트
├── setup.sh                  # 대화형 설정 스크립트
├── config/
│   └── config.yaml           # 설정 파일
├── src/
│   ├── search/               # 논문 검색 (PubMed, RSS)
│   ├── paper/                # PDF 다운로드, Figure 추출
│   ├── ai/                   # LLM 요약, 번역, 다이어그램
│   ├── output/               # HTML, PDF, Obsidian 출력
│   ├── storage/              # 논문 이력 관리
│   └── main.py               # 메인 파이프라인
├── scripts/
│   ├── setup_cron.sh         # Crontab 자동화 설정
│   └── run_cron.sh           # Cron 실행 스크립트
├── data/
│   └── paper_history.json    # 처리된 논문 이력
├── output/
│   ├── reports/              # HTML/PDF 리포트
│   └── obsidian/             # Obsidian 마크다운
└── .github/workflows/        # GitHub Actions
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
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.1:8b
```
```yaml
ai:
  llm_provider: ollama
  ollama:
    model: llama3.1:8b
```

### Q: 요약 품질을 높이고 싶습니다
A: Claude CLI를 설치하면 API 키 없이 Claude 사용 가능합니다. 또는 API 키를 설정하세요:
```yaml
ai:
  llm_provider: claude
  claude:
    model: claude-sonnet-4-20250514
```

### Q: Obsidian 연동은 어떻게 하나요?
A: `output/obsidian` 폴더를 Obsidian vault에 복사하거나, `config.yaml`에서 vault_path를 직접 지정하세요.

### Q: GitHub Actions가 실패합니다
A: Repository Secrets에 `PUBMED_EMAIL`이 설정되어 있는지 확인하세요. 이 값은 필수입니다.

### Q: 이미 설치된 버전을 업데이트하고 싶습니다
A: 같은 설치 명령어를 다시 실행하면 자동으로 업데이트됩니다:
```bash
curl -fsSL https://raw.githubusercontent.com/4to1stfloor/ai-research-curator/main/install.sh | bash
```

## License

MIT License

## Contributing

Issues와 PR 환영합니다!

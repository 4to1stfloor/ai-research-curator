# Paper Digest AI Agent

생물정보학/AI 분야의 최신 논문을 자동으로 수집, 요약, 번역하는 AI 에이전트입니다.

## 주요 기능

- **논문 검색**: PubMed, RSS 피드, bioRxiv에서 키워드/저널 기반 검색
- **중복 방지**: 이전에 처리한 논문 자동 제외
- **AI 요약**: Claude/OpenAI로 논문 핵심 내용 한국어 요약
- **Abstract 번역**: 영어-한국어 라인바이라인 번역 (영어 공부용)
- **그림 추출**: PDF에서 Figure 자동 추출
- **다이어그램 생성**: 연구 흐름 Mermaid 다이어그램 자동 생성
- **PDF 리포트**: 보기 좋은 PDF 리포트 생성
- **Obsidian 연동**: 노트앱에 자동 정리

## 빠른 시작

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
# 필수: 둘 중 하나
ANTHROPIC_API_KEY=your_claude_api_key
OPENAI_API_KEY=your_openai_api_key

# 선택: 이미지 생성용
GOOGLE_API_KEY=your_gemini_api_key

# 선택: PubMed 높은 rate limit
PUBMED_EMAIL=your_email@example.com
```

### 3. 설정 커스터마이즈

`config/config.yaml` 수정:

```yaml
search:
  journals:
    - Cell
    - Nature
    - Science
  keywords:
    - single-cell RNA-seq
    - machine learning
  max_papers: 5
  days_lookback: 7

ai:
  llm_provider: claude  # or openai
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

## 출력 예시

### PDF 리포트
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
    └── ...
```

## GitHub Actions 자동화

1. GitHub Secrets 설정:
   - `ANTHROPIC_API_KEY` 또는 `OPENAI_API_KEY`
   - `GOOGLE_API_KEY` (선택)
   - `PUBMED_EMAIL` (선택)

2. 매주 수요일 자동 실행 (한국시간 오전 9시)

3. Actions 탭에서 수동 실행 가능

## 프로젝트 구조

```
paper-digest/
├── config/
│   └── config.yaml          # 설정 파일
├── src/
│   ├── search/              # 논문 검색 (PubMed, RSS, bioRxiv)
│   ├── paper/               # PDF 다운로드 및 파싱
│   ├── ai/                  # LLM 요약, 번역, 다이어그램
│   ├── output/              # PDF, Obsidian 출력
│   ├── storage/             # 논문 이력 관리
│   └── main.py              # 메인 파이프라인
├── data/
│   └── paper_history.json   # 처리된 논문 이력
├── output/
│   ├── reports/             # PDF 리포트
│   └── obsidian/            # Obsidian 마크다운
└── .github/workflows/       # GitHub Actions
```

## 저널/키워드 추가

`config/config.yaml`에서 추가:

```yaml
search:
  journals:
    - Cell
    - Nature
    - Science
    - Nature Methods        # 추가
    - Genome Biology        # 추가

  keywords:
    - scRNA-seq
    - spatial transcriptomics  # 추가
    - CRISPR screening         # 추가
```

## FAQ

### Q: PDF가 다운로드 안됩니다
A: Open Access 논문만 자동 다운로드됩니다. 기관 인증이 필요한 논문은 링크만 제공됩니다.

### Q: 요약 품질을 높이고 싶습니다
A: `config.yaml`에서 모델 변경:
```yaml
ai:
  claude:
    model: claude-opus-4-20250514  # 더 강력한 모델
```

### Q: Obsidian 연동은 어떻게 하나요?
A: `output/obsidian` 폴더를 Obsidian vault에 복사하거나, vault_path를 직접 지정하세요.

## 향후 계획

- [ ] 기관 인증 (NCC, 서울대) 지원
- [ ] 이메일 알림
- [ ] 웹 대시보드
- [ ] 더 많은 저널 RSS 지원

## License

MIT License

## Contributing

Issues와 PR 환영합니다!

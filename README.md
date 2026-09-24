# PPT Motion

**기존 PPT/PDF의 디자인을 유지하면서, 차트와 핵심 메시지에 필요한 모션만 더하는 HTML 발표자료 제작 도구입니다.**

제목·짧은 글·표·차트가 많은 연구·업무·교육 자료에 사용할 수 있습니다. 원본 PDF의 글꼴과 도형을 SVG로 보존하고, 선택한 요소에 효과를 적용합니다. Codex 스킬, Claude Code 플러그인, Claude Desktop 업로드용 스킬과 독립 실행 가능한 Python CLI를 제공합니다.

> 결과물은 브라우저에서 재생하는 HTML 발표자료입니다. 원본 PPTX에 PowerPoint 네이티브 애니메이션을 삽입하는 도구는 아닙니다.

## 어떤 효과를 넣나요?

효과를 **수치를 드러내기**, **메시지를 강조하기**, **단순히 등장하기**로 구분합니다. 차트의 의미에 맞는 모션을 고르고, 모든 요소를 움직이지 않습니다.

| 요소 | 기본 처리 |
|---|---|
| 막대차트 | 실제 영점에서 양수·음수 방향으로 성장 |
| 누적 막대 | 모든 구간이 같은 영점과 타이밍으로 성장해 연결과 구성비 유지 |
| 선차트 | 원래 데이터 경로를 시작점부터 그리기. 색·점선 유지 |
| 도넛·파이·원형 게이지 | 회색 트랙 위로 원 둘레를 따라 원래 색과 무늬 채우기 |
| 히트맵 | 타일 위치와 숫자를 유지하며 색 드러내기 |
| 표 | 행·열·숫자를 고정하고 필요한 행이나 셀만 강조 |
| 제목·본문 | 처음부터 읽을 수 있게 유지. 필요한 문장에 밑줄·강조 |
| 별표·콜아웃 | 원래 표시를 한 번만 살짝 확대하거나 강조 |
| 로고·배경·구분선 | 기본적으로 고정 |

기본 효과는 함께 시작해 한 번 재생한 뒤 멈춥니다. 슬라이드를 자동으로 넘기거나 반복 재생하지 않습니다. 자세한 기준은 [유형별 모션](skill/ppt-motion/references/motion-language.md)을 참고하세요.

## 설치

[최신 릴리스](https://github.com/MarcoYou/ppt-motion/releases/latest)에서 사용 중인 앱에 맞는 ZIP을 받을 수 있습니다. 모두 같은 엔진과 모션 규칙을 사용합니다.

| 환경 | 설치 방법 | 사용 방법 |
|---|---|---|
| Codex | Codex ZIP을 풀고 `python3 install.py --client codex` | `$ppt-motion`과 파일 경로로 요청 |
| Claude Code | 아래 마켓플레이스 명령 또는 설치 스크립트 | `/ppt-motion:ppt-motion` |
| Claude Desktop | Desktop ZIP을 스킬 설정에서 업로드 | PDF를 첨부하고 PPT Motion으로 작업 요청 |
| 독립 CLI | 저장소 복제 후 `python3 ppt-motion` | 아래 CLI 작업 흐름 |

### Codex

Python **3.11 이상**이 필요합니다. ZIP 대신 저장소를 복제해도 됩니다.

```sh
git clone https://github.com/MarcoYou/ppt-motion.git
cd ppt-motion
python3 install.py --client codex
```

설치기는 스킬을 `${CODEX_HOME:-~/.codex}/skills/ppt-motion`에 복사하고, PyMuPDF·lxml의 지정 버전을 별도 캐시 가상환경에 준비합니다. 시스템 Python 패키지는 변경하지 않습니다. 처음 준비할 때는 패키지 다운로드가 필요하며 이후 실행은 해당 런타임을 재사용합니다. 설치 후 앱을 다시 열거나 새 작업에서 스킬을 확인하세요.

> $ppt-motion 이 PPTX와 PDF를 발표용으로 만들어줘. 디자인과 페이지 순서는 유지하고, 막대는 영점에서 성장, 선은 경로 그리기, 도넛은 원 둘레를 따라 색이 채워지게 해줘. 표와 제목은 읽기 편하게 유지해줘.

> $ppt-motion 이 PDF 앞 11페이지만 처리해줘. 각 장의 핵심 메시지에 맞춰 강조하고, 장식 요소는 움직이지 마.

### Claude Code

Claude Code에서 다음을 실행합니다.

```text
/plugin marketplace add MarcoYou/ppt-motion
/plugin install ppt-motion@ppt-motion
```

설치 후 다음처럼 호출합니다. 로컬 Python **3.11 이상**이 필요하며, 첫 작업에서 스킬 런타임을 준비합니다.

```text
/ppt-motion:ppt-motion /path/deck.pdf 앞 11페이지만 모션을 넣어줘. 원본 디자인은 유지하고 도넛은 원 둘레를 따라 색이 채워지게 해줘.
```

플러그인 대신 개인 스킬 폴더에 직접 설치할 수도 있습니다. 이 방식의 호출 이름은 `/ppt-motion`입니다. 두 방식 중 하나를 선택하면 됩니다.

```sh
python3 install.py --client claude-code
```

이 명령은 `~/.claude/skills/ppt-motion`에 설치합니다. ZIP 플러그인을 로컬에서 확인하려면 [Claude Code ZIP](https://github.com/MarcoYou/ppt-motion/releases/latest/download/ppt-motion-claude-code.zip)을 풀고 `claude --plugin-dir /path/to/ppt-motion`을 실행하세요. 설치 형식은 [Claude Code 플러그인 문서](https://code.claude.com/docs/en/plugins)와 [마켓플레이스 문서](https://code.claude.com/docs/en/plugin-marketplaces)를 따릅니다.

### Claude Desktop

1. [Desktop 스킬 ZIP](https://github.com/MarcoYou/ppt-motion/releases/latest/download/ppt-motion-claude-desktop.zip)을 받습니다. ZIP을 풀지 않고 업로드합니다.
2. Claude의 **Customize → Skills**에서 업로드 메뉴로 ZIP을 추가하고 활성화합니다.
3. **코드 실행 및 파일 생성**을 사용할 수 있는 환경에서 PDF를 대화에 첨부하고, “PPT Motion으로 앞 11페이지만 애니메이션 발표자료로 만들어줘”라고 요청합니다.
4. 결과로 받은 HTML 파일을 내려받아 브라우저에서 엽니다. 서버를 켤 필요가 없습니다.

Desktop 버전은 **사용자 지정 스킬**입니다. MCP 확장 파일(`.mcpb`)이 아닙니다. Claude의 실행 환경에서 첨부 파일을 처리하므로 Mac의 `/Users/...` 경로만 전달하면 로컬 파일을 읽을 수 없습니다. PPTX만 첨부했고 PDF 변환 도구가 없는 환경이라면, PowerPoint에서 내보낸 PDF도 첨부하세요. 필수 Python 패키지가 없으면 다운로드 가능한 실행 환경이 필요합니다.

앱 버전·계정·조직 설정에 따라 스킬 또는 코드 실행 메뉴의 가용성이 다를 수 있습니다. [Anthropic 사용자 지정 스킬 안내](https://support.claude.com/en/articles/12512198-how-to-create-custom-skills)를 참고하세요.

### 업데이트와 다른 설치 위치

```sh
git pull
python3 install.py --client codex
# 임의 위치에 설치하거나 런타임 준비를 나중으로 미루기
python3 install.py --client claude-code --skills-dir /path/to/skills --skip-runtime
```

설치기가 관리하는 수정되지 않은 스킬은 업데이트할 수 있습니다. 기존 스킬이 별도 설치본이거나 사용자가 수정했다면 덮어쓰지 않습니다. 교체하려는 경우에만 `--force`를 사용하며, 기존 폴더 또는 심볼릭 링크는 백업합니다. `--skip-runtime`으로 설치한 경우 첫 실행에서 의존성을 준비합니다. 캐시 위치는 `PPT_MOTION_RUNTIME_ROOT`로 지정할 수 있습니다. 오프라인 설치에는 준비된 캐시 또는 `PIP_NO_INDEX=1`, `PIP_FIND_LINKS`로 지정한 호환 wheel 저장소가 필요합니다.

Windows에서는 명령의 `python3`를 설치된 `python` 또는 `py -3`으로 바꾸세요. 아래 `./ppt-motion` 명령은 모든 환경에서 `python3 ppt-motion`으로 실행할 수 있습니다.

## 파일 준비

- **PPTX + PDF:** PPTX에서 제목·표·차트의 구조를 읽고, PDF를 디자인 기준으로 삼습니다.
- **PDF만 있음:** 텍스트와 벡터 도형을 추출해 효과를 적용할 영역을 선택합니다.
- **PPTX만 있음:** 같은 이름의 PDF를 먼저 찾습니다. 없으면 PowerPoint에서 PDF로 내보내는 방법을 권장합니다.

LibreOffice가 설치되어 있으면 별도 PDF로 변환할 수 있습니다. 변환 후 글꼴·줄바꿈·차트가 원본과 맞는지 확인해야 합니다.

```sh
./ppt-motion doctor --pptx /path/deck.pptx
./ppt-motion export-pdf --pptx /path/deck.pptx --out /path/deck.pdf
```

## CLI 작업 흐름

```sh
# 1. 원본 추출. PDF만 있으면 --pptx 옵션을 생략합니다.
./ppt-motion init --pptx /path/deck.pptx --pdf /path/deck.pdf --out ../motion-jobs/demo

# 2. 수정 가능한 객체별 계획 생성
./ppt-motion plan ../motion-jobs/demo --profile research

# 3. motion-plan.json에서 message, effect, ids, 좌표 등을 검토·수정
#    막대는 실제 영점, 원형 차트는 공통 중심과 반경이 필요합니다.
./ppt-motion apply-plan ../motion-jobs/demo

# 4. HTML 생성 및 원본 보존 검사
./ppt-motion build ../motion-jobs/demo
./ppt-motion check ../motion-jobs/demo

# 5. 서버 없이 열 수 있는 단일 HTML로 내보내기
./ppt-motion export-html ../motion-jobs/demo --out ../presentation.html

# 선택: 편집 중 로컬 미리보기
./ppt-motion serve ../motion-jobs/demo --port 4319
```

`presentation.html`은 다운로드하거나 복사해서 바로 열 수 있습니다. 기존 파일을 덮어쓰지 않으므로 다시 내보낼 때는 새 이름을 사용하세요. `serve`를 실행한 경우에는 `http://127.0.0.1:4319/`를 엽니다. 서버는 해당 컴퓨터에서만 접근할 수 있습니다. 종료는 `Ctrl-C`입니다.

- 일부 페이지: `init`에 `--pages 1-11` 또는 `--pages 1,3-5` 추가.
- `research`: 모든 요소를 정적으로 시작하고 필요한 효과만 선택.
- `explain`: PPTX와 연결된 긴 본문에 짧은 페이드 적용. 제목·표·불확실한 PDF 텍스트는 유지.
- `static`: 효과 없이 원형을 확인하는 출발점.

계획 생성만으로 차트가 자동 애니메이션화되지는 않습니다. 에이전트 또는 사용자가 원본을 보고 정확한 요소와 메시지를 선택해야 합니다. [객체별 작업법](skill/ppt-motion/references/object-workflow.md)과 [세부 설정](skill/ppt-motion/references/configuration.md)에 예시가 있습니다.

## 발표 도구

- `←` / `→`: 이전·다음 페이지
- `R`: 현재 페이지 효과 다시 재생
- `F`: 전체화면. 하단 발표 설명은 숨김
- 효과·강조 켜기/끄기
- 원본 PDF와 나란히 비교
- 요소 선택으로 정확한 ID와 좌표 확인
- 운영체제의 동작 줄이기 설정 지원

`export-html`은 슬라이드·원본 비교 이미지·CSS·JavaScript를 모두 포함한 단일 HTML을 만듭니다. 외부 서버나 글꼴·스크립트 다운로드 없이 열 수 있습니다. 편집용 `dist/`는 여러 파일로 구성되어 로컬 서버 또는 정적 호스팅을 사용합니다. 호스팅 배포는 별도 작업입니다.

## 반복 수정과 검증

`motion-plan.json`은 이름이 붙은 객체별 계획이고, `deck.json`은 빌드에 사용하는 정확한 설정입니다. 적용 전에 검증하며 이전 설정은 작업 폴더의 `history/`에 저장합니다.

원본·추출 결과·설정의 해시로 오래된 요소 ID를 잘못 적용하는 것을 막습니다. 설정을 수정한 뒤에는 다시 빌드해야 합니다. 새 계획은 `plan JOB --out JOB/motion-plan-v2.json`처럼 다른 파일로 생성할 수 있습니다.

`check`는 파일 해시와 SVG 도형·칠하기 순서를 검사합니다. 시각적 완성도와 메시지의 적절성까지 증명하지는 않으므로, 시작·중간·완료 프레임을 브라우저에서 확인하세요.

## 예제와 테스트

개인 발표자료 없이 생성한 가상 데이터로 테스트합니다. 아래 테스트 명령은 ZIP 설치본이 아닌 Git으로 복제한 저장소에서 실행합니다.

```sh
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\Activate.ps1
python -m pip install -r skill/ppt-motion/scripts/requirements.txt
python -m unittest discover -s tests -v
```

제목·본문·표·양음 막대·선·히트맵을 포함한 4페이지 예제도 만들 수 있습니다. 예제 생성에만 `python-pptx`가 추가로 필요합니다.

```sh
python -m pip install python-pptx
python examples/make_generic_demo.py --out ../motion-demo-source
./ppt-motion init --pptx ../motion-demo-source/generic-demo.pptx --pdf ../motion-demo-source/generic-demo.pdf --out ../motion-demo-job
./ppt-motion plan ../motion-demo-job --slide-map 1=1,2=2,3=3,4=4
```

예제 PDF는 직접 그린 디자인 기준이며, PPTX를 PowerPoint에서 내보낸 결과와 동일하다고 보장하지 않습니다. 검증 범위는 [QA.md](QA.md)에 정리했습니다.

릴리스 패키지를 다시 만들려면 저장소 루트에서 다음 명령을 실행합니다. 결과는 `dist/releases/`의 세 ZIP과 `SHA256SUMS`이며, 공개할 파일만 명시적으로 포함합니다.

```sh
python3 scripts/package_release.py
```

## 저장소 구조

```text
ppt-motion                     CLI 진입점 (자동 런타임 준비)
install.py                     Codex / Claude Code 스킬 설치
.claude-plugin/                Claude Code 플러그인·마켓플레이스
clients/claude-desktop/        Desktop 업로드 스킬 지침
scripts/package_release.py    세 환경용 ZIP·체크섬 생성
skill/ppt-motion/
  SKILL.md                     공통 작업 지침
  scripts/                     추출·계획·빌드·검증
  assets/                      HTML/SVG 발표 뷰어
  references/                  유형별 모션과 설정 문서
  agents/                      스킬 표시 정보
examples/make_generic_demo.py   가상 데이터 예제 생성
tests/                        자동화 테스트
CONTRACT.md                    데이터 구조와 엔진 계약
```

## 범위와 한계

- 이미지 한 장으로 붙인 차트는 막대·선·조각을 개별적으로 고르기 어렵습니다. 적절한 영역 강조를 쓰거나 원본 도형·데이터가 필요합니다.
- PPTX와 PDF의 페이지 수가 같다는 이유만으로 대응을 가정하지 않습니다. 텍스트 일치 또는 명시적 페이지 매핑을 사용합니다.
- 원본의 수치나 주장을 검증하거나 최신 데이터로 바꾸는 도구는 아닙니다.
- 원본 PDF/PPTX, 개인 작업 폴더, 추출 산출물은 이 저장소에 포함하지 않습니다.

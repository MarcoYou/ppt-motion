# PPT Motion

**기존 PPT/PDF의 디자인을 유지하면서, 차트와 핵심 메시지에 필요한 모션만 더하는 HTML 발표자료 제작 도구입니다.**

제목·짧은 글·표·차트가 많은 연구·업무·교육 자료에 사용할 수 있습니다. 원본 PDF의 글꼴과 도형을 SVG로 보존하고, 선택한 요소에 효과를 적용합니다. Codex 스킬과 독립 실행 가능한 Python CLI를 함께 제공합니다.

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

Python **3.11 이상**이 필요합니다. 필수 패키지는 PyMuPDF와 lxml입니다.

```sh
git clone https://github.com/MarcoYou/ppt-motion.git
cd ppt-motion
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r skill/ppt-motion/scripts/requirements.txt
./ppt-motion --version
```

위 명령은 macOS/Linux 기준입니다. Windows에서는 `.venv\Scripts\Activate.ps1`로 가상환경을 활성화하고, `./ppt-motion` 대신 `python skill/ppt-motion/scripts/ppt_motion.py`를 사용하면 됩니다.

### Codex 스킬로 등록

저장소 루트에서 다음 명령을 실행합니다. 같은 이름의 스킬이 이미 있으면 덮어쓰지 않고 오류가 나므로 기존 위치를 먼저 확인하세요.

```sh
PPT_MOTION_REPO="$(pwd)"
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
ln -s "$PPT_MOTION_REPO/skill/ppt-motion" "${CODEX_HOME:-$HOME/.codex}/skills/ppt-motion"
```

심볼릭 링크를 쓰기 어려운 환경에서는 `skill/ppt-motion/` 폴더를 Codex의 `skills/ppt-motion/`으로 복사할 수 있습니다. 스킬 실행 시에도 위 Python 의존성이 설치된 환경을 사용하세요.

Codex에 파일 경로와 함께 요청합니다.

> $ppt-motion 이 PPTX와 PDF를 발표용으로 만들어줘. 디자인과 페이지 순서는 유지하고, 막대는 영점에서 성장, 선은 경로 그리기, 도넛은 원 둘레를 따라 색이 채워지게 해줘. 표와 제목은 읽기 편하게 유지해줘.

> $ppt-motion 이 PDF 앞 11페이지만 처리해줘. 각 장의 핵심 메시지에 맞춰 강조하고, 장식 요소는 움직이지 마.

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

# 5. 로컬 브라우저에서 확인
./ppt-motion serve ../motion-jobs/demo --port 4319
```

`http://127.0.0.1:4319/`를 엽니다. 서버는 해당 컴퓨터에서만 접근할 수 있습니다. 종료는 `Ctrl-C`입니다.

- 일부 페이지: `init`에 `--pages 1-11` 또는 `--pages 1,3-5` 추가.
- `research`: 모든 요소를 정적으로 시작하고 필요한 효과만 선택.
- `explain`: PPTX와 연결된 긴 본문에 짧은 페이드 적용. 제목·표·불확실한 PDF 텍스트는 유지.
- `static`: 효과 없이 원형을 확인하는 출발점.

계획 생성만으로 차트가 자동 애니메이션화되지는 않습니다. Codex 또는 사용자가 원본을 보고 정확한 요소와 메시지를 선택해야 합니다. [객체별 작업법](skill/ppt-motion/references/object-workflow.md)과 [세부 설정](skill/ppt-motion/references/configuration.md)에 예시가 있습니다.

## 발표 도구

- `←` / `→`: 이전·다음 페이지
- `R`: 현재 페이지 효과 다시 재생
- `F`: 전체화면. 하단 발표 설명은 숨김
- 효과·강조 켜기/끄기
- 원본 PDF와 나란히 비교
- 요소 선택으로 정확한 ID와 좌표 확인
- 운영체제의 동작 줄이기 설정 지원

`dist/`에는 외부 글꼴·스크립트 없이 동작하는 정적 웹 파일이 생성됩니다. `file://`로 직접 열기보다는 위 로컬 서버 또는 정적 호스팅을 사용하세요. 호스팅 배포는 별도 작업입니다.

## 반복 수정과 검증

`motion-plan.json`은 이름이 붙은 객체별 계획이고, `deck.json`은 빌드에 사용하는 정확한 설정입니다. 적용 전에 검증하며 이전 설정은 작업 폴더의 `history/`에 저장합니다.

원본·추출 결과·설정의 해시로 오래된 요소 ID를 잘못 적용하는 것을 막습니다. 설정을 수정한 뒤에는 다시 빌드해야 합니다. 새 계획은 `plan JOB --out JOB/motion-plan-v2.json`처럼 다른 파일로 생성할 수 있습니다.

`check`는 파일 해시와 SVG 도형·칠하기 순서를 검사합니다. 시각적 완성도와 메시지의 적절성까지 증명하지는 않으므로, 시작·중간·완료 프레임을 브라우저에서 확인하세요.

## 예제와 테스트

개인 발표자료 없이 생성한 가상 데이터로 테스트합니다.

```sh
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

## 저장소 구조

```text
ppt-motion                     CLI 진입점
skill/ppt-motion/
  SKILL.md                     Codex 작업 지침
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

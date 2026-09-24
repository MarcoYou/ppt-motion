# PPT Motion 사용 가이드

[README로 돌아가기](../README.md)

## 설치 상세

모든 환경은 같은 엔진과 모션 규칙을 사용합니다. 로컬 실행에는 Python **3.11 이상**이 필요합니다. ZIP은 [최신 릴리스](https://github.com/MarcoYou/ppt-motion/releases/latest)에서 받으세요.

### Codex

Codex 대화에서 다음 설치 요청을 사용합니다.

```text
$skill-installer https://github.com/MarcoYou/ppt-motion/tree/main/skill/ppt-motion
```

설치 후 Codex를 다시 시작하고 `$ppt-motion`으로 호출합니다.

네이티브 플러그인을 지원하는 Codex CLI에서는 다음 명령을 사용할 수 있습니다.

```sh
codex plugin marketplace add MarcoYou/ppt-motion
codex plugin add ppt-motion@ppt-motion
```

저장소 또는 [Codex 스킬 ZIP](https://github.com/MarcoYou/ppt-motion/releases/latest/download/ppt-motion-codex.zip)으로 직접 설치할 수도 있습니다. ZIP은 먼저 압축을 풉니다.

```sh
git clone https://github.com/MarcoYou/ppt-motion.git
cd ppt-motion
python3 install.py --client codex
```

설치 위치는 `${CODEX_HOME:-~/.codex}/skills/ppt-motion`입니다. 네이티브 플러그인과 개인 스킬 중 하나를 선택하세요.

### ChatGPT

[OpenAI 플러그인 ZIP](https://github.com/MarcoYou/ppt-motion/releases/latest/download/ppt-motion-openai-plugin.zip)을 제공합니다. 공개 디렉터리 등록 상태는 [README](../README.md#설치)를 확인하세요. 패키지 제공 자체가 ChatGPT 공개 디렉터리에서 설치할 수 있다는 뜻은 아닙니다.

### Claude Code

Claude Code에서 다음을 실행합니다.

```text
/plugin marketplace add MarcoYou/ppt-motion
/plugin install ppt-motion@ppt-motion
```

호출 이름은 `/ppt-motion:ppt-motion`입니다. 개인 스킬 폴더에 직접 설치하려면 저장소에서 다음을 실행합니다. 이 방식의 호출 이름은 `/ppt-motion`이며, 두 방식 중 하나를 선택하세요.

```sh
python3 install.py --client claude-code
```

직접 설치 위치는 `~/.claude/skills/ppt-motion`입니다. [Claude Code ZIP](https://github.com/MarcoYou/ppt-motion/releases/latest/download/ppt-motion-claude-code.zip)을 로컬에서 확인하려면 압축을 풀고 `claude --plugin-dir /path/to/ppt-motion`을 실행하세요. 설치 형식은 [플러그인 문서](https://code.claude.com/docs/en/plugins)와 [마켓플레이스 문서](https://code.claude.com/docs/en/plugin-marketplaces)를 따릅니다.

### Claude Desktop

1. [Desktop 스킬 ZIP](https://github.com/MarcoYou/ppt-motion/releases/latest/download/ppt-motion-claude-desktop.zip)을 받습니다. 압축을 풀지 않습니다.
2. **Customize → Skills → + → Create skill → Upload a skill**에서 ZIP을 추가하고 활성화합니다.
3. **코드 실행 및 파일 생성**을 활성화한 대화에 PDF와 필요한 PPTX를 첨부하고 PPT Motion으로 작업을 요청합니다.
4. 결과 HTML을 내려받아 브라우저에서 엽니다.

이 배포본은 Claude 대화의 실행 환경에서 동작하는 사용자 지정 스킬입니다. MCP 확장 파일(`.mcpb`)이나 로컬 파일 연결 도구가 아니므로 `/Users/...` 경로만 전달하면 파일을 읽을 수 없습니다. PDF 변환 도구가 없는 환경에서는 PowerPoint에서 내보낸 PDF도 첨부하세요.

앱에 스킬 관리 메뉴가 없으면 같은 계정으로 [Claude Skills](https://claude.ai/customize/skills)를 확인하세요. 계정·조직 설정에 따라 가용성이 달라집니다. [Anthropic 사용자 지정 스킬 안내](https://support.claude.com/en/articles/12512198-how-to-create-custom-skills)에서 지원 조건을 확인할 수 있습니다.

## 런타임·업데이트·오프라인

`scripts/run.py`는 지정 버전의 PyMuPDF와 lxml을 별도 캐시 가상환경에 준비하며 시스템 Python 패키지를 변경하지 않습니다. 최초 준비에는 패키지 다운로드가 필요하고, 이후에는 캐시를 재사용합니다. 호스팅 실행 환경의 캐시는 세션 사이에 사라질 수 있습니다.

저장소와 `install.py`로 설치한 경우 다음처럼 업데이트합니다.

```sh
git pull
python3 install.py --client codex
```

임의 위치에 설치하거나 런타임 준비를 미룰 수도 있습니다.

```sh
python3 install.py --client claude-code --skills-dir /path/to/skills --skip-runtime
```

설치기가 관리하는 수정되지 않은 스킬은 업데이트할 수 있습니다. 별도 설치본이나 사용자가 수정한 스킬은 자동으로 덮어쓰지 않습니다. 교체하려는 경우에만 `--force`를 사용하세요. 기존 폴더 또는 심볼릭 링크는 백업합니다.

`--skip-runtime`을 사용하면 첫 실행에서 의존성을 준비합니다. 미리 준비하려면 `python3 skill/ppt-motion/scripts/run.py --setup`을 실행하세요. 캐시 위치는 `PPT_MOTION_RUNTIME_ROOT`로 지정할 수 있습니다. 오프라인 설치에는 준비된 캐시 또는 `PIP_NO_INDEX=1`, `PIP_FIND_LINKS`로 지정한 호환 wheel 저장소가 필요합니다.

Windows에서는 `python3`를 설치된 `python` 또는 `py -3`으로 바꾸세요. 아래 CLI 명령은 저장소 루트에서 실행합니다.

## 파일 준비

- **PPTX + PDF:** PPTX에서 제목·표·차트 구조를 읽고, PDF를 디자인 기준으로 사용합니다.
- **PDF만 있음:** 텍스트와 벡터 도형을 추출해 효과를 적용할 영역을 선택합니다.
- **PPTX만 있음:** 같은 이름의 PDF를 먼저 찾습니다. 없으면 PowerPoint에서 PDF로 내보내세요.

LibreOffice가 설치되어 있으면 별도 PDF로 변환할 수 있습니다. 변환 후 글꼴·줄바꿈·차트가 원본과 맞는지 확인해야 합니다.

```sh
python3 ppt-motion doctor --pptx /path/deck.pptx
python3 ppt-motion export-pdf --pptx /path/deck.pptx --out /path/deck.pdf
```

## CLI 작업 흐름

```sh
# 1. 원본 추출. PDF만 있으면 --pptx를 생략합니다.
python3 ppt-motion init --pptx /path/deck.pptx --pdf /path/deck.pdf --out ../motion-jobs/demo

# 2. 수정 가능한 객체별 계획 생성
python3 ppt-motion plan ../motion-jobs/demo --profile research

# 3. motion-plan.json의 message, effect, ids, 좌표 등을 검토·수정한 뒤 적용
python3 ppt-motion apply-plan ../motion-jobs/demo

# 4. HTML 생성 및 원본 보존 검사
python3 ppt-motion build ../motion-jobs/demo
python3 ppt-motion check ../motion-jobs/demo

# 5. 서버 없이 열 수 있는 단일 HTML로 내보내기
python3 ppt-motion export-html ../motion-jobs/demo --out ../presentation.html

# 선택: 편집 중 로컬 미리보기
python3 ppt-motion serve ../motion-jobs/demo --port 4319
```

일부 페이지만 처리하려면 `init`에 `--pages 1-11` 또는 `--pages 1,3-5`를 추가합니다. `init`과 `export-html`은 기존 결과를 덮어쓰지 않으므로 새 작업 폴더·출력 파일 이름을 사용하세요. 기존 작업은 해당 폴더에서 이어서 수정합니다.

`serve` 실행 후 `http://127.0.0.1:4319/`를 엽니다. 해당 컴퓨터에서만 접근할 수 있으며 종료는 `Ctrl-C`입니다. 단일 HTML에는 슬라이드·원본 비교 이미지·CSS·JavaScript가 모두 포함되어 외부 서버나 글꼴·스크립트 다운로드 없이 열립니다. 편집용 `dist/`는 여러 파일로 구성되어 로컬 서버 또는 정적 호스팅이 필요합니다. 호스팅 배포는 별도 작업입니다.

### 계획과 효과 선택

- `research`: 모든 요소를 정적으로 시작하고 필요한 효과만 선택합니다.
- `explain`: PPTX와 연결된 긴 본문에 짧은 페이드를 적용합니다. 제목·표·불확실한 PDF 텍스트는 유지합니다.
- `static`: 효과 없이 원형을 확인하는 출발점입니다.

계획 생성만으로 차트가 자동 애니메이션화되지는 않습니다. 에이전트 또는 사용자가 원본을 보고 정확한 요소와 메시지를 선택해야 합니다. 막대는 실제 영점, 원형 차트는 공통 중심과 반경이 필요합니다. 제목·축·레이블·표의 숫자는 읽을 수 있게 유지하며 장식은 기본적으로 움직이지 않습니다.

[유형별 모션](../skill/ppt-motion/references/motion-language.md), [객체별 작업법](../skill/ppt-motion/references/object-workflow.md), [세부 설정](../skill/ppt-motion/references/configuration.md)에서 효과 선택과 설정 예시를 확인하세요.

## 반복 수정과 검증

`motion-plan.json`은 이름이 붙은 객체별 계획이고, `deck.json`은 빌드에 사용하는 정확한 설정입니다. `apply-plan`은 적용 전에 검증하며 이전 설정을 작업 폴더의 `history/`에 저장합니다. 새 계획은 `plan JOB --out JOB/motion-plan-v2.json`처럼 다른 파일로 생성할 수 있습니다.

원본·추출 결과·설정의 해시로 오래된 요소 ID를 잘못 적용하는 것을 막습니다. 원본이 바뀌면 새 작업을 만들고, 설정을 수정한 뒤에는 다시 빌드하세요. PPTX와 PDF의 페이지 대응은 텍스트 일치 또는 `--slide-map 1=1,2=3` 같은 명시적 매핑을 사용하며, 페이지 수가 같다는 이유만으로 가정하지 않습니다.

`check`는 파일 해시와 SVG 도형·칠하기 순서를 검사합니다. 시각적 완성도와 메시지의 적절성까지 증명하지는 않으므로 시작·중간·완료 프레임을 브라우저에서 확인하세요. 원본 비교, 효과 끄기, 페이지 이동, 다시 재생, 전체화면과 운영체제의 동작 줄이기 설정도 확인할 수 있습니다.

## 개발과 릴리스

자동화 테스트는 개인 발표자료 없이 생성한 가상 데이터로 실행합니다. 다음 명령은 ZIP 설치본이 아닌 Git으로 복제한 저장소에서 사용하세요.

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
python3 ppt-motion init --pptx ../motion-demo-source/generic-demo.pptx --pdf ../motion-demo-source/generic-demo.pdf --out ../motion-demo-job
python3 ppt-motion plan ../motion-demo-job --slide-map 1=1,2=2,3=3,4=4
```

예제 PDF는 직접 그린 디자인 기준이며 PPTX를 PowerPoint에서 내보낸 결과와 동일하다고 보장하지 않습니다. 검증 범위는 [QA.md](../QA.md), 데이터 구조와 엔진 계약은 [CONTRACT.md](../CONTRACT.md)에 정리했습니다.

릴리스 패키지는 저장소 루트에서 생성합니다.

```sh
python3 scripts/package_release.py
```

결과는 `dist/releases/`의 환경별 ZIP과 `SHA256SUMS`입니다. 배포 파일만 명시적으로 포함하며 원본 PDF/PPTX, 개인 작업 폴더, 추출 산출물과 런타임 캐시는 제외합니다. 엔진과 뷰어의 원본은 `skill/ppt-motion/`, 클라이언트별 지침은 `clients/`, 패키징 코드는 `scripts/package_release.py`에서 관리합니다.

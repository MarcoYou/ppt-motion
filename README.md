# PPT Motion

기존 PPT/PDF의 글꼴·배치·차트 모양을 유지하고, 핵심 메시지에 필요한 모션을 더합니다. 결과물은 서버 없이 열 수 있는 **단일 HTML 발표자료**입니다. PPTX에 PowerPoint 애니메이션을 추가하는 도구는 아닙니다.

## 설치

| 환경 | 설치 경로 |
|---|---|
| **Codex** | 아래 설치 요청을 Codex 대화에 입력 |
| **ChatGPT** | [제출 패키지](https://github.com/MarcoYou/ppt-motion/releases/latest/download/ppt-motion-openai-plugin.zip) 준비 · 개발자 신원 인증 후 공개 등록 진행 |
| **Claude Code** | 아래 마켓플레이스 명령 실행 |
| **Claude Desktop** | [스킬 ZIP](https://github.com/MarcoYou/ppt-motion/releases/latest/download/ppt-motion-claude-desktop.zip)을 **Customize → Skills**에서 업로드 |

**Codex**

```text
$skill-installer https://github.com/MarcoYou/ppt-motion/tree/main/skill/ppt-motion
```

설치 후 Codex를 다시 시작하고 `$ppt-motion`으로 호출합니다. 네이티브 플러그인과 수동 설치는 [설치 상세](docs/usage.md#설치-상세)를 참고하세요.

**Claude Code**

```text
/plugin marketplace add MarcoYou/ppt-motion
/plugin install ppt-motion@ppt-motion
```

설치 후 `/ppt-motion:ppt-motion`으로 호출합니다.

로컬 실행에는 Python **3.11 이상**이 필요하며, 처음 사용할 때 필요한 패키지를 별도 환경에 준비합니다. Claude Desktop에서는 **코드 실행 및 파일 생성**을 활성화하고 파일을 대화에 첨부하세요.

## 사용

PDF를 준비하고, 같은 자료의 PPTX가 있으면 함께 전달하세요. PDF는 디자인 기준, PPTX는 제목·표·차트 구조 파악에 사용합니다. PPTX만 있다면 PowerPoint에서 PDF도 내보내는 것을 권장합니다.

Codex에서는 파일 경로와 함께 다음처럼 요청합니다. Claude에서는 해당 호출 이름으로 바꾸거나 PPT Motion을 사용해 달라고 요청하세요.

> $ppt-motion 이 PPTX와 PDF의 앞 11페이지를 HTML 발표자료로 만들어줘. 원본 디자인과 순서는 유지하고, 막대는 영점에서 성장, 선은 경로 그리기, 도넛은 원 둘레를 따라 색이 채워지게 해줘. 제목과 표는 읽기 편하게 유지해줘.

완성된 HTML을 내려받아 브라우저에서 열면 됩니다. 효과는 한 번 재생하고 멈추며, 슬라이드는 직접 넘깁니다.

- `←` / `→`: 이전·다음 페이지
- `R`: 현재 페이지 효과 다시 재생
- `F`: 전체화면
- 뷰어에서 효과 켜기·끄기, 원본 비교, 요소 선택 지원

## 더 알아보기

- [사용 가이드](docs/usage.md): 설치·업데이트, CLI, 오프라인 실행, 개발·검증
- [유형별 모션](skill/ppt-motion/references/motion-language.md): 차트와 메시지에 맞는 효과
- [객체별 작업법](skill/ppt-motion/references/object-workflow.md) · [세부 설정](skill/ppt-motion/references/configuration.md)
- [최신 릴리스](https://github.com/MarcoYou/ppt-motion/releases/latest) · [검증 범위](QA.md)

이미지 한 장으로 된 차트는 개별 막대나 선을 움직이기 어렵습니다. 원본 수치와 주장의 검증은 포함하지 않습니다.

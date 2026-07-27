// 강의자료개발 수업별 standalone 프로그램 — 갤러리 '수업' 예제.
//
// 인라인 스니펫(snippets.js)과 달리, 이 예제들은 여러 모듈을 한 파일로 평탄화한 대용량
// tkinter GUI 앱(수천 줄)이다. 그래서 코드를 번들에 인라인하지 않고 public/examples/*.py
// 로 서빙하며, 갤러리에서 카드 클릭 시 지연 fetch 해 파이썬 편집기에 로드한다. 대용량이라
// 로드 시 자동 블록 변환은 하지 않는다(원하면 상단 Convert 버튼으로 수동 변환).
//
// 원본: busan-robotics/강의자료개발/수업_*/소스코드/*_standalone.py 를 dobotkit+tm 블록 기반
// 간결 버전으로 재작성한 것. 각 항목의 `file` 은 public/examples/ 아래 경로.
//
// ⚠ 실행에는 실제 하드웨어가 필요하다(로봇팔=DobotLink+전원, 카메라=웹캠). 예전 주석은 원본
// standalone 의 "자동 mock 내장"을 그대로 옮겨 적었는데, 간결 버전에는 mock 이 없어 사실과
// 달랐다(실측: h1 이 DobotConnectionError 로 즉시 크래시). 지금은 각 예제가 하드웨어 연결
// 실패를 try/except 로 잡아 한국어 안내를 출력하고 깔끔히 종료한다 — 학생 화면에 raw
// 트레이스백이 뜨지 않는다. 변환(블록화)은 하드웨어 없이도 항상 가능하다.
//
// snippets.js 와 동일하게 window 전역으로 노출한다(ExampleGalleryContent 가 두 소스를 합쳐 읽음).

const LESSON_EXAMPLES = [
  {
    id: 'lesson-m1-sorting',
    title: '[중등] AI 분리수거 로봇팔',
    category: '수업 (중등)',
    file: 'm1_ai_sorting.py',
    preview: '색을 배워서(tm) 색깔별로 옮기는 로봇팔(dobotkit).\ntm.Model·predict + arm.move_to/suck — 블록으로 변환됨.',
  },
  {
    id: 'lesson-m2-rps',
    title: '[중등] 사람과 가위바위보 (핸드트래킹)',
    category: '수업 (중등)',
    file: 'm2_gesture_rps.py',
    preview: '가위바위보 손 모양을 배워서(tm) 로봇팔이 이기는 손을 낸다.\ntm.Model·predict + dobotkit 팔 제어 — 블록으로 변환됨.',
  },
  {
    id: 'lesson-h1-nlcontrol',
    title: '[고등] 자연어로 로봇 제어 (VLA)',
    category: '수업 (고등)',
    file: 'h1_nl_control.py',
    preview: '고등 파이썬 수업 — 자연어 명령 해석기를 함수로 만들어 로봇팔 제어(dobotkit).\nparse_command/run_command + 입력 루프. 실제 파이썬 코드로 학습.',
  },
  {
    id: 'lesson-h2-teleop',
    title: '[고등] 텔레오퍼레이션 (제스처 전기능 제어)',
    category: '수업 (고등)',
    file: 'h2_teleop.py',
    preview: '고등 파이썬 수업 — 제스처 분류(tm) 학습 후 로봇팔 실시간 원격 조종.\ntrain_gesture_model/apply_gesture + 제어 루프. 실제 파이썬 코드로 학습.',
  },
  {
    id: 'lesson-h3-drive',
    title: '[고등] 비전 AI 자율주행 (가르쳐서 달리는 차)',
    category: '수업 (고등)',
    file: 'h3_vision_drive.py',
    preview: '고등 파이썬 수업 — 수집→학습→추론(tm)으로 Magician GO 자율주행(dobotkit).\ncollect_and_train/drive + 주행 루프. 실제 파이썬 코드로 학습.',
  },
];

if (typeof window !== 'undefined') window.BlockPyLessonExamples = LESSON_EXAMPLES;

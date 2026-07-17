// 강의자료개발 수업별 standalone 프로그램 — 갤러리 '수업' 예제.
//
// 인라인 스니펫(snippets.js)과 달리, 이 예제들은 여러 모듈을 한 파일로 평탄화한 대용량
// tkinter GUI 앱(수천 줄)이다. 그래서 코드를 번들에 인라인하지 않고 public/examples/*.py
// 로 서빙하며, 갤러리에서 카드 클릭 시 지연 fetch 해 파이썬 편집기에 로드한다. 대용량이라
// 로드 시 자동 블록 변환은 하지 않는다(원하면 상단 Convert 버튼으로 수동 변환).
//
// 원본: busan-robotics/강의자료개발/수업_*/소스코드/*_standalone.py (자동 mock 내장 —
// 하드웨어/API 키가 없어도 실행된다). 각 항목의 `file` 은 public/examples/ 아래 경로.
//
// snippets.js 와 동일하게 window 전역으로 노출한다(ExampleGallery 가 두 소스를 합쳐 읽음).

const LESSON_EXAMPLES = [
  {
    id: 'lesson-m1-sorting',
    title: '[중등] AI 분리수거 로봇팔',
    category: '수업 (중등)',
    file: 'm1_ai_sorting.py',
    preview: 'AI 비전 색상 분류로 물체를 집어 분류하는 로봇팔 GUI.\ntkinter · opencv · pydobot — 하드웨어 없으면 자동 mock.',
  },
  {
    id: 'lesson-m2-rps',
    title: '[중등] 사람과 가위바위보 (핸드트래킹)',
    category: '수업 (중등)',
    file: 'm2_gesture_rps.py',
    preview: 'MediaPipe 핸드트래킹으로 제스처를 읽어 로봇과 가위바위보(HRI).\ntkinter · mediapipe · pydobot — 하드웨어 없으면 자동 mock.',
  },
  {
    id: 'lesson-h1-nlcontrol',
    title: '[고등] 자연어로 로봇 제어 (VLA)',
    category: '수업 (고등)',
    file: 'h1_nl_control.py',
    preview: '자연어 지시 → VLM(눈) + LLM(두뇌) → 보고 집기(VLA).\n키/서버 없으면 자동 mock 폴백.',
  },
  {
    id: 'lesson-h2-teleop',
    title: '[고등] 텔레오퍼레이션 (제스처 전기능 제어)',
    category: '수업 (고등)',
    file: 'h2_teleop.py',
    preview: 'MediaPipe 손 제스처로 로봇팔 전기능을 원격 조종.\ntkinter · mediapipe · pydobot — 하드웨어 없으면 자동 mock.',
  },
  {
    id: 'lesson-h3-drive',
    title: '[고등] 비전 AI 자율주행 (가르쳐서 달리는 차)',
    category: '수업 (고등)',
    file: 'h3_vision_drive.py',
    preview: 'Teachable Machine 스타일 수집→학습→추론으로 주행하는 Magician GO.\nnumpy 필수 · CURRICULUM_FORCE_MOCK=1 로 오프라인 데모.',
  },
];

if (typeof window !== 'undefined') window.BlockPyLessonExamples = LESSON_EXAMPLES;

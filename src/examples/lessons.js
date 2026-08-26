// 강의자료개발 수업별 standalone 프로그램 — 갤러리 '수업' 예제.
//
// 인라인 스니펫(snippets.js)과 달리, 이 예제들은 파일로 서빙한다(public/examples/*.py).
// 갤러리에서 카드 클릭 시 지연 fetch 해 파이썬 편집기에 로드한다.
//
// 원본: busan-robotics/강의자료개발/수업_*/소스코드/*_standalone.py 를 dobotkit+tm 블록 기반
// 간결 버전으로 재작성한 것. 각 항목의 `file` 은 public/examples/ 아래 경로.
//
// ── 2026-08-11 개선(계약 7): 수업을 **단계별 파일 3개**로 쪼갰다 ──────────────
// 학생이 완성본을 한 번에 보면 어디서부터 손대야 할지 모른다. 그래서 각 차시를
// ①→②→③ 로 나누고, **각 단계가 앞 단계를 통째로 포함**하게 만들었다. 그래서
// 어느 파일 하나만 열어도 그것만으로 처음부터 끝까지 돌아간다.
//   중등 1차시: 찾기 → 잡기 → 놓기        (자리 맞추기 필요 — robotvision 으로 픽셀→로봇 좌표)
//   중등 2차시: 손보기 → 응수하기 → 대전하기 (자리 맞추기 불필요 — 제자리에서 집게만 여닫는다)
//   고등 1차시: 알아듣기 → 움직이기 → 대화하기
//   고등 2차시: 배우기 → 움직이기 → 조종하기
//   고등 3차시: 배우기 → 고르기 → 달리기
// 배열 순서 = 단계 순서다(갤러리에서 뒤섞이지 않게 하려고 일부러 이 순서로 둔다).
//
// 각 차시의 마지막 단계(③)와 **같은 내용**의 기존 파일도 그대로 남아 있다
// (m1_ai_sorting_blocks.py · m2_gesture_rps_blocks.py · h1_nl_control.py ·
//  h2_teleop.py · h3_vision_drive.py). 지우지 않되 목록에는 단계 파일만 싣는다.
// 더 긴 교사용 원본(m1_ai_sorting.py · m2_gesture_rps.py)도 디스크에만 남겨 둔다.
//
// ⚠ 실행에는 실제 하드웨어가 필요하다(로봇팔=DobotLink+전원, 카메라=웹캠).
// ①단계는 로봇 없이도 돌아간다(카메라만). 변환(블록화)은 하드웨어 없이도 항상 가능하다.
//
// snippets.js 와 동일하게 window 전역으로 노출한다(ExampleGalleryContent 가 두 소스를 합쳐 읽음).

const LESSON_EXAMPLES = [
  // ── 중등 1차시 — AI 분리수거 로봇팔 (보정값으로 어느 자리든 찾아가 집는다) ──
  {
    id: 'lesson-m1-1-find',
    title: '[중등 1-①] 찾기 — 무엇인지·어디 있는지 알아보기',
    category: '수업 (중등)',
    file: 'm1_1_찾기.py',
    preview: '카메라로 사진 한 장을 찍어 무엇인지(모델.predict)와\n어디 있는지(robotvision.find_object)를 화면에 찍어 본다. 로봇은 아직 쓰지 않는다.',
  },
  {
    id: 'lesson-m1-2-pick',
    title: '[중등 1-②] 잡기 — 찾은 그 자리로 가서 집기',
    category: '수업 (중등)',
    file: 'm1_2_잡기.py',
    preview: '카메라가 본 픽셀 자리를 robotvision.to_robot 으로 로봇 좌표(mm)로 바꿔\n그 자리로 팔을 보내 집는다. 미리 로봇 패널 → 자리 맞추기 를 해 두어야 한다.',
  },
  {
    id: 'lesson-m1-sorting',
    title: '[중등 1-③] 놓기 — 이름표대로 함에 옮겨 놓기',
    category: '수업 (중등)',
    file: 'm1_3_놓기.py',
    preview: '1차시 완성본. 캔·플라스틱·종이 세 갈래로 갈라 함에 옮겨 놓고\n처음 자리로 돌아온 뒤 펌프를 끈다.',
  },

  // ── 중등 2차시 — 가위바위보 (제자리에서 집게만 여닫는다: 자리 맞추기 불필요) ──
  {
    id: 'lesson-m2-1-see',
    title: '[중등 2-①] 손보기 — 사람이 무슨 손을 냈는지 알아보기',
    category: '수업 (중등)',
    file: 'm2_1_손보기.py',
    preview: '카메라로 손 사진을 찍어 가위·바위·보 중 무엇인지 물어본다.\n로봇은 아직 쓰지 않는다.',
  },
  {
    id: 'lesson-m2-2-respond',
    title: '[중등 2-②] 응수하기 — 이기는 손을 한 번 내 보기',
    category: '수업 (중등)',
    file: 'm2_2_응수하기.py',
    preview: '알아본 손에 맞춰 로봇이 이기는 손을 낸다.\n바위=집게 닫기 · 보=펴기 · 가위=바람 끄기 — 팔은 제자리에서 움직이지 않는다.',
  },
  {
    id: 'lesson-m2-rps',
    title: '[중등 2-③] 대전하기 — 다섯 판 겨루고 마무리',
    category: '수업 (중등)',
    file: 'm2_3_대전하기.py',
    preview: '2차시 완성본. 되풀이 블록으로 다섯 판을 겨루고,\n끝나면 집게를 펴고 펌프를 끈다.',
  },

  // ── 고등 1차시 — 자연어로 로봇 제어 (VLA) ──
  {
    id: 'lesson-h1-1-parse',
    title: '[고등 1-①] 알아듣기 — 말에서 동작과 자리 뽑아내기',
    category: '수업 (고등)',
    file: 'h1_1_알아듣기.py',
    preview: '자연어 문장에서 동작(집기/놓기)과 자리를 뽑아내는 parse_command 를 만든다.\n로봇 없이 함수만 만들어 시험한다.',
  },
  {
    id: 'lesson-h1-2-move',
    title: '[고등 1-②] 움직이기 — 알아들은 대로 팔 움직이기',
    category: '수업 (고등)',
    file: 'h1_2_움직이기.py',
    preview: '해석 결과를 로봇 동작으로 옮기는 run_command 를 붙인다.\n미리 적어 둔 명령 몇 개를 차례로 실행해 본다.',
  },
  {
    id: 'lesson-h1-nlcontrol',
    title: '[고등 1-③] 대화하기 — 말로 시키면 계속 움직이기',
    category: '수업 (고등)',
    file: 'h1_3_대화하기.py',
    preview: '고등 1차시 완성본. input 루프로 명령을 계속 받아 처리하고\n"끝" 을 입력하면 홈으로 돌아가 펌프를 끈다.',
  },

  // ── 고등 2차시 — 텔레오퍼레이션 ──
  {
    id: 'lesson-h2-1-learn',
    title: '[고등 2-①] 배우기 — 제스처를 가르치고 저장하기',
    category: '수업 (고등)',
    file: 'h2_1_배우기.py',
    preview: '제스처 6가지를 카메라로 보여 주며 샘플을 모아 학습하고 파일로 저장한다.\n로봇은 아직 쓰지 않는다.',
  },
  {
    id: 'lesson-h2-2-map',
    title: '[고등 2-②] 움직이기 — 제스처 하나를 동작으로 바꾸기',
    category: '수업 (고등)',
    file: 'h2_2_움직이기.py',
    preview: '인식한 이름표를 팔 동작으로 옮기는 apply_gesture 를 붙인다.\n사진 한 장만 보고 한 번 움직여 본다.',
  },
  {
    id: 'lesson-h2-teleop',
    title: '[고등 2-③] 조종하기 — 제스처로 계속 원격 조종',
    category: '수업 (고등)',
    file: 'h2_3_조종하기.py',
    preview: '고등 2차시 완성본. 제어 루프로 계속 손을 읽어 팔을 조종하고\n마치면 홈으로 돌아가 펌프를 끈다.',
  },

  // ── 고등 3차시 — 비전 AI 자율주행 ──
  {
    id: 'lesson-h3-1-learn',
    title: '[고등 3-①] 배우기 — 길 사진을 방향별로 모아 학습',
    category: '수업 (고등)',
    file: 'h3_1_배우기.py',
    preview: '왼쪽·직진·오른쪽 세 상황의 길 사진을 모아 주행 모델을 학습하고 저장한다.\n주행로봇은 아직 쓰지 않는다.',
  },
  {
    id: 'lesson-h3-2-choose',
    title: '[고등 3-②] 고르기 — 사진 한 장 보고 방향 고르기',
    category: '수업 (고등)',
    file: 'h3_2_고르기.py',
    preview: '예측한 방향을 차의 동작으로 옮기는 drive 를 붙인다.\n한 번만 움직인 뒤 반드시 멈춰 세운다.',
  },
  {
    id: 'lesson-h3-drive',
    title: '[고등 3-③] 달리기 — 스스로 길을 보며 자율주행',
    category: '수업 (고등)',
    file: 'h3_3_달리기.py',
    preview: '고등 3차시 완성본. 주행 루프로 계속 길을 보며 Magician GO 를 달리게 하고\n끝나면 차를 멈춘다.',
  },
];

if (typeof window !== 'undefined') window.BlockPyLessonExamples = LESSON_EXAMPLES;

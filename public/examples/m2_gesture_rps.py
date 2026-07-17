# -*- coding: utf-8 -*-
"""[M2] 사람과 가위바위보 (HRI) — 단일 파일(standalone) 버전.

원본(taskB_curriculum/m2_gesture_hri/gui.py + 의존 모듈들: common.config /
common.safety / common.vision(HandTracker) / common.dobot_ctl / common.gui /
m2_gesture_hri.solution)을 **하나의 파이썬 파일**로 합친 것.

자동 생성물 — 로직은 원본과 동일하다(중복 구현/재작성 아님). 여러 모듈을 한 네임스페이스로
평탄화하고, config./safety. 같은 모듈 한정 참조가 이 파일 자신을 가리키도록 alias 처리했다.

실행:  python 가위바위보_standalone.py     (하드웨어 없으면 자동 mock)
필요:  tkinter(표준), 선택적으로 opencv-python / mediapipe / pillow / numpy / pydobot.
"""
from __future__ import annotations

import sys as _sys

# ── 패키지 평탄화용 self-alias ───────────────────────────────────────────────
# 원본은 common 패키지로 나뉘어 `config.X` / `safety.X` / `_config` / `_accel`
# 처럼 모듈을 한정해 서로를 참조했다. 단일 파일에서는 그 이름들이 모두 '이 모듈'을
# 가리키게 하면, 아래에 이어붙인 각 원본 코드의 참조가 그대로 동작한다.
config  = _sys.modules[__name__]   # config.CAM_HAND / config.is_mock() ...
safety  = _sys.modules[__name__]   # safety.check_move / safety.clamp_move ...
_config = _sys.modules[__name__]   # common.vision 내부 별칭
_accel  = None                     # 선택적 GPU 가속(accel) 비활성 → 순수 cv2 경로

# numpy: 일부 비전 경로에서 사용(없으면 안내).
try:
    import numpy as np
    _HAS_NUMPY = True
except Exception:
    np = None
    _HAS_NUMPY = False



# ==============================================================================
# ── common/config.py
# ==============================================================================

"""common/config.py — 중앙 설정 모듈 (커리큘럼 전역 공통 설정)

목적
----
교육용 두봇(Dobot Magician Lite) 커리큘럼의 모든 단계가 공유하는 설정값을
한곳에 모아 둡니다. AI 클라이언트, 로봇 제어, 카메라 등 다른 모듈은 이 파일의
값을 읽어 동작 모드를 결정합니다.

핵심 원칙 (ADR-0004)
--------------------
하드웨어(로봇/카메라)나 API 키가 **없어도** import와 mock 실행이 가능해야 합니다.
따라서:
  * pydobot / pyserial 같은 하드웨어 의존 라이브러리는 try/except로 감싸 import 하고,
    없으면 자동으로 mock 모드로 폴백합니다.
  * ANTHROPIC_API_KEY 환경변수가 없으면 AI 호출도 mock 으로 동작합니다.
  * CURRICULUM_FORCE_MOCK=1 로 언제든 강제 mock 을 켤 수 있습니다.

사용법
------
    from common import config            # 또는 import common.config as config

    if config.is_mock():
        print("mock 모드로 동작합니다 (하드웨어/키 없음)")

    port = config.DOBOT_PORT             # None 이면 자동탐지
    model = config.LLM_MODEL

직접 실행하면 현재 설정을 출력합니다(자가 데모):
    python -m common.config
    python common/config.py

순수 표준 라이브러리(os)만 사용합니다 — 추가 설치 불필요.
"""

import os  # 환경변수 읽기에 사용(표준 라이브러리만)


# ---------------------------------------------------------------------------
# 1) 환경변수 헬퍼
# ---------------------------------------------------------------------------
def _env_true(name: str) -> bool:
    """환경변수가 '참'을 의미하는 값인지 판정한다.

    '1', 'true', 'yes', 'on'(대소문자 무관)을 참으로 본다.
    값이 없으면 False.
    """
    # 환경변수를 읽어 공백 제거 후 소문자로 정규화
    raw = os.environ.get(name, "").strip().lower()
    # 흔히 쓰는 참 표현들과 비교
    return raw in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# 2) 환경변수에서 직접 읽는 설정값
# ---------------------------------------------------------------------------

# 로봇 시리얼 포트. 지정하지 않으면 None → 연결 시 자동탐지(pydobot/list_ports).
#   예) Windows: "COM3" / Linux: "/dev/ttyUSB0"
DOBOT_PORT: "str | None" = os.environ.get("DOBOT_PORT") or None

# Anthropic API 키. 없으면 None → AI 클라이언트는 mock 응답으로 동작.
ANTHROPIC_API_KEY: "str | None" = os.environ.get("ANTHROPIC_API_KEY") or None


# ---------------------------------------------------------------------------
# 2-b) 엔드이펙터 / 집기(그래스프) 설정 — 실측 캘리브레이션 (실제 하드웨어 검증값)
# ---------------------------------------------------------------------------
# EFFECTOR: 부착한 엔드이펙터 종류. "gripper"(그리퍼: 잡기/놓기) | "suction"(흡착컵).
#   사용자의 실제 두봇 매지션 라이트는 '그리퍼'를 사용한다(실측 검증).
#   환경변수 DOBOT_EFFECTOR 로 덮어쓸 수 있다(예: "suction").
EFFECTOR = os.environ.get("DOBOT_EFFECTOR", "gripper")  # "gripper" | "suction"

# GRASP_Z: 블록을 집는(그래스프) 하강 높이(mm). 실측 캘리브레이션값.
#   초록 매트 위 블록 몸통을 그리퍼가 감싸는 높이로, 실제 하드웨어 테스트로 검증되었다.
#   교구/책상 높이가 다르면 이 값(또는 DOBOT_GRASP_Z 환경변수)을 조정한다.
GRASP_Z = float(os.environ.get("DOBOT_GRASP_Z", "-25"))  # 집기 높이(mm), 실측값(교구/책상에 맞춰 조정)

# BACKGROUND_COLORS: 매트/배경으로 '항상 무시'할 색 목록(실측 버그 대응).
#   사용자의 매트가 초록색이라, 카메라에 매트가 작게 보여도 '초록 블록'으로 오검출되는
#   문제가 있었다. 이 목록에 속한 색은 비전 단계에서 무조건 배경으로 제외한다(매트색).
#   기본 ["green"]. 환경변수 DOBOT_BG_COLORS(콤마구분, 예: "green,gray")로 변경한다.
BACKGROUND_COLORS = [c.strip() for c in os.environ.get("DOBOT_BG_COLORS", "green").split(",") if c.strip()]


# ---------------------------------------------------------------------------
# 2-c) 카메라 인덱스 — 환경 강건화 (실측 버그 대응)
# ---------------------------------------------------------------------------
# OpenCV(VideoCapture)의 카메라 인덱스는 **환경 의존**이며, 어떤 카메라가 먼저
# enable 되는지(드라이버 로드 순서/USB 허브/노트북 내장캠 on-off)에 따라 0↔1 이
# 런타임마다 바뀔 수 있다. 실측: 노트북 웹캠을 켜자 index 0↔1 이 스왑되어,
# 차시 코드가 `Camera(source=0)`/`VideoCapture(0)` 로 하드코딩돼 있으면 엉뚱한
# 카메라를 열어 동작이 틀어졌다.
#   → 차시는 인덱스 숫자 대신 아래 두 '의미 있는 이름'을 쓴다. 환경이 바뀌어
#     인덱스가 스왑되면 코드 수정 없이 환경변수만 조정하면 된다.
#
#   CAM_HAND  : 사용자를 향한 카메라(손/제스처용). M2 가위바위보, H2 텔레오퍼레이션.
#   CAM_TABLE : 위에서 책상/매트를 내려다보는 카메라(블록/색상용). M1 색상분류,
#               H1 VLM 장면설명, A1 음성 색블록 정리.
#
# 현재 사용자 환경 기준 기본값: index 0 = 노트북 웹캠(사용자 향함, 손 제스처용),
#                              index 1 = 책상/두봇 카메라(위에서 매트, 블록용).
# 인덱스가 스왑되면 환경변수로 조정한다(예: 손=1, 책상=0 으로 바뀐 경우):
#   set DOBOT_CAM_HAND=1   /   set DOBOT_CAM_TABLE=0   (Windows)
#   export DOBOT_CAM_HAND=1 ; export DOBOT_CAM_TABLE=0 (Linux/macOS)
CAM_HAND = int(os.environ.get("DOBOT_CAM_HAND", "0"))    # 사용자 향함(제스처 M2/H2)
CAM_TABLE = int(os.environ.get("DOBOT_CAM_TABLE", "1"))  # 위에서 매트(블록 M1/H1/A1)


# ---------------------------------------------------------------------------
# 2-d) 하드웨어 가속(GPU) 사용 정책 — 비전 처리가 CPU로 버거울 때
# ---------------------------------------------------------------------------
# CPU만으로 mediapipe 손추적/YOLO 객체검출이 느릴 수 있어, '가능하면' GPU를 쓴다.
# 가속이 불가하거나 초기화에 실패하면 항상 CPU로 안전 폴백한다(동작 보장).
#   "auto"(기본): GPU 가능하면 GPU, 아니면 CPU.
#   "on"/"1"    : GPU 우선(초기화/워밍업 실패 시 CPU 폴백).
#   "off"/"0"   : 강제 CPU.
# 적용 대상(common/accel.py 가 탐지·결정): mediapipe HandLandmarker GPU delegate,
#   YOLO(ultralytics)의 torch CUDA device. (OpenCV는 CUDA 빌드일 때만 해당)
USE_GPU = (os.environ.get("DOBOT_USE_GPU", "auto") or "auto").strip().lower()


# ---------------------------------------------------------------------------
# 3) AI 모델 기본값 (CONTRACTS 계약 고정값)
# ---------------------------------------------------------------------------

# 텍스트 LLM(소크라테스식 힌트 등)에 쓰는 기본 모델
LLM_MODEL = "claude-sonnet-4-6"

# 이미지 이해(VLM: 카메라 프레임 설명 등)에 쓰는 기본 모델
VLM_MODEL = "claude-sonnet-4-6"

# MiniMax(OpenAI 호환) — H1 자연어 제어 / A1 음성 오케스트레이션의 명령 해석용.
# 키는 환경변수 MINIMAX_API_KEY 로 주입한다(코드에 넣지 말 것).
MINIMAX_MODEL = os.environ.get("MINIMAX_MODEL", "MiniMax-M2.5")
MINIMAX_API_KEY = os.environ.get("MINIMAX_API_KEY", "")

# STT(로컬 whisper) 모델 크기: tiny/base/small/medium/large-v3.
# 한국어 정확도를 위해 기본을 "medium" 으로 둔다. faster-whisper 가 설치돼 있으면
# int8 로 CPU 에서도 medium 이 충분히 빠르다(권장: pip install faster-whisper).
# 교실 PC가 느리면 WHISPER_MODEL=small, 더 정확히는 large-v3 로 조정.
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "medium")


# ---------------------------------------------------------------------------
# 3-b) H1 VLA 확장 — 시각 그라운딩(눈: 로컬 Qwen3-VL) · 픽셀→로봇 캘리브레이션
# ---------------------------------------------------------------------------
# "카메라에 보이는 것 집어줘"(vision_pick/vision_place)용 설정.
#   두뇌 = MiniMax(위 3절), 눈 = Qwen3-VL 2B(llama.cpp 로컬 서버, OpenAI 호환).
#   서버·모델·키가 없어도 GroundingClient 가 자동으로 mock 폴백한다(ADR-0004).
#   모든 값은 같은 이름의 환경변수로 덮어쓸 수 있다.

# 이 파일(common/) 기준 커리큘럼 루트(taskB_curriculum)의 절대경로.
_TASKB_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 그라운딩 공급자: "qwen-local"(로컬 llama.cpp 서버) | "mock"(무서버 데모/테스트).
GROUNDING_PROVIDER = os.environ.get("GROUNDING_PROVIDER", "qwen-local")

# 로컬 Qwen3-VL 서버(OpenAI 호환)의 베이스 URL. ensure_server 기본 포트 8123 과 일치.
GROUNDING_URL = os.environ.get("GROUNDING_URL", "http://127.0.0.1:8123/v1")

# Qwen3-VL 2B GGUF 모델 / 멀티모달 프로젝터 / llama-server 실행파일 경로(이미 배치됨).
QWEN_MODEL_PATH = os.environ.get(
    "QWEN_MODEL_PATH",
    os.path.join(_TASKB_ROOT, "models", "Qwen3VL-2B-Instruct-Q4_K_M.gguf"))
QWEN_MMPROJ_PATH = os.environ.get(
    "QWEN_MMPROJ_PATH",
    os.path.join(_TASKB_ROOT, "models", "mmproj-Qwen3VL-2B-Instruct-Q8_0.gguf"))
LLAMA_SERVER_EXE = os.environ.get(
    "LLAMA_SERVER_EXE",
    os.path.join(_TASKB_ROOT, "models", "llamacpp", "llama-server.exe"))

# 픽셀→로봇 4점 호모그래피 캘리브레이션 저장 파일(JSON). common/calibration.py 가 사용.
CALIB_PATH = os.environ.get("CALIB_PATH", os.path.join(_TASKB_ROOT, "calibration.json"))

# vision_pick/vision_place 의 접근(호버) 높이·집기 하강 높이(mm).
VISION_Z_HOVER = float(os.environ.get("VISION_Z_HOVER", "40.0"))  # 실측 필요(테이블·블록 높이)
VISION_Z_PICK = float(os.environ.get("VISION_Z_PICK", "-40.0"))   # 실측 필요(테이블·블록 높이)

# 캘리브레이션 마법사(H1 GUI)의 프리셋 4좌표 — 로봇 작업평면 (x, y) mm.
#   마법사가 로봇을 이 4지점으로 순차 이동시키고, 강사가 각 지점의 엔드이펙터를
#   카메라 화면에서 클릭해 (픽셀, 로봇) 대응쌍 4개를 만든다(4점 호모그래피).
#   조건: WORKSPACE 안 + 카메라 화면 안 + 넓게 퍼진 사각형(퇴화 배치 금지).
CALIB_PRESETS = [           # 실측 필요(교실 카메라 화각 안에 4점이 다 보이는지 확인)
    (200.0, -80.0),
    (200.0, 80.0),
    (300.0, 80.0),
    (300.0, -80.0),
]


# ---------------------------------------------------------------------------
# 4) 작업영역(WORKSPACE) — Magician Lite 보수적 안전 한계
# ---------------------------------------------------------------------------
# 단위: x,y,z 는 mm, r 은 deg.
# safety.check_move / clamp_move 가 이 범위로 좌표를 검사·클램프한다.
# 강사매뉴얼과 일치하는 '보수적' 기본값으로, 실제 기구 한계보다 안쪽으로 잡아 둔다.
WORKSPACE = {
    "x": (180, 320),    # 전후 방향 도달 범위(mm). 너무 가까우면 자기 베이스와 충돌 위험
    "y": (-150, 150),   # 좌우 방향(mm)
    "z": (-60, 150),    # 높이(mm). 음수는 책상 면 아래로 내려가는 흡착/그립 동작용
    "r": (-150, 150),   # 엔드이펙터 회전(deg)
}


# ---------------------------------------------------------------------------
# 5) 하드웨어 의존 라이브러리 가용성 점검 (없으면 mock 유도)
# ---------------------------------------------------------------------------
# pydobot / pyserial 이 설치되어 있지 않으면 실제 로봇 제어가 불가능하므로
# 자동으로 mock 모드로 폴백한다. import 자체는 절대 실패하지 않도록 try/except 로 감싼다.
try:
    import serial  # type: ignore[import-untyped]  # noqa: F401  (pyserial — pydobot 의 시리얼 통신 의존성)
    import pydobot  # type: ignore[import-untyped]  # noqa: F401  (순수 Python Dobot 드라이버)

    _HARDWARE_LIBS_AVAILABLE = True   # 두 라이브러리 모두 import 성공
except Exception:
    # 라이브러리 미설치/로드 실패 → 하드웨어 제어 불가로 간주
    _HARDWARE_LIBS_AVAILABLE = False

# opencv(cv2) 가용성 — 비전(카메라/색검출/제스처)의 실제 동작 가능 여부.
# LLM 키와 무관하다. (실제 웹캠이 없으면 vision 모듈이 합성 프레임으로 자동 폴백)
try:
    import cv2  # noqa: F401
    _CV2_AVAILABLE = True
except Exception:
    _CV2_AVAILABLE = False


# ---------------------------------------------------------------------------
# 6) USE_MOCK 자동판정
# ---------------------------------------------------------------------------
def _decide_use_mock() -> bool:
    """mock 모드 사용 여부를 자동 판정한다.

    다음 중 하나라도 해당하면 mock(True):
      1) CURRICULUM_FORCE_MOCK 환경변수가 참 → 강제 mock
      2) ANTHROPIC_API_KEY 가 없음 → AI 호출 불가
      3) pydobot/serial import 실패 → 로봇 제어 불가
    """
    # 1) 강제 mock 스위치가 켜져 있으면 즉시 True
    if _env_true("CURRICULUM_FORCE_MOCK"):
        return True
    # 2) AI 키가 없으면 AI 기능을 실제로 호출할 수 없으므로 mock
    if not ANTHROPIC_API_KEY:
        return True
    # 3) 하드웨어 라이브러리가 없으면 실제 로봇 제어 불가 → mock
    if not _HARDWARE_LIBS_AVAILABLE:
        return True
    # 위 조건이 모두 아니면 실제(real) 모드로 동작 가능
    return False


# 모듈 로드 시점에 한 번 자동 판정한 값(다른 모듈이 직접 참조하는 기본 플래그)
USE_MOCK: bool = _decide_use_mock()


def is_mock() -> bool:
    """현재 mock 모드인지 반환한다.

    CONTRACTS 계약 함수. 다른 모듈(dobot_ctl, ai_clients 등)은 mock 인자를
    명시하지 않았을 때 이 함수를 호출해 동작 모드를 결정한다.

    참고: 환경변수가 런타임에 바뀔 수 있으므로 매 호출 시 다시 판정해
    최신 상태를 반영한다(전역 USE_MOCK 도 함께 갱신).
    """
    global USE_MOCK
    # 호출 시점 기준으로 재판정하여 환경변수 변경을 반영
    USE_MOCK = _decide_use_mock()
    return USE_MOCK


# ---------------------------------------------------------------------------
# 6-b) 서브시스템별 mock 판정 (핵심: LLM 키 유무가 로봇/비전을 좌우하지 않게 분리)
#   - 로봇 : pydobot/serial 유무로만 결정 (LLM 키와 무관)
#   - 비전 : opencv(cv2) 유무로만 결정 (LLM 키와 무관; 실카메라 없으면 합성 폴백)
#   - AI   : ANTHROPIC_API_KEY 유무로만 결정 (Smart Tutor·H1·A1 에서만 사용)
#   CURRICULUM_FORCE_MOCK=1 이면 셋 다 강제 mock(오프라인 테스트용).
# 설계 원칙: LLM 은 '학생 개발 보조(Smart Tutor)'와 불가피한 H1 자연어·A1 음성에만
#           쓰며, 그 외 수업/로봇/비전은 LLM 없이 동작해야 한다.
# ---------------------------------------------------------------------------
def robot_is_mock() -> bool:
    """로봇을 mock 으로 돌릴지. FORCE_MOCK 또는 pydobot/serial 미설치일 때만 True.
    (LLM 키가 없어도 로봇은 실제로 구동되어야 한다.)"""
    if _env_true("CURRICULUM_FORCE_MOCK"):
        return True
    return not _HARDWARE_LIBS_AVAILABLE


def vision_is_mock() -> bool:
    """비전을 mock 으로 돌릴지. FORCE_MOCK 또는 opencv(cv2) 미설치일 때만 True.
    (실제 웹캠이 없으면 vision 모듈이 합성 프레임으로 자동 폴백한다.)"""
    if _env_true("CURRICULUM_FORCE_MOCK"):
        return True
    return not _CV2_AVAILABLE


def ai_is_mock() -> bool:
    """LLM/VLM/STT 를 mock 으로 돌릴지. FORCE_MOCK 또는 ANTHROPIC_API_KEY 없음."""
    if _env_true("CURRICULUM_FORCE_MOCK"):
        return True
    return not ANTHROPIC_API_KEY


# ---------------------------------------------------------------------------
# 7) 자가 데모 — 현재 설정 출력 (mock, 무하드웨어 실행 가능)
# ---------------------------------------------------------------------------



# ==============================================================================
# ── common/safety.py
# ==============================================================================

"""common/safety.py — SFR-002 안전필터 (학생용 두봇 라이트 교육 플랫폼).

목적
----
초·중·고 학생이 작성한 로봇 제어 코드와 실시간 좌표 명령이
로봇팔(또는 사람)을 다치게 하지 않도록 "한 번 더" 걸러 주는 안전 계층.

세 가지 역할
-------------
1) check_move(x, y, z, r)  : 한 점이 작업영역(WORKSPACE) 안인지 검사 → (안전여부, 한국어메시지)
2) clamp_move(x, y, z, r)  : 작업영역을 벗어난 좌표를 경계값으로 "끌어당겨" 보정
3) scan_code(source)       : 학생 코드 문자열을 정규식+AST로 정적 분석 →
                             위험 패턴([{line, severity, message}]) 목록 반환
                             (Z 과다 하강, 좌표/관절 범위 초과, while True 무한루프+정지없음,
                              큐 미정지, 흡착/그리퍼 미해제 등)

설계 원칙
---------
- WORKSPACE 는 common/config.py 에서 import 한다(단일 출처). config.py 가 아직
  없거나 import 실패해도 동작하도록 try/except 로 감싸 CONTRACTS.md 의
  기본값으로 자동 폴백한다(하드웨어·키 없이 import/실행 보장).
- AST 파싱이 SyntaxError 로 실패하면(학생 코드가 아직 미완성) 정규식 결과만 반환한다.
- 모든 경고문은 학생이 바로 이해할 수 있는 친절한 한국어로 작성한다.

사용법
------
    from common.safety import check_move, clamp_move, scan_code

    ok, msg = check_move(200, 0, 50)          # (True, "안전")
    x, y, z, r = clamp_move(500, 0, -200)     # 경계값으로 보정
    for w in scan_code(open("student.py").read()):
        print(w["line"], w["severity"], w["message"])

직접 실행(자가 데모, mock):
    python -m common.safety        # 또는  python common/safety.py
"""


import ast       # AST 기반 코드 분석(무한루프/큐 미정지 등 구조적 패턴 탐지)
import re        # 정규식 기반 1차 스캔(좌표/관절 숫자 추출 등)

# ---------------------------------------------------------------------------
# WORKSPACE 가져오기 — config 단일 출처, 실패 시 CONTRACTS.md 기본값으로 폴백
# ---------------------------------------------------------------------------
try:
    # 정상 경로: 패키지 설치/sys.path 가 taskB_curriculum 인 경우
    pass
except Exception:  # pragma: no cover - import 실패는 폴백으로 흡수
    try:
        # 상대 import 폴백(같은 패키지 내부에서 호출될 때)
        pass
    except Exception:
        # 최종 폴백: config.py 가 아직 없어도 import/실행이 되도록 기본값 사용
        # (값은 CONTRACTS.md 의 WORKSPACE 와 동일하게 유지할 것)
        WORKSPACE = {
            "x": (180, 320),    # 전후(mm)
            "y": (-150, 150),   # 좌우(mm)
            "z": (-60, 150),    # 상하(mm) — z 하한(-60)보다 더 내려가면 책상/지그 충돌 위험
            "r": (-150, 150),   # 엔드이펙터 회전(deg)
        }

# 관절(Joint) 각도 보수적 한계(deg). config 에는 없으므로 여기서 정의.
# 학생 코드가 j1~j4 또는 joint 값을 직접 다룰 때 범위 초과를 경고하는 데 쓴다.
JOINT_LIMITS = {
    "j1": (-90, 90),
    "j2": (0, 85),
    "j3": (-10, 90),
    "j4": (-150, 150),
}

# 심각도 단계 — 학생/검수자가 우선순위를 빠르게 파악하도록 3단계로 통일
SEV_CRITICAL = "critical"   # 즉시 충돌·고장 위험 (실행 금지 권장)
SEV_WARNING = "warning"     # 위험 가능성 (확인 후 실행)
SEV_INFO = "info"           # 권장사항 (안전 습관)


# ===========================================================================
# 1) 이동 좌표 검사 / 보정
# ===========================================================================
def check_move(x, y, z, r=0.0):
    """좌표 한 점이 작업영역(WORKSPACE) 안에 있는지 검사한다.

    반환: (bool 안전여부, str 한국어 메시지)
    - 안전하면 (True, "안전")
    - 벗어나면 (False, "어느 축이 어떻게 벗어났는지" 설명)
    """
    problems = []  # 위반 사항을 모아 한 번에 안내(학생이 여러 축을 동시에 고치도록)

    # 각 축을 (값, 라벨, 단위)로 묶어 동일한 로직으로 검사 → 코드 중복 제거
    for value, key, unit, label in (
        (x, "x", "mm", "X(전후)"),
        (y, "y", "mm", "Y(좌우)"),
        (z, "z", "mm", "Z(상하)"),
        (r, "r", "deg", "R(회전)"),
    ):
        lo, hi = WORKSPACE[key]          # 해당 축의 (하한, 상한)
        if value < lo:                   # 하한보다 작음
            extra = " ⚠ 너무 깊게 내려가 책상/물체와 충돌할 수 있어요." if key == "z" else ""
            problems.append(
                f"{label} 값 {value}{unit} 이(가) 최소 {lo}{unit} 보다 작습니다.{extra}"
            )
        elif value > hi:                 # 상한보다 큼
            problems.append(
                f"{label} 값 {value}{unit} 이(가) 최대 {hi}{unit} 을(를) 넘었습니다."
            )

    if problems:
        # 여러 위반을 줄바꿈으로 묶어 친절하게 안내
        return False, "작업영역을 벗어났습니다:\n  - " + "\n  - ".join(problems)
    return True, "안전"


def clamp_move(x, y, z, r=0.0):
    """작업영역을 벗어난 좌표를 경계값으로 끌어당겨 보정한다.

    로봇이 명령을 거부하는 대신 "가장 가까운 안전한 점"으로 옮겨 주는 용도.
    반환: (x, y, z, r) — 모두 WORKSPACE 범위 안으로 보정된 float 튜플
    """
    def _clamp(value, key):
        lo, hi = WORKSPACE[key]
        # max(lo, min(value, hi)) : 하한과 상한 사이로 가둔다(클램프)
        return float(max(lo, min(float(value), hi)))

    return (_clamp(x, "x"), _clamp(y, "y"), _clamp(z, "z"), _clamp(r, "r"))


# ===========================================================================
# 2) 코드 정적 분석 (정규식 + AST)
# ===========================================================================
def scan_code(source: str):
    """학생 코드 문자열을 분석해 위험 패턴 목록을 반환한다.

    반환: list[dict] — 각 항목 {"line": int, "severity": str, "message": str}
                       (line 은 1부터, 줄을 특정할 수 없으면 0)

    탐지 항목:
      - Z 과다 하강            : z 가 WORKSPACE['z'] 하한보다 낮은 이동 명령
      - 좌표/관절 범위 초과     : move_to / SetPTPCmd 좌표, joint 각도 범위 밖
      - while True 무한루프     : 내부에 break/return/정지 호출이 없는 경우
      - 큐 미정지              : start_exec 만 있고 stop_exec 가 없음
      - 엔드이펙터 미해제       : suck(True)/grip(True) 후 해제(False) 없음
      - 안전 검사 누락(info)    : 이동 명령은 있는데 check_move/clamp_move 호출이 전혀 없음
    """
    findings: list[dict] = []  # 결과 누적
    if not source or not source.strip():
        return findings

    lines = source.splitlines()

    # ----- (A) 정규식 1차 스캔: 줄 단위로 좌표/관절 숫자를 직접 검사 -----
    findings.extend(_scan_regex(lines))

    # ----- (B) AST 2차 스캔: 구조적 패턴(무한루프·큐/이펙터 미해제) 검사 -----
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        # 학생 코드가 아직 문법 오류면 AST 분석은 건너뛰고 안내만 추가
        findings.append({
            "line": e.lineno or 0,
            "severity": SEV_INFO,
            "message": "코드에 문법 오류가 있어 구조 분석은 건너뛰었어요. "
                       "먼저 문법 오류부터 고쳐 주세요.",
        })
    else:
        findings.extend(_scan_ast(tree, source))

    # 줄 번호 → 심각도 순으로 정렬해 보기 좋게 반환
    sev_rank = {SEV_CRITICAL: 0, SEV_WARNING: 1, SEV_INFO: 2}
    findings.sort(key=lambda f: (f["line"], sev_rank.get(f["severity"], 9)))
    return findings


# --- 정규식 1차 스캔 -------------------------------------------------------
# move_to(...) / SetPTPCmd(...) 안의 숫자 좌표를 잡아내기 위한 패턴들
_MOVE_CALL_RE = re.compile(r"\b(?:move_to|go)\s*\(([^)]*)\)")
_PTP_CALL_RE = re.compile(r"\bSetPTPCmd\s*\(([^)]*)\)")
# joint/관절 값을 숫자로 직접 대입하는 흔한 형태: j1 = 120, joint1=120 등
_JOINT_ASSIGN_RE = re.compile(r"\b(?:joint|j)\s*([1-4])\s*=\s*(-?\d+(?:\.\d+)?)")
_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")  # 인자 문자열에서 숫자만 추출


def _scan_regex(lines):
    """줄 단위 정규식 스캔 — Z 과다 하강 / 좌표·관절 범위 초과 탐지."""
    out = []
    z_lo, z_hi = WORKSPACE["z"]
    x_lo, x_hi = WORKSPACE["x"]
    y_lo, y_hi = WORKSPACE["y"]

    for i, line in enumerate(lines, start=1):
        # 주석은 분석 제외(# 뒤 무시) — 단순하지만 교육용으로 충분
        code = line.split("#", 1)[0]

        # move_to(x, y, z, ...) / go(...) 좌표 검사
        m = _MOVE_CALL_RE.search(code)
        if m:
            out.extend(_check_xyz_args(_NUM_RE.findall(m.group(1)), i,
                                       x_lo, x_hi, y_lo, y_hi, z_lo, z_hi))

        # SetPTPCmd(api, mode, x, y, z, r, ...) — 앞의 api/mode 2개를 건너뛴 좌표
        m = _PTP_CALL_RE.search(code)
        if m:
            nums = _NUM_RE.findall(m.group(1))
            # mode 가 숫자(0~9)로 들어오는 경우가 많아 첫 숫자(mode)는 제외
            coord_nums = nums[1:] if nums else nums
            out.extend(_check_xyz_args(coord_nums, i,
                                       x_lo, x_hi, y_lo, y_hi, z_lo, z_hi))

        # joint/관절 직접 대입 검사
        for jm in _JOINT_ASSIGN_RE.finditer(code):
            jkey = "j" + jm.group(1)
            val = float(jm.group(2))
            lo, hi = JOINT_LIMITS[jkey]
            if not (lo <= val <= hi):
                out.append({
                    "line": i,
                    "severity": SEV_CRITICAL,
                    "message": f"관절 {jkey} 각도 {val}° 가 안전 범위({lo}°~{hi}°)를 "
                               f"벗어났어요. 무리한 각도는 모터 손상·충돌을 일으킬 수 있어요.",
                })
    return out


def _check_xyz_args(nums, line, x_lo, x_hi, y_lo, y_hi, z_lo, z_hi):
    """이동 호출에서 추출한 숫자 리스트(x, y, z, ...)의 범위를 검사."""
    out = []
    if len(nums) < 3:
        # 좌표가 변수일 수 있음(숫자 3개 미만) → 정적 분석 대상 아님
        return out
    x, y, z = float(nums[0]), float(nums[1]), float(nums[2])

    # Z 과다 하강은 가장 흔하고 위험한 실수 → 별도 critical 메시지
    if z < z_lo:
        out.append({
            "line": line,
            "severity": SEV_CRITICAL,
            "message": f"Z={z}mm 로 너무 깊게 내려갑니다(하한 {z_lo}mm). "
                       f"로봇팔이 책상이나 물체에 부딪힐 수 있어요. "
                       f"Z 값을 {z_lo}mm 이상으로 올려 주세요.",
        })
    elif z > z_hi:
        out.append({
            "line": line, "severity": SEV_WARNING,
            "message": f"Z={z}mm 가 상한 {z_hi}mm 을 넘었어요. 도달하지 못할 수 있어요.",
        })

    # X, Y 범위 검사
    if not (x_lo <= x <= x_hi):
        out.append({
            "line": line, "severity": SEV_WARNING,
            "message": f"X={x}mm 가 작업영역({x_lo}~{x_hi}mm)을 벗어났어요.",
        })
    if not (y_lo <= y <= y_hi):
        out.append({
            "line": line, "severity": SEV_WARNING,
            "message": f"Y={y}mm 가 작업영역({y_lo}~{y_hi}mm)을 벗어났어요.",
        })
    return out


# --- AST 2차 스캔 ----------------------------------------------------------
# 큐/이펙터 관련 메서드 이름(정지·해제 여부 판단에 사용)
_QUEUE_START = {"_set_queued_cmd_start_exec", "SetQueuedCmdStartExec", "start_exec"}
_QUEUE_STOP = {"_set_queued_cmd_stop_exec", "SetQueuedCmdStopExec",
               "SetQueuedCmdForceStopExec", "stop_exec", "close", "disconnect"}
_LOOP_STOP_CALLS = {"close", "disconnect", "stop", "stop_exec",
                    "SetQueuedCmdStopExec", "SetQueuedCmdForceStopExec"}
# 이동/안전 관련 호출 이름
_MOVE_NAMES = {"move_to", "go", "SetPTPCmd"}
_SAFETY_NAMES = {"check_move", "clamp_move", "scan_code"}


def _call_name(node):
    """ast.Call 노드에서 호출되는 함수/메서드 이름(마지막 식별자)을 추출."""
    func = node.func
    if isinstance(func, ast.Name):          # foo(...)
        return func.id
    if isinstance(func, ast.Attribute):     # obj.foo(...)
        return func.attr
    return None


def _collect_call_names(node):
    """주어진 AST 서브트리 안의 모든 호출 이름 집합을 모은다."""
    names = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            n = _call_name(sub)
            if n:
                names.add(n)
    return names


def _scan_ast(tree, source):
    """AST 기반 구조 분석 — 무한루프 / 큐 미정지 / 이펙터 미해제 / 안전검사 누락."""
    out = []

    # (1) while True / while 1 무한루프 + 정지 수단 없음
    for node in ast.walk(tree):
        if isinstance(node, ast.While) and _is_constant_true(node.test):
            body_calls = _collect_call_names(node)
            has_break = any(isinstance(s, ast.Break) for s in ast.walk(node))
            has_return = any(isinstance(s, ast.Return) for s in ast.walk(node))
            has_stop = bool(body_calls & _LOOP_STOP_CALLS)
            if not (has_break or has_return or has_stop):
                out.append({
                    "line": node.lineno,
                    "severity": SEV_CRITICAL,
                    "message": "while True 무한 반복 안에 멈출 방법(break·return·정지/연결해제)이 "
                               "없어요. 로봇이 영원히 멈추지 않을 수 있으니 종료 조건을 넣어 주세요.",
                })

    # (2) 전체 코드 호출 이름 집합 — 큐/이펙터/안전 검사 판단에 사용
    all_calls = _collect_call_names(tree)

    # 큐 시작은 있는데 정지가 없음
    if (all_calls & _QUEUE_START) and not (all_calls & _QUEUE_STOP):
        out.append({
            "line": _first_call_line(tree, _QUEUE_START),
            "severity": SEV_WARNING,
            "message": "명령 큐를 시작(start_exec)했지만 정지(stop_exec)나 연결 해제(close)가 "
                       "없어요. 작업이 끝나면 큐를 멈추고 로봇 연결을 해제해 주세요.",
        })

    # (3) 흡착/그리퍼 ON 후 OFF 없음 — suck(True)/grip(True) 만 있고 해제 없음
    out.extend(_scan_effector_release(tree))

    # (4) 이동 명령은 있는데 안전 검사(check_move/clamp_move)가 전혀 없음(권장)
    if (all_calls & _MOVE_NAMES) and not (all_calls & _SAFETY_NAMES):
        out.append({
            "line": _first_call_line(tree, _MOVE_NAMES),
            "severity": SEV_INFO,
            "message": "이동 명령 전에 check_move()/clamp_move() 로 좌표를 한 번 확인하면 "
                       "더 안전해요. 안전 검사를 습관화해 보세요.",
        })

    return out


def _is_constant_true(test):
    """while 의 조건이 항상 참(True 또는 1)인지 판단."""
    if isinstance(test, ast.Constant):
        return bool(test.value)  # True 또는 0이 아닌 상수
    return False


def _first_call_line(tree, names):
    """주어진 이름 집합에 해당하는 첫 호출의 줄 번호(없으면 0)."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _call_name(node) in names:
            return node.lineno
    return 0


def _scan_effector_release(tree):
    """suck(True)/grip(True) 로 켠 뒤 해제(False) 호출이 없으면 경고."""
    out = []
    turned_on = {}   # {"suck": line, "grip": line} — 켠 위치 기록
    turned_off = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if name not in ("suck", "grip"):
            continue
        # 첫 인자(또는 enable=) 가 True/1 이면 ON, False/0 이면 OFF 로 판단
        on = _first_bool_arg(node)
        if on is True:
            turned_on.setdefault(name, node.lineno)
        elif on is False:
            turned_off.add(name)

    label = {"suck": "흡착(suck)", "grip": "그리퍼(grip)"}
    for name, line in turned_on.items():
        if name not in turned_off:
            out.append({
                "line": line,
                "severity": SEV_WARNING,
                "message": f"{label[name]} 을(를) 켰지만(True) 끄는 명령(False)이 없어요. "
                           f"작업이 끝나면 {label[name]} 을(를) 꺼서 물체를 놓아 주세요.",
            })
    return out


def _first_bool_arg(node):
    """호출의 첫 위치 인자 또는 enable= 키워드에서 True/False 를 추출(없으면 None)."""
    # 위치 인자 우선
    if node.args:
        a = node.args[0]
        if isinstance(a, ast.Constant) and isinstance(a.value, (bool, int)):
            return bool(a.value)
    # 키워드 인자(enable=, on=) 확인
    for kw in node.keywords:
        if kw.arg in ("enable", "on") and isinstance(kw.value, ast.Constant):
            return bool(kw.value.value)
    return None


# ===========================================================================
# 자가 데모 (mock) — 하드웨어/키 없이 위험 코드 샘플을 스캔해 결과 출력
# ===========================================================================



# ==============================================================================
# ── common/vision.py — HandTracker 포함
# ==============================================================================

"""common/vision.py — 비전(카메라/색검출/객체검출/손제스처) 공통 모듈.

목적
----
국립부산과학관 두봇 라이트 교육 커리큘럼의 **비전 입력 계층**을 담당한다.
색 블록 픽앤플레이스, YOLO 객체검출, 손 제스처 기반 상호작용 차시가 모두
이 모듈의 동일한 인터페이스(CONTRACTS.md) 위에서 동작한다.

핵심 원칙 (ADR-0004)
--------------------
- **하드웨어·모델·API 키 없이도 import와 실행이 된다.** opencv / numpy /
  ultralytics(YOLO) / mediapipe 같은 무거운 의존성은 모두 try/except로 감싸,
  없으면 자동으로 mock 모드로 폴백한다.
- mock 모드에서는 numpy(있으면)로 합성 프레임(색상 블록 배치)을 만들고,
  검출기는 결정적인 캔드(canned) 결과를 돌려준다 → 교실에서 카메라가 없어도
  학생이 코드 흐름을 그대로 체험할 수 있다.

사용법
------
    from common.vision import Camera, detect_colors, YoloDetector, HandTracker

    with Camera(mock=True) as cam:          # 카메라 열기 (없으면 mock)
        frame = cam.read()                  # 한 프레임 획득(ndarray)
        blocks = detect_colors(frame)       # [{color,bbox,center,area}, ...]
        hands = HandTracker(mock=True).process(frame)
        gesture = HandTracker.classify_gesture(hands.get("landmarks"))

자가 데모
---------
    python -m common.vision      (또는 직접 실행)
  → mock 프레임을 만들어 색검출 결과와 제스처 분류 결과를 출력한다.

인터페이스 계약: deliverables/pm/CONTRACTS.md  →  common/vision.py 절
"""


# os: 모델 캐시 경로 계산·파일 존재 확인에 사용(표준 라이브러리 — 항상 가용).
import os

# ──────────────────────────────────────────────────────────────────────────
# 안전한 의존성 import — 없으면 mock으로 폴백 (하드웨어/모델/키 불필요)
# ──────────────────────────────────────────────────────────────────────────

# numpy: 프레임은 ndarray로 표현. 없으면 합성 프레임도 못 만들므로 가장 기초.
try:
    import numpy as np  # noqa: N813 (관례상 np)
    _HAS_NUMPY = True
except Exception:  # pragma: no cover - 환경에 numpy가 없을 때만
    np = None  # type: ignore[assignment]  # 이후 코드에서 _HAS_NUMPY로 분기
    _HAS_NUMPY = False

# opencv: HSV 변환·윤곽 검출·카메라 캡처에 사용. 없으면 mock 색검출로 폴백.
try:
    import cv2  # type: ignore
    _HAS_CV2 = True
except Exception:
    cv2 = None  # type: ignore[assignment]
    _HAS_CV2 = False

# config: 전역 mock 판정. 아직 작성 전이거나 import 실패해도 vision은 동작해야 함.
try:
    _config = config
except Exception:
    _config = None  # type: ignore[assignment]

# accel: GPU 가속 정책/탐지. 없거나 실패해도 vision 은 CPU 로 동작해야 함.
try:
    _accel = None
except Exception:
    _accel = None  # type: ignore[assignment]


def _global_is_mock() -> bool:
    """config.is_mock()이 있으면 그 값을, 없으면 numpy 유무로 추정.

    config 모듈이 아직 없거나 import에 실패해도 vision 단독으로 동작하도록
    방어적으로 처리한다. numpy조차 없으면 무조건 mock.
    """
    if _config is not None:
        try:
            # 비전 전용 판정(vision_is_mock)을 우선 사용 — opencv 유무로만 결정하며
            # LLM 키와 무관(설계: 비전은 LLM 없이 동작). 구버전 호환으로 is_mock 폴백.
            decider = getattr(_config, "vision_is_mock", None) or getattr(_config, "is_mock", None)
            if decider is not None:
                return bool(decider())
        except Exception:
            pass
    # config가 없으면: numpy/opencv가 없으면 당연히 mock
    return not (_HAS_NUMPY and _HAS_CV2)


# ──────────────────────────────────────────────────────────────────────────
# 색상 팔레트 — HSV(OpenCV 기준: H 0~179, S 0~255, V 0~255) 임계 범위
#   빨강은 색상환 양끝(0 근처 + 179 근처)에 걸쳐 두 구간으로 나눈다.
#   각 값은 (BGR표시색, [ (low,high), ... ]) 형태.
# ──────────────────────────────────────────────────────────────────────────
DEFAULT_PALETTE: dict[str, dict] = {
    "red": {
        "bgr": (0, 0, 255),
        "ranges": [((0, 80, 60), (10, 255, 255)),
                   ((170, 80, 60), (179, 255, 255))],
    },
    "green": {
        "bgr": (0, 200, 0),
        "ranges": [((40, 60, 50), (85, 255, 255))],
    },
    "blue": {
        "bgr": (255, 0, 0),
        "ranges": [((100, 80, 50), (130, 255, 255))],
    },
    "yellow": {
        "bgr": (0, 220, 220),
        "ranges": [((20, 80, 80), (35, 255, 255))],
    },
}

# 검출로 인정할 최소 면적(픽셀). 너무 작은 잡음 블롭은 무시.
_MIN_AREA = 400


# ──────────────────────────────────────────────────────────────────────────
# Camera — 실제 웹캠 또는 mock(합성/샘플) 프레임 공급자
# ──────────────────────────────────────────────────────────────────────────
class Camera:
    """카메라 프레임 공급원.

    파라미터
    --------
    source : int | str
        OpenCV VideoCapture에 넘길 카메라 인덱스(0) 또는 동영상 경로.
    mock : bool | None
        None이면 config.is_mock()/환경으로 자동 판정. True면 강제 mock.
    sample_dir : str | None
        mock일 때 이 폴더의 이미지(jpg/png)를 순환 재생. 없으면 합성 프레임 생성.
    """

    def __init__(self, source=0, mock=None, sample_dir=None):
        # mock 여부 결정: 명시값 우선, 없으면 전역 판정
        self.mock = _global_is_mock() if mock is None else bool(mock)
        self.source = source
        self.sample_dir = sample_dir
        self._cap = None            # 실제 카메라(VideoCapture) 핸들
        self._samples: list = []    # mock 샘플 이미지 경로 목록
        self._idx = 0               # 샘플/합성 프레임 순환 인덱스

        if self.mock:
            # mock: 샘플 폴더가 있으면 이미지 목록을 모은다(없으면 합성으로 폴백)
            self._load_samples()
        else:
            # 실제 카메라 열기. 실패하면 친절히 mock으로 강등.
            if not _HAS_CV2:
                print("[Camera] OpenCV가 없어 mock 모드로 전환합니다.")
                self.mock = True
                self._load_samples()
            else:
                self._cap = cv2.VideoCapture(self.source)
                if not self._cap or not self._cap.isOpened():
                    print(f"[Camera] 카메라({self.source})를 열 수 없어 "
                          "mock 모드로 전환합니다.")
                    self.mock = True
                    self._cap = None
                    self._load_samples()

    # --- 컨텍스트 매니저: with Camera() as cam: 형태로 안전하게 열고 닫기 ---
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False  # 예외를 삼키지 않음

    def _load_samples(self):
        """sample_dir에서 이미지 경로를 수집(있을 때만). os는 지연 import."""
        if not self.sample_dir:
            return
        try:
            import os
            exts = (".jpg", ".jpeg", ".png", ".bmp")
            files = sorted(
                os.path.join(self.sample_dir, f)
                for f in os.listdir(self.sample_dir)
                if f.lower().endswith(exts)
            )
            self._samples = files
        except Exception:
            # 폴더가 없거나 접근 불가 → 합성 프레임으로 폴백
            self._samples = []

    def read(self):
        """한 프레임을 반환한다.

        - 실제 카메라: VideoCapture.read()
        - mock + 샘플폴더: 폴더 이미지 순환(읽기 실패 시 합성으로 폴백)
        - mock + 폴더없음: numpy 합성 프레임(색상 블록 배치)
        반환: np.ndarray (H, W, 3) BGR. numpy가 전혀 없으면 RuntimeError.
        """
        if not self.mock and self._cap is not None:
            ok, frame = self._cap.read()
            if not ok:
                # 스트림 끝/오류 → mock으로 안전하게 폴백
                print("[Camera] 프레임 읽기 실패 → mock 합성 프레임 사용.")
                return self._synthetic_frame()
            return frame

        # mock: 샘플 폴더 이미지가 있으면 순환 재생
        if self._samples and _HAS_CV2:
            path = self._samples[self._idx % len(self._samples)]
            self._idx += 1
            img = cv2.imread(path)
            if img is not None:
                return img
            # 읽기 실패 시 합성으로 폴백

        # 합성 프레임
        frame = self._synthetic_frame()
        self._idx += 1
        return frame

    def _synthetic_frame(self, w=640, h=480):
        """numpy로 합성 프레임 생성 — 회색 배경에 색상 블록 3개 배치.

        red/green/blue 블록을 고정 좌표에 그려, detect_colors가 항상
        결정적으로 3개를 잡도록 한다(교육용 재현성).
        numpy가 없으면 RuntimeError로 명확히 안내.
        """
        if not _HAS_NUMPY:
            raise RuntimeError(
                "numpy가 없어 합성 프레임을 만들 수 없습니다. "
                "`pip install numpy` 후 다시 시도하세요."
            )
        # 중립 회색 배경(BGR) — 색 블록과 대비되도록
        frame = np.full((h, w, 3), 60, dtype=np.uint8)

        # (color_name, (cx, cy)) — 블록 중심을 가로로 분산 배치
        layout = [
            ("red", (140, 240)),
            ("green", (320, 240)),
            ("blue", (500, 240)),
        ]
        half = 55  # 블록 한 변 절반 길이(→ 약 110x110 정사각형)
        for name, (cx, cy) in layout:
            bgr = DEFAULT_PALETTE[name]["bgr"]
            # BGR 채널을 직접 채워 채도/명도 높은 블록을 그린다
            frame[cy - half:cy + half, cx - half:cx + half] = bgr
        return frame

    def release(self):
        """카메라 자원 해제(있을 때만)."""
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None


# ──────────────────────────────────────────────────────────────────────────
# detect_colors — HSV 임계 기반 색 블록 검출
# ──────────────────────────────────────────────────────────────────────────
def detect_colors(frame, palette=None) -> list[dict]:
    """프레임에서 팔레트 색상 블록을 찾아 목록으로 반환한다.

    파라미터
    --------
    frame : np.ndarray (BGR)
        Camera.read()가 돌려준 프레임.
    palette : dict | None
        DEFAULT_PALETTE 형식. None이면 기본 팔레트(red/green/blue/yellow).

    반환
    ----
    list[dict] : [{color, bbox, center, area}, ...]
        bbox=(x,y,w,h), center=(cx,cy), area=면적(px). 면적 내림차순 정렬.

    동작
    ----
    opencv/numpy가 있으면 HSV 마스크 → 윤곽선으로 실제 검출.
    둘 중 하나라도 없으면 mock 캔드 결과(합성 프레임 좌표와 동일)를 반환.
    """
    palette = palette or DEFAULT_PALETTE

    # opencv/numpy 미설치 또는 frame이 ndarray가 아니면 캔드 결과로 폴백
    if not (_HAS_CV2 and _HAS_NUMPY) or not _is_ndarray(frame):
        return _mock_color_detections(palette)

    # BGR → HSV 변환 (OpenCV 색검출의 표준 전처리)
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    results: list[dict] = []

    for color_name, spec in palette.items():
        # 한 색에 여러 HSV 구간(예: 빨강)이 있을 수 있어 마스크를 OR로 합친다
        mask = None
        for (lo, hi) in spec["ranges"]:
            lo_arr = np.array(lo, dtype=np.uint8)
            hi_arr = np.array(hi, dtype=np.uint8)
            part = cv2.inRange(hsv, lo_arr, hi_arr)
            mask = part if mask is None else cv2.bitwise_or(mask, part)

        if mask is None:  # 팔레트에 HSV 구간(ranges)이 하나도 없으면 이 색은 건너뜀
            continue

        # 노이즈 제거: 열림(open) 연산으로 작은 점/구멍 정리
        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

        # 윤곽선 검출(외곽선만). OpenCV 버전별 반환 개수 차이 방어.
        found = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                 cv2.CHAIN_APPROX_SIMPLE)
        contours = found[-2]  # (img,)contours,hierarchy → 뒤에서 2번째가 contours

        for cnt in contours:
            area = float(cv2.contourArea(cnt))
            if area < _MIN_AREA:
                continue  # 잡음 블롭 무시
            x, y, w, h = cv2.boundingRect(cnt)  # 외접 사각형
            results.append({
                "color": color_name,
                "bbox": (int(x), int(y), int(w), int(h)),
                "center": (int(x + w / 2), int(y + h / 2)),
                "area": area,
            })

    # 큰 블록이 먼저 오도록 면적 내림차순 정렬(픽 우선순위에 유용)
    results.sort(key=lambda d: d["area"], reverse=True)
    return results


def _mock_color_detections(palette) -> list[dict]:
    """opencv 없이도 쓰는 캔드 색검출 결과(합성 프레임 좌표와 일치)."""
    # _synthetic_frame의 red/green/blue 블록 위치(half=55)와 동일하게 맞춤
    canned = [
        ("red", 140, 240),
        ("green", 320, 240),
        ("blue", 500, 240),
    ]
    half = 55
    side = half * 2
    out = []
    for name, cx, cy in canned:
        if name not in palette:
            continue
        out.append({
            "color": name,
            "bbox": (cx - half, cy - half, side, side),
            "center": (cx, cy),
            "area": float(side * side),
        })
    return out


# ──────────────────────────────────────────────────────────────────────────
# YoloDetector — ultralytics YOLO 래퍼 (없으면 캔드 박스)
# ──────────────────────────────────────────────────────────────────────────
class YoloDetector:
    """ultralytics YOLO 객체 검출 래퍼.

    ultralytics가 없거나 mock이면 모델 로드를 건너뛰고 캔드 박스를 반환한다.
    """

    def __init__(self, model="yolo11n.pt", mock=None):
        self.mock = _global_is_mock() if mock is None else bool(mock)
        self.model_name = model
        self._model = None
        self.device = "cpu"   # 추론 디바이스: 'cuda'(가속) | 'cpu'

        if self.mock:
            return  # mock이면 무거운 모델 로드 자체를 하지 않음

        # 실제 모드: ultralytics 지연 import. 실패하면 mock으로 강등.
        try:
            from ultralytics import YOLO  # type: ignore
            self._model = YOLO(model)  # 가중치 파일 로드(다운로드 발생 가능)
            # 가속: 정책상 GPU 가능하면 CUDA 로(아니면 CPU). 실패해도 CPU 로 안전 폴백.
            self.device = _accel.torch_device() if _accel is not None else "cpu"
            if self.device != "cpu":
                try:
                    self._model.to(self.device)   # 가중치를 GPU 로 이동(예열)
                    print(f"[YoloDetector] CUDA(GPU) 사용(가속): device={self.device}")
                except Exception as e:
                    print(f"[YoloDetector] GPU 이동 실패({type(e).__name__}) → CPU.")
                    self.device = "cpu"
        except Exception as e:
            print(f"[YoloDetector] ultralytics 로드 실패({e}) → mock 전환.")
            self.mock = True

    def detect(self, frame) -> list[dict]:
        """프레임에서 객체를 검출해 [{label, conf, bbox}, ...]를 반환.

        bbox=(x, y, w, h) (좌상단 + 폭/높이). mock이면 캔드 박스.
        """
        if self.mock or self._model is None or not _is_ndarray(frame):
            return self._mock_detections()

        # 실제 추론. 결과 파싱 중 예외가 나면 안전하게 캔드로 폴백.
        try:
            res = self._model(frame, device=self.device, verbose=False)[0]  # 가속 device 지정
            out: list[dict] = []
            names = getattr(self._model, "names", {})
            for box in res.boxes:
                # xyxy(좌상단/우하단) → xywh로 변환
                x1, y1, x2, y2 = [float(v) for v in box.xyxy[0].tolist()]
                cls_id = int(box.cls[0])
                out.append({
                    "label": names.get(cls_id, str(cls_id)),
                    "conf": float(box.conf[0]),
                    "bbox": (int(x1), int(y1), int(x2 - x1), int(y2 - y1)),
                })
            return out
        except Exception as e:
            print(f"[YoloDetector] 추론 실패({e}) → mock 박스 반환.")
            return self._mock_detections()

    @staticmethod
    def _mock_detections() -> list[dict]:
        """모델 없이 쓰는 캔드 객체 검출 결과(교육 데모용 고정값)."""
        return [
            {"label": "cube", "conf": 0.92, "bbox": (110, 200, 110, 110)},
            {"label": "cube", "conf": 0.88, "bbox": (470, 200, 110, 110)},
            {"label": "hand", "conf": 0.75, "bbox": (260, 120, 130, 160)},
        ]


# ──────────────────────────────────────────────────────────────────────────
# HandTracker — MediaPipe Hands 래퍼 (없으면 캔드 랜드마크)
# ──────────────────────────────────────────────────────────────────────────
class HandTracker:
    """MediaPipe 손 추적 래퍼 + 제스처 분류.

    mediapipe가 없거나 mock이면 캔드 랜드마크를 반환한다.
    랜드마크는 21개 점의 (x, y, z) 정규화 좌표(0~1) 리스트.

    백엔드 우선순위(초기화 시 자동 선택):
      1) 레거시 ``mp.solutions.hands`` (구버전 mediapipe, ≤0.10.x 일부)
      2) Tasks API ``mp.tasks.vision.HandLandmarker`` (신버전; 0.10.35 등)
         - 모델 파일 ``models/hand_landmarker.task`` 를 자동 다운로드/캐시.
      3) 둘 다 불가 → mock 폴백(캔드 랜드마크).
    어떤 단계든 실패하면 친절한 메시지 후 안전하게 mock 으로 강등한다.
    """

    # MediaPipe Hands 21개 랜드마크 인덱스 중 분류에 쓰는 핵심 점
    WRIST = 0
    THUMB_TIP = 4
    INDEX_MCP = 5   # 검지 첫 마디(손바닥쪽)
    INDEX_TIP = 8
    MIDDLE_MCP = 9
    MIDDLE_TIP = 12
    RING_TIP = 16
    PINKY_TIP = 20

    # Tasks API HandLandmarker 모델(.task) 다운로드 정보
    _MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/"
                  "hand_landmarker/hand_landmarker/float16/1/"
                  "hand_landmarker.task")
    # 저장 위치: 이 파일(common/) 기준 상위 루트의 models/ 폴더
    #   (os 는 모듈 상단에서 안전하게 import 됨 — 미설치 환경이 없는 표준 라이브러리)
    _MODEL_PATH = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "models", "hand_landmarker.task",
    )

    def __init__(self, mock=None):
        self.mock = _global_is_mock() if mock is None else bool(mock)
        self._hands = None        # 레거시 mp.solutions.hands.Hands 인스턴스
        self._landmarker = None   # Tasks API HandLandmarker 인스턴스
        self._mp = None
        self._backend = "mock"    # 'solutions' | 'tasks' | 'mock'
        self._delegate = "CPU"    # 'GPU' | 'CPU' — Tasks API 가속 delegate(폴백 후 실제값)

        if self.mock:
            return  # mock이면 mediapipe 초기화 생략

        # 실제 모드: mediapipe 지연 import. 실패 시 mock 강등.
        try:
            import mediapipe as mp  # type: ignore
            self._mp = mp
        except Exception as e:
            print(f"[HandTracker] mediapipe 로드 실패({e}) → mock 전환.")
            self.mock = True
            return

        # 1) 레거시 solutions API 가 있으면 그대로 사용(구버전 호환)
        if hasattr(mp, "solutions") and hasattr(getattr(mp, "solutions"), "hands"):
            try:
                self._hands = mp.solutions.hands.Hands(
                    static_image_mode=True,      # 단일 프레임 처리(추적 누적 X)
                    max_num_hands=1,             # 교육 데모: 한 손만
                    min_detection_confidence=0.5,
                )
                self._backend = "solutions"
                return
            except Exception as e:
                print(f"[HandTracker] solutions API 초기화 실패({e}) → Tasks API 시도.")
                self._hands = None

        # 2) Tasks API(HandLandmarker) 시도 — 신버전 mediapipe(0.10.35 등)
        if hasattr(mp, "tasks"):
            try:
                self._init_tasks_api(mp)
                self._backend = "tasks"
                return
            except Exception as e:
                print(f"[HandTracker] Tasks API 초기화 실패({e}) → mock 전환.")
                self._landmarker = None

        # 3) 둘 다 불가 → mock 폴백
        print("[HandTracker] 사용 가능한 mediapipe 손 검출 백엔드가 없어 "
              "mock 모드로 전환합니다.")
        self.mock = True

    # --- Tasks API 초기화(모델 다운로드 + GPU/CPU delegate 선택) -------------
    def _init_tasks_api(self, mp):
        """mp.tasks.vision.HandLandmarker 를 IMAGE 모드로 생성한다.

        가속: 정책상 GPU 를 시도(가능 시)하고, 생성/워밍업이 실패하면 CPU 로 폴백한다.
        모델(.task)이 없으면 _MODEL_URL 에서 받아 _MODEL_PATH 에 캐시한다.
        네트워크 실패/오프라인이면 RuntimeError 를 던져 상위에서 mock 폴백.
        """
        model_path = self._ensure_model()  # 없으면 다운로드(실패 시 예외)

        # Tasks API 구성요소 가져오기(신버전 mediapipe 경로)
        BaseOptions = mp.tasks.BaseOptions
        vision = mp.tasks.vision
        HandLandmarker = vision.HandLandmarker
        HandLandmarkerOptions = vision.HandLandmarkerOptions
        RunningMode = vision.RunningMode

        def _build(delegate=None):
            # delegate 가 None 이면 인자 자체를 빼서 '구버전 mediapipe 원래 동작(CPU)'과 동일하게.
            if delegate is not None:
                base = BaseOptions(model_asset_path=model_path, delegate=delegate)
            else:
                base = BaseOptions(model_asset_path=model_path)
            options = HandLandmarkerOptions(
                base_options=base,
                running_mode=RunningMode.IMAGE,   # 단일 프레임(추적 누적 X)
                num_hands=1,                      # 교육 데모: 한 손만
                min_hand_detection_confidence=0.5,
            )
            return HandLandmarker.create_from_options(options)

        # delegate enum 이 있는 버전만 GPU/CPU 를 명시한다. 없으면 인자 없이 빌드(=원래 동작).
        Delegate = getattr(BaseOptions, "Delegate", None)
        prefer_gpu = bool(_accel is not None and _accel.mediapipe_prefer_gpu())

        # 1) 정책이 GPU 시도(auto/on)이고 delegate enum 이 있으면 GPU 로 만들고 워밍업 검증
        if prefer_gpu and Delegate is not None:
            try:
                lm = _build(Delegate.GPU)
                self._warmup(mp, lm)          # GPU delegate 가 실제로 도는지 1회 검증
                self._landmarker = lm
                self._delegate = "GPU"
                print("[HandTracker] Tasks API: GPU delegate 사용(가속).")
                return
            except Exception as e:
                # 데스크톱 Windows 등 GPU delegate 미지원 → 조용히 CPU 로 폴백
                print(f"[HandTracker] GPU delegate 사용 불가({type(e).__name__}) → CPU 폴백.")

        # 2) CPU(기본/폴백). delegate enum 이 없으면 인자 없이(=구버전 원래 동작).
        self._landmarker = _build(Delegate.CPU if Delegate is not None else None)
        self._delegate = "CPU"

    def _warmup(self, mp, landmarker):
        """작은 더미 이미지로 1회 detect 해 delegate(특히 GPU)가 실제 동작하는지 검증한다.

        GPU delegate 는 create 는 성공해도 첫 추론에서 실패하는 플랫폼이 있어,
        여기서 한 번 돌려 보고 예외가 나면 호출측이 CPU 로 폴백하게 한다.
        numpy 가 없으면 검증을 건너뛴다(이후 process 에서 처리).
        """
        if not _HAS_NUMPY:
            return
        dummy = np.zeros((48, 48, 3), dtype=np.uint8)
        img = mp.Image(image_format=mp.ImageFormat.SRGB, data=dummy)
        landmarker.detect(img)   # 예외 발생 시 상위 try 가 받아 CPU 폴백

    def backend_info(self) -> str:
        """현재 손추적 백엔드/가속 요약 문자열(GUI 로그용)."""
        if self.mock:
            return "mock(캔드 랜드마크)"
        if self._backend == "tasks":
            return f"mediapipe Tasks/{self._delegate}"
        if self._backend == "solutions":
            return "mediapipe solutions/CPU"
        return self._backend

    @classmethod
    def _ensure_model(cls):
        """HandLandmarker 모델 파일을 보장한다(있으면 그대로, 없으면 다운로드).

        반환: 모델 파일의 절대 경로(str).
        네트워크 실패/오프라인이면 친절한 메시지 후 RuntimeError 를 던진다.
        """
        model_path = cls._MODEL_PATH
        # 이미 존재하고 비어있지 않으면 재다운로드 생략
        if os.path.exists(model_path) and os.path.getsize(model_path) > 0:
            return model_path

        os.makedirs(os.path.dirname(model_path), exist_ok=True)
        print(f"[HandTracker] HandLandmarker 모델 다운로드 중 …\n"
              f"            URL : {cls._MODEL_URL}\n"
              f"            저장: {model_path}")
        try:
            import urllib.request
            # 임시 파일로 받아 완료 후 교체(부분 다운로드로 오염 방지)
            tmp_path = model_path + ".part"
            urllib.request.urlretrieve(cls._MODEL_URL, tmp_path)
            os.replace(tmp_path, model_path)
            print("[HandTracker] 모델 다운로드 완료.")
            return model_path
        except Exception as e:
            # 부분 파일 정리
            try:
                if os.path.exists(model_path + ".part"):
                    os.remove(model_path + ".part")
            except Exception:
                pass
            raise RuntimeError(
                "HandLandmarker 모델을 내려받지 못했습니다(오프라인/네트워크 문제일 수 있음). "
                f"수동으로 아래 URL 의 파일을 받아 {model_path} 에 두면 됩니다.\n"
                f"  {cls._MODEL_URL}\n  (원인: {e})"
            ) from e

    def process(self, frame) -> dict:
        """프레임에서 손을 찾아 {landmarks, handedness}를 반환(없으면 {}).

        landmarks : list[(x, y, z)] (21개, 정규화 0~1)
        handedness : 'Left' | 'Right'

        백엔드(solutions/tasks)에 따라 입력 처리만 다르고, 반환 형식은 동일하다.
        """
        if (self.mock
                or (self._hands is None and self._landmarker is None)
                or not _is_ndarray(frame)):
            return self._mock_hand()

        try:
            # MediaPipe는 RGB 입력을 기대 → BGR에서 변환
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB) if _HAS_CV2 else frame

            if self._backend == "tasks":
                return self._process_tasks(rgb)
            return self._process_solutions(rgb)
        except Exception as e:
            print(f"[HandTracker] 처리 실패({e}) → mock 랜드마크 반환.")
            return self._mock_hand()

    def _process_solutions(self, rgb) -> dict:
        """레거시 solutions API 로 손을 검출해 표준 dict 로 변환."""
        res = self._hands.process(rgb)
        if not res.multi_hand_landmarks:
            return {}  # 손을 못 찾음
        lm = res.multi_hand_landmarks[0].landmark
        landmarks = [(p.x, p.y, p.z) for p in lm]
        handed = "Right"
        if res.multi_handedness:
            handed = res.multi_handedness[0].classification[0].label
        return {"landmarks": landmarks, "handedness": handed}

    def _process_tasks(self, rgb) -> dict:
        """Tasks API HandLandmarker 로 손을 검출해 표준 dict 로 변환.

        반환 형식은 solutions 경로와 동일: {'landmarks': [(x,y,z)*21], 'handedness': ...}
        손이 없으면 {} 반환(기존 계약 유지).
        """
        mp = self._mp
        # numpy RGB → mp.Image(SRGB). frame 이 ndarray 가 아니면 process()에서 걸러짐.
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        res = self._landmarker.detect(mp_image)
        if not res.hand_landmarks:
            return {}  # 손을 못 찾음
        lm = res.hand_landmarks[0]            # 첫 손의 21개 정규화 랜드마크
        landmarks = [(p.x, p.y, p.z) for p in lm]
        handed = "Right"
        # handedness 는 [[Category, ...], ...] 구조(첫 손의 최상위 라벨)
        try:
            if res.handedness and res.handedness[0]:
                handed = res.handedness[0][0].category_name
        except Exception:
            pass
        return {"landmarks": landmarks, "handedness": handed}

    @staticmethod
    def _mock_hand() -> dict:
        """캔드 랜드마크 — '편 손(open)'으로 분류되도록 구성한 21점."""
        # 손목을 아래(y 큰 값), 손가락 끝을 위(y 작은 값)에 두어 '펴짐'을 표현.
        # 인덱스별 (x, y, z). z는 0으로 단순화.
        lm = [(0.5, 0.95, 0.0)] * 21  # 일단 손목 위치로 초기화
        # 손목
        lm[0] = (0.50, 0.95, 0.0)
        # 엄지: 손목에서 옆+위로 뻗음
        lm[1] = (0.42, 0.88, 0.0)
        lm[2] = (0.36, 0.80, 0.0)
        lm[3] = (0.32, 0.73, 0.0)
        lm[4] = (0.28, 0.66, 0.0)   # 엄지 끝
        # 검지(5 MCP → 8 TIP): 위로 곧게 펴짐
        lm[5] = (0.46, 0.62, 0.0)
        lm[6] = (0.46, 0.50, 0.0)
        lm[7] = (0.46, 0.40, 0.0)
        lm[8] = (0.46, 0.30, 0.0)   # 검지 끝(MCP보다 한참 위 = 펴짐)
        # 중지(9 → 12)
        lm[9] = (0.52, 0.62, 0.0)
        lm[10] = (0.52, 0.48, 0.0)
        lm[11] = (0.52, 0.36, 0.0)
        lm[12] = (0.52, 0.26, 0.0)  # 중지 끝
        # 약지(13 → 16)
        lm[13] = (0.58, 0.63, 0.0)
        lm[14] = (0.58, 0.50, 0.0)
        lm[15] = (0.58, 0.39, 0.0)
        lm[16] = (0.58, 0.30, 0.0)  # 약지 끝
        # 새끼(17 → 20)
        lm[17] = (0.64, 0.66, 0.0)
        lm[18] = (0.64, 0.55, 0.0)
        lm[19] = (0.64, 0.46, 0.0)
        lm[20] = (0.64, 0.38, 0.0)  # 새끼 끝
        return {"landmarks": lm, "handedness": "Right"}

    @staticmethod
    def classify_gesture(landmarks) -> str:
        """랜드마크로 손 제스처를 분류한다.

        반환: 'open' | 'fist' | 'point' | 'pinch' | 'none'

        규칙(간단·교육용, 정규화 좌표 가정. 화면 위 = y 작음):
          - 손가락이 '펴짐' = 끝(TIP)이 첫 마디(MCP)보다 위(y가 더 작음).
          - pinch  : 엄지끝과 검지끝이 매우 가깝다(우선 판정).
          - point  : 검지만 펴고 중지/약지/새끼는 접힘.
          - open   : 검지·중지·약지·새끼 모두 펴짐.
          - fist   : 네 손가락 모두 접힘.
          - none   : 그 외/입력 없음.
        """
        # 입력 방어: 21점이 아니면 분류 불가
        if not landmarks or len(landmarks) < 21:
            return "none"

        def y(i):  # i번 점의 y좌표
            return landmarks[i][1]

        def dist(a, b):  # 두 점 사이 유클리드 거리(2D)
            ax, ay = landmarks[a][0], landmarks[a][1]
            bx, by = landmarks[b][0], landmarks[b][1]
            return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5

        # 각 손가락이 펴졌는지: 끝이 MCP보다 위(y 작음)면 펴짐
        index_open = y(HandTracker.INDEX_TIP) < y(HandTracker.INDEX_MCP)
        middle_open = y(HandTracker.MIDDLE_TIP) < y(HandTracker.MIDDLE_MCP)
        # 약지/새끼는 MCP 인덱스가 팔레트에 없어 중지 MCP 기준선으로 근사
        ring_open = y(HandTracker.RING_TIP) < y(HandTracker.MIDDLE_MCP)
        pinky_open = y(HandTracker.PINKY_TIP) < y(HandTracker.MIDDLE_MCP)

        # 손 크기 기준 거리(손목→중지MCP)로 pinch 임계를 정규화
        hand_span = dist(HandTracker.WRIST, HandTracker.MIDDLE_MCP) or 1e-6
        pinch_gap = dist(HandTracker.THUMB_TIP, HandTracker.INDEX_TIP)

        # 1) pinch: 엄지끝-검지끝이 손 크기 대비 충분히 가까움
        if pinch_gap < hand_span * 0.30:
            return "pinch"

        # 2) point: 검지만 펴짐
        if index_open and not (middle_open or ring_open or pinky_open):
            return "point"

        # 3) open: 네 손가락 모두 펴짐
        if index_open and middle_open and ring_open and pinky_open:
            return "open"

        # 4) fist: 네 손가락 모두 접힘
        if not (index_open or middle_open or ring_open or pinky_open):
            return "fist"

        # 5) 그 외 애매한 상태
        return "none"


# ──────────────────────────────────────────────────────────────────────────
# 내부 유틸
# ──────────────────────────────────────────────────────────────────────────
def _is_ndarray(x) -> bool:
    """x가 numpy ndarray인지 안전하게 확인(numpy 미설치 시 False)."""
    return _HAS_NUMPY and isinstance(x, np.ndarray)


# ──────────────────────────────────────────────────────────────────────────
# 자가 데모 (mock) — 하드웨어/모델 없이 색검출 + 제스처 분류 출력
# ──────────────────────────────────────────────────────────────────────────



# ==============================================================================
# ── common/dobot_ctl.py
# ==============================================================================

"""common/dobot_ctl.py — 두봇 라이트(Dobot Magician Lite) 제어 래퍼 (ADR-0002)

목적
----
교육용 커리큘럼에서 학생/강사가 한 줄로 로봇팔을 안전하게 제어하도록 돕는
얇은 래퍼다. 내부적으로 순수 파이썬 라이브러리 ``pydobot``(시리얼 직접 통신,
DLL 불필요)을 사용한다. 자세한 근거는 ``docs/두봇_라이트_API.md`` 7절(pydobot 경로) 참고.

핵심 안전 원칙 (SFR-002)
------------------------
- 모든 이동은 ``common.safety.clamp_move`` 로 작업영역(WORKSPACE) 안으로 클램프한다.
  안전범위를 벗어난 좌표가 들어오면 거부하지 않고 가까운 안전점으로 보정 후 경고를 띄운다.
- ``with`` 블록 종료 시 흡착/그리퍼를 끄는 '안전정지' 후 연결을 해제한다.

하드웨어/키 없이 동작 (ADR-0004)
--------------------------------
- ``pydobot`` import 실패(미설치) 또는 ``config.is_mock()`` 이 True 이면
  실제 하드웨어 대신 :class:`MockDobot` 으로 자동 폴백한다.
- 따라서 이 파일은 로봇·시리얼 포트 없이도 import 되고 자가 데모가 실행된다.

사용법
------
>>> from common.dobot_ctl import get_robot
>>> with get_robot() as bot:          # mock 자동판정(키/하드웨어 없으면 mock)
...     bot.home()                    # 원점 복귀
...     bot.move_to(220, 0, 50)       # 직선 이동(절대좌표, mm)
...     bot.suck(True)                # 흡착 ON
...     print(bot.get_pose())         # {'x':..,'y':..,'z':..,'r':..,'j1':..,..}

명시적으로 mock/실하드웨어를 강제하려면 ``get_robot(mock=True)`` / ``get_robot(mock=False)``.

자가 데모
---------
``python common/dobot_ctl.py`` 실행 시 mock 으로
home → move_to → suck → get_pose 시퀀스를 수행하고 명령 로그를 출력한다.
"""


# 표준 라이브러리: 경고 출력 / 재시도·정착 지연용
import time
import warnings

# ----------------------------------------------------------------------------
# 1) 의존 모듈 import — 하드웨어/키 없이도 import 되도록 모두 try/except 로 감싼다.
# ----------------------------------------------------------------------------

# (a) pydobot: 실제 로봇 제어용 순수 파이썬 라이브러리. 미설치면 None 으로 두고 mock 폴백.
try:
    import pydobot  # type: ignore
    _PYDOBOT_AVAILABLE = True            # pydobot 사용 가능 플래그
except Exception:                        # ImportError 외에 시리얼 의존성 문제 등도 포괄
    pydobot = None                       # 미설치 시 None
    _PYDOBOT_AVAILABLE = False

# ----------------------------------------------------------------------------
# 1-1) pydobot.Dobot._read_message 'patient-read' 몽키패치 (검증된 1차 방어선)
# ----------------------------------------------------------------------------
# 근본원인: pydobot 기본 ``Dobot._read_message`` 는 시리얼 응답을 0.1초만 단발로
# 기다린 뒤 None 을 반환한다. 빠른 연속 이동에서 응답이 그 안에 다 안 오면 None 이
# 돌아오고, 이를 사용하는 pydobot 내부가
# ``AttributeError: 'NoneType' object has no attribute 'params'`` 로 크래시한다
# (실측: 게임 중 약 1/3 이동 실패, 아래 _retry/_reconnect 재시도로도 가끔 복구 실패).
#
# 해결: 응답을 충분히(최대 2초) 기다리며 들어오는 바이트를 누적하고, 데이터가
# 들어온 뒤 더 이상 오지 않으면 메시지 완성으로 간주해 한 번에 파싱하는
# 'patient-read' 버전으로 모듈 임포트 시점에 한 번 교체한다.
# (실측: patient_read 적용 후 16/16 이동 성공·0 실패·재시도경고 0 으로 완전 해결)
#
# - 이 패치는 _retry/_reconnect/_settle(아래 RobotController) 의 이중 안전망보다
#   앞단에서 동작하는 **1차 방어선**이다. 기존 로직은 그대로 유지한다.
# - 실 pydobot.Dobot 에만 적용되며 MockDobot/ mock 경로에는 전혀 영향이 없다.
# - import(또는 Message 임포트) 실패 시 조용히 건너뛴다(무해). pydobot 미설치면 패치 안 함.
if _PYDOBOT_AVAILABLE:
    try:
        from pydobot.message import Message as _PydobotMessage  # type: ignore

        def _patient_read_message(self):
            """pydobot.Dobot._read_message 의 인내심 있는 대체 구현.

            원본은 0.1초만 기다리고 None 을 반환하지만, 이 버전은 최대 2초까지
            바이트를 누적하며 기다리고, 데이터가 들어온 뒤 잠시 더 안 오면 메시지가
            완성된 것으로 보고 한 번에 파싱한다(원본 시그니처 self 유지)."""
            buf = bytearray()
            deadline = time.time() + 2.0
            idle = 0
            while time.time() < deadline:
                b = self.ser.read_all()
                if b:
                    buf.extend(b)
                    idle = 0
                elif buf:
                    idle += 1
                    if idle >= 2:   # 데이터가 들어온 뒤 더 안 오면 메시지 완성으로 간주
                        break
                time.sleep(0.04)
            if buf:
                try:
                    return _PydobotMessage(bytes(buf))
                except Exception:
                    return None
            return None

        # 실제 교체(monkeypatch). 교체 실패해도 무해하도록 전체를 try/except 로 감쌌다.
        pydobot.dobot.Dobot._read_message = _patient_read_message
    except Exception:
        # pydobot 구조 변경/임포트 실패 등 — 패치를 건너뛰어도 기존 안전망으로 동작.
        pass

# (b) 시리얼 포트 자동탐지(선택). 없어도 동작해야 하므로 try/except.
try:
    from serial.tools import list_ports  # type: ignore
except Exception:
    list_ports = None                    # 포트 탐지 불가 시 None

# (c) config: 작업영역/mock 판정. 아직 없을 수 있으므로 폴백 기본값을 둔다.
try:
    pass
except Exception:
    config = None  # type: ignore[assignment]  # config 미존재 시 아래 _is_mock 가 보수적으로 mock 선택

# (d) safety: 안전필터(클램프/검사). 없으면 항등(클램프 안 함) 폴백을 제공한다.
try:
    pass
except Exception:
    safety = None  # type: ignore[assignment]

# config 가 없을 때 사용할 보수적 기본 작업영역(강사매뉴얼/CONTRACTS 와 동일 값).
_DEFAULT_WORKSPACE = {
    "x": (180, 320),    # 전후(mm)
    "y": (-150, 150),   # 좌우(mm)
    "z": (-60, 150),    # 상하(mm)
    "r": (-150, 150),   # 엔드이펙터 회전(deg)
}


def _is_mock(mock: bool | None) -> bool:
    """이 컨트롤러가 mock 으로 동작해야 하는지 최종 판정한다.

    우선순위:
      1) 인자 ``mock`` 이 명시되면(True/False) 그대로 따른다.
      2) pydobot 이 없으면 무조건 mock(실하드웨어 불가).
      3) config.robot_is_mock() 결과를 따른다 — **로봇은 pydobot 유무로만 판정하며
         LLM 키 유무와 무관하다**(ADR/설계: LLM 없이도 로봇은 실제 동작해야 함).
      4) config 도 없으면 안전하게 mock 으로 본다.
    """
    if mock is not None:                  # 1) 명시적 지정이 최우선
        return bool(mock)
    if not _PYDOBOT_AVAILABLE:            # 2) 라이브러리가 없으면 실하드웨어 불가
        return True
    if config is not None:
        # 로봇 전용 판정(robot_is_mock)을 우선 사용. 구버전 호환으로 is_mock 폴백.
        decider = getattr(config, "robot_is_mock", None) or getattr(config, "is_mock", None)
        if decider is not None:
            try:
                return bool(decider())     # 3) 로봇 mock 자동판정(키와 무관)
            except Exception:
                return True                # 판정 중 오류 시 안전하게 mock
    return True                            # 4) config 부재 → mock


def _get_workspace() -> dict:
    """현재 작업영역(안전 한계)을 반환한다. config 가 있으면 그 값을, 없으면 기본값."""
    if config is not None and hasattr(config, "WORKSPACE"):
        return config.WORKSPACE
    return _DEFAULT_WORKSPACE


def _clamp(x, y, z, r):
    """좌표를 작업영역 안으로 클램프한다.

    common.safety.clamp_move 가 있으면 그것을 사용하고(SFR-002 단일 출처),
    없으면 내장 폴백으로 WORKSPACE 범위에 맞춰 직접 클램프한다.
    반환: (x, y, z, r, clamped) — clamped 는 보정이 일어났는지 여부(bool).
    """
    # 1순위: 안전 모듈의 공식 클램프 사용
    if safety is not None and hasattr(safety, "clamp_move"):
        cx, cy, cz, cr = safety.clamp_move(x, y, z, r)
        # 입력과 결과가 다르면 보정이 일어난 것
        clamped = (cx, cy, cz, cr) != (x, y, z, r)
        return cx, cy, cz, cr, clamped

    # 폴백: WORKSPACE 범위로 직접 클램프
    ws = _get_workspace()

    def _cl(v, lo_hi):
        lo, hi = lo_hi
        return min(max(v, lo), hi)        # [lo, hi] 구간으로 제한

    cx = _cl(x, ws["x"])
    cy = _cl(y, ws["y"])
    cz = _cl(z, ws["z"])
    cr = _cl(r, ws["r"])
    clamped = (cx, cy, cz, cr) != (x, y, z, r)
    return cx, cy, cz, cr, clamped


# ----------------------------------------------------------------------------
# 2) MockDobot — 하드웨어 없는 가짜 로봇. RobotController 가 감싸는 내부 드라이버이며,
#    pydobot.Dobot 과 동일한 호출 인터페이스(pose/move_to/suck/grip/...)를 흉내 낸다.
#    모든 명령을 self.log 리스트에 기록한다(테스트/검수/교육 시연용).
# ----------------------------------------------------------------------------
class MockDobot:
    """가짜 두봇 — 실제 하드웨어 없이 명령을 기록만 한다.

    pydobot.Dobot 과 같은 메서드(pose/move_to/suck/grip/speed/wait/close)를 제공하므로
    RobotController 입장에서 실드라이버와 똑같이 다룰 수 있다.
    모든 호출은 ``self.log`` 에 ``(명령이름, 인자...)`` 형태로 적재된다.
    """

    def __init__(self, port=None, verbose=False):
        # 내부 상태: 현재 포즈(좌표/관절). 홈 기준의 합리적 초기값.
        self.x, self.y, self.z, self.r = 200.0, 0.0, 0.0, 0.0
        self.j1 = self.j2 = self.j3 = self.j4 = 0.0
        self.port = port                  # 받은 포트(가짜이므로 사용 안 함)
        self.verbose = verbose            # 로그를 화면에도 출력할지
        self.log: list[tuple] = []        # 명령 기록 리스트
        self._suction = False             # 흡착 상태
        self._grip = False                # 그리퍼 상태
        self._record("__init__", port)    # 생성도 기록

    def _record(self, name, *args):
        """명령 한 건을 로그에 적재(필요 시 화면 출력)."""
        entry = (name, *args)
        self.log.append(entry)
        if self.verbose:
            print(f"[MockDobot] {entry}")

    # --- pydobot.Dobot 호환 메서드들 ---------------------------------------
    def home(self):
        """원점 복귀(가짜). 포즈를 홈 기준값으로 되돌린다."""
        self.x, self.y, self.z, self.r = 200.0, 0.0, 0.0, 0.0
        self.j1 = self.j2 = self.j3 = self.j4 = 0.0
        self._record("home")

    def move_to(self, x, y, z, r=0.0, wait=False):
        """직선 이동(가짜). 내부 포즈를 목표값으로 갱신하고 기록."""
        self.x, self.y, self.z, self.r = float(x), float(y), float(z), float(r)
        self._record("move_to", x, y, z, r, wait)

    def suck(self, enable):
        """흡착 ON/OFF(가짜)."""
        self._suction = bool(enable)
        self._record("suck", bool(enable))

    def grip(self, enable):
        """그리퍼 잡기/놓기(가짜)."""
        self._grip = bool(enable)
        self._record("grip", bool(enable))

    def pump_off(self):
        """엔드이펙터 공압 펌프 완전 정지(가짜) — isCtrlEnabled=0 상당.

        실 pydobot 의 grip/suck(False) 는 펌프를 켠 채 그리퍼만 여는 것과 달리,
        이건 펌프 자체를 끈 상태를 표현한다. 흡착/그리퍼 상태도 해제로 본다."""
        self._suction = False
        self._grip = False
        self._pump = False
        self._record("pump_off")

    def speed(self, velocity=100.0, acceleration=100.0):
        """속도/가속 설정(가짜)."""
        self._record("speed", velocity, acceleration)

    def wait(self, ms):
        """대기(가짜) — 실제로 멈추지 않고 기록만 한다."""
        self._record("wait", ms)

    def pose(self):
        """현재 포즈를 pydobot 과 같은 8-튜플로 반환."""
        self._record("pose")
        return (self.x, self.y, self.z, self.r,
                self.j1, self.j2, self.j3, self.j4)

    def close(self):
        """연결 해제(가짜)."""
        self._record("close")


# ----------------------------------------------------------------------------
# 3) RobotController — CONTRACTS 의 공개 인터페이스. 실드라이버/Mock 을 동일하게 감싼다.
# ----------------------------------------------------------------------------
class RobotController:
    """두봇 라이트 제어기 (pydobot 래퍼, ADR-0002).

    mock 여부에 따라 내부 드라이버로 :class:`MockDobot` 또는 ``pydobot.Dobot`` 을 쓴다.
    공개 메서드: connect/home/move_to/suck/grip/get_pose/disconnect 와 컨텍스트 매니저.

    실하드웨어 안정화 (통신 글리치 대응 + 재연결 복구)
    --------------------------------------------------
    실제 두봇(pydobot)으로 빠른 연속 이동 명령을 보내면, 간헐적으로 응답이 None 으로
    와서 pydobot 내부에서 ``AttributeError: 'NoneType' object has no attribute 'params'``
    류의 통신 오류로 크래시한다(실측). 같은 명령을 즉시 재시도해도 시리얼 버퍼/연결이
    어긋난(desync) 상태라 복구되지 않는 경우가 있다. 이를 막기 위해
    **실하드웨어(self.mock=False)에서만**:
      - 모든 device.* 호출을 :meth:`_retry` 재시도 래퍼로 감싼다
        (실패 시 ``_RETRY_DELAY`` 만큼 sleep 후 ``_MAX_RETRIES`` 회까지 재시도).
      - 재시도 직전마다 :meth:`_flush_input` 로 시리얼 입력 버퍼의 잔류 바이트를
        비워 응답 어긋남(desync)을 줄인다.
      - in-place 재시도(N회)로도 실패하면 :meth:`_reconnect` 로 **연결을 재설정**한 뒤
        실패했던 동작을 한 번 더 시도한다(reconnect-on-failure). pydobot.Dobot 의
        재연결은 큐 클리어+포즈읽기만 하므로 팔이 움직이지 않아 안전하다.
      - 큐 이동(move_to/home) 직후 ``_SETTLE_DELAY`` 만큼의 작은 정착 지연을 둬
        연속 명령을 안정화한다(교육용 반응성 유지를 위해 과도한 지연은 금지).
    mock(MockDobot) 경로에는 지연/재시도/재연결을 적용하지 않는다(즉시 동작·결정성 유지).
    """

    # --- 실하드웨어 안정화 상수(필요 시 인자/속성으로 조정 가능) -------------
    _MAX_RETRIES = 3        # device.* 호출 실패 시 최대 (in-place) 재시도 횟수
    _RETRY_DELAY = 0.4      # 재시도 전 대기(초)
    _SETTLE_DELAY = 0.3     # 큐 이동 후 정착 지연(초) — 연속 명령 안정화

    def __init__(self, port=None, mock=None,
                 settle_delay=None, max_retries=None, retry_delay=None):
        # 사용할 포트(None 이면 connect 시 자동탐지 시도). config.DOBOT_PORT 가 있으면 보조로 사용.
        self.port = port
        if self.port is None and config is not None:
            self.port = getattr(config, "DOBOT_PORT", None)
        # 최종 mock 판정(인자 → pydobot 유무 → config 순)
        self.mock = _is_mock(mock)
        self.device = None                # 내부 드라이버(연결 후 채워짐)
        self.connected = False            # 연결 상태 플래그
        # 안정화 파라미터: 인자로 받으면 인스턴스 속성으로 덮어쓰고, 아니면 클래스 상수 사용.
        if settle_delay is not None:
            self._settle_delay = float(settle_delay)
        else:
            self._settle_delay = self._SETTLE_DELAY
        if max_retries is not None:
            self._max_retries = int(max_retries)
        else:
            self._max_retries = self._MAX_RETRIES
        if retry_delay is not None:
            self._retry_delay = float(retry_delay)
        else:
            self._retry_delay = self._RETRY_DELAY

    # --- 연결 / 해제 -------------------------------------------------------
    def connect(self) -> bool:
        """로봇에 연결한다. mock 이면 MockDobot 생성, 아니면 pydobot.Dobot 연결.

        반환: 연결 성공 여부(bool). 실하드웨어 연결 실패 시 자동으로 mock 으로 폴백한다.
        """
        if self.connected:                # 중복 연결 방지
            return True

        if self.mock:                     # mock 모드: 가짜 로봇
            self.device = MockDobot(port=self.port)
            self.connected = True
            return True

        # 실하드웨어 모드: 포트 자동탐지(미지정 시)
        port = self._resolve_port()
        try:
            # pydobot 연결 (verbose=False: 교육용으로 콘솔 소음 최소화)
            self.device = self._open_device(port)
            self.port = port                      # 재연결 복구에서 재사용하도록 확정 포트 보관
            self.connected = True
            return True
        except Exception as e:            # 연결 실패 → 친절한 경고 후 mock 폴백
            warnings.warn(
                f"로봇 연결에 실패했습니다({e}). 모의(mock) 모드로 전환합니다. "
                f"하드웨어/포트를 확인하세요."
            )
            self.mock = True
            self.device = MockDobot(port=port)
            self.connected = True
            return True

    def _resolve_port(self):
        """사용할 시리얼 포트를 결정한다.

        우선순위: self.port(명시/config.DOBOT_PORT) > 자동탐지.
        자동탐지는 **블루투스 포트를 제외하고 USB 시리얼(두봇)을 우선** 선택한다.
        (블루투스 COM 은 열면 'Access denied' 가 나므로 첫 포트를 무작정 쓰면 안 됨.)
        """
        port = self.port
        if port is None and list_ports is not None:
            ports = list(list_ports.comports())   # 연결된 시리얼 포트 목록
            if ports:
                def _score(p):
                    desc = " ".join(str(x or "") for x in
                                    (p.description, p.device,
                                     getattr(p, "manufacturer", ""),
                                     getattr(p, "hwid", ""))).lower()
                    if "bluetooth" in desc or "블루투스" in desc:
                        return -1                 # 블루투스 제외
                    s = 0
                    if "usb" in desc:
                        s += 2                    # USB 시리얼 우선(두봇)
                    if any(k in desc for k in ("serial", "ch340", "cp210", "ftdi", "silicon")):
                        s += 1
                    return s
                cand = [p for p in ports if _score(p) >= 0]   # 블루투스 빼고
                if cand:
                    cand.sort(key=_score, reverse=True)
                    port = cand[0].device
                else:
                    port = ports[0].device        # 전부 블루투스뿐이면 폴백
        return port

    def _open_device(self, port):
        """pydobot.Dobot 인스턴스를 생성해 반환한다(연결 핵심 로직 단일 출처).

        pydobot.Dobot.__init__ 은 큐 시작/클리어 + 파라미터 설정 + 포즈 읽기만 하고
        실제 모션(이동)은 수행하지 않으므로, 이 호출만으로 팔이 움직이지 않는다.
        => 재연결 복구(:meth:`_reconnect`)에서 재사용해도 안전하다.
        """
        return pydobot.Dobot(port=port, verbose=False)

    def disconnect(self) -> None:
        """연결을 해제한다. 이미 끊겼으면 아무것도 하지 않는다."""
        if self.device is not None:
            try:
                self.device.close()       # pydobot/Mock 공통 close()
            except Exception as e:
                warnings.warn(f"연결 해제 중 경고: {e}")
        self.device = None
        self.connected = False

    def _ensure(self):
        """명령 전 연결을 보장한다(미연결이면 자동 connect)."""
        if not self.connected:
            self.connect()

    # --- 실하드웨어 안정화: 입력버퍼 플러시 / 재연결 복구 / 재시도 래퍼 -----
    def _flush_input(self):
        """시리얼 입력 버퍼의 잔류 바이트를 비운다(응답 어긋남=desync 예방).

        실하드웨어에서 연속 명령 중 응답이 어긋나면(이전 응답의 잔류 바이트가 다음
        명령의 응답으로 잘못 해석됨) None 응답/AttributeError 의 원인이 된다.
        pydobot.Dobot 은 내부에 ``ser``(pyserial.Serial)를 직접 들고 있으므로
        ``device.ser.reset_input_buffer()`` 로 잔류 바이트를 비운다.
        ser 가 없거나(또는 Mock) 호출이 실패해도 조용히 무시한다(베스트-에포트).
        """
        if self.mock:                     # mock: 시리얼 없음 → 아무것도 안 함
            return
        try:
            ser = getattr(self.device, "ser", None)
            if ser is not None and hasattr(ser, "reset_input_buffer"):
                ser.reset_input_buffer()
        except Exception:
            pass                          # 플러시는 베스트-에포트 — 실패해도 무시

    def _reconnect(self):
        """연결을 안전하게 재설정한다(reconnect-on-failure 의 핵심).

        현재 device 를 close 한 뒤 같은 포트(self.port)로 pydobot.Dobot 을 다시 연다.
        pydobot.Dobot.__init__ 은 큐 클리어 + 포즈읽기만 하고 모션은 없으므로 팔이
        움직이지 않아 재연결이 안전하다(실하드웨어 전용 — mock 에서는 호출되지 않음).
        실패하면 예외를 그대로 전파한다(상위 _retry 가 잡아 최종 메시지로 변환).
        """
        # 1) 기존 연결을 안전하게 정리(close 실패는 무시 — 어차피 새로 열 것).
        old = self.device
        if old is not None:
            try:
                old.close()
            except Exception:
                pass
        self.device = None
        self.connected = False
        # 2) 같은 포트로 재연결(자동탐지가 필요하면 _resolve_port 가 처리).
        port = self._resolve_port()
        self.device = self._open_device(port)
        self.port = port
        self.connected = True

    def _retry(self, action_name, func, *args, **kwargs):
        """device.* 호출을 통신 글리치에 강건하게 감싸는 재시도 + 재연결 래퍼.

        실하드웨어(self.mock=False)에서만 동작하며 다음 순서로 복구를 시도한다:
          1) 호출이 통신 오류로 실패하면 입력버퍼를 플러시하고 ``self._retry_delay``
             만큼 sleep 후 ``self._max_retries`` 회까지 in-place 재시도한다.
          2) in-place 재시도로도 실패하면 :meth:`_reconnect` 로 연결을 재설정한 뒤
             실패했던 동작(func)을 한 번 더 호출한다(reconnect-on-failure).
          3) 재연결 후 호출도 실패하면 어느 동작/포트에서 실패했는지 담은 친절한
             한국어 RuntimeError 로 raise 한다(원인 체이닝).
        대표 증상: 응답이 None 으로 와서 pydobot 내부가
        ``AttributeError: 'NoneType' object has no attribute 'params'`` 로 크래시.
        같은 명령을 즉시 재시도해도 시리얼 버퍼/연결이 어긋나면 복구가 안 되므로
        (1)의 플러시와 (2)의 재연결이 필요하다.

        mock 경로에서는 지연/재시도/재연결 없이 즉시 1회만 호출한다(반응성·결정성 유지).

        action_name : 실패 메시지에 표시할 동작 이름(예: "이동(move_to)").
        func        : 실제로 호출할 device 메서드(또는 임의의 호출 가능 객체).

        주의: func 는 보통 ``self.device.<메서드>`` 형태의 바운드 메서드로 전달된다.
        재연결 시 device 객체가 새로 만들어지므로, 재연결 후 호출은 새 device 의
        같은 이름 메서드를 다시 바인딩해 호출한다(메서드 이름으로 재바인딩).
        """
        # mock 경로: 안정화 불필요 → 그대로 1회 호출(예외도 그대로 전파).
        if self.mock:
            return func(*args, **kwargs)

        last_exc = None
        # 총 시도 횟수 = 최초 1회 + 재시도. (_max_retries 가 '최대 재시도 횟수')
        attempts = max(1, self._max_retries)
        for attempt in range(1, attempts + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:  # AttributeError(None 응답)·serial 예외 등 통신오류 포괄
                last_exc = e
                if attempt < attempts:
                    # 마지막 시도가 아니면: 입력버퍼 플러시 + 잠시 쉬고 재시도.
                    self._flush_input()   # 잔류 바이트 비우기(desync 회복)
                    warnings.warn(
                        f"로봇 통신 오류로 '{action_name}' 재시도 "
                        f"{attempt}/{attempts - 1} (원인: {e})"
                    )
                    time.sleep(self._retry_delay)

        # --- in-place 재시도 전부 실패 → 재연결 복구(reconnect-on-failure) ---
        warnings.warn(
            f"로봇 '{action_name}' 이 {attempts}회 재시도로도 실패하여 "
            f"연결을 재설정합니다(포트: {self.port})."
        )
        try:
            self._reconnect()                              # 연결 재설정(팔 안 움직임)
            self._flush_input()                            # 재연결 직후 입력버퍼 정리
            time.sleep(self._retry_delay)                  # 재연결 안정화 대기
            rebound = self._rebind(func)                   # 새 device 에 메서드 재바인딩
            return rebound(*args, **kwargs)                # 실패했던 동작 재실행
        except Exception as e:
            last_exc = e

        # 재연결 후에도 실패 → 친절한 한국어 메시지로 raise(원인 체이닝).
        raise RuntimeError(
            f"로봇 '{action_name}' 동작이 통신 오류로 {attempts}회 재시도와 "
            f"재연결 복구 후에도 실패했습니다(포트: {self.port}). "
            f"케이블/포트 연결과 펌웨어 상태를 확인하세요. "
            f"(마지막 오류: {last_exc})"
        ) from last_exc

    def _rebind(self, func):
        """재연결 후, func 가 (재연결 전) device 의 바운드 메서드였다면 새 device 의
        같은 이름 메서드로 다시 바인딩해 돌려준다.

        device 메서드가 아니면(임의 호출 가능 객체) func 를 그대로 반환한다.
        """
        # 바운드 메서드의 소유 객체(__self__)가 (구) device 였으면 새 device 로 교체.
        owner = getattr(func, "__self__", None)
        name = getattr(func, "__name__", None)
        if owner is not None and name and self.device is not None:
            rebound = getattr(self.device, name, None)
            if callable(rebound):
                return rebound
        return func

    def _settle(self):
        """큐 이동(move_to/home) 직후의 작은 정착 지연.

        실하드웨어(self.mock=False)에서만 ``self._settle_delay`` 초 만큼 쉬어
        빠른 연속 명령에서 응답이 None 으로 오는 통신 글리치를 줄인다.
        mock 경로에서는 아무 일도 하지 않는다(즉시).
        """
        if self.mock:
            return
        if self._settle_delay and self._settle_delay > 0:
            time.sleep(self._settle_delay)

    # --- 동작 명령 ---------------------------------------------------------
    def home(self) -> None:
        """원점 복귀. 전원 직후 좌표 신뢰성 확보를 위해 권장(API 문서 8절)."""
        self._ensure()
        # MockDobot 은 home() 을 갖지만, 실 pydobot.Dobot 에는 home() 이 없다.
        if hasattr(self.device, "home"):
            self._retry("원점 복귀(home)", self.device.home)   # MockDobot 경로
        else:
            # pydobot 경로: 별도 홈 명령이 없으므로 작업영역 중앙 안전점으로 이동해 대체한다.
            ws = _get_workspace()
            hx = (ws["x"][0] + ws["x"][1]) / 2.0   # x 중앙
            hy = 0.0                                # y 중앙(좌우 0)
            hz = ws["z"][1]                         # z 최상단(가장 안전)
            self._retry("원점 복귀(home)",
                        self.device.move_to, hx, hy, hz, 0.0, wait=True)
        # 큐 이동 후 정착 지연(실하드웨어에서만) — 연속 명령 안정화.
        self._settle()

    def move_to(self, x, y, z, r=0.0, wait=True) -> dict:
        """직선 이동(절대좌표, mm/deg). 안전범위 밖이면 클램프하고 경고한다.

        반환: 실행 결과 dict
          {'requested': {x,y,z,r}, 'actual': {x,y,z,r}, 'clamped': bool}
        """
        self._ensure()
        # 1) 안전 클램프: 작업영역 밖이면 가까운 안전점으로 보정
        cx, cy, cz, cr, clamped = _clamp(x, y, z, r)
        if clamped:
            # 거부 대신 보정 + 경고(교육용: 왜 못 가는지 학생에게 알려줌)
            warnings.warn(
                f"요청 좌표({x}, {y}, {z}, r={r})가 안전 작업영역을 벗어나 "
                f"({cx}, {cy}, {cz}, r={cr})로 클램프했습니다."
            )
        # 2) 실제 이동(보정된 안전 좌표로) — 통신 글리치 대비 재시도 래퍼로 감쌈.
        self._retry("이동(move_to)",
                    self.device.move_to, cx, cy, cz, cr, wait=wait)
        # 큐 이동 후 정착 지연(실하드웨어에서만) — 연속 명령 안정화.
        self._settle()
        # 3) 결과 보고
        return {
            "requested": {"x": x, "y": y, "z": z, "r": r},
            "actual": {"x": cx, "y": cy, "z": cz, "r": cr},
            "clamped": clamped,
        }

    def suck(self, on: bool) -> None:
        """흡착컵 ON/OFF."""
        self._ensure()
        self._retry("흡착(suck)", self.device.suck, bool(on))

    def grip(self, on: bool) -> None:
        """그리퍼 잡기(True)/놓기(False)."""
        self._ensure()
        self._retry("그리퍼(grip)", self.device.grip, bool(on))

    def grasp(self, on: bool) -> None:
        """엔드이펙터 추상화: 부착한 도구에 맞게 '집기/놓기'를 수행한다.

        config.EFFECTOR 가 "gripper"(기본/실측)면 그리퍼(grip)를, "suction"이면
        흡착컵(suck)을 사용한다. 차시 코드는 이 메서드만 호출하면 되며, 실제 교구가
        그리퍼든 흡착이든 같은 픽앤플레이스 로직이 그대로 동작한다.

        on : True = 잡기(집기), False = 놓기.
        """
        self._ensure()
        # config 가 있으면 EFFECTOR 설정을 따르고, 없으면 보수적으로 그리퍼로 본다(실측 기본).
        effector = getattr(config, "EFFECTOR", "gripper") if config is not None else "gripper"
        if str(effector).lower() == "suction":
            self.suck(bool(on))           # 흡착컵: ON=집기, OFF=놓기
        else:
            self.grip(bool(on))           # 그리퍼(기본): True=잡기, False=놓기

    def get_pose(self) -> dict:
        """현재 포즈를 dict 로 반환: {x,y,z,r,j1,j2,j3,j4}."""
        self._ensure()
        x, y, z, r, j1, j2, j3, j4 = self._retry("포즈 조회(get_pose)", self.device.pose)
        return {"x": x, "y": y, "z": z, "r": r,
                "j1": j1, "j2": j2, "j3": j3, "j4": j4}

    def pump_off(self) -> None:
        """엔드이펙터 공압 펌프를 완전히 끈다(isCtrlEnabled=0).

        suck(False)/grip(False) 는 진공/그립만 해제할 뿐 펌프는 계속 돈다. '펌프 꺼'
        같은 명령은 이 메서드로 펌프 회로 자체를 끈다(공개 API). 내부 구현 위임.
        """
        self._effector_pump_off()

    # --- 엔드이펙터 펌프 완전 정지 -----------------------------------------
    def _effector_pump_off(self) -> None:
        """엔드이펙터 공압 펌프를 **완전히 끈다**(isCtrlEnabled=0).

        실측 문제: pydobot 의 grip(False)/suck(False) 는 명령 첫 바이트를 항상
        isCtrlEnabled=1 로 보내, '그리퍼만 열' 뿐 **공압 펌프는 계속 돈다**(소음·발열·잔압).
        종료(창 닫기/with 종료) 시엔 펌프 자체를 꺼야 하므로, SetEndEffectorGripper /
        SuctionCup 명령을 **isCtrlEnabled=0(첫 바이트 0x00)** 으로 직접 만들어 보낸다.

        - 실 pydobot(device._send_command 보유): 원시 Message 두 개(그리퍼/흡착) 전송.
        - MockDobot(pump_off 보유): 기록만.
        종료 경로이므로 실패해도 예외를 던지지 않고 경고만 남긴다.
        """
        dev = self.device
        if dev is None:
            return
        # 실 pydobot 경로: isCtrlEnabled=0 원시 명령
        if hasattr(dev, "_send_command"):
            try:
                from pydobot.message import Message
                from pydobot.enums.CommunicationProtocolIDs import CommunicationProtocolIDs as _CID  # type: ignore[import-untyped]
                from pydobot.enums.ControlValues import ControlValues as _CV  # type: ignore[import-untyped]
            except Exception as e:                      # pydobot 내부 경로가 다르면 조용히 포기
                warnings.warn(f"펌프 OFF 준비 실패(원시 명령 불가): {e}")
                return
            for _name, _id in (("그리퍼", _CID.SET_GET_END_EFFECTOR_GRIPPER),
                               ("흡착", _CID.SET_GET_END_EFFECTOR_SUCTION_CUP)):
                try:
                    msg = Message()
                    msg.id = _id
                    msg.ctrl = _CV.THREE
                    msg.params = bytearray([0x00, 0x00])  # [isCtrlEnabled=0, state=0] → 펌프 OFF
                    dev._send_command(msg)                # 종료 경로: 재시도/재연결 없이 1회 전송
                except Exception as e:
                    warnings.warn(f"펌프 OFF({_name}) 중 경고: {e}")
            return
        # MockDobot 등: 기록만(테스트 가시성)
        if hasattr(dev, "pump_off"):
            try:
                dev.pump_off()
            except Exception:
                pass

    # --- 안전정지 ----------------------------------------------------------
    def _safe_stop(self) -> None:
        """안전정지: 흡착/그리퍼를 꺼 물체 낙하·끼임을 막고, **공압 펌프까지 완전히 끈다**.

        순서: (1) 흡착/그리퍼 '놓기'로 잡고 있던 물체를 먼저 안전하게 해제 →
              (2) 펌프 자체를 끈다(isCtrlEnabled=0). 놓기만 하면 펌프가 계속 돌기 때문.
        각 단계를 독립적으로 try 로 감싸(한쪽 실패가 다른쪽을 막지 않게), 종료 경로이므로
        끝까지 실패해도 예외를 던지지 않고 경고만 남긴다."""
        if self.device is None:
            return
        # (1) 흡착 해제와 그리퍼 개방을 각각 독립적으로 시도(잡은 물체 먼저 놓기).
        try:
            self._retry("안전정지-흡착 해제(suck off)", self.device.suck, False)
        except Exception as e:
            warnings.warn(f"안전정지(흡착 해제) 중 경고: {e}")
        try:
            self._retry("안전정지-그리퍼 개방(grip off)", self.device.grip, False)
        except Exception as e:
            warnings.warn(f"안전정지(그리퍼 개방) 중 경고: {e}")
        # 그리퍼가 실제로 열릴 시간을 잠깐 준 뒤(실하드웨어만) 펌프를 끈다.
        if hasattr(self.device, "_send_command"):
            try:
                time.sleep(0.4)
            except Exception:
                pass
        # (2) 공압 펌프 자체를 완전히 끈다(isCtrlEnabled=0). ← 핵심: 놓기만으론 펌프가 계속 돈다.
        self._effector_pump_off()

    # --- 컨텍스트 매니저 ---------------------------------------------------
    def __enter__(self) -> "RobotController":
        """with 진입 시 자동 연결."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:  # type: ignore[exit-return]
        """with 종료 시 안전정지 후 연결 해제. 예외는 억제하지 않는다(False)."""
        self._safe_stop()                 # 1) 엔드이펙터 끄기
        self.disconnect()                 # 2) 연결 해제
        return False                      # 예외를 그대로 전파


# ----------------------------------------------------------------------------
# 4) 팩토리 함수 — 권장 진입점.
# ----------------------------------------------------------------------------
def get_robot(port=None, mock=None) -> RobotController:
    """RobotController 를 생성해 반환한다(연결은 connect()/with 에서).

    인자
      port: 시리얼 포트(None 이면 자동탐지/config 값)
      mock: True/False 강제, None 이면 자동판정(키·하드웨어 없으면 mock)
    """
    return RobotController(port=port, mock=mock)


# ----------------------------------------------------------------------------
# 5) 자가 데모 (mock) — 하드웨어 없이 실행 가능. home → move_to → suck → pose.
# ----------------------------------------------------------------------------



# ==============================================================================
# ── m2_gesture_hri/solution.py — 가위바위보 로직
# ==============================================================================

"""m2_gesture_hri/solution.py — [모범답안] 사람과 가위바위보 (인간-로봇 상호작용, HRI)

═══════════════════════════════════════════════════════════════════════════
[차시] M2 · 중등부(Block→Python) · "사람과 가위바위보 — HRI 제스처 인식 게임"
[학습목표]
  ① 손 랜드마크 → 가위·바위·보 '판단 로직'(순수함수 classify_rps)을 설계한다.
  ② 가위바위보 승패표(게임 규칙) 로직을 직접 만든다.
  ③ HRI 상호작용 흐름(사람 손 → 분류 → 로봇 수 → 내기 → 승패 → 반응)을 설계한다.
  ④ 위험 동작(이동·하강) 전에 안전검사(safety)를 먼저 부른다.
[수업철학] 110분 · 5E(참여-탐구-설명-정교화-평가) · 'Logic-First, Syntax-Later'
[산업연계 PBL] 협동로봇(코봇) 현장의 "사람 제스처를 읽고 반응하는" HRI를 교실에서 재현한다.
═══════════════════════════════════════════════════════════════════════════

┌──────────────────────────────────────────────────────────────────────────┐
│ 1) 손모양 → 가위바위보 분류 규칙 (펴진 손가락 수/상태로 판단)              │
├────────────┬───────────────┬───────────────────────────────────────────────┤
│ 손모양     │ 펴진 손가락   │ 분류 결과(classify_rps)                       │
├────────────┼───────────────┼───────────────────────────────────────────────┤
│ 가위 ✌     │ 검지+중지 2개 │ 'scissors'                                    │
│ 바위 ✊     │ 0개(주먹)     │ 'rock'                                        │
│ 보 ✋       │ 5개(편 손)    │ 'paper'                                       │
│ (그 외)    │ 애매/없음     │ 'none' (미인식 → 라운드 건너뜀)               │
└────────────┴───────────────┴───────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│ 2) 가위바위보 승패표 (학생 기준: 학생이 이기면 'win')                      │
├────────────────┬────────────┬────────────┬─────────────────────────────────┤
│ 학생(가로) ↓   │ rock 바위  │ paper 보   │ scissors 가위                   │
├────────────────┼────────────┼────────────┼─────────────────────────────────┤
│ rock 바위      │ draw 비김  │ lose 짐    │ win  이김                       │
│ paper 보       │ win  이김  │ draw 비김  │ lose 짐                         │
│ scissors 가위  │ lose 짐    │ win  이김  │ draw 비김                       │
└────────────────┴────────────┴────────────┴─────────────────────────────────┘

[블록 대응 주석] 중등부는 엔트리/스크래치 블록 사고를 파이썬으로 옮긴다.
  · "[손] 펴진 손가락 세기"            → _finger_states(landmarks)
  · "만약 <펴진손가락=2> 이라면 가위"  → if up == [.., True, True, ..]: 'scissors'
  · "[로봇] 자기 수 정하기(무작위)"    → decide_robot_move()
  · "[로봇] 자기 수 마커로 이동하기"   → robot_play(bot, move)
  · "만약 <학생 이김> 이라면 세리머니" → if result == 'win': celebrate(...)
  · "계속 반복하기 (N라운드)"          → for r in range(rounds):
  ※ 각 핵심 줄에 [블록] 주석으로 대응 블록을 병기했다.

[사용법]
    # 하드웨어/키 없이 mock으로 끝까지 실행
    set CURRICULUM_FORCE_MOCK=1   (Windows) / export CURRICULUM_FORCE_MOCK=1
    python m2_gesture_hri/solution.py

[준비물(물리 교구)] 두봇 라이트 1대(흡착/그리퍼 키트), USB 웹캠 1대(손 인식),
    (마커 매트 불필요 — 로봇은 그리퍼 개폐 3동작으로 수를 표현: 바위=닫기·보=펴기·가위=끄기).
"""

# ── sys.path 부트스트랩(공통 모듈 import 경로 확보) — 두 줄 고정 규약 ──────────
import os, sys; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import random  # 로봇이 자기 수를 무작위로 정할 때 사용

# 공통 모듈(계약 CONTRACTS.md) — 하드웨어/키 없이도 mock으로 동작
pass
pass
pass

# MediaPipe/하드웨어는 try/except로 보호됨(common.vision 내부). 여기서는 mock 경로로 동작.


# ════════════════════════════════════════════════════════════════════════════
# A. 손 랜드마크 → 가위/바위/보 분류 (★학습 핵심: 순수함수 classify_rps)
# ════════════════════════════════════════════════════════════════════════════

# MediaPipe Hands 21점 랜드마크 인덱스(분류에 쓰는 핵심 점만)
# 각 손가락은 MCP(첫 마디) → PIP(둘째 마디) → TIP(끝) 순. 방향무관 판정엔
# '손목(WRIST)에서 본 거리'를 쓰므로 PIP·TIP 인덱스가 핵심이다.
WRIST = 0          # 손목(거리 판정의 기준점)
THUMB_TIP = 4      # 엄지 끝
INDEX_MCP = 5      # 검지 첫 마디(손바닥쪽)
INDEX_PIP = 6      # 검지 둘째 마디
INDEX_TIP = 8      # 검지 끝
MIDDLE_MCP = 9     # 중지 첫 마디
MIDDLE_PIP = 10    # 중지 둘째 마디
MIDDLE_TIP = 12    # 중지 끝
RING_MCP = 13      # 약지 첫 마디
RING_PIP = 14      # 약지 둘째 마디
RING_TIP = 16      # 약지 끝
PINKY_MCP = 17     # 새끼 첫 마디
PINKY_PIP = 18     # 새끼 둘째 마디
PINKY_TIP = 20     # 새끼 끝

# (PIP, TIP) 쌍 — 검지·중지·약지·새끼 순. _finger_states가 이 순서로 판정한다.
_FINGER_PIP_TIP = (
    (INDEX_PIP, INDEX_TIP),     # 검지
    (MIDDLE_PIP, MIDDLE_TIP),   # 중지
    (RING_PIP, RING_TIP),       # 약지
    (PINKY_PIP, PINKY_TIP),     # 새끼
)

# 펴짐 판정 마진: dist(wrist,TIP) ≥ dist(wrist,PIP) × 이 값이면 '펴짐'.
# 1.0보다 살짝 크게 둬서 손가락이 거의 접힌 노이즈를 펴짐으로 오판하지 않게 한다.
_EXTEND_MARGIN = 1.10


def _xy(point):
    """랜드마크 한 점에서 (x, y)를 꺼낸다.

    common.vision.HandTracker는 (x,y,z) 튜플, common.mocks는 {"x","y","z"} dict로
    랜드마크를 주므로 두 형태를 모두 받아들이도록 방어한다(단위테스트 호환).
    """
    if isinstance(point, dict):                 # mocks.SAMPLE_HAND_LANDMARKS 형태
        return float(point["x"]), float(point["y"])
    return float(point[0]), float(point[1])     # HandTracker (x,y,z) 튜플 형태


def _dist2d(landmarks, a, b):
    """두 랜드마크 a, b 사이의 2D(x,y) 거리. 정규화 좌표면 거리도 정규화 단위.

    z(깊이)는 무시한다 — 책상을 내려다보는 카메라에선 x,y만으로 충분하고,
    회전(손이 옆으로 누움)에도 거리는 보존되므로 방향무관 판정에 적합하다.
    """
    ax, ay = _xy(landmarks[a])
    bx, by = _xy(landmarks[b])
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


def _finger_states(landmarks):
    """각 손가락이 '펴졌는지'를 (검지,중지,약지,새끼) 4개 bool로 반환한다.

    ★방향무관(rotation-invariant) 판정★
      책상을 위에서 내려다보는 카메라는 손을 임의 방향(세로/가로/대각)으로 잡는다.
      그래서 'TIP이 위(y 작음)면 펴짐' 같은 화면축 기준은 손이 누우면 틀린다.
      대신 손목(WRIST=0)에서의 '거리'를 본다 — 거리는 회전해도 변하지 않으므로
      손이 어느 방향이든 같은 결과가 나온다.

      각 손가락 '펴짐' = dist(WRIST, TIP) ≥ dist(WRIST, PIP) × _EXTEND_MARGIN
        · 손가락을 펴면 끝(TIP)이 둘째 마디(PIP)보다 손목에서 더 멀어진다.
        · 접으면 끝이 손바닥 쪽으로 말려 PIP보다 손목에 가까워진다.
      마진(1.10)으로 거의 접힌 손가락의 미세 노이즈를 펴짐으로 오판하지 않게 한다.
    """
    states = []
    for pip, tip in _FINGER_PIP_TIP:            # 검지·중지·약지·새끼 순
        d_pip = _dist2d(landmarks, WRIST, pip)  # 손목→PIP 거리
        d_tip = _dist2d(landmarks, WRIST, tip)  # 손목→TIP 거리
        # [블록] "손가락 끝이 둘째 마디보다 손목에서 멀면 → 펴짐"
        states.append(d_tip >= d_pip * _EXTEND_MARGIN)
    return tuple(states)                        # (검지, 중지, 약지, 새끼)


def classify_rps(landmarks):
    """[★순수함수] 손 랜드마크 → 'rock' | 'paper' | 'scissors' | 'none'.

    입력: landmarks — 21점 리스트((x,y,z) 튜플 또는 {"x","y","z"} dict 모두 허용).
    출력: 가위바위보 분류 문자열. 입력이 없거나 애매하면 'none'.

    판단 로직(펴진 손가락 수/상태):
      · 바위(rock)     = 네 손가락 모두 접힘(펴진 수 0)            → ✊
      · 보(paper)      = 네 손가락 모두 펴짐(펴진 수 4)            → ✋
      · 가위(scissors) = 검지+중지만 펴짐(펴진 수 2, 약지·새끼 접힘) → ✌
      · 그 외          = 'none'(미인식)
    ※ 이 함수는 로봇·카메라에 의존하지 않는 순수함수 → 단위테스트가 쉽다.
    """
    # 입력 방어: 21점이 아니면 분류 불가
    if not landmarks or len(landmarks) < 21:
        return "none"                           # [블록] "손이 없으면 → 미인식"

    index_up, middle_up, ring_up, pinky_up = _finger_states(landmarks)
    up_count = sum((index_up, middle_up, ring_up, pinky_up))  # 펴진 손가락 수

    # [블록] "만약 펴진 손가락이 0개 이면 → 바위"
    if up_count == 0:
        return "rock"                           # ✊ 주먹

    # [블록] "만약 검지·중지만 펴짐 이면 → 가위"
    if index_up and middle_up and not ring_up and not pinky_up:
        return "scissors"                       # ✌ 검지+중지

    # [블록] "만약 네 손가락 모두 펴짐 이면 → 보"
    if index_up and middle_up and ring_up and pinky_up:
        return "paper"                          # ✋ 편 손

    # 그 외 애매한 손모양(예: 손가락 3개) → 미인식
    return "none"


# ════════════════════════════════════════════════════════════════════════════
# B. 가위바위보 게임 규칙 (승패표)
# ════════════════════════════════════════════════════════════════════════════

# 사람이 보는 한국어 이름(콘솔 피드백용)
RPS_KO = {"rock": "바위 ✊", "paper": "보 ✋", "scissors": "가위 ✌", "none": "미인식"}

# 각 수가 '이기는' 상대 — rock은 scissors를 이긴다 …
_BEATS = {"rock": "scissors", "scissors": "paper", "paper": "rock"}


def judge(student, robot):
    """학생 수 vs 로봇 수 → 학생 기준 'win' | 'lose' | 'draw' | 'none'.

    [블록] "만약 <학생 수가 로봇 수를 이김> 이라면 → 이김"
    student/robot: 'rock'|'paper'|'scissors'. 둘 중 하나라도 'none'이면 'none'.
    """
    # 둘 중 하나라도 미인식이면 판정 불가
    if student == "none" or robot == "none":
        return "none"
    # 같은 수면 비김
    if student == robot:
        return "draw"                           # [블록] "같으면 → 비김"
    # 학생 수가 로봇 수를 이기는 관계면 승, 아니면 패
    if _BEATS[student] == robot:
        return "win"                            # [블록] "이기면 → 이김"
    return "lose"                               # [블록] "그 외 → 짐"


# ════════════════════════════════════════════════════════════════════════════
# C. 로봇의 '수 결정' 과 '내기'(매트 마커로 이동)
# ════════════════════════════════════════════════════════════════════════════

# 두봇 라이트는 손이 없으므로 그리퍼 3동작으로 수를 '낸다'(이동 없음 → 마커 매트 불필요, 안전↑).
#   바위 ✊ = 그리퍼 닫기(grip True)  · 보 ✋ = 그리퍼 펴기(grip False)  · 가위 ✌ = 그리퍼 끄기(펌프 OFF)
RPS_GRIPPER = {
    "rock":     "close",   # [블록] "그리퍼 닫기"  — 주먹처럼 꽉
    "paper":    "open",    # [블록] "그리퍼 펴기"  — 편 손처럼 활짝
    "scissors": "off",     # [블록] "그리퍼 끄기"  — 제3의 상태(펌프 OFF)
}
HOME_Z = 90          # 세리머니(celebrate)에서 쓰는 안전 상승 높이(z, mm)


def decide_robot_move(strategy="random", last_student=None):
    """로봇이 자기 수를 정한다.

    [블록] "로봇 수 = 무작위로 정하기 / (확장) 직전 학생 수에 따라 정하기"
    strategy:
      · "random"  : 무작위(기본). 공정한 가위바위보.
      · "counter" : 교육적 확장 — '직전 학생 수를 이기는 수'를 낸다(간단 전략).
                    last_student가 없거나 'none'이면 무작위로 폴백.
    반환: 'rock'|'paper'|'scissors'
    """
    moves = ["rock", "paper", "scissors"]
    # 확장 전략: 직전 학생 수를 이기는 수를 고른다(예측·대응 개념 학습)
    if strategy == "counter" and last_student in _BEATS:
        # last_student를 이기는 수 = last_student를 'beats' 하는 쪽을 역으로 찾기
        for move, loser in _BEATS.items():
            if loser == last_student:
                return move                     # [블록] "직전 학생 수를 이기는 수 내기"
    # 기본 전략: 무작위
    return random.choice(moves)                 # [블록] "무작위로 한 개 고르기"


def robot_play(bot, move):
    """로봇이 자기 수(move)를 그리퍼 동작으로 '낸다'(이동 없음).

    [블록] "만약 <수 = 바위> 이면 그리퍼 닫기 / 보 이면 펴기 / 가위 이면 끄기"
    바위 ✊ = 닫기(grip True) · 보 ✋ = 펴기(grip False) · 가위 ✌ = 끄기(펌프 OFF)
    반환: 수행한 그리퍼 동작 문자열('close'|'open'|'off') — 로그·검수용.
    """
    action = RPS_GRIPPER[move]                  # 자기 수 → 그리퍼 동작
    if action == "close":
        bot.grip(True)                          # [블록] "그리퍼 닫기"  (바위 ✊)
    elif action == "open":
        bot.grip(False)                         # [블록] "그리퍼 펴기"  (보 ✋)
    else:                                       # "off"
        bot._effector_pump_off()                # [블록] "그리퍼 끄기"  (가위 ✌, 펌프 OFF)
    return action


def celebrate(bot, result):
    """승패에 따른 로봇의 간단한 반응 동작(세리머니, 안전범위 내).

    [블록] "만약 <로봇이 이김> 이라면 작은 세리머니, 비기면 끄덕, 지면 차분히"
    승/패/무에 따라 작은 좌우/상하 흔들기로 표현(작업영역 안의 작은 진폭).
    """
    # 로봇 입장의 결과는 학생 기준의 반대 — 학생이 'lose'면 로봇이 이긴 것
    if result == "lose":                        # 로봇 승리 → 작은 세리머니
        print("   🤖 로봇: (승리 세리머니) 좌우로 살짝 흔들기")
        bot.move_to(230, -40, HOME_Z)           # [블록] "왼쪽으로 살짝"
        bot.move_to(230,  40, HOME_Z)           # [블록] "오른쪽으로 살짝"
    elif result == "win":                       # 학생 승리 → 로봇은 차분히 끄덕
        print("   🤖 로봇: (인정) 끄덕끄덕")
        bot.move_to(230, 0, HOME_Z - 20)        # 살짝 숙임
        bot.move_to(230, 0, HOME_Z)             # 원위치
    else:                                       # 비김/미인식 → 중앙 대기
        print("   🤖 로봇: (대기) 중앙으로 복귀")
        bot.move_to(230, 0, HOME_Z)
    # 마지막엔 항상 중앙 안전 위치로 복귀
    bot.move_to(230, 0, HOME_Z)


# ════════════════════════════════════════════════════════════════════════════
# D. HRI 게임 루프 — N라운드 진행 + 점수 집계
# ════════════════════════════════════════════════════════════════════════════

def play_round(bot, student_landmarks, strategy="random", last_student=None):
    """한 라운드 진행: 학생 손 분류 → 로봇 수 결정 → 내기 → 승패 판정 → 반응.

    반환: dict {student, robot, result} — 점수 집계와 로그에 사용.
    """
    # 0) 라운드 시작 리셋 — 그리퍼 펴기(가위=끄기 다음 라운드에도 정상 복귀)
    bot.grip(False)                             # [블록] "그리퍼 펴기(리셋)"
    # 1) 학생 손모양 분류(순수함수) — 카메라 프레임 대신 랜드마크를 직접 받는다
    student = classify_rps(student_landmarks)   # [블록] "[손] 가위바위보 분류하기"

    # 미인식이면 라운드를 건너뛴다(점수 변동 없음)
    if student == "none":
        print("   👀 학생 손을 인식하지 못했어요(none). 이번 라운드는 건너뜁니다.")
        return {"student": "none", "robot": "none", "result": "none"}

    # 2) 로봇이 자기 수를 정한다
    robot = decide_robot_move(strategy, last_student)  # [블록] "[로봇] 수 정하기"

    # 3) 로봇이 그리퍼 동작으로 '낸다'
    robot_play(bot, robot)                      # [블록] "[로봇] 그리퍼로 수 내기"

    # 4) 승패 판정(학생 기준)
    result = judge(student, robot)              # [블록] "승패표로 판정하기"

    # 5) 콘솔 피드백
    verdict = {"win": "🎉 학생 승!", "lose": "🤖 로봇 승!", "draw": "🤝 비김!"}[result]
    print(f"   학생={RPS_KO[student]:8s} vs 로봇={RPS_KO[robot]:8s} → {verdict}")

    # 6) 로봇 반응 동작(세리머니 등)
    celebrate(bot, result)                      # [블록] "[로봇] 결과에 반응하기"

    return {"student": student, "robot": robot, "result": result}


def run_rps_session(student_landmark_sequence, rounds=None, strategy="random",
                    bot=None, mock=True):
    """가위바위보 N라운드 세션을 진행하고 점수를 집계해 반환한다.

    인자
      student_landmark_sequence : 라운드별 학생 손 랜드마크 리스트의 시퀀스.
      rounds                    : 진행할 라운드 수(None이면 시퀀스 길이).
      strategy                  : 로봇 수 결정 전략("random" 기본 | "counter").
      bot                       : RobotController(없으면 mock으로 새로 만든다).
      mock                      : bot이 없을 때 mock 로봇을 만들지 여부.
    반환: dict {scores:{win,lose,draw,none}, rounds:[라운드별 결과]}
    """
    seq = list(student_landmark_sequence)
    n = rounds if rounds is not None else len(seq)   # [블록] "라운드 수 정하기"

    # 점수판 초기화(학생 기준)
    scores = {"win": 0, "lose": 0, "draw": 0, "none": 0}
    history = []
    last_student = None   # counter 전략에서 쓰는 '직전 학생 수'

    # 로봇 준비(없으면 mock 생성). with로 종료 시 안전정지 보장
    own_bot = bot is None
    if own_bot:
        bot = get_robot(mock=mock)              # [블록] "로봇 가져오기"
        bot.connect()
    bot.home()                                  # [블록] "원점으로 가기"

    try:
        # ── N라운드 반복 ──────────────────────────────────────────────
        for r in range(n):                      # [블록] "계속 반복하기 (N번)"
            print(f"\n━━ 라운드 {r + 1}/{n} ━━")
            landmarks = seq[r % len(seq)] if seq else None  # 시퀀스 순환
            outcome = play_round(bot, landmarks, strategy, last_student)
            scores[outcome["result"]] += 1      # [블록] "점수 올리기"
            history.append(outcome)
            # 다음 라운드의 counter 전략을 위해 직전 학생 수 기억
            if outcome["student"] != "none":
                last_student = outcome["student"]
    finally:
        # 세션 종료: 직접 만든 로봇이면 안전정지 + 연결 해제
        if own_bot:
            bot._safe_stop()                    # 흡착/그리퍼 OFF(안전)
            bot.disconnect()

    return {"scores": scores, "rounds": history}


# ════════════════════════════════════════════════════════════════════════════
# E. 캔드 학생 손 시퀀스 — mock 테스트용(가위/바위/보 샘플 랜드마크)
# ════════════════════════════════════════════════════════════════════════════

def sample_landmarks(shape):
    """가위/바위/보 각각의 캔드 21점 랜드마크를 만든다(HandTracker mock과 호환).

    shape: 'rock'|'paper'|'scissors'.
    common.vision.HandTracker._mock_hand()의 '편 손' 21점을 기준으로,
    필요한 손가락 끝을 MCP 아래(y 큰 값)로 내려 '접힘'을 만든다.
    반환: [(x,y,z), ...] 21점 — classify_rps가 그대로 분류할 수 있다.
    """
    # 기준: 편 손(보) — 모든 손가락이 펴진 상태의 21점
    base = [list(p) for p in HandTracker._mock_hand()["landmarks"]]
    fold_y = 0.80   # MCP(≈0.62)보다 아래로 내려 '접힘'을 표현하는 y값

    if shape == "paper":
        pass                                    # 편 손 그대로(보 ✋)
    elif shape == "rock":
        # 바위 ✊: 검지·중지·약지·새끼 모두 접기
        for i in (INDEX_TIP, MIDDLE_TIP, RING_TIP, PINKY_TIP):
            base[i][1] = fold_y
    elif shape == "scissors":
        # 가위 ✌: 검지·중지는 펴고, 약지·새끼만 접기
        for i in (RING_TIP, PINKY_TIP):
            base[i][1] = fold_y
    else:
        raise ValueError(f"알 수 없는 손모양: {shape}")

    return [tuple(p) for p in base]


# 데모용 학생 손 시퀀스(가위 → 바위 → 보 → 가위 → 바위)
DEMO_SEQUENCE = [
    sample_landmarks("scissors"),
    sample_landmarks("rock"),
    sample_landmarks("paper"),
    sample_landmarks("scissors"),
    sample_landmarks("rock"),
]


# ════════════════════════════════════════════════════════════════════════════
# F. 자가 데모 (mock) — 하드웨어/카메라/키 없이 끝까지 실행
# ════════════════════════════════════════════════════════════════════════════



# ==============================================================================
# ── common/gui.py — LessonGUI
# ==============================================================================

"""common/gui.py — 차시 공용 GUI 베이스 (Tkinter + OpenCV 카메라 + 로봇 + 비상정지).

목적
----
강사/학생이 **마우스로 직접** 차시를 실행·조작하도록 하는 공통 GUI 틀.
좌측에 라이브 카메라(오버레이 가능), 우측에 로봇 연결/상태·차시별 컨트롤·로그·
빨간 **비상정지** 버튼을 둔다. 차시별 GUI는 이 베이스에 콜백만 주입하면 된다.

설계
----
- 카메라 캡처는 **백그라운드 스레드**에서 돌고, 매 프레임 `process_frame(frame, app)`
  콜백을 호출한다(여기서 차시 로직·로봇 이동 수행 가능 — UI 스레드 안 막음).
  콜백은 화면에 그릴 BGR 프레임을 반환한다(오버레이 포함).
- UI 스레드는 `after()`로 최신 프레임만 캔버스에 표시(PIL ImageTk).
- 로봇 연결/비상정지/로그는 스레드 안전하게 처리.

의존성: tkinter(기본), opencv-python, Pillow, numpy. 없으면 친절한 오류.
하드웨어/카메라 없어도 import 는 되며, 실행 시 카메라/로봇이 없으면 mock/안내로 폴백.

사용 예 (차시 GUI)
------------------
    from common.gui import LessonGUI
    def proc(frame, app):
        # frame(BGR) 처리·오버레이, app.set_status(...), app.robot 사용 가능
        return frame
    app = LessonGUI("M2 가위바위보", camera_index=0, use_robot=True,
                    process_frame=proc,
                    controls=[("게임 시작", on_start)])
    app.run()
"""

import threading
import time

# --- tkinter (표준) ---
try:
    import tkinter as tk
    from tkinter import scrolledtext
    _HAS_TK = True
except Exception:
    tk = None
    _HAS_TK = False

# --- opencv / Pillow / numpy (가드) ---
try:
    import cv2
    _HAS_CV2 = True
except Exception:
    cv2 = None
    _HAS_CV2 = False

try:
    from PIL import Image, ImageTk
    _HAS_PIL = True
except Exception:
    Image = ImageTk = None
    _HAS_PIL = False

try:
    import numpy as np
    _HAS_NUMPY = True
except Exception:
    np = None
    _HAS_NUMPY = False

# 로봇 제어기(있으면). GUI 자체는 로봇 없이도 동작.
try:
    pass
except Exception:
    get_robot = None


# 색상(테마) — 차분한 다크 패널
_BG = "#1e1e2e"
_PANEL = "#2a2a3c"
_FG = "#e6e6e6"
_ACCENT = "#4f9dff"
_DANGER = "#e5484d"


class LessonGUI:
    """차시 공용 GUI 창.

    파라미터
    --------
    title : 창 제목.
    camera_index : 사용할 카메라 인덱스(차시에 맞게: 손=CAM_HAND, 책상=CAM_TABLE).
    use_robot : True면 로봇 연결 버튼/상태 표시.
    port : 로봇 포트(None이면 자동/설정).
    process_frame : callback(frame_bgr, app) -> frame_bgr. 매 프레임 호출(캡처 스레드).
                    여기서 차시 로직·오버레이·로봇 이동 수행. None이면 원본 표시.
    controls : [(라벨, callback(app)), ...] 우측에 추가할 버튼들.
    info : 상단에 표시할 안내 문구.
    """

    def __init__(self, title="차시", camera_index=0, use_robot=True, port=None,
                 process_frame=None, controls=None, info="", build_controls=None,
                 on_canvas_click=None):
        if not _HAS_TK:
            raise RuntimeError("tkinter 가 없어 GUI를 띄울 수 없습니다.")
        if not (_HAS_CV2 and _HAS_PIL):
            raise RuntimeError("GUI 카메라 표시는 opencv-python 과 Pillow 가 필요합니다. "
                               "`pip install opencv-python pillow` 후 실행하세요.")
        self.title = title
        self.camera_index = camera_index
        self.use_robot = use_robot
        self.port = port
        self._process_frame = process_frame
        self._controls = controls or []
        self.info = info
        self._build_controls = build_controls   # callback(parent_frame, app): 커스텀 위젯 추가용
        self._on_canvas_click = on_canvas_click  # callback(px, py, app): 카메라 영상 클릭 시(픽셀좌표)
        self._frame_wh = None                    # 마지막 표시 프레임 크기(w,h) — 클릭 좌표 보정용

        # 상태
        self.robot = None            # 연결된 RobotController(없으면 None)
        self.running = True          # 캡처 루프 on/off
        self._cap = None
        self._raw = None             # 카메라 최신 원본 프레임(BGR)
        self._display = None         # 표시용(처리/오버레이 결과) 프레임(BGR)
        self._display_ver = 0        # 표시 프레임 버전(바뀐 경우에만 다시 그림 → UI 부하↓)
        self._shown_ver = -1
        self._lock = threading.Lock()
        self._log_q: list[str] = []

        self._build_ui()
        self._start_camera()

    # ---------------- UI 구성 ----------------
    def _build_ui(self):
        self.root = tk.Tk()
        self.root.title(self.title)
        self.root.configure(bg=_BG)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # 좌측: 카메라
        left = tk.Frame(self.root, bg=_BG)
        left.grid(row=0, column=0, padx=8, pady=8, sticky="n")
        self.canvas = tk.Label(left, bg="#000000", bd=0, highlightthickness=0)
        # 첫 프레임 표시 전, Label 의 width/height 는 '텍스트 단위(문자/줄)'로 해석돼
        # 창이 거대(480줄≈7000px)해진다. 640x480 px 블랭크 이미지를 미리 넣어 픽셀 크기를
        # 고정한다(첫 프레임이 오면 그 이미지로 교체됨). 참조 유지(GC 방지).
        self._blank_img = tk.PhotoImage(width=640, height=480)
        self.canvas.configure(image=self._blank_img)
        self.canvas.pack()
        # 카메라 영상 클릭 → 픽셀좌표 콜백(캘리브레이션 등). 영상은 원본 해상도로 표시하므로
        # 위젯 좌표 ≈ 프레임 픽셀좌표(표시 크기와 다르면 _canvas_click 에서 스케일 보정).
        if self._on_canvas_click is not None:
            self.canvas.bind("<Button-1>", self._canvas_click)
        tk.Label(left, text=self.info, bg=_BG, fg=_FG, wraplength=640,
                 justify="left", font=("맑은 고딕", 10)).pack(anchor="w", pady=(6, 0))

        # 우측: 컨트롤 패널
        #   컨트롤이 많아 창 높이를 넘으면 잘리던 문제 → 세로 '스크롤' 가능하게 한다.
        #   단, 비상정지(E-STOP)와 로그는 스크롤 영역 '밖' 하단에 고정해 **항상 보이게**
        #   한다(안전·실시간 가시성). 나머지(제목/상태/로봇연결/차시 컨트롤)는 스크롤된다.
        right_outer = tk.Frame(self.root, bg=_PANEL)
        right_outer.grid(row=0, column=1, padx=(0, 8), pady=8, sticky="ns")

        # (1) 하단 고정: 비상정지 — 스크롤과 무관하게 항상 보임(맨 아래)
        estop = tk.Button(right_outer, text="■ 비상정지 (E-STOP)", command=self._estop,
                          bg=_DANGER, fg="white", font=("맑은 고딕", 12, "bold"),
                          relief="raised", height=2)
        estop.pack(side="bottom", fill="x", padx=12, pady=(6, 10))

        # (2) 하단 고정: 로그 — 항상 보임(실시간 메시지 확인). E-STOP 바로 위.
        log_frame = tk.Frame(right_outer, bg=_PANEL)
        log_frame.pack(side="bottom", fill="x", padx=12)
        tk.Label(log_frame, text="로그", bg=_PANEL, fg=_FG,
                 font=("맑은 고딕", 10, "bold")).pack(anchor="w", pady=(6, 2))
        self.logbox = scrolledtext.ScrolledText(log_frame, width=34, height=8,
                                                bg="#16161f", fg="#cfcfcf",
                                                font=("Consolas", 9))
        self.logbox.pack(fill="x")

        # (3) 상단 스크롤 영역: 나머지 컨트롤을 담는 캔버스 + 스크롤바
        sc_canvas = tk.Canvas(right_outer, bg=_PANEL, highlightthickness=0, bd=0)
        sc_bar = tk.Scrollbar(right_outer, orient="vertical", command=sc_canvas.yview)
        sc_canvas.configure(yscrollcommand=sc_bar.set)
        sc_bar.pack(side="right", fill="y")
        sc_canvas.pack(side="left", fill="both", expand=True)

        # 실제 컨트롤이 쌓이는 내부 프레임(= 이전의 right). 이후 코드는 그대로 사용.
        right = tk.Frame(sc_canvas, bg=_PANEL, padx=12, pady=12)
        sc_canvas.create_window((0, 0), window=right, anchor="nw")

        # 창 전체가 화면에 들어오도록 스크롤 영역 가시 높이 상한을 화면높이에 맞춰 정한다.
        try:
            screen_h = self.root.winfo_screenheight()
        except Exception:
            screen_h = 900
        _max_panel_h = max(240, min(640, screen_h - 390))  # 로그/E-STOP/창여백 제외분

        def _sync_scroll(_evt=None):
            # 내용 크기에 맞춰 스크롤영역/캔버스 크기 갱신(짧으면 짧게, 길면 상한+스크롤)
            sc_canvas.configure(scrollregion=sc_canvas.bbox("all"))
            sc_canvas.configure(height=min(right.winfo_reqheight(), _max_panel_h),
                                width=right.winfo_reqwidth())
        right.bind("<Configure>", _sync_scroll)

        # 마우스휠: 패널에 마우스가 올라가 있을 때만 스크롤(카메라 위에선 동작 안 함)
        def _wheel(evt):
            sc_canvas.yview_scroll(int(-1 * (evt.delta / 120)), "units")
        sc_canvas.bind("<Enter>", lambda e: sc_canvas.bind_all("<MouseWheel>", _wheel))
        sc_canvas.bind("<Leave>", lambda e: sc_canvas.unbind_all("<MouseWheel>"))

        # ── 이하 컨트롤은 모두 스크롤 내부 프레임(right)에 쌓는다 ──
        tk.Label(right, text=self.title, bg=_PANEL, fg=_ACCENT,
                 font=("맑은 고딕", 14, "bold")).pack(anchor="w")

        # 상태 라벨
        self.status_var = tk.StringVar(value="준비됨")
        tk.Label(right, textvariable=self.status_var, bg=_PANEL, fg=_FG,
                 font=("맑은 고딕", 11), wraplength=260, justify="left").pack(
            anchor="w", pady=(8, 8))

        # 로봇 연결
        if self.use_robot:
            self.robot_status = tk.StringVar(value="로봇: 미연결")
            tk.Label(right, textvariable=self.robot_status, bg=_PANEL, fg=_FG,
                     font=("맑은 고딕", 10)).pack(anchor="w")
            self._mk_btn(right, "로봇 연결", self._connect_robot_async, _ACCENT)

        # 차시별 컨트롤 버튼
        for label, cb in self._controls:
            self._mk_btn(right, label, lambda c=cb: c(self), "#3a3a52")

        # 차시별 커스텀 위젯(텍스트 입력·보드 등) — 콜백이 우측 패널에 직접 추가
        if self._build_controls is not None:
            try:
                self._build_controls(right, self)
            except Exception as e:
                self.log(f"[컨트롤 구성 오류] {e}")

        self.log(f"'{self.title}' 시작. 카메라 index={self.camera_index}.")

    def _canvas_click(self, event):
        """카메라 영상 클릭 → 프레임 픽셀좌표로 변환해 콜백 호출(캘리브레이션 마킹 등).

        영상은 원본 해상도(1:1)로 캔버스 좌상단부터 표시하므로 위젯좌표가 곧 픽셀좌표다.
        표시 영상 크기(_frame_wh) 밖 클릭(여백)은 무시한다. 첫 프레임 표시 전이면 무시.
        """
        cb = self._on_canvas_click
        if cb is None:
            return
        px, py = event.x, event.y
        wh = self._frame_wh
        if wh is None:
            return                                  # 아직 첫 프레임 표시 전 — 좌표 기준 없음
        fw, fh = wh
        # 영상은 캔버스 좌상단(0,0)부터 원본 해상도(1:1)로 그려지므로 위젯좌표 == 픽셀좌표.
        # 영상 영역 밖 클릭은 무시(여백 클릭 방지).
        if px < 0 or py < 0 or px >= fw or py >= fh:
            return
        try:
            cb(int(px), int(py), self)
        except Exception as e:
            self.log(f"[클릭 처리 오류] {type(e).__name__}: {e}")

    def _mk_btn(self, parent, label, cmd, color):
        b = tk.Button(parent, text=label, command=cmd, bg=color, fg="white",
                      font=("맑은 고딕", 11), relief="flat", height=1)
        b.pack(fill="x", pady=3)
        return b

    # ---------------- 로그/상태(스레드 안전) ----------------
    def log(self, msg: str):
        self._log_q.append(time.strftime("%H:%M:%S ") + str(msg))

    def set_status(self, msg: str):
        try:
            self.status_var.set(str(msg))
        except Exception:
            pass

    def _drain_log(self):
        if self._log_q:
            for line in self._log_q:
                self.logbox.insert("end", line + "\n")
            self._log_q.clear()
            self.logbox.see("end")

    # ---------------- 카메라 ----------------
    # 끊김(뚝뚝) 방지: [캡처(빠른 읽기)] / [처리(무거운 AI·로봇)] / [표시] 를 분리하고,
    # 카메라 버퍼를 최신 1장만 유지(밀림·지연 누적 방지). 처리 스레드는 항상 '최신
    # 원본'만 처리(밀린 프레임은 드롭)하여 지연이 쌓이지 않게 한다.
    def _start_camera(self):
        self._cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
        if self._cap:
            try:
                self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # 최신 프레임만(지연/밀림 방지)
            except Exception:
                pass
        if not self._cap or not self._cap.isOpened():
            self.log(f"[경고] 카메라 {self.camera_index} 를 열 수 없습니다. 다른 인덱스를 시도하세요.")
        threading.Thread(target=self._capture_loop, daemon=True).start()  # 빠른 읽기
        if self._process_frame is not None:
            threading.Thread(target=self._worker_loop, daemon=True).start()  # 무거운 처리
        self._tick()  # UI 갱신 루프 시작

    def _capture_loop(self):
        """카메라에서 최대한 빠르게 읽어 최신 원본(_raw)만 유지(버퍼 밀림 방지)."""
        while self.running:
            if not self._cap:
                time.sleep(0.1)
                continue
            ok, frame = self._cap.read()
            if not ok or frame is None:
                time.sleep(0.02)
                continue
            with self._lock:
                self._raw = frame
                if self._process_frame is None:
                    self._display = frame   # 처리기 없으면 원본을 그대로 표시
                    self._display_ver += 1
            time.sleep(0.003)

    def _worker_loop(self):
        """무거운 처리(mediapipe/로봇)는 별도 스레드에서 '최신 원본'에만 수행.
        밀린 프레임은 건너뛰어(드롭) 지연 누적·끊김을 막는다."""
        last = None
        while self.running:
            with self._lock:
                frame = self._raw
            if frame is None or frame is last:
                time.sleep(0.008)
                continue
            last = frame
            try:
                out = self._process_frame(frame.copy(), self)  # 차시 로직(로봇 이동 등)
            except Exception as e:
                self.log(f"[처리 오류] {type(e).__name__}: {e}")
                out = frame
            with self._lock:
                self._display = out
                self._display_ver += 1
            time.sleep(0.003)

    def _tick(self):
        # 최신 표시 프레임을 캔버스에 표시(UI 스레드). 처리결과 있으면 그것, 없으면 원본.
        with self._lock:
            ver = self._display_ver
            need = (ver != self._shown_ver)        # 프레임이 바뀐 경우에만 다시 그림
            src = self._display if self._display is not None else self._raw
            frame = src.copy() if (need and src is not None) else None
        if frame is not None:
            try:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(rgb)
                imgtk = ImageTk.PhotoImage(image=img)
                self.canvas.imgtk = imgtk  # 참조 유지(GC 방지)
                self.canvas.configure(image=imgtk)
                self._frame_wh = (img.width, img.height)  # 클릭 좌표 보정용 표시 크기
                self._shown_ver = ver
            except Exception:
                pass
        self._drain_log()
        if self.running:
            self.root.after(15, self._tick)

    # ---------------- 로봇 ----------------
    def _connect_robot_async(self):
        self.robot_status.set("로봇: 연결 중...")
        threading.Thread(target=self._connect_robot, daemon=True).start()

    def _connect_robot(self):
        if get_robot is None:
            self.log("[오류] 로봇 제어 모듈을 불러올 수 없습니다.")
            return
        try:
            bot = get_robot(port=self.port, mock=False)
            bot.connect()
            self.robot = bot
            mode = "mock" if getattr(bot, "mock", False) else "실기"
            self.robot_status.set(f"로봇: 연결됨({mode})")
            self.log(f"로봇 연결됨 ({mode}). 홈 복귀 중...")
            bot.home()
            self.log("홈 복귀 완료.")
        except Exception as e:
            self.robot_status.set("로봇: 연결 실패")
            self.log(f"[로봇 연결 오류] {e}")

    def _estop(self):
        self.log("■ 비상정지!")
        self.set_status("■ 비상정지됨")
        bot = self.robot
        if bot is not None:
            try:
                # 흡착/그리퍼 끄고 정지 시도
                if hasattr(bot, "_safe_stop"):
                    threading.Thread(target=bot._safe_stop, daemon=True).start()
            except Exception as e:
                self.log(f"[비상정지 오류] {e}")

    # ---------------- 종료 ----------------
    def _on_close(self):
        """창 종료 시: 캡처 중단 → 카메라 해제 → 로봇 안전정지 + 연결 해제(COM 포트 완전 해제) → 창 파괴."""
        self.running = False           # 캡처/틱 루프 중단 신호
        time.sleep(0.2)                # 캡처 스레드가 진행 중 프레임 처리 끝낼 시간
        # 1) 카메라 해제
        try:
            if self._cap:
                self._cap.release()
                self._cap = None
        except Exception:
            pass
        # 2) 로봇: 안전정지(흡착/그리퍼 OFF) → disconnect(device.close() = 시리얼/COM 포트 해제)
        bot = self.robot
        if bot is not None:
            try:
                if hasattr(bot, "_safe_stop"):
                    bot._safe_stop()
            except Exception:
                pass
            try:
                bot.disconnect()       # COM 포트 완전 해제
                self.log("로봇 연결 해제(COM 포트 반환).")
            except Exception:
                pass
            self.robot = None
        # 3) 창 파괴(프로세스 종료 시 OS 가 남은 핸들도 정리)
        try:
            self.root.destroy()
        except Exception:
            pass

    def run(self):
        self.root.mainloop()


# 자가 데모 — 카메라 뷰어만(로봇 없이). 카메라 index 0.



# ==============================================================================
# ── m2_gesture_hri/gui.py — M2 화면/조작 로직 + main()
# ==============================================================================

"""m2_gesture_hri/gui.py — 마우스로 조작하는 가위바위보 수동 테스트 GUI.

[차시] M2 · 사람과 가위바위보 (HRI)
[카메라] config.CAM_HAND (사용자를 향한 웹캠 — 손/제스처)

강사/학생이 마우스로 직접 조작·수동 테스트하는 GUI다. 공통 베이스
common.gui.LessonGUI 위에 콜백만 주입한다.

  · process_frame : 카메라 스레드에서 매 프레임 호출. HandTracker로 손을
    찾고 solution.classify_rps 로 제스처를 판정해 한글 제스처명을 오버레이.
    최근 제스처/랜드마크를 app 에 보관(한판내기 버튼이 사용).
  · controls "한 판 내기!" : 스레드에서 로봇 연결 + 제스처 인식되어 있으면
    solution.play_round(robot, 최근 랜드마크) 실행 → 점수 누적·로그.
  · build_controls : 점수판 라벨(이김/짐/비김).

규칙 준수:
  · 로봇 이동(버튼 콜백)은 threading.Thread 로 실행(UI 안 막힘).
  · 기존 solution 함수(classify_rps, play_round, RPS_KO)를 재사용.
  · GUI 생성/실행은 if __name__ == "__main__" 아래에서만 — import 시 안전.
  · 하드웨어/카메라/키 없어도 import 는 성공.
"""

# ── sys.path 부트스트랩(공통 모듈 import 경로 확보) — 두 줄 고정 규약 ──────────
import os, sys; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import threading
import time

pass
pass
pass


# 안내 문구(상단 표시)
INFO = ("노트북 웹캠에 손이 보이게 하세요(가위/바위/보). 화면에 인식된 제스처가 "
        "한글로 표시됩니다. '로봇 연결' 후 손을 고정한 상태에서 '한 판 내기!'를 "
        "누르면 로봇이 마커로 자기 수를 내고 승패를 가립니다.")

# process_frame 안 오버레이용 색(BGR)
_GREEN = (80, 220, 80)
_GRAY = (170, 170, 170)


def make_process_frame():
    """카메라 스레드에서 쓸 process_frame 콜백을 만든다(HandTracker 1개 보유).

    매 프레임: 손 검출 → classify_rps 로 제스처 판정 → 한글명 오버레이.
    최근 제스처/랜드마크를 app 에 저장해 '한 판 내기!' 버튼이 쓰게 한다.
    """
    tracker = HandTracker(mock=False)            # 실기(하드웨어 없으면 내부 mock 폴백)
    import cv2                                    # 베이스가 cv2 보장(없으면 GUI 생성 단계에서 차단)

    def process_frame(frame, app):
        # 비전 백엔드(가속) 1회 로그 — GPU delegate/CPU 어느 쪽으로 도는지 보이게
        if not getattr(app, "_vbackend_logged", False):
            app._vbackend_logged = True
            try:
                app.log(f"[비전 백엔드] {tracker.backend_info()}")
            except Exception:
                pass

        # 1) 손 검출(표준 dict {landmarks, handedness}; 손 없으면 {})
        try:
            result = tracker.process(frame)
        except Exception as e:
            app.log(f"[손 인식 오류] {e}")
            result = {}

        landmarks = result.get("landmarks") if result else None

        # 2) 제스처 분류(순수함수 재사용)
        gesture = solution.classify_rps(landmarks) if landmarks else "none"

        # 3) 최근 상태 보관(버튼 콜백이 사용)
        app.last_gesture = gesture
        app.last_landmarks = landmarks if gesture != "none" else None

        # 4) 오버레이 — 한글 제스처명(RPS_KO 재사용) + 손 랜드마크 점
        ko = solution.RPS_KO.get(gesture, "미인식")
        color = _GREEN if gesture != "none" else _GRAY
        cv2.putText(frame, f"gesture: {gesture}", (12, 36),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2, cv2.LINE_AA)
        # 한글은 cv2 기본 폰트가 못 그리므로 상태바에 한글로, 화면엔 영문/이모지 키만.
        app.set_status(f"현재 제스처: {ko}")

        # 손 랜드마크 점 찍기(정규화 좌표 → 픽셀)
        if landmarks:
            h, w = frame.shape[:2]
            for p in landmarks:
                px, py = int(p[0] * w), int(p[1] * h)
                cv2.circle(frame, (px, py), 3, color, -1)

        return frame

    return process_frame


def on_play_round(app):
    """'한 판 내기!' 버튼 콜백 — 로봇 이동이므로 스레드에서 실행(UI 안 막힘)."""
    def worker():
        bot = app.robot
        if bot is None:
            app.log("[안내] 먼저 '로봇 연결'을 눌러 로봇을 연결하세요.")
            app.set_status("로봇 미연결 — 연결 후 다시 시도하세요.")
            return

        gesture = getattr(app, "last_gesture", "none")
        landmarks = getattr(app, "last_landmarks", None)
        if gesture == "none" or not landmarks:
            app.log("[안내] 손 제스처가 인식되지 않았습니다. 손을 고정한 뒤 다시 누르세요.")
            app.set_status("제스처 미인식 — 손을 카메라에 고정하세요.")
            return

        app.log(f"한 판 시작! 학생 제스처={solution.RPS_KO.get(gesture, gesture)}")
        app.set_status("로봇이 수를 내는 중...")
        try:
            # 기존 차시 로직 재사용 — 로봇이 마커로 내고 승패 판정까지 수행
            outcome = solution.play_round(bot, landmarks)
        except Exception as e:
            app.log(f"[한 판 내기 오류] {type(e).__name__}: {e}")
            app.set_status("한 판 진행 중 오류 발생")
            return

        # 점수 누적(학생 기준 win/lose/draw/none)
        result = outcome.get("result", "none")
        if result in app.scores:
            app.scores[result] += 1
        _refresh_scoreboard(app)

        s_ko = solution.RPS_KO.get(outcome.get("student", "none"), "미인식")
        r_ko = solution.RPS_KO.get(outcome.get("robot", "none"), "미인식")
        verdict = {"win": "🎉 학생 승!", "lose": "🤖 로봇 승!",
                   "draw": "🤝 비김!", "none": "👀 미인식"}.get(result, result)
        app.log(f"학생={s_ko} vs 로봇={r_ko} → {verdict}")
        app.set_status(verdict)

    threading.Thread(target=worker, daemon=True).start()


def _refresh_scoreboard(app):
    """점수판 라벨 갱신(UI 스레드 안전: StringVar.set)."""
    sc = app.scores
    try:
        app.score_var.set(f"이김 {sc['win']}   짐 {sc['lose']}   비김 {sc['draw']}")
    except Exception:
        pass


def make_build_controls():
    """우측 패널에 점수판 라벨을 추가하는 build_controls 콜백을 만든다."""
    def build_controls(parent, app):
        import tkinter as tk

        # 점수 상태 초기화(app 에 보관)
        app.scores = {"win": 0, "lose": 0, "draw": 0, "none": 0}
        app.last_gesture = "none"
        app.last_landmarks = None

        tk.Label(parent, text="점수판 (학생 기준)", bg="#2a2a3c", fg="#e6e6e6",
                 font=("맑은 고딕", 10, "bold")).pack(anchor="w", pady=(12, 2))

        app.score_var = tk.StringVar(value="이김 0   짐 0   비김 0")
        tk.Label(parent, textvariable=app.score_var, bg="#16161f", fg="#9fe09f",
                 font=("맑은 고딕", 12, "bold"), padx=8, pady=6,
                 anchor="w").pack(fill="x")

    return build_controls


def main():
    """GUI 생성·실행(이 함수는 __main__ 에서만 호출)."""
    pass

    app = LessonGUI(
        title="M2 · 가위바위보 (HRI)",
        camera_index=config.CAM_HAND,
        use_robot=True,
        process_frame=make_process_frame(),
        controls=[("한 판 내기!", on_play_round)],
        build_controls=make_build_controls(),
        info=INFO,
    )
    app.run()


if __name__ == "__main__":
    # Windows 콘솔(cp949) 한글/이모지 출력 보정 — 미지원 환경이면 그대로 진행
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    main()


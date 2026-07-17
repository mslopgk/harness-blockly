# -*- coding: utf-8 -*-
"""[H1] 자연어로 로봇 제어 (VLA · 보고 집기) GUI — 단일 파일(standalone) 버전.

원본(taskB_curriculum/h1_vlm_nl_control/gui.py + 의존 모듈들: common.config /
common.safety / common.vision / common.ai_clients / common.calibration /
common.grounding / common.motion_control / common.dobot_ctl / common.gui /
h1_vlm_nl_control.solution)을 **하나의 파이썬 파일**로 합친 것.

자동 생성물 — 로직은 원본과 동일하다(중복 구현/재작성 아님). 여러 모듈을 한 네임스페이스로
평탄화하고, config./safety. 같은 모듈 한정 참조가 이 파일 자신을 가리키도록 alias 처리했다.

실행:  python 자연어제어_standalone.py     (하드웨어/API 키 없으면 자동 mock)
       CURRICULUM_FORCE_MOCK=1 로 언제든 오프라인 mock 데모를 강제할 수 있다.
필요:  tkinter(표준). 선택적으로 opencv-python / pillow / numpy / pydobot.
       MiniMax(두뇌)·로컬 Qwen VLM(눈)은 키/서버가 없으면 자동으로 mock 폴백한다.
"""
from __future__ import annotations

import sys as _sys

# ── 패키지 평탄화용 self-alias ───────────────────────────────────────────────
# 원본은 common 패키지로 나뉘어 `config.X` / `safety.X` / `_config` / `_accel`
# 처럼 모듈을 한정해 서로를 참조했다. 단일 파일에서는 그 이름들이 모두 '이 모듈'을
# 가리키게 하면, 아래에 이어붙인 각 원본 코드의 참조가 그대로 동작한다.
config  = _sys.modules[__name__]   # config.WORKSPACE / config.is_mock() ...
safety  = _sys.modules[__name__]   # safety.check_move / safety.clamp_move ...
_config = _sys.modules[__name__]   # common.vision/ai_clients/... 내부 별칭
_accel  = None                     # 선택적 GPU 가속(accel) 비활성 → 순수 cv2 경로

# numpy: 캘리브레이션(어핀)·비전/그라운딩 프레임 처리에서 사용(없으면 안내 후 폴백).
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
# ── common/vision.py
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
# ── common/ai_clients.py
# ==============================================================================

"""ai_clients.py — 공급자무관 AI 클라이언트 래퍼 (ADR-0001).

목적
----
LLM(대형언어모델)·VLM(비전언어모델)·STT(음성→텍스트) 세 가지 AI 기능을
**하나의 일관된 인터페이스**로 제공한다. 차시(P2) 코드와 검수 스크립트는
이 래퍼만 바라보면 되므로, 실제 백엔드(anthropic/whisper)가 바뀌어도
교육 코드를 고치지 않아도 된다(= 공급자무관, provider-agnostic).

핵심 안전장치 (교육용·무하드웨어 원칙, ADR-0004)
------------------------------------------------
- anthropic / whisper / numpy 같은 무거운(또는 키가 필요한) 의존성은
  파일 상단에서 try/except 로 감싸 **없으면 자동으로 Mock 백엔드로 폴백**한다.
- API 키가 없거나 config.is_mock()이 True면 역시 Mock 으로 동작한다.
- Mock 백엔드는 **결정적(deterministic)** 인 캔드(canned) 응답을 돌려주고,
  호출 인자를 self.calls 리스트에 기록한다(테스트·디버깅용).

사용법
------
    from common.ai_clients import LLMClient, VLMClient, STTClient

    llm = LLMClient()                                  # 키 없으면 자동 Mock
    answer = llm.complete(
        messages=[{"role": "user", "content": "안녕?"}],
        system="너는 친절한 조수야.",
    )

    vlm = VLMClient()
    desc = vlm.describe(image="photo.png", prompt="무엇이 보이나요?")
    # image 는 파일 경로(str) 또는 numpy 배열(ndarray) 모두 허용

    stt = STTClient()
    text = stt.transcribe("recording.wav")

이 파일을 직접 실행하면(python ai_clients.py) mock 자가 데모가 돈다.
"""


import base64
import io
import json
import os
from typing import Any

# ──────────────────────────────────────────────────────────────────────────
# 1) 의존성 import — 없으면 None 으로 두고, 이후 mock 으로 폴백한다.
#    (하드웨어/키 없는 교실 PC에서도 import 자체는 반드시 성공해야 함)
# ──────────────────────────────────────────────────────────────────────────
try:
    import anthropic  # 실제 LLM/VLM 백엔드(Claude)
except Exception:  # pragma: no cover - 미설치 환경 폴백
    anthropic = None  # type: ignore[assignment]

try:
    import whisper  # 실제 STT 백엔드(OpenAI Whisper, 로컬 모델)
except Exception:  # pragma: no cover
    whisper = None  # type: ignore[assignment]

# faster-whisper(CTranslate2): 같은 정확도로 훨씬 빠르고(int8 CPU) 메모리도 적게 써서
# medium/large 모델을 교실 PC에서도 현실적으로 돌릴 수 있다. 있으면 우선 사용한다.
try:
    from faster_whisper import WhisperModel as _FasterWhisperModel
except Exception:  # pragma: no cover
    _FasterWhisperModel = None  # type: ignore[assignment]

try:
    import numpy as np  # ndarray 이미지 인코딩에 사용
except Exception:  # pragma: no cover
    np = None  # type: ignore[assignment]

# ── config 연동 (선택적) ──────────────────────────────────────────────────
# config.py 는 다른 단계에서 만들어진다. 아직 없을 수도 있으므로 방어적으로 읽는다.
try:
    _config = config
except Exception:  # pragma: no cover - config 미존재 시 환경변수로 대체
    _config = None  # type: ignore[assignment]


# 계약(CONTRACTS.md)에 명시된 기본 모델명.
# config.py 가 있으면 그 값을 우선 사용하고, 없으면 아래 기본값을 쓴다.
_DEFAULT_LLM_MODEL = getattr(_config, "LLM_MODEL", "claude-sonnet-4-6")
_DEFAULT_VLM_MODEL = getattr(_config, "VLM_MODEL", "claude-sonnet-4-6")

# MiniMax(OpenAI 호환) 설정 — 키가 있으면 실제 호출, 없으면 mock 으로 폴백.
_DEFAULT_MINIMAX_MODEL = getattr(_config, "MINIMAX_MODEL", None) \
    or os.environ.get("MINIMAX_MODEL", "MiniMax-M2.5")
_MINIMAX_BASE_URL = (getattr(_config, "MINIMAX_BASE_URL", None)
                     or os.environ.get("MINIMAX_BASE_URL")
                     or "https://api.minimax.io/v1").rstrip("/")


def _get_minimax_key() -> str | None:
    """MiniMax API 키를 config 또는 환경변수(MINIMAX_API_KEY)에서 읽는다."""
    if _config is not None and getattr(_config, "MINIMAX_API_KEY", None):
        return _config.MINIMAX_API_KEY  # type: ignore[attr-defined]
    return os.environ.get("MINIMAX_API_KEY")


def _resolve_mock(mock: bool | None) -> bool:
    """이 클라이언트가 mock 으로 동작해야 하는지 최종 판정한다.

    우선순위:
      1) 호출자가 mock=True/False 를 명시하면 그대로 따른다.
      2) config.is_mock() 이 있으면 그 값을 따른다(키/하드웨어 자동판정).
      3) 그 외에는 ANTHROPIC_API_KEY 환경변수 유무로 판정한다.
    """
    if mock is not None:          # (1) 명시값이 최우선
        return bool(mock)
    if _config is not None:
        # AI 전용 판정(ai_is_mock: 키 유무로만 결정)을 우선. 구버전 호환 is_mock 폴백.
        decider = getattr(_config, "ai_is_mock", None) or getattr(_config, "is_mock", None)
        if decider is not None:
            try:
                return bool(decider())  # (2) AI mock 자동판정(키 없으면 True)
            except Exception:  # pragma: no cover
                pass
    # (3) 키가 없으면 mock
    return not os.environ.get("ANTHROPIC_API_KEY")


def _get_api_key() -> str | None:
    """ANTHROPIC API 키를 config 또는 환경변수에서 읽는다."""
    if _config is not None and getattr(_config, "ANTHROPIC_API_KEY", None):
        return _config.ANTHROPIC_API_KEY  # type: ignore[attr-defined]
    return os.environ.get("ANTHROPIC_API_KEY")


def _is_ndarray(obj: Any) -> bool:
    """주어진 객체가 numpy 배열인지 안전하게 확인한다(numpy 미설치 대비)."""
    return np is not None and isinstance(obj, np.ndarray)


def _encode_image_to_base64(image: Any) -> tuple[str, str]:
    """이미지를 base64 문자열로 인코딩한다.

    반환: (media_type, base64_data)
    - image 가 파일 경로(str): 파일을 읽어 확장자로 media_type 추론.
    - image 가 ndarray: PNG 로 임시 인코딩(메모리 상에서). PIL 사용.
    """
    # (A) 파일 경로인 경우: 바이트를 그대로 읽는다.
    if isinstance(image, str):
        ext = os.path.splitext(image)[1].lower().lstrip(".")
        media = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png",
                 "gif": "gif", "webp": "webp"}.get(ext, "png")
        with open(image, "rb") as f:
            data = f.read()
        return f"image/{media}", base64.standard_b64encode(data).decode("utf-8")

    # (B) numpy 배열인 경우: PNG 로 임시 인코딩한다.
    if _is_ndarray(image):
        try:
            from PIL import Image  # 지연 import (필요할 때만)
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "ndarray 이미지를 인코딩하려면 Pillow(PIL)가 필요합니다. "
                "`pip install pillow` 후 다시 시도하세요."
            ) from exc
        buf = io.BytesIO()
        # ndarray(H,W,3) 등을 이미지로 변환해 PNG 바이트로 저장.
        Image.fromarray(image).save(buf, format="PNG")
        return "image/png", base64.standard_b64encode(buf.getvalue()).decode("utf-8")

    # (C) 그 외 타입은 지원하지 않음.
    raise TypeError(
        f"image 는 파일 경로(str) 또는 numpy.ndarray 여야 합니다. (받은 타입: {type(image).__name__})"
    )


# ──────────────────────────────────────────────────────────────────────────
# 2) Mock 백엔드 — 결정적 캔드 응답 + 호출 인자 기록
#    (하드웨어/키 없이도 차시 코드와 테스트가 끝까지 돌게 해 준다)
# ──────────────────────────────────────────────────────────────────────────
class _MockBackend:
    """모든 Mock 클라이언트의 공통 부모.

    self.calls 에 (메서드명, 인자딕셔너리) 튜플을 차곡차곡 기록한다.
    테스트에서 `client.calls[-1]` 로 마지막 호출 인자를 검사할 수 있다.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []  # 호출 기록(검수·테스트용)

    def _record(self, method: str, **kwargs: Any) -> None:
        """호출 한 건을 기록한다."""
        self.calls.append((method, kwargs))


# ──────────────────────────────────────────────────────────────────────────
# 3) LLMClient — 텍스트 대화/생성
# ──────────────────────────────────────────────────────────────────────────
class LLMClient(_MockBackend):
    """공급자무관 LLM 래퍼. 기본 공급자는 anthropic(Claude)."""

    def __init__(self, provider: str = "anthropic", model: str | None = None,
                 mock: bool | None = None, *, _http_post: Any = None) -> None:
        super().__init__()                       # self.calls 초기화
        self.provider = provider
        self._http_post = _http_post             # (minimax) 테스트용 주입 가능한 전송기
        self._client = None
        if provider == "minimax":
            # MiniMax(OpenAI 호환) — 키가 있으면 실제, 없으면 mock 으로 폴백.
            self.model = model or _DEFAULT_MINIMAX_MODEL
            self._base_url = _MINIMAX_BASE_URL
            self._api_key = _get_minimax_key()
            # mock 판정은 MINIMAX 키 유무로만(anthropic 키/라이브러리와 무관).
            self.mock = bool(mock) if mock is not None else (not self._api_key)
        else:
            # 기존 anthropic(Claude) 경로 — 동작 불변.
            self.model = model or _DEFAULT_LLM_MODEL  # 계약상 기본: claude-sonnet-4-6
            self.mock = _resolve_mock(mock) or anthropic is None
            if not self.mock:
                self._client = anthropic.Anthropic(api_key=_get_api_key())

    def complete(self, messages: list[dict], system: str = "") -> str:
        """대화 메시지 목록을 받아 모델의 답변 텍스트(str)를 돌려준다.

        messages: [{"role": "user"/"assistant", "content": "..."}] 형식.
        system  : 시스템 프롬프트(역할/말투 지시). 비어 있으면 생략.
        """
        if self.mock:
            # ── Mock: 호출 인자 기록 후 결정적 응답 생성 ──
            self._record("complete", messages=messages, system=system)
            # 마지막 사용자 발화를 추려 응답에 echo (결정적·디버깅 친화).
            last_user = ""
            for m in reversed(messages):
                if m.get("role") == "user":
                    last_user = str(m.get("content", ""))
                    break
            return f"[MOCK-LLM] system={system!r} | 마지막입력={last_user!r}"

        # ── 실제(MiniMax, OpenAI 호환 chat completions) ──
        if self.provider == "minimax":
            return self._complete_minimax(messages, system)

        # ── 실제(Claude Messages API, claude-api 스킬 가이드 준수) ──
        # adaptive thinking 권장값 사용, max_tokens 는 비스트리밍 안전값.
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system or anthropic.NOT_GIVEN,
            messages=messages,
        )
        # content 는 블록 리스트 → text 블록만 모아 이어 붙인다.
        return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")

    # -- MiniMax(OpenAI 호환) 실제 호출 -------------------------------------- #
    def _complete_minimax(self, messages: list[dict], system: str = "") -> str:
        """MiniMax 의 /chat/completions(OpenAI 호환)를 호출해 답변 텍스트를 돌려준다."""
        msgs = ([{"role": "system", "content": system}] if system else []) + list(messages)
        payload = json.dumps(
            {"model": self.model, "messages": msgs, "temperature": 0.0}
        ).encode("utf-8")
        raw = self._minimax_post(f"{self._base_url}/chat/completions", payload)
        data = json.loads(raw)
        content = str(data["choices"][0]["message"]["content"])
        # MiniMax 추론 모델(M2.x 등)은 <think>...</think> 로 사고과정을 먼저 낸다.
        # 그 안의 대괄호/예시가 다운스트림 JSON 파서를 오작동시키므로, 실제 답변만
        # 남기려고 마지막 </think> 뒤만 취한다(추론 태그 없으면 원문 그대로).
        if "</think>" in content:
            content = content.rsplit("</think>", 1)[-1]
        return content.strip()

    def _minimax_post(self, url: str, payload: bytes) -> str:
        """MiniMax 로 POST. 테스트 시 _http_post(url, payload, api_key) 주입으로 대체."""
        if self._http_post is not None:            # 테스트/대체 전송기
            return str(self._http_post(url, payload, self._api_key))
        import urllib.request

        req = urllib.request.Request(
            url, data=payload, method="POST",
            headers={"Authorization": f"Bearer {self._api_key}",
                     "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - 신뢰 엔드포인트
            return resp.read().decode("utf-8")


# ──────────────────────────────────────────────────────────────────────────
# 4) VLMClient — 이미지 설명(비전)
# ──────────────────────────────────────────────────────────────────────────
class VLMClient(_MockBackend):
    """공급자무관 VLM 래퍼. 이미지+질문 → 설명 텍스트."""

    def __init__(self, provider: str = "anthropic", model: str | None = None,
                 mock: bool | None = None) -> None:
        super().__init__()
        self.provider = provider
        self.model = model or _DEFAULT_VLM_MODEL  # 계약상 기본: claude-sonnet-4-6
        self.mock = _resolve_mock(mock) or anthropic is None
        self._client = None
        if not self.mock:
            self._client = anthropic.Anthropic(api_key=_get_api_key())

    def describe(self, image: Any, prompt: str) -> str:
        """이미지를 보고 prompt 질문에 대한 설명 텍스트(str)를 돌려준다.

        image: 파일 경로(str) 또는 numpy.ndarray(임시 인코딩) 모두 허용.
        """
        if self.mock:
            # ── Mock: 인자 기록(이미지 타입만 요약 기록) 후 결정적 응답 ──
            img_kind = "ndarray" if _is_ndarray(image) else f"path:{image}"
            self._record("describe", image=img_kind, prompt=prompt)
            return f"[MOCK-VLM] 이미지({img_kind})에 대한 설명 - 질문={prompt!r}"

        # ── 실제: 이미지를 base64 로 인코딩해 vision 메시지 구성 ──
        media_type, b64 = _encode_image_to_base64(image)
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": [
                    {  # 이미지 블록(텍스트보다 앞에 두는 것이 권장)
                        "type": "image",
                        "source": {"type": "base64",
                                   "media_type": media_type, "data": b64},
                    },
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")


# ──────────────────────────────────────────────────────────────────────────
# 5) STTClient — 음성 파일 → 텍스트
# ──────────────────────────────────────────────────────────────────────────
# 로봇 명령 도메인 어휘 힌트 — whisper 가 이 문맥으로 인식해 정확도가 오른다.
_STT_PROMPT = ("로봇 팔 제어 명령. 홈, 이동, 위로, 아래로, 왼쪽, 오른쪽, "
               "앞으로, 뒤로, 흡착, 그리퍼, 펌프, 정지, 센티미터, 밀리미터.")


class STTClient(_MockBackend):
    """공급자무관 STT 래퍼(로컬 whisper).

    백엔드는 둘 중 가용한 것을 자동 선택한다:
      - faster-whisper(있으면 우선): CTranslate2 기반, 같은 정확도로 빠르고 가벼움 →
        medium/large 를 CPU 에서도 현실적으로 사용.
      - openai-whisper: 순정 구현(폴백).
    둘 다 없으면 mock 으로 동작한다.
    """

    def __init__(self, provider: str = "whisper", mock: bool | None = None,
                 model_name: str | None = None) -> None:
        super().__init__()
        self.provider = provider
        # STT 는 API 키가 아니라 whisper 계열 라이브러리 설치 여부로 판정한다.
        _has_stt = (_FasterWhisperModel is not None) or (whisper is not None)
        self.mock = (mock if mock is not None else False) or (not _has_stt)
        # config 강제 mock 도 반영(키/하드웨어 자동판정).
        if mock is None and _config is not None and hasattr(_config, "is_mock"):
            try:
                self.mock = self.mock or bool(_config.is_mock())
            except Exception:  # pragma: no cover
                pass
        # 모델 크기: 인자 > config.WHISPER_MODEL > 환경변수 > 기본 "medium".
        # (small/base 는 한국어 정확도가 낮음. faster-whisper 면 medium 도 충분히 빠르다.)
        self.model_name = (
            model_name
            or getattr(_config, "WHISPER_MODEL", None)
            or os.environ.get("WHISPER_MODEL")
            or "medium"
        )
        self.backend = None        # "faster" | "openai" | None(mock)
        self._model = None         # 지연 로드될 모델
        if not self.mock:
            if _FasterWhisperModel is not None:
                # int8 양자화로 CPU 에서 빠르게. GPU 가 있으면 자동으로 활용된다.
                self._model = _FasterWhisperModel(
                    self.model_name, device="auto", compute_type="int8")
                self.backend = "faster"
            else:
                self._model = whisper.load_model(self.model_name)
                self.backend = "openai"

    def _resolve_audio(self, audio_path: str):
        """가능하면 WAV 를 직접 배열로 읽어 ffmpeg 의존을 없앤다.

        whisper 계열은 기본적으로 ffmpeg 로 오디오를 로드한다(Windows 에서 ffmpeg
        미설치 시 FileNotFoundError [WinError 2]). A1 녹음은 16kHz mono WAV 이므로
        직접 float32 배열로 읽어 넘기면 ffmpeg 없이 인식된다. 실패하면 경로로 폴백.
        """
        if str(audio_path).lower().endswith(".wav"):
            try:
                pass
                data, rate = load_wav_float32(audio_path)
                if rate == 16000:
                    return data
            except Exception:
                pass
        return audio_path

    def transcribe(self, audio_path: str) -> str:
        """음성 파일 경로를 받아 인식된 텍스트(str)를 돌려준다."""
        if self.mock:
            # ── Mock: 인자 기록 후 결정적 응답 ──
            self._record("transcribe", audio_path=audio_path)
            return f"[MOCK-STT] {audio_path!r} 음성을 텍스트로 변환한 결과입니다."

        audio_input = self._resolve_audio(audio_path)

        if self.backend == "faster":
            # faster-whisper: 세그먼트 이터레이터를 이어붙인다.
            segments, _info = self._model.transcribe(
                audio_input,
                language="ko",
                condition_on_previous_text=False,
                initial_prompt=_STT_PROMPT,
            )
            return "".join(seg.text for seg in segments).strip()

        # openai-whisper 폴백.
        result = self._model.transcribe(
            audio_input,
            language="ko",
            fp16=False,
            condition_on_previous_text=False,
            initial_prompt=_STT_PROMPT,
        )
        return str(result.get("text", "")).strip()


# ──────────────────────────────────────────────────────────────────────────
# 6) 자가 데모 — mock 으로 LLM/VLM/STT 각각 1회 호출
#    (하드웨어·키 없이 `python ai_clients.py` 로 동작 확인 가능)
# ──────────────────────────────────────────────────────────────────────────



# ==============================================================================
# ── common/calibration.py
# ==============================================================================

# -*- coding: utf-8 -*-
"""common/calibration.py — 카메라 픽셀 → 로봇 좌표(mm) 4점 호모그래피 캘리브레이션.

목적
----
H1 VLA 확장(vision_pick/vision_place)의 좌표 변환 계층. Qwen3-VL 이 돌려준
"화면 픽셀 좌표"를 로봇팔이 이해하는 "작업평면 mm 좌표"로 바꾼다.
GUI 캘리브레이션 마법사가 (픽셀, 로봇) 대응쌍 4개 이상을 등록하면
DLT(Direct Linear Transform) 호모그래피를 **순수 numpy** SVD 로 푼다(cv2 금지).

수학 배경(교육용 요약)
----------------------
평면→평면 사영변환(호모그래피) H(3×3)는 [px, py, 1]·Hᵀ → [x', y', w] 에서
(x'/w, y'/w) 가 로봇 좌표가 된다. 대응쌍 하나당 방정식 2줄이 나오므로
미지수 8개(스케일 제외)를 풀려면 최소 4쌍이 필요하다. 쌍이 더 많으면
최소제곱 해(SVD 최소 특이벡터)가 되어 잡음에 강해진다.

핵심 원칙 (ADR-0004, 무하드웨어)
--------------------------------
- numpy 가 없어도 **import 는 절대 죽지 않는다**(solve 만 numpy 필요).
  pixel_to_robot/save/load 는 순수 파이썬으로 동작한다.
- config.py 에 CALIB_PATH 가 아직 없어도 방어적으로 기본 경로를 쓴다.

사용법
------
    from common.calibration import Calibration, DEFAULT_CALIB_PATH

    calib = Calibration()
    calib.add_pair((100, 100), (200, -50))   # (픽셀 xy) ↔ (로봇 mm xy)
    ... 4쌍 이상 등록 ...
    report = calib.solve()                    # {"mean_err_mm":.., "max_err_mm":..}
    rx, ry = calib.pixel_to_robot(320, 240)   # 픽셀 → 로봇 mm
    calib.save(DEFAULT_CALIB_PATH)
    calib2 = Calibration.load(DEFAULT_CALIB_PATH)   # H 포함 시 즉시 is_solved

자가 데모: python -m common.calibration  (합성 쌍으로 solve→변환→저장/복원 시연)
"""

import json
import math
import os
import sys
from typing import Any

# sys.path 부트스트랩 — 단독 실행(python common/calibration.py)에서도
# `from common import ...` 가 되도록 코드 루트(taskB_curriculum)를 추가.
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:  # pragma: no cover - reconfigure 미지원 환경
    pass

# ──────────────────────────────────────────────────────────────────────────
# 안전한 의존성 import — 없으면 폴백 (import 자체는 절대 실패하지 않음)
# ──────────────────────────────────────────────────────────────────────────
try:
    import numpy as np  # DLT 행렬 SVD 에만 사용
    _HAS_NUMPY = True
except Exception:  # pragma: no cover - numpy 미설치 환경 폴백
    np = None  # type: ignore[assignment]
    _HAS_NUMPY = False

# config: CALIB_PATH 위임. 아직 CALIB_PATH 가 없거나 config 자체가 없어도 동작.
try:
    _config = config
except Exception:  # pragma: no cover - config 미존재 시 기본 경로 사용
    _config = None  # type: ignore[assignment]

# 기본 캘리브레이션 저장 경로: config.CALIB_PATH 가 있으면 그 값,
# 없으면 <taskB_curriculum>/calibration.json (이 파일 기준 상위 폴더).
_TASKB_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CALIB_PATH: str = str(getattr(
    _config, "CALIB_PATH", os.path.join(_TASKB_ROOT, "calibration.json"),
))

__all__ = ["Calibration", "DEFAULT_CALIB_PATH"]


def _project(h: list[list[float]], px: float, py: float) -> tuple[float, float]:
    """호모그래피 H 로 픽셀 (px, py) 를 사영한다: [px,py,1]·Hᵀ → (x/w, y/w).

    solve() 의 잔차 계산과 pixel_to_robot 이 공유하는 순수 함수.
    예외: w≈0 (픽셀이 소실선 위) → RuntimeError — 물리적으로 잘못된
          캘리브레이션 신호이므로 좌표를 지어내지 않고 멈춘다.
    """
    px, py = float(px), float(py)
    w = h[2][0] * px + h[2][1] * py + h[2][2]
    if abs(w) < 1e-12:
        raise RuntimeError(
            "호모그래피 특이점(w≈0)입니다 — 캘리브레이션을 다시 하세요.")
    x = (h[0][0] * px + h[0][1] * py + h[0][2]) / w
    y = (h[1][0] * px + h[1][1] * py + h[1][2]) / w
    return (float(x), float(y))


class Calibration:
    """4점(이상) 대응쌍으로 픽셀→로봇 호모그래피를 푸는 캘리브레이터.

    속성
    ----
    pairs : list[tuple[tuple[float, float], tuple[float, float]]]
        [((px, py), (rx, ry)), ...] — 등록된 (픽셀, 로봇 mm) 대응쌍.
    """

    def __init__(self) -> None:
        # 대응쌍: [((px, py), (rx, ry)), ...]
        self.pairs: list[tuple[tuple[float, float], tuple[float, float]]] = []
        # 풀린 호모그래피(행 우선 3×3). None 이면 미해결 상태.
        # 순수 파이썬 리스트로 보관 → numpy 없이도 변환/저장/복원 가능.
        self._H: list[list[float]] | None = None

    # ------------------------------------------------------------------ #
    # 대응쌍 관리
    # ------------------------------------------------------------------ #
    def add_pair(self, pixel_xy: tuple[float, float],
                 robot_xy: tuple[float, float]) -> None:
        """(픽셀 xy, 로봇 mm xy) 대응쌍 하나를 등록한다.

        새 쌍이 들어오면 기존 해(H)는 더 이상 유효하지 않으므로 무효화한다
        (다시 solve() 해야 is_solved 가 True 가 된다).
        """
        px, py = float(pixel_xy[0]), float(pixel_xy[1])
        rx, ry = float(robot_xy[0]), float(robot_xy[1])
        self.pairs.append(((px, py), (rx, ry)))
        self._H = None  # 데이터가 바뀌었으니 기존 해 무효화

    def clear(self) -> None:
        """등록된 대응쌍과 풀린 해를 모두 지운다(마법사 재시작용)."""
        self.pairs.clear()
        self._H = None

    @property
    def n_pairs(self) -> int:
        """등록된 대응쌍 개수."""
        return len(self.pairs)

    @property
    def is_solved(self) -> bool:
        """호모그래피가 풀려 pixel_to_robot 을 쓸 수 있는 상태인지."""
        return self._H is not None

    # ------------------------------------------------------------------ #
    # DLT 호모그래피 풀기 (순수 numpy SVD — cv2 불필요)
    # ------------------------------------------------------------------ #
    def solve(self) -> dict[str, float]:
        """등록쌍으로 DLT 호모그래피를 풀고 재투영 잔차 리포트를 돌려준다.

        각 쌍 ((u,v),(x,y)) 은 아래 두 방정식(2N×9 행렬의 두 행)을 만든다:
            [u, v, 1, 0, 0, 0, -x·u, -x·v, -x] · h = 0
            [0, 0, 0, u, v, 1, -y·u, -y·v, -y] · h = 0
        h(9) 는 SVD 의 최소 특이값 우측 특이벡터(= 최소제곱 해)로 구한다.

        반환: {"mean_err_mm": 평균 재투영 오차, "max_err_mm": 최대 재투영 오차}
        예외: n_pairs < 4 → ValueError("... 4점 필요 ..."),
              numpy 미설치 → RuntimeError(친절 안내),
              대응쌍 배치 퇴화(일직선/중복 등) → RuntimeError.
        실패 시 self._H 는 반드시 None 으로 남는다(is_solved=False) —
        잘못 풀린 H 로 로봇이 움직이는 일이 없게 한다("모르면 멈춘다").
        """
        if self.n_pairs < 4:
            raise ValueError(
                f"호모그래피를 풀려면 최소 4점 필요 (현재 {self.n_pairs}점)")
        if not _HAS_NUMPY:
            raise RuntimeError(
                "numpy 가 없어 캘리브레이션을 풀 수 없습니다. "
                "`pip install numpy` 후 다시 시도하세요.")

        # 2N×9 DLT 행렬 구성
        rows: list[list[float]] = []
        for (u, v), (x, y) in self.pairs:
            rows.append([u, v, 1.0, 0.0, 0.0, 0.0, -x * u, -x * v, -x])
            rows.append([0.0, 0.0, 0.0, u, v, 1.0, -y * u, -y * v, -y])
        a = np.asarray(rows, dtype=np.float64)

        # SVD: 최소 특이값의 우측 특이벡터가 ‖A·h‖ 최소화 해
        _, sv, vt = np.linalg.svd(a)
        # 퇴화 감지: 유일해가 존재하려면 rank(A)=8 이어야 한다. 4점이 일직선에
        # 가깝거나 겹치면 널공간이 2차원 이상이 되어 8번째 특이값이 0 으로
        # 무너진다(실측: 정상 배치 sv[7]/sv[0]≈1e-6, 일직선 ≤1e-17).
        # (h=vt[-1] 은 SVD 단위벡터라 norm(h)==1 — norm 검사로는 못 잡는다.)
        if float(sv[7]) <= 1e-9 * float(sv[0]):
            raise RuntimeError(
                "대응쌍 배치가 퇴화했습니다(4점이 한 직선에 가깝거나 겹침) — "
                "점 배치를 넓게 바꿔 다시 캘리브레이션하세요.")
        hm = vt[-1].reshape(3, 3)
        # 보기 좋게 H[2][2]=1 로 정규화(0 에 가까우면 스케일만 유지)
        if abs(float(hm[2, 2])) > 1e-12:
            hm = hm / hm[2, 2]
        cand = [[float(hm[i, j]) for j in range(3)] for i in range(3)]

        # 등록쌍 재투영 잔차(등록 데이터가 얼마나 잘 맞았는지 → GUI 표시용).
        # 후보 H(cand) 로 계산이 **전부 성공한 뒤에만** self._H 로 채택한다 —
        # 등록쌍이 소실선 위에 있으면(_project 의 w≈0) 해를 남기지 않고 중단.
        errs: list[float] = []
        try:
            for (u, v), (x, y) in self.pairs:
                rx, ry = _project(cand, u, v)
                errs.append(math.hypot(rx - x, ry - y))
        except RuntimeError:
            self._H = None  # 실패한 해가 is_solved/save 로 새지 않게 확정 무효화
            raise
        self._H = cand
        return {
            "mean_err_mm": float(sum(errs) / len(errs)),
            "max_err_mm": float(max(errs)),
        }

    # ------------------------------------------------------------------ #
    # 좌표 변환 (순수 파이썬 — numpy 불필요)
    # ------------------------------------------------------------------ #
    def pixel_to_robot(self, px: float, py: float) -> tuple[float, float]:
        """픽셀 좌표 (px, py) → 로봇 작업평면 좌표 (x, y) mm.

        [px, py, 1] 에 H 를 곱해 (x/w, y/w) 로 사영한다.
        예외: 미해결(is_solved=False) → RuntimeError.
        """
        if self._H is None:
            raise RuntimeError(
                "캘리브레이션이 풀리지 않았습니다 — solve() 또는 load() 를 먼저 하세요.")
        return _project(self._H, px, py)

    # ------------------------------------------------------------------ #
    # 저장/복원 (JSON — 순수 파이썬)
    # ------------------------------------------------------------------ #
    def save(self, path: str) -> None:
        """대응쌍과 (풀렸다면) H 를 JSON 으로 저장한다.

        형식: {"pairs": [[[px,py],[rx,ry]], ...], "H": [[..]*3] | null}
        """
        data: dict[str, Any] = {
            "pairs": [[[px, py], [rx, ry]] for (px, py), (rx, ry) in self.pairs],
            "H": self._H,  # 미해결이면 null 로 저장(상태 그대로 왕복)
        }
        parent = os.path.dirname(os.path.abspath(path))
        if parent:  # 하위 폴더가 없으면 만들어 준다(교실 PC 첫 실행 대비)
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str) -> "Calibration":
        """save() 가 만든 JSON 을 읽어 Calibration 을 복원한다.

        H 가 포함돼 있으면 즉시 is_solved=True (재-solve 불필요).
        파일이 없으면 FileNotFoundError 가 그대로 전파된다(호출측 판단).
        """
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        calib = cls()
        for item in data.get("pairs") or []:
            (px, py), (rx, ry) = item[0], item[1]
            calib.add_pair((float(px), float(py)), (float(rx), float(ry)))
        h = data.get("H")
        if h is not None:
            # add_pair 가 해를 무효화하므로 반드시 쌍 등록 '후' 에 H 를 복원한다.
            calib._H = [[float(h[i][j]) for j in range(3)] for i in range(3)]
        return calib


# ──────────────────────────────────────────────────────────────────────────
# 자가 데모 — 합성 대응쌍으로 solve → 변환 → 저장/복원 (무하드웨어)
# ──────────────────────────────────────────────────────────────────────────



# ==============================================================================
# ── common/grounding.py
# ==============================================================================

# -*- coding: utf-8 -*-
"""common/grounding.py — 시각 그라운딩(자연어 지칭 → 픽셀 좌표) 클라이언트.

목적
----
H1 VLA 확장("카메라에 보이는 것 집어줘")의 **눈** 역할. 카메라 프레임과
자연어 타깃("빨간 블록")을 받아, 그 물체 중심의 **픽셀 좌표**를 돌려준다.
백엔드는 로컬 Qwen3-VL 2B(llama.cpp llama-server, OpenAI 호환 API)이며,
좌표 규약은 0–1000 정규화 ``{"point_2d": [x, y]}`` (2026-07-14 실측 벤치 확정).

핵심 안전장치 (교육용·무하드웨어 원칙, ai_clients.py 패턴)
----------------------------------------------------------
- 서버/모델/키가 없어도 import 와 실행이 절대 죽지 않는다.
  CURRICULUM_FORCE_MOCK=1 또는 provider="mock"(또는 mock=True) 이면
  결정적 MockGrounding 백엔드로 폴백한다.
- 실모드에서도 서버없음/타임아웃/파싱실패는 예외 없이 ``None`` 을 반환한다
  ("모르면 멈춘다" — 상위 resolve 단계가 안전하게 중단).
- HTTP 는 urllib 만 사용하고, 테스트용 ``_http_post``/``_http_get`` 주입
  슬롯을 둔다(ai_clients 의 MiniMax 경로와 동일한 스텁 방식).

좌표 파싱 함정(실측 회귀)
-------------------------
응답에서 정규식으로 숫자만 뽑으면 키 이름 ``point_2d`` 의 '2' 가 잡힌다.
→ ``parse_point_xy`` 는 **대괄호 안 숫자쌍을 최우선**으로 파싱한다.

사용법
------
    from common.grounding import GroundingClient, ensure_server

    proc = ensure_server()               # 로컬 llama-server 보장(이미 떠 있으면 None)
    g = GroundingClient()                # 서버 없으면 자동 mock
    xy = g.point(frame, "빨간 블록")     # (px, py) 픽셀 | None

이 파일을 직접 실행하면(python -m common.grounding) mock 자가 데모가 돈다.
"""


import base64
import hashlib
import json
import os
import re
import struct
import subprocess
import time
import urllib.request
import zlib
from typing import Any, cast
from urllib.parse import urlsplit

# ──────────────────────────────────────────────────────────────────────────
# 1) 의존성 import — 없으면 None 으로 두고, 이후 mock 으로 폴백한다.
# ──────────────────────────────────────────────────────────────────────────
try:
    import numpy as np  # 프레임(ndarray) 처리용 — 없어도 import 는 성공해야 함
except Exception:  # pragma: no cover - 미설치 환경 폴백
    np = None  # type: ignore[assignment]

try:
    _config = config
except Exception:  # pragma: no cover - config 미존재/단독 실행 시
    _config = None  # type: ignore[assignment]


# ──────────────────────────────────────────────────────────────────────────
# 2) 상수 — 기본 엔드포인트/모델 경로는 config 위임(없으면 아래 기본값)
# ──────────────────────────────────────────────────────────────────────────
QWEN_CHAT_URL_DEFAULT = "http://127.0.0.1:8123/v1"  # config.GROUNDING_URL 위임

# 이 파일(common/) 기준 커리큘럼 루트(taskB_curriculum) — models/ 기본 경로 계산용.
_TASKB_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 그라운딩 시스템 프롬프트 — JSON 한 개만, 0-1000 정규화 좌표 명시(실측 벤치 검증).
_GROUNDING_SYSTEM = (
    "You are a visual grounding assistant. Locate the requested object in the image "
    'and reply with ONLY a JSON object: {"point_2d": [x, y]} — the center point of '
    "the object, in 0-1000 normalized coordinates. No other text."
)

__all__ = [
    "QWEN_CHAT_URL_DEFAULT", "GroundingClient", "MockGrounding",
    "parse_point_xy", "ensure_server",
]


def _cfg(name: str, default: str) -> str:
    """config 의 문자열 상수를 읽는다(없으면 default)."""
    val = getattr(_config, name, None) if _config is not None else None
    return str(val) if val else default


def _force_mock() -> bool:
    """그라운딩의 mock 자동판정 — **CURRICULUM_FORCE_MOCK 만** 본다.

    주의: config.is_mock() 을 쓰면 안 된다. 그건 ANTHROPIC_API_KEY 부재로도 True 가
    되는데, 그라운딩은 Anthropic 이 아니라 로컬 Qwen 서버(llama-server)를 쓴다. 교실
    PC 는 대개 Anthropic 키가 없으므로(두뇌는 MiniMax), config.is_mock() 을 따르면
    실제 Qwen 눈이 항상 mock 으로 죽어 vision 명령이 실기에서 영구 거부된다.
    서버 미가동 시의 폴백은 point() 가 None 을 돌려주는 것으로 이미 처리된다.
    """
    val = os.environ.get("CURRICULUM_FORCE_MOCK", "").strip().lower()
    return val in ("1", "true", "yes", "on")


def _frame_hw(frame: Any) -> tuple[int, int]:
    """프레임의 (H, W). shape 가 없으면 교육용 기본 해상도(480, 640)."""
    try:
        return int(frame.shape[0]), int(frame.shape[1])
    except Exception:
        return (480, 640)


# ──────────────────────────────────────────────────────────────────────────
# 3) 좌표 파싱 — 대괄호 숫자쌍 우선 (순수함수, pytest 대상)
# ──────────────────────────────────────────────────────────────────────────
def parse_point_xy(text: str) -> tuple[float, float] | None:
    """VLM 응답 텍스트에서 좌표쌍 (x, y) 를 추출한다. 실패 시 None.

    1순위: 대괄호 안의 숫자쌍 ``[x, y]`` — 키 이름 ``point_2d`` 의 '2' 가
           숫자로 잘못 잡히는 함정(실측)을 회피한다.
    2순위: 키 이름(point_2d/bbox_2d 등)을 지운 뒤 남은 숫자 2개.
    여분 텍스트/코드펜스가 섞여 있어도 동작한다.
    """
    if not text:
        return None
    m = re.search(r"\[\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)", text)
    if m:
        return float(m.group(1)), float(m.group(2))
    cleaned = re.sub(r"point_2d|bbox_2d|point2d|_2d", "", text)
    nums = re.findall(r"-?\d+(?:\.\d+)?", cleaned)
    if len(nums) < 2:
        return None
    return float(nums[0]), float(nums[1])


# ──────────────────────────────────────────────────────────────────────────
# 4) 프레임 → PNG base64 인코딩 (PIL 있으면 사용, 없으면 순수 zlib 폴백)
# ──────────────────────────────────────────────────────────────────────────
def _png_bytes_pure(frame: Any) -> bytes:
    """순수 표준 라이브러리(zlib/struct) PNG 인코더 — RGB 8bit, 필터 0.

    PIL/opencv 가 없는 교실 PC에서도 실서버 경로가 동작하도록 하는 폴백.
    """
    arr = frame
    if np is not None:
        arr = np.ascontiguousarray(arr, dtype=np.uint8)
    h, w = int(arr.shape[0]), int(arr.shape[1])
    # 각 스캔라인 앞에 필터 타입 0(없음) 바이트를 붙인다.
    raw = b"".join(b"\x00" + arr[y].tobytes() for y in range(h))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)  # 8bit / color type 2 = RGB
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _encode_png_b64(frame: Any) -> str:
    """HxWx3 uint8 RGB ndarray → PNG base64 문자열."""
    try:
        import io  # 지연 import (PIL 경로에서만 필요)

        from PIL import Image
        buf = io.BytesIO()
        Image.fromarray(frame).save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        # PIL 미설치/실패 → 순수 zlib PNG 인코더로 폴백
        return base64.b64encode(_png_bytes_pure(frame)).decode("ascii")


# ──────────────────────────────────────────────────────────────────────────
# 5) MockGrounding — 결정적 좌표 생성기 (무서버 데모/테스트용 백엔드)
# ──────────────────────────────────────────────────────────────────────────
class MockGrounding:
    """GroundingClient(provider="mock") 의 내부 백엔드.

    - set_point 로 등록한 target 은 그 정규화(0..1) 좌표를 돌려준다.
    - 미등록 target 은 문자열 sha256 해시 기반의 **결정적** 좌표(0.1~0.9)를
      돌려준다(같은 target → 항상 같은 좌표, 프로세스 무관).
    """

    def __init__(self) -> None:
        self._points: dict[str, tuple[float, float]] = {}

    def set_point(self, target: str, norm_xy: tuple[float, float]) -> None:
        """target 의 정규화(0..1) 좌표를 등록한다(테스트/GUI 데모용)."""
        self._points[str(target)] = (float(norm_xy[0]), float(norm_xy[1]))

    def point_norm(self, target: str) -> tuple[float, float]:
        """등록값 우선, 미등록이면 해시 기반 결정적 정규화 좌표."""
        key = str(target)
        if key in self._points:
            return self._points[key]
        digest = hashlib.sha256(key.encode("utf-8")).digest()
        nx = 0.1 + 0.8 * (digest[0] / 255.0)   # 프레임 가장자리(0/1)는 피한다
        ny = 0.1 + 0.8 * (digest[1] / 255.0)
        return (nx, ny)

    def point(self, frame: Any, target: str) -> tuple[float, float] | None:
        """프레임 크기에 맞춘 픽셀 좌표. frame 이 None 이면 None."""
        if frame is None:
            return None
        h, w = _frame_hw(frame)
        nx, ny = self.point_norm(target)
        return (nx * w, ny * h)


# ──────────────────────────────────────────────────────────────────────────
# 6) GroundingClient — 자연어 target → 프레임 픽셀 좌표
# ──────────────────────────────────────────────────────────────────────────
class GroundingClient:
    """시각 그라운딩 클라이언트 (qwen-local 실서버 | mock 폴백).

    파라미터
    --------
    provider : "qwen-local"(기본) | "mock"(강제 mock 백엔드).
               기본값("qwen-local") 그대로 두면 config.GROUNDING_PROVIDER 에
               위임한다 — GROUNDING_PROVIDER=mock 환경변수/설정이 실제로
               반영된다(명시 인자가 있으면 그 값이 우선).
    endpoint : OpenAI 호환 베이스 URL(예: http://127.0.0.1:8123/v1).
               None 이면 config.GROUNDING_URL → QWEN_CHAT_URL_DEFAULT.
    mock     : True/False 명시 시 최우선. None 이면 config.is_mock() 자동판정.
    timeout  : HTTP 타임아웃(초). 새 장면 추론이 ~6s(실측)라 기본 120s.
    _http_post/_http_get : 테스트용 주입 슬롯(ai_clients 패턴).
    """

    def __init__(self, provider: str = "qwen-local", endpoint: str | None = None,
                 mock: bool | None = None, timeout: float = 120.0,
                 *, _http_post: Any = None, _http_get: Any = None) -> None:
        # 기본값이면 config.GROUNDING_PROVIDER 위임(죽은 설정 방지 — 문서화된
        # 스위치 GROUNDING_PROVIDER=mock 이 조용히 무시되지 않게 한다).
        if provider == "qwen-local":
            provider = _cfg("GROUNDING_PROVIDER", "qwen-local")
        self.provider = provider
        self.timeout = float(timeout)
        self.endpoint = (endpoint or _cfg("GROUNDING_URL", QWEN_CHAT_URL_DEFAULT)).rstrip("/")
        self.calls: list[dict[str, Any]] = []  # 호출 기록(검수·테스트용)
        self._http_post = _http_post         # 테스트용 주입 가능한 전송기(POST)
        self._http_get = _http_get           # 테스트용 주입 가능한 전송기(GET/health)
        self.mock_backend = MockGrounding()  # mock 시 좌표 공급원(set_point 대상)
        # mock 판정 — provider="mock" 최우선 → 호출자 명시값 → config.is_mock().
        if provider == "mock":
            self._mock = True
        elif mock is not None:
            self._mock = bool(mock)
        else:
            self._mock = _force_mock()

    # -- 상태 ---------------------------------------------------------------- #
    @property
    def is_mock(self) -> bool:
        """mock 백엔드로 동작 중인지."""
        return self._mock

    def _health_url(self) -> str:
        """endpoint 의 호스트 기준 /health URL (…/v1 을 떼고 붙인다)."""
        parts = urlsplit(self.endpoint)
        return f"{parts.scheme}://{parts.netloc}/health"

    def is_ready(self) -> bool:
        """그라운딩 백엔드 준비 여부. mock 은 항상 True, 예외는 False."""
        if self._mock:
            return True
        return _health_ok(self._health_url(), timeout=min(self.timeout, 3.0),
                          _http_get=self._http_get)

    # -- mock 편의(등록 위임) -------------------------------------------------- #
    def set_point(self, target: str, norm_xy: tuple[float, float]) -> None:
        """mock 백엔드에 target 의 정규화(0..1) 좌표를 등록한다(데모/테스트)."""
        self.mock_backend.set_point(target, norm_xy)

    # -- 핵심: 포인팅 ----------------------------------------------------------- #
    def point(self, frame: Any, target: str) -> tuple[float, float] | None:
        """frame(HxWx3 uint8 RGB)에서 target 중심의 **픽셀 좌표**를 찾는다.

        서버없음/타임아웃/파싱실패 어떤 경우에도 예외를 던지지 않고 None 을
        반환한다("모르면 멈춘다" — 상위 resolve 단계가 안전하게 중단).
        """
        self.calls.append({"method": "point", "target": target, "mock": self._mock})
        if frame is None:
            return None
        if self._mock:
            return self.mock_backend.point(frame, target)

        h, w = _frame_hw(frame)
        try:
            b64 = _encode_png_b64(frame)
            payload = json.dumps({
                "model": "qwen3vl",
                "temperature": 0,
                "max_tokens": 80,
                "messages": [
                    {"role": "system", "content": _GROUNDING_SYSTEM},
                    {"role": "user", "content": [
                        {"type": "image_url",
                         "image_url": {"url": "data:image/png;base64," + b64}},
                        {"type": "text", "text": f"Point to: {target}"},
                    ]},
                ],
            }).encode("utf-8")
            raw = self._post(self.endpoint + "/chat/completions", payload)
            data = json.loads(raw)
            content = str(data["choices"][0]["message"]["content"])
        except Exception:
            return None  # 서버없음/타임아웃/응답형식 오류 → 조용히 None

        xy = parse_point_xy(content)
        if xy is None:
            return None  # 파싱 실패 → None
        # 0-1000 정규화 → 픽셀. 모델이 범위를 벗어나도 프레임 안으로 클램프.
        px = min(max(xy[0] / 1000.0 * w, 0.0), float(w - 1))
        py = min(max(xy[1] / 1000.0 * h, 0.0), float(h - 1))
        return (px, py)

    def _post(self, url: str, payload: bytes) -> str:
        """로컬 서버로 POST. 테스트 시 _http_post(url, payload) 주입으로 대체."""
        if self._http_post is not None:  # 테스트/대체 전송기
            return str(self._http_post(url, payload))
        req = urllib.request.Request(
            url, data=payload, method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310 - 로컬 서버
            return str(resp.read().decode("utf-8"))


# ──────────────────────────────────────────────────────────────────────────
# 7) 서버 헬스체크 + ensure_server (llama-server 기동 보장)
# ──────────────────────────────────────────────────────────────────────────
def _health_ok(url: str, timeout: float = 2.0, _http_get: Any = None) -> bool:
    """GET url 이 200 이면 True. 어떤 예외도 False (서버 부재 = 정상 상황)."""
    try:
        if _http_get is not None:  # 테스트/대체 전송기
            return bool(_http_get(url))
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 - 로컬 서버
            return int(resp.status) == 200
    except Exception:
        return False


def ensure_server(model: str | None = None, mmproj: str | None = None,
                  port: int = 8123, exe: str | None = None,
                  wait_s: float = 60.0,
                  *, _popen: Any = None, _health_check: Any = None,
                  _sleep: Any = None) -> subprocess.Popen[bytes] | None:
    """로컬 llama-server(Qwen3-VL) 가동을 보장한다.

    - 이미 ``/health`` 가 200 이면 **None** 을 반환(기존 서버 재사용).
    - 아니면 llama-server 를 기동(``-c 8192, --threads cpu-2, --no-webui``,
      실측 벤치와 동일 옵션)하고 health 가 뜰 때까지 최대 wait_s 초
      **유한 루프**로 폴링한 뒤 Popen 핸들을 반환한다.
    - 실행파일/모델 파일이 없으면 RuntimeError(친절한 안내 포함).
    - 폴링 시간 내에 준비되지 않으면 자식 프로세스를 정리하고 RuntimeError.
    - 테스트 주입: _popen(argv)→proc, _health_check(url)→bool, _sleep(sec).
      (실서버 없이 기동 경로를 검증하기 위한 스텁 슬롯)
    """
    health = _health_check if _health_check is not None else _health_ok
    sleep = _sleep if _sleep is not None else time.sleep
    health_url = f"http://127.0.0.1:{int(port)}/health"

    if health(health_url):
        return None  # 이미 떠 있음 → 재사용

    # 기본 경로: config 상수(models/ 아래, 이미 배치됨) → 하드코딩 폴백.
    model = model or _cfg("QWEN_MODEL_PATH", os.path.join(
        _TASKB_ROOT, "models", "Qwen3VL-2B-Instruct-Q4_K_M.gguf"))
    mmproj = mmproj or _cfg("QWEN_MMPROJ_PATH", os.path.join(
        _TASKB_ROOT, "models", "mmproj-Qwen3VL-2B-Instruct-Q8_0.gguf"))
    exe = exe or _cfg("LLAMA_SERVER_EXE", os.path.join(
        _TASKB_ROOT, "models", "llamacpp", "llama-server.exe"))

    missing = [p for p in (exe, model, mmproj) if not os.path.exists(p)]
    if missing:
        raise RuntimeError(
            "llama-server 를 기동할 수 없습니다 — 아래 파일이 없습니다:\n  "
            + "\n  ".join(missing)
            + "\nmodels/README.md 의 재다운로드 안내를 참고하세요."
        )

    # --threads = cpu-2 (스펙 §2b·실측 벤치와 동일 옵션): 추론 중에도 GUI/카메라
    # 스레드가 굶지 않도록 코어 2개를 남긴다(하한 1 — 저코어 교실 PC 안전).
    argv = [exe, "-m", model, "--mmproj", mmproj, "--port", str(int(port)),
            "-c", "8192", "--threads", str(max(1, (os.cpu_count() or 4) - 2)),
            "--no-webui"]
    if _popen is not None:  # 테스트/대체 실행기
        proc = cast("subprocess.Popen[bytes]", _popen(argv))
    else:
        proc = subprocess.Popen(  # noqa: S603 - 신뢰된 로컬 실행파일
            argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # health 폴링 — wait_s 초 한도의 유한 루프(0.5s 간격).
    tries = max(1, int(float(wait_s) / 0.5))
    for _ in range(tries):
        if health(health_url):
            return proc
        sleep(0.5)

    # 기동 실패 → 자식 정리 후 명확한 오류
    try:
        proc.kill()
    except Exception:  # pragma: no cover - 이미 종료된 경우 등
        pass
    raise RuntimeError(
        f"llama-server 가 {float(wait_s):.0f}s 안에 준비되지 않았습니다 (port={port}). "
        "모델 로드가 느린 PC 라면 wait_s 를 늘려 보세요."
    )


# ──────────────────────────────────────────────────────────────────────────
# 8) 자가 데모 — mock 으로 전 과정 확인 (서버/카메라/키 불필요)
# ──────────────────────────────────────────────────────────────────────────



# ==============================================================================
# ── common/motion_control.py
# ==============================================================================

# -*- coding: utf-8 -*-
"""common/motion_control.py — 자연어 → 로봇 동작 계획/실행 (색 무관, 범용).

H1(자연어 제어)·A1(음성 제어)이 공유하는 "언어 → 구조화 동작 → 안전 실행" 레이어다.
색 판별(detect_colors)에 의존하지 않으며, 명령을 아래 **고정 스키마의 동작 리스트**로
바꾼 뒤 RobotController 로 순차 실행한다. (색 인식은 M1 전용이므로 여기엔 없음.)

동작 스키마(각 항목은 dict):
    {"action": "home"}
    {"action": "move_to", "x": .., "y": .., "z": .., "r": ..}       # 절대 이동(mm/deg)
    {"action": "move_relative", "dx": .., "dy": .., "dz": .., "dr": ..}  # 상대 이동
    {"action": "suck", "on": bool}     # 흡착 on/off
    {"action": "grip", "on": bool}     # 그리퍼 close/open
    {"action": "speed", "velocity": .., "acceleration": ..}  # (지원 시) 속도%
    {"action": "vision_pick", "target": "<명사구>"}    # 카메라에 보이는 물체 집기(치환 필요)
    {"action": "vision_place", "target": "<명사구>"}   # 보이는 위치 옆/위에 내려놓기(치환 필요)
    {"action": "unknown", "reason": ".."}

vision_pick/vision_place 는 그대로 실행할 수 없는 **지연 액션**이다 —
resolve_vision_actions() 가 카메라 프레임(눈: GroundingClient)과 4점 캘리브레이션
(common.calibration)으로 좌표 액션 시퀀스(move_to→move_to→suck→move_to)로 치환한다.
치환 단계가 하나라도 확신이 없으면("모르면 멈춘다") 전체를 중단한다.

해석 경로:
  - 실제(non-mock) LLM(예: MiniMax) 주입 시 → LLM 이 JSON 배열 출력 → 견고 파싱(+1회 재질문).
  - 아니면(기본) → 로컬 규칙 파서(키/인터넷 불필요, 다단계 명령 분해).
방향 규약: 오른쪽 +Y / 왼쪽 -Y / 앞 +X / 뒤 -X / 위 +Z / 아래 -Z.
"""

import json
import re
from typing import Any

pass

# config: VISION_Z_HOVER/VISION_Z_PICK/EFFECTOR 상수 위임. 없어도 기본값으로 동작(방어적).
try:
    _config = config
except Exception:  # pragma: no cover - config 미존재/단독 실행 시
    _config = None  # type: ignore[assignment]


def _check_move(x: float, y: float, z: float) -> tuple[bool, str]:
    """safety.check_move 위임(없으면 항상 안전으로 폴백 — import는 안 죽는다)."""
    try:
        pass
        ok, msg = check_move(x, y, z)
        return bool(ok), str(msg)
    except Exception:  # pragma: no cover - safety 미존재 시 방어
        return True, "안전(safety 미탑재)"

# 로봇 좌표계 방향 → 상대이동 축·부호(mm 단위 계수).
_DIRECTION_AXIS = {
    "right": ("dy", +1.0), "left": ("dy", -1.0),
    "forward": ("dx", +1.0), "back": ("dx", -1.0),
    "up": ("dz", +1.0), "down": ("dz", -1.0),
}
_DIRECTION_WORDS = {
    "right": ("오른", "우측", "right"), "left": ("왼", "좌측", "left"),
    "forward": ("앞", "전진", "forward"), "back": ("뒤", "후진", "back"),
    "up": ("위로", "위", "올려", "up"), "down": ("아래", "내려", "down"),
}
_HOME_WORDS = ("홈", "원점", "처음 위치", "처음위치", "home")
_STOP_WORDS = ("정지", "멈춰", "멈춤", "스톱", "stop")
_GRIP_WORDS = ("그리퍼", "집게")
_ON_WORDS = ("켜", "집", "붙", "빨", "닫", "쥐", "on")
_OFF_WORDS = ("놓", "떼", "풀", "열", "벌", "꺼", "끄", "해제", "off")
# 복합 명령을 단계로 나누는 접속어.
_STEP_SPLIT = re.compile(
    r"\s*(?:그리고|그다음에?|그 다음에?|그 ?후에?|후에|한 뒤에?|하고 나서|하고|갔다가|갔다|가서|"
    r"간 다음|다음에?|,|→|그런 다음)\s*"
)
_CM = re.compile(r"(-?\d+(?:\.\d+)?)\s*(?:cm|센티미터|센치|센티)", re.IGNORECASE)
_MM = re.compile(r"(-?\d+(?:\.\d+)?)\s*(?:mm|밀리미터|밀리)", re.IGNORECASE)

# 비전 지칭 명령(H1 VLA §2c): "<명사구>(을|를)? 집어" / "<명사구>(에|위에|옆에) 놔".
#   맨 동사("집어"/"놓아", 명사구 없음)는 기존대로 흡착 on/off 로 남긴다.
_VISION_PICK = re.compile(r"^(.+?)\s*(?:을|를)\s*집|^(.+?)\s+집")
_VISION_PLACE = re.compile(r"^(.+?)\s*(?:위에|옆에|에)\s*(?:내려\s*)?(?:놔|놓아|놓고|놓기)")
# 방향/지시어만 남은 "명사구"는 비전 타깃이 아니다("위에 놔" → 비전 아님).
_VISION_TARGET_STOPWORDS = {
    "위", "아래", "앞", "뒤", "옆", "왼쪽", "오른쪽", "여기", "거기", "저기",
    "위로", "아래로", "제자리", "바닥",
}

MOTION_SYSTEM_PROMPT = (
    "너는 로봇팔 동작 계획기다. 사용자의 자연어 명령을 아래 스키마의 JSON 배열로만 출력한다. "
    "설명·마크다운 없이 JSON 배열만 출력하라. 복합 명령이면 순서대로 여러 동작을 배열에 담아라.\n"
    "가능한 동작:\n"
    '  {"action":"home"}\n'
    '  {"action":"move_to","x":220,"y":0,"z":40,"r":0}\n'
    '  {"action":"move_relative","dx":0,"dy":0,"dz":20,"dr":0}\n'
    '  {"action":"suck","on":true}   {"action":"grip","on":true}\n'
    '  {"action":"pump_off"}   # 공압 펌프 완전 정지(흡착만 해제가 아니라 펌프 회로 OFF)\n'
    '  {"action":"speed","velocity":50,"acceleration":50}\n'
    '  {"action":"vision_pick","target":"빨간 블록"}    # 카메라에 보이는 물체 집기\n'
    '  {"action":"vision_place","target":"컵"}          # 보이는 위치 옆/위에 내려놓기\n'
    "방향 규약: 오른쪽=+Y, 왼쪽=-Y, 앞=+X, 뒤=-X, 위=+Z, 아래=-Z (mm). "
    "카메라에 보이는 물체를 지칭하는 명령은 vision_pick/vision_place 로 출력하고 "
    "target 에 한국어 명사구를 그대로 담아라. "
    '예) "보이는 빨간 블록 집어" → [{"action":"vision_pick","target":"빨간 블록"}] · '
    '"지우개를 컵 옆에 놔" → [{"action":"vision_pick","target":"지우개"},'
    '{"action":"vision_place","target":"컵"}]. '
    "이해할 수 없으면 [{\"action\":\"unknown\",\"reason\":\"...\"}]."
)

__all__ = [
    "MOTION_SYSTEM_PROMPT", "normalize_action", "parse_actions_json",
    "parse_motion_local", "plan_motion", "execute_motion",
    "resolve_vision_actions",
]


# --------------------------------------------------------------------------- #
# 검증/정규화
# --------------------------------------------------------------------------- #
def _num(v: Any, default: float) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "on", "yes", "y")
    return False


def normalize_action(obj: Any) -> dict[str, Any]:
    """원시 dict 를 검증된 동작 dict 로. 실패 시 {'action':'unknown',...}."""
    if not isinstance(obj, dict) or not isinstance(obj.get("action"), str):
        return {"action": "unknown", "reason": "형식 오류"}
    a = obj["action"].strip().lower()
    if a == "home":
        return {"action": "home"}
    if a == "pump_off":
        return {"action": "pump_off"}
    if a == "move_to":
        return {"action": "move_to", "x": _num(obj.get("x"), 0.0), "y": _num(obj.get("y"), 0.0),
                "z": _num(obj.get("z"), 0.0), "r": _num(obj.get("r"), 0.0)}
    if a == "move_relative":
        return {"action": "move_relative", "dx": _num(obj.get("dx"), 0.0),
                "dy": _num(obj.get("dy"), 0.0), "dz": _num(obj.get("dz"), 0.0),
                "dr": _num(obj.get("dr"), 0.0)}
    if a in ("suck", "grip"):
        return {"action": a, "on": _bool(obj.get("on"))}
    if a == "speed":
        return {"action": "speed", "velocity": _num(obj.get("velocity"), 100.0),
                "acceleration": _num(obj.get("acceleration"), 100.0)}
    if a in ("vision_pick", "vision_place"):
        target = str(obj.get("target") or "").strip()
        if not target:  # target 이 비면 unknown 처리(H1 VLA §2c)
            return {"action": "unknown", "reason": f"{a}: target 없음"}
        return {"action": a, "target": target}
    if a == "unknown":
        return {"action": "unknown", "reason": str(obj.get("reason", "unknown"))}
    return {"action": "unknown", "reason": f"미지원 action: {a}"}


def parse_actions_json(text: str) -> list[dict[str, Any]]:
    """LLM 원문 → 검증된 동작 리스트. 예외 없이, 실패 시 []."""
    if not text:
        return []
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    cand = m.group(1) if m else text
    s, e = cand.find("["), cand.rfind("]")
    if s == -1 or e == -1 or e < s:
        return []
    try:
        data = json.loads(cand[s:e + 1])
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out = [normalize_action(it) for it in data]
    return [a for a in out if a["action"] != "unknown"]


# --------------------------------------------------------------------------- #
# 로컬 규칙 파서(무모델·무API, 다단계)
# --------------------------------------------------------------------------- #
def _distance_mm(text: str, default: float) -> float:
    m = _CM.search(text)
    if m:
        return float(m.group(1)) * 10.0
    m = _MM.search(text)
    if m:
        return float(m.group(1))
    m = re.search(r"(-?\d+(?:\.\d+)?)", text)   # 단위 없는 숫자는 mm 로 간주
    return float(m.group(1)) if m else default


def _parse_one(step: str) -> dict[str, Any] | None:
    c = step.strip()
    if not c:
        return None
    if any(w in c for w in _HOME_WORDS):
        return {"action": "home"}
    # 펌프 완전 정지: '펌프' + 끄기/정지 → 흡착 해제(suck False)가 아니라 pump_off.
    #   (suck(False) 는 진공만 풀 뿐 펌프 회로는 계속 돌기 때문)
    if "펌프" in c and (any(w in c for w in _OFF_WORDS) or "정지" in c):
        return {"action": "pump_off"}
    # 흡착/그리퍼. on/off 판정: 끄기 동사만 있으면 off, 아니면 on(맨 '흡착'도 on).
    is_grip = any(w in c for w in _GRIP_WORDS)
    has_suck = "흡착" in c or "석션" in c
    on = any(w in c for w in _ON_WORDS)
    off = any(w in c for w in _OFF_WORDS)
    if has_suck or is_grip:
        name = "grip" if is_grip else "suck"
        return {"action": name, "on": not (off and not on)}
    # 카메라에 보이는 물체 지칭(H1 VLA): "<명사구> 집어" → vision_pick,
    #   "<명사구>(에|위에|옆에) 놔" → vision_place. 맨 동사는 아래 흡착 규칙으로.
    m = _VISION_PLACE.search(c)
    if m:
        target = _vision_target(m.group(1))
        if target:
            return {"action": "vision_place", "target": target}
    m = _VISION_PICK.search(c)
    if m:
        target = _vision_target(m.group(1) or m.group(2) or "")
        if target:
            return {"action": "vision_pick", "target": target}
    if (on or off) and not _has_direction(c):   # 맨 동사 "집어"/"놓아" → 흡착
        return {"action": "suck", "on": not (off and not on)}
    # 속도
    if "속도" in c or "빠르" in c or "느리" in c:
        v = 100.0 if "빠르" in c else (30.0 if "느리" in c else 0.0)
        m = re.search(r"(\d+(?:\.\d+)?)", c)
        if m:
            v = float(m.group(1))
        if v:
            return {"action": "speed", "velocity": v, "acceleration": v}
    # 방향 상대 이동
    direction = _first_direction(c)
    if direction is not None:
        axis, sign = _DIRECTION_AXIS[direction]
        dist = _distance_mm(c, 20.0)
        act = {"action": "move_relative", "dx": 0.0, "dy": 0.0, "dz": 0.0, "dr": 0.0}
        act[axis] = sign * dist
        return act
    return {"action": "unknown", "reason": f"해석 불가: {step!r}"}


def _vision_target(raw: str) -> str:
    """비전 명령에서 추출한 명사구를 다듬는다. 빈 문자열이면 '비전 아님' 신호.

    - 접두 수식("보이는", "카메라에 보이는")은 지운다.
    - "지우개를 컵" 처럼 목적어 조사(을/를) 뒤에 참조물이 이어지면 그쪽만 남긴다
      (vision_place 의 기준 물체 추출: "지우개를 컵 옆에 놔" → "컵").
    - 방향/지시어만 남으면("위", "옆" 등) 비전 타깃이 아니므로 "" 를 돌려준다.
    """
    t = (raw or "").strip()
    t = re.sub(r"^(?:카메라에\s*)?보이는\s*", "", t)
    m = re.search(r"(?:을|를)\s+(\S.*)$", t)
    if m:
        t = m.group(1)
    t = t.strip()
    return "" if t in _VISION_TARGET_STOPWORDS else t


def _has_direction(c: str) -> bool:
    return _first_direction(c) is not None


def _first_direction(c: str) -> str | None:
    for d, words in _DIRECTION_WORDS.items():
        if any(w in c for w in words):
            return d
    return None


def parse_motion_local(command: str) -> list[dict[str, Any]]:
    """자연어 명령을 규칙으로 동작 리스트로 분해(다단계). 색 무관, 무API."""
    steps = [s for s in _STEP_SPLIT.split(command or "") if s.strip()]
    if not steps:
        return []
    out: list[dict[str, Any]] = []
    for s in steps:
        act = _parse_one(s)
        if act is not None and act["action"] != "unknown":
            out.append(act)
    return out


# --------------------------------------------------------------------------- #
# 비전 액션 치환(H1 VLA §2c) — vision_pick/vision_place → 좌표 액션 시퀀스
# --------------------------------------------------------------------------- #
_VISION_ACTIONS = ("vision_pick", "vision_place")


def _vision_z(name: str, default: float) -> float:
    """config 의 VISION_Z_* 상수(mm)를 읽는다(없으면 default). # 실측 필요(config 참조)"""
    try:
        return float(getattr(_config, name))
    except (TypeError, ValueError, AttributeError):
        return default


def resolve_vision_actions(actions: list[dict[str, Any]], frame: Any,
                           grounding: Any, calib: Any,
                           ) -> tuple[list[dict[str, Any]], list[str]]:
    """vision_pick/vision_place 를 카메라(눈)+캘리브레이션으로 좌표 액션에 치환한다.

    파라미터
    --------
    actions   : plan_motion 이 만든 동작 리스트(비전 액션 포함 가능).
    frame     : 카메라 프레임(np.ndarray HxWx3) 또는 None.
    grounding : GroundingClient/MockGrounding 규약 — point(frame, target) → (px,py)|None.
    calib     : common.calibration.Calibration 규약 — is_solved, pixel_to_robot(px,py).

    "모르면 멈춘다" — 아래 4중 중단 경로에서는 ([], [사유]) 를 반환해
    상위(run_visual_command/GUI)가 **아무 동작도 실행하지 않게** 한다:
      1) frame 이 None            → ["카메라 프레임 없음"]
      2) calib 미해결(is_solved X) → ["캘리브레이션 필요"]
      3) grounding.point 가 None  → ["'{target}' 못 찾음"]
      4) 변환 좌표가 작업영역 밖   → ["... 작업영역 밖 — 캘리브레이션을 다시 하세요"]
         (execute_motion 의 clamp 가 '조용히' 경계로 끌어당겨 엉뚱한 곳을 집는 것 방지)

    vision_* 가 없으면 (actions 그대로, []) 를 반환한다(비전 무관 경로 무변화).
    치환 시퀀스: move_to(hover) → move_to(pick 높이) → 집기(grip|suck) → move_to(hover).
    집기 명령은 config.EFFECTOR("gripper"→grip / "suction"→suck)에 맞춰 생성한다.

    반환: (치환 완료 액션 리스트, GUI/콘솔 표시용 메시지 리스트).
    """
    if not any(a.get("action") in _VISION_ACTIONS for a in actions):
        return list(actions), []
    if frame is None:
        return [], ["카메라 프레임 없음"]
    if not bool(getattr(calib, "is_solved", False)):
        return [], ["캘리브레이션 필요"]

    z_hover = _vision_z("VISION_Z_HOVER", 40.0)   # 접근(호버) 높이  # 실측 필요
    z_pick = _vision_z("VISION_Z_PICK", -40.0)    # 집기 하강 높이   # 실측 필요
    # 엔드이펙터에 맞는 집기 명령: 그리퍼면 grip, 흡착컵이면 suck (RobotController.grasp 와 동일 분기).
    grasp_action = "suck" if str(getattr(_config, "EFFECTOR", "gripper")) == "suction" else "grip"
    resolved: list[dict[str, Any]] = []
    messages: list[str] = []
    for act in actions:
        name = act.get("action")
        if name not in _VISION_ACTIONS:
            resolved.append(dict(act))
            continue
        target = str(act.get("target", ""))
        xy = grounding.point(frame, target)       # 눈: 자연어 → 픽셀 좌표
        if xy is None:
            return [], [f"'{target}' 못 찾음"]
        px, py = float(xy[0]), float(xy[1])
        try:
            rx, ry = calib.pixel_to_robot(px, py)  # 픽셀 → 로봇 작업평면 mm
        except Exception as e:                     # 특이점 등 — 실행 없이 중단
            return [], [f"좌표 변환 실패: {e}"]
        rx, ry = float(rx), float(ry)
        # 4번째 중단: 변환 좌표가 작업영역 밖이면 clamp 로 실행하지 말고 전체 중단.
        ok, why = _check_move(rx, ry, z_pick)
        if not ok:
            return [], [f"'{target}' 좌표({rx:.0f}, {ry:.0f})mm 가 작업영역 밖 "
                        f"— 캘리브레이션을 다시 하세요 ({why.splitlines()[0]})"]
        on = name == "vision_pick"
        messages.append(f"[{name}] '{target}' → 픽셀({px:.0f}, {py:.0f}) "
                        f"→ 로봇({rx:.1f}, {ry:.1f})mm")
        resolved.extend([
            {"action": "move_to", "x": rx, "y": ry, "z": z_hover, "r": 0.0},
            {"action": "move_to", "x": rx, "y": ry, "z": z_pick, "r": 0.0},
            {"action": grasp_action, "on": on},
            {"action": "move_to", "x": rx, "y": ry, "z": z_hover, "r": 0.0},
        ])
    return resolved, messages


# --------------------------------------------------------------------------- #
# 계획(LLM 우선, 로컬 폴백) + 실행
# --------------------------------------------------------------------------- #
def _is_real_llm(llm: Any) -> bool:
    return llm is not None and not getattr(llm, "mock", False) and callable(
        getattr(llm, "complete", None)
    )


def plan_motion(command: str, llm: Any = None) -> tuple[list[dict[str, Any]], str]:
    """명령 → (동작 리스트, 원문). 실제 LLM 있으면 그걸로, 없으면 로컬 규칙."""
    if _is_real_llm(llm):
        raw = llm.complete(
            messages=[{"role": "user", "content": command}], system=MOTION_SYSTEM_PROMPT
        )
        actions = parse_actions_json(raw)
        if not actions:  # 1회 재질문(self-repair)
            raw = llm.complete(
                messages=[{"role": "user",
                           "content": "이전 출력이 올바른 JSON 배열이 아니었다. JSON 배열만 다시 출력하라.\n" + command}],
                system=MOTION_SYSTEM_PROMPT,
            )
            actions = parse_actions_json(raw)
        return actions, raw
    actions = parse_motion_local(command)
    return actions, json.dumps(actions, ensure_ascii=False)


def execute_motion(actions: list[dict[str, Any]], bot: Any) -> list[str]:
    """검증된 동작 리스트를 안전검사 후 순서대로 실행. 반환: 단계별 로그."""
    logs: list[str] = []
    for act in actions:
        a = act["action"]
        try:
            if a == "home":
                bot.home()
                logs.append("[home] 원점 복귀")
            elif a == "move_to":
                cx, cy, cz, cr = safety.clamp_move(act["x"], act["y"], act["z"], act["r"])
                bot.move_to(cx, cy, cz, cr)
                logs.append(f"[move_to] ({cx},{cy},{cz},r={cr})")
            elif a == "move_relative":
                p = bot.get_pose()
                tx, ty, tz = p["x"] + act["dx"], p["y"] + act["dy"], p["z"] + act["dz"]
                tr = p.get("r", 0.0) + act["dr"]
                cx, cy, cz, cr = safety.clamp_move(tx, ty, tz, tr)
                bot.move_to(cx, cy, cz, cr)
                logs.append(f"[move_relative] → ({cx},{cy},{cz})")
            elif a in ("suck", "grip"):
                getattr(bot, a)(act["on"])
                logs.append(f"[{a}] {'ON' if act['on'] else 'OFF'}")
            elif a == "pump_off":
                fn = getattr(bot, "pump_off", None)
                if callable(fn):
                    fn()
                    logs.append("[pump_off] 공압 펌프 완전 정지(isCtrlEnabled=0)")
                else:  # 폴백: 최소한 흡착 해제
                    getattr(bot, "suck", lambda _v: None)(False)
                    logs.append("[pump_off] pump_off 미지원 — 흡착 해제로 대체")
            elif a == "speed":
                fn = getattr(bot, "speed", None)
                if callable(fn):
                    fn(act["velocity"], act["acceleration"])
                    logs.append(f"[speed] v={act['velocity']} a={act['acceleration']}")
                else:
                    logs.append("[speed] 이 로봇은 속도 설정 미지원 — 생략")
            else:
                logs.append(f"[건너뜀] 알 수 없는 동작: {a}")
        except Exception as e:  # 실행 예외는 로그로만(파이프라인 중단 방지)
            logs.append(f"[오류] {a}: {e}")
    return logs



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
# ── common/gui.py
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
# ── h1_vlm_nl_control/solution.py
# ==============================================================================

# -*- coding: utf-8 -*-
"""H1 · 자연어로 로봇 제어 (범용 동작, 색 무관) · [모범답안]

차시 목표
---------
"홈으로 복귀", "오른쪽으로 5cm 이동", "위로 20mm", "흡착 켜" 같은 **자연어 명령**을
받아 로봇이 스스로 수행한다. VLA(Vision-Language-Action)의 Language→Action 실용 패턴:

    [자연어 명령] --(LLM/규칙)--> 구조화 동작 JSON
        예) [{"op 아님, action":"move_relative","dy":80}, {"action":"home"}]
    --safety 검사(작업영역 클램프)--> --dobot 실행--> (위험하면 보정/중단)

설계 원칙
---------
- **색 판별은 이 차시에 없다.** 색 인식(detect_colors)은 M1(색상 분류) 전용이다.
  H1 은 좌표·방향·홈·엔드이펙터 같은 **범용 동작**을 자연어로 제어한다.
- 언어 해석은 **MiniMax(OpenAI 호환) LLM** 으로 한다. MINIMAX_API_KEY 가 없으면
  LLMClient 가 mock 이 되어 **로컬 규칙 파서**(common.motion_control)로 폴백한다
  (키·인터넷 없이도 차시가 끝까지 동작).
- 스키마/파서/실행은 공통 레이어 common.motion_control 을 재사용한다(중복 구현 금지).
- **VLA 확장(vision_pick)**: "빨간 블록 집어"처럼 카메라에 보이는 물체를 지칭하면
  run_visual_command 가 눈(GroundingClient, 로컬 Qwen3-VL | mock)과 4점 캘리브레이션
  (common.calibration)으로 좌표를 알아내 집기/놓기 시퀀스를 실행한다.
  한 단계라도 확신이 없으면("모르면 멈춘다") 실행하지 않고 사유를 돌려준다.

무하드웨어 실행: `python solution.py` 또는 CURRICULUM_FORCE_MOCK=1 로 mock 데모가 돈다.
"""
# ── sys.path 부트스트랩(코드 루트 taskB_curriculum 를 import 경로에 추가) ──
import os
import sys

from typing import Any

pass
pass

__all__ = ["plan_actions", "execute_actions", "run_command", "run_visual_command",
           "MOTION_SYSTEM_PROMPT"]


# ===========================================================================
# 1) 언어 해석 — 자연어 → 구조화 동작 리스트
# ===========================================================================
def plan_actions(command, llm=None):
    """자연어 명령을 동작 리스트로 해석한다.

    - 실제(non-mock) LLM(예: MiniMax)이 주입되면 그 LLM 으로 JSON 배열을 얻고
      견고 파싱(+1회 self-repair)한다.
    - 아니면 로컬 규칙 파서(색 무관, 다단계 분해)로 처리한다.

    반환: (actions, raw_text)
    """
    return plan_motion(command, llm)


# ===========================================================================
# 2) 실행 — 동작 리스트를 안전검사(작업영역 클램프) 후 순차 실행
# ===========================================================================
def execute_actions(actions, bot):
    """검증된 동작 리스트를 순서대로 실행한다. 반환: 단계별 실행 로그(list[str])."""
    return execute_motion(actions, bot)


# ===========================================================================
# 3) 오케스트레이션 — 명령 1건을 끝까지 처리
# ===========================================================================
def run_command(command, llm=None, bot=None):
    """자연어 명령 1건을 처리한다(해석 → 안전검사 → 실행).

    bot 이 None 이면 mock 로봇을 만든다. 유효한 동작을 못 얻으면 안전하게 중단한다.
    반환: dict {command, actions, raw, logs, status('ok'|'aborted')}
    """
    if bot is None:
        bot = get_robot(mock=True)
    actions, raw = plan_actions(command, llm)
    if not actions:
        return {"command": command, "actions": [], "raw": raw,
                "logs": ["[안전중단] 유효한 동작을 얻지 못해 실행을 중단합니다."],
                "status": "aborted"}
    logs = execute_actions(actions, bot)
    return {"command": command, "actions": actions, "raw": raw,
            "logs": logs, "status": "ok"}


# ===========================================================================
# 3-b) VLA 확장 — "카메라에 보이는 것 집어줘" (vision_pick/vision_place)
# ===========================================================================
def _to_rgb(frame: Any) -> Any:
    """BGR(vision.Camera/OpenCV 관례) → RGB(GroundingClient.point 규약).

    gui.py 의 _to_rgb 와 동일한 가드 — ndarray 가 아니면(shape 만 흉내낸
    테스트용 가짜 프레임 등) 변환 없이 원본을 돌려준다.
    """
    if frame is None:
        return None
    try:
        return frame[:, :, ::-1]
    except Exception:
        return frame


def _read_frame(cam: Any) -> Any:
    """cam.read() 를 두 규약 모두에서 RGB 프레임으로 정규화한다(실패 시 None).

    - common.vision.Camera : read() → frame (ndarray)
    - OpenCV VideoCapture  : read() → (ok, frame)
    카메라가 없거나 read 가 실패하면 None — 상위 resolve 단계가 안전 중단한다.

    채널 규약(실모드 결함 회귀): vision.Camera.read() 는 **BGR** 를 돌려주지만
    GroundingClient.point 의 계약은 **RGB**(HxWx3 uint8) 다. 여기서 변환하지
    않으면 실서버(Qwen) 경로에서 '빨간 블록'이 파랗게 보여 색 지칭 그라운딩이
    체계적으로 어긋난다 — 반환 직전 BGR→RGB 로 뒤집는다.
    """
    if cam is None:
        return None
    try:
        out = cam.read()
    except Exception:
        return None
    if isinstance(out, tuple):                   # OpenCV 스타일 (ok, frame)
        if len(out) == 2:
            ok, frame = out
            return _to_rgb(frame) if ok else None
        return None
    return _to_rgb(out)


def run_visual_command(command: str, bot: Any, cam: Any,
                       grounding: Any, calib: Any, llm: Any = None) -> dict[str, Any]:
    """카메라를 보는 자연어 명령 1건을 처리한다(계획 → 비전 치환 → 안전 실행).

    흐름(스펙 §2d): frame = cam.read()(BGR→RGB 정규화) → plan_motion(두뇌: LLM/규칙)
    → resolve_vision_actions(눈: grounding + 캘리브레이션 calib)
    → 문제없을 때만 execute_motion(안전 클램프 경유).
    비전 단계가 하나라도 확신이 없으면("모르면 멈춘다") 아무 동작도 실행하지
    않고 messages 에 사유를 담아 돌려준다.

    반환: {"actions": 치환 완료 액션, "messages": 표시용 메시지, "executed": bool}
          (+ 부가: "raw" = 계획 원문, 실행됐다면 "logs" = 단계별 실행 로그)
    """
    frame = _read_frame(cam)
    actions, raw = plan_motion(command, llm)
    if not actions:
        return {"actions": [], "messages": ["유효한 동작을 얻지 못해 실행을 중단합니다."],
                "executed": False, "raw": raw}
    resolved, messages = resolve_vision_actions(actions, frame, grounding, calib)
    if not resolved:                              # 중단 3경로(프레임/캘리브/못 찾음)
        return {"actions": [], "messages": messages, "executed": False, "raw": raw}
    logs = execute_motion(resolved, bot)
    return {"actions": resolved, "messages": messages, "executed": True,
            "raw": raw, "logs": logs}


# ===========================================================================
# 4) 자가 데모 (mock) — 하드웨어/키 없이 로컬 규칙으로 끝까지 실행
# ===========================================================================
def _demo():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print("=" * 70)
    print(" H1 · 자연어로 로봇 제어 (범용 동작, 색 무관) · 무API 데모")
    print("=" * 70)
    commands = [
        "홈으로 복귀",
        "오른쪽으로 5cm 이동",
        "위로 20mm 올린 다음 흡착 켜",
        "왼쪽으로 3cm 이동하고 흡착 꺼",
        "노래 불러줘",                    # 해석 불가 → graceful 안전중단
    ]
    with get_robot(mock=True) as bot:
        for i, cmd in enumerate(commands, 1):
            print(f"\n[명령 {i}] {cmd}")
            res = run_command(cmd, llm=None, bot=bot)   # llm=None → 로컬 규칙
            print("  · 동작계획 :", res["actions"])
            for line in res["logs"]:
                print("     -", line)
            print("  · 상태     :", res["status"])
    print("\n데모 완료: 색 판별 없이 자연어 → 동작 → 안전실행 파이프라인이 동작했습니다.")


def _demo_visual():
    """VLA 확장 mock 데모 — '빨간 블록 집어' 전 과정(눈→좌표→집기) 시연.

    서버·카메라·키 없이: 눈 = MockGrounding(등록 좌표), 캘리브레이션 = 합성
    4점(항등 유사 어핀), 로봇 = MockDobot. 스펙 §2d 데모 시나리오.
    """
    pass
    pass
    pass

    print("\n" + "=" * 70)
    print(" H1 VLA 확장 · '카메라에 보이는 것 집어줘' (vision_pick) mock 데모")
    print("=" * 70)

    # 1) 눈(mock): '빨간 블록' 위치를 정규화(0..1) 좌표로 등록 → 결정적 시연
    grounding = GroundingClient(provider="mock")
    grounding.set_point("빨간 블록", (0.25, 0.62))
    print(f"[눈] MockGrounding 준비(is_mock={grounding.is_mock}) — "
          "'빨간 블록' @ (0.25, 0.62) 등록")

    # 2) 캘리브레이션(합성, 항등 유사 어핀): 픽셀(0..640, 0..480) → 작업영역 mm
    #    rx = 0.2·px + 180 (180~308mm), ry = 0.5·py − 120 (−120~120mm)
    calib = Calibration()
    for (u, v) in [(0.0, 0.0), (640.0, 0.0), (0.0, 480.0), (640.0, 480.0)]:
        calib.add_pair((u, v), (0.2 * u + 180.0, 0.5 * v - 120.0))
    try:
        rep = calib.solve()
        print(f"[캘리브레이션] 합성 4점 solve — 평균 오차 {rep['mean_err_mm']:.2e}mm")
    except RuntimeError:                     # numpy 없는 환경 → 같은 어핀 H 직접 주입
        calib._H = [[0.2, 0.0, 180.0], [0.0, 0.5, -120.0], [0.0, 0.0, 1.0]]
        print("[캘리브레이션] numpy 없음 → 데모용 H 직접 주입(동일 어핀)")

    # 3) 카메라(mock 합성 프레임) + 로봇(MockDobot) 으로 전 과정 실행
    with Camera(mock=True) as cam, get_robot(mock=True) as bot:
        cmd = "빨간 블록 집어"
        print(f"\n[명령] {cmd}")
        res = run_visual_command(cmd, bot, cam, grounding, calib)
        for msg in res["messages"]:
            print("  ·", msg)
        print("  · 동작계획 :", res["actions"])
        for line in res.get("logs", []):
            print("     -", line)
        print("  · executed :", res["executed"])
    print("\nVLA 데모 완료: 눈(mock VLM) → 캘리브레이션(mm) → 집기 시퀀스가 동작했습니다.")





# ==============================================================================
# ── h1_vlm_nl_control/gui.py — main()
# ==============================================================================

# -*- coding: utf-8 -*-
"""H1 · 자연어로 로봇 제어 — 수동 테스트 GUI (+VLA 확장: 눈·캘리브레이션·확인 게이트)

기존 기능(보존)
---------------
- 우측: 자연어 명령 입력 + [실행] — solution 의 plan_actions/execute_actions 재사용.
- 좌측: 작업 공간 카메라(LessonGUI 내장 패시브 뷰, 색검출 없음).

VLA 확장(스펙 §2e — "카메라에 보이는 것 집어줘")
------------------------------------------------
1. 카메라 패널: common.vision.Camera 미리보기(백그라운드 스레드, ~10fps).
   [카메라 연결/해제] 토글 — mock 이면 합성 프레임(카메라 없이 동작).
2. 로컬 VLM(눈): [Qwen 연결] → ensure_server(백그라운드 기동) + is_ready 표시
   ("눈: 연결됨/모의/없음"). 실패해도 GUI 는 모의(mock) 눈으로 계속 동작.
3. 캘리브레이션 마법사: [캘리브레이션 시작] → 로봇이 config.CALIB_PRESETS 4좌표를
   순차 방문(mock 은 즉시) → 각 지점에서 카메라 화면 클릭(진행 n/4) → solve →
   잔차 표시("평균 오차 X.Xmm") → config.CALIB_PATH 저장.
   [검증 모드]: 화면 클릭 → pixel_to_robot → 로봇 z=VISION_Z_HOVER 이동.
   시작 시 CALIB_PATH 가 존재하면 자동 로드("캘리브레이션 로드됨").
4. 명령 플로우: 계획에 vision_pick/vision_place 가 있으면 눈(point) 결과를 프레임
   위 십자+라벨 오버레이로 표시하고 [▶ 실행]/[취소] 확인 게이트를 거친 뒤에만
   실행한다. vision 없는 명령은 기존처럼 즉시 실행. 모든 단계 로그.
5. 종료 시 VLA 카메라/우리가 띄운 llama-server 자식/로봇을 정리한다.

규칙 준수 (H3 gui.py 스레딩/_ui 패턴 승계)
------------------------------------------
- 로봇 이동·서버 기동·VLM 조회는 전부 threading(백그라운드 워커) — UI 안 막힘.
- Tk 위젯 갱신은 _ui(root.after) 경유. 헤드리스(가짜 app)에선 직접 호출로 폴백.
- GUI 생성/실행은 __main__ 아래에서만. import 만으로는 창/카메라/로봇 안 열림.
- 하드웨어/키/서버 없어도 import 와 콜백 단위 호출이 절대 죽지 않는다(mock 폴백).

헤드리스 스모크(무 Tk — 모든 콜백이 가짜 app 으로 호출 가능):
    CURRICULUM_FORCE_MOCK=1 python -m pytest tests/test_h1_vla_gui.py -q
"""
# ── sys.path 부트스트랩(코드 루트 taskB_curriculum 를 import 경로에 추가) ──
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:  # pragma: no cover - reconfigure 미지원 콘솔
    pass

import threading
import time
from typing import Any
from urllib.parse import urlsplit

# tkinter: 디스플레이 없는 환경에서도 import 가 죽지 않도록 가드(헤드리스 스모크).
try:
    import tkinter as tk
    _HAS_TK = True
except Exception:  # pragma: no cover - 헤드리스 환경 폴백
    tk = None  # type: ignore[assignment]
    _HAS_TK = False

# cv2: 오버레이 라벨 텍스트에만 사용(없으면 십자만 — 순수 슬라이싱으로 그림).
try:
    import cv2
    _HAS_CV2 = True
except Exception:  # pragma: no cover - opencv 미설치 폴백
    cv2 = None  # type: ignore[assignment]
    _HAS_CV2 = False

pass
pass
pass
pass
pass
pass
pass

# solution 의 계획/실행 함수 재사용(중복 구현 금지)
pass

INFO = (
    "자연어 명령을 입력하고 [실행]을 누르세요. 로봇은 먼저 '로봇 연결'로 연결합니다.\n"
    "예시) '홈으로 복귀' · '오른쪽으로 5cm 이동' · '위로 20mm 올린 다음 흡착 켜'\n"
    "VLA) '빨간 블록 집어' 같은 비전 명령은 [카메라 연결] 후 십자 오버레이 확인 → [▶ 실행].\n"
    "캘리브레이션: [캘리브레이션 시작] → 로봇이 4지점 방문 → 각 지점의 집게 끝을 화면 클릭.\n"
    "MINIMAX_API_KEY 가 있으면 MiniMax 로, 없으면 로컬 규칙으로 해석합니다(색 판별 없음)."
)

CAM_POLL_S = 0.1                                  # 카메라 미리보기 주기(~10fps)
_VISION_ACTIONS = ("vision_pick", "vision_place")  # 확인 게이트 대상 액션


# ===========================================================================
# 0) 공통 헬퍼 — Tk 유무/스레드에 안전한 UI 갱신 (H3 _ui 패턴)
# ===========================================================================
def _force_mock() -> bool:
    """CURRICULUM_FORCE_MOCK 강제 mock 스위치(이때는 llama-server 도 안 띄운다)."""
    return os.environ.get("CURRICULUM_FORCE_MOCK", "").strip().lower() in (
        "1", "true", "yes", "on")


def _ui(app: Any, fn: Any, *args: Any) -> None:
    """위젯 갱신을 UI 스레드로 넘긴다(root.after). 헤드리스(가짜 app)면 직접 호출."""
    root = getattr(app, "root", None)
    if root is not None:
        try:
            root.after(0, fn, *args)
            return
        except Exception:
            pass
    try:
        fn(*args)
    except Exception:
        pass


def _set_var(app: Any, name: str, text: str) -> None:
    """app.<name> 이 tk.StringVar 면 _ui 경유로 갱신(헤드리스면 조용히 무시)."""
    var = getattr(app, name, None)
    if var is not None and hasattr(var, "set"):
        _ui(app, var.set, text)


def _set_btn_text(app: Any, name: str, text: str) -> None:
    """app.<name> 버튼의 라벨을 바꾼다(헤드리스면 조용히 무시)."""
    btn = getattr(app, name, None)
    if btn is not None:
        _ui(app, lambda: btn.configure(text=text))


def _set_gate_enabled(app: Any, enabled: bool) -> None:
    """[▶ 실행]/[취소] 확인 게이트 버튼 활성/비활성(헤드리스면 no-op)."""
    state = "normal" if enabled else "disabled"

    def _apply() -> None:
        for name in ("_btn_exec", "_btn_cancel"):
            btn = getattr(app, name, None)
            if btn is not None:
                try:
                    btn.configure(state=state)
                except Exception:
                    pass

    _ui(app, _apply)


# ===========================================================================
# 1) VLA 상태 초기화 — Tk 불필요(헤드리스 스모크의 진입점)
# ===========================================================================
def _init_vla_state(app: Any) -> None:
    """VLA 확장 상태를 app 에 붙인다. LessonGUI 든 테스트용 가짜 app 이든
    log()/set_status() 만 있으면 동작한다(무하드웨어·무서버·무 Tk).

    CALIB_PATH 가 존재하면 캘리브레이션을 자동 로드한다(스펙 §2e-3).
    """
    app._llm = LLMClient(provider="minimax")     # 두뇌(키 없으면 mock → 규칙 폴백)
    app._grounding = GroundingClient()           # 눈(서버/키 없으면 자동 mock)
    app._server_proc = None                      # 우리가 띄운 llama-server 자식
    app._vla_cam = None                          # common.vision.Camera | None
    app._vla_cam_running = False                 # 미리보기 루프 플래그
    app._vla_frame = None                        # 최신 BGR 프레임(눈/마법사 입력)
    app._vla_lock = threading.Lock()
    app._pending = None                          # 확인 게이트 대기 {"actions","messages"}
    app._abort = threading.Event()               # E-STOP: 진행 중 시퀀스 즉시 중단 신호
    app._wizard_mode = "idle"                    # "idle" | "collect" | "verify"
    app._wizard_idx = 0                          # 수집 진행(0..4)
    app._wizard_calib = None                     # 수집 중인 새 Calibration
    app._calib = Calibration()
    path = str(getattr(config, "CALIB_PATH", "") or "")
    if path and os.path.exists(path):
        try:
            app._calib = Calibration.load(path)
            app.log(f"캘리브레이션 로드됨 ({app._calib.n_pairs}쌍, "
                    f"{os.path.basename(path)})")
        except Exception as e:
            app.log(f"[경고] 캘리브레이션 파일 로드 실패: {e}")


# ===========================================================================
# 2) 프레임 헬퍼 — 최신 프레임 공유(peek) + LessonGUI 캔버스 표시
# ===========================================================================
def _peek_frame(app: Any) -> Any:
    """최신 카메라 프레임(BGR)을 돌려준다(없으면 None).

    1순위: VLA 카메라 스레드가 갱신하는 _vla_frame.
    2순위: LessonGUI 내장 캡처의 원본(_raw) — 실카메라 패시브 뷰 재사용.
    """
    lock = getattr(app, "_vla_lock", None)
    if lock is not None:
        with lock:
            frame = getattr(app, "_vla_frame", None)
        if frame is not None:
            return frame
    lock2 = getattr(app, "_lock", None)
    if lock2 is not None:
        with lock2:
            return getattr(app, "_raw", None)
    return None


def _to_rgb(frame: Any) -> Any:
    """BGR(OpenCV/vision.Camera 관례) → RGB(GroundingClient 규약). 실패 시 원본."""
    try:
        return frame[:, :, ::-1]
    except Exception:
        return frame


def _push_display(app: Any, frame: Any) -> None:
    """LessonGUI 표시 버퍼(_display)에 프레임을 밀어넣는다(헤드리스면 no-op)."""
    lock = getattr(app, "_lock", None)
    if lock is None:
        return
    with lock:
        app._display = frame
        app._display_ver = int(getattr(app, "_display_ver", 0)) + 1


def _show_frame(app: Any, frame: Any) -> None:
    """미리보기 프레임 표시 — 확인 게이트(오버레이) 대기 중엔 화면을 고정한다.

    pending 체크와 표시 버퍼 push 를 _lock 아래에서 원자적으로 처리한다(TOCTOU 방지):
    카메라 스레드가 'pending 없음'을 본 직후 확인 게이트가 오버레이를 올려도,
    이어지는 라이브 프레임이 그 오버레이를 덮어쓰지 않게 한다(pending 중이면 skip).
    """
    lock = getattr(app, "_lock", None)
    if lock is None:
        return
    with lock:
        if getattr(app, "_pending", None) is not None:
            return
        app._display = frame
        app._display_ver = int(getattr(app, "_display_ver", 0)) + 1


def _draw_cross(frame: Any, px: float, py: float, label: str = "") -> Any:
    """프레임(BGR)에 노란 십자 + 라벨을 그린다(순수 슬라이싱 — cv2 없이도 십자).

    주의: cv2 기본 폰트는 한글을 렌더링하지 못하므로 라벨은 보조 표기일 뿐이며,
    정확한 타깃명은 로그에 병기된다.
    """
    try:
        h, w = int(frame.shape[0]), int(frame.shape[1])
        x = min(max(int(round(px)), 0), w - 1)
        y = min(max(int(round(py)), 0), h - 1)
        color = (0, 255, 255)                      # BGR 노랑
        arm = 14                                   # 십자 팔 길이(px)
        frame[y, max(0, x - arm):min(w, x + arm + 1)] = color
        frame[max(0, y - arm):min(h, y + arm + 1), x] = color
    except Exception:
        return frame
    if label and _HAS_CV2:
        try:
            cv2.putText(frame, str(label), (min(x + 10, w - 1), max(y - 10, 14)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
        except Exception:
            pass
    return frame


# ===========================================================================
# 3) 카메라 패널 — 독립 연결/해제 토글 + 미리보기 스레드 (H3 패턴)
# ===========================================================================
def _cam_source(app: Any) -> "int | str":
    """카메라 소스 입력란 값 → int 인덱스 또는 경로 문자열(교실 PC별 조정, §3)."""
    var = getattr(app, "_cam_src_var", None)
    raw = ""
    if var is not None:
        try:
            raw = str(var.get()).strip()
        except Exception:
            raw = ""
    if not raw:
        return int(getattr(config, "CAM_TABLE", 0))
    return int(raw) if raw.lstrip("+-").isdigit() else raw


def _toggle_camera(app: Any) -> None:
    """[카메라 연결/해제] 토글 — 연결(느릴 수 있음)은 백그라운드 워커에서."""
    if getattr(app, "_vla_cam", None) is None:
        threading.Thread(target=_cam_connect_worker, args=(app,), daemon=True).start()
    else:
        _disconnect_camera(app)


def _release_builtin_cap(app: Any) -> None:
    """LessonGUI 내장 패시브 캡처를 해제한다(같은 장치를 두 번 열지 않게).

    내장 _cap 을 영구 해제하고, 내장 표시 버퍼(_raw)도 _lock 아래에서 무효화한다.
    (해제 후 남은 stale 프레임으로 _peek_frame 이 폴백해 비전/캘리브가 옛 화면으로
    도는 것을 막는다 — "모르면 멈춘다".)
    """
    cap = getattr(app, "_cap", None)
    app._cap = None
    if cap is not None:
        try:
            cap.release()
        except Exception:
            pass
    lock = getattr(app, "_lock", None)
    if lock is not None:
        with lock:
            app._raw = None


def _cam_connect_worker(app: Any) -> None:
    """카메라를 연다(카메라 부재/mock 이면 합성 프레임). 미리보기 스레드 시작."""
    _set_var(app, "_vla_cam_var", "연결 중...")
    # 장치 경합 방지: 같은 카메라 인덱스를 LessonGUI 내장 캡처가 독점 중이면 새 Camera 가
    # 실패/모의로 떨어지므로, Camera 생성 **전에** 내장 캡처를 해제한다.
    _release_builtin_cap(app)
    try:
        cam = Camera(source=_cam_source(app))     # mock 자동판정(FORCE_MOCK/cv2 부재)
    except Exception as e:
        _set_var(app, "_vla_cam_var", "실패")
        app.log(f"[카메라 오류] {e}")
        return
    app._vla_cam = cam
    app._vla_cam_running = True
    threading.Thread(target=_cam_loop, args=(app,), daemon=True).start()
    is_mock = bool(getattr(cam, "mock", False))
    _set_var(app, "_vla_cam_var", "연결됨 · " + ("모의(합성)" if is_mock else "실카메라"))
    _set_btn_text(app, "_btn_cam", "카메라 해제")
    app.log(f"카메라 연결됨 (mock={is_mock}).")


def _disconnect_camera(app: Any) -> None:
    """카메라 해제 — 미리보기 루프 정지 + 자원 반환 + 프레임 버퍼 무효화.

    LessonGUI 내장 버퍼(_raw)도 함께 비운다: 내장 캡처는 _cam_connect_worker 가
    이미 영구 해제했으므로(_cap=None) _raw 에는 해제 이전의 **정지 화면**만
    남는다 — 지우지 않으면 _peek_frame 이 그 stale 프레임으로 폴백해
    캘리브레이션/비전 게이트가 옛 화면으로 진행된다("모르면 멈춘다" 우회).
    """
    app._vla_cam_running = False
    cam = getattr(app, "_vla_cam", None)
    app._vla_cam = None
    lock = getattr(app, "_vla_lock", None)
    if lock is not None:
        with lock:
            app._vla_frame = None
    lock2 = getattr(app, "_lock", None)
    if lock2 is not None:
        with lock2:
            app._raw = None                       # 내장 _cap 은 이미 None → 안 되살아남
    if cam is not None:
        try:
            cam.release()
        except Exception:
            pass
    _set_var(app, "_vla_cam_var", "미연결")
    _set_btn_text(app, "_btn_cam", "카메라 연결")
    app.log("카메라 해제.")


def _cam_loop(app: Any) -> None:
    """카메라 미리보기 루프(~10fps). _vla_cam_running 플래그로 종료(유한 동작)."""
    while getattr(app, "_vla_cam_running", False):
        cam = getattr(app, "_vla_cam", None)
        if cam is None:
            break
        try:
            frame = cam.read()
        except Exception as e:
            app.log(f"[카메라 읽기 오류] {e}")
            time.sleep(0.5)
            continue
        # 해제 직후의 늦은 프레임이 버퍼를 되살리지 않도록 저장 직전 재확인
        if frame is not None and getattr(app, "_vla_cam_running", False):
            lock = getattr(app, "_vla_lock", None)
            if lock is not None:
                with lock:
                    app._vla_frame = frame
            _show_frame(app, frame)
        time.sleep(CAM_POLL_S)


# ===========================================================================
# 4) 눈(로컬 VLM) — [Qwen 연결] : ensure_server 백그라운드 + 상태 표시
# ===========================================================================
def _grounding_port() -> int:
    """config.GROUNDING_URL 에서 포트를 파싱한다(ensure_server 와 클라이언트 포트 일치).

    GROUNDING_URL 을 다른 포트로 바꿔도 ensure_server 가 같은 포트에 서버를 띄우도록
    한다(하드코딩 8123 과의 불일치 방지). 파싱 실패 시 기본 8123.
    """
    url = str(getattr(config, "GROUNDING_URL", "") or "")
    try:
        return int(urlsplit(url).port or 8123)
    except Exception:
        return 8123


def _connect_qwen(app: Any) -> None:
    """[Qwen 연결] 버튼 — 서버 기동(느림)은 백그라운드 워커에서."""
    threading.Thread(target=_qwen_worker, args=(app,), daemon=True).start()


def _qwen_worker(app: Any) -> None:
    """ensure_server 로 로컬 llama-server 를 보장하고 눈 상태를 갱신한다.

    실패해도 GUI 는 죽지 않는다 — 모의(mock) 눈으로 폴백해 수업을 계속한다.
    CURRICULUM_FORCE_MOCK=1 이면 서버 기동 자체를 건너뛴다(오프라인 데모).
    """
    if _force_mock():
        app._grounding = GroundingClient(provider="mock")
        _set_var(app, "_eye_var", "눈: 모의")
        app.log("[Qwen] CURRICULUM_FORCE_MOCK=1 — 서버 기동 없이 모의(mock) 눈 사용.")
        return
    _set_var(app, "_eye_var", "눈: 연결 중...")
    app.log("[Qwen] 로컬 VLM 서버 확인/기동 중... (첫 모델 로드는 수십 초 걸릴 수 있음)")
    try:
        proc = ensure_server(port=_grounding_port())  # 이미 떠 있으면 None(재사용)
        if proc is not None:
            app._server_proc = proc               # 우리가 띄웠으면 종료 시 정리
    except Exception as e:
        app._grounding = GroundingClient(provider="mock")
        _set_var(app, "_eye_var", "눈: 없음(모의 폴백)")
        app.log(f"[Qwen] 서버 기동 실패 → 모의(mock) 눈으로 계속: {e}")
        return
    g = GroundingClient(mock=False)               # 서버가 떴으니 실모드 명시
    if g.is_mock:                                 # config GROUNDING_PROVIDER=mock 존중
        app._grounding = g
        _set_var(app, "_eye_var", "눈: 모의")
        app.log("[Qwen] GROUNDING_PROVIDER=mock 설정 — 모의(mock) 눈을 사용합니다.")
    elif g.is_ready():
        app._grounding = g
        _set_var(app, "_eye_var", "눈: 연결됨")
        app.log("[Qwen] 로컬 VLM 연결됨 — 실제 시각 그라운딩을 사용합니다.")
    else:
        app._grounding = GroundingClient(provider="mock")
        _set_var(app, "_eye_var", "눈: 없음(모의 폴백)")
        app.log("[Qwen] 서버 응답 없음 → 모의(mock) 눈으로 계속합니다.")


# ===========================================================================
# 5) 캘리브레이션 마법사 — 4점 수집 → solve → 잔차 → 저장 (+ 검증 모드)
# ===========================================================================
def _calib_presets() -> list[tuple[float, float]]:
    """config.CALIB_PRESETS 4좌표(mm)를 읽는다(없으면 보수적 기본값). # 실측 필요"""
    raw = getattr(config, "CALIB_PRESETS", None) or [
        (200.0, -80.0), (200.0, 80.0), (300.0, 80.0), (300.0, -80.0)]
    return [(float(p[0]), float(p[1])) for p in raw]


def _start_calibration(app: Any) -> None:
    """[캘리브레이션 시작] — 프리셋 4좌표 순회 수집 모드 진입(화면 클릭 대기)."""
    if getattr(app, "_vla_cam", None) is None:
        app.log("[안전중단] 비전/캘리브레이션은 [카메라 연결] 후 사용하세요.")
        return
    if _peek_frame(app) is None:
        app.log("[캘리브레이션] 카메라 프레임이 없습니다 — 먼저 '카메라 연결'을 누르세요.")
        return
    if getattr(app, "robot", None) is None:
        app.log("[캘리브레이션] 로봇 미연결 — 이동 없이 진행합니다(연습/모의 모드).")
    app._wizard_calib = Calibration()             # 새로 수집(성공 시에만 채택)
    app._wizard_mode = "collect"
    app._wizard_idx = 0
    app.log("[캘리브레이션] 시작 — 로봇이 4개 지점을 차례로 방문합니다.")
    threading.Thread(target=_calib_move_worker, args=(app, 0), daemon=True).start()


def _calib_move_worker(app: Any, idx: int) -> None:
    """로봇을 idx 번째 프리셋 좌표(z=HOVER)로 이동시키고 화면 클릭을 요청한다."""
    presets = _calib_presets()
    if idx >= len(presets):
        return
    rx, ry = presets[idx]
    z = float(getattr(config, "VISION_Z_HOVER", 40.0))
    bot = getattr(app, "robot", None)
    if bot is not None:
        cx, cy, cz, cr = safety.clamp_move(rx, ry, z, 0.0)
        try:
            bot.move_to(cx, cy, cz, cr)
        except Exception as e:
            app.log(f"[캘리브레이션] 이동 오류({idx + 1}/{len(presets)}): {e}")
    app.log(f"[캘리브레이션] {idx + 1}/{len(presets)} — 로봇({rx:.0f}, {ry:.0f})mm 지점. "
            "화면에서 엔드이펙터(집게 끝) 위치를 클릭하세요.")
    app.set_status(f"캘리브레이션 {idx + 1}/{len(presets)} — 화면 클릭 대기")


def on_canvas_click(px: int, py: int, app: Any) -> None:
    """카메라 화면 클릭 콜백(LessonGUI on_canvas_click 규약: 프레임 픽셀좌표)."""
    mode = getattr(app, "_wizard_mode", "idle")
    if mode == "collect":
        _calib_click(app, float(px), float(py))
    elif mode == "verify":
        threading.Thread(target=_verify_move_worker,
                         args=(app, float(px), float(py)), daemon=True).start()


def _calib_click(app: Any, px: float, py: float) -> None:
    """수집 모드 클릭 1회 = (픽셀, 프리셋 로봇좌표) 대응쌍 1개 등록(진행 n/4)."""
    presets = _calib_presets()
    idx = int(getattr(app, "_wizard_idx", 0))
    calib = getattr(app, "_wizard_calib", None)
    if calib is None or idx >= len(presets):
        return
    calib.add_pair((px, py), presets[idx])
    app._wizard_idx = idx + 1
    app.log(f"[캘리브레이션] {idx + 1}/{len(presets)} 등록: "
            f"픽셀({px:.0f}, {py:.0f}) ↔ 로봇{presets[idx]}mm")
    if app._wizard_idx < len(presets):
        threading.Thread(target=_calib_move_worker,
                         args=(app, app._wizard_idx), daemon=True).start()
    else:
        _finish_calibration(app)


def _finish_calibration(app: Any) -> None:
    """4점 수집 완료 → solve → 잔차 표시 → CALIB_PATH 저장 → 채택."""
    app._wizard_mode = "idle"
    calib = getattr(app, "_wizard_calib", None)
    app._wizard_calib = None
    if calib is None:
        return
    try:
        rep = calib.solve()
    except Exception as e:
        app.log(f"[캘리브레이션] solve 실패: {e} — [캘리브레이션 시작]으로 다시 하세요.")
        app.set_status("캘리브레이션 실패")
        return
    app._calib = calib                            # solve 성공 시에만 채택(이전 해 보호)
    msg = f"평균 오차 {rep['mean_err_mm']:.1f}mm (최대 {rep['max_err_mm']:.1f}mm)"
    path = str(getattr(config, "CALIB_PATH", "") or "")
    if path:
        try:
            calib.save(path)
            app.log(f"[캘리브레이션] 완료 — {msg} · 저장됨: {os.path.basename(path)}")
        except Exception as e:
            app.log(f"[캘리브레이션] 완료 — {msg} · 저장 실패: {e}")
    else:  # pragma: no cover - config 에 CALIB_PATH 가 없는 비정상 환경
        app.log(f"[캘리브레이션] 완료 — {msg} (저장 경로 없음)")
    _set_var(app, "_calib_var", f"캘리브레이션: {msg}")
    app.set_status(f"캘리브레이션 완료 · {msg}")


def _toggle_verify(app: Any) -> None:
    """[검증 모드] 토글 — 화면 클릭 → pixel_to_robot → 로봇 z=HOVER 이동."""
    if getattr(app, "_wizard_mode", "idle") == "verify":
        app._wizard_mode = "idle"
        app.set_status("검증 모드 종료")
        app.log("[검증] 종료.")
        return
    calib = getattr(app, "_calib", None)
    if not bool(getattr(calib, "is_solved", False)):
        app.log("[검증] 캘리브레이션이 없습니다 — 먼저 마법사를 완료(또는 로드)하세요.")
        return
    app._wizard_mode = "verify"
    app.set_status("검증 모드 — 화면을 클릭하면 로봇이 그 위치로 이동")
    app.log("[검증] 시작 — 화면 클릭 → pixel_to_robot → z=HOVER 이동. "
            "(버튼을 다시 누르면 종료)")


def _verify_move_worker(app: Any, px: float, py: float) -> None:
    """검증 클릭 1회: 픽셀 → 로봇 mm 변환 → 안전 클램프 → z=HOVER 이동."""
    calib = getattr(app, "_calib", None)
    if calib is None:
        app.log("[검증] 캘리브레이션이 없습니다 — 먼저 마법사를 완료하세요.")
        return
    try:
        rx, ry = calib.pixel_to_robot(px, py)
    except Exception as e:
        app.log(f"[검증] 변환 실패: {e}")
        return
    z = float(getattr(config, "VISION_Z_HOVER", 40.0))
    cx, cy, cz, cr = safety.clamp_move(float(rx), float(ry), z, 0.0)
    app.log(f"[검증] 픽셀({px:.0f}, {py:.0f}) → 로봇({rx:.1f}, {ry:.1f})mm "
            f"→ 이동({cx}, {cy}, {cz})")
    bot = getattr(app, "robot", None)
    if bot is None:
        app.log("[검증] 로봇 미연결 — 좌표만 표시하고 이동은 생략합니다.")
        return
    try:
        bot.move_to(cx, cy, cz, cr)
    except Exception as e:
        app.log(f"[검증] 이동 오류: {e}")


# ===========================================================================
# 6) 명령 플로우 — 계획 → (vision 이면 오버레이 + 확인 게이트) → 안전 실행
# ===========================================================================
class _CachedGrounding:
    """target 별 point 결과를 1회만 조회(캐시)하는 래퍼.

    오버레이 표시와 resolve_vision_actions 가 같은 좌표를 공유하고,
    실서버 VLM(새 장면 ~6s)을 같은 target 으로 두 번 부르지 않게 한다.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.cache: dict[str, "tuple[float, float] | None"] = {}

    def point(self, frame: Any, target: str) -> "tuple[float, float] | None":
        key = str(target)
        if key not in self.cache:
            self.cache[key] = self._inner.point(frame, target)
        return self.cache[key]


def _has_vision(actions: list[dict[str, Any]]) -> bool:
    """계획에 vision_pick/vision_place 가 포함돼 있는지(확인 게이트 대상)."""
    return any(a.get("action") in _VISION_ACTIONS for a in actions)


def _run_command_thread(app: Any, command: str) -> None:
    """'실행' 버튼 콜백(스레드 본문): 자연어 → 계획 → (비전 확인 게이트) → 실행.

    명령 해석은 MiniMax LLM(app._llm)으로 한다. MINIMAX_API_KEY 가 없으면 그
    클라이언트가 mock 이 되어 plan_actions 가 로컬 규칙으로 폴백하므로,
    키·인터넷 없이도 동작한다. vision_* 계획은 즉시 실행하지 않고
    십자 오버레이 + [▶ 실행]/[취소] 확인 게이트를 거친다(스펙 §2e-4).
    """
    abort = getattr(app, "_abort", None)
    if abort is not None:
        abort.clear()                             # 새 명령 시작 — 이전 E-STOP 래치 해제
    app.set_status(f"실행 중: {command}")
    app.log(f"[명령] {command}")

    # 1) 자연어 → 동작 계획(MiniMax 또는 로컬 규칙)
    try:
        actions, _raw = plan_actions(command, getattr(app, "_llm", None))
    except Exception as e:
        app.log(f"[오류] 계획 실패: {e}")
        app.set_status("실행 실패(계획)")
        return
    app.log(f"[동작계획] {actions}")

    if not actions:
        app.log("[안전중단] 유효한 동작을 얻지 못해 실행을 중단합니다.")
        app.set_status("안전중단(유효 동작 없음)")
        return

    # 2) 비전 명령이면 확인 게이트 경유(즉시 실행 금지), 아니면 기존 즉시 실행
    if _has_vision(actions):
        _prepare_vision_confirm(app, actions)
        return
    _execute_on_robot(app, actions)


def _estop_robot(app: Any, bot: Any) -> None:
    """E-STOP 시퀀스 중단 시 로봇을 안전 정지한다.

    가능하면 RobotController._safe_stop(흡착/그리퍼 해제 + 펌프 정지)을, 없으면
    최소한 흡착/그리퍼를 끈다. 종료 경로이므로 어떤 예외도 삼킨다.
    """
    fn = getattr(bot, "_safe_stop", None)
    if callable(fn):
        try:
            fn()
            return
        except Exception as e:
            app.log(f"[E-STOP] 안전정지 오류: {e}")
    for meth in ("suck", "grip"):
        f = getattr(bot, meth, None)
        if callable(f):
            try:
                f(False)
            except Exception:
                pass


def _execute_on_robot(app: Any, actions: list[dict[str, Any]]) -> None:
    """동작 리스트를 로봇에서 실행(미연결이면 계획만 표시) — 기존 경로 보존.

    E-STOP: 매 동작 실행 **전에** app._abort 를 검사한다. 세트되면 남은 동작
    (하강·흡착·복귀 등)을 실행하지 않고 즉시 로봇을 안전 정지한다
    ("비상정지 후에도 시퀀스가 계속 도는" critical 결함 차단).
    """
    bot = getattr(app, "robot", None)
    if bot is None:
        app.log("[안내] 로봇이 미연결입니다. 계획만 표시하고 실행은 생략합니다.")
        app.set_status("계획 완료(로봇 미연결)")
        return
    abort = getattr(app, "_abort", None)
    try:
        for act in actions:
            if abort is not None and abort.is_set():
                app.log("[E-STOP] 시퀀스 중단 — 남은 동작을 실행하지 않습니다.")
                _estop_robot(app, bot)
                app.set_status("■ 비상정지 — 시퀀스 중단")
                return
            for line in execute_actions([act], bot):  # 한 동작씩(매 동작 전 abort 검사)
                app.log("  - " + str(line))
        app.set_status("실행 완료")
    except Exception as e:
        app.log(f"[실행 오류] {e}")
        app.set_status("실행 오류")


def _prepare_vision_confirm(app: Any, actions: list[dict[str, Any]]) -> None:
    """vision_* 계획을 눈+캘리브레이션으로 치환하고 오버레이+확인 게이트를 연다.

    "모르면 멈춘다": 프레임 없음/캘리브레이션 필요/타깃 못 찾음이면 실행 없이
    사유를 로그로 남기고 중단한다(resolve_vision_actions 의 3중 중단 경로).
    """
    # 게이트 0: VLA 카메라가 연결됐을 때만 비전 명령 허용(내장 패시브 뷰의 stale
    #   프레임으로 확인 게이트·캘리브레이션을 우회하는 것을 원천 차단).
    if getattr(app, "_vla_cam", None) is None:
        app.log("[안전중단] 비전/캘리브레이션은 [카메라 연결] 후 사용하세요.")
        app.set_status("안전중단(카메라 미연결)")
        return
    # 게이트 0-b: 모의(mock) 눈 좌표로 실기 로봇을 움직이지 않는다(엉뚱한 곳 집기 방지).
    #   둘 다 mock 이거나 둘 다 실기일 때만 진행한다.
    grounding_obj = getattr(app, "_grounding", None)
    robot = getattr(app, "robot", None)
    if (robot is not None and getattr(grounding_obj, "is_mock", False)
            and not getattr(robot, "mock", True)):
        app.log("[안전중단] 모의 눈(mock) 좌표로는 실기 로봇을 움직이지 않습니다 "
                "— [Qwen 연결] 후 사용")
        app.set_status("안전중단(모의 눈·실기 로봇)")
        return
    frame = _peek_frame(app)
    if frame is None:
        app.log("[안전중단] 카메라 프레임 없음 — '카메라 연결' 후 다시 시도하세요.")
        app.set_status("안전중단(카메라 프레임 없음)")
        return
    grounding = _CachedGrounding(
        getattr(app, "_grounding", None) or GroundingClient(provider="mock"))
    calib = getattr(app, "_calib", None) or Calibration()

    app.set_status("눈(VLM) 조회 중... (새 장면은 수 초 걸릴 수 있음)")
    resolved, messages = resolve_vision_actions(
        list(actions), _to_rgb(frame), grounding, calib)
    for m in messages:
        app.log("  · " + str(m))
    if not resolved:
        app.set_status("안전중단(비전) — " + (str(messages[0]) if messages else ""))
        return

    # 오버레이: 찾은 표적마다 십자 + 라벨(한글 라벨은 로그에 병기 — cv2 폰트 한계)
    try:
        overlay = frame.copy()
    except Exception:
        overlay = frame
    n = 0
    for target, xy in grounding.cache.items():
        if xy is None:
            continue
        _draw_cross(overlay, float(xy[0]), float(xy[1]), str(target))
        n += 1
    app._pending = {"actions": resolved, "messages": list(messages)}
    _push_display(app, overlay)                   # _pending 설정 후 → 화면 고정
    _set_gate_enabled(app, True)
    app.log(f"[확인] 표적 {n}건을 화면에 십자로 표시했습니다 — "
            "위치가 맞으면 [▶ 실행], 아니면 [취소].")
    app.set_status("확인 대기 — [▶ 실행] / [취소]")


def _confirm_execute(app: Any) -> "threading.Thread | None":
    """[▶ 실행] — 확인 게이트를 통과한 비전 액션을 백그라운드에서 실행한다."""
    pending = getattr(app, "_pending", None)
    app._pending = None                           # 화면 고정 해제(미리보기 재개)
    _set_gate_enabled(app, False)
    if not pending:
        app.log("[안내] 대기 중인 비전 명령이 없습니다.")
        return None
    t = threading.Thread(target=_execute_on_robot,
                         args=(app, pending["actions"]), daemon=True)
    t.start()
    return t


def _cancel_pending(app: Any) -> None:
    """[취소] — 대기 중인 비전 명령을 폐기한다(로봇은 움직이지 않음)."""
    had = getattr(app, "_pending", None) is not None
    app._pending = None
    _set_gate_enabled(app, False)
    app.log("[취소] 비전 명령을 취소했습니다." if had else "[안내] 취소할 명령이 없습니다.")
    app.set_status("취소됨" if had else "준비됨")


# ===========================================================================
# 7) 우측 패널 구성(기존 + VLA 확장) — LessonGUI build_controls 규약
# ===========================================================================
def build_controls(parent: Any, app: Any) -> None:
    """우측 패널: 기존 명령 입력/실행 + 확인 게이트 + 카메라/눈/캘리브레이션."""
    _init_vla_state(app)                          # Tk 무관 상태(캘리브 자동 로드 포함)

    bg = parent["bg"]
    fg, dim = "#e6e6e6", "#9aa0b5"

    # ── 기존: 자연어 명령 입력 + 실행 ─────────────────────────────────────
    tk.Label(parent, text="자연어 명령", bg=bg, fg=fg,
             font=("맑은 고딕", 10, "bold")).pack(anchor="w", pady=(12, 2))
    entry = tk.Entry(parent, width=32, font=("맑은 고딕", 11))
    entry.insert(0, "홈으로 복귀")
    entry.pack(fill="x", pady=(0, 4))

    def on_run(_evt: Any = None) -> None:
        command = str(entry.get()).strip()
        if not command:
            app.log("[안내] 명령을 입력하세요.")
            return
        # 로봇 이동/VLM 조회를 포함하므로 반드시 스레드에서 실행(UI 안 막힘)
        threading.Thread(target=_run_command_thread, args=(app, command),
                         daemon=True).start()

    entry.bind("<Return>", on_run)                # Enter 로도 실행
    tk.Button(parent, text="실행", command=on_run, bg="#4f9dff", fg="white",
              font=("맑은 고딕", 11, "bold"), relief="flat", height=1).pack(
        fill="x", pady=(0, 2))
    tk.Label(parent, text="예: '위로 20mm 올린 다음 흡착 켜' · '빨간 블록 집어'",
             bg=bg, fg=dim, font=("맑은 고딕", 9)).pack(anchor="w")

    # ── 확인 게이트: vision 명령일 때만 활성화(평소 비활성) ────────────────
    gate = tk.Frame(parent, bg=bg)
    gate.pack(fill="x", pady=(4, 2))
    app._btn_exec = tk.Button(gate, text="▶ 실행", state="disabled",
                              command=lambda: _confirm_execute(app),
                              bg="#188038", fg="white",
                              font=("맑은 고딕", 10, "bold"), relief="flat")
    app._btn_exec.pack(side="left", fill="x", expand=True, padx=(0, 3))
    app._btn_cancel = tk.Button(gate, text="취소", state="disabled",
                                command=lambda: _cancel_pending(app),
                                bg="#5f6368", fg="white",
                                font=("맑은 고딕", 10, "bold"), relief="flat")
    app._btn_cancel.pack(side="left", fill="x", expand=True, padx=(3, 0))

    # ── VLA 확장: 카메라 패널(독립 연결 토글) ─────────────────────────────
    tk.Label(parent, text="─ VLA 확장 (보고 집기) ─", bg=bg, fg=dim,
             font=("맑은 고딕", 9)).pack(anchor="w", pady=(10, 2))
    cam_row = tk.Frame(parent, bg=bg)
    cam_row.pack(fill="x", pady=(0, 2))
    tk.Label(cam_row, text="소스", bg=bg, fg=fg,
             font=("맑은 고딕", 9)).pack(side="left")
    app._cam_src_var = tk.StringVar(value=str(config.CAM_TABLE))
    tk.Entry(cam_row, textvariable=app._cam_src_var, width=6,
             font=("Consolas", 10)).pack(side="left", padx=(4, 6))
    app._btn_cam = tk.Button(cam_row, text="카메라 연결",
                             command=lambda: _toggle_camera(app),
                             bg="#188038", fg="white",
                             font=("맑은 고딕", 9, "bold"), relief="flat")
    app._btn_cam.pack(side="left", fill="x", expand=True)
    app._vla_cam_var = tk.StringVar(value="미연결")
    tk.Label(parent, textvariable=app._vla_cam_var, bg=bg, fg=dim,
             font=("맑은 고딕", 9)).pack(anchor="w")

    # ── VLA 확장: 눈(로컬 VLM) 연결 ──────────────────────────────────────
    tk.Button(parent, text="Qwen 연결 (로컬 VLM)", command=lambda: _connect_qwen(app),
              bg="#8e24aa", fg="white", font=("맑은 고딕", 10),
              relief="flat").pack(fill="x", pady=(6, 1))
    app._eye_var = tk.StringVar(
        value="눈: 모의" if app._grounding.is_mock else "눈: 없음 — [Qwen 연결]")
    tk.Label(parent, textvariable=app._eye_var, bg=bg, fg=dim,
             font=("맑은 고딕", 9)).pack(anchor="w")

    # ── VLA 확장: 캘리브레이션 마법사 + 검증 모드 ─────────────────────────
    tk.Button(parent, text="캘리브레이션 시작 (4점)",
              command=lambda: _start_calibration(app), bg="#3a3a52", fg="white",
              font=("맑은 고딕", 10), relief="flat").pack(fill="x", pady=(6, 1))
    tk.Button(parent, text="검증 모드 (클릭→이동)",
              command=lambda: _toggle_verify(app), bg="#3a3a52", fg="white",
              font=("맑은 고딕", 10), relief="flat").pack(fill="x", pady=(0, 1))
    app._calib_var = tk.StringVar(
        value="캘리브레이션: 로드됨" if app._calib.is_solved else "캘리브레이션: 없음")
    tk.Label(parent, textvariable=app._calib_var, bg=bg, fg=dim,
             font=("맑은 고딕", 9)).pack(anchor="w")


# ===========================================================================
# 8) 종료 정리 + main — Tk 인스턴스화는 여기(__main__)에서만
# ===========================================================================
def _cleanup_vla(app: Any) -> None:
    """종료 정리(스펙 §2e-5): VLA 카메라 해제 + 우리가 띄운 llama-server 종료."""
    app._vla_cam_running = False
    cam = getattr(app, "_vla_cam", None)
    app._vla_cam = None
    if cam is not None:
        try:
            cam.release()
        except Exception:
            pass
    proc = getattr(app, "_server_proc", None)
    app._server_proc = None
    if proc is not None:
        try:
            proc.terminate()
        except Exception:
            pass


def _find_estop_button(app: Any) -> Any:
    """LessonGUI 위젯 트리에서 E-STOP(비상정지) 버튼을 찾는다(없으면 None).

    LessonGUI 가 버튼 참조를 노출하지 않으므로 텍스트("비상정지")로 찾아 command 를
    재바인딩한다 — _on_close 를 root.protocol 로 재등록하는 것과 동일하게, 이미
    바인딩된 콜백을 감싸기 위한 훅.
    """
    root = getattr(app, "root", None)
    if root is None or tk is None:
        return None
    stack = [root]
    while stack:                                  # 유한 순회(위젯 트리)
        w = stack.pop()
        try:
            if isinstance(w, tk.Button) and "비상정지" in str(w.cget("text")):
                return w
        except Exception:
            pass
        try:
            stack.extend(w.winfo_children())
        except Exception:
            pass
    return None


def main() -> None:
    """GUI 를 띄운다(Tk 인스턴스화는 이 함수 안에서만 — 헤드리스 스모크 유지)."""
    app = LessonGUI(
        title="H1 · 자연어로 로봇 제어 (+VLA 보고 집기)",
        camera_index=config.CAM_TABLE,            # 패시브 작업공간 뷰(색검출 없음)
        use_robot=True,
        build_controls=build_controls,
        on_canvas_click=on_canvas_click,          # 캘리브레이션/검증 클릭
        info=INFO,
    )
    # 종료 훅: LessonGUI 기본 정리(내장 카메라/로봇) 앞에 VLA 자원 정리를 끼운다.
    base_close = app._on_close

    def _close() -> None:
        _cleanup_vla(app)
        base_close()

    app.root.protocol("WM_DELETE_WINDOW", _close)

    # E-STOP 훅: 비상정지 시 (1) 진행 중 _execute_on_robot 루프를 즉시 중단시키고
    #   (2) 대기 중 확인 게이트를 취소한 뒤 (3) LessonGUI 기본 비상정지를 호출한다.
    #   (_on_close 를 감싸는 것과 동일한 패턴 — 이미 바인딩된 콜백을 감싼다.)
    base_estop = app._estop

    def _estop_all() -> None:
        app._abort.set()                          # 진행 중 시퀀스 즉시 중단 신호
        _cancel_pending(app)                      # 대기 중 확인 게이트 취소(로봇 안 움직임)
        base_estop()                              # LessonGUI 기본 비상정지(흡착/그리퍼 OFF)

    app._estop = _estop_all
    estop_btn = _find_estop_button(app)
    if estop_btn is not None:
        try:
            estop_btn.configure(command=_estop_all)
        except Exception:
            pass
    app.run()


if __name__ == "__main__":
    main()


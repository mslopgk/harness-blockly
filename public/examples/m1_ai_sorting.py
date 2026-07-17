# -*- coding: utf-8 -*-
"""[M1] AI 비전 색상 분류 GUI — 단일 파일(standalone) 버전.

원본(dobot-main/.../m1_color_sort/gui.py + 의존 모듈들: common.config /
common.safety / common.vision / common.dobot_ctl / common.gui /
m1_color_sort.solution / h2_teleop.solution)을 **하나의 파이썬 파일**로 합친 것.

자동 생성물 — 로직은 원본과 동일하다(중복 구현/재작성 아님). 여러 모듈을 한 네임스페이스로
평탄화하고, config./safety. 같은 모듈 한정 참조가 이 파일 자신을 가리키도록 alias 처리했다.

실행:  python m1_color_sort_standalone.py     (하드웨어 없으면 자동 mock)
필요:  tkinter(표준), 선택적으로 opencv-python / pillow / numpy / pydobot.
"""
from __future__ import annotations

import sys as _sys

# ── 패키지 평탄화용 self-alias ───────────────────────────────────────────────
# 원본은 common 패키지로 나뉘어 `config.X` / `safety.X` / `_config` / `_accel`
# 처럼 모듈을 한정해 서로를 참조했다. 단일 파일에서는 그 이름들이 모두 '이 모듈'을
# 가리키게 하면, 아래에 이어붙인 각 원본 코드의 참조가 그대로 동작한다.
config  = _sys.modules[__name__]   # config.WORKSPACE / config.is_mock() ...
safety  = _sys.modules[__name__]   # safety.check_move / safety.clamp_move ...
_config = _sys.modules[__name__]   # common.vision 내부 별칭
_accel  = None                     # 선택적 GPU 가속(accel) 비활성 → 순수 cv2 경로

# numpy: 아핀 캘리브레이션(estimate_affine)·일부 비전 경로에서 사용(없으면 안내).
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
# ── h2_teleop/solution.py — estimate_affine / apply_affine
# ==============================================================================

def estimate_affine(correspondences):
    """대응점들로 아핀 변환행렬 M(2x3)을 최소제곱으로 추정한다.

    모델:  [rx]   [ a  b  c ] [cx]
           [ry] = [ d  e  f ] [cy]
                              [ 1 ]
    즉 미지수 6개(a..f)를 N개 대응점(각 2식)으로 푼다. N>=3이면 유일해/과결정.

    인자
      correspondences: [((cx,cy),(rx,ry)), ...]  최소 3쌍 권장.
    반환
      np.ndarray shape (2,3)  — 아핀 행렬 M.
    예외
      ValueError: 대응점이 3쌍 미만이거나 numpy 부재 시(학생용 한국어 메시지).
    """
    # numpy 가 없으면 이 차시는 진행 불가 → 명확히 안내
    if not _HAS_NUMPY:
        raise ValueError("이 차시는 numpy가 필요합니다. `pip install numpy` 후 실행하세요.")
    # 대응점은 미지수 6개를 풀기 위해 최소 3쌍(=6식) 필요
    if correspondences is None or len(correspondences) < 3:
        raise ValueError("대응점이 최소 3쌍 필요합니다(현재 "
                         f"{0 if not correspondences else len(correspondences)}쌍).")

    # 설계행렬 A(2N x 6)와 관측벡터 b(2N) 구성
    A_rows = []   # 각 대응점이 2개의 행(rx식, ry식)을 만든다
    b_rows = []   # 대응되는 로봇 좌표값
    for (cx, cy), (rx, ry) in correspondences:
        # rx = a*cx + b*cy + c*1   → 계수 [cx, cy, 1, 0, 0, 0]
        A_rows.append([cx, cy, 1.0, 0.0, 0.0, 0.0])
        b_rows.append(rx)
        # ry = d*cx + e*cy + f*1   → 계수 [0, 0, 0, cx, cy, 1]
        A_rows.append([0.0, 0.0, 0.0, cx, cy, 1.0])
        b_rows.append(ry)

    A = np.array(A_rows, dtype=float)   # (2N, 6) 설계행렬
    b = np.array(b_rows, dtype=float)   # (2N,)  관측벡터

    # 최소제곱해: ||A·p - b|| 최소화하는 p(6,) = [a,b,c,d,e,f]
    p, *_ = np.linalg.lstsq(A, b, rcond=None)

    # 6개 파라미터를 2x3 행렬로 재배열해 반환
    return p.reshape(2, 3)
def apply_affine(M, point):
    """추정된 아핀행렬 M으로 카메라 점을 로봇 좌표(mm)로 사상한다(순수함수).

    인자
      M: np.ndarray(2,3) 아핀행렬.
      point: (cx, cy) 카메라(픽셀) 좌표.
    반환
      (rx, ry) 로봇 평면 좌표(float, mm).
    """
    cx, cy = point                       # 카메라 점 분해
    vec = np.array([cx, cy, 1.0])        # 동차좌표(끝에 1 추가) — 평행이동 c,f 반영
    rx, ry = M.dot(vec)                  # M(2x3) · vec(3,) = (2,) → (rx, ry)
    return float(rx), float(ry)          # 파이썬 float 로 정리해 반환


# ==============================================================================
# ── m1_color_sort/solution.py
# ==============================================================================

"""m1_color_sort/solution.py — [M1·중등부] AI 비전 색상 분류 스마트팩토리 (모범답안)

차시 개요 (110분 · 5E · Logic-First, Syntax-Later · 산업연계 PBL)
----------------------------------------------------------------
[문제상황] 스마트팩토리 컨베이어에 색이 뒤섞인 부품이 흘러온다. 사람이 일일이
           고르면 느리고 실수가 잦다. → "색을 보고(센서/비전) 스스로 판단(if-분기)해서
           색깔별 상자에 자동으로 담는 로봇"을 만들자.
[해결흐름] 카메라 프레임 획득 → OpenCV 색검출(+YOLO 객체탐지 옵션)으로 부품 인식
           → 색상에 따라 서로 다른 목적지 좌표로 픽앤플레이스(그리퍼 잡기/놓기).
           (엔드이펙터는 config.EFFECTOR 로 추상화 — 실측 기본은 '그리퍼'.)
[학습목표] 비전 데이터(색)를 조건문(if/elif/else)으로 분기하는 '판단 로직'을 설계하고,
           안전(작업영역·Z하강)을 지키며 로봇을 제어한다.

블록 ↔ 파이썬 대응 (중등부 특이사항)
------------------------------------
각 핵심 줄 위에 "# [블록] ~블록에 해당" 주석을 달아, 블록코딩 플랫폼의 블록과
파이썬 한 줄이 1:1로 대응됨을 보인다. (Logic-First: 먼저 흐름(블록)으로 사고 → Syntax-Later)

공통 라이브러리 (CONTRACTS.md)
------------------------------
- common.dobot_ctl.get_robot()    : 로봇 제어(하드웨어 없으면 MockDobot 자동)
- common.vision.Camera/detect_colors/YoloDetector : 비전 입력
- common.safety.check_move/scan_code              : 안전 검사
- common.config.is_mock()                         : mock 자동판정

하드웨어/키 없이 실행
---------------------
    set CURRICULUM_FORCE_MOCK=1   (또는 키/하드웨어 없으면 자동 mock)
    python m1_color_sort/solution.py
→ 합성 프레임의 red/green/blue 블록을 검출해 색깔별 좌표로 분류하는 전 과정을 시연한다.

로봇 좌표 근거: docs/두봇_라이트_API.md (좌표계 84~87행, 픽앤플레이스 251~264행)
"""

# ── sys.path 부트스트랩 2줄 (COR: common 패키지를 어디서 실행해도 import 가능하게) ──
import os, sys; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# COR: 위 한 줄로 코드 루트(taskB_curriculum)를 import 경로 맨 앞에 추가한다.

import time  # COR: 각 동작 시간 측정/로그용(표준 라이브러리)

# COR: 공통 라이브러리 import — 로봇/비전/안전/설정을 한 곳에서 가져온다.
pass
pass
pass
pass


# ===========================================================================
# 1) 색상 → 분류 좌표 매핑  (스마트팩토리의 "색깔별 적재 상자" 정의)
#    값은 docs/두봇_라이트_API.md 픽앤플레이스 예제와 WORKSPACE(180~320, -150~150) 안쪽.
#    z_approach: 물체 위 안전 접근 높이 / z_pick: 집을 때 하강 높이(작업영역 하한 -60 이상)
# ===========================================================================
# COR: 색깔별 목적지(드롭 좌표)와 픽 높이를 사전(dict)으로 정의 → if 분기의 데이터 출처.
SORT_BINS = {
    # 빨강 부품 → 왼쪽 앞 상자
    "red":   {"drop": (210, -120, 40), "label": "1번(빨강) 상자"},
    # 초록 부품 → 가운데 앞 상자
    "green": {"drop": (250, 0, 40),    "label": "2번(초록) 상자"},
    # 파랑 부품 → 오른쪽 앞 상자
    "blue":  {"drop": (210, 120, 40),  "label": "3번(파랑) 상자"},
}

# COR: 어느 색에도 해당하지 않을 때(불량/미지정) 보내는 '리젝트' 위치.
REJECT_BIN = {"drop": (300, 0, 60), "label": "검사대(미분류)"}

# COR: 컨베이어에서 부품을 집는 가상의 픽업 지점(카메라 인식 후 집는 곳).
PICK_POINT = (220, 0)          # (x, y) — z 는 접근/하강 높이를 따로 지정
Z_APPROACH = 50                # COR: 물체 위 안전 접근 높이(mm). 충돌 없이 위에서 정렬.
# 집기(그래스프) 하강 높이(mm) — 실측 캘리브레이션값(config.GRASP_Z).
#   실제 두봇 라이트 + 그리퍼로 검증: 초록 매트 위 블록 몸통을 감싸는 높이(z=-25).
#   교구/책상 높이가 다르면 common/config.py 의 GRASP_Z(또는 DOBOT_GRASP_Z)로 조정한다.
GRASP_Z = getattr(config, "GRASP_Z", -25)   # COR: 집기 높이(mm). WORKSPACE z 하한(-60)보다 위 → 안전.
# 호환용 별칭: 기존 이름(Z_PICK)을 GRASP_Z 로 맞춘다(다른 곳에서 참조해도 동일 값).
Z_PICK = GRASP_Z
# 튕김 방지용 중간 들기 높이(mm). 그리퍼를 닫은 직후 천천히 한 번 들어 블록이 튕기지 않게 한다.
Z_LIFT_MID = max(GRASP_Z + 20, -5)          # COR: 집은 직후 살짝 드는 중간높이(실측 휴리스틱)


# ===========================================================================
# 2) 색 판단 로직 (핵심: if-분기) — "이 색이면 어디로 보낼까?"
#    Logic-First 의 심장. 비전 결과(색 이름)를 받아 목적지를 결정한다.
# ===========================================================================
def decide_destination(color: str) -> dict:
    """검출된 색 이름을 받아 보낼 상자(목적지 dict)를 결정한다.

    반환: {"drop": (x,y,z), "label": str}
    """
    # [블록] "만약 <색 = 빨강> 이면" 블록에 해당
    if color == "red":
        return SORT_BINS["red"]          # COR: 빨강 → 1번 상자
    # [블록] "아니고 만약 <색 = 초록> 이면" 블록에 해당
    elif color == "green":
        return SORT_BINS["green"]        # COR: 초록 → 2번 상자
    # [블록] "아니고 만약 <색 = 파랑> 이면" 블록에 해당
    elif color == "blue":
        return SORT_BINS["blue"]         # COR: 파랑 → 3번 상자
    # [블록] "그 외에는" 블록에 해당
    else:
        return REJECT_BIN                # COR: 미지정 색 → 검사대로 리젝트


# ===========================================================================
# 3) 픽앤플레이스 1회 동작 (집기 → 들기 → 목적지 이동 → 놓기)
#    docs/두봇_라이트_API.md 251~264행 픽앤플레이스 시퀀스를 공통 래퍼로 옮긴 형태.
# ===========================================================================
def pick_and_place(bot, pick_xy, dest):
    """한 부품을 픽업 지점에서 집어 목적지(dest['drop'])에 놓는다.

    bot     : RobotController(get_robot())
    pick_xy : (x, y) 픽업 지점
    dest    : {"drop": (x,y,z), "label": str}
    """
    px, py = pick_xy                     # COR: 픽업 좌표 분해
    dx, dy, _dz = dest["drop"]           # COR: 드롭 x,y 만 사용. z(=SORT_BINS 의 40)는 참조용이며
    #       실제 놓기 하강 높이는 아래 PLACE_Z(=GRASP_Z)를 쓴다(아래 설명 참조).
    # --- 놓기 높이 = 집은 높이(GRASP_Z) ---
    #   [실측 버그수정] 기존엔 dz(=SORT_BINS 의 40)까지만 내려가 grasp(False)로 풀어,
    #   집은 높이(GRASP_Z=-25)보다 ~65mm 위에서 블록을 '툭' 떨어뜨렸다.
    #   평평한 책상 가정(집는 면 == 놓는 면 높이)에서, 놓을 때도 GRASP_Z 까지 내려가
    #   살살 내려놓는다. (SORT_BINS 의 x,y 는 그대로 분류함 위치로 사용)
    PLACE_Z = GRASP_Z                    # COR: 놓기 하강 높이 = 집은 높이(책상면). dz 대신 사용.

    # --- 안전가드: 이동 전 모든 목표점이 작업영역 안인지 먼저 검사(위험 동작 전 safety) ---
    for (tx, ty, tz, what) in [
        (px, py, Z_APPROACH, "픽업 접근"),
        (px, py, GRASP_Z,    "픽업 하강(그래스프)"),
        (px, py, Z_LIFT_MID, "튕김방지 중간들기"),
        (dx, dy, Z_APPROACH, "드롭 접근"),
        (dx, dy, PLACE_Z,    "드롭 하강(놓기, GRASP_Z)"),
    ]:
        # [블록] "만약 <좌표가 안전영역 밖> 이면 멈춤" 안전블록에 해당
        ok, msg = check_move(tx, ty, tz)         # COR: safety 로 좌표 사전검사
        if not ok:                                # COR: 위험하면 동작 중단(거부)
            print(f"  [안전중단] {what} 좌표가 위험합니다 → {msg.splitlines()[0]}")
            return False                          # COR: 이 부품은 처리하지 않음

    # --- 픽앤플레이스 시퀀스 (move_to 는 내부에서 한 번 더 클램프되는 이중 안전) ---
    # [블록] "픽업 위치 위로 이동" 블록에 해당
    bot.move_to(px, py, Z_APPROACH)      # COR: 1) 물체 위 안전높이로 접근
    # [블록] "아래로 내려가기" 블록에 해당
    bot.move_to(px, py, GRASP_Z)         # COR: 2) 집을 높이(실측 GRASP_Z)까지 하강
    # [블록] "그리퍼 잡기" 블록에 해당
    bot.grasp(True)                      # COR: 3) 집기 ON(그리퍼 닫기/흡착) → 부품 잡기
    # [블록] "살짝 들어올리기(튕김 방지)" 블록에 해당
    bot.move_to(px, py, Z_LIFT_MID)      # COR: 4a) 닫은 직후 중간높이로 천천히 한 번 들기(튕김 방지)
    # [블록] "들어올리기" 블록에 해당
    bot.move_to(px, py, Z_APPROACH)      # COR: 4b) 다시 안전높이로 완전히 들어올림
    # [블록] "목적지 위로 이동" 블록에 해당
    bot.move_to(dx, dy, Z_APPROACH)      # COR: 5) 목적 상자 위로 수평 이동
    # [블록] "내려놓기 높이로 이동" 블록에 해당
    bot.move_to(dx, dy, PLACE_Z)         # COR: 6) 집은 높이(GRASP_Z, 책상면)까지 하강 → 살살 내려놓기
    # [블록] "그리퍼 놓기" 블록에 해당
    bot.grasp(False)                     # COR: 7) 집기 OFF(그리퍼 열기/흡착 해제) → 부품 놓기
    # [블록] "들어올리기" 블록에 해당
    bot.move_to(dx, dy, Z_APPROACH)      # COR: 8) 안전높이로 복귀(다음 동작 준비)
    return True                          # COR: 정상 처리 완료


# ===========================================================================
# 3-b) 검출 robust화: 배경(초록 매트) 제외 + 최소면적 + 색당 가장 큰 1개
#    실측 문제: 카메라가 '초록 매트(배경)'를 거대한 초록 블록으로 다수 검출한다.
#    → 실제 부품 블록만 남기는 검증된 휴리스틱을 적용한다.
# ===========================================================================
def select_blocks(blocks, frame=None, min_area=1500):
    """검출 결과(blocks)에서 실제 부품 블록만 골라낸다(배경 매트 제외).

    실측 버그 대응(핵심)
    --------------------
    사용자의 매트가 '초록색'이라, 카메라에 매트가 작게 보이면 면적 우세 휴리스틱을
    못 넘겨 '초록 매트 조각'이 '초록 블록'으로 오검출됐다. 그래서 매트색을 명시 목록
    (config.BACKGROUND_COLORS, 기본 ["green"])으로 두고 **항상 무조건 제외**한다.

    제외 규칙(둘 중 하나라도 배경이면 제외):
      A) config.BACKGROUND_COLORS 에 속한 색은 **항상 배경(매트)으로 제외**(주 규칙).
      B) (보조) 면적 우세 자동판정: 가장 넓게 깔린 색이 (다음으로 넓은 색의 3배 이상)이고,
         (frame 이 주어지면 frame 전체 면적의 15% 이상)이면 그 색도 배경으로 간주.

    그 외:
      - min_area 미만의 작은 블롭은 잡음으로 제거한다.
      - 남은 색마다 '가장 큰 영역 1개'만 대표로 남긴다(중복 검출 정리).

    규칙 B 의 배경 판단이 불가하거나(색이 1개뿐 등) 조건을 만족하지 않으면 규칙 B 로는
    어떤 색도 제외하지 않는다 → 배경색(A)만 빠지고 균등한 나머지 블록은 그대로 통과한다.

    Args:
        blocks   : detect_colors(frame) 결과. [{color,bbox,center,area}, ...]
        frame    : (선택) 원본 프레임. frame.shape 로 전체 면적을 구해 배경 판단을 강화.
        min_area : 이 면적 미만 블록은 잡음으로 제거(px). 실측 기본 1500.

    Returns:
        list[dict] : 거른 블록 목록(색당 최대 1개), 면적 내림차순.
    """
    blocks = list(blocks or [])
    if not blocks:
        return []

    # --- (1) 잡음(min_area 미만) 제거 — 배경 판정 전에 먼저 거른다.
    #         (작은 잡음 블롭이 색별 총면적/배경 판정을 왜곡하지 않도록)
    candidates = [b for b in blocks if float(b.get("area", 0.0)) >= min_area]
    if not candidates:
        return []

    # --- (2) 배경색 집합 구성(규칙 A 매트색 + 규칙 B 면적우세) — 공용 헬퍼 ---
    background_colors = _compute_background_colors(candidates, frame)

    # --- (3) 배경색 제외 + 색마다 가장 큰 영역 1개만 대표로 남김 ---
    best_by_color: dict = {}
    for b in candidates:
        c = b.get("color")
        if c in background_colors:
            continue                       # 배경(매트)은 통째로 제외(규칙 A 또는 B)
        if c not in best_by_color or float(b.get("area", 0.0)) > float(best_by_color[c].get("area", 0.0)):
            best_by_color[c] = b

    # 면적 내림차순으로 정렬해 반환(픽 우선순위 일관)
    return sorted(best_by_color.values(), key=lambda d: float(d.get("area", 0.0)), reverse=True)


def _compute_background_colors(candidates, frame=None, use_area_dominance=True):
    """검출 후보들에서 '배경(매트)으로 간주할 색 집합'을 만든다(규칙 A + 규칙 B).

    규칙 A(주): config.BACKGROUND_COLORS(기본 ["green"]) 는 항상 배경.
    규칙 B(보조): 색이 2종 이상일 때, 가장 넓은 색이 (2등의 3배 이상)이고
                 (frame 주어지면 전체 면적의 15% 이상)이면 그 색도 배경으로 간주.

    use_area_dominance: 규칙 B 적용 여부.
      - True(기본): 컨베이어 단일 블록(select_blocks)용 — 매트가 BACKGROUND_COLORS 에
        없을 때도 압도적으로 넓은 색을 배경으로 자동 제외(보조 안전망).
      - False: '다중 블록 자동분류'(select_all_blocks)용 — 서로 다른 색이 섞여 있을 때
        가장 많은/큰 '실제 부품 색'을 배경으로 오인 제외하면 안 되므로 규칙 B 를 끈다.
        (배경은 규칙 A 의 명시 목록 BACKGROUND_COLORS 로만 제외)
    select_blocks / select_all_blocks 가 공유한다(중복 제거).
    """
    background_colors = set(getattr(config, "BACKGROUND_COLORS", ["green"]) or [])

    if not use_area_dominance:
        return background_colors      # 규칙 A 만(다중 블록: 실제 색을 배경으로 오인 금지)

    # 색별 총면적 합산(규칙 B 면적 우세 판정용)
    area_by_color: dict = {}
    for b in candidates:
        c = b.get("color")
        area_by_color[c] = area_by_color.get(c, 0.0) + float(b.get("area", 0.0))

    if len(area_by_color) >= 2:
        ranked = sorted(area_by_color.items(), key=lambda kv: kv[1], reverse=True)
        top_color, top_area = ranked[0]
        _, second_area = ranked[1]
        dominates = top_area >= second_area * 3       # 1등이 2등의 3배 이상
        big_enough = True
        frame_area = _frame_area(frame)
        if frame_area is not None:
            big_enough = top_area >= frame_area * 0.15  # 화면의 15% 이상
        if dominates and big_enough:
            background_colors.add(top_color)
    return background_colors


def select_all_blocks(blocks, frame=None, min_area=1500):
    """배경(매트) 제외 + 잡음 제거 후 **모든** 실제 부품 블록을 반환한다.

    select_blocks 와 달리 색당 1개로 합치지 않고, **같은 색 여러 개도 각각 보존**한다.
    여러 위치에 흩어진 블록을 하나씩 집어 분류하는 '다중 블록 자동분류'(GUI)용.

    Args:
        blocks   : detect_colors(frame) 결과. [{color,bbox,center,area}, ...]
        frame    : (선택) 원본 프레임. 배경 면적 판정(규칙 B) 강화.
        min_area : 이 면적 미만 블록은 잡음으로 제거(px).

    Returns:
        list[dict] : 거른 블록 목록(전부), 면적 내림차순.
    """
    blocks = list(blocks or [])
    if not blocks:
        return []
    candidates = [b for b in blocks if float(b.get("area", 0.0)) >= min_area]
    if not candidates:
        return []
    # 다중 블록 모드: 규칙 B(면적 우세) 끔 — 가장 많은/큰 '실제 색'을 배경으로 오인 제외 방지.
    background_colors = _compute_background_colors(candidates, frame, use_area_dominance=False)
    kept = [b for b in candidates if b.get("color") not in background_colors]
    # 면적 내림차순. 동일 면적이면 center(x,y)로 안정 정렬 → 재검출 간 픽 순서가 흔들리지 않게.
    def _sortkey(d):
        cx, cy = d.get("center", (0, 0))
        return (-float(d.get("area", 0.0)), float(cx), float(cy))
    return sorted(kept, key=_sortkey)


def _frame_area(frame):
    """frame 의 전체 픽셀 면적(W*H)을 구한다. 알 수 없으면 None.

    numpy ndarray 든 _FakeFrame 이든 shape=(H,W,...) 를 가지면 면적을 계산한다.
    """
    shape = getattr(frame, "shape", None)
    if shape is None or len(shape) < 2:
        return None
    try:
        return float(shape[0] * shape[1])     # H * W
    except Exception:
        return None


# ===========================================================================
# 4) 비전 → 판단 → 동작 전체 파이프라인 (한 프레임 처리)
# ===========================================================================
def sort_one_frame(bot, frame, use_yolo=False):
    """한 프레임에서 '가장 큰 블록 1개'만 검출해 분류 픽앤플레이스를 수행한다.

    컨베이어 모델(실측 정합)
    ------------------------
    M1 은 고정 픽업점(PICK_POINT)에서 집는 '컨베이어' 모델이다. 한 프레임에 여러
    색이 보여도 픽업점은 하나뿐이므로, 검출된 색마다 같은 좌표(220,0)에서 여러 번
    집으면 헛집기/오분류가 난다(실측: 초록+빨강 2개로 인식해 빨강을 초록 상자로 잘못
    옮김). 그래서 한 프레임에서는 **가장 큰 블록 1개만** 집어 옮긴다.
      - 2개 이상 검출 : '가장 큰 1개만 처리' 로그 후 1개만 픽앤플레이스.
      - 0개 검출      : '블록 없음' 로그 후 아무 동작도 하지 않음(헛집기 금지).

    반환: 처리 요약 리스트 [{color, dest_label, placed}] (처리한 블록만, 최대 1개)
    """
    # [블록] "카메라에서 색 찾기" 블록에 해당
    #   검출 직후 select_blocks 로 배경(매트) 제외 + 잡음 제거 + 색당 1개로 정제한다.
    #   (반환은 면적 내림차순 → 맨 앞이 가장 큰 블록)
    blocks = select_blocks(detect_colors(frame), frame)  # COR: 색검출 → 실측 휴리스틱 정제

    # (옵션) YOLO 객체탐지: "정말 부품(cube)인지" 한 번 더 확인하는 산업용 보조검증
    if use_yolo:
        # [블록] "AI 물체 인식 켜기" 블록에 해당
        objects = YoloDetector().detect(frame)   # COR: YOLO 로 객체 박스 검출(mock 캔드)
        n_cube = sum(1 for o in objects if o["label"] == "cube")  # COR: cube 개수 집계
        print(f"  [YOLO] 객체 {len(objects)}개 검출(cube {n_cube}개) — 색검출 보조검증")

    print(f"  [비전] 색 블록 {len(blocks)}개 검출(매트 제외·정제 후)")

    # [블록] "만약 <블록이 없으면> 아무것도 안 하기" 블록에 해당
    if not blocks:                        # COR: 0개 → 헛집기 금지(동작 안 함)
        print("  - 블록 없음 → 이번 프레임은 처리하지 않음(헛집기 금지)")
        return []

    # [블록] "가장 큰 블록 1개만 고르기" 블록에 해당
    #   select_blocks 가 면적 내림차순으로 주므로 맨 앞이 가장 큰 블록.
    if len(blocks) >= 2:                  # COR: 2개 이상이면 가장 큰 1개만 처리한다고 안내
        others = ", ".join(b["color"] for b in blocks[1:])
        print(f"  - 블록 {len(blocks)}개 중 가장 큰 1개만 처리(나머지 [{others}]는 다음 프레임에서)")
    target = blocks[0]                    # COR: 컨베이어 모델 — 한 프레임에 한 블록만 집는다

    color = target["color"]               # COR: 처리할 블록의 색 이름
    # [블록] "색에 따라 목적지 정하기" 블록(=decide_destination)에 해당
    dest = decide_destination(color)      # COR: ★핵심 if-분기로 목적지 결정
    print(f"  - {color:6s} 검출 center={target['center']} → {dest['label']} 로 분류")
    # [블록] "픽앤플레이스 실행" 블록에 해당
    placed = pick_and_place(bot, PICK_POINT, dest)  # COR: 실제 집어 옮기기(1회)

    return [{"color": color, "dest_label": dest["label"], "placed": placed}]


# ===========================================================================
# 5) 데모 (mock) — 하드웨어/키 없이 끝까지 실행
#    컨베이어 모델: '한 프레임에 한 블록'을 차례로 흘려보내 하나씩 분류한다.
#    (if-분기 교육효과 유지: 프레임마다 색이 달라 red/blue/미지정 분기를 모두 시연)
# ===========================================================================
def _demo_frame(blocks):
    """데모용 가짜 프레임 — detect_colors 가 그대로 돌려줄 '검출 블록 목록'을 품는다.

    실 카메라가 없을 때도 '한 프레임 한 블록' 컨베이어 시나리오를 결정적으로
    재현하려고, frame 객체가 자기 검출결과(blocks)를 들고 다니게 한다.
    shape 도 제공해 select_blocks 의 배경 면적 판정(보조 규칙 B)이 동작하게 한다.
    """
    class _F:
        shape = (480, 640, 3)             # H, W, C — _frame_area 계산용
        def __init__(self, blocks):
            self.blocks = blocks
    return _F(blocks)


def _demo_block(color, area, center=(220, 240)):
    """데모용 검출 블록 한 건(색/면적/중심)."""
    return {"color": color, "area": float(area),
            "center": center, "bbox": (center[0] - 55, center[1] - 55, 110, 110)}





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
# ── m1_color_sort/gui.py — M1 화면/조작 로직 + main()
# ==============================================================================

"""m1_color_sort/gui.py — [M1] AI 비전 색상 분류 GUI (다중 블록·임의 위치 자동 분류)

강사/학생이 마우스로 직접 색상 분류 차시를 실행/테스트하는 GUI.

이번 버전의 핵심: **블록이 어느 위치에 있든, 여러 개가 있어도** 카메라로 전부
찾아 하나씩 집어 색깔별로 자동 분류한다(고정 픽업점 모델 → 위치기반 모델로 업그레이드).

동작 원리(왜 캘리브레이션이 필요한가)
--------------------------------------
카메라는 픽셀(0~W, 0~H) 좌표로 블록을 본다. 로봇은 mm 좌표로 움직인다. 둘을 잇는
**아핀 변환행렬 M**(픽셀→로봇)을 한 번 추정(캘리브레이션)해 두면, 화면 어디에 있는
블록이든 그 픽셀중심을 로봇 좌표로 바꿔 정확히 집을 수 있다(H2 텔레옵의 좌표변환과 동일 원리).

카메라가 팔 말단에 달렸든 책상 위(노트북 웹캠)든 동일하게 동작하도록, **검출은 항상
같은 '관측 자세'에서** 수행한다(그 자세에서 캘리브레이션 → 그 자세에서 검출 → 일관).

사용 순서(우측 패널)
--------------------
 1) '로봇 연결'.
 2) 팔을 카메라가 작업영역을 잘 보는 자세로 두고 '관측자세 저장'(생략 시 캘리브레이션
    시작 시 현재 자세가 자동 저장됨).
 3) [캘리브레이션] 블록 하나를 매트에 놓고 → 화면에서 그 블록을 **클릭**(픽셀 마킹)
    → jog 버튼으로 팔 끝을 그 블록 바로 위로 이동 → '대응점 기록'. 위치를 바꿔 3회 이상
    반복 → '캘리브레이션 완료'. (재투영 오차가 작게 나오면 정확)
 4) 블록 여러 개를 아무 데나 올려놓고 '자동 분류 시작' → 큰 것부터 하나씩 집어
    색깔별 상자로 옮기고, 다 없어지면 자동 종료. '정지'로 중단.

모든 비전/판단/동작 로직은 solution.py 함수를 재사용한다(중복 구현 금지):
  detect_colors, select_all_blocks, decide_destination, pick_and_place,
  estimate_affine, apply_affine

하드웨어/카메라/키 없이도 import 는 성공해야 한다(창/카메라/로봇은
`if __name__ == "__main__":` 아래에서만 연다).
"""

# ── sys.path 부트스트랩: 코드 루트(taskB_curriculum)를 import 경로에 추가 ──
import os, sys

import threading
import time

# 비전(색검출) — 카메라/자동분류 스레드에서 사용
pass
pass

# solution 의 판단/동작/좌표변환 로직 재사용(중복 구현 금지)
pass
pass

# cv2 는 오버레이용. import 가드(없어도 모듈 import 는 성공해야 함).
try:
    import cv2
except Exception:
    cv2 = None


# 색 이름 → BGR(오버레이 색)
_DRAW_BGR = {
    "red":   (0, 0, 255),
    "green": (0, 200, 0),
    "blue":  (255, 80, 0),
    "yellow": (0, 220, 220),
    "pink":  (200, 0, 200),
}

JOG_STEP_DEFAULT = 10.0    # 기본 jog 한 칸(mm)
SETTLE_SEC = 0.6           # 관측 자세 이동 후 카메라/팔 안정화 대기(초)
MAX_PICKS = 30             # 자동 분류 1회 최대 픽 수(무한루프 방지 안전상한)


# ===========================================================================
# process_frame — 매 프레임: 모든 블록 검출·오버레이 + 마킹 픽셀 표시
# ===========================================================================
def make_process_frame():
    def process_frame(frame, app):
        if cv2 is None:
            return frame
        try:
            blocks = select_all_blocks(detect_colors(frame), frame)
        except Exception as e:
            app.log(f"[검출 오류] {type(e).__name__}: {e}")
            blocks = []
        app._blocks = blocks   # 자동 분류 worker 는 자체 캡처를 쓰지만, 표시/상태용으로 보관

        # 검출된 모든 블록 오버레이(번호 + 색)
        for i, b in enumerate(blocks, start=1):
            color = b.get("color", "?")
            draw = _DRAW_BGR.get(color, (255, 255, 255))
            bbox = b.get("bbox")
            if bbox:
                x, y, w, h = (int(v) for v in bbox)
                cv2.rectangle(frame, (x, y), (x + w, y + h), draw, 2)
            center = b.get("center")
            if center:
                cx, cy = int(center[0]), int(center[1])
                cv2.circle(frame, (cx, cy), 5, draw, -1)
                cv2.putText(frame, f"{i}.{color}", (cx - 24, cy - 12),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, draw, 2, cv2.LINE_AA)

        # 캘리브레이션 마킹 픽셀(노란 십자) 표시
        mp = getattr(app, "_marked_pixel", None)
        if mp is not None:
            mx, my = int(mp[0]), int(mp[1])
            cv2.drawMarker(frame, (mx, my), (0, 255, 255), cv2.MARKER_CROSS, 22, 2)
            cv2.putText(frame, "marked", (mx + 8, my - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2, cv2.LINE_AA)

        # 상태줄
        calib = "캘리브레이션됨" if getattr(app, "_M", None) is not None else "미캘리브레이션"
        if getattr(app, "_auto_running", False):
            app.set_status(f"자동 분류 중… (검출 {len(blocks)}개) [{calib}]")
        else:
            app.set_status(f"검출 {len(blocks)}개 · {calib} · 대응점 {len(getattr(app,'_calib_pairs',[]))}개")
        return frame

    return process_frame


# ===========================================================================
# 캔버스 클릭 → 캘리브레이션 픽셀 마킹
# ===========================================================================
def on_canvas_click(px, py, app):
    app._marked_pixel = (px, py)
    app.log(f"픽셀 마킹: ({px},{py}). 이제 팔 끝을 이 블록 바로 위로 jog 한 뒤 '대응점 기록'을 누르세요.")


# ===========================================================================
# 로봇 동작 헬퍼 (모두 별도 스레드에서 — UI 안 막음)
# ===========================================================================
def _need_robot(app):
    if app.robot is None:
        app.log("[안내] 먼저 '로봇 연결'을 누르세요.")
        app.set_status("로봇 미연결")
        return False
    return True


def _go_observe(app, settle=SETTLE_SEC):
    """관측 자세로 이동(없으면 현재 자세를 관측자세로 저장). worker 스레드에서 호출."""
    bot = app.robot
    if app._observe_pose is None:
        p = bot.get_pose()
        app._observe_pose = (p["x"], p["y"], p["z"], p["r"])
        app.log(f"관측 자세 자동 저장: ({p['x']:.0f},{p['y']:.0f},{p['z']:.0f}, r={p['r']:.0f})")
    x, y, z, r = app._observe_pose
    bot.move_to(x, y, z, r, wait=True)
    time.sleep(settle)


def on_save_observe(app):
    if not _need_robot(app):
        return
    def w():
        try:
            p = app.robot.get_pose()
            app._observe_pose = (p["x"], p["y"], p["z"], p["r"])
            app.log(f"관측 자세 저장: ({p['x']:.0f},{p['y']:.0f},{p['z']:.0f}, r={p['r']:.0f})")
            app.set_status("관측 자세 저장됨")
        except Exception as e:
            app.log(f"[관측자세 오류] {type(e).__name__}: {e}")
    threading.Thread(target=w, daemon=True).start()


def _jog(app, dx=0.0, dy=0.0, dz=0.0):
    if not _need_robot(app):
        return
    if getattr(app, "_auto_running", False):
        app.log("[안내] 자동 분류 중에는 jog 할 수 없습니다. 먼저 '정지'.")
        return
    def w():
        try:
            p = app.robot.get_pose()
            nx, ny, nz = p["x"] + dx, p["y"] + dy, p["z"] + dz
            app.robot.move_to(nx, ny, nz, p["r"], wait=True)
            app.set_status(f"위치 ≈ ({nx:.0f}, {ny:.0f}, {nz:.0f})")
        except Exception as e:
            app.log(f"[이동 오류] {type(e).__name__}: {e}")
    threading.Thread(target=w, daemon=True).start()


# ===========================================================================
# 캘리브레이션
# ===========================================================================
def on_record_point(app):
    if not _need_robot(app):
        return
    if getattr(app, "_marked_pixel", None) is None:
        app.log("[안내] 먼저 화면에서 블록을 클릭해 픽셀을 마킹하세요.")
        return
    def w():
        try:
            # 관측 자세가 아직 없으면 첫 기록 시점의 자세를 관측자세로 고정
            if app._observe_pose is None:
                p0 = app.robot.get_pose()
                app._observe_pose = (p0["x"], p0["y"], p0["z"], p0["r"])
                app.log("관측 자세를 현재 자세로 고정(검출은 항상 이 자세에서).")
            p = app.robot.get_pose()
            pair = (app._marked_pixel, (p["x"], p["y"]))
            app._calib_pairs.append(pair)
            app.log(f"대응점 {len(app._calib_pairs)} 기록: 픽셀{app._marked_pixel} ↔ "
                    f"로봇({p['x']:.0f},{p['y']:.0f})")
            app._marked_pixel = None
            # 기록 직후 관측 자세로 자동 복귀 → 팔 말단 카메라에서도 다음 점을 같은 시점에서
            # 클릭할 수 있다(수동으로 좌표 맞춰 되돌릴 필요 없음).
            app.log("관측 자세로 복귀 중…")
            _go_observe(app)
            if len(app._calib_pairs) >= 3:
                app.set_status(f"대응점 {len(app._calib_pairs)}개 — 다음 블록 클릭 또는 '캘리브레이션 완료'")
            else:
                app.set_status(f"대응점 {len(app._calib_pairs)}개 — 다음 블록 클릭 후 jog→기록")
        except Exception as e:
            app.log(f"[대응점 기록 오류] {type(e).__name__}: {e}")
    threading.Thread(target=w, daemon=True).start()


def _too_collinear(pairs):
    """캘리브레이션 픽셀점들이 거의 한 직선 위에 있으면 True(아핀이 부정확해짐).

    중심화한 픽셀좌표의 두 번째 특이값(2D 퍼짐의 약한 축)이 너무 작으면 직선에 가깝다.
    numpy 가 없으면 검사를 건너뛴다(False).
    """
    try:
        import numpy as _np
        pts = _np.array([[c[0], c[1]] for (c, _r) in pairs], dtype=float)
        pts = pts - pts.mean(axis=0)
        sv = _np.linalg.svd(pts, compute_uv=False)
        return len(sv) < 2 or sv[1] < 25.0   # 약한 축 퍼짐 < ~25px → 거의 일직선
    except Exception:
        return False


def on_finish_calib(app):
    pairs = list(getattr(app, "_calib_pairs", []))   # 스냅샷(기록 스레드와의 경합 방지)
    if len(pairs) < 3:
        app.log(f"[안내] 대응점이 최소 3개 필요합니다(현재 {len(pairs)}개).")
        return
    if _too_collinear(pairs):
        app.log("[거부] 대응점들이 거의 일직선입니다 → 변환이 부정확해집니다. "
                "작업영역 네 귀퉁이처럼 넓게 퍼뜨려 다시 찍으세요('캘리브레이션 초기화' 후).")
        app.set_status("대응점이 일직선 — 더 넓게 다시 캘리브레이션 필요")
        return
    try:
        M = estimate_affine(pairs)
        app._M = M
        # 재투영 오차(작을수록 정확) — 대응점을 다시 사상해 본다
        max_err = 0.0
        for (c, r) in pairs:
            pr = apply_affine(M, c)
            err = ((pr[0] - r[0]) ** 2 + (pr[1] - r[1]) ** 2) ** 0.5
            max_err = max(max_err, err)
        app.log(f"캘리브레이션 완료(대응점 {len(pairs)}개). 재투영 최대오차 {max_err:.1f} mm.")
        if max_err > 15:
            app.log("  ⚠ 오차가 큽니다(>15mm). 대응점을 더 넓게/정확히 다시 찍어보세요.")
        app.set_status(f"캘리브레이션됨(오차 {max_err:.1f}mm) — 자동 분류 가능")
    except Exception as e:
        app.log(f"[캘리브레이션 오류] {type(e).__name__}: {e}")


def on_clear_calib(app):
    app._calib_pairs = []
    app._M = None
    app._marked_pixel = None
    app.log("캘리브레이션 초기화(대응점·행렬 삭제).")
    app.set_status("미캘리브레이션")


# ===========================================================================
# 다중 블록 자동 분류
# ===========================================================================
def _block_key(b):
    """블록의 위치/색을 양자화한 식별키 — 재검출 간 같은 블록을 매칭(잔상/지터 흡수)."""
    cx, cy = b.get("center", (0, 0))
    return (b.get("color", "?"), round(float(cx) / 25.0), round(float(cy) / 25.0))


def _auto_worker(app):
    """관측자세 → 모든 블록 검출 → 큰 것부터 하나씩 집어 분류 → 재검출. 반복.

    도달 불가/반복 실패 블록은 '건너뜀(블랙리스트)' 처리하고 **나머지는 계속** 분류한다
    (블록 하나가 전체 배치를 멈추지 않게). 모든 블록이 처리/건너뜀되면 종료.
    """
    bot = app.robot
    M = app._M
    picks = 0
    skipped = set()         # 건너뛴 블록 키(도달 불가·반복 실패) → 다시 시도하지 않음
    attempts = {}           # 블록 키별 시도 횟수(같은 블록이 안 사라지면 누적 → 건너뜀)
    try:
        while app._auto_running and picks < MAX_PICKS:
            # 1) 관측 자세로 이동 후 안정화 → 신선한 프레임 확보(팔말단 카메라 일관성)
            _go_observe(app)
            if not app._auto_running:
                break
            with app._lock:
                frame = None if app._raw is None else app._raw.copy()
            if frame is None:
                time.sleep(0.1)
                continue
            blocks = select_all_blocks(detect_colors(frame), frame)
            # 처리 가능한(아직 건너뛰지 않은) 블록만 후보 — 면적 큰 순(select_all_blocks 보장)
            todo = [b for b in blocks if _block_key(b) not in skipped]
            if not todo:
                if blocks:
                    app.log(f"남은 {len(blocks)}개는 모두 '건너뜀' 처리됨 → 자동 분류 종료.")
                else:
                    app.log("남은 블록 없음 → 자동 분류 완료.")
                break

            # 2) 가장 큰 블록을 픽셀→로봇 변환해 집기
            target = todo[0]
            color = target.get("color", "?")
            center = target.get("center")
            key = _block_key(target)
            if not center:                       # center 누락 방어 → 건너뜀
                skipped.add(key)
                app.log(f"  - center 정보 없음({color}) → 건너뜀.")
                continue
            cx, cy = center

            # 같은 블록을 여러 번 시도했는데도 계속 검출되면(헛집기) 건너뛴다.
            attempts[key] = attempts.get(key, 0) + 1
            if attempts[key] > 2:
                skipped.add(key)
                app.log(f"  - {color} 블록이 반복 시도 후에도 남아 있어 건너뜁니다(캘리브레이션 확인).")
                continue

            rx, ry = apply_affine(M, (cx, cy))
            dest = decide_destination(color)
            app.log(f"[자동 {picks+1}] {color} @픽셀({cx:.0f},{cy:.0f}) → "
                    f"로봇({rx:.0f},{ry:.0f}) → {dest['label']}")
            if not app._auto_running:
                break
            ok = pick_and_place(bot, (rx, ry), dest)
            picks += 1
            if not ok:                            # 안전검사 거부(작업영역 밖 등) → 이 블록만 건너뜀
                skipped.add(key)
                app.log("  - 안전검사로 이 블록은 건너뜀(나머지는 계속).")
            # 루프 상단에서 다시 관측자세로 가 재검출
        if picks >= MAX_PICKS:
            app.log(f"[안전상한] 최대 {MAX_PICKS}회 픽에 도달해 정지합니다.")
    except Exception as e:
        app.log(f"[자동 분류 오류] {type(e).__name__}: {e}")
    finally:
        app._auto_running = False
        # 마무리 관측자세 복귀 — 단, 창이 닫히거나 로봇 연결이 끊긴 뒤엔 시도하지 않음(#종료가드)
        try:
            if getattr(app, "running", False) and app.robot is not None:
                _go_observe(app, settle=0.1)
        except Exception:
            pass
        app.log(f"자동 분류 종료(총 {picks}회 픽, 건너뜀 {len(skipped)}개).")
        app.set_status(f"대기 중 (총 {picks}회 분류)")


def on_auto_start(app):
    if not _need_robot(app):
        return
    if getattr(app, "_M", None) is None:
        app.log("[안내] 먼저 캘리브레이션을 완료하세요(픽셀→로봇 변환 필요).")
        app.set_status("미캘리브레이션 — 자동 분류 불가")
        return
    if getattr(app, "_auto_running", False):
        app.log("[안내] 이미 자동 분류 중입니다.")
        return
    app._auto_running = True
    app.log("자동 분류 시작 — 블록을 다 옮길 때까지 하나씩 처리합니다('정지'로 중단).")
    threading.Thread(target=_auto_worker, args=(app,), daemon=True).start()


def on_auto_stop(app):
    if getattr(app, "_auto_running", False):
        app._auto_running = False
        app.log("자동 분류 정지 요청 — 현재 동작을 마치고 멈춥니다.")
    else:
        app.log("[안내] 자동 분류가 실행 중이 아닙니다.")


# ===========================================================================
# 우측 패널 커스텀 위젯(jog 그리드 + 캘리브레이션 + 자동분류 버튼)
# ===========================================================================
def build_controls(parent, app):
    import tkinter as tk

    # build_controls 는 LessonGUI.__init__ 도중에 호출된다(=main()의 사후 초기화보다 먼저).
    # 따라서 여기서 차시 상태 기본값을 먼저 보장한다 — 특히 아래에서 직접 읽는 _jog_step 이
    # 없으면 AttributeError 로 build_controls 가 중간에 끊겨 jog 이하 버튼이 안 그려졌다(버그).
    for _k, _v in (("_blocks", []), ("_marked_pixel", None), ("_calib_pairs", []),
                   ("_M", None), ("_observe_pose", None),
                   ("_jog_step", JOG_STEP_DEFAULT), ("_auto_running", False)):
        if not hasattr(app, _k):
            setattr(app, _k, _v)

    def section(text):
        tk.Label(parent, text=text, bg="#2a2a3c", fg="#9ecbff",
                 font=("맑은 고딕", 10, "bold")).pack(anchor="w", pady=(10, 2))

    def btn(text, cmd, color="#3a3a52", small=False):
        b = tk.Button(parent, text=text, command=cmd, bg=color, fg="white",
                      font=("맑은 고딕", 10), relief="flat",
                      height=(1 if small else 1))
        b.pack(fill="x", pady=2)
        return b

    # --- 관측 자세 ---
    section("① 관측 자세 (카메라가 작업영역을 보는 자세)")
    btn("현재 자세를 관측자세로 저장", lambda: on_save_observe(app), "#2f6f4f")

    # --- jog 그리드 (팔 끝을 블록 위로 옮길 때 사용) ---
    section("② 팔 이동(jog) — 캘리브레이션용")
    grid = tk.Frame(parent, bg="#2a2a3c")
    grid.pack(fill="x", pady=2)

    def jbtn(g, txt, r, c, dx=0.0, dy=0.0, dz=0.0):
        b = tk.Button(g, text=txt, width=4,
                      command=lambda: _jog(app, dx=dx, dy=dy, dz=dz),
                      bg="#3a3a52", fg="white", font=("맑은 고딕", 9), relief="flat")
        b.grid(row=r, column=c, padx=2, pady=2, sticky="nsew")

    # 로봇 좌표: x=전후, y=좌우, z=상하. step 은 app._jog_step.
    s = app._jog_step
    jbtn(grid, "X+ 앞",  0, 1, dx=+s)
    jbtn(grid, "X- 뒤",  2, 1, dx=-s)
    jbtn(grid, "Y- 좌",  1, 0, dy=-s)
    jbtn(grid, "Y+ 우",  1, 2, dy=+s)
    jbtn(grid, "Z+ 상",  0, 3, dz=+s)
    jbtn(grid, "Z- 하",  2, 3, dz=-s)
    for c in range(4):
        grid.grid_columnconfigure(c, weight=1)

    # step 조절
    step_row = tk.Frame(parent, bg="#2a2a3c")
    step_row.pack(fill="x", pady=2)
    tk.Label(step_row, text="step(mm):", bg="#2a2a3c", fg="#e6e6e6",
             font=("맑은 고딕", 9)).pack(side="left")
    step_var = tk.StringVar(value=str(int(app._jog_step)))

    def set_step(val):
        try:
            app._jog_step = float(val)
        except Exception:
            return
        # 그리드 버튼은 생성시 step 을 캡처하므로, 변경 즉시 반영되도록 재바인딩
        for child in grid.winfo_children():
            child.destroy()
        s2 = app._jog_step
        jbtn(grid, "X+ 앞", 0, 1, dx=+s2)
        jbtn(grid, "X- 뒤", 2, 1, dx=-s2)
        jbtn(grid, "Y- 좌", 1, 0, dy=-s2)
        jbtn(grid, "Y+ 우", 1, 2, dy=+s2)
        jbtn(grid, "Z+ 상", 0, 3, dz=+s2)
        jbtn(grid, "Z- 하", 2, 3, dz=-s2)
        app.log(f"jog step = {app._jog_step:.0f} mm")

    for val in (1, 5, 10, 30):
        tk.Radiobutton(step_row, text=str(val), value=str(val), variable=step_var,
                       command=lambda v=val: set_step(v), bg="#2a2a3c", fg="#e6e6e6",
                       selectcolor="#16161f", font=("맑은 고딕", 9)).pack(side="left")

    # --- 캘리브레이션 ---
    section("③ 캘리브레이션 (화면 블록 클릭 → 팔을 그 위로 → 기록, 3회+)")
    btn("대응점 기록(현재 위치)", lambda: on_record_point(app), "#3a5a8a")
    btn("캘리브레이션 완료", lambda: on_finish_calib(app), "#2f6f4f")
    btn("캘리브레이션 초기화", lambda: on_clear_calib(app), "#5a3a3a", small=True)

    # --- 자동 분류 ---
    section("④ 자동 분류 (여러 블록을 하나씩)")
    btn("▶ 자동 분류 시작", lambda: on_auto_start(app), "#2f6f4f")
    btn("■ 정지", lambda: on_auto_stop(app), "#7a5a2f")


INFO = (
    "[M1 색상 분류 — 다중 블록] 블록을 매트 아무 곳에나(여러 개도) 올려놓으세요. "
    "처음 한 번 캘리브레이션하면(우측 ①~③), '자동 분류 시작'으로 화면의 블록을 큰 것부터 "
    "하나씩 집어 색깔별 상자(빨강/초록/파랑·그 외 검사대)로 옮깁니다. 초록 매트는 배경으로 제외됩니다."
)


def main():
    pass
    app = LessonGUI(
        title="M1 색상 분류 (다중 블록)",
        camera_index=config.CAM_TABLE,
        use_robot=True,
        process_frame=make_process_frame(),
        info=INFO,
        build_controls=build_controls,
        on_canvas_click=on_canvas_click,
    )
    # 차시 상태 초기화
    app._blocks = []
    app._marked_pixel = None
    app._calib_pairs = []
    app._M = None
    app._observe_pose = None
    app._jog_step = JOG_STEP_DEFAULT
    app._auto_running = False
    app.run()


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()


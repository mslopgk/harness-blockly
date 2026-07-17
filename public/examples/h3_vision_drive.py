# -*- coding: utf-8 -*-
"""[H3] 비전 AI 자율주행 GUI — 단일 파일(standalone) 버전.

원본(taskB_curriculum/h3_vision_ai/gui.py + 의존 모듈들: common.vision_drive /
common.go_cam / common.go_ctl / h3_vision_ai.solution)을 **하나의 파이썬 파일**로
합친 것. Magician GO 주행 카 + 카메라로 '가르쳐서 달리는 자동차'(Teachable Machine
스타일 수집→학습→추론) 를 구현한다.

자동 생성물 — 로직은 원본과 동일하다(중복 구현/재작성 아님). 여러 모듈을 한
네임스페이스로 평탄화하고, 모듈 한정 참조(S.CLASSES 등)가 이 파일 자신을 가리키도록
alias 처리했다.

실행:  CURRICULUM_FORCE_MOCK=1 python 자율주행_standalone.py   (하드웨어 없이 데모)
       python 자율주행_standalone.py                          (GO COM5 + K210 COM16)
필요:  numpy(필수), tkinter(표준). 실로봇: websockets + DobotLink.exe. 카메라: pyserial.
"""

import sys as _sys

# ── 패키지 평탄화용 self-alias ───────────────────────────────────────────────
# 원본 gui.py 는 `from h3_vision_ai import solution as S` 로 차시 로직을 S 로 참조했다
# (S.CLASSES / S.FEATURE_SIZE / S.autonomous_drive / S.LOOP_DT). 단일 파일에서는
# 그 이름이 '이 모듈' 자신을 가리키게 하면, 아래 이어붙인 solution 코드가 그대로 쓰인다.
S = _sys.modules[__name__]



# ==============================================================================
# ── common/vision_drive.py — VisionPolicy / extract_features
# ==============================================================================

# -*- coding: utf-8 -*-
"""학습된 시각 정책 — 카메라 이미지를 조향 클래스로 매핑하는 경량 분류기.

순수 numpy 소프트맥스 로지스틱 회귀. '녹음-재생'이 아니라 이미지→행동을 일반화하는
정책을 데이터에서 학습한다(가중치 = AI가 보는 곳). 학습/시험 정확도로 과적합을 관찰.
"""

import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:
    pass

from typing import Any

import numpy as np
import numpy.typing as npt

# 팀이 학습한 모델을 저장/불러올 기본 경로.
# GUI [모델 저장] 이 여기에 쓰고, scaffold.py --model 이 여기서 읽는다(같은 PC).
DEFAULT_MODEL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "team_model.npz"
)


def extract_features(
    frame: npt.NDArray[np.uint8], size: tuple[int, int] = (32, 24)
) -> npt.NDArray[np.float32]:
    """프레임(HxWx3 RGB uint8) → 다운스케일·그레이·정규화·평탄화 1D float32(0..1)."""
    arr = np.asarray(frame)
    if arr.ndim == 3:
        gray = arr.mean(axis=2)
    else:
        gray = arr.astype(np.float64)
    w, h = int(size[0]), int(size[1])
    height, width = gray.shape
    # 최근접 다운샘플(외부 의존 없이)
    ys = (np.linspace(0, height - 1, h)).astype(int)
    xs = (np.linspace(0, width - 1, w)).astype(int)
    small = gray[np.ix_(ys, xs)]
    return (small.reshape(-1) / 255.0).astype(np.float32)


def _softmax(z: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    result: npt.NDArray[np.float64] = e / e.sum(axis=1, keepdims=True)
    return result


class VisionPolicy:
    """이미지→조향 클래스 분류기(소프트맥스 로지스틱 회귀)."""

    def __init__(
        self, classes: list[str], feature_size: tuple[int, int] = (32, 24)
    ) -> None:
        self._classes = list(classes)
        self._idx = {c: i for i, c in enumerate(self._classes)}
        self.feature_size = (int(feature_size[0]), int(feature_size[1]))
        self._X: list[npt.NDArray[np.float32]] = []
        self._y: list[int] = []
        self._W: npt.NDArray[np.float64] | None = None
        self._b: npt.NDArray[np.float64] | None = None

    @property
    def classes(self) -> list[str]:
        return list(self._classes)

    @property
    def counts(self) -> dict[str, int]:
        d = {c: 0 for c in self._classes}
        for yi in self._y:
            d[self._classes[yi]] += 1
        return d

    @property
    def is_trained(self) -> bool:
        return self._W is not None

    def add_example(self, frame: npt.NDArray[np.uint8], label: str) -> None:
        if label not in self._idx:
            raise ValueError(f"알 수 없는 라벨: {label!r} (classes={self._classes!r})")
        self._X.append(extract_features(frame, self.feature_size))
        self._y.append(self._idx[label])

    def train(
        self,
        epochs: int = 200,
        lr: float = 0.5,
        val_ratio: float = 0.2,
        seed: int = 0,
    ) -> dict[str, Any]:
        if not self._X:
            raise RuntimeError("학습 예시가 없습니다. add_example()으로 데이터를 먼저 모으세요.")
        X = np.stack(self._X).astype(np.float64)
        y = np.array(self._y, dtype=int)
        n, d = X.shape
        k = len(self._classes)
        rng = np.random.default_rng(seed)
        perm = rng.permutation(n)
        X, y = X[perm], y[perm]
        n_val = int(round(n * val_ratio))
        Xv, yv = X[:n_val], y[:n_val]
        Xt, yt = X[n_val:], y[n_val:]
        if len(Xt) == 0:  # val_ratio 과대 방지
            Xt, yt, Xv, yv = X, y, X[:0], y[:0]
        W = np.zeros((d, k))
        b = np.zeros((1, k))
        Y = np.eye(k)[yt]
        m = len(Xt)
        for _ in range(int(epochs)):
            P = _softmax(Xt @ W + b)
            gW = Xt.T @ (P - Y) / m
            gb = (P - Y).mean(axis=0, keepdims=True)
            W -= lr * gW
            b -= lr * gb
        self._W, self._b = W, b
        train_acc = float((np.argmax(_softmax(Xt @ W + b), axis=1) == yt).mean())
        if len(Xv):
            pv = np.argmax(_softmax(Xv @ W + b), axis=1)
            val_acc = float((pv == yv).mean())
            conf = np.zeros((k, k), dtype=int)
            for t, pr in zip(yv, pv):
                conf[t, pr] += 1
        else:
            val_acc, conf = train_acc, np.zeros((k, k), dtype=int)
        return {
            "train_acc": train_acc,
            "val_acc": val_acc,
            "confusion": conf,
            "n_train": len(Xt),
            "n_val": len(Xv),
        }

    def predict(self, frame: npt.NDArray[np.uint8]) -> tuple[str, float]:
        if self._W is None or self._b is None:
            raise RuntimeError("학습되지 않았습니다. train()을 먼저 호출하세요.")
        f = extract_features(frame, self.feature_size).astype(np.float64)[None, :]
        p = _softmax(f @ self._W + self._b)[0]
        i = int(np.argmax(p))
        return self._classes[i], float(p[i])

    def predict_proba(self, frame: npt.NDArray[np.uint8]) -> dict[str, float]:
        """클래스별 확률 전체를 반환(합=1). 티처블머신식 신뢰도 막대 표시용."""
        if self._W is None or self._b is None:
            raise RuntimeError("학습되지 않았습니다. train()을 먼저 호출하세요.")
        f = extract_features(frame, self.feature_size).astype(np.float64)[None, :]
        p = _softmax(f @ self._W + self._b)[0]
        return {c: float(p[i]) for i, c in enumerate(self._classes)}

    def save(self, path: str) -> None:
        if self._W is None or self._b is None:
            raise RuntimeError("학습되지 않아 저장할 수 없습니다.")
        np.savez(
            path,
            W=self._W,
            b=self._b,
            classes=np.array(self._classes),
            fs=np.array(self.feature_size),
        )

    @classmethod
    def load(cls, path: str) -> "VisionPolicy":
        d = np.load(path, allow_pickle=False)
        fs = d["fs"]
        obj = cls([str(c) for c in d["classes"]], (int(fs[0]), int(fs[1])))
        obj._W, obj._b = d["W"], d["b"]
        return obj



# ==============================================================================
# ── common/go_cam.py — 카메라 추상화(Mock/Folder/K210)
# ==============================================================================

# -*- coding: utf-8 -*-
"""카메라 추상화 — 로봇 K210(C타입) / 저장 이미지 폴더(SD) / 모의 카메라를 단일 인터페이스로.

수업 코드가 하드웨어에 독립적이 되게 한다. CURRICULUM_FORCE_MOCK=1 또는 pyserial 미설치 시
MockCamera(라인 위치를 프레임에 반영한 합성 도로)로 자동 폴백 — 무하드웨어 학습·검증 가능.
K210 소스는 검증된 뷰어 방식(COM16 CP210x 115200 → REPL 확보 → 캡처 루프 → FRM:base64) 재사용.
"""

import glob
import io
import os
import sys
import time
from typing import Any, Optional

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:
    pass

import numpy as np

try:
    import serial  # type: ignore[import-untyped]  # noqa: F401
    _HAS_SERIAL = True
except Exception:  # pragma: no cover
    _HAS_SERIAL = False


def cam_is_mock() -> bool:
    """CURRICULUM_FORCE_MOCK=1 이거나 pyserial이 없으면 True(모의 카메라 사용)."""
    if os.environ.get("CURRICULUM_FORCE_MOCK", "").strip() == "1":
        return True
    return not _HAS_SERIAL


class MockCamera:
    """라인 위치를 프레임에 반영하는 합성 도로 카메라.

    라인은 가우시안 명암 프로파일(부드러운 경계)로 렌더링한다. 실제 카메라가 담는
    라인도 경계가 흐려지므로, 하드 이진 줄무늬보다 학습된 정책이 인접 위치 간에
    일반화하기 쉬운 연속적인 특징을 제공한다(암기가 아닌 진짜 학습을 검증하려면
    프레임이 위치에 따라 부드럽게 변해야 한다).
    """

    is_mock = True
    _SIGMA = 5.0  # 라인 흐림 폭(px) — 다운샘플 격자보다 넓어 인접 위치 간 특징이 겹치게 함

    def __init__(self, w: int = 64, h: int = 48) -> None:
        self.w, self.h = int(w), int(h)
        self._pos = 0.0

    def set_line_pos(self, x: float) -> None:
        self._pos = max(-1.0, min(1.0, float(x)))

    def get_frame(self) -> np.ndarray:
        cx = (self._pos + 1.0) * 0.5 * (self.w - 1)
        xs = np.arange(self.w, dtype=np.float64)
        dist = np.abs(xs - cx)
        darkness = np.exp(-(dist ** 2) / (2 * self._SIGMA ** 2))
        col_val = (220 - darkness * 200).astype(np.uint8)
        img = np.empty((self.h, self.w, 3), dtype=np.uint8)
        img[:, :, :] = col_val[None, :, None]
        return img

    def close(self) -> None:
        pass


class FolderCamera:
    """폴더의 이미지들을 정렬 순환 공급(저장 데이터셋/SD용)."""

    is_mock = False

    def __init__(self, folder: str) -> None:
        exts = ("*.jpg", "*.jpeg", "*.png", "*.bmp")
        files: list[str] = []
        for e in exts:
            files.extend(glob.glob(os.path.join(folder, e)))
        self._files = sorted(files)
        self._i = 0

    def get_frame(self) -> Optional[np.ndarray]:
        if not self._files:
            return None
        from PIL import Image
        path = self._files[self._i % len(self._files)]
        self._i += 1
        return np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)

    def close(self) -> None:
        pass


class K210Camera:  # pragma: no cover - 하드웨어 필요, 단위테스트 제외
    """로봇 K210 카메라(C타입 시리얼) 라이브 프레임. 하드웨어 필요.

    중요한 타이밍: 이 카메라 펌웨어는 frozen 라인검출 앱이 부팅하며 센서를 독점한다.
    앱이 센서를 완전히 잡기 *전*의 짧은 부팅 창에서 인터럽트하고 캡처 루프를 주입해야
    스트리밍이 된다(부팅 대기가 3초처럼 길면 앱이 먼저 센서를 잡아 리셋됨). 그래서
    포트를 새로 열어(=CP210x DTR 토글로 리셋 유발) 짧게 대기 후 즉시 인터럽트하고,
    첫 유효 프레임이 올 때까지 검증한다. 실패하면 포트를 닫고 다시 여는 식으로
    재시도(=뷰어의 [재연결])한다 — 실측 적중률이 시도당 ~75%라 몇 번 재시도로 안정화.
    """

    is_mock = False
    _CAP = (
        "import sensor,ubinascii,gc\ngc.collect()\nsensor.reset()\n"
        "sensor.set_pixformat(sensor.RGB565)\nsensor.set_framesize(sensor.QQVGA)\n"
        "sensor.run(1)\nsensor.skip_frames(time=500)\nwhile True:\n"
        "  img=sensor.snapshot()\n  img.compress(quality=50)\n"
        "  print('FRM:'+ubinascii.b2a_base64(img.to_bytes()).decode().strip())\n"
    )
    _B64 = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
    _BOOT_WAIT = 1.2  # 갓 부팅 창(초) — 앱이 센서를 잡기 전에 인터럽트하려면 짧아야 함
    _VERIFY = 6.0     # 스트리밍 시작 검증 대기(초) — 첫 프레임까지 여유
    _DEBUG = os.environ.get("K210_DEBUG", "").strip() == "1"

    def __init__(self, port: str = "COM16", baud: int = 115200, attempts: int = 6) -> None:
        import serial as _s
        self._serial_mod = _s
        self.port = port
        self.baud = baud
        self._ser: Any = None  # pyserial(untyped) 핸들 또는 None
        self._buf = b""
        self._first: Optional[np.ndarray] = None
        last = ""
        for k in range(max(1, attempts)):
            try:
                if self._try_start():
                    if self._DEBUG:
                        print("[K210] 연결 성공(시도 %d)" % (k + 1), file=sys.stderr)
                    return
                if self._DEBUG:
                    print("[K210] 시도 %d: 프레임 미검증" % (k + 1), file=sys.stderr)
            except Exception as e:  # 포트 오류 등 — 닫고 재시도
                last = str(e)
                if self._DEBUG:
                    print("[K210] 시도 %d 예외: %s" % (k + 1, e), file=sys.stderr)
            self._close_ser()
            time.sleep(1.0)
        raise RuntimeError(
            "K210 라이브 스트리밍 시작 실패(%d회 시도) — USB-C를 뺐다 꽂고 다시 연결하세요. %s"
            % (attempts, last))

    def _try_start(self) -> bool:
        """포트 새로 열기 → 갓 부팅 창 대기 → 인터럽트 → 캡처 루프 주입 → 첫 프레임 검증."""
        self._ser = self._serial_mod.Serial(self.port, self.baud, timeout=0.2)
        time.sleep(0.2)
        t0 = time.time()
        while time.time() - t0 < self._BOOT_WAIT:
            self._ser.read(8192)
        if not self._enter_repl():
            if self._DEBUG:
                print("[K210]   REPL 확보 실패", file=sys.stderr)
            return False
        self._ser.write(("exec(" + repr(self._CAP) + ")\r\n").encode())
        self._buf = b""
        frame = self._read_frame(timeout=self._VERIFY)  # 실제로 스트리밍이 시작됐는지 검증
        if frame is not None:
            self._first = frame
            return True
        return False

    def _enter_repl(self) -> bool:
        # 부팅 창이 좁아 시도를 짧게(3회) — 실패하면 상위에서 포트 재오픈 재시도.
        for _ in range(3):
            for _ in range(3):
                self._ser.write(b"\x03")
                time.sleep(0.12)
            self._ser.write(b"\r\n")
            time.sleep(0.25)
            self._ser.reset_input_buffer()
            self._ser.write(b"print('P9')\r\n")
            time.sleep(0.4)
            if b"P9" in self._ser.read(65536):
                return True
        return False

    def _read_frame(self, timeout: float = 2.0) -> Optional[np.ndarray]:
        import base64
        from PIL import Image
        t0 = time.time()
        while time.time() - t0 < timeout:
            self._buf += self._ser.read(16384)
            while b"\n" in self._buf:
                line, self._buf = self._buf.split(b"\n", 1)
                i = line.rfind(b"FRM:")
                if i < 0:
                    continue
                tok = bytes(c for c in line[i + 4:] if c in self._B64)
                if len(tok) < 100:
                    continue
                tok += b"=" * (-len(tok) % 4)
                try:
                    raw = base64.b64decode(tok)
                except Exception:
                    continue
                if raw[:2] == b"\xff\xd8" and raw[-2:] == b"\xff\xd9":
                    return np.asarray(Image.open(io.BytesIO(raw)).convert("RGB"), dtype=np.uint8)
            if len(self._buf) > 262144:  # 폭주 방지
                self._buf = self._buf[-65536:]
        return None

    def get_frame(self) -> Optional[np.ndarray]:
        if self._first is not None:  # 시작 검증에서 받은 첫 프레임 재사용
            f, self._first = self._first, None
            return f
        return self._read_frame(timeout=2.0)

    def _close_ser(self) -> None:
        try:
            if self._ser is not None:
                self._ser.write(b"\x03")
                time.sleep(0.1)
                self._ser.close()
        except Exception:
            pass
        self._ser = None

    def close(self) -> None:
        self._close_ser()


def get_camera(source: Optional[str] = None, mock: Optional[bool] = None):
    """카메라 팩토리 — source/mock에 따라 MockCamera/FolderCamera/K210Camera를 반환."""
    use_mock = cam_is_mock() if mock is None else bool(mock)
    if use_mock:
        return MockCamera()
    if source and source.lower().startswith("k210:"):  # pragma: no cover
        return K210Camera(source.split(":", 1)[1] or "COM16")
    if source and os.path.isdir(source):
        return FolderCamera(source)
    return K210Camera("COM16")  # pragma: no cover



# ==============================================================================
# ── common/go_ctl.py — Magician GO 제어(실로봇/MockGO)
# ==============================================================================

# -*- coding: utf-8 -*-
"""Dobot Magician GO(주행 카) 제어 래퍼 — H3 차시용 공통 레이어.

팔(Magician Lite)용 common.dobot_ctl 과 같은 역할을 GO에 대해 수행한다:
    - get_go(port=..., mock=...) 팩토리 하나로 실로봇/모의로봇을 동일 인터페이스로 제공
    - with 문 종료 시 무조건 트레이싱 OFF + 비상정지 (크래시에도 로봇이 서 있도록)
    - 초음파 응답 정규화(키 검증·40cm 클램프) — 안전 판정이 센서 이상값에 속지 않도록

실로봇 경로는 DobotLink(ws://localhost:9090) JSON-RPC 를 사용한다.
2026-07-02 실기 검증 완료 사항이 코드에 반영되어 있다:
    - SetTraceAuto 는 isTrace 를 int(1/0) 로, type=0 과 함께 보내야 동작
      (bool 로 보내면 펌웨어가 조용히 무시 — 켜지지도 꺼지지도 않음)
    - 공식 순찰 파라미터: 속도 20, PID (0.5, 0, 0.5)
    - connect 핸드셰이크는 거짓 성공 가능 → battery() 읽기로 링크 검증 필수
    - 초음파는 40cm 이상을 전부 40으로 보고(상한 클램프)

모의로봇(MockGO)은 하드웨어·DobotLink 없이 수업 코드를 끝까지 실행할 수 있게
라인 치우침(offset)과 오도미터를 물리 흉내 수준으로 시뮬레이션한다.
CURRICULUM_FORCE_MOCK=1 환경변수 또는 websockets 미설치 시 자동으로 mock 이 된다.
"""


import math
import os
import time
from typing import Any, Dict, Optional, Tuple

_ws_connect: Any = None  # websockets.sync.client.connect (미설치 시 None)
try:
    from websockets.sync.client import connect as _ws_connect  # type: ignore  # noqa: F811

    _HAS_WS = True
except Exception:  # pragma: no cover - websockets 미설치 환경
    _HAS_WS = False

# ---------------------------------------------------------------------------
# 하드웨어 실측으로 확정된 기본값 (2026-07-02)
# ---------------------------------------------------------------------------
DEFAULT_PORT = "COM5"          # GO 무선 동글의 관례 포트 (이 PC 실측)
WS_HOST = "localhost"
WS_PORT = 9090
WS_TIMEOUT_S = 6.0

PATROL_SPEED = 20              # DobotLab '라인 순찰 시작' 버튼과 동일
PATROL_PID = (0.5, 0.0, 0.5)   # 공식 데모 값 — 50 같은 큰 값은 요동으로 라인 이탈
ULTRA_MAX_CM = 40              # 초음파 상한 클램프(실측): 40 이상은 전부 40으로 보고
OBSTACLE_CM = 15               # 이 값(cm) 미만이면 장애물로 판단하는 권장 임계값


def go_is_mock() -> bool:
    """모의로봇 사용 여부 자동 판정.

    CURRICULUM_FORCE_MOCK=1 이면 무조건 mock, websockets 가 없어도 mock.
    """
    if os.environ.get("CURRICULUM_FORCE_MOCK", "").strip() == "1":
        return True
    return not _HAS_WS


class GoError(RuntimeError):
    """GO/DobotLink 통신 오류 (메시지는 학생이 읽는 한국어)."""


# ---------------------------------------------------------------------------
# DobotLink JSON-RPC 클라이언트 (실로봇 경로)
# ---------------------------------------------------------------------------
class _DobotLinkClient:
    """ws://localhost:9090 의 DobotLink 에 붙는 최소 JSON-RPC 클라이언트."""

    def __init__(self, host: str = WS_HOST, port: int = WS_PORT,
                 timeout: float = WS_TIMEOUT_S) -> None:
        self._url = f"ws://{host}:{port}"
        self._timeout = timeout
        self._ws: Any = None  # 연결된 websockets 소켓(미연결 시 None)
        self._next_id = 0

    def connect(self) -> "_DobotLinkClient":
        if not _HAS_WS:
            raise GoError("websockets 패키지가 없습니다. `pip install websockets` 후 다시 실행하세요.")
        try:
            self._ws = _ws_connect(self._url, open_timeout=self._timeout)
        except Exception as e:
            raise GoError(
                f"DobotLink({self._url})에 연결할 수 없습니다. "
                f"DobotLink.exe 가 실행 중인지 확인하세요. ({e})"
            ) from e
        return self

    def close(self) -> None:
        if self._ws is not None:
            try:
                self._ws.close()
            finally:
                self._ws = None

    def call(self, method: str, **params: Any) -> Any:
        """요청을 보내고 응답을 기다린다. 오류/타임아웃이면 GoError."""
        import json

        if self._ws is None:
            raise GoError("DobotLink 에 연결되어 있지 않습니다. connect() 먼저 호출하세요.")
        self._next_id += 1
        req_id = self._next_id
        self._ws.send(json.dumps({
            "jsonrpc": "2.0", "id": req_id,
            "method": f"dobotlink.{method}", "params": params,
        }))
        deadline = time.monotonic() + self._timeout
        while time.monotonic() < deadline:
            try:
                raw = self._ws.recv(timeout=max(0.05, deadline - time.monotonic()))
            except Exception as e:
                raise GoError(
                    f"'{method}' 응답 대기 중 타임아웃({self._timeout:.0f}초). "
                    f"GO 전원이 켜져 있고 무선 동글이 연결되어 있는지 확인하세요. ({e})"
                ) from e
            msg = json.loads(raw)
            if msg.get("id") != req_id:
                continue  # 다른 알림/응답은 건너뛴다
            if "error" in msg:
                raise GoError(f"'{method}' 호출 실패: {msg['error']}")
            return msg.get("result")
        raise GoError(f"'{method}' 응답 대기 중 타임아웃({self._timeout:.0f}초).")

    def notify(self, method: str, **params: Any) -> None:
        """응답을 기다리지 않는 일방향 전송 (비상정지 전용 — 절대 블록되지 않음)."""
        import json

        if self._ws is None:
            return
        try:
            self._ws.send(json.dumps({
                "jsonrpc": "2.0",
                "method": f"dobotlink.{method}", "params": params,
            }))
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 공통 유틸: 초음파 정규화
# ---------------------------------------------------------------------------
_ULTRA_KEYS = ("front", "back", "left", "right")


def normalize_ultra(raw: Any) -> Optional[Dict[str, float]]:
    """초음파 원시 응답을 검증·정규화한다.

    - dict 가 아니거나 front/back/left/right 키가 빠지면 None (→ 호출부는 정지 판단)
    - 0 이하·비수치 값도 None (미장착 센서 센티널 방어)
    - 40cm 초과는 40 으로 클램프 (하드웨어가 원래 40 상한)
    """
    if not isinstance(raw, dict):
        return None
    out: Dict[str, float] = {}
    for k in _ULTRA_KEYS:
        v = raw.get(k)
        if not isinstance(v, (int, float)) or v <= 0:
            return None
        out[k] = min(float(v), float(ULTRA_MAX_CM))
    return out


# ---------------------------------------------------------------------------
# 실로봇 컨트롤러
# ---------------------------------------------------------------------------
class GoController:
    """Magician GO 실로봇 제어. get_go() 를 통해 얻고 with 문으로 사용한다.

    with 블록이 어떻게 끝나든(정상/예외/Ctrl-C) __exit__ 가
    트레이싱 OFF + 비상정지 + 연결 종료를 보장한다.
    """

    is_mock = False

    def __init__(self, port: str = DEFAULT_PORT) -> None:
        self.port = port
        self._client = _DobotLinkClient()

    # -- 연결 ---------------------------------------------------------------
    def connect(self) -> "GoController":
        self._client.connect()
        try:
            self._call("ConnectDobot")
        except GoError as e:
            self._client.close()
            raise GoError(f"GO 연결 실패 (포트 {self.port}): {e}") from e
        # 핸드셰이크는 거짓 성공이 가능하므로 battery() 로 링크를 실제 검증한다.
        try:
            self.battery()
        except GoError as e:
            self._client.close()
            raise GoError(
                f"포트 {self.port} 는 열렸지만 GO 가 응답하지 않습니다. "
                f"로봇 전원 스위치를 확인하세요. ({e})"
            ) from e
        return self

    def __enter__(self) -> "GoController":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        # 무슨 일이 있어도 로봇은 멈춘 상태로 끝난다.
        try:
            self.auto_trace(False)
        except Exception:
            pass
        try:
            self.emergency_stop()
        except Exception:
            pass
        self._client.close()

    def close(self) -> None:
        self.__exit__(None, None, None)

    def _call(self, func: str, **params: Any) -> Any:
        params["portName"] = self.port
        return self._client.call(f"MagicianGO.{func}", **params)

    # -- 센서 ---------------------------------------------------------------
    def battery(self) -> Dict[str, Any]:
        return self._call("GetBatteryVoltage")

    def ultrasonic(self) -> Optional[Dict[str, float]]:
        """정규화된 4방향 초음파(cm). 센서 이상 시 None."""
        return normalize_ultra(self._call("GetUltrasoundData"))

    def trace_angle(self) -> Dict[str, int]:
        """하부(CAR) 카메라의 라인 인식 결과 {'angle': .., 'count': ..}."""
        raw = self._call("GetCarCameraAngle")
        if not isinstance(raw, dict):
            return {"angle": 0, "count": 0}
        return {"angle": int(raw.get("angle", 0)), "count": int(raw.get("count", 0))}

    def odometer(self) -> Dict[str, float]:
        raw = self._call("GetSpeedometer")
        return {k: float(raw.get(k, 0.0)) for k in ("x", "y", "yaw")}

    def set_odometer(self, x: float = 0, y: float = 0, yaw: float = 0) -> Any:
        return self._call("SetSpeedometer", x=x, y=y, yaw=yaw)

    # -- 펌웨어 라인 순찰 -----------------------------------------------------
    def trace_speed(self, speed: float) -> Any:
        return self._call("SetTraceSpeed", speed=speed)

    def trace_pid(self, p: float, i: float, d: float) -> Any:
        return self._call("SetTracePid", p=p, i=i, d=d)

    def auto_trace(self, on: bool) -> Any:
        # isTrace 는 반드시 int(1/0) + type=0 — bool 이면 펌웨어가 조용히 무시한다
        # (2026-07-02 실기 검증. DobotLab '라인 순찰' 버튼과 동일한 와이어 포맷)
        self._call("SetTraceLoop", enable=bool(on))
        return self._call("SetTraceAuto", isTrace=int(bool(on)), type=0)

    # -- 주행 ---------------------------------------------------------------
    def move(self, x: float = 0, y: float = 0, r: float = 0) -> Any:
        """연속 속도 주행 (x+: 전진, y+: 좌횡이동, r+: 반시계 회전).

        주의: 멈추라고 할 때까지 계속 달린다. 반드시 유한 루프 안에서 쓰고
        정지는 stop()/with 블록 종료에 맡긴다. |속도| 는 30 으로 클램프.
        """
        clamp = lambda v: max(-30.0, min(30.0, float(v)))  # noqa: E731
        return self._call("SetMoveSpeed", x=clamp(x), y=clamp(y), r=clamp(r))

    def stop(self) -> Any:
        return self.move(0, 0, 0)

    def emergency_stop(self) -> None:
        """응답을 기다리지 않는 정지 — 링크가 죽어도 절대 블록되지 않는다."""
        self._client.notify("MagicianGO.SetMoveSpeed",
                            portName=self.port, x=0, y=0, r=0)


# ---------------------------------------------------------------------------
# 모의 로봇 (하드웨어/DobotLink 없이 수업 코드 전체 실행)
# ---------------------------------------------------------------------------
class MockGO:
    """MagicianGO 의 물리 흉내 모형.

    - 라인 치우침(offset, 도 단위)이 매 스텝 조금씩 흘러가고(드리프트),
      학생의 조향(move 의 r)이 그것을 되돌린다 → P제어가 실제로 '동작'한다.
    - auto_trace(True) 면 펌웨어 PID 를 흉내: P 가 크면 크게 요동친다.
    - 오도미터는 move 명령을 시간 적분해 전진량을 흉내낸다.
    """

    is_mock = True
    CENTER = 245  # 실기 실측 중앙값과 동일하게 맞춘 모의 영점

    def __init__(self, port: str = DEFAULT_PORT) -> None:
        self.port = port
        self._offset = 6.0        # 시작부터 살짝 치우쳐 있게 (학생 조향이 필요하도록)
        self._tick = 0
        self._tracing = False
        self._pid = PATROL_PID
        self._trace_speed = 0.0
        self._odo = {"x": 0.0, "y": 0.0, "yaw": 0.0}
        self._last_move: Tuple[float, float, float] = (0.0, 0.0, 0.0)
        self.move_log: list = []  # 테스트가 조향 이력을 검사할 수 있도록 기록

    # -- 연결 (즉시 성공) -----------------------------------------------------
    def connect(self) -> "MockGO":
        return self

    def __enter__(self) -> "MockGO":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self._tracing = False
        self._last_move = (0.0, 0.0, 0.0)

    def close(self) -> None:
        self.__exit__(None, None, None)

    # -- 센서 ---------------------------------------------------------------
    def battery(self) -> Dict[str, Any]:
        return {"powerVoltage": 11.7, "powerPercentage": 1.0, "powerSourceStatus": 0}

    def ultrasonic(self) -> Optional[Dict[str, float]]:
        return {"front": 40.0, "back": 40.0, "left": 40.0, "right": 40.0}

    def trace_angle(self) -> Dict[str, int]:
        self._step()
        if abs(self._offset) > 60:      # 너무 치우치면 카메라가 라인을 놓친다
            return {"angle": 0, "count": 0}
        return {"angle": int(round(self.CENTER + self._offset)), "count": 1}

    def odometer(self) -> Dict[str, float]:
        return dict(self._odo)

    def set_odometer(self, x: float = 0, y: float = 0, yaw: float = 0) -> None:
        self._odo = {"x": float(x), "y": float(y), "yaw": float(yaw)}

    # -- 펌웨어 순찰 ----------------------------------------------------------
    def trace_speed(self, speed: float) -> None:
        self._trace_speed = float(speed)

    def trace_pid(self, p: float, i: float, d: float) -> None:
        self._pid = (float(p), float(i), float(d))

    def auto_trace(self, on: bool) -> None:
        self._tracing = bool(on)

    # -- 주행 ---------------------------------------------------------------
    def move(self, x: float = 0, y: float = 0, r: float = 0) -> None:
        self._last_move = (float(x), float(y), float(r))
        self.move_log.append(self._last_move)

    def stop(self) -> None:
        self.move(0, 0, 0)

    def emergency_stop(self) -> None:
        self._last_move = (0.0, 0.0, 0.0)

    # -- 내부 물리 흉내 --------------------------------------------------------
    def _step(self) -> None:
        self._tick += 1
        if self._tracing:
            # 펌웨어 PID 흉내: P 가 적정(≈0.5)이면 ±3도, 과대하면 크게 요동
            p = self._pid[0]
            amp = 3.0 if p <= 2.0 else min(70.0, p * 1.4)
            self._offset = amp * math.sin(self._tick * 0.9)
            if self._trace_speed > 0:
                self._odo["x"] += self._trace_speed * 0.24  # 실측 비율(속도20→약 4.8mm/틱)
            return
        # 수동 주행: 드리프트가 라인을 벗어나게 하고, 조향(r)이 되돌린다.
        # 부호 규약: angle > CENTER(offset>0) 일 때 음수 조향(r<0)이 offset 을
        # 줄여야 P제어가 수렴한다 → offset 변화량에 +r_cmd 계수.
        x_cmd, _y, r_cmd = self._last_move
        drift = 1.6 * math.sin(self._tick * 0.35) + 0.9
        self._offset += drift + 1.15 * r_cmd
        if x_cmd:
            self._odo["x"] += x_cmd * 0.24
            self._odo["yaw"] += r_cmd * 0.4


# ---------------------------------------------------------------------------
# 팩토리
# ---------------------------------------------------------------------------
def get_go(port: Optional[str] = None, mock: Optional[bool] = None):
    """GO 컨트롤러 팩토리. `with get_go(port="COM5") as go:` 로 사용한다.

    mock=None 이면 자동판정(go_is_mock): CURRICULUM_FORCE_MOCK=1 또는
    websockets 미설치 시 MockGO, 아니면 실로봇(GoController)에 연결한다.
    """
    use_mock = go_is_mock() if mock is None else bool(mock)
    p = port or DEFAULT_PORT
    if use_mock:
        return MockGO(p).connect()
    return GoController(p).connect()



# ==============================================================================
# ── h3_vision_ai/solution.py — 차시 로직(수집/학습/자율주행)
# ==============================================================================

# -*- coding: utf-8 -*-
"""H3 · 고등부(Python) — 비전 AI 자율주행: 카메라만 보고 라인을 따라가는 학습된 정책 [모범답안]

수업 목표 (110분 · 5E · 산업연계 PBL)
    1. '녹음-재생'과 '학습된 정책'의 차이를 설명할 수 있다(암기 vs 일반화).
    2. 카메라 프레임 예시를 모아 소프트맥스 분류기를 학습시킬 수 있다.
    3. 학습/시험 정확도와 혼동행렬로 과적합 여부를 관찰할 수 있다.
    4. 학습에 없던 라인 위치에서도 정책이 옳게 동작함을 확인해 '일반화'를 체감한다.

핵심 개념
    - 정책(policy) = 이미지 → 조향 클래스 매핑을 데이터로부터 학습한 함수(가중치 W,b)
    - 학습 정확도와 시험(검증) 정확도가 크게 벌어지면 과적합(암기)을 의심한다
    - 복구 예시(recovery example): 정상 상태뿐 아니라 '치우친 상태 → 되돌리는 라벨'도
      학습에 넣어야 실주행에서 코스를 벗어나지 않는다(일반화의 핵심 재료)

산업 연계
    자율주행차의 차선 유지 보조(LKA)는 규칙(rule)이 아니라 방대한 주행 영상으로
    학습된 신경망 정책이 조향을 결정한다. 오늘 우리는 그 축소판을 라인트랙과
    소형 로봇으로 만든다: 카메라 → (학습된) 정책 → 조향.

설계 특이사항 (단위테스트 가능)
    분류기(common.vision_drive.VisionPolicy)와 카메라(common.go_cam)는 이미 검증된
    독립 모듈이다. 이 파일은 그 둘과 로봇(common.go_ctl)을 잇는 차시 로직만 담당하며,
    should_stop / collect_dataset / autonomous_drive 는 mock 주입으로 하드웨어 없이
    pytest 검증된다.

안전 (QUR-002)
    - 주행 루프는 정지 조건이 있는 유한 루프(for)다. while True 금지.
    - 매 스텝 신뢰도가 임계값 미만이면 정지한다 — "모르면 멈춘다".
    - 매 스텝 초음파를 확인해 임계값 미만(장애물)이거나 응답이 이상하면(None) 중단한다.
    - 로봇 사용은 `with get_go(...) as go:` — 블록이 어떻게 끝나든 정지가 보장된다.

실행법
    실로봇(수집·학습 포함):  python h3_vision_ai/solution.py --port COM5
    저장모델로 실주행:        python h3_vision_ai/solution.py --port COM5 --model
        └ GUI가 저장한 team_model.npz 를 불러와 수집·학습을 건너뛰고 곧바로 주행
          (모델은 PC에서 돌고 PC가 무선으로 GO에 조향 명령 전송 · Ctrl+C 로 정지)
    모의:    CURRICULUM_FORCE_MOCK=1 python h3_vision_ai/solution.py
    (실로봇은 GO 전원 ON + 무선 동글 + DobotLink.exe 실행 + K210 카메라(COM16) + 라인트랙 필요.
     --model 실주행 전에는 GUI를 완전히 종료해 COM 포트 점유를 풀 것.)

주의 (부호)
    CLASS_STEER 의 부호(LEFT→+, RIGHT→-)는 트랙 위 카메라 장착 방향에 따라 반대일 수
    있다. 실기에서 라인이 왼쪽에 있을 때 로봇이 실제로 왼쪽으로 되돌아오는지 반드시
    확인하고, 반대면 부호를 뒤집는다(hardware_test.py 참고).
"""

import os
import sys


try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:
    pass

import time
from typing import Any, Dict, List, Optional, Tuple

pass
pass
pass

# ===========================================================================
# 차시 상수 — 학생이 실기에서 확인·조정하는 값들
# ===========================================================================
CLASSES = ["LEFT", "STRAIGHT", "RIGHT"]
CLASS_STEER: Dict[str, float] = {"LEFT": 8.0, "STRAIGHT": 0.0, "RIGHT": -8.0}  # 부호 실기 확인
FEATURE_SIZE = (32, 24)
LOOP_DT = 0.1

# 정상 주행(중앙 근처) + 복구(치우친 상태→되돌리는 라벨) 예시 계획.
# (line_pos, label): line_pos 는 MockCamera 기준 -1(왼쪽)..+1(오른쪽).
NORMAL_PLAN: List[Tuple[float, str]] = [
    (-0.15, "STRAIGHT"), (0.0, "STRAIGHT"), (0.15, "STRAIGHT"),
]
RECOVERY_PLAN: List[Tuple[float, str]] = [
    (-0.8, "LEFT"), (-0.55, "LEFT"), (-0.35, "LEFT"),
    (0.35, "RIGHT"), (0.55, "RIGHT"), (0.8, "RIGHT"),
]


# ===========================================================================
# 1) [순수함수] 안전 판단 — 하드웨어 없이 pytest 로 검증된다
# ===========================================================================
def should_stop(
    ultra: Optional[Dict[str, float]], threshold: float = OBSTACLE_CM
) -> Tuple[bool, str]:
    """초음파 판독 → (정지해야 하나, 사유). '모르면 멈춘다'."""
    if not ultra:
        return True, "초음파 응답 이상(모르면 멈춘다)"
    nearest_dir = min(ultra, key=ultra.get)  # type: ignore[arg-type]
    nearest = ultra[nearest_dir]
    if nearest < threshold:
        return True, f"{nearest_dir}={nearest:.0f}cm < {threshold:.0f}cm"
    return False, ""


# ===========================================================================
# 2) 데이터 수집 — 실기에서는 학생 시범주행이 대체, 여기선 mock/자동 데모용
# ===========================================================================
def collect_dataset(
    cam: Any, policy: VisionPolicy, plan: List[Tuple[float, str]], per: int = 6
) -> int:
    """plan 의 각 (line_pos, label) 마다 per 장씩 프레임을 모아 policy 에 등록한다.

    반환: 실제로 등록된 예시 총 수(프레임이 None 이면 건너뛴다).
    """
    n = 0
    for line_pos, label in plan:
        if hasattr(cam, "set_line_pos"):
            cam.set_line_pos(line_pos)
        for _ in range(per):
            frame = cam.get_frame()
            if frame is not None:
                policy.add_example(frame, label)
                n += 1
    return n


# ===========================================================================
# 3) 자율주행 — 인지(카메라) → 판단(학습된 정책 + 안전) → 제어(조향)
# ===========================================================================
def autonomous_drive(
    go: Any,
    cam: Any,
    policy: VisionPolicy,
    conf_th: float = 0.6,
    speed: float = 10.0,
    steps: int = 60,
    loop_dt: float = LOOP_DT,
) -> Dict[str, Any]:
    """학습된 정책만으로 카메라를 보고 주행하는 유한 루프.

    반환: {"steps": 실제 이동 횟수, "stops": 프레임 없음으로 정지한 횟수,
           "low_conf": 저신뢰 정지 횟수, "aborted": 장애물로 조기 종료했나,
           "reason": 조기 종료 사유}
    """
    out: Dict[str, Any] = {
        "steps": 0, "stops": 0, "low_conf": 0, "aborted": False, "reason": "",
    }
    try:
        for _ in range(int(steps)):                     # 유한 루프 (안전 규칙)
            frame = cam.get_frame()                      # [인지]
            if frame is None:
                go.stop()
                out["stops"] += 1
                time.sleep(loop_dt)
                continue
            label, conf = policy.predict(frame)          # [판단] 학습된 정책
            if conf < conf_th:                            # "모르면 멈춘다"
                go.stop()
                out["low_conf"] += 1
                time.sleep(loop_dt)
                continue
            stop, why = should_stop(go.ultrasonic())      # [판단] 장애물?
            if stop:
                out["aborted"] = True
                out["reason"] = why
                break
            go.move(x=speed, r=CLASS_STEER[label])        # [제어]
            out["steps"] += 1
            time.sleep(loop_dt)
    finally:
        go.stop()                                         # 루프가 어떻게 끝나든 정지
    return out


# ===========================================================================
# 4) 자가 데모 — mock 이면 하드웨어 없이 수집→학습→일반화→주행이 그대로 돈다
# ===========================================================================
def main(
    port: Optional[str] = None,
    mock: Optional[bool] = None,
    model_path: Optional[str] = None,
) -> int:
    print("=" * 64)
    print(" H3 · 비전 AI 자율주행 — 모범답안 데모")
    print("=" * 64)
    with get_go(port=port, mock=mock) as go:
        kind = "모의(Mock)" if getattr(go, "is_mock", False) else "실로봇"
        batt = go.battery()
        print(f"[연결] {kind} · 배터리 {batt.get('powerVoltage', '?')}V\n")

        cam = get_camera(mock=getattr(go, "is_mock", None))
        try:
            if model_path:
                # -- 불러오기: GUI가 저장한 팀 모델을 그대로 로드 ------------
                policy = VisionPolicy.load(model_path)
                print(f"[불러오기] GUI가 저장한 모델을 불러왔어요 → {model_path}")
                print(f"           클래스={policy.classes} · 특징 크기={policy.feature_size}")
                print("           (수집·학습은 GUI에서 이미 끝냈으니 건너뜁니다)")
            else:
                policy = VisionPolicy(CLASSES, feature_size=FEATURE_SIZE)

                # -- 데이터 수집(정상 + 복구) ---------------------------------
                plan = NORMAL_PLAN + RECOVERY_PLAN
                n = collect_dataset(cam, policy, plan, per=6)
                print(f"[수집] 예시 {n}개 (클래스별: {policy.counts})")

                # -- 학습 -------------------------------------------------------
                metrics = policy.train(epochs=400, lr=0.5, val_ratio=0.2, seed=0)
                print(
                    f"[학습] train_acc={metrics['train_acc']:.2f} "
                    f"val_acc={metrics['val_acc']:.2f} "
                    f"(train={metrics['n_train']}, val={metrics['n_val']})"
                )
                # 혼동행렬(대각=정답, 비대각=오분류) — 과적합/오분류를 눈으로
                print(f"[혼동행렬] 행=실제 / 열=예측, 순서={policy.classes}")
                for cls, row in zip(policy.classes, metrics["confusion"]):
                    print(f"    {cls:>9}: {list(int(v) for v in row)}")

                # -- 일반화 확인: 학습에 없던 위치로 예측 -----------------------
                probe_pos, expect = -0.65, "LEFT"
                if hasattr(cam, "set_line_pos"):
                    cam.set_line_pos(probe_pos)
                    frame = cam.get_frame()
                    label, conf = policy.predict(frame)
                    ok = "OK" if label == expect else "관찰"
                    print(
                        f"[일반화] 학습에 없던 line_pos={probe_pos} → "
                        f"예측={label}(신뢰도 {conf:.2f}, 기대={expect}) [{ok}]"
                    )

            # -- 자율주행 ----------------------------------------------------
            #    실모델(불러오기)이면 트랙 완주용으로 길게, mock 자가데모면 짧게.
            drive_steps = 200 if model_path else 10
            print(f"[주행] 학습된 정책만으로 자율주행 (steps={drive_steps}) · Ctrl+C 로 즉시 정지")
            if hasattr(cam, "set_line_pos"):
                cam.set_line_pos(-0.7)
            result = autonomous_drive(
                go, cam, policy, conf_th=0.5, speed=10.0, steps=drive_steps
            )
            print(
                f"  → 이동 {result['steps']}회, 저신뢰정지 {result['low_conf']}회, "
                f"프레임없음정지 {result['stops']}회", end="",
            )
            if result["aborted"]:
                print(f", 중단: {result['reason']}")
            else:
                print(" — 정상 완료")
        finally:
            cam.close()

    print("\n[종료] 정지 확인 완료. 수고했습니다!")
    return 0





# ==============================================================================
# ── h3_vision_ai/gui.py — H3 조종석 GUI + main()
# ==============================================================================

# -*- coding: utf-8 -*-
"""H3 · 고등부(Python) — 비전 AI 자율주행 학습-주행 조종석 GUI (Magician GO + K210 카메라).

디자인: Google Teachable Machine 스타일 — 밝은 카드형 3열 레이아웃
    [1. 수집] 클래스별 카드에서 '지금 화면'을 예시로 녹화
    [2. 학습] 모델 학습(학습/시험 정확도)
    [3. 미리보기] 라이브 카메라 + 클래스별 실시간 신뢰도 막대(색상) + 자율주행
흐름(수집→학습→추론)이 화면 배치 그대로라 티처블머신의 학습 경험을 재현한다.

안전(구 규칙기반 H3 GUI에서 승계한 규칙):
    - 로봇 동작(연결·주행)은 threading, DobotLink RPC는 _go_lock 으로 직렬화.
    - 주행 판단(신뢰도 임계값·초음파 안전정지·조향)은 solution.autonomous_drive 에 전량 위임.
    - 유한 루프(while True 금지), 창 종료 시 go.stop()/close() 보장.
    - Tk 인스턴스화는 __main__ 에서만(무하드웨어 헤드리스 스모크 가능).

실행법
    CURRICULUM_FORCE_MOCK=1 python h3_vision_ai/gui.py   (하드웨어 없이 데모)
    python h3_vision_ai/gui.py                            (GO COM5 + K210 카메라 COM16)
"""

import os
import sys


try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:
    pass

import threading
import time
from typing import Any, Optional

pass
pass
pass
S = _sys.modules[__name__]

# ── 파라미터 ────────────────────────────────────────────────────────────────
CAM_POLL_S = 0.05
DRIVE_CHUNK = 5
DRIVE_MAX_CHUNKS = 400
CANVAS_W, CANVAS_H = 300, 226
BAR_W = 200

# ── 티처블머신식 밝은 테마 ────────────────────────────────────────────────────
BG = "#F1F3F4"        # 창 배경(구글 그레이)
CARD = "#FFFFFF"      # 카드
INK = "#3C4043"       # 본문 텍스트
MUTED = "#5F6368"     # 보조 텍스트
LINE = "#DADCE0"      # 테두리/트랙
DARKBTN = "#3C4043"   # 강조 버튼(학습)
DANGER = "#D93025"    # 비상정지
OKGREEN = "#188038"
# 클래스별 색상(인덱스 순환) — 티처블머신처럼 클래스마다 고유색
PALETTE = ["#1A73E8", "#F9A825", "#8E24AA", "#00897B", "#E8710A"]

F = "맑은 고딕"


class H3VisionApp:
    """H3 비전 AI 조종석(Teachable Machine 스타일). 생성은 __main__ 에서만."""

    def __init__(self) -> None:
        import tkinter as tk
        from tkinter import scrolledtext

        self.tk = tk
        self.go: Any = None
        self.cam: Any = None
        self.policy = VisionPolicy(S.CLASSES, feature_size=S.FEATURE_SIZE)
        self._colors = {c: PALETTE[i % len(PALETTE)] for i, c in enumerate(S.CLASSES)}

        self._go_lock = threading.RLock()
        self._cam_lock = threading.Lock()
        self._latest_frame: Optional[Any] = None
        self._cam_running = False
        self._cam_thread: Optional[threading.Thread] = None
        self._drive_stop = threading.Event()
        self._drive_thread: Optional[threading.Thread] = None
        self._log_q: list = []

        # per-class 위젯 참조
        self.count_vars: dict = {}
        self.bar_fill: dict = {}
        self.bar_pct: dict = {}
        self.bar_track_w: dict = {}

        root = tk.Tk()
        self.root = root
        root.title("H3 · 비전 AI 자율주행 — 가르쳐서 달리는 자동차")
        root.configure(bg=BG)
        root.protocol("WM_DELETE_WINDOW", self._on_close)

        # ── 상단 바: 타이틀 + 연결 + 비상정지 ──────────────────────────────
        top = tk.Frame(root, bg=BG)
        top.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 6))
        tk.Label(top, text="비전 AI 자율주행", bg=BG, fg=INK,
                 font=(F, 17, "bold")).pack(side="left")
        tk.Label(top, text="  카메라로 보고 · 예시로 배우고 · 스스로 달린다",
                 bg=BG, fg=MUTED, font=(F, 10)).pack(side="left")
        estop = tk.Button(top, text="■ 비상정지", command=self._estop,
                          bg=DANGER, fg="white", font=(F, 11, "bold"),
                          relief="flat", padx=14, pady=4, cursor="hand2")
        estop.pack(side="right")

        conn = tk.Frame(root, bg=BG)
        conn.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))
        self.mock_var = tk.BooleanVar(
            value=os.environ.get("CURRICULUM_FORCE_MOCK", "").strip() == "1")
        self.port_var = tk.StringVar(value=os.environ.get("DOBOT_GO_PORT", "COM5"))
        self.cam_var = tk.StringVar(value="k210:COM16")
        self.status_var = tk.StringVar(value="준비됨")
        self.robot_status = tk.StringVar(value="미연결")
        self.cam_status = tk.StringVar(value="미연결")

        # row0: 모의 체크(다음 연결에 적용) + 전체 상태
        tk.Checkbutton(conn, text="모의(Mock) — 다음 연결에 적용", variable=self.mock_var,
                       bg=BG, fg=INK, selectcolor=CARD, activebackground=BG,
                       font=(F, 9)).grid(row=0, column=0, columnspan=2, sticky="w")
        tk.Label(conn, textvariable=self.status_var, bg=BG, fg=MUTED,
                 font=(F, 9)).grid(row=0, column=2, columnspan=2, sticky="w", padx=(10, 0))

        # row1: 로봇(GO) 독립 연결
        tk.Label(conn, text="로봇 GO 포트", bg=BG, fg=MUTED,
                 font=(F, 9)).grid(row=1, column=0, sticky="w", pady=(4, 0))
        tk.Entry(conn, textvariable=self.port_var, width=8, relief="solid", bd=1,
                 font=("Consolas", 10)).grid(row=1, column=1, sticky="w", padx=(4, 8), pady=(4, 0))
        self.go_btn = tk.Button(conn, text="로봇 연결", command=self._toggle_go,
                                bg="#1A73E8", fg="white", font=(F, 9, "bold"),
                                relief="flat", padx=12, pady=2, width=8, cursor="hand2")
        self.go_btn.grid(row=1, column=2, sticky="w", pady=(4, 0))
        tk.Label(conn, textvariable=self.robot_status, bg=BG, fg=MUTED,
                 font=(F, 9)).grid(row=1, column=3, sticky="w", padx=(8, 0), pady=(4, 0))

        # row2: 카메라(K210) 독립 연결
        tk.Label(conn, text="카메라 소스", bg=BG, fg=MUTED,
                 font=(F, 9)).grid(row=2, column=0, sticky="w", pady=(4, 0))
        tk.Entry(conn, textvariable=self.cam_var, width=13, relief="solid", bd=1,
                 font=("Consolas", 10)).grid(row=2, column=1, sticky="w", padx=(4, 8), pady=(4, 0))
        self.cam_btn = tk.Button(conn, text="카메라 연결", command=self._toggle_cam,
                                 bg="#188038", fg="white", font=(F, 9, "bold"),
                                 relief="flat", padx=12, pady=2, width=8, cursor="hand2")
        self.cam_btn.grid(row=2, column=2, sticky="w", pady=(4, 0))
        tk.Label(conn, textvariable=self.cam_status, bg=BG, fg=MUTED,
                 font=(F, 9)).grid(row=2, column=3, sticky="w", padx=(8, 0), pady=(4, 0))

        # ── 본문 3열 ────────────────────────────────────────────────────────
        body = tk.Frame(root, bg=BG)
        body.grid(row=2, column=0, padx=16, pady=(0, 8), sticky="n")
        self._build_collect(body, tk)
        self._arrow(body, 1)
        self._build_train(body, tk)
        self._arrow(body, 3)
        self._build_preview(body, tk)

        # ── 로그(하단, 접힘) ─────────────────────────────────────────────────
        self.logbox = scrolledtext.ScrolledText(root, width=100, height=5, bg="#FAFAFA",
                                                fg=MUTED, relief="solid", bd=1,
                                                font=("Consolas", 9))
        self.logbox.grid(row=3, column=0, padx=16, pady=(0, 14), sticky="ew")

        self.log("시작. GO 포트/카메라를 확인하고 '연결'을 누르세요. (모의 체크 시 하드웨어 불필요)")
        self._tick()

    # ── 카드/위젯 헬퍼 ──────────────────────────────────────────────────────
    def _card(self, parent: Any, col: int) -> Any:
        tk = self.tk
        c = tk.Frame(parent, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        c.grid(row=0, column=col, sticky="n", padx=0, pady=0)
        return c

    def _arrow(self, parent: Any, col: int) -> None:
        self.tk.Label(parent, text="→", bg=BG, fg="#BDC1C6",
                      font=(F, 20)).grid(row=0, column=col, padx=6)

    def _card_title(self, card: Any, num: str, text: str) -> None:
        tk = self.tk
        h = tk.Frame(card, bg=CARD)
        h.pack(fill="x", padx=14, pady=(12, 2))
        tk.Label(h, text=num, bg="#E8F0FE", fg="#1A73E8", font=(F, 10, "bold"),
                 width=2, height=1).pack(side="left")
        tk.Label(h, text=text, bg=CARD, fg=INK, font=(F, 12, "bold")).pack(
            side="left", padx=(8, 0))

    # ── 1. 수집 ─────────────────────────────────────────────────────────────
    def _build_collect(self, body: Any, tk: Any) -> None:
        card = self._card(body, 0)
        self._card_title(card, "1", "수집 — 예시로 가르치기")
        tk.Label(card, text="방향 버튼으로 '지금 화면'을 그 클래스로 기록.\n"
                            "여러 위치 + 복구 예시를 골고루 넣어야 일반화됩니다.",
                 bg=CARD, fg=MUTED, font=(F, 9), justify="left").pack(
            anchor="w", padx=14, pady=(0, 6))
        for cls in S.CLASSES:
            col = self._colors[cls]
            row = tk.Frame(card, bg=CARD, highlightbackground=LINE, highlightthickness=1)
            row.pack(fill="x", padx=14, pady=5)
            tk.Frame(row, bg=col, width=6, height=44).pack(side="left", fill="y")
            info = tk.Frame(row, bg=CARD)
            info.pack(side="left", fill="both", expand=True, padx=8, pady=6)
            tk.Label(info, text=cls, bg=CARD, fg=INK, font=(F, 11, "bold")).pack(anchor="w")
            cv = tk.StringVar(value="0 샘플")
            self.count_vars[cls] = cv
            tk.Label(info, textvariable=cv, bg=CARD, fg=MUTED, font=(F, 9)).pack(anchor="w")
            tk.Button(row, text="＋ 녹화", command=lambda c=cls: self._record(c),
                      bg=col, fg="white", font=(F, 10, "bold"), relief="flat",
                      padx=10, pady=8, cursor="hand2").pack(side="right", padx=(0, 10))
        tk.Frame(card, bg=CARD, height=8).pack()

    # ── 2. 학습 ─────────────────────────────────────────────────────────────
    def _build_train(self, body: Any, tk: Any) -> None:
        card = self._card(body, 2)
        self._card_title(card, "2", "학습")
        inner = tk.Frame(card, bg=CARD)
        inner.pack(fill="both", expand=True, padx=16, pady=8)
        tk.Button(inner, text="모델 학습", command=self._train_async,
                  bg=DARKBTN, fg="white", font=(F, 12, "bold"), relief="flat",
                  padx=16, pady=12, cursor="hand2").pack(fill="x", pady=(6, 10))
        self.train_head = tk.StringVar(value="아직 학습 전")
        tk.Label(inner, textvariable=self.train_head, bg=CARD, fg=INK,
                 font=(F, 11, "bold")).pack(anchor="w")
        self.train_var = tk.StringVar(
            value="예시를 모은 뒤 '모델 학습'을 누르세요.\n학습/시험 정확도가 크게\n벌어지면 과적합(암기)입니다.")
        tk.Label(inner, textvariable=self.train_var, bg=CARD, fg=MUTED, font=("Consolas", 9),
                 justify="left").pack(anchor="w", pady=(4, 0))
        # 학습한 모델을 파일로 저장 → 학생이 파이썬(scaffold.py --model)으로 실제 주행
        tk.Button(inner, text="💾 모델 저장 (파이썬으로 직접 주행)", command=self._save_model,
                  bg=OKGREEN, fg="white", font=(F, 11, "bold"), relief="flat",
                  padx=12, pady=10, cursor="hand2").pack(fill="x", pady=(12, 4))
        self.save_var = tk.StringVar(
            value="학습 뒤 저장하면, 각자 PC에서\npython scaffold.py --model 로\n이 모델로 진짜 로봇을 움직입니다.")
        tk.Label(inner, textvariable=self.save_var, bg=CARD, fg=MUTED, font=("Consolas", 9),
                 justify="left").pack(anchor="w", pady=(2, 0))

    # ── 3. 미리보기 + 자율주행 ────────────────────────────────────────────────
    def _build_preview(self, body: Any, tk: Any) -> None:
        card = self._card(body, 4)
        self._card_title(card, "3", "미리보기 — AI의 판단")
        wrap = tk.Frame(card, bg=CARD)
        wrap.pack(fill="both", expand=True, padx=14, pady=8)
        self.canvas = tk.Label(wrap, bg="#202124", width=CANVAS_W, height=CANVAS_H)
        self._blank = tk.PhotoImage(width=CANVAS_W, height=CANVAS_H)
        self.canvas.configure(image=self._blank)
        self.canvas.pack()

        bars = tk.Frame(wrap, bg=CARD)
        bars.pack(fill="x", pady=(10, 4))
        for cls in S.CLASSES:
            col = self._colors[cls]
            r = tk.Frame(bars, bg=CARD)
            r.pack(fill="x", pady=2)
            tk.Label(r, text=cls, bg=CARD, fg=INK, font=(F, 9, "bold"),
                     width=9, anchor="w").pack(side="left")
            track = tk.Frame(r, bg="#ECEFF1", width=BAR_W, height=20,
                             highlightbackground=LINE, highlightthickness=1)
            track.pack(side="left")
            track.pack_propagate(False)
            fill = tk.Frame(track, bg=col)
            fill.place(x=0, y=0, relheight=1.0, relwidth=0.0)
            self.bar_fill[cls] = fill
            pv = tk.StringVar(value="0%")
            self.bar_pct[cls] = pv
            tk.Label(r, textvariable=pv, bg=CARD, fg=MUTED, font=("Consolas", 9),
                     width=5, anchor="e").pack(side="left", padx=(6, 0))
        self.pred_var = tk.StringVar(value="예측: (학습 후 표시)")
        tk.Label(wrap, textvariable=self.pred_var, bg=CARD, fg=INK,
                 font=(F, 11, "bold")).pack(anchor="w", pady=(4, 8))

        # 자율주행 컨트롤
        drv = tk.Frame(wrap, bg=CARD)
        drv.pack(fill="x")
        self.conf_var = self._num_row(drv, "신뢰도 임계값", 0.6)
        drv2 = tk.Frame(wrap, bg=CARD)
        drv2.pack(fill="x", pady=(2, 6))
        self.speed_var = self._num_row(drv2, "속도", 10.0)
        brow = tk.Frame(wrap, bg=CARD)
        brow.pack(fill="x")
        tk.Button(brow, text="▶ 자율주행", command=self._start_drive, bg=OKGREEN,
                  fg="white", font=(F, 11, "bold"), relief="flat", padx=12, pady=8,
                  cursor="hand2").pack(side="left", fill="x", expand=True, padx=(0, 4))
        tk.Button(brow, text="■ 정지", command=self._stop_drive, bg="#5F6368",
                  fg="white", font=(F, 11, "bold"), relief="flat", padx=12, pady=8,
                  cursor="hand2").pack(side="left", fill="x", expand=True, padx=(4, 0))
        self.drive_stat_var = tk.StringVar(value="이동:0  저신뢰정지:0  프레임없음:0")
        tk.Label(wrap, textvariable=self.drive_stat_var, bg=CARD, fg=MUTED,
                 font=("Consolas", 9)).pack(anchor="w", pady=(6, 0))

    def _num_row(self, parent: Any, label: str, default: float) -> Any:
        tk = self.tk
        tk.Label(parent, text=label, bg=CARD, fg=INK, width=12, anchor="w",
                 font=(F, 9)).pack(side="left")
        var = tk.StringVar(value=str(default))
        tk.Entry(parent, textvariable=var, width=7, relief="solid", bd=1,
                 font=("Consolas", 10)).pack(side="left")
        return var

    def _f(self, var: Any, name: str) -> Optional[float]:
        try:
            return float(var.get().strip())
        except Exception:
            self.log(f"[입력 오류] {name} 값 '{var.get()}' 을 숫자로 읽을 수 없습니다.")
            return None

    # ── 로그/UI 스레드 안전 ─────────────────────────────────────────────────
    def _ui(self, fn: Any, *args: Any) -> None:
        try:
            self.root.after(0, fn, *args)
        except Exception:
            pass

    def log(self, msg: str) -> None:
        self._log_q.append(time.strftime("%H:%M:%S ") + str(msg))

    def _drain_log(self) -> None:
        if self._log_q:
            for line in self._log_q:
                self.logbox.insert("end", line + "\n")
            self._log_q.clear()
            self.logbox.see("end")

    def _set_counts(self, cls: str) -> None:
        self.count_vars[cls].set(f"{self.policy.counts.get(cls, 0)} 샘플")

    # ── 로봇(GO) 독립 연결/해제 ───────────────────────────────────────────────
    def _set_go_connected(self, connected: bool, is_mock: bool = False) -> None:
        self.go_btn.configure(text="로봇 해제" if connected else "로봇 연결",
                              bg="#5F6368" if connected else "#1A73E8")
        self.robot_status.set(
            ("연결됨 · " + ("모의" if is_mock else "실로봇")) if connected else "미연결")

    def _toggle_go(self) -> None:
        if self.go is None:
            port = self.port_var.get().strip() or None
            mock = True if self.mock_var.get() else None
            threading.Thread(target=self._go_worker, args=(port, mock), daemon=True).start()
        else:
            self._disconnect_go()

    def _go_worker(self, port: Optional[str], mock: Optional[bool]) -> None:
        self._ui(self.robot_status.set, "연결 중...")
        try:
            go = get_go(port=port, mock=mock)
        except Exception as e:
            self._ui(self.robot_status.set, "실패")
            self.log(f"[로봇 오류] {e}")
            return
        self.go = go
        self._ui(self._set_go_connected, True, getattr(go, "is_mock", False))
        self.log(f"로봇 연결됨 ({'모의' if getattr(go, 'is_mock', False) else '실로봇'}).")

    def _disconnect_go(self) -> None:
        self._drive_stop.set()   # 주행 중이면 먼저 멈춤
        go, self.go = self.go, None
        if go is not None:
            try:
                with self._go_lock:
                    go.close()
            except Exception:
                pass
        self._set_go_connected(False)
        self.log("로봇 해제.")

    # ── 카메라(K210) 독립 연결/해제 ───────────────────────────────────────────
    def _set_cam_connected(self, connected: bool, is_mock: bool = False) -> None:
        self.cam_btn.configure(text="카메라 해제" if connected else "카메라 연결",
                               bg="#5F6368" if connected else "#188038")
        self.cam_status.set(
            ("연결됨 · " + ("모의" if is_mock else "K210")) if connected else "미연결")

    def _toggle_cam(self) -> None:
        if self.cam is None:
            source = self.cam_var.get().strip() or None
            mock = True if self.mock_var.get() else None
            threading.Thread(target=self._cam_worker, args=(source, mock), daemon=True).start()
        else:
            self._disconnect_cam()

    def _cam_worker(self, source: Optional[str], mock: Optional[bool]) -> None:
        self._ui(self.cam_status.set, "연결 중...")
        try:
            cam = get_camera(source=source, mock=mock)
        except Exception as e:
            self._ui(self.cam_status.set, "실패")
            self.log(f"[카메라 오류] {e} (동글 재삽입 후 다시 '카메라 연결')")
            return
        self.cam = cam
        self._cam_running = True
        self._cam_thread = threading.Thread(target=self._cam_loop, daemon=True)
        self._cam_thread.start()
        self._ui(self._set_cam_connected, True, getattr(cam, "is_mock", False))
        self.log(f"카메라 연결됨 (is_mock={getattr(cam, 'is_mock', '?')}).")

    def _disconnect_cam(self) -> None:
        self._cam_running = False
        cam, self.cam = self.cam, None
        with self._cam_lock:
            self._latest_frame = None
        if cam is not None:
            try:
                cam.close()
            except Exception:
                pass
        self._set_cam_connected(False)
        self.log("카메라 해제.")

    def _cam_loop(self) -> None:
        while self._cam_running:
            cam = self.cam
            if cam is None:
                time.sleep(0.1)
                continue
            try:
                frame = cam.get_frame()
            except Exception as e:
                self.log(f"[카메라 오류] {e}")
                time.sleep(0.5)
                continue
            if frame is not None:
                with self._cam_lock:
                    self._latest_frame = frame
            time.sleep(0.01)

    def _peek_frame(self) -> Optional[Any]:
        with self._cam_lock:
            return self._latest_frame

    # ── 녹화 ────────────────────────────────────────────────────────────────
    def _record(self, label: str) -> None:
        frame = self._peek_frame()
        if frame is None:
            self.log("[기록 불가] 아직 카메라 프레임이 없습니다. 먼저 연결하세요.")
            return
        try:
            self.policy.add_example(frame, label)
        except Exception as e:
            self.log(f"[기록 오류] {e}")
            return
        self._set_counts(label)
        self.log(f"[기록] {label} +1  (총 {self.policy.counts.get(label, 0)})")

    # ── 학습 ────────────────────────────────────────────────────────────────
    def _train_async(self) -> None:
        threading.Thread(target=self._train, daemon=True).start()

    def _train(self) -> None:
        if not any(self.policy.counts.values()):
            self.log("[학습 불가] 예시가 없습니다. 먼저 ＋녹화로 기록하세요.")
            return
        self._ui(self.status_var.set, "학습 중...")
        try:
            m = self.policy.train(epochs=400, lr=0.5, val_ratio=0.2, seed=0)
        except Exception as e:
            self._ui(self.status_var.set, "학습 실패")
            self.log(f"[학습 오류] {e}")
            return
        self._ui(self.status_var.set, f"학습 완료 · train={m['train_acc']:.0%}")
        self._ui(self.train_head.set, f"학습 완료 · 시험 정확도 {m['val_acc']:.0%}")
        self._ui(self.train_var.set,
                 f"train_acc={m['train_acc']:.2f}  val_acc={m['val_acc']:.2f}\n"
                 f"(train {m['n_train']}건 / val {m['n_val']}건)\n혼동행렬:\n{m['confusion']}")
        self.log(f"[학습] train_acc={m['train_acc']:.2f} val_acc={m['val_acc']:.2f}")

    # ── 모델 저장 ────────────────────────────────────────────────────────────
    def _save_model(self) -> None:
        """학습된 정책을 팀 공용 경로에 저장한다. 이후 scaffold.py --model 이 읽는다."""
        if not self.policy.is_trained:
            self.log("[저장 불가] 먼저 '모델 학습'을 누르세요.")
            self._ui(self.save_var.set, "아직 학습 전이라 저장할 수 없어요.\n먼저 '모델 학습'을 누르세요.")
            return
        try:
            self.policy.save(DEFAULT_MODEL_PATH)
        except Exception as e:
            self.log(f"[저장 오류] {e}")
            self._ui(self.save_var.set, f"저장 실패: {e}")
            return
        self.log(f"[저장] 모델 저장 완료 → {DEFAULT_MODEL_PATH}")
        self._ui(self.save_var.set,
                 "저장 완료! 이제 GUI를 닫고 각자 PC에서\n"
                 "python h3_vision_ai/scaffold.py --port COM5 --model\n"
                 "을 실행하면 이 모델로 진짜 로봇이 달립니다.")

    # ── 자율주행 ─────────────────────────────────────────────────────────────
    def _start_drive(self) -> None:
        if self.go is None:
            self.log("자율주행하려면 먼저 '로봇 연결'을 누르세요.")
            return
        if self.cam is None:
            self.log("자율주행하려면 먼저 '카메라 연결'을 누르세요.")
            return
        if not self.policy.is_trained:
            self.log("먼저 '모델 학습'을 누르세요.")
            return
        if self._drive_thread is not None and self._drive_thread.is_alive():
            self.log("이미 주행 중입니다. 먼저 정지를 누르세요.")
            return
        conf_th = self._f(self.conf_var, "신뢰도 임계값")
        speed = self._f(self.speed_var, "속도")
        if conf_th is None or speed is None:
            return
        self._drive_stop.clear()
        self._drive_thread = threading.Thread(
            target=self._drive_run, args=(conf_th, speed), daemon=True)
        self._drive_thread.start()

    def _stop_drive(self) -> None:
        self._drive_stop.set()

    def _drive_run(self, conf_th: float, speed: float) -> None:
        go, cam, policy = self.go, self.cam, self.policy
        self._ui(self.status_var.set, "자율주행 중...")
        self.log(f"[주행] 시작 conf_th={conf_th}, speed={speed}")
        total = {"steps": 0, "stops": 0, "low_conf": 0}
        try:
            for _ in range(DRIVE_MAX_CHUNKS):        # 유한 루프(안전)
                if self._drive_stop.is_set():
                    self.log("[주행] 사용자 정지 요청")
                    break
                with self._go_lock:
                    res = S.autonomous_drive(
                        go, cam, policy, conf_th=conf_th, speed=speed,
                        steps=DRIVE_CHUNK, loop_dt=S.LOOP_DT)
                total["steps"] += res["steps"]
                total["stops"] += res["stops"]
                total["low_conf"] += res["low_conf"]
                self._ui(self._update_drive_stat, dict(total))
                if res["aborted"]:
                    self.log(f"[안전중단] {res['reason']}")
                    break
        except Exception as e:
            self.log(f"[주행 오류] {e}")
        finally:
            with self._go_lock:
                try:
                    go.stop()
                except Exception:
                    pass
            self._ui(self.status_var.set, "주행 정지됨")
            self.log(f"[주행] 종료. 이동 {total['steps']}, 저신뢰정지 {total['low_conf']}, "
                     f"프레임없음 {total['stops']}")

    def _update_drive_stat(self, total: dict) -> None:
        self.drive_stat_var.set(
            f"이동:{total['steps']}  저신뢰정지:{total['low_conf']}  "
            f"프레임없음:{total['stops']}")

    # ── 신뢰도 막대(티처블머신식) — UI 스레드에서 최신 프레임으로 갱신 ──────────
    def _update_bars(self) -> None:
        frame = self._peek_frame()
        if frame is None or not self.policy.is_trained:
            return
        try:
            probs = self.policy.predict_proba(frame)
        except Exception:
            return
        top = max(probs, key=lambda k: probs[k])
        for cls, p in probs.items():
            try:
                self.bar_fill[cls].place_configure(relwidth=max(0.0, min(1.0, p)))
                self.bar_pct[cls].set(f"{p * 100:.0f}%")
            except Exception:
                pass
        conf_th = self._f(self.conf_var, "임계값") or 0.6
        mark = "✓" if probs[top] >= conf_th else "· 저신뢰 → 정지"
        self.pred_var.set(f"예측: {top}  ({probs[top]:.0%}) {mark}")

    # ── 카메라 표시(UI 스레드) ────────────────────────────────────────────────
    def _tick(self) -> None:
        frame = self._peek_frame()
        if frame is not None:
            try:
                from PIL import Image, ImageTk
                img = Image.fromarray(frame).resize(
                    (CANVAS_W, CANVAS_H), Image.Resampling.NEAREST)
                imgtk = ImageTk.PhotoImage(img)
                self.canvas.imgtk = imgtk  # type: ignore[attr-defined]
                self.canvas.configure(image=imgtk)
            except Exception:
                pass
        self._update_bars()
        self._drain_log()
        try:
            self.root.after(int(CAM_POLL_S * 1000), self._tick)
        except Exception:
            pass

    # ── 비상정지/종료 ────────────────────────────────────────────────────────
    def _estop(self) -> None:
        self.log("■ 비상정지!")
        self.status_var.set("■ 비상정지됨")
        self._drive_stop.set()
        go = self.go
        if go is not None:
            try:
                go.emergency_stop()
            except Exception as e:
                self.log(f"[비상정지 오류] {e}")

    def _on_close(self) -> None:
        self._drive_stop.set()
        self._cam_running = False
        cam, self.cam = self.cam, None
        go, self.go = self.go, None
        if cam is not None:
            try:
                cam.close()
            except Exception:
                pass
        if go is not None:
            try:
                with self._go_lock:
                    go.close()
            except Exception:
                pass
        try:
            self.root.destroy()
        except Exception:
            pass

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    app = H3VisionApp()
    app.run()



# ============================================================================
# ── standalone 편의: mock 여부 조회(스모크 테스트/사용자 확인용)
# ============================================================================
def is_mock() -> bool:
    """이 실행이 모의(mock) 경로인지: GO(로봇) 또는 카메라 중 하나라도 mock 이면 True.

    CURRICULUM_FORCE_MOCK=1 이거나 websockets/pyserial 미설치 시 mock 이 된다.
    """
    return bool(go_is_mock() or cam_is_mock())


"""robotvision — 카메라에서 본 물건의 '픽셀 자리'를 로봇의 '진짜 자리(mm)'로 바꿔 준다.

왜 필요한가
-----------
카메라 사진에서 물건을 찾으면 결과는 "가로 320번째, 세로 240번째 점"처럼 **픽셀** 이다.
그런데 로봇팔은 mm 단위의 좌표(x, y)로만 움직인다. 둘은 서로 다른 자(尺)라서 그대로는
이어 붙일 수 없다. 그래서 수업 시작 전에 한 번 **자리 맞추기(캘리브레이션)** 를 해 두고,
그때 구한 변환표(아핀 행렬 M)로 픽셀 → mm 를 바꾼다. 이 모듈이 있어야 학생 블록에서
"카메라로 본 그 자리로 가서 집기"를 할 수 있다.

좌표계
------
  픽셀 좌표 (u, v)  : 카메라 사진 기준. u=가로(왼→오), v=세로(위→아래), 왼쪽 위가 (0, 0).
  로봇 좌표 (x, y)  : dobotkit MagicianLite 작업평면의 mm. 높이 z 는 여기서 다루지 않는다
                      (물건 높이는 수업마다 다르므로 예제에서 직접 정한다).

아핀 변환식 — src/utils/affineCalib.js 의 applyAffine 과 **같은 행/열 배치**
  M = [[a, b, c],
       [d, e, f]]
  x = a*u + b*v + c
  y = d*u + e*v + f

보정값 파일
-----------
워크스페이스(= 파이썬이 실행되는 폴더)의 `robot_calib.json` 에서 읽는다. 형식은
src/data/robotCalib.default.json 과 같고, 실제로는 로봇 패널의 '자리 맞추기'가 저장한다.
파일이 없거나 M 이 아직 측정 전이면 is_ready() 는 False 이고 to_robot() 은 한국어 안내
오류를 낸다.

학생 블록에서 쓰는 함수는 셋뿐이다 — is_ready(), to_robot(u, v), find_object(frame).
"""
import json
import os

# 보정 파일 이름 (계약 4: <WORKSPACE_DIR>/robot_calib.json)
CALIB_FILE = "robot_calib.json"

# 자리 맞추기를 아직 안 했을 때 학생에게 보여 줄 안내문
_NOT_READY_MESSAGE = (
    "자리 맞추기를 먼저 해 주세요. 로봇 패널 → 자리 맞추기\n"
    "(카메라가 본 자리를 로봇 자리로 바꾸려면 " + CALIB_FILE + " 파일이 있어야 합니다.)"
)

# 같은 파일을 반복해 읽지 않도록 기억해 둔다. 파일이 바뀌면(수정시각) 다시 읽는다.
_cache = {"path": None, "mtime": None, "M": None}


def _candidate_paths():
    """robot_calib.json 을 찾아볼 자리들 — 실행 폴더가 먼저다."""
    paths = [os.path.join(os.getcwd(), CALIB_FILE)]
    workspace = os.environ.get("BLOCKPY_WORKSPACE")
    if workspace:
        paths.append(os.path.join(workspace, CALIB_FILE))
    return paths


def _valid_matrix(M):
    """M 이 쓸 수 있는 2x3 숫자 행렬인가."""
    if not isinstance(M, (list, tuple)) or len(M) != 2:
        return False
    for row in M:
        if not isinstance(row, (list, tuple)) or len(row) != 3:
            return False
        for n in row:
            if isinstance(n, bool) or not isinstance(n, (int, float)):
                return False
    return True


def _load_matrix():
    """보정 파일에서 아핀 행렬 M 을 읽어 온다. 없거나 미측정이면 None."""
    for path in _candidate_paths():
        if not os.path.exists(path):
            continue
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            mtime = None
        if _cache["path"] == path and _cache["mtime"] == mtime:
            return _cache["M"]
        M = None
        try:
            f = open(path, "r", encoding="utf-8")
            try:
                data = json.load(f)
            finally:
                f.close()
            if isinstance(data, dict):
                # measured 가 명시적으로 False 면 아직 안 잰 것으로 본다.
                if data.get("measured", True) is not False:
                    candidate = data.get("M")
                    if _valid_matrix(candidate):
                        M = [[float(n) for n in row] for row in candidate]
        except (ValueError, OSError, UnicodeDecodeError):
            M = None  # 깨진 파일 → 미보정으로 취급(학생에게는 안내문이 뜬다)
        _cache["path"] = path
        _cache["mtime"] = mtime
        _cache["M"] = M
        return M
    return None


def is_ready():
    """자리 맞추기가 끝나 있으면 True, 아직이면 False."""
    return _load_matrix() is not None


def to_robot(u, v):
    """카메라 픽셀 (u, v) → 로봇 좌표 (x, y) mm.

    자리 맞추기를 안 했으면 한국어 안내와 함께 RuntimeError 를 낸다.
    """
    M = _load_matrix()
    if M is None:
        raise RuntimeError(_NOT_READY_MESSAGE)
    u = float(u)
    v = float(v)
    # affineCalib.js 의 applyAffine 과 같은 순서로 곱한다(행=출력축, 열=[u, v, 1]).
    x = M[0][0] * u + M[0][1] * v + M[0][2]
    y = M[1][0] * u + M[1][1] * v + M[1][2]
    return (x, y)


def find_object(frame):
    """사진에서 배경과 가장 다른 '가장 큰 덩어리'의 가운데 점 (u, v) 를 돌려준다.

    못 찾으면 None. 화면 가장자리의 작은 얼룩에 흔들리지 않도록 최소 면적 기준을 둔다.
    """
    import cv2

    if frame is None:
        return None
    shape = getattr(frame, "shape", None)
    if shape is None or len(shape) < 2:
        return None
    height = int(shape[0])
    width = int(shape[1])
    if height < 2 or width < 2:
        return None

    if len(shape) == 3 and shape[2] == 3:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    else:
        gray = frame
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # 배경과 물건을 자동으로 가르는 밝기 기준(Otsu). 흰 부분이 화면 절반을 넘으면
    # 그건 물건이 아니라 배경이므로 흑백을 뒤집는다.
    _, mask = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if cv2.countNonZero(mask) * 2 > width * height:
        mask = cv2.bitwise_not(mask)

    # 점 같은 잡음 제거(열기 연산).
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

    found = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = found[-2]  # OpenCV 3/4 의 반환 개수 차이를 흡수
    if contours is None or len(contours) == 0:
        return None

    # 너무 작으면 잡음(가장자리 얼룩), 너무 크면 배경 전체다. 둘 다 버린다.
    total = float(width * height)
    min_area = max(200.0, total * 0.002)
    max_area = total * 0.9

    best = None
    best_area = 0.0
    for c in contours:
        area = cv2.contourArea(c)
        if area < min_area or area > max_area:
            continue
        if area > best_area:
            best_area = area
            best = c
    if best is None:
        return None

    m = cv2.moments(best)
    if m["m00"] == 0:
        return None
    u = m["m10"] / m["m00"]
    v = m["m01"] / m["m00"]
    return (int(round(u)), int(round(v)))

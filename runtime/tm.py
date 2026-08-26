"""tm — 파이썬 네이티브 Teachable Machine.

MobileNetV2(전이학습) 특징 + 소형 head(dense100-relu→denseN-softmax)를 파이썬 안에서 수집·학습·
추론한다. 브라우저 TM 패널과 같은 개념이나 전 과정 파이썬이라 자기일관적(크로스-환경 패리티 없음).
frame 은 numpy uint8 (H,W,3) 이미지(cv2 로 캡처, BGR). server.js 가 PYTHONPATH 로 실어 `import tm`.
의존성: tensorflow, numpy. tensorflow 미설치 시 friendly 오류로 degrade.
"""
import os
import numpy as np

_IMAGE_SIZE = 224
_base = None  # lazy MobileNet featurizer (프로세스당 1회)


def _ensure_tf():
    try:
        import tensorflow as tf
        return tf
    except ImportError as e:
        raise RuntimeError(
            "tm: tensorflow 가 필요합니다. `pip install tensorflow` 후 다시 실행하세요."
        ) from e


def _resolve_weights():
    # 가중치를 찾는 순서:
    #   1) BLOCKPY_TM_WEIGHTS — 온라인 설치본이 첫 실행 때 받아 둔 파일(앱이 이 변수로 알려 준다).
    #      설치 폴더에는 쓸 수 없어 userData 아래에 두므로 경로를 코드에 박을 수 없다.
    #   2) runtime/mobilenet_v2_weights.h5 — 오프라인 완본이 함께 담아 온 것.
    #   3) keras 'imagenet' — 위 둘이 없을 때. 이때는 **첫 학습에 인터넷이 필요하다**.
    env = os.environ.get("BLOCKPY_TM_WEIGHTS", "").strip()
    if env and os.path.exists(env):
        return env
    here = os.path.dirname(os.path.abspath(__file__))
    bundled = os.path.join(here, "mobilenet_v2_weights.h5")
    return bundled if os.path.exists(bundled) else "imagenet"


def _ensure_base():
    global _base
    if _base is not None:
        return _base
    tf = _ensure_tf()
    from tensorflow.keras.applications import MobileNetV2
    _base = MobileNetV2(input_shape=(_IMAGE_SIZE, _IMAGE_SIZE, 3), alpha=1.0,
                        include_top=False, weights=_resolve_weights(), pooling="avg")
    return _base


def _embed(frame):
    """frame(numpy uint8 H,W,3, BGR) -> MobileNet 임베딩 [1,1280]."""
    tf = _ensure_tf()
    from tensorflow.keras.applications.mobilenet_v2 import preprocess_input
    a = np.asarray(frame)
    if a.ndim != 3 or a.shape[2] != 3:
        raise ValueError("tm: frame 은 (H,W,3) numpy 이미지여야 합니다.")
    a = a[:, :, ::-1]  # cv2 BGR -> RGB
    img = tf.image.resize(tf.convert_to_tensor(a[np.newaxis].astype("float32")),
                          [_IMAGE_SIZE, _IMAGE_SIZE])
    x = preprocess_input(img)
    return np.asarray(_ensure_base().predict(x, verbose=0))


def _build_head(tf, dim, n):
    m = tf.keras.Sequential([
        tf.keras.layers.Input((dim,)),
        tf.keras.layers.Dense(100, activation="relu"),
        tf.keras.layers.Dense(n, activation="softmax"),
    ])
    m.compile(optimizer="adam", loss="sparse_categorical_crossentropy", metrics=["accuracy"])
    return m


class Model:
    def __init__(self, labels):
        if not isinstance(labels, (list, tuple)) or len(labels) < 2:
            raise ValueError("tm.Model: labels 는 2개 이상의 클래스 이름 리스트여야 합니다.")
        self._labels = [str(l) for l in labels]
        self._idx = {l: i for i, l in enumerate(self._labels)}
        self._X, self._y, self._head = [], [], None

    @property
    def labels(self):
        return list(self._labels)

    def add_example(self, frame, label):
        if label not in self._idx:
            raise ValueError(f"tm: 알 수 없는 라벨 {label!r} (labels={self._labels})")
        self._X.append(_embed(frame)[0])
        self._y.append(self._idx[label])

    def train(self, epochs=30):
        if not self._X:
            raise RuntimeError("tm: 학습할 예시가 없습니다. 먼저 add_example 로 수집하세요.")
        counts = np.bincount(self._y, minlength=len(self._labels))
        if (counts == 0).any():
            missing = [self._labels[i] for i in np.where(counts == 0)[0]]
            raise RuntimeError(f"tm: 각 클래스에 예시가 1개 이상 필요합니다. 부족: {missing}")
        tf = _ensure_tf()
        X = np.asarray(self._X, dtype="float32")
        y = np.asarray(self._y)
        self._head = _build_head(tf, X.shape[1], len(self._labels))
        self._head.fit(X, y, epochs=epochs, verbose=0)

    def _proba(self, frame):
        if self._head is None:
            raise RuntimeError("tm: 아직 학습되지 않았습니다. train() 을 먼저 호출하세요.")
        return np.asarray(self._head.predict(_embed(frame), verbose=0))[0]

    def predict(self, frame):
        p = self._proba(frame)
        i = int(np.argmax(p))
        return self._labels[i], float(p[i])

    def predict_proba(self, frame):
        p = self._proba(frame)
        return {l: float(p[i]) for i, l in enumerate(self._labels)}

    def save(self, path):
        if self._head is None:
            raise RuntimeError("tm: 학습 후 저장할 수 있습니다. train() 을 먼저 호출하세요.")
        W1, b1, W2, b2 = self._head.get_weights()
        np.savez(path, labels=np.array(self._labels, dtype=object), W1=W1, b1=b1, W2=W2, b2=b2)


def load_model(path):
    d = np.load(path, allow_pickle=True)
    labels = [str(l) for l in d["labels"]]
    tf = _ensure_tf()
    m = Model(labels)
    head = _build_head(tf, int(d["W1"].shape[0]), len(labels))
    head.set_weights([d["W1"], d["b1"], d["W2"], d["b2"]])
    m._head = head
    return m

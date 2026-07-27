# [H2] 텔레오퍼레이션 — 손 제스처로 로봇팔을 실시간 원격 조종한다
# 고등 파이썬 수업: 제스처 분류(Teachable Machine)를 파이썬으로 학습하고,
# 인식 결과를 로봇 동작에 매핑하는 제어 루프를 함수로 구조화한다.
import tm
import cv2
import dobotkit

GESTURES = ['위', '아래', '왼쪽', '오른쪽', '집기', '펴기']


def train_gesture_model(cam, samples_per_class=20):
    """각 제스처를 카메라로 보여주며 샘플을 모아 학습한다."""
    model = tm.Model(GESTURES)
    for name in GESTURES:
        print('"' + name + '" 제스처를 보여주세요...')
        for _ in range(samples_per_class):
            ok, frame = cam.read()
            if ok:
                model.add_example(frame, name)
    model.train()
    return model


def apply_gesture(arm, label):
    """인식된 제스처를 로봇팔 동작으로 바꾼다."""
    if label == '위':
        arm.move_relative(0, 0, 15)
    elif label == '아래':
        arm.move_relative(0, 0, -15)
    elif label == '왼쪽':
        arm.move_relative(0, 15, 0)
    elif label == '오른쪽':
        arm.move_relative(0, -15, 0)
    elif label == '집기':
        arm.suck(True)
    elif label == '펴기':
        arm.suck(False)


def main():
    cam = cv2.VideoCapture(0)
    model = train_gesture_model(cam)

    try:
        arm = dobotkit.MagicianLite()
    except Exception as e:
        print('로봇팔에 연결할 수 없습니다:', e)
        print('DobotLink 프로그램을 켜고 팔 전원을 넣은 뒤 다시 실행하세요.')
        return
    arm.home()

    print('이제 제스처로 팔을 조종하세요. (Ctrl+C 로 종료)')
    while True:
        ok, frame = cam.read()
        if not ok:
            continue
        label, conf = model.predict(frame)
        if conf > 0.7:
            apply_gesture(arm, label)


if __name__ == '__main__':
    main()

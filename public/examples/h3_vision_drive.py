# [H3] 비전 AI 자율주행 — 카메라로 길을 배워서 스스로 달린다
# 고등 파이썬 수업: 수집→학습→추론(Teachable Machine 스타일)을 파이썬으로 구현하고,
# 예측 결과로 Magician GO 를 주행시키는 자율주행 루프를 함수로 구조화한다.
import tm
import cv2
import dobotkit

DIRECTIONS = ['왼쪽', '직진', '오른쪽']


def collect_and_train(cam, samples_per_class=30):
    """방향별로 길 사진을 모아 주행 모델을 학습한다."""
    model = tm.Model(DIRECTIONS)
    for name in DIRECTIONS:
        print('"' + name + '" 상황의 길을 보여주세요...')
        for _ in range(samples_per_class):
            ok, frame = cam.read()
            if ok:
                model.add_example(frame, name)
    model.train()
    return model


def drive(car, label):
    """예측한 방향으로 주행한다."""
    if label == '왼쪽':
        car.move(30, 0, -20)
    elif label == '오른쪽':
        car.move(30, 0, 20)
    else:
        car.forward(30)


def main():
    cam = cv2.VideoCapture(0)
    model = collect_and_train(cam)

    try:
        car = dobotkit.MagicianGO.open('COM5')
    except Exception as e:
        print('주행로봇에 연결할 수 없습니다:', e)
        print('DobotLink 를 켜고 차량 전원/무선동글을 확인한 뒤 다시 실행하세요.')
        return
    print('자율주행을 시작합니다!')
    for step in range(500):
        ok, frame = cam.read()
        if not ok:
            continue
        label, conf = model.predict(frame)
        print('방향:', label, round(conf, 2))
        drive(car, label)
    car.stop()


if __name__ == '__main__':
    main()

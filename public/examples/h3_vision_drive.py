# [H3] 비전 AI 자율주행 — 카메라로 길을 배워서 스스로 달린다
# 가르쳐서 달리는 자동차(Teachable Machine 스타일): 카메라 화면으로
# 왼쪽/직진/오른쪽을 배우고(수집→학습), 그 예측으로 Magician GO 를 주행시킨다.
import tm
import cv2
import dobotkit

cam = cv2.VideoCapture(0)

# 1) 주행 방향 모델 학습 (길 사진을 방향별로 보여주며 수집)
model = tm.Model(['왼쪽', '직진', '오른쪽'])
ok, frame = cam.read()
model.add_example(frame, '직진')
model.train()

# 2) 주행 카 연결
car = dobotkit.MagicianGO.open('COM5')

# 3) 카메라를 보며 자율주행
for step in range(200):
    ok, frame = cam.read()
    label, conf = model.predict(frame)
    print('자율주행 방향:', label)
    if label == '왼쪽':
        car.move(30, 0, -20)
    elif label == '오른쪽':
        car.move(30, 0, 20)
    else:
        car.forward(30)
car.stop()

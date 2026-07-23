# [M1] AI 분리수거 로봇팔 — 색을 배워서 색깔별로 분류한다
# 카메라로 색을 가르치고(Teachable Machine), 로봇팔이 색깔별 통으로 옮긴다.
import tm
import cv2
import dobotkit

cam = cv2.VideoCapture(0)

# 1) 색상 분류 모델 만들고 학습 (각 색 물체를 카메라로 보여주며 수집)
model = tm.Model(['빨강', '파랑', '노랑'])
ok, frame = cam.read()
model.add_example(frame, '빨강')
model.train()

# 2) 로봇팔 연결하고 시작 자세로
arm = dobotkit.MagicianLite()
arm.home()

# 3) 색을 알아보고 색깔별 통으로 옮기기
ok, frame = cam.read()
label, conf = model.predict(frame)
print('분류 결과:', label, conf)

arm.move_to(200, 0, 40)
arm.suck(True)
if label == '빨강':
    arm.move_to(150, 100, 40)
elif label == '파랑':
    arm.move_to(150, 0, 40)
else:
    arm.move_to(150, -100, 40)
arm.suck(False)
arm.home()

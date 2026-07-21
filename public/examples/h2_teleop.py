# [H2] 텔레오퍼레이션 — 손 제스처로 로봇팔을 원격 조종한다
# 카메라로 손 제스처(위/아래/집기/펴기)를 배우고(Teachable Machine),
# 실시간으로 알아보며 로봇팔을 그때그때 움직인다.
import tm
import cv2
import dobotkit

cam = cv2.VideoCapture(0)

# 1) 제스처 모델 학습
model = tm.Model(['위', '아래', '집기', '펴기'])
ok, frame = cam.read()
model.add_example(frame, '위')
model.train()

# 2) 로봇팔 연결
arm = dobotkit.MagicianLite()
arm.home()

# 3) 손 제스처를 계속 읽어 로봇팔을 조종
for step in range(100):
    ok, frame = cam.read()
    label, conf = model.predict(frame)
    print(label, conf)
    if label == '위':
        arm.move_relative(0, 0, 15)
    elif label == '아래':
        arm.move_relative(0, 0, -15)
    elif label == '집기':
        arm.suck(True)
    elif label == '펴기':
        arm.suck(False)

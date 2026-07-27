# [M1] AI 분리수거 로봇팔 — 색을 배워서 색깔별로 분류한다
# 카메라로 색을 가르치고(Teachable Machine), 로봇팔이 색깔별 통으로 옮긴다.
import tm
import cv2
import dobotkit
import os

# 학습한 모델을 저장해두는 파일. 다음 실행부터는 이 파일을 불러와 바로 사용한다.
MODEL_FILE = 'color_model.npz'

cam = cv2.VideoCapture(0)

# 1) 모델 준비 — 저장된 모델이 있으면 불러오고, 없으면 새로 배운 뒤 저장한다
if os.path.exists(MODEL_FILE):
    model = tm.load_model(MODEL_FILE)
    print('저장된 모델을 불러왔습니다:', MODEL_FILE)
else:
    model = tm.Model(['빨강', '파랑', '노랑'])
    ok, frame = cam.read()
    model.add_example(frame, '빨강')
    model.train()
    model.save(MODEL_FILE)
    print('학습한 모델을 저장했습니다:', MODEL_FILE)

# 2) 로봇팔 연결하고 시작 자세로
try:
    arm = dobotkit.MagicianLite()
except Exception as e:
    print('로봇팔에 연결할 수 없습니다:', e)
    print('DobotLink 프로그램을 켜고 팔 전원을 넣은 뒤 다시 실행하세요.')
    raise SystemExit
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

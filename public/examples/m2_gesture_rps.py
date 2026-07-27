# [M2] 사람과 가위바위보 — 손 모양을 배워서 로봇이 대결한다
# 카메라로 가위/바위/보를 가르치고(Teachable Machine), 사람 손을 알아본 뒤
# 로봇팔이 이기는 손을 낸다.
import tm
import cv2
import dobotkit
import os

# 학습한 모델을 저장해두는 파일. 다음 실행부터는 이 파일을 불러와 바로 사용한다.
MODEL_FILE = 'rps_model.npz'

cam = cv2.VideoCapture(0)

# 1) 모델 준비 — 저장된 모델이 있으면 불러오고, 없으면 새로 배운 뒤 저장한다
if os.path.exists(MODEL_FILE):
    model = tm.load_model(MODEL_FILE)
    print('저장된 모델을 불러왔습니다:', MODEL_FILE)
else:
    model = tm.Model(['가위', '바위', '보'])
    ok, frame = cam.read()
    model.add_example(frame, '가위')
    model.train()
    model.save(MODEL_FILE)
    print('학습한 모델을 저장했습니다:', MODEL_FILE)

# 2) 로봇팔 연결
try:
    arm = dobotkit.MagicianLite()
except Exception as e:
    print('로봇팔에 연결할 수 없습니다:', e)
    print('DobotLink 프로그램을 켜고 팔 전원을 넣은 뒤 다시 실행하세요.')
    raise SystemExit
arm.home()

# 3) 사람 손을 알아보고, 이기는 손을 낸다
ok, frame = cam.read()
label, conf = model.predict(frame)
print('사람:', label)

if label == '가위':
    robot = '바위'
elif label == '바위':
    robot = '보'
else:
    robot = '가위'
print('로봇:', robot)

# 로봇이 손을 '탁' 내미는 동작
arm.move_to(200, 0, 60)
arm.move_to(200, 0, 20)
arm.home()

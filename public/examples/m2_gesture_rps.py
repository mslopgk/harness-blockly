# [M2] 사람과 가위바위보 — 손 모양을 배워서 로봇이 대결한다
# 카메라로 가위/바위/보를 가르치고(Teachable Machine), 사람 손을 알아본 뒤
# 로봇팔이 이기는 손을 낸다.
import tm
import cv2
import dobotkit

cam = cv2.VideoCapture(0)

# 1) 가위바위보 모델 학습 (각 손 모양을 카메라로 보여주며 수집)
model = tm.Model(['가위', '바위', '보'])
ok, frame = cam.read()
model.add_example(frame, '가위')
model.train()

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

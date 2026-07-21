# [H1] 자연어로 로봇 제어 — 말(명령어)로 로봇팔을 움직인다
# 사람이 입력한 명령을 알아듣고 로봇팔이 해당 동작을 수행한다.
# (원래 수업은 VLM+LLM 을 쓰지만, 여기서는 명령어 → 동작 매핑으로 핵심을 익힌다.)
import dobotkit

# 로봇팔 연결
arm = dobotkit.MagicianLite()
arm.home()
arm.set_speed(50, 50)

# 명령을 입력받아 실행 (예: 집어, 놓아, 올려, 내려, 집으로)
command = input('명령을 말하세요: ')

if command == '집어':
    arm.move_to(200, 0, 20)
    arm.suck(True)
elif command == '놓아':
    arm.move_to(150, 100, 20)
    arm.suck(False)
elif command == '올려':
    arm.move_relative(0, 0, 40)
elif command == '내려':
    arm.move_relative(0, 0, -40)
elif command == '집으로':
    arm.home()
else:
    print('모르는 명령이에요:', command)

print('현재 위치:', arm.get_pose())

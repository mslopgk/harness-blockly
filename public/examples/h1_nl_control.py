# [H1] 자연어로 로봇 제어 — 말로 지시하면 로봇팔이 알아듣고 움직인다
# 고등 파이썬 수업: 자연어(키워드) 해석 → 동작 매핑을 함수로 구조화한다.
# (원래 수업은 VLM(눈)+LLM(두뇌)로 VLA를 하지만, 여기선 파이썬으로 명령 해석기를 직접 만든다.)
import dobotkit

# 미리 정해둔 자리 (실제로는 카메라 캘리브레이션으로 픽셀→로봇 좌표를 구한다)
PLACES = {
    '왼쪽': (150, 100, 40),
    '가운데': (200, 0, 40),
    '오른쪽': (150, -100, 40),
}


def parse_command(text):
    """자연어 문장에서 동작(집기/놓기)과 위치를 뽑아낸다."""
    action = None
    if '집' in text:
        action = 'pick'
    elif '놓' in text or '내려' in text:
        action = 'place'

    place = None
    for name in PLACES:
        if name in text:
            place = name
    return action, place


def run_command(arm, text):
    """해석한 명령을 로봇팔 동작으로 실행한다."""
    action, place = parse_command(text)
    if place is not None:
        x, y, z = PLACES[place]
        arm.move_to(x, y, z)
    if action == 'pick':
        arm.suck(True)
    elif action == 'place':
        arm.suck(False)
    else:
        print('무슨 동작인지 모르겠어요:', text)


def main():
    try:
        arm = dobotkit.MagicianLite()
    except Exception as e:
        print('로봇팔에 연결할 수 없습니다:', e)
        print('DobotLink 프로그램을 켜고 팔 전원을 넣은 뒤 다시 실행하세요.')
        return
    arm.set_speed(50, 50)
    arm.home()

    print('명령을 말해보세요. (예: "왼쪽 물건 집어", "가운데에 놓아")  끝내려면 "끝"')
    while True:
        text = input('명령> ')
        if text == '끝' or text == '':
            break
        run_command(arm, text)

    arm.home()
    print('종료합니다. 마지막 위치:', arm.get_pose())


if __name__ == '__main__':
    main()

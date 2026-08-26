# [H1-②] 움직이기 — 알아들은 명령대로 로봇팔을 움직인다
#
# ①알아듣기 를 그대로 담고 있고, 뒤에 '동작 실행'이 붙었다.
# 이 파일 하나만 열어도 돌아간다.
#
# 새로 배우는 것: 해석 결과(동작, 자리)를 로봇 동작으로 바꿔 주는 함수 run_command.
# 블록으로도 깔끔히 펼쳐지도록 try/except·컴프리헨션·데코레이터는 쓰지 않는다.
import dobotkit

# 미리 정해둔 자리 (2차시에서는 카메라 캘리브레이션으로 픽셀→로봇 좌표를 구한다)
자리표 = {
    '왼쪽': (150, 100, 40),
    '가운데': (200, 0, 40),
    '오른쪽': (150, -100, 40),
}


def parse_command(문장):
    """자연어 문장에서 동작(집기/놓기)과 자리 이름을 뽑아낸다."""
    동작 = None
    if '집' in 문장:
        동작 = 'pick'
    elif '놓' in 문장 or '내려' in 문장:
        동작 = 'place'

    자리 = None
    for 이름 in 자리표:
        if 이름 in 문장:
            자리 = 이름
    return 동작, 자리


def run_command(팔, 문장):
    """해석한 명령을 로봇팔 동작으로 실행한다."""
    동작, 자리 = parse_command(문장)
    if 자리 is not None:
        x, y, z = 자리표[자리]
        팔.move_to(x, y, z)
    if 동작 == 'pick':
        팔.suck(True)
    elif 동작 == 'place':
        팔.suck(False)
    else:
        print('무슨 동작인지 모르겠어요:', 문장)


def main():
    팔 = dobotkit.MagicianLite()
    팔.set_speed(50, 50)
    팔.home()

    # 미리 적어 둔 명령 몇 개를 차례로 실행해 본다
    연습문장 = ['왼쪽 물건 집어', '오른쪽에 놓아']
    for 문장 in 연습문장:
        print('명령:', 문장)
        run_command(팔, 문장)

    팔.home()
    print('마지막 위치:', 팔.get_pose())

    # 바람을 끄지 않으면 계속 돌아간다 — 코드 마지막은 언제나 펌프 정지
    팔.pump_off()


if __name__ == '__main__':
    main()

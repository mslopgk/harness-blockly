# [H2-③] 조종하기 — 제스처로 로봇팔을 계속 원격 조종한다 (고등 2차시 완성본)
# [H2] 텔레오퍼레이션 — 손 제스처로 로봇팔을 실시간 원격 조종한다
#
# ①배우기 + ②움직이기 를 그대로 담고 있고, 뒤에 '제어 루프'가 붙었다.
# 이 파일 하나만 열어도 처음부터 끝까지 돌아간다.
#
# 고등 파이썬 수업: 제스처 분류(Teachable Machine)를 파이썬으로 학습하고,
# 인식 결과를 로봇 동작에 매핑하는 제어 루프를 함수로 구조화한다.
# 블록으로도 깔끔히 펼쳐지도록 try/except·컴프리헨션·데코레이터는 쓰지 않는다.
import tm
import os
import cv2
import dobotkit

제스처들 = ['위', '아래', '왼쪽', '오른쪽', '집기', '펴기']

모델파일 = 'gesture_model.npz'
한제스처당샘플수 = 20
조종횟수 = 300


def train_gesture_model(카메라):
    """각 제스처를 카메라로 보여주며 샘플을 모아 학습한다."""
    모델 = tm.Model(제스처들)
    for 이름 in 제스처들:
        print('"' + 이름 + '" 제스처를 보여주세요...')
        for 번 in range(한제스처당샘플수):
            찍힘, 사진 = 카메라.read()
            if 찍힘:
                모델.add_example(사진, 이름)
    모델.train()
    return 모델


def get_gesture_model(카메라):
    """저장된 모델이 있으면 불러오고, 없으면 새로 학습한 뒤 저장한다."""
    if os.path.exists(모델파일):
        print('저장된 모델을 불러왔습니다:', 모델파일)
        return tm.load_model(모델파일)
    모델 = train_gesture_model(카메라)
    모델.save(모델파일)
    print('학습한 모델을 저장했습니다:', 모델파일)
    return 모델


def apply_gesture(팔, 이름표):
    """인식된 제스처를 로봇팔 동작으로 바꾼다."""
    if 이름표 == '위':
        팔.move_relative(0, 0, 15)
    elif 이름표 == '아래':
        팔.move_relative(0, 0, -15)
    elif 이름표 == '왼쪽':
        팔.move_relative(0, 15, 0)
    elif 이름표 == '오른쪽':
        팔.move_relative(0, -15, 0)
    elif 이름표 == '집기':
        팔.suck(True)
    elif 이름표 == '펴기':
        팔.suck(False)


def main():
    카메라 = cv2.VideoCapture(0)
    모델 = get_gesture_model(카메라)

    팔 = dobotkit.MagicianLite()
    팔.home()

    print('이제 제스처로 팔을 조종하세요.')
    for 번 in range(조종횟수):
        찍힘, 사진 = 카메라.read()
        if 찍힘:
            이름표, 확신 = 모델.predict(사진)
            if 확신 > 0.7:
                apply_gesture(팔, 이름표)

    팔.home()
    print('조종을 마쳤습니다.')

    # 바람을 끄지 않으면 계속 돌아간다 — 코드 마지막은 언제나 펌프 정지
    팔.pump_off()


if __name__ == '__main__':
    main()

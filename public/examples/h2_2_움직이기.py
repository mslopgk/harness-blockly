# [H2-②] 움직이기 — 알아본 제스처 하나를 로봇 동작으로 바꾼다
#
# ①배우기 를 그대로 담고 있고, 뒤에 '제스처 → 로봇 동작 매핑'이 붙었다.
# 이 파일 하나만 열어도 돌아간다.
#
# 새로 배우는 것: apply_gesture — 인식된 이름표를 팔의 동작으로 옮겨 주는 함수.
# 아직 계속 조종하지는 않는다(그건 ③조종하기). 여기서는 사진 한 장만 본다.
# 블록으로도 깔끔히 펼쳐지도록 try/except·컴프리헨션·데코레이터는 쓰지 않는다.
import tm
import os
import cv2
import dobotkit

제스처들 = ['위', '아래', '왼쪽', '오른쪽', '집기', '펴기']

모델파일 = 'gesture_model.npz'
한제스처당샘플수 = 20


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

    # 사진 한 장만 보고 그대로 한 번 움직여 본다
    찍힘, 사진 = 카메라.read()
    이름표, 확신 = 모델.predict(사진)
    print('제스처:', 이름표, 확신)
    if 확신 > 0.7:
        apply_gesture(팔, 이름표)
    else:
        print('잘 모르겠어요 — 손을 카메라에 더 크게 보여 주세요')

    팔.home()

    # 바람을 끄지 않으면 계속 돌아간다 — 코드 마지막은 언제나 펌프 정지
    팔.pump_off()


if __name__ == '__main__':
    main()

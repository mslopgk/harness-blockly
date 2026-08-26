# [H2-①] 배우기 — 제스처를 카메라로 가르치고 저장한다 (로봇 없음)
#
# 고등 2차시를 세 단계로 나눈 첫 번째 파일이다(배우기 → 움직이기 → 조종하기).
# 이 단계는 로봇을 쓰지 않는다. 제스처 6가지를 카메라로 보여 주며 샘플을 모아
# 모델을 학습하고 파일로 저장하는 것까지가 목표다.
#
# 한 번 학습해 두면 다음 실행부터는 카메라로 다시 가르치지 않아도 된다.
# 블록으로도 깔끔히 펼쳐지도록 try/except·컴프리헨션·데코레이터는 쓰지 않는다.
import tm
import os
import cv2

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


def main():
    카메라 = cv2.VideoCapture(0)
    모델 = get_gesture_model(카메라)
    print('배운 제스처:', 모델.labels)

    # 방금 배운 것이 맞는지 사진 한 장으로 확인해 본다
    찍힘, 사진 = 카메라.read()
    이름표, 확신 = 모델.predict(사진)
    print('지금 제스처:', 이름표, 확신)


if __name__ == '__main__':
    main()

# [H3-②] 고르기 — 사진 한 장을 보고 갈 방향을 골라 한 번 움직인다
#
# ①배우기 를 그대로 담고 있고, 뒤에 '방향 → 주행 동작 매핑'이 붙었다.
# 이 파일 하나만 열어도 돌아간다.
#
# 새로 배우는 것: drive — 예측한 방향을 차의 동작으로 옮겨 주는 함수.
# 아직 계속 달리지는 않는다(그건 ③달리기). 여기서는 한 번만 움직이고 멈춘다.
# 블록으로도 깔끔히 펼쳐지도록 try/except·컴프리헨션·데코레이터는 쓰지 않는다.
import tm
import os
import cv2
import dobotkit

방향들 = ['왼쪽', '직진', '오른쪽']

모델파일 = 'drive_model.npz'
한방향당샘플수 = 30


def collect_and_train(카메라):
    """방향별로 길 사진을 모아 주행 모델을 학습한다."""
    모델 = tm.Model(방향들)
    for 이름 in 방향들:
        print('"' + 이름 + '" 상황의 길을 보여주세요...')
        for 번 in range(한방향당샘플수):
            찍힘, 사진 = 카메라.read()
            if 찍힘:
                모델.add_example(사진, 이름)
    모델.train()
    return 모델


def get_drive_model(카메라):
    """저장된 모델이 있으면 불러오고, 없으면 새로 학습한 뒤 저장한다."""
    if os.path.exists(모델파일):
        print('저장된 모델을 불러왔습니다:', 모델파일)
        return tm.load_model(모델파일)
    모델 = collect_and_train(카메라)
    모델.save(모델파일)
    print('학습한 모델을 저장했습니다:', 모델파일)
    return 모델


def drive(차, 이름표):
    """예측한 방향으로 주행한다."""
    if 이름표 == '왼쪽':
        차.move(30, 0, -20)
    elif 이름표 == '오른쪽':
        차.move(30, 0, 20)
    else:
        차.forward(30)


def main():
    카메라 = cv2.VideoCapture(0)
    모델 = get_drive_model(카메라)

    차 = dobotkit.MagicianGO.open('COM5')

    # 사진 한 장만 보고 그 방향으로 한 번 움직여 본다
    찍힘, 사진 = 카메라.read()
    이름표, 확신 = 모델.predict(사진)
    print('방향:', 이름표, round(확신, 2))
    drive(차, 이름표)

    # 주행로봇에는 펌프(바람)가 없다 — 대신 반드시 멈춰 세우고 끝낸다
    차.stop()


if __name__ == '__main__':
    main()

# [H3-①] 배우기 — 길 사진을 방향별로 모아 학습한다 (주행로봇 없음)
#
# 고등 3차시를 세 단계로 나눈 첫 번째 파일이다(배우기 → 고르기 → 달리기).
# 이 단계는 주행로봇을 쓰지 않는다. 왼쪽·직진·오른쪽 세 상황의 길 사진을 모아
# 모델을 학습하고 파일로 저장하는 것까지가 목표다.
#
# 한 번 학습해 두면 다음 실행부터는 길 사진을 다시 모으지 않아도 된다.
# 블록으로도 깔끔히 펼쳐지도록 try/except·컴프리헨션·데코레이터는 쓰지 않는다.
import tm
import os
import cv2

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


def main():
    카메라 = cv2.VideoCapture(0)
    모델 = get_drive_model(카메라)
    print('배운 방향:', 모델.labels)


if __name__ == '__main__':
    main()

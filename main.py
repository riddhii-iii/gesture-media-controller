import cv2
import mediapipe as mp
import time
import math
import numpy as np
import pyautogui
from ctypes import cast, POINTER, windll
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

try:
    import screen_brightness_control as sbc
except ImportError:
    sbc = None

#  Setup
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(
    static_image_mode=False,
    max_num_hands=1,
    model_complexity=0,
    min_detection_confidence=0.7,
    min_tracking_confidence=0.7
)
mp_draw = mp.solutions.drawing_utils

cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
cap.set(cv2.CAP_PROP_FPS, 30)

devices = AudioUtilities.GetSpeakers()
interface = devices.Activate(
    IAudioEndpointVolume._iid_,
    CLSCTX_ALL,
    None
)
volume = cast(interface, POINTER(IAudioEndpointVolume))

#  Variables 
pTime = 0
smoothVol = 0
volBar = 400
volPer = 0
smoothBrightness = 50
brightBar = 400
brightPer = 50
last_volume_set = 0
last_brightness_set = 0

mute = False
mute_start_time = None
last_play_pause = 0
screenshot_start_time = None
screenshot_message = ""
screenshot_message_until = 0
last_screenshot_time = 0
current_gesture = None
gesture_start_time = 0

if sbc is not None:
    try:
        smoothBrightness = sbc.get_brightness(display=0)[0]
        brightPer = smoothBrightness
        brightBar = np.interp(smoothBrightness, [0, 100], [400, 150])
    except Exception:
        sbc = None

# Finger Detection 
def fingers_up(lm_list):
    fingers = []

    # Thumb
    fingers.append(1 if lm_list[4][1] > lm_list[3][1] else 0)

    # Other fingers
    tips = [8, 12, 16, 20]
    for tip in tips:
        fingers.append(1 if lm_list[tip][2] < lm_list[tip - 2][2] else 0)

    return fingers


def gesture_match(fingers, states):
    for finger_state, expected in zip(fingers, states):
        if expected == -1:
            continue
        if finger_state != expected:
            return False
    return True


def press_media_play_pause():
    VK_MEDIA_PLAY_PAUSE = 0xB3
    KEYEVENTF_KEYUP = 0x0002
    windll.user32.keybd_event(VK_MEDIA_PLAY_PAUSE, 0, 0, 0)
    windll.user32.keybd_event(VK_MEDIA_PLAY_PAUSE, 0, KEYEVENTF_KEYUP, 0)


#  Main Loop
while True:
    now = time.time()
    success, img = cap.read()
    if not success:
        continue

    img = cv2.flip(img, 1)
    imgRGB = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    results = hands.process(imgRGB)

    lm_list = []

    if results.multi_hand_landmarks:
        handLms = results.multi_hand_landmarks[0]
        h, w, _ = img.shape

        for id, lm in enumerate(handLms.landmark):
            cx, cy = int(lm.x * w), int(lm.y * h)
            lm_list.append([id, cx, cy])

        mp_draw.draw_landmarks(img, handLms, mp_hands.HAND_CONNECTIONS)

    if len(lm_list) != 0:

        fingers = fingers_up(lm_list)
        candidate_gesture = None

        if gesture_match(fingers, [-1, 1, 0, 0, 0]):
            candidate_gesture = "volume"
        elif gesture_match(fingers, [-1, 0, 0, 0, 1]):
            candidate_gesture = "brightness"
        elif gesture_match(fingers, [-1, 1, 1, 0, 0]):
            candidate_gesture = "play_pause"
        elif gesture_match(fingers, [0, 1, 1, 1, 0]):
            candidate_gesture = "screenshot"

        if candidate_gesture != current_gesture:
            current_gesture = candidate_gesture
            gesture_start_time = now

        gesture_hold_time = now - gesture_start_time if current_gesture else 0

        #  Volume Control (Thumb + Index)
        x1, y1 = lm_list[4][1], lm_list[4][2]
        x2, y2 = lm_list[8][1], lm_list[8][2]

        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2

        length = math.hypot(x2 - x1, y2 - y1)
        vol_length = max(50, min(270, length))

        if current_gesture == "volume" and gesture_hold_time > 0.15:
            # Smooth volume
            volScalar = np.interp(vol_length, [50, 270], [0.0, 1.0])
            smoothVol = smoothVol + (volScalar - smoothVol) * 0.2
            if now - last_volume_set > 0.05:
                volume.SetMasterVolumeLevelScalar(smoothVol, None)
                last_volume_set = now

            volBar = np.interp(vol_length, [50, 270], [400, 150])
            volPer = np.interp(vol_length, [50, 270], [0, 100])

            # Drawing
            cv2.circle(img, (x1, y1), 8, (255, 0, 255), cv2.FILLED)
            cv2.circle(img, (x2, y2), 8, (255, 0, 255), cv2.FILLED)
            cv2.line(img, (x1, y1), (x2, y2), (255, 0, 255), 2)
            cv2.circle(img, (cx, cy), 8, (255, 0, 255), cv2.FILLED)

        #  Mute Gesture (Hold pinch) 
        if current_gesture == "volume" and gesture_hold_time > 0.15 and length < 35:
            if mute_start_time is None:
                mute_start_time = now
            elif now - mute_start_time > 1:
                mute = not mute
                volume.SetMute(mute, None)
                mute_start_time = None
        else:
            mute_start_time = None

        #  Play / Pause (Index + Middle)
        if current_gesture == "play_pause" and gesture_hold_time > 0.25:
            if now - last_play_pause > 1.2:
                press_media_play_pause()
                last_play_pause = now

        #  Brightness Control (Thumb + Pinky)
        x3, y3 = lm_list[20][1], lm_list[20][2]
        bright_length = math.hypot(x3 - x1, y3 - y1)
        bright_length = max(50, min(270, bright_length))
        bright_cx, bright_cy = (x1 + x3) // 2, (y1 + y3) // 2

        if current_gesture == "brightness" and gesture_hold_time > 0.15:
            target_brightness = np.interp(bright_length, [50, 270], [0, 100])
            smoothBrightness = smoothBrightness + (target_brightness - smoothBrightness) * 0.2
            brightBar = np.interp(smoothBrightness, [0, 100], [400, 150])
            brightPer = smoothBrightness

            if sbc is not None and now - last_brightness_set > 0.1:
                try:
                    sbc.set_brightness(int(smoothBrightness))
                    last_brightness_set = now
                except Exception:
                    sbc = None

            cv2.circle(img, (x1, y1), 8, (0, 255, 255), cv2.FILLED)
            cv2.circle(img, (x3, y3), 8, (0, 255, 255), cv2.FILLED)
            cv2.line(img, (x1, y1), (x3, y3), (0, 255, 255), 2)
            cv2.circle(img, (bright_cx, bright_cy), 8, (0, 255, 255), cv2.FILLED)

        #  Screenshot Gesture (Open palm hold)
        if current_gesture == "screenshot" and gesture_hold_time > 0.8 and now - last_screenshot_time > 3:
            if screenshot_start_time is None:
                screenshot_start_time = now
            elif now - screenshot_start_time > 1.2:
                screenshot_name = f"screenshot_{int(time.time())}.png"
                pyautogui.screenshot(screenshot_name)
                screenshot_message = f"Saved: {screenshot_name}"
                screenshot_message_until = now + 2
                last_screenshot_time = now
                screenshot_start_time = None
        else:
            screenshot_start_time = None

    #  UI 
    cv2.rectangle(img, (50, 150), (85, 400), (255, 0, 0), 2)
    cv2.rectangle(img, (50, int(volBar)), (85, 400), (255, 0, 0), cv2.FILLED)
    cv2.putText(img, f'{int(volPer)}%', (40, 430),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 0), 2)
    cv2.putText(img, "VOL", (45, 140),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)

    cv2.rectangle(img, (550, 150), (585, 400), (0, 255, 255), 2)
    cv2.rectangle(img, (550, int(brightBar)), (585, 400), (0, 255, 255), cv2.FILLED)
    cv2.putText(img, f'{int(brightPer)}%', (535, 430),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
    cv2.putText(img, "BRT", (545, 140),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

    if mute:
        cv2.putText(img, "MUTED", (200, 70),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 3)

    if sbc is None:
        cv2.putText(img, "Brightness control unavailable", (150, 460),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

    if screenshot_message and time.time() < screenshot_message_until:
        cv2.putText(img, screenshot_message, (150, 100),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

    if current_gesture:
        cv2.putText(img, f"Gesture: {current_gesture}", (150, 130),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

    # FPS
    cTime = time.time()
    fps = 1 / (cTime - pTime) if cTime != pTime else 0
    pTime = cTime

    cv2.putText(img, f'FPS: {int(fps)}', (20, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

    cv2.putText(img, "Gesture Media Controller", (350, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)

    cv2.imshow("Controller", img)

    if cv2.waitKey(1) & 0xFF == 27:
        break

cap.release()
cv2.destroyAllWindows()

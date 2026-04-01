# Gesture Media Controller 

Control your system using hand gestures in real-time.

## Features
- Volume control (thumb + index)
- Brightness control (thumb + pinky)
- Play/Pause gesture
- Screenshot capture gesture
- Smooth transitions and gesture hold detection

## Tech Stack
- OpenCV
- MediaPipe
- Pycaw
- PyAutoGUI
- screen-brightness-control

## How it works
Hand landmarks are detected using MediaPipe.  
Different finger combinations trigger different system actions.

## Setup

bash
pip install -r requirements.txt
python main.py
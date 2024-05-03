import sys
import pyautogui
import sqlalchemy
import threading
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, DateTime, create_engine, MetaData, Table, asc
from sqlalchemy.orm import sessionmaker
import time
import json
from pynput import mouse, keyboard
from PIL import Image, ImageDraw
import cv2
import os

print("Click 'ESC' to end the recording.")

recording = []
count = 0


Base = declarative_base()
is_abort = False


class Event(Base):
    __tablename__ = 'events'
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=sqlalchemy.func.now())
    json_data_str = Column(String)


def draw_pointer(source_img_path, x, y, button, key, action):
    with Image.open(source_img_path) as img:
        draw = ImageDraw.Draw(img)
        rect_height = 20
        rect_width = 600
        color = 'orange'
        if x > 0 and y > 0:
            if str(button) == 'Button.right':
                color = 'blue'
            elif str(button) == 'Button.left':
                color = 'green'
            pointer_size = 24
            x0 = x - pointer_size // 2
            y0 = y - pointer_size // 2
            x1 = x0 + pointer_size
            y1 = y0 + pointer_size
            draw.ellipse([(x0, y0), (x1, y1)], fill=color)

        rect_x0 = 0
        rect_y0 = 0
        rect_x1 = rect_x0 + rect_width
        rect_y1 = rect_y0 + rect_height
        draw.rectangle([(rect_x0, rect_y0), (rect_x1, rect_y1)], fill="#666600")

        text = f"x={x}, y={y}, key={key}, action={action}"
        text_color = "white"
        draw.text((5, 5), text, fill=text_color)

        img.save(source_img_path)


def create_db_session(engine):
    meta = MetaData()
    events_table = Table('events', meta, Column('id', Integer, primary_key=True, autoincrement=True),
                         Column('timestamp', DateTime, default=sqlalchemy.func.now()), Column('json_data_str', String))
    meta.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def save_event(session, data):
    if 'key' in data['action']:
        action = 'type'
    elif 'button' in data['action']:
        action = 'click'
    else:
        action = 'move'

    screen_shot = f'c:/windows/temp/{action}_{(time.time())}.png'
    data['screen_shot'] = screen_shot
    json_data = json.dumps(data)
    event = Event(json_data_str=json_data)
    session.add(event)
    session.commit()

    t = threading.Thread(target=trigger_screenshot, args=(str(screen_shot),))
    t.start()


def on_press(key):
    global is_abort
    try:
        json_object = {
            'action': 'pressed_key',
            'key': key.char,
            '_time': time.time(),
        }
        if key == keyboard.Key.esc:
            print("Keyboard recording ended.")
            is_abort = True
            return False
    except AttributeError:
        if key == keyboard.Key.esc:
            print("Recording ended.")
            is_abort = True
            return False

        json_object = {
            'action': 'pressed_key',
            'key': str(key),
            '_time': time.time(),
        }

    save_event(global_session, json_object)


def on_release(key):
    try:
        json_object = {
            'action': 'released_key',
            'key': key.char,
            '_time': time.time(),
            'screen_shot': ''
        }
    except AttributeError:
        json_object = {
            'action': 'released_key',
            'key': str(key),
            '_time': time.time(),
        }
    save_event(global_session, json_object)


def on_move(x, y):
    if len(recording) >= 1:
        if (recording[-1]['action'] == "pressed" and \
            recording[-1]['button'] == 'Button.left') or \
                (recording[-1]['action'] == "moved" and \
                 time.time() - recording[-1]['_time'] > 0.02):
            json_object = {
                'action': 'moved',
                'x': x,
                'y': y,
                '_time': time.time(),
            }

            save_event(global_session, json_object)

    if is_abort: return False


def trigger_screenshot(filename):
    screenshot = pyautogui.screenshot()
    screenshot.save(filename)


def on_click(x, y, button, pressed):
    screen_shot = ''
    if pressed:
        json_object = {
            'action': 'button clicked' if pressed else 'button unclicked',
            'button': str(button),
            'x': x,
            'y': y,
            '_time': time.time(),
        }

        save_event(global_session, json_object)

    if is_abort: return False


def on_scroll(x, y, dx, dy):
    json_object = {
        'action': 'scroll',
        'vertical_direction': int(dy),
        'horizontal_direction': int(dx),
        'x': x,
        'y': y,
        '_time': time.time(),
    }

    if is_abort: return False


def start_recording(session):
    global global_session
    global_session = session
    keyboard_listener = keyboard.Listener(
        on_press=on_press,
        on_release=on_release)

    mouse_listener = mouse.Listener(
        on_click=on_click,
        on_scroll=on_scroll,
        on_move=on_move)

    keyboard_listener.start()
    mouse_listener.start()
    keyboard_listener.join()
    mouse_listener.join()


def create_video(screenshots, output_filename='c://windows/temp/output_video.mp4', fps=30, frame_duration=1):
    try:
        first_image = cv2.imread(screenshots[0])
        if first_image is None:
            print("Error: The first file cannot be loaded..")
            return

        height, width, _ = first_image.shape
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_filename, fourcc, fps, (width, height))

        for screenshot in screenshots:

            img = cv2.imread(screenshot)
            if img is None:
                print(f"Error: {screenshot} cannot be loaded, ignoring it.")
                continue

            for _ in range(fps * frame_duration):
                out.write(img)

        out.release()

        print(f"Video generated: {output_filename}")

    except Exception as e:
        print("Error creating video:", e)


def compile_data(engine):
    try:
        session = create_db_session(engine)
        events = session.query(Event).order_by(asc(Event.timestamp)).all()
        screenshots = []

        for event in events:
            data = json.loads(event.json_data_str)
            if 'screen_shot' in data and data['screen_shot'] != '' and os.path.exists(data['screen_shot']):
                print('processing: ', data['screen_shot'])
                key = ''
                button = ''
                action = ''
                x = 0
                y = 0
                if 'key' in data['action']:
                    key = data['key']
                    action = 'type'
                elif 'button' in data['action']:
                    button = data['button']
                    x = data['x']
                    y = data['y']
                    action = 'click'
                else:
                    x = data['x']
                    y = data['y']
                    action = 'move'
                draw_pointer(data['screen_shot'], x, y, button, key, action)
                screenshots.append(data['screen_shot'])

        print("Creating video...")
        create_video(screenshots)
        for screenshot in screenshots:
            os.remove(screenshot)
            print(screenshot, 'deleted')


    except Exception as e:
        print("Error compiling data:", e)
    finally:
        if session:
            session.close()


def main():
    if len(sys.argv) != 2:
        print("Use: python record.py [record|compile]")
        return

    db_path = "c://windows/temp/scicrop-user-stats.db"
    engine = create_engine(f'sqlite:///{db_path}', echo=True)
    if sys.argv[1] == "record":

        if os.path.exists(db_path):
            os.remove(db_path)
            print(f"File {db_path} deleted.")
        else:
            print(f"File {db_path} not found.")
        session = create_db_session(engine)
        start_recording(session)
    elif sys.argv[1] == "compile":
        compile_data(engine)
    else:
        print("Command not recognized. Use 'record' or 'compile'.")


if __name__ == "__main__":
    main()

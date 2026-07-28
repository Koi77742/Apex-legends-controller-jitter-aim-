import sys
import os
import time
import re
import math
import ctypes
import random
from pathlib import Path

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
os.environ.setdefault("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1")
try:
    import pygame
except ImportError:
    print("Library missing. Run: pip install pygame")
    sys.exit(1)

try:
    from pygame._sdl2 import controller as sdl_controller
except ImportError:
    sdl_controller = None

try:
    import yaml
except ImportError:
    print("CRITICAL ERROR: YAML library missing. Run: pip install pyyaml")
    sys.exit(1)

try:
    from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                                   QLabel, QSlider, QFrame, QPushButton, QComboBox,
                                   QGroupBox, QFormLayout, QColorDialog, QInputDialog,
                                   QMessageBox)
    from PySide6.QtCore import Qt, QThread, QTimer
    from PySide6.QtGui import QColor
except ImportError:
    print("CRITICAL ERROR: PySide6 missing. Run: pip install PySide6")
    sys.exit(1)

APP_DIR = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent
)
APP_EXECUTABLE_NAME = (
    Path(sys.executable).stem
    if getattr(sys, "frozen", False)
    else Path(sys.argv[0]).stem
) or "skp"
CONFIG_FILE = APP_DIR / "config.yaml"
MOUSE_MOVE_RELATIVE = 0x0001
PROFILE_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9 _-]{0,63}")


def get_profile_path(name):
    clean_name = str(name).strip()
    if not PROFILE_NAME_PATTERN.fullmatch(clean_name):
        return None
    return APP_DIR / f"{clean_name}.yaml"


SDL_AXIS_RIGHT_X = 2
SDL_AXIS_RIGHT_Y = 3
SDL_AXIS_TRIGGER_LEFT = 4
SDL_AXIS_TRIGGER_RIGHT = 5

SDL_BUTTON_A = 0
SDL_BUTTON_B = 1
SDL_BUTTON_X = 2
SDL_BUTTON_Y = 3
SDL_BUTTON_BACK = 4
SDL_BUTTON_START = 6
SDL_BUTTON_LEFT_STICK = 7
SDL_BUTTON_RIGHT_STICK = 8
SDL_BUTTON_LEFT_SHOULDER = 9
SDL_BUTTON_RIGHT_SHOULDER = 10

CONTROLLER_BUTTONS = {
    "None": -1,
    "A / Cross": SDL_BUTTON_A,
    "B / Circle": SDL_BUTTON_B,
    "X / Square": SDL_BUTTON_X,
    "Y / Triangle": SDL_BUTTON_Y,
    "Left Bumper (LB / L1)": SDL_BUTTON_LEFT_SHOULDER,
    "Right Bumper (RB / R1)": SDL_BUTTON_RIGHT_SHOULDER,
    "View (Back / Share)": SDL_BUTTON_BACK,
    "Menu (Start / Options)": SDL_BUTTON_START,
    "Left Stick Click (L3)": SDL_BUTTON_LEFT_STICK,
    "Right Stick Click (R3)": SDL_BUTTON_RIGHT_STICK,
}

LEGACY_BUTTON_NAMES = {
    "A": "A / Cross",
    "B": "B / Circle",
    "X": "X / Square",
    "Y": "Y / Triangle",
    "Left Bumper (LB)": "Left Bumper (LB / L1)",
    "Right Bumper (RB)": "Right Bumper (RB / R1)",
    "View (Back)": "View (Back / Share)",
    "Menu (Start)": "Menu (Start / Options)",
}

LEGACY_CONTROL_NAMES = {
    "Left Trigger (LT)": "Left Trigger (LT / L2)",
    "Right Trigger (RT)": "Right Trigger (RT / R2)",
    "Left Bumper (LB)": "Left Bumper (LB / L1)",
    "Right Bumper (RB)": "Right Bumper (RB / R1)",
}


def canonical_button_name(name):
    clean_name = str(name)
    return LEGACY_BUTTON_NAMES.get(clean_name, clean_name)


def canonical_control_name(name):
    clean_name = str(name)
    return LEGACY_CONTROL_NAMES.get(clean_name, clean_name)


class GamepadDevice:
    """Stable Xbox/PlayStation input wrapper with raw-joystick fallback."""

    XBOX_RAW_BUTTONS = {
        SDL_BUTTON_A: 0,
        SDL_BUTTON_B: 1,
        SDL_BUTTON_X: 2,
        SDL_BUTTON_Y: 3,
        SDL_BUTTON_BACK: 6,
        SDL_BUTTON_START: 7,
        SDL_BUTTON_LEFT_STICK: 8,
        SDL_BUTTON_RIGHT_STICK: 9,
        SDL_BUTTON_LEFT_SHOULDER: 4,
        SDL_BUTTON_RIGHT_SHOULDER: 5,
    }
    PLAYSTATION_RAW_BUTTONS = {
        SDL_BUTTON_A: 0,
        SDL_BUTTON_B: 1,
        SDL_BUTTON_X: 2,
        SDL_BUTTON_Y: 3,
        SDL_BUTTON_BACK: 8,
        SDL_BUTTON_START: 9,
        SDL_BUTTON_LEFT_STICK: 10,
        SDL_BUTTON_RIGHT_STICK: 11,
        SDL_BUTTON_LEFT_SHOULDER: 4,
        SDL_BUTTON_RIGHT_SHOULDER: 5,
    }

    def __init__(self, device_index):
        self.controller = None
        self.joystick = None
        self.standardized = False

        if sdl_controller and sdl_controller.is_controller(device_index):
            self.controller = sdl_controller.Controller(device_index)
            self.joystick = self.controller.as_joystick()
            self.standardized = True
        else:
            self.joystick = pygame.joystick.Joystick(device_index)
            self.joystick.init()

        self.instance_id = self.joystick.get_instance_id()
        self.name = self.joystick.get_name()
        self.guid = self.joystick.get_guid()
        lower_name = self.name.lower()
        self.raw_button_map = (
            self.PLAYSTATION_RAW_BUTTONS
            if any(
                marker in lower_name
                for marker in (
                    "playstation",
                    "dualshock",
                    "dualsense",
                    "wireless controller",
                    "ps4",
                    "ps5",
                )
            )
            else self.XBOX_RAW_BUTTONS
        )

    @staticmethod
    def _clamp(value, minimum, maximum):
        return max(minimum, min(float(value), maximum))

    def is_attached(self):
        if self.standardized:
            return bool(self.controller.attached())
        return bool(self.joystick.get_init())

    def get_button(self, button_code):
        if button_code < 0:
            return False
        if self.standardized:
            return bool(self.controller.get_button(button_code))

        raw_button = self.raw_button_map.get(button_code, button_code)
        if raw_button >= self.joystick.get_numbuttons():
            return False
        return bool(self.joystick.get_button(raw_button))

    def get_trigger(self, left):
        if self.standardized:
            axis = SDL_AXIS_TRIGGER_LEFT if left else SDL_AXIS_TRIGGER_RIGHT
            return self._clamp(self.controller.get_axis(axis) / 32768.0, 0.0, 1.0)

        num_axes = self.joystick.get_numaxes()
        axis = 4 if left else 5
        if num_axes < 6:
            axis = 2 if left else 3
        if axis >= num_axes:
            return 0.0
        raw_value = self.joystick.get_axis(axis)
        return self._clamp((raw_value + 1.0) / 2.0, 0.0, 1.0)

    def get_right_stick(self):
        if self.standardized:
            rx = self.controller.get_axis(SDL_AXIS_RIGHT_X) / 32767.0
            ry = self.controller.get_axis(SDL_AXIS_RIGHT_Y) / 32767.0
        elif self.joystick.get_numaxes() >= 4:
            rx = self.joystick.get_axis(2)
            ry = self.joystick.get_axis(3)
        else:
            return 0.0, 0.0

        return self._clamp(rx, -1.0, 1.0), self._clamp(ry, -1.0, 1.0)

    def get_control_value(self, control_name):
        if "Left Trigger" in control_name:
            return self.get_trigger(left=True)
        if "Right Trigger" in control_name:
            return self.get_trigger(left=False)
        if "Left Bumper" in control_name:
            return 1.0 if self.get_button(SDL_BUTTON_LEFT_SHOULDER) else 0.0
        if "Right Bumper" in control_name:
            return 1.0 if self.get_button(SDL_BUTTON_RIGHT_SHOULDER) else 0.0
        return 0.0

    def close(self):
        try:
            if self.controller is not None:
                self.controller.quit()
            elif self.joystick is not None:
                self.joystick.quit()
        except pygame.error:
            pass


def open_first_gamepad(preferred_guid=""):
    if sdl_controller and not sdl_controller.get_init():
        sdl_controller.init()

    preferred_guid = str(preferred_guid).strip().casefold()
    fallback_device = None
    for device_index in range(pygame.joystick.get_count()):
        try:
            device = GamepadDevice(device_index)
        except (pygame.error, OSError):
            continue

        if preferred_guid and device.guid.casefold() == preferred_guid:
            if fallback_device is not None:
                fallback_device.close()
            return device

        if fallback_device is None:
            fallback_device = device
        else:
            device.close()

    return fallback_device

def get_default_config():
    return {
        "AccentColor": "#ff007f", "AimAssist": 100, "AimControl": "Left Trigger (LT / L2)", "Down": 30,
        "Dz": 3, "Left": 25, "OutputMode": "Standard Windows (1PC)",
        "Right": 25, "ShootControl": "Right Trigger (RT / R2)", "Speed": 5, "Toggle1": "None",
        "Toggle2": "None", "Up": 25, "script_enabled": True, "StickDeadzone": 4,
        "StickSensitivity": 195, "ActivationDelay": 0
    }

def create_default_config():
    default_config = get_default_config()
    try:
        with open(CONFIG_FILE, "w") as f:
            yaml.safe_dump(default_config, f, default_flow_style=False)
    except Exception: pass
    return default_config

def load_initial_config():
    if not os.path.exists(CONFIG_FILE): return create_default_config()
    try:
        with open(CONFIG_FILE, "r") as f:
            data = yaml.safe_load(f)
            if data:
                defaults = get_default_config()
                for k, v in defaults.items():
                    if k not in data: data[k] = v
                return data
    except Exception: pass
    return create_default_config()


def calculate_aim_boost(rx, ry, deadzone, sensitivity, boost_percent):
    deadzone = max(0.0, min(float(deadzone), 0.95))
    sensitivity = max(0.0, float(sensitivity))
    raw_magnitude = math.hypot(rx, ry)

    if raw_magnitude <= deadzone or raw_magnitude == 0.0:
        return 0.0, 0.0

    direction_x = rx / raw_magnitude
    direction_y = ry / raw_magnitude
    normalized_magnitude = min(
        1.0, (raw_magnitude - deadzone) / (1.0 - deadzone)
    )

    assist_strength = max(0.0, min(float(boost_percent), 100.0)) / 100.0

    curve_exponent = 1.0 - (0.55 * assist_strength)
    curved_magnitude = normalized_magnitude ** curve_exponent
    centre_gain = 1.0 + (
        1.25 * assist_strength * (1.0 - normalized_magnitude)
    )
    assisted_magnitude = min(1.0, curved_magnitude * centre_gain)

    return (
        direction_x * assisted_magnitude * sensitivity,
        direction_y * assisted_magnitude * sensitivity,
    )


class InputWorker(QThread):
    def __init__(self, config_ref):
        super().__init__()
        self.config = config_ref
        self.running = True

    def run(self):
        winmm = ctypes.WinDLL('winmm')
        winmm.timeBeginPeriod(1)
        pygame.init()
        pygame.joystick.init()
        self.worker = None
        try:
            self.process_loop()
        finally:
            winmm.timeEndPeriod(1)
            pygame.quit()

    def process_loop(self):
        sequence_index = 0
        cur_x, cur_y = 0, 0
        toggle_pressed_last_frame = False
        trigger_active_last = False
        trigger_start_time = 0.0
        next_reconnect_attempt = 0.0

        active_preference = str(
            self.config.get("ControllerGuid", "")
        ).strip()
        controller = open_first_gamepad(active_preference)
        removed_event_types = {pygame.JOYDEVICEREMOVED}
        if hasattr(pygame, "CONTROLLERDEVICEREMOVED"):
            removed_event_types.add(pygame.CONTROLLERDEVICEREMOVED)
        added_event_types = {pygame.JOYDEVICEADDED}
        if hasattr(pygame, "CONTROLLERDEVICEADDED"):
            added_event_types.add(pygame.CONTROLLERDEVICEADDED)

        while self.running:
            try:
                for event in pygame.event.get():
                    if event.type in added_event_types:
                        if (
                            controller is not None
                            and active_preference
                            and controller.guid.casefold()
                            != active_preference.casefold()
                        ):
                            controller.close()
                            controller = None
                        next_reconnect_attempt = 0.0
                    elif (
                        controller is not None
                        and event.type in removed_event_types
                        and getattr(event, "instance_id", None)
                        == controller.instance_id
                    ):
                        controller.close()
                        controller = None
                        next_reconnect_attempt = time.monotonic() + 0.25

                configured_preference = str(
                    self.config.get("ControllerGuid", "")
                ).strip()
                if configured_preference != active_preference:
                    active_preference = configured_preference
                    if controller is not None:
                        controller.close()
                        controller = None
                    next_reconnect_attempt = 0.0

                if controller is not None and not controller.is_attached():
                    controller.close()
                    controller = None
                    next_reconnect_attempt = time.monotonic() + 0.25

                if (
                    controller is None
                    and time.monotonic() >= next_reconnect_attempt
                ):
                    controller = open_first_gamepad(active_preference)
                    next_reconnect_attempt = time.monotonic() + 0.5

                currently_pressing_toggle = False
                if controller:
                    t1_name = canonical_button_name(
                        self.config.get("Toggle1", "None")
                    )
                    t2_name = canonical_button_name(
                        self.config.get("Toggle2", "None")
                    )
                    t1_id = CONTROLLER_BUTTONS.get(t1_name, -1)
                    t2_id = CONTROLLER_BUTTONS.get(t2_name, -1)

                    t1_active = (t1_id == -1) or controller.get_button(t1_id)
                    t2_active = (t2_id == -1) or controller.get_button(t2_id)

                    if t1_id != -1 or t2_id != -1:
                        currently_pressing_toggle = t1_active and t2_active

                if currently_pressing_toggle and not toggle_pressed_last_frame:
                    self.config["script_enabled"] = not self.config.get(
                        "script_enabled", True
                    )

                toggle_pressed_last_frame = currently_pressing_toggle

                controller_active = False

                if controller:
                    aim_setting = canonical_control_name(
                        self.config.get("AimControl", "Left Trigger (LT / L2)")
                    )
                    shoot_setting = canonical_control_name(
                        self.config.get("ShootControl", "Right Trigger (RT / R2)")
                    )
                    aim_value = controller.get_control_value(aim_setting)
                    shoot_value = controller.get_control_value(shoot_setting)
                    threshold = max(
                        0.0, min(self.config.get("Dz", 3) / 100.0, 1.0)
                    )

                    if aim_value > threshold and shoot_value > threshold:
                        controller_active = True

                is_input_active = (
                    self.config.get("script_enabled", True) and controller_active
                )

                if is_input_active:
                    if not trigger_active_last:
                        trigger_start_time = time.perf_counter()
                        trigger_active_last = True

                    delay_ms = self.config.get("ActivationDelay", 0)
                    if (
                        time.perf_counter() - trigger_start_time
                    ) >= (delay_ms / 1000.0):
                        r = self.config.get("Right", 25)
                        l = self.config.get("Left", 25)
                        u = self.config.get("Up", 25)
                        d = self.config.get("Down", 30)
                        targets = [
                            (r, -u),
                            (-l, d),
                            (r, 0),
                            (-l, 0),
                            (0, -u),
                            (0, d),
                        ]

                        target_x, target_y = targets[sequence_index]

                        manual_x, manual_y = 0.0, 0.0
                        if controller:
                            rx, ry = controller.get_right_stick()
                            dzone = (
                                self.config.get("StickDeadzone", 4) / 100.0
                            )
                            sens = (
                                self.config.get("StickSensitivity", 195) / 100.0
                            )
                            boost = self.config.get("AimAssist", 100)
                            manual_x, manual_y = calculate_aim_boost(
                                rx, ry, dzone, sens, boost
                            )

                        step_x = (
                            target_x
                            - cur_x
                            + manual_x
                            + random.gauss(0, 0.2)
                        )
                        step_y = (
                            target_y
                            - cur_y
                            + manual_y
                            + random.gauss(0, 0.2)
                        )

                        try:
                            ctypes.windll.user32.mouse_event(
                                MOUSE_MOVE_RELATIVE,
                                int(step_x),
                                int(step_y),
                                0,
                                0,
                            )
                        except Exception:
                            pass

                        cur_x, cur_y = target_x, target_y
                        sequence_index = (sequence_index + 1) % len(targets)

                        duration_ms = max(1, self.config.get("Speed", 5))
                        start_time = time.perf_counter()
                        target_time = start_time + (duration_ms / 1000.0)
                        if duration_ms > 2:
                            time.sleep((duration_ms - 2) / 1000.0)
                        while time.perf_counter() < target_time:
                            pass
                    else:
                        time.sleep(0.001)
                else:
                    trigger_active_last = False
                    if cur_x != 0 or cur_y != 0:
                        try:
                            ctypes.windll.user32.mouse_event(
                                MOUSE_MOVE_RELATIVE,
                                int(-cur_x),
                                int(-cur_y),
                                0,
                                0,
                            )
                        except Exception:
                            pass
                        cur_x = cur_y = 0
                    time.sleep(0.005)

            except (pygame.error, OSError, IndexError, ValueError):
                if controller is not None:
                    controller.close()
                    controller = None
                toggle_pressed_last_frame = False
                trigger_active_last = False
                next_reconnect_attempt = time.monotonic() + 0.5
                time.sleep(0.05)

        if controller is not None:
            controller.close()
                


class MainPanel(QWidget):
    def __init__(self):
        super().__init__()
        pygame.init()
        pygame.joystick.init()
        self.worker = None
        
        self.config = load_initial_config()
        self.accent_color = self.config.get("AccentColor", "#ff007f")
        self.sliders = {}
        self.value_labels = {}
        
        self.setWindowTitle(APP_EXECUTABLE_NAME)
        self.setFixedSize(590, 950)
        
        self.setStyleSheet(self.get_stylesheet())
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(10)
        
        color_row = QHBoxLayout()
        color_row.addWidget(QLabel("Menu Color:"))
        self.color_btn = QPushButton("🎨 Change Color")
        self.color_btn.clicked.connect(self.change_accent_color)
        color_row.addWidget(self.color_btn)
        color_row.addStretch()
        self.brand_label = QLabel("Vynex")
        self.brand_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.brand_label.setStyleSheet(
            f"color: {self.accent_color}; font-size: 15px; font-weight: bold;"
        )
        color_row.addWidget(self.brand_label)
        main_layout.addLayout(color_row)
        
        profiles = QGroupBox("CONFIGS")
        p_layout = QVBoxLayout(profiles); p_layout.setContentsMargins(10, 20, 10, 10)
        self.profile_combo = QComboBox(); self.load_yaml_profiles(); p_layout.addWidget(self.profile_combo)
        
        index = self.profile_combo.findText("config")
        if index >= 0: self.profile_combo.setCurrentIndex(index)

        btn_row = QHBoxLayout()
        for t, f in [("Load", self.load_config), ("Save", self.save_config), ("New", self.new_config), ("Rename", self.rename_config), ("Delete", self.delete_config)]:
            btn = QPushButton(t); btn.clicked.connect(f); btn_row.addWidget(btn)
        p_layout.addLayout(btn_row); main_layout.addWidget(profiles)
        
        ctrl = QGroupBox("INPUT MANAGEMENT")
        c_layout = QFormLayout(ctrl); c_layout.setContentsMargins(10, 20, 10, 10)
        
        self.controller_combo = QComboBox()
        self.refresh_controllers()
        self.controller_combo.currentIndexChanged.connect(
            self.on_controller_changed
        )
        self.output_mode_combo = QComboBox(); self.output_mode_combo.addItems(["Standard Windows (1PC)"])
        
        h = QHBoxLayout(); refresh_btn = QPushButton("Refresh Devices"); refresh_btn.clicked.connect(self.refresh_controllers)
        h.addWidget(refresh_btn); h.addStretch()
        
        c_layout.addRow("Active Gamepad:", self.controller_combo)
        c_layout.addRow("Output Driver:", self.output_mode_combo)
        c_layout.addRow("Utilities:", h)
        main_layout.addWidget(ctrl)
        
        btns = QGroupBox("MAPPING TRIGGERS"); b_layout = QFormLayout(btns); b_layout.setContentsMargins(10, 20, 10, 10)
        self.aim_combo = QComboBox()
        self.shoot_combo = QComboBox()
        
        b_layout.addRow("Aim Modifier:", self.aim_combo)
        b_layout.addRow("Fire Trigger:", self.shoot_combo)
        main_layout.addWidget(btns)

        tgls = QGroupBox("TOGGLE BUTTONS"); t_layout = QFormLayout(tgls); t_layout.setContentsMargins(10, 20, 10, 10)
        self.toggle1_combo = QComboBox()
        self.toggle2_combo = QComboBox()

        t_layout.addRow("Toggle Button 1:", self.toggle1_combo)
        t_layout.addRow("Toggle Button 2:", self.toggle2_combo)
        main_layout.addWidget(tgls)

        self.output_mode_combo.setCurrentText(self.config.get("OutputMode", "Standard Windows (1PC)"))
        self.update_bind_options(self.output_mode_combo.currentText())
        self.output_mode_combo.currentTextChanged.connect(self.on_output_mode_changed)

        self.aim_combo.currentTextChanged.connect(lambda t: self.config.update({"AimControl": t}))
        self.shoot_combo.currentTextChanged.connect(lambda t: self.config.update({"ShootControl": t}))
        self.toggle1_combo.currentTextChanged.connect(lambda t: self.config.update({"Toggle1": t}))
        self.toggle2_combo.currentTextChanged.connect(lambda t: self.config.update({"Toggle2": t}))
        
        jitter = QGroupBox("VALUE CONFIGURATION")
        j_layout = QVBoxLayout(jitter); j_layout.setContentsMargins(10, 20, 10, 10); j_layout.setSpacing(5)
        
        settings = [
            ("Right", self.config.get("Right", 25), 100, 1),
            ("Left", self.config.get("Left", 25), 100, 1),
            ("Up", self.config.get("Up", 25), 100, 1),
            ("Down", self.config.get("Down", 30), 100, 1),
            ("Speed", self.config.get("Speed", 5), 100, 1),
            ("Dz", self.config.get("Dz", 3), 30, 1),
            ("StickDeadzone", self.config.get("StickDeadzone", 4), 50, 100),
            ("StickSensitivity", self.config.get("StickSensitivity", 195), 500, 100),
            ("AimAssist", self.config.get("AimAssist", 100), 100, 1),
            ("ActivationDelay", self.config.get("ActivationDelay", 0), 1000, 1)
        ]
        for name, default, maxv, div in settings:
            j_layout.addWidget(self.create_slider_row(name, default, maxv, div))
        main_layout.addWidget(jitter)
        
        footer = QLabel("Vynex\nInput Configuration")
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet("color: #444444; font-size: 10px; margin-top: 5px;")
        main_layout.addWidget(footer)
        
        QTimer.singleShot(100, self.start_background_services)

    def start_background_services(self):
        try:
            self.worker = InputWorker(self.config)
            self.worker.start()
        except Exception as e:
            print(f"Failed to start input worker: {e}")

    def on_output_mode_changed(self, text):
        self.config["OutputMode"] = text
        self.update_bind_options(text)

    def update_bind_options(self, mode_str):
        self.aim_combo.blockSignals(True); self.shoot_combo.blockSignals(True)
        self.toggle1_combo.blockSignals(True); self.toggle2_combo.blockSignals(True)
        
        self.aim_combo.clear(); self.shoot_combo.clear()
        self.toggle1_combo.clear(); self.toggle2_combo.clear()
        
        aim_items = [
            "Left Trigger (LT / L2)",
            "Left Bumper (LB / L1)",
            "Right Bumper (RB / R1)",
        ]
        shoot_items = [
            "Right Trigger (RT / R2)",
            "Right Bumper (RB / R1)",
            "Left Bumper (LB / L1)",
        ]
        toggle_items = list(CONTROLLER_BUTTONS.keys())
        default_aim = "Left Trigger (LT / L2)"
        default_shoot = "Right Trigger (RT / R2)"
        default_t1 = "None"
        default_t2 = "None"

        self.aim_combo.addItems(aim_items); self.shoot_combo.addItems(shoot_items)
        self.toggle1_combo.addItems(toggle_items); self.toggle2_combo.addItems(toggle_items)

        cfg_aim = canonical_control_name(
            self.config.get("AimControl", default_aim)
        )
        if cfg_aim not in aim_items: cfg_aim = default_aim
        self.aim_combo.setCurrentText(cfg_aim); self.config["AimControl"] = cfg_aim

        cfg_shoot = canonical_control_name(
            self.config.get("ShootControl", default_shoot)
        )
        if cfg_shoot not in shoot_items: cfg_shoot = default_shoot
        self.shoot_combo.setCurrentText(cfg_shoot); self.config["ShootControl"] = cfg_shoot

        cfg_t1 = canonical_button_name(self.config.get("Toggle1", default_t1))
        if cfg_t1 not in toggle_items: cfg_t1 = default_t1
        self.toggle1_combo.setCurrentText(cfg_t1); self.config["Toggle1"] = cfg_t1

        cfg_t2 = canonical_button_name(self.config.get("Toggle2", default_t2))
        if cfg_t2 not in toggle_items: cfg_t2 = default_t2
        self.toggle2_combo.setCurrentText(cfg_t2); self.config["Toggle2"] = cfg_t2

        self.aim_combo.blockSignals(False); self.shoot_combo.blockSignals(False)
        self.toggle1_combo.blockSignals(False); self.toggle2_combo.blockSignals(False)

    def create_slider_row(self, label, default, max_val, divisor=1):
        frame = QFrame(); layout = QHBoxLayout(frame); layout.setContentsMargins(0, 0, 0, 0)
        name_label = QLabel(label); name_label.setFixedWidth(130); slider = QSlider(Qt.Horizontal)
        slider.setRange(0, max_val); slider.setValue(default)
        
        display_val = f"{default/divisor:.2f}" if divisor > 1 else str(default)
        value_label = QLabel(display_val)
        value_label.setAlignment(Qt.AlignCenter); value_label.setFixedWidth(50)
        value_label.setStyleSheet(f"color: {self.accent_color}; font-weight: bold; font-size: 14px;")
        
        self.sliders[label] = slider; self.value_labels[label] = value_label
        
        def on_change(v):
            self.config.update({label: v})
            if divisor > 1:
                value_label.setText(f"{v/divisor:.2f}")
            else:
                value_label.setText(str(v))
                
        slider.valueChanged.connect(on_change)
        layout.addWidget(name_label); layout.addWidget(slider); layout.addWidget(value_label)
        return frame

    def load_yaml_profiles(self):
        self.profile_combo.clear()
        files = [f.stem for f in APP_DIR.glob("*.yaml") if get_profile_path(f.stem)]
        self.profile_combo.addItems(files if files else ["No Configuration Files"])

    def load_config(self):
        name = self.profile_combo.currentText().strip()
        file_path = get_profile_path(name)
        if not file_path or not file_path.is_file(): return
        try:
            with open(file_path, "r") as f:
                data = yaml.safe_load(f)
                if isinstance(data, dict):
                    self.config.update(data)
                    if "OutputMode" in data: self.output_mode_combo.setCurrentText(data["OutputMode"])
                    if "ControllerGuid" in data: self.refresh_controllers()
                    self.update_bind_options(self.output_mode_combo.currentText())

                    for k, v in data.items():
                        if k in self.sliders:
                            val = int(v)
                            self.sliders[k].setValue(val)
                            if k in self.value_labels:
                                div = 100 if "Stick" in k else 1
                                self.value_labels[k].setText(f"{val/div:.2f}" if div > 1 else str(val))
                    
                    if "AimControl" in data: self.aim_combo.setCurrentText(data["AimControl"])
                    if "ShootControl" in data: self.shoot_combo.setCurrentText(data["ShootControl"])
                    if "Toggle1" in data: self.toggle1_combo.setCurrentText(data["Toggle1"])
                    if "Toggle2" in data: self.toggle2_combo.setCurrentText(data["Toggle2"])
                    if "AccentColor" in data:
                        self.accent_color = data["AccentColor"]
                        self.setStyleSheet(self.get_stylesheet())
                        for sk, slbl in self.value_labels.items():
                            sdiv = 100 if "Stick" in sk else 1
                            slbl.setStyleSheet(f"color: {self.accent_color}; font-weight: bold; font-size: 14px;")
        except Exception: pass

    def save_config(self):
        name = self.profile_combo.currentText().strip()
        file_path = get_profile_path(name)
        if not file_path:
            QMessageBox.warning(self, "Invalid profile", "Use only letters, numbers, spaces, hyphens, and underscores.")
            return
        for key, slider in self.sliders.items(): self.config[key] = slider.value()
        self.config["AimControl"] = self.aim_combo.currentText()
        self.config["ShootControl"] = self.shoot_combo.currentText()
        self.config["Toggle1"] = self.toggle1_combo.currentText()
        self.config["Toggle2"] = self.toggle2_combo.currentText()
        self.config["OutputMode"] = self.output_mode_combo.currentText()
        self.config["AccentColor"] = self.accent_color
        with open(file_path, "w") as f:
            yaml.safe_dump(self.config, f, default_flow_style=False)

    def new_config(self):
        name, ok = QInputDialog.getText(self, "New Profile Block", "Filename string:")
        if ok and name and name.strip():
            name = name.strip()
            file_path = get_profile_path(name)
            if not file_path:
                QMessageBox.warning(self, "Invalid profile", "Use only letters, numbers, spaces, hyphens, and underscores.")
                return
            for key, slider in self.sliders.items(): self.config[key] = slider.value()
            self.config["AimControl"] = self.aim_combo.currentText()
            self.config["ShootControl"] = self.shoot_combo.currentText()
            self.config["Toggle1"] = self.toggle1_combo.currentText()
            self.config["Toggle2"] = self.toggle2_combo.currentText()
            self.config["OutputMode"] = self.output_mode_combo.currentText()
            self.config["AccentColor"] = self.accent_color
            with open(file_path, "w") as f:
                yaml.safe_dump(self.config, f, default_flow_style=False)
            self.load_yaml_profiles(); self.profile_combo.setCurrentText(name)

    def rename_config(self):
        old = self.profile_combo.currentText().strip()
        if not old or "No Configuration" in old: return
        new, ok = QInputDialog.getText(self, "Modify String Designation", "New identifier string:", text=old)
        if ok and new and new.strip() and old != new.strip():
            new = new.strip()
            old_path = get_profile_path(old)
            new_path = get_profile_path(new)
            if not old_path or not new_path:
                QMessageBox.warning(self, "Invalid profile", "Use only letters, numbers, spaces, hyphens, and underscores.")
                return
            if old_path.is_file(): 
                os.rename(old_path, new_path)
                self.load_yaml_profiles()
                self.profile_combo.setCurrentText(new)

    def delete_config(self):
        name = self.profile_combo.currentText().strip()
        file_path = get_profile_path(name)
        if file_path and file_path.is_file(): 
            os.remove(file_path)
            self.load_yaml_profiles()

    def refresh_controllers(self):
        preferred_guid = str(self.config.get("ControllerGuid", "")).strip()
        self.controller_combo.blockSignals(True)
        self.controller_combo.clear()
        for device_index in range(pygame.joystick.get_count()):
            try:
                joystick = pygame.joystick.Joystick(device_index)
                self.controller_combo.addItem(
                    joystick.get_name(), joystick.get_guid()
                )
            except pygame.error:
                continue

        selected_index = (
            self.controller_combo.findData(preferred_guid)
            if preferred_guid
            else -1
        )
        if preferred_guid and selected_index < 0:
            self.controller_combo.addItem(
                "Selected controller (disconnected)", preferred_guid
            )
            selected_index = self.controller_combo.count() - 1

        if self.controller_combo.count() == 0:
            self.controller_combo.addItem("No controller connected", "")
        elif selected_index < 0:
            selected_index = 0

        self.controller_combo.setCurrentIndex(max(0, selected_index))
        self.controller_combo.blockSignals(False)
        self.on_controller_changed(self.controller_combo.currentIndex())

    def on_controller_changed(self, index):
        if index < 0:
            return
        controller_guid = str(self.controller_combo.itemData(index) or "").strip()
        if controller_guid:
            self.config["ControllerGuid"] = controller_guid

    def change_accent_color(self):
        color = QColorDialog.getColor(QColor(self.accent_color), self)
        if color.isValid(): 
            self.accent_color = color.name()
            self.config["AccentColor"] = self.accent_color
            self.setStyleSheet(self.get_stylesheet())
            self.brand_label.setStyleSheet(
                f"color: {self.accent_color}; font-size: 15px; font-weight: bold;"
            )
            for label in self.value_labels.values():
                label.setStyleSheet(f"color: {self.accent_color}; font-weight: bold; font-size: 14px;")

    def get_stylesheet(self):
        return f"QWidget {{ background-color: #08080a; color: #d8d8d8; font-family: 'Segoe UI', sans-serif; }} QGroupBox {{ margin-top: 5px; padding-top: 15px; border: 1px solid #141418; border-radius: 6px; color: {self.accent_color}; font-weight: bold; }} QPushButton {{ background-color: #141418; color: white; border: none; border-radius: 4px; padding: 6px 12px; font-weight: 600; }} QPushButton:hover {{ background-color: {self.accent_color}; }} QComboBox {{ background-color: #141418; color: white; border: 1px solid #1c1c22; border-radius: 4px; padding: 5px; }} QSlider::groove:horizontal {{ height: 6px; background: #141418; border-radius: 3px; }} QSlider::sub-page:horizontal {{ background: {self.accent_color}; border-radius: 3px; }} QSlider::handle:horizontal {{ background: white; width: 14px; height: 14px; margin: -4px 0; border-radius: 7px; }}"

    def closeEvent(self, event):
        if self.worker:
            self.worker.running = False
            self.worker.wait()
        for key, slider in self.sliders.items(): self.config[key] = slider.value()
        self.config["AimControl"] = self.aim_combo.currentText()
        self.config["ShootControl"] = self.shoot_combo.currentText()
        self.config["Toggle1"] = self.toggle1_combo.currentText()
        self.config["Toggle2"] = self.toggle2_combo.currentText()
        self.config["OutputMode"] = self.output_mode_combo.currentText()
        self.config["AccentColor"] = self.accent_color
        
        try:
            with open(CONFIG_FILE, "w") as f:
                yaml.safe_dump(self.config, f, default_flow_style=False)
        except Exception:
            pass
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName(APP_EXECUTABLE_NAME)
    app.setApplicationDisplayName(APP_EXECUTABLE_NAME)
    app.setStyle("Fusion")

    main_window = MainPanel()
    main_window.show()
    sys.exit(app.exec())

# -*- coding: utf-8 -*-
"""
坤展成-中控多窗口播放器
开发公司：北京方桑兄弟科技有限公司
联系方式：18210234280
版本：v2.0 - 新增窗口独立媒体列表、广播+独立控制、配置自动保存
"""

import sys
import os

# PyInstaller打包后设置VLC路径
if getattr(sys, 'frozen', False):
    bundle_dir = sys._MEIPASS
    vlc_path = os.path.join(bundle_dir, 'vlc')
    if os.path.exists(vlc_path):
        os.environ['PYTHON_VLC_MODULE_PATH'] = vlc_path
        os.environ['PATH'] = vlc_path + os.pathsep + os.environ.get('PATH', '')
        if hasattr(os, 'add_dll_directory'):
            os.add_dll_directory(vlc_path)

import socket
import struct
import threading
import time
import hashlib
import json
import base64
import re
import uuid
from datetime import datetime, timedelta
import platform
if platform.system() == 'Windows':
    from ctypes import windll, c_void_p, c_int, byref, Structure, POINTER
else:
    windll = None
    from ctypes import c_void_p, c_int, byref, Structure, POINTER

# PyQt5 导入
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QTextEdit, QLineEdit,
    QSlider, QCheckBox, QComboBox, QGroupBox, QFrame, QDialog,
    QSpinBox, QDoubleSpinBox, QButtonGroup, QRadioButton, QTabWidget,
    QMessageBox, QSystemTrayIcon, QMenu, QAction, QFileDialog,
    QListWidget, QListWidgetItem, QStyle, QProgressBar, QSplitter,
    QToolButton, QScrollArea, QSizePolicy, QDesktopWidget
)
from PyQt5.QtCore import (
    Qt, QTimer, QPoint, QSize, QRect, QSettings, QThread,
    pyqtSignal, QUrl, QMutex, QWaitCondition
)
from PyQt5.QtGui import (
    QIcon, QPixmap, QFont, QColor, QPainter, QPen, QBrush,
    QKeySequence, QScreen
)
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtNetwork import QUdpSocket, QTcpSocket, QTcpServer, QHostAddress

# 尝试导入VLC
try:
    import vlc
    VLC_AVAILABLE = True
except ImportError:
    VLC_AVAILABLE = False
    print("警告: VLC库未安装，将使用PyQt5内置播放器")

# 尝试导入串口
try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False
    print("警告: pyserial库未安装，串口功能不可用")

# 常量定义
APP_NAME = "坤展成-中控多窗口播放器"
APP_VERSION = "v2.0"
COMPANY_NAME = "北京方桑兄弟科技有限公司"
CONTACT_PHONE = "18210234280"

# 通信端口定义
UDP_BROADCAST_PORT = 8880
TCP_BROADCAST_PORT = 8881
WINDOW_UDP_PORTS = [8888, 8889, 8890, 8891]
WINDOW_TCP_PORTS = [8892, 8893, 8894, 8895]

# 授权相关
TRIAL_DAYS = 30
LICENSE_FILE = "license.dat"
MACHINE_CODE_FILE = "machine_code.dat"

# 配置文件路径
CONFIG_FILE = "player_config.json"


# ============== 配置自动保存/加载 ==============

class ConfigManager:
    """配置管理类 - 自动保存和加载所有设置"""
    
    def __init__(self):
        self.config_file = CONFIG_FILE
        self.config = self._get_default_config()
        self.auto_save_timer = QTimer()
        self.auto_save_timer.timeout.connect(self.save_config)
        self.auto_save_timer.start(30000)  # 每30秒自动保存
        
    def _get_default_config(self):
        """获取默认配置"""
        return {
            "main_window": {
                "geometry": {"x": 100, "y": 100, "width": 1400, "height": 900}
            },
            "windows": {},  # 各窗口的独立配置
            "global_volume": 80,
            "last_opened_windows": [],
            "auto_play_on_open": True,
            "loop_playback": True,
            "last_media_directory": ""
        }
    
    def load_config(self):
        """加载配置"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    # 合并加载的配置和默认配置
                    self.config = self._merge_configs(self._get_default_config(), loaded)
                    print(f"配置已加载: {self.config_file}")
                    return True
        except Exception as e:
            print(f"加载配置失败: {e}")
        return False
    
    def save_config(self):
        """保存配置"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"保存配置失败: {e}")
            return False
    
    def save_config_immediately(self):
        """立即保存配置（用于重要操作后）"""
        self.save_config()
    
    def _merge_configs(self, default, loaded):
        """合并配置"""
        for key, value in loaded.items():
            if key in default and isinstance(default[key], dict) and isinstance(value, dict):
                default[key] = self._merge_configs(default[key], value)
            else:
                default[key] = value
        return default
    
    def get_main_window_geometry(self):
        """获取主窗口几何信息"""
        return self.config.get("main_window", {}).get("geometry", {})
    
    def set_main_window_geometry(self, geometry):
        """设置主窗口几何信息"""
        if "main_window" not in self.config:
            self.config["main_window"] = {}
        self.config["main_window"]["geometry"] = geometry
    
    def get_window_config(self, window_id):
        """获取指定窗口的配置"""
        return self.config.get("windows", {}).get(str(window_id), {})
    
    def set_window_config(self, window_id, window_config):
        """设置指定窗口的配置"""
        if "windows" not in self.config:
            self.config["windows"] = {}
        self.config["windows"][str(window_id)] = window_config
    
    def get_global_volume(self):
        """获取全局音量"""
        return self.config.get("global_volume", 80)
    
    def set_global_volume(self, volume):
        """设置全局音量"""
        self.config["global_volume"] = volume
    
    def get_auto_play_on_open(self):
        """获取打开窗口时是否自动播放"""
        return self.config.get("auto_play_on_open", True)
    
    def get_loop_playback(self):
        """获取是否循环播放"""
        return self.config.get("loop_playback", True)
    
    def set_last_opened_windows(self, window_ids):
        """设置上次打开的窗口列表"""
        self.config["last_opened_windows"] = window_ids
    
    def get_last_media_directory(self):
        """获取上次使用的媒体目录"""
        return self.config.get("last_media_directory", "")
    
    def set_last_media_directory(self, directory):
        """设置上次使用的媒体目录"""
        self.config["last_media_directory"] = directory


# ============== 机器码和授权管理 ==============

class LicenseManager:
    """授权管理类"""
    
    @staticmethod
    def get_machine_code():
        """获取机器码 - 基于硬件信息生成"""
        try:
            cpu_id = LicenseManager._get_cpu_id()
            disk_serial = LicenseManager._get_disk_serial()
            mac = LicenseManager._get_mac_address()
            
            raw = f"{cpu_id}-{disk_serial}-{mac}-KUNZHANCHENG"
            machine_code = hashlib.md5(raw.encode('utf-8')).hexdigest().upper()
            return machine_code
        except Exception as e:
            print(f"获取机器码失败: {e}")
            return "ERROR-MACHINE-CODE"
    
    @staticmethod
    def _get_cpu_id():
        """获取CPU ID"""
        try:
            import subprocess
            result = subprocess.run(
                'wmic cpu get ProcessorID',
                shell=True, capture_output=True, text=True
            )
            lines = result.stdout.strip().split('\n')
            if len(lines) > 1:
                return lines[1].strip()
        except:
            pass
        return "CPU-DEFAULT-ID"
    
    @staticmethod
    def _get_disk_serial():
        """获取磁盘序列号"""
        try:
            import subprocess
            result = subprocess.run(
                'wmic diskdrive get serialnumber',
                shell=True, capture_output=True, text=True
            )
            lines = result.stdout.strip().split('\n')
            if len(lines) > 1:
                return lines[1].strip()
        except:
            pass
        return "DISK-DEFAULT-SERIAL"
    
    @staticmethod
    def _get_mac_address():
        """获取MAC地址"""
        try:
            mac = uuid.getnode()
            return ':'.join(f'{(mac >> i) & 0xff:02x}' for i in range(0, 48, 8))
        except:
            return "MAC-DEFAULT-ADDR"
    
    @staticmethod
    def get_network_time():
        """获取网络时间"""
        try:
            import socket
            NTP_SERVER = "time.windows.com"
            NTP_PORT = 123
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(5)
            
            ntp_packet = b'\x1b' + 47 * b'\0'
            sock.sendto(ntp_packet, (NTP_SERVER, NTP_PORT))
            response = sock.recv(48)
            sock.close()
            
            timestamp = struct.unpack('!I', response[40:44])[0]
            timestamp -= 2208988800
            return datetime.fromtimestamp(timestamp)
        except Exception as e:
            print(f"获取网络时间失败: {e}")
            return datetime.now()
    
    @staticmethod
    def save_license(license_key):
        """保存授权信息"""
        try:
            with open(LICENSE_FILE, 'w', encoding='utf-8') as f:
                f.write(license_key)
            return True
        except Exception as e:
            print(f"保存授权失败: {e}")
            return False
    
    @staticmethod
    def load_license():
        """加载授权信息"""
        try:
            if os.path.exists(LICENSE_FILE):
                with open(LICENSE_FILE, 'r', encoding='utf-8') as f:
                    return f.read().strip()
        except:
            pass
        return None
    
    @staticmethod
    def verify_license(license_key):
        """验证授权码"""
        if not license_key:
            return False, "未找到授权码"
        
        try:
            expected = LicenseManager.generate_license_key(LicenseManager.get_machine_code())
            if license_key == expected:
                return True, "授权成功"
            else:
                return False, "授权码无效"
        except Exception as e:
            return False, f"验证失败: {e}"
    
    @staticmethod
    def generate_license_key(machine_code):
        """生成授权码"""
        salt = "KUNZHANCHENG-2024-LICENSE"
        raw = f"{machine_code}-{salt}"
        key = hashlib.md5(raw.encode('utf-8')).hexdigest().upper()
        return '-'.join([key[i:i+4] for i in range(0, 16, 4)])
    
    @staticmethod
    def check_license_status():
        """检查授权状态"""
        license_key = LicenseManager.load_license()
        
        if license_key:
            valid, msg = LicenseManager.verify_license(license_key)
            if valid:
                return True, "已授权", None
        
        start_time = LicenseManager.get_network_time()
        expire_time = start_time + timedelta(days=TRIAL_DAYS)
        remaining = (expire_time - start_time).days
        
        return False, "试用版", remaining


# ============== 视频播放器窗口 ==============

class VideoWindow(QFrame):
    """无边框视频播放窗口"""
    
    # 信号定义
    clicked = pyqtSignal(int)  # 点击信号，携带窗口编号
    media_list_changed = pyqtSignal(int, list)  # 媒体列表改变信号
    playback_state_changed = pyqtSignal(int, str)  # 播放状态改变信号
    
    def __init__(self, window_id, parent=None):
        super().__init__(parent)
        self.window_id = window_id
        self.is_locked = False
        self.is_visible = True
        self.media_files = []  # 每个窗口独立的媒体列表
        self.current_index = -1
        self.is_playing = False
        self.volume = 80
        self.is_muted = False
        self.is_fullscreen = False
        self.is_loop = True  # 默认循环播放
        
        # 初始化UI
        self.init_ui()
        
        # 初始化播放器
        self.init_player()
        
        # 拖拽相关
        self.drag_position = None
        self.is_dragging = False
        
    def init_ui(self):
        """初始化UI"""
        self.setWindowFlags(
            Qt.Window | 
            Qt.FramelessWindowHint | 
            Qt.WindowStaysOnTopHint 
        )
        self.setStyleSheet("""
            QFrame {
                background-color: #1a1a1a;
                border: 2px solid #333;
                border-radius: 5px;
            }
        """)
        
        # 布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 标题栏
        self.title_bar = QWidget()
        self.title_bar.setStyleSheet("background-color: #2d2d2d;")
        self.title_bar_layout = QHBoxLayout(self.title_bar)
        self.title_bar_layout.setContentsMargins(10, 5, 10, 5)
        
        self.title_label = QLabel(f"窗口 {self.window_id}")
        self.title_label.setStyleSheet("color: white; font-weight: bold;")
        
        self.lock_btn = QPushButton("🔓")
        self.lock_btn.setFixedSize(30, 30)
        self.lock_btn.clicked.connect(self.toggle_lock)
        self.lock_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                color: #aaa;
                font-size: 16px;
            }
            QPushButton:hover {
                color: white;
            }
        """)
        
        self.fullscreen_btn = QPushButton("⛶")
        self.fullscreen_btn.setFixedSize(30, 30)
        self.fullscreen_btn.clicked.connect(self.toggle_fullscreen)
        self.fullscreen_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                color: #aaa;
                font-size: 16px;
            }
            QPushButton:hover {
                color: white;
            }
        """)
        
        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(30, 30)
        self.close_btn.clicked.connect(self.hide_window)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                color: #aaa;
                font-size: 16px;
            }
            QPushButton:hover {
                color: #ff5555;
            }
        """)
        
        self.title_bar_layout.addWidget(self.title_label)
        self.title_bar_layout.addStretch()
        self.title_bar_layout.addWidget(self.lock_btn)
        self.title_bar_layout.addWidget(self.fullscreen_btn)
        self.title_bar_layout.addWidget(self.close_btn)
        
        layout.addWidget(self.title_bar)
        
        # 视频显示区域
        self.video_label = QLabel("双击添加媒体")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setStyleSheet("""
            QLabel {
                color: #666;
                font-size: 24px;
                background-color: #0a0a0a;
            }
        """)
        self.video_label.setMinimumSize(640, 360)
        
        # 安装事件过滤器
        self.video_label.installEventFilter(self)
        
        layout.addWidget(self.video_label)
        
        # 状态栏
        self.status_bar = QWidget()
        self.status_bar.setStyleSheet("background-color: #2d2d2d;")
        self.status_bar_layout = QHBoxLayout(self.status_bar)
        self.status_bar_layout.setContentsMargins(10, 5, 10, 5)
        
        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("color: #aaa;")
        
        self.media_label = QLabel("")
        self.media_label.setStyleSheet("color: #888; font-size: 12px;")
        
        self.status_bar_layout.addWidget(self.status_label)
        self.status_bar_layout.addStretch()
        self.status_bar_layout.addWidget(self.media_label)
        
        layout.addWidget(self.status_bar)
        
        self.resize(800, 500)
        
    def eventFilter(self, obj, event):
        """事件过滤器"""
        if obj == self.video_label:
            if event.type() == 7:  # MouseButtonPress
                if event.button() == Qt.LeftButton:
                    self.is_dragging = True
                    self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
                    self.activateWindow()
            elif event.type() == 8:  # MouseMove
                if self.is_dragging and not self.is_locked:
                    self.move(event.globalPos() - self.drag_position)
            elif event.type() == 10:  # MouseButtonRelease
                self.is_dragging = False
            elif event.type() == 12:  # MouseButtonDblClick
                self.toggle_fullscreen()
        return super().eventFilter(obj, event)
    
    def init_player(self):
        """初始化播放器"""
        if VLC_AVAILABLE:
            self.vlc_instance = vlc.Instance()
            self.vlc_player = self.vlc_instance.media_player_new()
            self.vlc_player.set_hwnd(int(self.winId()) if platform.system() == 'Windows' else self.video_label.winId())
        else:
            self.vlc_instance = None
            self.vlc_player = None
            self.media_player = QMediaPlayer()
            self.media_player.setVideoOutput(self.video_label)
        
    def set_media_files(self, files):
        """设置媒体文件列表（覆盖）"""
        self.media_files = list(files)
        self.current_index = -1
        self.media_list_changed.emit(self.window_id, self.media_files)
        self.update_media_label()
        
        if files and self.is_loop:
            self.current_index = 0
            self.play()
    
    def add_media_file(self, file_path):
        """添加媒体文件到列表"""
        if file_path not in self.media_files:
            self.media_files.append(file_path)
            self.media_list_changed.emit(self.window_id, self.media_files)
            self.update_media_label()
            
            # 如果是第一个文件且配置了自动播放
            if len(self.media_files) == 1 and self.current_index == -1:
                self.current_index = 0
                if hasattr(self, '_auto_play') and self._auto_play:
                    self.play()
    
    def remove_media_file(self, index):
        """移除媒体文件"""
        if 0 <= index < len(self.media_files):
            removed = self.media_files.pop(index)
            if self.current_index == index:
                self.current_index = min(index, len(self.media_files) - 1)
                if self.current_index >= 0:
                    self.play()
            elif self.current_index > index:
                self.current_index -= 1
            self.media_list_changed.emit(self.window_id, self.media_files)
            self.update_media_label()
            return removed
        return None
    
    def get_media_files(self):
        """获取媒体文件列表"""
        return self.media_files.copy()
    
    def update_media_label(self):
        """更新媒体文件名显示"""
        if self.media_files and self.current_index >= 0:
            name = os.path.basename(self.media_files[self.current_index])
            self.media_label.setText(f"{self.current_index + 1}/{len(self.media_files)}: {name}")
        else:
            self.media_label.setText("")
    
    def play(self, file_path=None):
        """播放指定文件或当前文件"""
        if file_path:
            if file_path in self.media_files:
                self.current_index = self.media_files.index(file_path)
            else:
                self.add_media_file(file_path)
                self.current_index = len(self.media_files) - 1
        
        if not self.media_files or self.current_index < 0:
            self.status_label.setText("无媒体文件")
            return
        
        if self.current_index >= len(self.media_files):
            self.current_index = 0
        
        media_path = self.media_files[self.current_index]
        
        if VLC_AVAILABLE and self.vlc_player:
            media = self.vlc_instance.media_new(media_path)
            self.vlc_player.set_media(media)
            self.vlc_player.audio_set_volume(self.volume if not self.is_muted else 0)
            self.vlc_player.play()
        else:
            self.media_player.setMedia(QMediaContent(QUrl.fromLocalFile(media_path)))
            self.media_player.setVolume(self.volume if not self.is_muted else 0)
            self.media_player.play()
        
        self.is_playing = True
        self.status_label.setText("播放中")
        self.update_media_label()
        self.playback_state_changed.emit(self.window_id, "playing")
    
    def pause(self):
        """暂停"""
        if VLC_AVAILABLE and self.vlc_player:
            self.vlc_player.pause()
        else:
            self.media_player.pause()
        self.is_playing = False
        self.status_label.setText("已暂停")
        self.playback_state_changed.emit(self.window_id, "paused")
    
    def stop(self):
        """停止"""
        if VLC_AVAILABLE and self.vlc_player:
            self.vlc_player.stop()
        else:
            self.media_player.stop()
        self.is_playing = False
        self.status_label.setText("已停止")
        self.current_index = -1
        self.update_media_label()
        self.playback_state_changed.emit(self.window_id, "stopped")
    
    def replay(self):
        """重播"""
        if self.current_index >= 0 and self.current_index < len(self.media_files):
            self.play()
    
    def next_media(self):
        """下一个媒体"""
        if self.media_files:
            self.current_index = (self.current_index + 1) % len(self.media_files)
            self.play()
    
    def prev_media(self):
        """上一个媒体"""
        if self.media_files:
            self.current_index = (self.current_index - 1) % len(self.media_files)
            self.play()
    
    def set_volume(self, volume):
        """设置音量"""
        self.volume = volume
        if VLC_AVAILABLE and self.vlc_player:
            if not self.is_muted:
                self.vlc_player.audio_set_volume(volume)
        else:
            if not self.is_muted:
                self.media_player.setVolume(volume)
    
    def toggle_mute(self):
        """切换静音"""
        self.is_muted = not self.is_muted
        if VLC_AVAILABLE and self.vlc_player:
            self.vlc_player.audio_set_volume(0 if self.is_muted else self.volume)
        else:
            self.media_player.setVolume(0 if self.is_muted else self.volume)
        return self.is_muted
    
    def set_loop(self, enabled):
        """设置是否循环播放"""
        self.is_loop = enabled
    
    def toggle_lock(self):
        """切换锁定状态"""
        self.is_locked = not self.is_locked
        self.lock_btn.setText("🔒" if self.is_locked else "🔓")
        self.setWindowFlags(
            Qt.Window | 
            Qt.FramelessWindowHint | 
            (Qt.WindowStaysOnTopHint if self.is_visible else 0)
        )
        if self.is_visible:
            self.show()
        return self.is_locked
    
    def toggle_fullscreen(self):
        """切换全屏"""
        self.is_fullscreen = not self.is_fullscreen
        if self.is_fullscreen:
            self.setWindowFlags(
                Qt.Window |
                Qt.FramelessWindowHint |
                Qt.WindowStaysOnTopHint |
                Qt.WindowFullScreen
            )
        else:
            self.setWindowFlags(
                Qt.Window |
                Qt.FramelessWindowHint |
                (Qt.WindowStaysOnTopHint if self.is_visible else 0)
            )
        self.show()
        self.raise_()
    
    def set_position(self, x, y, width, height):
        """设置窗口位置和大小"""
        self.move(x, y)
        self.resize(width, height)
        
        # 等待窗口准备好后再设置视频输出
        QTimer.singleShot(100, self._setup_video_output)
    
    def _setup_video_output(self):
        """设置视频输出（延迟调用）"""
        if VLC_AVAILABLE and self.vlc_player:
            if platform.system() == 'Windows':
                self.vlc_player.set_hwnd(int(self.winId()))
            else:
                self.vlc_player.set_nsobject(int(self.video_label.winId()))
    
    def set_always_on_top(self, enabled):
        """设置是否总在最前"""
        self.is_visible = enabled
        flags = Qt.Window | Qt.FramelessWindowHint
        if enabled:
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()
    
    def hide_window(self):
        """隐藏窗口"""
        self.hide()
        self.is_visible = False
    
    def show_window(self):
        """显示窗口"""
        self.show()
        self.is_visible = True
        self.raise_()
        self.activateWindow()
    
    def get_config(self):
        """获取窗口配置"""
        return {
            "position": {
                "x": self.x(),
                "y": self.y(),
                "width": self.width(),
                "height": self.height()
            },
            "is_visible": self.is_visible,
            "is_locked": self.is_locked,
            "is_always_on_top": self.is_visible,
            "media_files": self.media_files,
            "current_index": self.current_index,
            "volume": self.volume,
            "is_muted": self.is_muted,
            "is_loop": self.is_loop
        }
    
    def apply_config(self, config):
        """应用窗口配置"""
        if "position" in config:
            pos = config["position"]
            self.set_position(pos.get("x", 100), pos.get("y", 100), 
                            pos.get("width", 800), pos.get("height", 500))
        
        if "media_files" in config:
            self.media_files = config["media_files"]
        
        if "current_index" in config:
            self.current_index = config["current_index"]
        
        if "volume" in config:
            self.volume = config["volume"]
        
        if "is_muted" in config:
            self.is_muted = config["is_muted"]
        
        if "is_loop" in config:
            self.is_loop = config["is_loop"]
        
        if "is_visible" in config and config["is_visible"]:
            self.show_window()
        
        if "is_locked" in config:
            self.is_locked = config["is_locked"]
            self.lock_btn.setText("🔒" if self.is_locked else "🔓")
        
        self.update_media_label()
        self.media_list_changed.emit(self.window_id, self.media_files)


# ============== 网络管理 ==============

class NetworkManager(QThread):
    """网络通信管理"""
    
    udp_received = pyqtSignal(str, str, int)
    tcp_received = pyqtSignal(str, str, int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.udp_socket = None
        self.tcp_socket = None
        self.tcp_server = None
        self.running = False
        
    def start_network(self):
        """启动网络服务"""
        self.running = True
        self.start()
        
    def stop_network(self):
        """停止网络服务"""
        self.running = False
        if self.udp_socket:
            self.udp_socket.close()
        if self.tcp_socket:
            self.tcp_socket.close()
        if self.tcp_server:
            self.tcp_server.close()
        self.quit()
        self.wait()
    
    def run(self):
        """线程运行"""
        self.setup_udp_listener(UDP_BROADCAST_PORT)
        self.setup_tcp_server(TCP_BROADCAST_PORT)
        
        while self.running:
            self.msleep(100)
    
    def setup_udp_listener(self, port):
        """设置UDP监听"""
        self.udp_socket = QUdpSocket(self)
        self.udp_socket.bind(port, QUdpSocket.ReuseAddressHint)
        self.udp_socket.readyRead.connect(self.read_udp)
    
    def read_udp(self):
        """读取UDP数据"""
        while self.udp_socket.hasPendingDatagrams():
            data, host, port = self.udp_socket.readDatagram(8192)
            message = data.decode('utf-8', errors='ignore').strip()
            self.udp_received.emit(message, host.toString(), port)
    
    def setup_tcp_server(self, port):
        """设置TCP服务器"""
        self.tcp_server = QTcpServer(self)
        self.tcp_server.newConnection.connect(self.handle_tcp_connection)
        self.tcp_server.listen(QHostAddress.Any, port)
    
    def handle_tcp_connection(self):
        """处理TCP连接"""
        client = self.tcp_server.nextPendingConnection()
        client.readyRead.connect(lambda: self.read_tcp(client))
    
    def read_tcp(self, client):
        """读取TCP数据"""
        data = client.readAll().data()
        message = data.decode('utf-8', errors='ignore').strip()
        self.tcp_received.emit(message, client.peerAddress().toString(), client.peerPort())
    
    def send_udp(self, message, target_ip, port):
        """发送UDP消息"""
        sock = QUdpSocket(self)
        sock.writeDatagram(message.encode('utf-8'), QHostAddress(target_ip), port)
        sock.close()
    
    def send_tcp(self, message, target_ip, port):
        """发送TCP消息"""
        sock = QTcpSocket(self)
        sock.connectToHost(QHostAddress(target_ip), port)
        if sock.waitForConnected(1000):
            sock.write(message.encode('utf-8'))
            sock.close()


# ============== 串口管理 ==============

class SerialManager(QThread):
    """串口通信管理"""
    
    data_received = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.serial = None
        self.running = False
        self.port = ""
        self.baudrate = 9600
        
    def configure(self, port, baudrate=9600):
        """配置串口"""
        self.port = port
        self.baudrate = baudrate
        
    def connect(self):
        """连接串口"""
        if SERIAL_AVAILABLE and self.port:
            try:
                self.serial = serial.Serial(self.port, self.baudrate, timeout=1)
                self.running = True
                self.start()
                return True
            except Exception as e:
                print(f"串口连接失败: {e}")
        return False
    
    def disconnect(self):
        """断开串口"""
        self.running = False
        if self.serial and self.serial.is_open:
            self.serial.close()
        self.quit()
        self.wait()
    
    def is_connected(self):
        """检查是否连接"""
        return self.serial is not None and self.serial.is_open
    
    def send(self, data):
        """发送数据"""
        if self.serial and self.serial.is_open:
            self.serial.write(data.encode('utf-8'))
    
    def run(self):
        """线程运行"""
        while self.running and self.serial and self.serial.is_open:
            try:
                if self.serial.in_waiting > 0:
                    data = self.serial.readline().decode('utf-8', errors='ignore').strip()
                    if data:
                        self.data_received.emit(data)
                self.msleep(50)
            except Exception as e:
                print(f"串口读取错误: {e}")
                break


# ============== 主窗口 ==============

class MainWindow(QMainWindow):
    """主控制窗口"""
    
    def __init__(self):
        super().__init__()
        
        # 初始化配置管理器
        self.config_manager = ConfigManager()
        self.config_manager.load_config()
        
        # 窗口管理
        self.video_windows = {}
        self.current_window_id = 1
        self.is_minimized_to_tray = False
        
        # 初始化网络和串口
        self.network_manager = NetworkManager(self)
        self.network_manager.udp_received.connect(self.on_udp_message)
        self.network_manager.tcp_received.connect(self.on_tcp_message)
        
        self.serial_manager = SerialManager(self)
        self.serial_manager.data_received.connect(self.on_serial_data)
        
        # 初始化UI
        self.init_ui()
        
        # 启动网络
        self.network_manager.start_network()
        
        # 恢复上次的窗口配置
        self.restore_windows()
        
        # 应用加载的配置
        self.apply_loaded_config()
    
    def init_ui(self):
        """初始化UI"""
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setGeometry(100, 100, 1400, 900)
        
        # 应用保存的主窗口几何
        geometry = self.config_manager.get_main_window_geometry()
        if geometry:
            self.setGeometry(
                geometry.get("x", 100),
                geometry.get("y", 100),
                geometry.get("width", 1400),
                geometry.get("height", 900)
            )
        
        # 中心部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)
        
        # 标签页
        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(self.create_control_tab(), "控制面板")
        self.tab_widget.addTab(self.create_settings_tab(), "设置")
        self.tab_widget.addTab(self.create_network_tab(), "网络控制")
        self.tab_widget.addTab(self.create_about_tab(), "关于")
        
        main_layout.addWidget(self.tab_widget)
        
        # 创建托盘图标
        self.create_tray_icon()
    
    def create_control_tab(self):
        """创建控制面板标签页"""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        
        # 左侧面板 - 窗口管理
        left_panel = self.create_window_panel()
        
        # 中间面板 - 媒体列表（根据选中窗口显示不同内容）
        self.media_panel = self.create_media_panel()
        
        # 右侧面板 - 控制区
        right_panel = self.create_control_area_panel()
        
        # 分割器
        splitter1 = QSplitter(Qt.Horizontal)
        splitter1.addWidget(left_panel)
        splitter1.addWidget(self.media_panel)
        splitter1.addWidget(right_panel)
        splitter1.setStretchFactor(0, 1)
        splitter1.setStretchFactor(1, 2)
        splitter1.setStretchFactor(2, 1)
        
        layout.addWidget(splitter1)
        
        return widget
    
    def create_window_panel(self):
        """创建窗口管理面板"""
        group = QGroupBox("窗口管理")
        layout = QVBoxLayout(group)
        
        # 窗口标签组
        self.window_tabs = QButtonGroup()
        window_layout = QGridLayout()
        
        for i in range(1, 9):
            btn = QPushButton(f"窗口{i}")
            btn.setCheckable(True)
            btn.setMinimumHeight(40)
            btn.clicked.connect(lambda checked, wid=i: self.select_window(wid))
            row = (i - 1) // 4
            col = (i - 1) % 4
            window_layout.addWidget(btn, row, col)
            self.window_tabs.addButton(btn, i)
        
        layout.addLayout(window_layout)
        
        # 选中窗口1
        self.window_tabs.button(1).setChecked(True)
        
        # 窗口位置设置
        pos_group = QGroupBox("窗口位置")
        pos_layout = QGridLayout(pos_group)
        
        pos_layout.addWidget(QLabel("X:"), 0, 0)
        self.x_spin = QSpinBox()
        self.x_spin.setRange(0, 3840)
        self.x_spin.setValue(100)
        pos_layout.addWidget(self.x_spin, 0, 1)
        
        pos_layout.addWidget(QLabel("Y:"), 0, 2)
        self.y_spin = QSpinBox()
        self.y_spin.setRange(0, 2160)
        self.y_spin.setValue(100)
        pos_layout.addWidget(self.y_spin, 0, 3)
        
        pos_layout.addWidget(QLabel("宽:"), 1, 0)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(320, 1920)
        self.width_spin.setValue(800)
        pos_layout.addWidget(self.width_spin, 1, 1)
        
        pos_layout.addWidget(QLabel("高:"), 1, 2)
        self.height_spin = QSpinBox()
        self.height_spin.setRange(240, 1080)
        self.height_spin.setValue(600)
        pos_layout.addWidget(self.height_spin, 1, 3)
        
        layout.addWidget(pos_group)
        
        # 打开/关闭按钮
        btn_layout = QHBoxLayout()
        self.open_btn = QPushButton("📺 打开窗口")
        self.open_btn.clicked.connect(self.open_current_window)
        btn_layout.addWidget(self.open_btn)
        
        self.close_btn = QPushButton("❌ 关闭窗口")
        self.close_btn.clicked.connect(self.close_current_window)
        btn_layout.addWidget(self.close_btn)
        
        layout.addLayout(btn_layout)
        
        # 预设尺寸
        preset_layout = QHBoxLayout()
        presets = [("720p", 1280, 720), ("1080p", 1920, 1080), ("480p", 854, 480)]
        for name, w, h in presets:
            btn = QPushButton(name)
            btn.clicked.connect(lambda checked, width=w, height=h: self.set_window_size(width, height))
            preset_layout.addWidget(btn)
        layout.addLayout(preset_layout)
        
        layout.addStretch()
        
        return group
    
    def create_media_panel(self):
        """创建媒体列表面板（根据选中窗口显示不同内容）"""
        group = QGroupBox("媒体列表")
        group.setMinimumWidth(400)
        layout = QVBoxLayout(group)
        
        # 当前窗口指示
        self.media_panel_title = QLabel("窗口 1 的媒体列表")
        self.media_panel_title.setStyleSheet("font-weight: bold; color: #2196F3;")
        layout.addWidget(self.media_panel_title)
        
        # 媒体列表
        self.media_list = QListWidget()
        self.media_list.setMinimumHeight(200)
        self.media_list.itemDoubleClicked.connect(self.play_selected_media)
        layout.addWidget(self.media_list)
        
        # 媒体列表按钮
        media_btn_layout = QHBoxLayout()
        add_btn = QPushButton("➕ 添加")
        add_btn.clicked.connect(self.add_media_file)
        media_btn_layout.addWidget(add_btn)
        
        remove_btn = QPushButton("➖ 移除")
        remove_btn.clicked.connect(self.remove_selected_media)
        media_btn_layout.addWidget(remove_btn)
        
        clear_btn = QPushButton("🗑 清空")
        clear_btn.clicked.connect(self.clear_media_list)
        media_btn_layout.addWidget(clear_btn)
        
        layout.addLayout(media_btn_layout)
        
        return group
    
    def create_control_area_panel(self):
        """创建控制区域面板（广播控制 + 独立控制）"""
        group = QGroupBox("控制区域")
        layout = QVBoxLayout(group)
        
        # ===== 广播控制区 =====
        broadcast_group = QGroupBox("🌐 广播控制（控制所有窗口）")
        broadcast_layout = QGridLayout(broadcast_group)
        
        broadcast_buttons = [
            ("▶ 全部播放", "play_all"),
            ("⏸ 全部暂停", "pause_all"),
            ("⏹ 全部停止", "stop_all"),
            ("🔄 全部重播", "replay_all"),
            ("⏮ 全部上一个", "prev_all"),
            ("⏭ 全部下一个", "next_all"),
        ]
        
        for i, (text, cmd) in enumerate(broadcast_buttons):
            btn = QPushButton(text)
            btn.setMinimumHeight(40)
            btn.clicked.connect(lambda checked, c=cmd: self.broadcast_control(c))
            broadcast_layout.addWidget(btn, i // 3, i % 3)
        
        layout.addWidget(broadcast_group)
        
        # ===== 独立控制区 =====
        independent_group = QGroupBox("🎯 独立控制（各窗口独立控制）")
        independent_layout = QVBoxLayout(independent_group)
        
        # 窗口控制按钮容器
        self.window_controls_container = QWidget()
        self.window_controls_layout = QVBoxLayout(self.window_controls_container)
        self.window_controls_layout.setAlignment(Qt.AlignTop)
        
        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidget(self.window_controls_container)
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(200)
        independent_layout.addWidget(scroll)
        
        # 无窗口提示
        self.no_window_label = QLabel("尚未打开任何窗口\n打开窗口后将在此显示控制按钮")
        self.no_window_label.setAlignment(Qt.AlignCenter)
        self.no_window_label.setStyleSheet("color: #888; padding: 20px;")
        self.window_controls_layout.addWidget(self.no_window_label)
        
        layout.addWidget(independent_group)
        
        # ===== 全局音量控制 =====
        volume_group = QGroupBox("🔊 全局音量")
        volume_layout = QHBoxLayout(volume_group)
        
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(self.config_manager.get_global_volume())
        self.volume_slider.valueChanged.connect(self.on_volume_changed)
        volume_layout.addWidget(self.volume_slider)
        
        self.volume_label = QLabel(f"{self.volume_slider.value()}%")
        self.volume_layout = volume_layout
        
        self.mute_btn = QPushButton("🔊 静音")
        self.mute_btn.clicked.connect(self.toggle_mute)
        volume_layout.addWidget(self.mute_btn)
        
        layout.addWidget(volume_group)
        
        # ===== 日志区 =====
        log_group = QGroupBox("日志")
        log_layout = QVBoxLayout(log_group)
        
        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(150)
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        
        layout.addWidget(log_group)
        
        return group
    
    def create_settings_tab(self):
        """创建设置标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 自动播放设置
        auto_group = QGroupBox("播放设置")
        auto_layout = QVBoxLayout(auto_group)
        
        self.auto_play_checkbox = QCheckBox("打开窗口时自动播放")
        self.auto_play_checkbox.setChecked(self.config_manager.get_auto_play_on_open())
        auto_layout.addWidget(self.auto_play_checkbox)
        
        self.loop_playback_checkbox = QCheckBox("循环播放媒体")
        self.loop_playback_checkbox.setChecked(self.config_manager.get_loop_playback())
        auto_layout.addWidget(self.loop_playback_checkbox)
        
        layout.addWidget(auto_group)
        
        # 串口设置
        serial_group = QGroupBox("串口设置")
        serial_layout = QHBoxLayout(serial_group)
        
        serial_layout.addWidget(QLabel("串口:"))
        self.serial_port_combo = QComboBox()
        self.update_serial_ports()
        serial_layout.addWidget(self.serial_port_combo)
        
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.update_serial_ports)
        serial_layout.addWidget(refresh_btn)
        
        self.serial_connect_btn = QPushButton("连接串口")
        self.serial_connect_btn.clicked.connect(self.toggle_serial_connection)
        serial_layout.addWidget(self.serial_connect_btn)
        
        layout.addWidget(serial_group)
        
        # 窗口预设
        preset_group = QGroupBox("窗口预设布局")
        preset_layout = QGridLayout(preset_group)
        
        presets = [
            ("单窗口", [[0, 0, 1920, 1080]]),
            ("左右分屏", [[0, 0, 960, 1080], [960, 0, 960, 1080]]),
            ("四宫格", [[0, 0, 960, 540], [960, 0, 960, 540], 
                       [0, 540, 960, 540], [960, 540, 960, 540]]),
            ("上下分屏", [[0, 0, 1920, 540], [0, 540, 1920, 540]]),
        ]
        
        for i, (name, positions) in enumerate(presets):
            btn = QPushButton(name)
            btn.clicked.connect(lambda checked, pos=positions: self.apply_preset_layout(pos))
            preset_layout.addWidget(btn, i // 2, i % 2)
        
        layout.addWidget(preset_group)
        
        # 保存按钮
        save_btn = QPushButton("💾 立即保存配置")
        save_btn.clicked.connect(self.save_config_now)
        layout.addWidget(save_btn)
        
        layout.addStretch()
        
        return widget
    
    def create_network_tab(self):
        """创建网络控制标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 目标设置
        target_group = QGroupBox("目标设置")
        target_layout = QGridLayout(target_group)
        
        target_layout.addWidget(QLabel("目标IP:"), 0, 0)
        self.target_ip_edit = QLineEdit("255.255.255.255")
        target_layout.addWidget(self.target_ip_edit, 0, 1)
        
        target_layout.addWidget(QLabel("UDP端口:"), 0, 2)
        self.udp_port_spin = QSpinBox()
        self.udp_port_spin.setRange(1, 65535)
        self.udp_port_spin.setValue(8880)
        target_layout.addWidget(self.udp_port_spin, 0, 3)
        
        target_layout.addWidget(QLabel("TCP端口:"), 0, 4)
        self.tcp_port_spin = QSpinBox()
        self.tcp_port_spin.setRange(1, 65535)
        self.tcp_port_spin.setValue(8881)
        target_layout.addWidget(self.tcp_port_spin, 0, 5)
        
        layout.addWidget(target_group)
        
        # 命令发送
        command_group = QGroupBox("发送命令")
        command_layout = QGridLayout(command_group)
        
        commands = [
            ("播放", "play"), ("暂停", "pause"), ("停止", "stop"),
            ("上一个", "prev"), ("下一个", "next"), ("静音", "mute")
        ]
        
        for i, (text, cmd) in enumerate(commands):
            btn = QPushButton(text)
            btn.clicked.connect(lambda checked, c=cmd: self.broadcast_network_command(c))
            command_layout.addWidget(btn, i // 3, i % 3)
        
        # 自定义命令
        cmd_layout = QHBoxLayout()
        self.custom_cmd_edit = QLineEdit()
        self.custom_cmd_edit.setPlaceholderText("输入自定义命令...")
        cmd_layout.addWidget(self.custom_cmd_edit)
        
        send_udp_btn = QPushButton("UDP发送")
        send_udp_btn.clicked.connect(lambda: self.send_custom_command("udp"))
        cmd_layout.addWidget(send_udp_btn)
        
        send_tcp_btn = QPushButton("TCP发送")
        send_tcp_btn.clicked.connect(lambda: self.send_custom_command("tcp"))
        cmd_layout.addWidget(send_tcp_btn)
        
        command_layout.addLayout(cmd_layout, 2, 0, 1, 6)
        
        layout.addWidget(command_group)
        
        # 手动控制命令
        manual_group = QGroupBox("窗口手动控制")
        manual_layout = QHBoxLayout(manual_group)
        
        manual_layout.addWidget(QLabel("窗口号:"))
        self.manual_window_spin = QSpinBox()
        self.manual_window_spin.setRange(1, 8)
        manual_layout.addWidget(self.manual_window_spin)
        
        manual_layout.addWidget(QLabel("命令:"))
        self.manual_cmd_combo = QComboBox()
        self.manual_cmd_combo.addItems(["play", "pause", "stop", "replay", "next", "prev"])
        manual_layout.addWidget(self.manual_cmd_combo)
        
        manual_send_btn = QPushButton("发送到窗口")
        manual_send_btn.clicked.connect(self.send_to_specific_window)
        manual_layout.addWidget(manual_send_btn)
        
        layout.addWidget(manual_group)
        
        layout.addStretch()
        
        return widget
    
    def create_about_tab(self):
        """创建关于标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        layout.addWidget(QLabel(f"<h1>{APP_NAME}</h1>"))
        layout.addWidget(QLabel(f"版本: {APP_VERSION}"))
        layout.addWidget(QLabel(f"开发公司: {COMPANY_NAME}"))
        layout.addWidget(QLabel(f"联系方式: {CONTACT_PHONE}"))
        
        info_text = QTextEdit()
        info_text.setReadOnly(True)
        info_text.setHtml("""
            <h3>功能说明</h3>
            <ul>
                <li>支持最多8个独立视频播放窗口</li>
                <li>每个窗口有独立的媒体列表</li>
                <li>支持广播控制和独立控制</li>
                <li>支持网络（UDP/TCP）远程控制</li>
                <li>支持串口控制</li>
                <li>自动保存和加载配置</li>
                <li>支持多种视频格式</li>
            </ul>
            
            <h3>快捷键</h3>
            <ul>
                <li>Ctrl+1~8: 切换当前窗口</li>
                <li>Space: 播放/暂停</li>
                <li>←/→: 上一个/下一个媒体</li>
                <li>M: 静音</li>
                <li>F: 全屏</li>
            </ul>
        """)
        layout.addWidget(info_text)
        
        layout.addStretch()
        
        return widget
    
    def create_tray_icon(self):
        """创建托盘图标"""
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setToolTip(APP_NAME)
        self.tray_icon.activated.connect(self.on_tray_activated)
        
        # 创建菜单
        tray_menu = QMenu()
        show_action = QAction("显示主窗口", self)
        show_action.triggered.connect(self.show_main_window)
        tray_menu.addAction(show_action)
        
        hide_action = QAction("隐藏到托盘", self)
        hide_action.triggered.connect(self.hide_to_tray)
        tray_menu.addAction(hide_action)
        
        tray_menu.addSeparator()
        
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self.quit_application)
        tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()
    
    # ============== 窗口管理方法 ==============
    
    def select_window(self, window_id):
        """选择窗口"""
        self.current_window_id = window_id
        self.window_tabs.button(window_id).setChecked(True)
        
        # 更新媒体列表显示
        self.update_media_list_display()
        
        self.log(f"已选择窗口 {window_id}")
    
    def update_media_list_display(self):
        """更新媒体列表显示"""
        self.media_panel_title.setText(f"窗口 {self.current_window_id} 的媒体列表")
        
        # 清空列表
        self.media_list.clear()
        
        # 如果窗口存在，显示其媒体列表
        if self.current_window_id in self.video_windows:
            window = self.video_windows[self.current_window_id]
            for file_path in window.get_media_files():
                item = QListWidgetItem(os.path.basename(file_path))
                item.setData(Qt.UserRole, file_path)
                self.media_list.addItem(item)
    
    def update_window_controls(self):
        """更新独立控制区的窗口按钮"""
        # 清除现有控件（保留提示标签）
        while self.window_controls_layout.count() > 1:
            item = self.window_controls_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # 显示/隐藏无窗口提示
        self.no_window_label.setVisible(len(self.video_windows) == 0)
        
        # 为每个已打开的窗口添加控制按钮
        for window_id, window in sorted(self.video_windows.items()):
            window_control = self.create_window_control_widget(window_id, window)
            self.window_controls_layout.insertWidget(
                self.window_controls_layout.count() - 1,  # 在提示标签前插入
                window_control
            )
    
    def create_window_control_widget(self, window_id, window):
        """创建单个窗口的控制组件"""
        group = QGroupBox(f"窗口 {window_id}")
        group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #444;
                border-radius: 5px;
                margin-top: 10px;
                padding: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        layout = QHBoxLayout(group)
        
        # 播放状态指示
        status_label = QLabel("▶" if window.is_playing else "⏸")
        status_label.setStyleSheet("font-size: 16px;")
        layout.addWidget(status_label)
        
        # 独立控制按钮
        play_btn = QPushButton("▶")
        play_btn.setToolTip("播放")
        play_btn.clicked.connect(lambda: self.play_window(window_id))
        layout.addWidget(play_btn)
        
        pause_btn = QPushButton("⏸")
        pause_btn.setToolTip("暂停")
        pause_btn.clicked.connect(lambda: self.pause_window(window_id))
        layout.addWidget(pause_btn)
        
        stop_btn = QPushButton("⏹")
        stop_btn.setToolTip("停止")
        stop_btn.clicked.connect(lambda: self.stop_window(window_id))
        layout.addWidget(stop_btn)
        
        prev_btn = QPushButton("⏮")
        prev_btn.setToolTip("上一个")
        prev_btn.clicked.connect(lambda: self.prev_window_media(window_id))
        layout.addWidget(prev_btn)
        
        next_btn = QPushButton("⏭")
        next_btn.setToolTip("下一个")
        next_btn.clicked.connect(lambda: self.next_window_media(window_id))
        layout.addWidget(next_btn)
        
        # 文件数量
        file_count = len(window.get_media_files())
        count_label = QLabel(f"{file_count}个文件")
        count_label.setStyleSheet("color: #888;")
        layout.addWidget(count_label)
        
        # 选中按钮
        select_btn = QPushButton("选中")
        select_btn.setCheckable(True)
        select_btn.setChecked(window_id == self.current_window_id)
        select_btn.clicked.connect(lambda: self.select_window(window_id))
        layout.addWidget(select_btn)
        
        return group
    
    def open_current_window(self):
        """打开当前选中的窗口"""
        x = self.x_spin.value()
        y = self.y_spin.value()
        w = self.width_spin.value()
        h = self.height_spin.value()
        
        self.x_spin.setValue(x)
        self.y_spin.setValue(y)
        self.width_spin.setValue(w)
        self.height_spin.setValue(h)
        
        # 创建或移动窗口
        if self.current_window_id not in self.video_windows:
            window = VideoWindow(self.current_window_id)
            window.clicked.connect(self.on_video_window_clicked)
            window.media_list_changed.connect(self.on_window_media_changed)
            window.playback_state_changed.connect(self.on_window_playback_changed)
            
            # 应用保存的窗口配置
            saved_config = self.config_manager.get_window_config(self.current_window_id)
            if saved_config:
                window.apply_config(saved_config)
            
            # 如果没有保存的配置，设置位置并根据配置决定是否自动播放
            if not saved_config:
                window.set_position(x, y, w, h)
                window._auto_play = self.config_manager.get_auto_play_on_open()
            
            self.video_windows[self.current_window_id] = window
            
            # 连接播放结束信号
            if VLC_AVAILABLE:
                window.vlc_player.event_manager().event_attach(
                    vlc.EventType().MediaPlayerEndReached,
                    lambda event, w=window: self.on_media_ended(w)
                )
        
        window = self.video_windows[self.current_window_id]
        window.set_position(x, y, w, h)
        window.show()
        window.raise_()
        window.activateWindow()
        
        # 自动播放（如果窗口是新打开的且配置允许）
        if self.config_manager.get_auto_play_on_open() and window.current_index < 0 and window.media_files:
            window.current_index = 0
            window.play()
        
        # 更新独立控制区
        self.update_window_controls()
        
        # 保存配置
        self.config_manager.set_last_opened_windows(list(self.video_windows.keys()))
        self.config_manager.save_config_immediately()
        
        self.log(f"窗口{self.current_window_id}已打开")
    
    def close_current_window(self):
        """关闭当前选中的窗口"""
        if self.current_window_id in self.video_windows:
            # 保存窗口配置
            window = self.video_windows[self.current_window_id]
            self.config_manager.set_window_config(self.current_window_id, window.get_config())
            self.config_manager.save_config_immediately()
            
            # 关闭窗口
            window.close()
            del self.video_windows[self.current_window_id]
            
            # 更新独立控制区
            self.update_window_controls()
            
            self.log(f"窗口{self.current_window_id}已关闭")
    
    def restore_windows(self):
        """恢复上次的窗口配置"""
        last_windows = self.config_manager.config.get("last_opened_windows", [])
        
        for window_id in last_windows:
            if window_id not in self.video_windows:
                # 临时切换到窗口ID以打开
                self.current_window_id = window_id
                self.open_current_window()
        
        # 恢复窗口1为当前选择
        if 1 in self.video_windows:
            self.select_window(1)
    
    def apply_loaded_config(self):
        """应用加载的配置"""
        # 设置音量
        volume = self.config_manager.get_global_volume()
        self.volume_slider.setValue(volume)
        
        # 设置复选框
        self.auto_play_checkbox.setChecked(self.config_manager.get_auto_play_on_open())
        self.loop_playback_checkbox.setChecked(self.config_manager.get_loop_playback())
    
    def set_window_size(self, width, height):
        """预设窗口尺寸"""
        self.width_spin.setValue(width)
        self.height_spin.setValue(height)
    
    def apply_preset_layout(self, positions):
        """应用预设布局"""
        for i, pos in enumerate(positions):
            if i + 1 not in self.video_windows:
                self.current_window_id = i + 1
                self.x_spin.setValue(pos[0])
                self.y_spin.setValue(pos[1])
                self.width_spin.setValue(pos[2])
                self.height_spin.setValue(pos[3])
                self.open_current_window()
            else:
                window = self.video_windows[i + 1]
                window.set_position(pos[0], pos[1], pos[2], pos[3])
        
        self.log(f"已应用预设布局")
    
    # ============== 媒体列表方法 ==============
    
    def add_media_file(self):
        """添加媒体文件"""
        last_dir = self.config_manager.get_last_media_directory()
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择媒体文件",
            last_dir,
            "媒体文件 (*.mp4 *.avi *.mkv *.mov *.wmv *.flv *.webm *.mp3 *.wav *.jpg *.jpeg *.png *.bmp *.ppt *.pptx);;所有文件 (*.*)"
        )
        
        if files:
            # 保存目录
            self.config_manager.set_last_media_directory(os.path.dirname(files[0]))
            
            # 添加到当前窗口的列表
            if self.current_window_id in self.video_windows:
                window = self.video_windows[self.current_window_id]
                for file_path in files:
                    window.add_media_file(file_path)
            else:
                # 窗口未打开时，先打开窗口
                self.open_current_window()
                window = self.video_windows[self.current_window_id]
                for file_path in files:
                    window.add_media_file(file_path)
            
            # 更新显示
            self.update_media_list_display()
            
            self.log(f"已添加 {len(files)} 个文件到窗口{self.current_window_id}")
    
    def remove_selected_media(self):
        """移除选中的媒体"""
        if self.current_window_id in self.video_windows:
            current_row = self.media_list.currentRow()
            if current_row >= 0:
                window = self.video_windows[self.current_window_id]
                removed = window.remove_media_file(current_row)
                self.update_media_list_display()
                self.log(f"已移除: {os.path.basename(removed)}")
    
    def clear_media_list(self):
        """清空媒体列表"""
        if self.current_window_id in self.video_windows:
            window = self.video_windows[self.current_window_id]
            window.stop()
            window.set_media_files([])
            self.update_media_list_display()
            self.log("媒体列表已清空")
    
    def play_selected_media(self, item):
        """播放选中的媒体"""
        file_path = item.data(Qt.UserRole)
        if file_path and self.current_window_id in self.video_windows:
            self.video_windows[self.current_window_id].play(file_path)
            self.log(f"播放: {os.path.basename(file_path)}")
    
    # ============== 控制方法 ==============
    
    def on_video_window_clicked(self, window_id):
        """视频窗口被点击"""
        self.select_window(window_id)
        btn = self.window_tabs.button(window_id)
        if btn:
            btn.setChecked(True)
    
    def on_window_media_changed(self, window_id, media_files):
        """窗口媒体列表改变"""
        if window_id == self.current_window_id:
            self.update_media_list_display()
        
        # 保存配置
        if window_id in self.video_windows:
            self.config_manager.set_window_config(window_id, self.video_windows[window_id].get_config())
    
    def on_window_playback_changed(self, window_id, state):
        """窗口播放状态改变"""
        # 更新独立控制区的显示
        self.update_window_controls()
    
    def on_media_ended(self, window):
        """媒体播放结束"""
        if window.is_loop:
            window.next_media()
        else:
            window.is_playing = False
            window.status_label.setText("播放完成")
    
    # ===== 广播控制 =====
    
    def broadcast_control(self, command):
        """广播控制所有窗口"""
        for window_id, window in self.video_windows.items():
            if command == "play_all":
                if window.media_files:
                    if window.current_index < 0:
                        window.current_index = 0
                    window.play()
            elif command == "pause_all":
                window.pause()
            elif command == "stop_all":
                window.stop()
            elif command == "replay_all":
                window.replay()
            elif command == "prev_all":
                window.prev_media()
            elif command == "next_all":
                window.next_media()
        
        cmd_names = {
            "play_all": "全部播放",
            "pause_all": "全部暂停", 
            "stop_all": "全部停止",
            "replay_all": "全部重播",
            "prev_all": "全部上一个",
            "next_all": "全部下一个"
        }
        self.log(cmd_names.get(command, command))
    
    # ===== 独立窗口控制 =====
    
    def play_window(self, window_id):
        """播放指定窗口"""
        if window_id in self.video_windows:
            window = self.video_windows[window_id]
            if window.media_files:
                if window.current_index < 0:
                    window.current_index = 0
                window.play()
            self.update_window_controls()
            self.log(f"窗口{window_id}播放")
    
    def pause_window(self, window_id):
        """暂停指定窗口"""
        if window_id in self.video_windows:
            self.video_windows[window_id].pause()
            self.update_window_controls()
            self.log(f"窗口{window_id}暂停")
    
    def stop_window(self, window_id):
        """停止指定窗口"""
        if window_id in self.video_windows:
            self.video_windows[window_id].stop()
            self.update_window_controls()
            self.log(f"窗口{window_id}停止")
    
    def prev_window_media(self, window_id):
        """上一个媒体"""
        if window_id in self.video_windows:
            self.video_windows[window_id].prev_media()
    
    def next_window_media(self, window_id):
        """下一个媒体"""
        if window_id in self.video_windows:
            self.video_windows[window_id].next_media()
    
    # ===== 音量控制 =====
    
    def on_volume_changed(self, value):
        """音量改变"""
        self.volume_label.setText(f"{value}%")
        self.config_manager.set_global_volume(value)
        
        for window in self.video_windows.values():
            window.set_volume(value)
    
    def toggle_mute(self):
        """切换静音"""
        is_muted = False
        for window in self.video_windows.values():
            is_muted = window.toggle_mute()
        
        self.mute_btn.setText("🔇 取消静音" if is_muted else "🔊 静音")
        self.log("已切换静音状态")
    
    # ===== 网络控制 =====
    
    def on_udp_message(self, message, addr, port):
        """UDP消息接收"""
        self.log(f"UDP[{port}] <- {addr}: {message}")
        self.parse_network_command(message)
    
    def on_tcp_message(self, message, addr, port):
        """TCP消息接收"""
        self.log(f"TCP[{port}] <- {addr}: {message}")
        self.parse_network_command(message)
    
    def parse_network_command(self, command):
        """解析网络命令"""
        command = command.strip()
        
        # 格式: windowid_command 或 windowid:command
        parts = re.split(r'[_,:]', command)
        if len(parts) >= 2 and parts[0].isdigit():
            window_id = int(parts[0])
            cmd = parts[1].lower()
        else:
            window_id = self.current_window_id
            cmd = command.lower()
        
        self.execute_command(cmd, window_id)
    
    def execute_command(self, command, window_id):
        """执行命令"""
        if window_id == 0:
            # 广播到所有窗口
            for wid, window in self.video_windows.items():
                self.execute_single_command(window, command)
        elif window_id in self.video_windows:
            self.execute_single_command(self.video_windows[window_id], command)
    
    def execute_single_command(self, window, command):
        """执行单个命令"""
        cmd = command.lower()
        if cmd == "play":
            if window.media_files:
                if window.current_index < 0:
                    window.current_index = 0
                window.play()
        elif cmd == "pause":
            window.pause()
        elif cmd == "stop":
            window.stop()
        elif cmd == "replay":
            window.replay()
        elif cmd == "next":
            window.next_media()
        elif cmd == "prev":
            window.prev_media()
        elif cmd == "mute":
            if not window.is_muted:
                window.toggle_mute()
        elif cmd == "unmute":
            if window.is_muted:
                window.toggle_mute()
    
    def broadcast_network_command(self, command):
        """广播网络命令"""
        target_ip = self.target_ip_edit.text()
        
        port = self.udp_port_spin.value()
        self.network_manager.send_udp(command, target_ip, port)
        self.log(f"UDP广播 -> {target_ip}:{port}: {command}")
    
    def send_custom_command(self, protocol):
        """发送自定义命令"""
        command = self.custom_cmd_edit.text().strip()
        if not command:
            return
        
        target_ip = self.target_ip_edit.text()
        
        if protocol == "udp":
            port = self.udp_port_spin.value()
            self.network_manager.send_udp(command, target_ip, port)
            self.log(f"UDP发送 -> {target_ip}:{port}: {command}")
        else:
            port = self.tcp_port_spin.value()
            self.network_manager.send_tcp(command, target_ip, port)
            self.log(f"TCP发送 -> {target_ip}:{port}: {command}")
    
    def send_to_specific_window(self):
        """发送到指定窗口"""
        window_id = self.manual_window_spin.value()
        command = self.manual_cmd_combo.currentText()
        self.execute_command(command, window_id)
        self.log(f"窗口{window_id}执行: {command}")
    
    # ===== 串口控制 =====
    
    def update_serial_ports(self):
        """更新串口列表"""
        self.serial_port_combo.clear()
        
        if SERIAL_AVAILABLE:
            ports = serial.tools.list_ports.comports()
            for port in ports:
                self.serial_port_combo.addItem(port.device)
        else:
            self.serial_port_combo.addItem("串口不可用")
    
    def toggle_serial_connection(self):
        """切换串口连接"""
        if self.serial_manager.is_connected():
            self.serial_manager.disconnect()
            self.serial_connect_btn.setText("连接串口")
            self.log("串口已断开")
        else:
            port = self.serial_port_combo.currentText()
            if port and port != "串口不可用":
                self.serial_manager.configure(port)
                if self.serial_manager.connect():
                    self.serial_connect_btn.setText("断开串口")
                    self.log(f"串口已连接: {port}")
                else:
                    self.log(f"串口连接失败: {port}")
    
    def on_serial_data(self, data):
        """串口数据接收"""
        self.log(f"串口 <- {data}")
        self.parse_network_command(data)
    
    # ===== 系统方法 =====
    
    def show_main_window(self):
        """显示主窗口"""
        self.show()
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.is_minimized_to_tray = False
    
    def hide_to_tray(self):
        """隐藏到托盘"""
        self.hide()
        self.is_minimized_to_tray = True
    
    def on_tray_activated(self, reason):
        """托盘图标激活"""
        if reason == QSystemTrayIcon.Trigger:
            self.show_main_window()
    
    def save_config_now(self):
        """立即保存配置"""
        # 保存所有窗口配置
        for window_id, window in self.video_windows.items():
            self.config_manager.set_window_config(window_id, window.get_config())
        
        # 保存主窗口几何
        self.config_manager.set_main_window_geometry({
            "x": self.x(),
            "y": self.y(),
            "width": self.width(),
            "height": self.height()
        })
        
        # 保存设置
        self.config_manager.config["auto_play_on_open"] = self.auto_play_checkbox.isChecked()
        self.config_manager.config["loop_playback"] = self.loop_playback_checkbox.isChecked()
        
        self.config_manager.save_config_immediately()
        self.log("配置已保存")
    
    def log(self, message):
        """记录日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
        self.statusBar().showMessage(message, 3000)
    
    def closeEvent(self, event):
        """关闭事件"""
        reply = QMessageBox.question(
            self,
            "确认退出",
            "确定要退出程序吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # 保存配置
            self.save_config_now()
            
            # 关闭所有视频窗口
            for window in list(self.video_windows.values()):
                window.close()
            
            # 停止网络和串口
            self.network_manager.stop_network()
            if self.serial_manager.is_connected():
                self.serial_manager.disconnect()
            
            # 关闭托盘图标
            self.tray_icon.hide()
            
            event.accept()
        else:
            event.ignore()
    
    def quit_application(self):
        """退出应用"""
        self.save_config_now()
        
        for window in list(self.video_windows.values()):
            window.close()
        
        self.network_manager.stop_network()
        if self.serial_manager.is_connected():
            self.serial_manager.disconnect()
        
        self.tray_icon.hide()
        
        QApplication.quit()


# ============== 程序入口 ==============

def main():
    # 启用高DPI支持
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(COMPANY_NAME)
    
    # 设置应用图标
    try:
        app.setWindowIcon(QIcon.fromTheme("media-player"))
    except:
        pass
    
    # 创建并显示主窗口
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

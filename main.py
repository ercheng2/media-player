# -*- coding: utf-8 -*-
"""
坤展成-中控多窗口播放器
开发公司：北京万乘兄弟科技有限公司
联系方式：18210234280
版本：v2.42 - PPT后台加载+循环播放修复+点击防抖
"""

import sys
import os
import uuid
import platform

# Linux下设置VLC插件路径，确保root用户也能使用VLC
if not os.environ.get('VLC_PLUGIN_PATH') and platform.system() == 'Linux':
    os.environ['VLC_PLUGIN_PATH'] = '/usr/lib/x86_64-linux-gnu/vlc/plugins/'

# PyInstaller打包后设置VLC路径（必须在import vlc之前）
# 注意：python-vlc如果PYTHON_VLC_LIB_PATH指向不存在的文件会sys.exit(1)直接退出！
if getattr(sys, 'frozen', False):
    bundle_dir = sys._MEIPASS
    # 查找libvlc.dll - 优先_MEIPASS/vlc/，然后exe同级vlc/，然后系统VLC
    _vlc_dll_candidates = [
        os.path.join(bundle_dir, 'vlc', 'libvlc.dll'),
        os.path.join(bundle_dir, 'libvlc.dll'),
    ]
    if platform.system() == 'Windows':
        exe_dir = os.path.dirname(sys.executable)
        _vlc_dll_candidates.extend([
            os.path.join(exe_dir, 'vlc', 'libvlc.dll'),
            os.path.join(exe_dir, 'libvlc.dll'),
            r'C:\Program Files\VideoLAN\VLC\libvlc.dll',
        ])
    
    _vlc_dll_found = None
    for _p in _vlc_dll_candidates:
        if os.path.exists(_p):
            _vlc_dll_found = _p
            print(f"找到VLC DLL: {_p}")
            break
    
    if _vlc_dll_found:
        # 设置python-vlc需要的环境变量（只有文件确实存在才设置！）
        os.environ['PYTHON_VLC_LIB_PATH'] = _vlc_dll_found
        _vlc_dir = os.path.dirname(_vlc_dll_found)
        os.environ['PYTHON_VLC_MODULE_PATH'] = _vlc_dir
        os.environ['PATH'] = _vlc_dir + os.pathsep + os.environ.get('PATH', '')
        if hasattr(os, 'add_dll_directory'):
            try:
                os.add_dll_directory(_vlc_dir)
            except:
                pass
    else:
        print("未找到VLC DLL，将使用QMediaPlayer内置播放器")

import socket
import struct
import threading
import time
import hashlib
import json
import base64
import re
from datetime import datetime, timedelta
import ctypes
if platform.system() == 'Windows':
    from ctypes import windll, c_void_p, c_int, byref, Structure, POINTER
    import ctypes.wintypes as wintypes
else:
    windll = None
    from ctypes import c_void_p, c_int, byref, Structure, POINTER
    wintypes = None

# PyQt5 导入
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QTextEdit, QLineEdit,
    QSlider, QCheckBox, QComboBox, QGroupBox, QFrame, QDialog,
    QSpinBox, QDoubleSpinBox, QButtonGroup, QRadioButton, QTabWidget,
    QMessageBox, QSystemTrayIcon, QMenu, QAction, QFileDialog,
    QListWidget, QListWidgetItem, QStyle, QProgressBar, QSplitter,
    QToolButton, QScrollArea, QSizePolicy, QDesktopWidget,
    QTableWidget, QTableWidgetItem, QHeaderView
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
from PyQt5.QtMultimediaWidgets import QVideoWidget
from PyQt5.QtNetwork import QUdpSocket, QTcpSocket, QTcpServer, QHostAddress

# 尝试导入VLC
VLC_AVAILABLE = False
try:
    import vlc
    VLC_AVAILABLE = True
    print("VLC模块导入成功")
except SystemExit:
    # python-vlc在找不到DLL时会sys.exit(1)，这里拦截
    VLC_AVAILABLE = False
    print("警告: VLC库加载失败(sys.exit)，将使用PyQt5内置播放器")
except Exception as e:
    VLC_AVAILABLE = False
    print(f"警告: VLC库未安装({e})，将使用PyQt5内置播放器")

# 环境变量NO_VLC=1可强制禁用VLC，用于排查问题
if os.environ.get('NO_VLC') == '1':
    VLC_AVAILABLE = False
    print("NO_VLC=1，已强制禁用VLC，使用QMediaPlayer")

# Linux下强制使用VLC（QMediaPlayer在Linux上GStreamer有问题）
if platform.system() == 'Linux' and not VLC_AVAILABLE:
    print("警告: Linux下强烈建议安装VLC，QMediaPlayer可能无法正常播放视频")

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
APP_VERSION = "v2.36"
COMPANY_NAME = "北京万乘兄弟科技有限公司"
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


def get_resource_path(relative_path):
    """获取资源文件的绝对路径，兼容PyInstaller打包"""
    if getattr(sys, 'frozen', False):
        # PyInstaller打包后的路径
        base_path = sys._MEIPASS
    else:
        # 开发环境路径
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


def get_config_path(filename):
    """获取配置文件的绝对路径，兼容PyInstaller打包"""
    if getattr(sys, 'frozen', False):
        # 打包后，配置放在exe同级目录
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, filename)


# ============== 配置管理类 ==============

class ConfigManager:
    """配置管理类 - 启动时加载，退出时保存"""
    
    def __init__(self):
        # 使用正确的配置文件路径（兼容打包后）
        self.config_file = get_config_path(CONFIG_FILE)
        self.config = self._get_default_config()
        
    def _get_default_config(self):
        """获取默认配置"""
        return {
            "main_window": {
                "x": 100, "y": 100, "width": 1100, "height": 800
            },
            "global_volume": 80,
            "windows": {}  # 各窗口的独立配置
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
        return self.config.get("main_window", {})
    
    def set_main_window_geometry(self, x, y, width, height):
        """设置主窗口几何信息"""
        self.config["main_window"] = {"x": x, "y": y, "width": width, "height": height}
    
    def get_global_volume(self):
        """获取全局音量"""
        return self.config.get("global_volume", 80)
    
    def set_global_volume(self, volume):
        """设置全局音量"""
        self.config["global_volume"] = volume
    
    def get_window_media_files(self, window_id):
        """获取指定窗口的媒体文件列表"""
        return self.config.get("windows", {}).get(str(window_id), {}).get("media_files", [])
    
    def set_window_media_files(self, window_id, media_files):
        """设置指定窗口的媒体文件列表"""
        if "windows" not in self.config:
            self.config["windows"] = {}
        if str(window_id) not in self.config["windows"]:
            self.config["windows"][str(window_id)] = {}
        self.config["windows"][str(window_id)]["media_files"] = media_files
    
    def get_window_position(self, window_id):
        """获取窗口位置"""
        return self.config.get("windows", {}).get(str(window_id), {}).get("position", {"x": 100, "y": 100, "width": 800, "height": 600})
    
    def set_window_position(self, window_id, x, y, width, height):
        """设置窗口位置"""
        if "windows" not in self.config:
            self.config["windows"] = {}
        if str(window_id) not in self.config["windows"]:
            self.config["windows"][str(window_id)] = {}
        self.config["windows"][str(window_id)]["position"] = {"x": x, "y": y, "width": width, "height": height}
    
    def get_window_auto_open(self, window_id):
        """获取窗口是否自动打开"""
        return self.config.get("windows", {}).get(str(window_id), {}).get("auto_open", False)
    
    def set_window_auto_open(self, window_id, auto_open):
        """设置窗口是否自动打开"""
        if "windows" not in self.config:
            self.config["windows"] = {}
        if str(window_id) not in self.config["windows"]:
            self.config["windows"][str(window_id)] = {}
        self.config["windows"][str(window_id)]["auto_open"] = auto_open
    
    def get_window_is_open(self, window_id):
        """获取窗口是否打开状态（记忆还原用）"""
        return self.config.get("windows", {}).get(str(window_id), {}).get("is_open", False)
    
    def set_window_is_open(self, window_id, is_open):
        """设置窗口是否打开状态"""
        if "windows" not in self.config:
            self.config["windows"] = {}
        if str(window_id) not in self.config["windows"]:
            self.config["windows"][str(window_id)] = {}
        self.config["windows"][str(window_id)]["is_open"] = is_open
    
    def get_minimize_to_tray(self):
        """获取是否启动时最小化到托盘"""
        return self.config.get("minimize_to_tray", False)
    
    def set_minimize_to_tray(self, minimize):
        """设置是否启动时最小化到托盘"""
        self.config["minimize_to_tray"] = minimize
    
    def get_window_default_media(self, window_id):
        """获取窗口默认播放的媒体"""
        return self.config.get("windows", {}).get(str(window_id), {}).get("default_media", "")
    
    def get_window_default_loop(self, window_id):
        """获取窗口默认播放是否循环（兼容旧配置）"""
        return self.config.get("windows", {}).get(str(window_id), {}).get("default_loop", False)
    
    def set_window_default_loop(self, window_id, loop):
        """设置窗口默认播放是否循环（兼容旧配置）"""
        if "windows" not in self.config:
            self.config["windows"] = {}
        if str(window_id) not in self.config["windows"]:
            self.config["windows"][str(window_id)] = {}
        self.config["windows"][str(window_id)]["default_loop"] = loop
    
    def get_media_settings(self, window_id):
        """获取窗口下所有媒体的设置 {idx: {default: bool, loop: bool}}"""
        return self.config.get("windows", {}).get(str(window_id), {}).get("media_settings", {})
    
    def set_media_settings(self, window_id, settings):
        """设置窗口下所有媒体的设置"""
        if "windows" not in self.config:
            self.config["windows"] = {}
        if str(window_id) not in self.config["windows"]:
            self.config["windows"][str(window_id)] = {}
        self.config["windows"][str(window_id)]["media_settings"] = settings
    
    def get_media_item_setting(self, window_id, media_idx):
        """获取单个媒体的设置"""
        settings = self.get_media_settings(window_id)
        return settings.get(str(media_idx), {"default": False, "loop": False})
    
    def set_media_item_setting(self, window_id, media_idx, key, value):
        """设置单个媒体的某项配置 (key: default/loop)"""
        settings = self.get_media_settings(window_id)
        idx_key = str(media_idx)
        if idx_key not in settings:
            settings[idx_key] = {"default": False, "loop": False}
        # 如果设为默认，清除其他项的默认
        if key == "default" and value:
            for k in settings:
                settings[k]["default"] = False
        settings[idx_key][key] = value
        self.set_media_settings(window_id, settings)
    
    def set_window_default_media(self, window_id, media_path):
        """设置窗口默认播放的媒体"""
        if "windows" not in self.config:
            self.config["windows"] = {}
        if str(window_id) not in self.config["windows"]:
            self.config["windows"][str(window_id)] = {}
        self.config["windows"][str(window_id)]["default_media"] = media_path


# ============== 机器码和授权管理 ==============

class LicenseManager:
    """授权管理类"""
    
    @staticmethod
    def get_machine_code():
        """获取机器码 - 基于硬件信息生成"""
        try:
            # 获取CPU ID
            cpu_id = LicenseManager._get_cpu_id()
            # 获取磁盘序列号
            disk_serial = LicenseManager._get_disk_serial()
            # 获取MAC地址
            mac = LicenseManager._get_mac_address()
            
            # 组合并生成机器码
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
            # 使用NTP服务器获取时间
            import socket
            NTP_SERVER = "time.windows.com"
            NTP_PORT = 123
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(5)
            
            # NTP时间戳
            ntp_packet = b'\x1b' + 47 * b'\0'
            sock.sendto(ntp_packet, (NTP_SERVER, NTP_PORT))
            response = sock.recv(48)
            sock.close()
            
            # 解析时间戳
            timestamp = struct.unpack('!I', response[40:44])[0]
            timestamp -= 2208988800  # 转换为Unix时间戳
            return datetime.fromtimestamp(timestamp)
        except Exception as e:
            print(f"获取网络时间失败: {e}")
            return datetime.now()  # 失败时返回本地时间
    
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
            # 授权码格式: BASE64(MD5(机器码 + 盐值))
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
        # 生成可读格式 XXXX-XXXX-XXXX-XXXX
        return '-'.join([key[i:i+4] for i in range(0, 16, 4)])
    
    @staticmethod
    def check_license_status():
        """检查授权状态"""
        license_key = LicenseManager.load_license()
        
        if license_key:
            valid, msg = LicenseManager.verify_license(license_key)
            if valid:
                return True, "已授权", None
        
        # 获取网络时间作为试用期开始
        start_time = LicenseManager.get_network_time()
        expire_time = start_time + timedelta(days=TRIAL_DAYS)
        remaining = (expire_time - start_time).days
        
        return False, "试用版", remaining


# ============== 视频播放器窗口 ==============

class VideoWindow(QFrame):
    """无边框视频播放窗口"""
    
    # 信号定义
    clicked = pyqtSignal(int)  # 点击信号，携带窗口编号
    window_closed = pyqtSignal(int)  # 窗口关闭信号，携带窗口编号
    
    # 类变量：跟踪当前正在拖拽的窗口
    _dragging_window = None
    
    def __init__(self, window_id, parent=None):
        super().__init__(parent)
        self.window_id = window_id
        self.is_locked = False
        self.is_visible = True
        self.media_files = []
        self.current_index = -1
        self.is_playing = False
        self.volume = 80
        self.is_muted = False
        self.loop_play = False  # 循环播放标志
        
        # 初始化UI
        self.init_ui()
        
        # 初始化播放器
        self.init_player()
        
        # 拖拽相关 - Windows用定时器+API方案，Linux用Qt原生鼠标事件
        self.drag_position = None
        self.is_dragging = False
        self.click_detected = False  # 用于Linux下区分拖动和点击
        # Windows专用
        self.last_left_down = False
        self.click_pending = False  # 标记是否需要触发clicked信号
        if platform.system() == 'Windows':
            self.drag_timer = QTimer(self)
            self.drag_timer.timeout.connect(self.check_drag)
            self.drag_timer.start(50)  # 20fps，够用且不堵主线程
        
    def check_drag(self):
        """定时器检查鼠标状态，实现窗口拖拽
        
        不依赖Qt事件系统，直接用Windows API检测鼠标按键和位置。
        使用GetCursorPos替代QCursor.pos()，更稳定。
        用geometry()替代frameGeometry()，无边框窗口更准确。
        """
        if platform.system() != 'Windows' or not self.isVisible() or windll is None:
            return
        
        try:
            # 如果其他窗口正在拖拽，跳过
            if VideoWindow._dragging_window is not None and VideoWindow._dragging_window != self:
                return
            
            # 获取鼠标左键状态
            left_down = windll.user32.GetAsyncKeyState(1) & 0x8000
            
            # 用Windows API获取鼠标位置，比QCursor更可靠
            class POINT(Structure):
                _fields_ = [("x", c_int), ("y", c_int)]
            pt = POINT()
            windll.user32.GetCursorPos(byref(pt))
            mx, my = pt.x, pt.y
            
            # 检查鼠标是否在窗口内（用geometry，无边框窗口更准确）
            geo = self.geometry()
            in_window = (geo.x() <= mx < geo.x() + geo.width() and 
                        geo.y() <= my < geo.y() + geo.height())
            
            if left_down and not self.last_left_down:
                # 鼠标按下
                if in_window:
                    if not self.click_pending:
                        self.click_pending = True
                        self.clicked.emit(self.window_id)
                    if not self.is_locked:
                        from PyQt5.QtCore import QPoint
                        self.drag_position = QPoint(mx - geo.x(), my - geo.y())
                        self.is_dragging = True
                        VideoWindow._dragging_window = self
            elif not left_down and self.last_left_down:
                # 鼠标释放
                self.is_dragging = False
                self.drag_position = None
                self.click_pending = False
                if VideoWindow._dragging_window == self:
                    VideoWindow._dragging_window = None
            elif left_down and self.is_dragging and not self.is_locked:
                # 拖动中
                if self.drag_position:
                    from PyQt5.QtCore import QPoint
                    self.move(QPoint(mx - self.drag_position.x(), my - self.drag_position.y()))
            
            self.last_left_down = left_down
        except:
            self.is_dragging = False
            self.drag_position = None
            self.last_left_down = False
            self.click_pending = False
            if VideoWindow._dragging_window == self:
                VideoWindow._dragging_window = None
    
    # Linux下使用Qt原生鼠标事件处理窗口拖动
    if platform.system() != 'Windows':
        def mousePressEvent(self, event):
            """Linux下鼠标按下事件"""
            if event.button() == Qt.LeftButton and not self.is_locked:
                self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
                self.is_dragging = True
                self.click_detected = False
                VideoWindow._dragging_window = self
                event.accept()
            else:
                super().mousePressEvent(event)
        
        def mouseMoveEvent(self, event):
            """Linux下鼠标移动事件"""
            if event.buttons() == Qt.LeftButton and self.is_dragging and not self.is_locked:
                if self.drag_position:
                    self.click_detected = True  # 有移动就不是点击
                    self.move(event.globalPos() - self.drag_position)
                    event.accept()
            else:
                super().mouseMoveEvent(event)
        
        def mouseReleaseEvent(self, event):
            """Linux下鼠标释放事件"""
            if event.button() == Qt.LeftButton:
                self.is_dragging = False
                self.drag_position = None
                if VideoWindow._dragging_window == self:
                    VideoWindow._dragging_window = None
                # 如果没有拖动过，算作点击
                if not self.click_detected:
                    self.clicked.emit(self.window_id)
                self.click_detected = False
                event.accept()
            else:
                super().mouseReleaseEvent(event)
        
        def wheelEvent(self, event):
            """Linux下鼠标滚轮事件（用于音量控制等）"""
            # 暂不处理，保持原有行为
            super().wheelEvent(event)
    
    def init_ui(self):
        """初始化UI"""
        self.setWindowFlags(
            Qt.Window | 
            Qt.FramelessWindowHint | 
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setStyleSheet("""
            VideoWindow {
                background-color: black;
                border: none;
            }
        """)
        
        # 创建视频容器（VLC渲染到这个控件上）
        self.video_frame = QWidget(self)
        self.video_frame.setStyleSheet("background-color: black;")
        self.video_frame.setGeometry(0, 0, 800, 600)
        self.video_frame.show()
        
        # 图片显示标签（覆盖在video_frame上方，用于显示图片文件）
        self.image_label = QLabel(self)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background-color: black;")
        self.image_label.setGeometry(0, 0, 800, 600)
        self.image_label.hide()
        
        # 窗口编号标签（在视频上方）
        self.label_id = QLabel(f"窗口{self.window_id}", self)
        self.label_id.setStyleSheet("""
            QLabel {
                background-color: rgba(0, 0, 0, 150);
                color: white;
                padding: 5px 10px;
                border-radius: 3px;
                font-size: 14px;
            }
        """)
        self.label_id.move(10, 10)
        self.label_id.raise_()  # 确保在最上层
        self.label_id.show()
        
        # 设置初始大小和位置
        self.resize(800, 600)
        
        # 启用鼠标追踪，确保能接收鼠标事件
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
    
    def resizeEvent(self, event):
        """窗口大小改变时更新视频容器和图片标签尺寸"""
        super().resizeEvent(event)
        if hasattr(self, 'video_frame'):
            self.video_frame.setGeometry(0, 0, self.width(), self.height())
        # QVideoWidget同步大小
        if hasattr(self, 'video_widget') and not self.use_vlc:
            self.video_widget.setGeometry(0, 0, self.width(), self.height())
        if hasattr(self, 'image_label'):
            self.image_label.setGeometry(0, 0, self.width(), self.height())
            # 如果图片正在显示，重新缩放图片
            if self.image_label.isVisible() and hasattr(self, '_current_image_path'):
                pixmap = QPixmap(self._current_image_path)
                if not pixmap.isNull():
                    self.image_label.setPixmap(pixmap.scaled(self.width(), self.height(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
        # 更新VLC视频拉伸
        if hasattr(self, 'vlc_player') and self.use_vlc and self.is_playing:
            try:
                self._safe_set_vlc_stretch()
            except:
                pass
        
    def init_player(self):
        """初始化播放器"""
        if VLC_AVAILABLE:
            # VLC播放器
            try:
                if platform.system() == 'Linux':
                    self.vlc_instance = vlc.Instance('--no-video-title-show --vout xcb_x11 --avcodec-hw=none')
                else:
                    self.vlc_instance = vlc.Instance('--no-video-title-show --no-overlay')
                self.vlc_player = self.vlc_instance.media_player_new()
                # 渲染窗口句柄延迟到showEvent中设置，避免窗口未show时winId无效
                self._vlc_hwnd_set = False
                self.use_vlc = True
                
                # 设置VLC事件管理器，监听播放结束事件
                self.vlc_events = self.vlc_player.event_manager()
                self.vlc_events.event_attach(vlc.EventType.MediaPlayerEndReached, self._on_vlc_end_reached)
            except Exception as e:
                print(f"VLC初始化失败，回退到QMediaPlayer: {e}")
                self.use_vlc = False
        else:
            self.use_vlc = False
        
        if not self.use_vlc:
            # PyQt5播放器 - 使用QVideoWidget作为视频输出
            # 直接放在VideoWindow上（不是video_frame），用setGeometry铺满
            self.video_widget = QVideoWidget(self)
            self.video_widget.setStyleSheet("background-color: black;")
            self.video_widget.setAspectRatioMode(Qt.IgnoreAspectRatio)  # 拉伸铺满窗口
            self.video_widget.setGeometry(0, 0, self.width(), self.height())
            self.video_widget.show()
            self.video_widget.lower()  # 置于底层，让label_id在上方
            
            self.media_player = QMediaPlayer()
            self.media_player.setVideoOutput(self.video_widget)
            self.media_player.stateChanged.connect(self._on_qt_state_changed)
            self.use_vlc = False
        
    def showEvent(self, event):
        """窗口显示事件 - 延迟设置VLC渲染窗口句柄"""
        super().showEvent(event)
        # 首次show时设置VLC窗口句柄（需要有效winId）
        if hasattr(self, 'vlc_player') and self.use_vlc and not self._vlc_hwnd_set:
            try:
                if platform.system() == 'Linux':
                    self.vlc_player.set_xwindow(int(self.video_frame.winId()))
                else:
                    self.vlc_player.set_hwnd(int(self.video_frame.winId()))
                self._vlc_hwnd_set = True
                print(f"VLC窗口句柄已设置: {self.video_frame.winId()}")
            except Exception as e:
                print(f"设置VLC窗口句柄失败: {e}")
    
    def set_position(self, x, y, width, height):
        """设置窗口位置和大小"""
        self.move(int(x), int(y))
        self.resize(int(width), int(height))
    
    def _on_vlc_end_reached(self, event):
        """VLC播放结束回调"""
        if self.loop_play:
            # 循环播放：直接回开头重播，不修改is_playing
            QTimer.singleShot(300, self._loop_replay)
        else:
            self.is_playing = False
    
    def _on_qt_state_changed(self, state):
        """Qt播放器状态改变回调"""
        from PyQt5.QtMultimedia import QMediaPlayer
        if state == QMediaPlayer.StoppedState and self.loop_play:
            QTimer.singleShot(100, self._loop_replay)
        elif state == QMediaPlayer.StoppedState:
            self.is_playing = False
    
    def _force_video_stretch(self):
        """Linux下强制视频铺满窗口 - 通过resize触发GStreamer重新布局"""
        if not self.use_vlc and hasattr(self, 'video_widget'):
            # 微调尺寸触发GStreamer重新计算渲染区域
            w, h = self.width(), self.height()
            self.video_widget.setGeometry(0, 0, w, h - 1)
            QTimer.singleShot(50, lambda: self.video_widget.setGeometry(0, 0, self.width(), self.height()))
    
    def toggle_loop(self):
        """切换循环播放"""
        self.loop_play = not self.loop_play
        return self.loop_play
    
    def _loop_replay(self):
        """循环播放重播 - 用set_time/setPosition回到开头，避免stop+play状态冲突"""
        try:
            if self.use_vlc:
                # VLC: 直接设回起点播放，不stop
                self.vlc_player.set_time(0)
                self.vlc_player.play()
                QTimer.singleShot(300, self._safe_apply_volume)
                QTimer.singleShot(500, self._safe_set_vlc_stretch)
            else:
                # QMediaPlayer: setPosition回到开头
                from PyQt5.QtCore import QUrl
                from PyQt5.QtMultimedia import QMediaContent
                self.media_player.setPosition(0)
                self.media_player.play()
        except Exception as e:
            print(f"循环重播失败，fallback到replay: {e}")
            self.replay()
        
    def set_media_files(self, files):
        """设置媒体文件列表"""
        self.media_files = files
        self.current_index = -1
        
    def add_media_file(self, file_path):
        """添加媒体文件"""
        if file_path not in self.media_files:
            self.media_files.append(file_path)
            return True
        return False
    
    def play(self, file_path=None):
        """播放视频或显示图片"""
        if file_path is None:
            if self.current_index >= 0 and self.current_index < len(self.media_files):
                file_path = self.media_files[self.current_index]
            else:
                return False
        else:
            # 如果指定了文件，先找到索引
            if file_path in self.media_files:
                self.current_index = self.media_files.index(file_path)
        
        if not os.path.exists(file_path):
            print(f"文件不存在: {file_path}")
            return False
        
        # 根据文件扩展名判断媒体类型
        ext = os.path.splitext(file_path)[1].lower()
        image_exts = ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp']
        video_exts = ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.ts', '.m3u8', '.3gp', '.rm', '.rmvb']
        
        try:
            # 处理图片文件
            if ext in image_exts:
                return self._show_image(file_path)
            
            # 处理PPT文件
            if ext in ['.ppt', '.pptx']:
                return self._show_ppt(file_path)
            
            # 处理视频文件
            # 隐藏图片标签，显示视频容器
            self.image_label.hide()
            self.video_frame.show()
            # 非VLC模式，显示QVideoWidget并置底层
            if hasattr(self, 'video_widget') and not self.use_vlc:
                self.video_widget.show()
                self.video_widget.setGeometry(0, 0, self.width(), self.height())
                self.video_widget.lower()
            
            if self.use_vlc:
                # 先停止当前播放
                try:
                    self.vlc_player.stop()
                except:
                    pass
                
                # 确保VLC窗口句柄已设置
                if hasattr(self, '_vlc_hwnd_set') and not self._vlc_hwnd_set:
                    try:
                        if platform.system() == 'Linux':
                            self.vlc_player.set_xwindow(int(self.video_frame.winId()))
                        else:
                            self.vlc_player.set_hwnd(int(self.video_frame.winId()))
                        self._vlc_hwnd_set = True
                    except Exception as e:
                        print(f"播放时设置VLC窗口句柄失败: {e}")
                
                media = self.vlc_instance.media_new(file_path)
                # 添加选项让视频拉伸填充窗口
                media.add_option(':no-keep-aspect-ratio')
                self.vlc_player.set_media(media)
                self.vlc_player.play()
                
                # 立即设置音量（VLC需要播放后才能设置音量）
                self.is_playing = True
                
                # 多次设置拉伸确保生效（VLC需要视频渲染后才能设置aspect ratio）
                QTimer.singleShot(200, lambda: self._safe_set_vlc_stretch())
                QTimer.singleShot(500, lambda: self._safe_set_vlc_stretch())
                QTimer.singleShot(1000, lambda: self._safe_set_vlc_stretch())
                QTimer.singleShot(300, lambda: self._safe_apply_volume())
            else:
                # QMediaPlayer模式
                self.media_player.setMedia(QMediaContent(QUrl.fromLocalFile(file_path)))
                self.media_player.play()
                self.is_playing = True
                # Linux下GStreamer切换视频后不铺满，延迟强制resize触发重新布局
                if platform.system() == 'Linux' and hasattr(self, 'video_widget'):
                    QTimer.singleShot(100, self._force_video_stretch)
                    QTimer.singleShot(500, self._force_video_stretch)
            return True
        except Exception as e:
            print(f"播放失败: {e}")
            return False
    
    def _show_image(self, file_path):
        """显示图片文件"""
        # 停止视频播放
        try:
            if self.use_vlc:
                self.vlc_player.stop()
            else:
                self.media_player.stop()
        except:
            pass
        
        # 加载并显示图片
        pixmap = QPixmap(file_path)
        if pixmap.isNull():
            print(f"无法加载图片: {file_path}")
            return False
        
        # 保存当前图片路径用于窗口缩放时重新显示
        self._current_image_path = file_path
        
        # 缩放图片以适应窗口
        scaled_pixmap = pixmap.scaled(self.width(), self.height(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        self.image_label.setPixmap(scaled_pixmap)
        self.image_label.show()
        self.video_frame.hide()
        # 非VLC模式下，隐藏QVideoWidget避免遮挡图片
        if hasattr(self, 'video_widget') and not self.use_vlc:
            self.video_widget.hide()
        self.is_playing = True
        return True
    

    def _convert_ppt_to_images(self, ppt_path):
        """将PPT转换为图片列表，返回图片路径列表"""
        import hashlib
        import subprocess
        import fitz
        
        # 生成缓存目录
        file_hash = hashlib.md5(open(ppt_path, 'rb').read()).hexdigest()[:8]
        cache_dir = f"/tmp/ppt_slides/{file_hash}"
        
        # 如果已有缓存，直接返回
        if os.path.exists(cache_dir) and os.listdir(cache_dir):
            images = sorted([os.path.join(cache_dir, f) for f in os.listdir(cache_dir) if f.endswith('.png')])
            if images:
                return images
        
        os.makedirs(cache_dir, exist_ok=True)
        
        # Windows优先用PowerPoint COM自动化
        if platform.system() == 'Windows':
            images = self._convert_ppt_with_comtypes(ppt_path, cache_dir)
            if images is not None:
                return images
        
        # 回退到LibreOffice方案
        return self._convert_ppt_with_libreoffice(ppt_path, cache_dir)
    
    def _convert_ppt_with_comtypes(self, ppt_path, cache_dir):
        """Windows下用PowerPoint COM转换PPT为图片"""
        try:
            import comtypes.client
            import pythoncom
            pythoncom.CoInitialize()
            
            powerpoint = comtypes.client.CreateObject("PowerPoint.Application")
            powerpoint.Visible = False
            
            presentation = powerpoint.Presentations.Open(
                os.path.abspath(ppt_path),
                WithWindow=False
            )
            
            # 导出为PNG图片
            export_path = os.path.abspath(cache_dir)
            presentation.Export(export_path, "PNG")
            presentation.Close()
            powerpoint.Quit()
            
            pythoncom.CoUninitialize()
            
            # 收集导出的图片
            images = sorted([os.path.join(cache_dir, f) for f in os.listdir(cache_dir) if f.lower().endswith('.png')])
            return images if images else None
            
        except ImportError:
            print("comtypes未安装，跳过PowerPoint COM方案")
            return None
        except Exception as e:
            print(f"PowerPoint COM转换失败: {e}")
            try:
                pythoncom.CoUninitialize()
            except:
                pass
            return None
    
    def _convert_ppt_with_libreoffice(self, ppt_path, cache_dir):
        """LibreOffice方案转换PPT"""
        import subprocess
        import fitz
        
        # 检查LibreOffice
        soffice = None
        if platform.system() == 'Windows':
            win_paths = [
                r'C:\Program Files\LibreOffice\program\soffice.exe',
                r'C:\Program Files (x86)\LibreOffice\program\soffice.exe',
            ]
            for wp in win_paths:
                if os.path.exists(wp):
                    soffice = wp
                    break
        else:
            for cmd in ['libreoffice', 'soffice']:
                result = subprocess.run(['which', cmd], capture_output=True, text=True)
                if result.returncode == 0:
                    soffice = cmd.strip()
                    break
        
        if not soffice:
            return None  # 没有LibreOffice
        
        # PPT → PDF（加--norestore避免锁文件卡死，超时30秒）
        try:
            subprocess.run([soffice, '--headless', '--norestore', '--convert-to', 'pdf', 
                           ppt_path, '--outdir', cache_dir], 
                           capture_output=True, timeout=30)
        except subprocess.TimeoutExpired:
            print("PPT转PDF超时（30秒）")
            return None
        except Exception as e:
            print(f"PPT转PDF失败: {e}")
            return None
        
        # 找到生成的PDF
        pdf_files = [f for f in os.listdir(cache_dir) if f.endswith('.pdf')]
        if not pdf_files:
            return None
        
        pdf_path = os.path.join(cache_dir, pdf_files[0])
        
        # PDF → 图片
        try:
            doc = fitz.open(pdf_path)
            images = []
            for page_num in range(len(doc)):
                page = doc[page_num]
                mat = fitz.Matrix(2, 2)  # 2x缩放，提高清晰度
                pix = page.get_pixmap(matrix=mat)
                img_path = os.path.join(cache_dir, f"slide_{page_num+1:03d}.png")
                pix.save(img_path)
                images.append(img_path)
            doc.close()
            # 删除PDF节省空间
            try:
                os.remove(pdf_path)
            except:
                pass
        except Exception as e:
            print(f"PDF转图片失败: {e}")
            return None
        
        return images

    def _show_ppt(self, file_path):
        """显示PPT文件"""
        # 停止视频播放
        try:
            if self.use_vlc:
                self.vlc_player.stop()
            else:
                self.media_player.stop()
        except:
            pass
        
        # 停止之前的PPT定时器
        if hasattr(self, '_ppt_timer'):
            self._ppt_timer.stop()
        
        # 停止之前的转换线程
        if hasattr(self, '_ppt_convert_thread') and self._ppt_convert_thread is not None:
            try:
                self._ppt_convert_thread.quit()
                self._ppt_convert_thread.wait(1000)
            except:
                pass
        
        # 显示加载提示
        self.image_label.setText("正在加载PPT...")
        self.image_label.setStyleSheet("""
            background-color: black;
            color: white;
            font-size: 24px;
            font-weight: bold;
        """)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.show()
        self.video_frame.hide()
        self._ppt_loading = True
        QApplication.processEvents()
        
        # 在后台线程中转换PPT
        ppt_path_ref = file_path
        
        class PPTConvertThread(QThread):
            finished = pyqtSignal(list)    # 成功，返回图片列表
            error = pyqtSignal(str)        # 失败，返回错误信息
            
            def __init__(self, parent_window, ppt_path):
                super().__init__()
                self.parent_window = parent_window
                self.ppt_path = ppt_path
            
            def run(self):
                try:
                    images = self.parent_window._convert_ppt_to_images(self.ppt_path)
                    if images is not None and len(images) > 0:
                        self.finished.emit(images)
                    else:
                        self.error.emit("PPT转换失败，请检查是否安装了Office或LibreOffice")
                except Exception as e:
                    self.error.emit(f"PPT转换出错: {str(e)}")
        
        self._ppt_convert_thread = PPTConvertThread(self, ppt_path_ref)
        self._ppt_convert_thread.finished.connect(self._on_ppt_converted)
        self._ppt_convert_thread.error.connect(self._on_ppt_convert_error)
        self._ppt_convert_thread.start()
        return True
    
    def _on_ppt_converted(self, images):
        """PPT转换完成回调"""
        if not self._ppt_loading:
            return
        
        # 保存PPT图片列表和当前页码
        self._ppt_images = images
        self._ppt_current_page = 0
        self._current_image_path = images[0]
        
        # 显示第一页
        self._show_ppt_page(0)
        
        # 设置自动翻页定时器（每5秒翻一页）
        self._ppt_timer = QTimer()
        self._ppt_timer.timeout.connect(self._ppt_next_page)
        self._ppt_timer.start(5000)
        
        self.is_playing = True
        self._ppt_loading = False
    
    def _on_ppt_convert_error(self, error_msg):
        """PPT转换失败回调"""
        self.image_label.setText(f"PPT预览失败\n{error_msg}")
        self.image_label.setStyleSheet("""
            background-color: black;
            color: white;
            font-size: 16px;
            font-weight: bold;
        """)
        self.is_playing = False
        self._ppt_loading = False

    def _show_ppt_page(self, page_index):
        """显示PPT指定页"""
        if not hasattr(self, '_ppt_images') or not self._ppt_images or page_index >= len(self._ppt_images):
            return
        
        self._ppt_current_page = page_index
        img_path = self._ppt_images[page_index]
        self._current_image_path = img_path
        
        pixmap = QPixmap(img_path)
        if not pixmap.isNull():
            scaled_pixmap = pixmap.scaled(self.width(), self.height(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            self.image_label.setPixmap(scaled_pixmap)
            self.image_label.show()
            self.video_frame.hide()
        
        # 更新窗口标题显示页码
        if hasattr(self, 'label_id'):
            self.label_id.setText(f"窗口{self.window_id} - PPT {page_index+1}/{len(self._ppt_images)}")

    def _ppt_next_page(self):
        """PPT自动翻页"""
        if not hasattr(self, '_ppt_images') or not self._ppt_images:
            return
        next_page = (self._ppt_current_page + 1) % len(self._ppt_images)
        self._show_ppt_page(next_page)

    def _safe_apply_volume(self):
        """安全地应用音量设置"""
        try:
            if hasattr(self, 'vlc_player') and self.use_vlc and not self.is_muted and self.is_playing:
                self.vlc_player.audio_set_volume(self.volume)
        except:
            pass
    
    def _safe_set_vlc_stretch(self):
        """安全地设置VLC视频拉伸"""
        try:
            if hasattr(self, 'vlc_player') and self.use_vlc and self.is_playing:
                # 设置视频拉伸填充窗口
                self.vlc_player.video_set_scale(0)
                # 获取窗口尺寸并设置宽高比
                w, h = self.width(), self.height()
                self.vlc_player.video_set_aspect_ratio(f"{w}:{h}")
        except:
            pass
    
    def pause(self):
        """暂停"""
        try:
            if self.use_vlc:
                self.vlc_player.pause()
            else:
                self.media_player.pause()
            self.is_playing = False
        except:
            pass
    
    def stop(self):
        """停止"""
        # 隐藏图片标签，恢复视频显示
        if hasattr(self, 'image_label'):
            self.image_label.hide()
            self.image_label.clear()
            if hasattr(self, '_current_image_path'):
                delattr(self, '_current_image_path')
        if hasattr(self, 'video_frame'):
            self.video_frame.show()
        
        # 停止PPT翻页定时器
        if hasattr(self, '_ppt_timer'):
            self._ppt_timer.stop()
        # 清理PPT相关属性
        if hasattr(self, '_ppt_images'):
            delattr(self, '_ppt_images')
        if hasattr(self, '_ppt_current_page'):
            delattr(self, '_ppt_current_page')
        
        try:
            if self.use_vlc:
                self.vlc_player.stop()
            else:
                self.media_player.stop()
            self.is_playing = False
        except:
            pass
    
    def replay(self):
        """重播"""
        self.stop()
        result = self.play()
        if self.use_vlc:
            QTimer.singleShot(500, self._safe_set_vlc_stretch)
        elif platform.system() == 'Linux' and hasattr(self, 'video_widget'):
            QTimer.singleShot(300, self._force_video_stretch)
        return result
        
    def next_media(self):
        """下一个媒体"""
        if self.media_files:
            self.current_index = (self.current_index + 1) % len(self.media_files)
            result = self.play()
            if self.use_vlc:
                QTimer.singleShot(500, self._safe_set_vlc_stretch)
            elif platform.system() == 'Linux' and hasattr(self, 'video_widget'):
                QTimer.singleShot(300, self._force_video_stretch)
            return result
        return False
    
    def prev_media(self):
        """上一个媒体"""
        if self.media_files:
            self.current_index = (self.current_index - 1) % len(self.media_files)
            result = self.play()
            if self.use_vlc:
                QTimer.singleShot(500, self._safe_set_vlc_stretch)
            elif platform.system() == 'Linux' and hasattr(self, 'video_widget'):
                QTimer.singleShot(300, self._force_video_stretch)
            return result
        return False
    
    def set_volume(self, volume):
        """设置音量"""
        self.volume = max(0, min(100, volume))
        if not self.is_muted:
            if self.use_vlc:
                self.vlc_player.audio_set_volume(self.volume)
            else:
                self.media_player.setVolume(self.volume)
    
    def toggle_mute(self):
        """切换静音"""
        self.is_muted = not self.is_muted
        if self.use_vlc:
            self.vlc_player.audio_set_volume(0 if self.is_muted else self.volume)
        else:
            self.media_player.setVolume(0 if self.is_muted else self.volume)
        return self.is_muted
    
    def toggle_fullscreen(self):
        """切换全屏"""
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()
    
    def lock(self):
        """锁定窗口"""
        self.is_locked = True
        self.label_id.hide()
        # 禁用鼠标追踪
        self.setMouseTracking(False)
        
    def unlock(self):
        """解锁窗口"""
        self.is_locked = False
        self.label_id.show()
        self.setMouseTracking(True)
        
    def toggle_lock(self):
        """切换锁定状态"""
        if self.is_locked:
            self.unlock()
        else:
            self.lock()
        return self.is_locked
    
    def keyPressEvent(self, event):
        """按键事件"""
        if event.key() in [Qt.Key_V, Qt.Key_PageDown]:
            self.toggle_lock()
            event.accept()
        elif event.key() == Qt.Key_Escape:
            if self.isFullScreen():
                self.showNormal()
            event.accept()
        elif event.key() == Qt.Key_Return or event.key() == Qt.Key_F:
            self.toggle_fullscreen()
            event.accept()
        # PPT翻页快捷键
        elif event.key() == Qt.Key_Left:
            if hasattr(self, '_ppt_images') and self._ppt_images:
                prev_page = (self._ppt_current_page - 1) % len(self._ppt_images)
                self._show_ppt_page(prev_page)
                event.accept()
            else:
                super().keyPressEvent(event)
        elif event.key() == Qt.Key_Right:
            if hasattr(self, '_ppt_images') and self._ppt_images:
                next_page = (self._ppt_current_page + 1) % len(self._ppt_images)
                self._show_ppt_page(next_page)
                event.accept()
            else:
                super().keyPressEvent(event)
        else:
            super().keyPressEvent(event)
    
    def closeEvent(self, event):
        """关闭事件"""
        # 停止拖拽定时器
        if hasattr(self, 'drag_timer'):
            self.drag_timer.stop()
        self.stop()
        # 清除拖拽状态
        if VideoWindow._dragging_window == self:
            VideoWindow._dragging_window = None
        # 发出窗口关闭信号
        self.window_closed.emit(self.window_id)
        event.accept()
    
    def get_position(self):
        """获取窗口位置和大小"""
        geometry = self.geometry()
        return geometry.x(), geometry.y(), geometry.width(), geometry.height()


# ============== 网络通信类 ==============

class NetworkManager(QThread):
    """网络通信管理器"""
    
    # 信号定义
    command_received = pyqtSignal(str, int)  # 命令, 窗口ID (0表示广播)
    udp_message = pyqtSignal(str, str, int)  # 消息, 地址, 端口
    tcp_connected = pyqtSignal(int)  # 窗口ID
    tcp_disconnected = pyqtSignal(int)  # 窗口ID
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.udp_sockets = {}  # {port: socket}
        self.tcp_sockets = {}  # {port: socket}
        self.tcp_server = None
        self.running = False
        
    def start_network(self):
        """启动网络服务"""
        self.running = True
        self.start()
        
    def stop_network(self):
        """停止网络服务"""
        self.running = False
        # 关闭所有socket
        for sock in list(self.udp_sockets.values()) + list(self.tcp_sockets.values()):
            try:
                sock.close()
            except:
                pass
        if self.tcp_server:
            self.tcp_server.close()
        self.quit()
        self.wait()
    
    def run(self):
        """线程主循环"""
        # 创建UDP socket用于接收
        self.setup_udp_receiver()
        
        # 创建TCP服务器
        self.setup_tcp_server()
        
        while self.running:
            self.process_udp_messages()
            self.process_tcp_connections()
            self.msleep(10)
    
    def setup_udp_receiver(self):
        """设置UDP接收"""
        # 监听广播端口
        for port in [UDP_BROADCAST_PORT] + WINDOW_UDP_PORTS:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sock.bind(('', port))
                sock.settimeout(0.1)
                self.udp_sockets[port] = sock
            except Exception as e:
                print(f"UDP端口 {port} 绑定失败: {e}")
    
    def setup_tcp_server(self):
        """设置TCP服务器"""
        try:
            self.tcp_server = QTcpServer()
            self.tcp_server.listen(QHostAddress.AnyIPv4, TCP_BROADCAST_PORT)
            self.tcp_server.newConnection.connect(self.handle_tcp_connection)
        except Exception as e:
            print(f"TCP服务器启动失败: {e}")
    
    def process_udp_messages(self):
        """处理UDP消息"""
        for port, sock in self.udp_sockets.items():
            try:
                sock.settimeout(0.01)
                data, addr = sock.recvfrom(1024)
                message = data.decode('utf-8', errors='ignore').strip()
                if message:
                    self.udp_message.emit(message, addr[0], port)
                    self.parse_command(message, port - UDP_BROADCAST_PORT if port != UDP_BROADCAST_PORT else 0)
            except socket.timeout:
                continue
            except Exception as e:
                pass
    
    def process_tcp_connections(self):
        """处理TCP连接"""
        pass  # 使用Qt的事件处理
    
    def handle_tcp_connection(self):
        """处理TCP连接"""
        while self.tcp_server.hasPendingConnections():
            client = self.tcp_server.nextPendingConnection()
            port = client.localPort()
            
            # 确定窗口ID
            if port == TCP_BROADCAST_PORT:
                window_id = 0
            else:
                window_id = port - WINDOW_TCP_PORTS[0] + 1
            
            self.tcp_sockets[client] = {'window_id': window_id}
            client.readyRead.connect(lambda: self.read_tcp_data(client))
            client.disconnected.connect(lambda: self.close_tcp_connection(client))
            self.tcp_connected.emit(window_id)
    
    def read_tcp_data(self, client):
        """读取TCP数据"""
        while client.bytesAvailable():
            data = client.read(1024)
            message = data.decode('utf-8', errors='ignore').strip()
            if message:
                window_id = self.tcp_sockets.get(client, {}).get('window_id', 0)
                self.parse_command(message, window_id)
    
    def close_tcp_connection(self, client):
        """关闭TCP连接"""
        if client in self.tcp_sockets:
            window_id = self.tcp_sockets[client]['window_id']
            del self.tcp_sockets[client]
            self.tcp_disconnected.emit(window_id)
        client.close()
    
    def parse_command(self, message, window_id):
        """解析命令
        支持格式: 
          windowid_command_param (如 1_play_2)
          windowid:command:param (如 1:play:2)
          command (如 play)
        """
        parts = re.split(r'[_,:]', message.strip())
        if len(parts) >= 2:
            if parts[0].isdigit():
                wid = int(parts[0])
                cmd = parts[1].lower()
                # 如果有第三个参数（如播放编号），组合为 play_2 格式
                if len(parts) > 2 and parts[2].isdigit():
                    cmd = f"{cmd}_{parts[2]}"
                self.command_received.emit(cmd, wid)
            else:
                cmd = parts[0].lower()
                if len(parts) > 1 and parts[1].isdigit():
                    cmd = f"{cmd}_{parts[1]}"
                self.command_received.emit(cmd, window_id)
        else:
            self.command_received.emit(message.lower().strip(), window_id)
    
    def send_udp(self, message, host, port):
        """发送UDP消息"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.sendto(message.encode('utf-8'), (host, port))
            sock.close()
            return True
        except Exception as e:
            print(f"UDP发送失败: {e}")
            return False
    
    def send_tcp(self, message, host, port):
        """发送TCP消息"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((host, port))
            sock.send(message.encode('utf-8'))
            sock.close()
            return True
        except Exception as e:
            print(f"TCP发送失败: {e}")
            return False


# ============== 串口管理类 ==============

class SerialManager(QThread):
    """串口通信管理"""
    
    data_received = pyqtSignal(str)  # 收到的数据
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.serial_port = None
        self.running = False
        self.port_name = 'COM1'
        self.baudrate = 115200
        self.bytesize = 8
        self.stopbits = 1
        self.parity = 'N'
        
    def configure(self, port, baudrate=115200, bytesize=8, stopbits=1, parity='N'):
        """配置串口参数"""
        self.port_name = port
        self.baudrate = baudrate
        self.bytesize = bytesize
        self.stopbits = stopbits
        self.parity = parity
    
    def connect(self):
        """连接串口"""
        if SERIAL_AVAILABLE and self.serial_port is None:
            try:
                self.serial_port = serial.Serial(
                    port=self.port_name,
                    baudrate=self.baudrate,
                    bytesize=self.bytesize,
                    stopbits=self.stopbits,
                    parity=self.parity,
                    timeout=0.1
                )
                self.running = True
                self.start()
                return True
            except Exception as e:
                print(f"串口连接失败: {e}")
                return False
        return False
    
    def disconnect(self):
        """断开串口"""
        self.running = False
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
        self.serial_port = None
        self.quit()
        self.wait()
    
    def is_connected(self):
        """检查连接状态"""
        return self.serial_port is not None and self.serial_port.is_open
    
    def send(self, data):
        """发送数据"""
        if self.is_connected():
            try:
                if isinstance(data, str):
                    data = data.encode('utf-8')
                self.serial_port.write(data)
                return True
            except Exception as e:
                print(f"串口发送失败: {e}")
                return False
        return False
    
    def run(self):
        """线程主循环"""
        while self.running and self.serial_port:
            try:
                if self.serial_port.in_waiting:
                    data = self.serial_port.readline()
                    if data:
                        try:
                            message = data.decode('utf-8', errors='ignore').strip()
                            if message:
                                self.data_received.emit(message)
                        except:
                            pass
            except Exception as e:
                print(f"串口读取错误: {e}")
            self.msleep(10)
    
    @staticmethod
    def list_ports():
        """列出可用串口"""
        if SERIAL_AVAILABLE:
            ports = serial.tools.list_ports.comports()
            return [p.device for p in ports]
        return []


# ============== 激活对话框 ==============

class ActivationDialog(QDialog):
    """激活对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("软件激活")
        self.setModal(True)
        self.resize(500, 300)
        self.init_ui()
        
    def init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout()
        layout.setSpacing(20)
        
        # 标题
        title = QLabel("坤展成-中控多窗口播放器")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # 机器码
        machine_code_label = QLabel("机器码：")
        layout.addWidget(machine_code_label)
        
        self.machine_code_edit = QLineEdit()
        self.machine_code_edit.setReadOnly(True)
        self.machine_code_edit.setText(LicenseManager.get_machine_code())
        layout.addWidget(self.machine_code_edit)
        
        # 授权码
        license_label = QLabel("授权码：")
        layout.addWidget(license_label)
        
        self.license_edit = QLineEdit()
        self.license_edit.setPlaceholderText("请输入授权码")
        layout.addWidget(self.license_edit)
        
        # 提示信息
        hint = QLabel("请联系经销商获取授权码")
        hint.setStyleSheet("color: gray;")
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)
        
        # 按钮
        btn_layout = QHBoxLayout()
        self.ok_btn = QPushButton("激活")
        self.ok_btn.clicked.connect(self.do_activation)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        
        self.setLayout(layout)
        
    def do_activation(self):
        """执行激活"""
        license_key = self.license_edit.text().strip()
        if not license_key:
            QMessageBox.warning(self, "提示", "请输入授权码")
            return
        
        valid, msg = LicenseManager.verify_license(license_key)
        if valid:
            LicenseManager.save_license(license_key)
            QMessageBox.information(self, "成功", "激活成功！")
            self.accept()
        else:
            QMessageBox.warning(self, "失败", msg)


# ============== 关于对话框 ==============

class AboutDialog(QDialog):
    """关于对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("关于")
        self.setModal(True)
        self.resize(400, 300)
        self.init_ui()
        
    def init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout()
        layout.setSpacing(15)
        
        # 软件名称
        name = QLabel(APP_NAME)
        name.setStyleSheet("font-size: 20px; font-weight: bold;")
        name.setAlignment(Qt.AlignCenter)
        layout.addWidget(name)
        
        # 版本
        version = QLabel(f"版本 {APP_VERSION}")
        version.setAlignment(Qt.AlignCenter)
        layout.addWidget(version)
        
        # 开发商
        company = QLabel(f"开发公司：{COMPANY_NAME}")
        company.setAlignment(Qt.AlignCenter)
        layout.addWidget(company)
        
        # 联系方式
        contact = QLabel(f"联系方式：{CONTACT_PHONE}")
        contact.setAlignment(Qt.AlignCenter)
        layout.addWidget(contact)
        
        # 版权
        copyright = QLabel("版权所有 翻版必究")
        copyright.setStyleSheet("color: gray;")
        copyright.setAlignment(Qt.AlignCenter)
        layout.addWidget(copyright)
        
        # 关闭按钮
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
        
        layout.addStretch()
        self.setLayout(layout)


# ============== 窗口设置对话框 ==============

class WindowSettingsDialog(QDialog):
    """窗口设置对话框"""
    
    def __init__(self, title="窗口设置", x=100, y=100, width=800, height=600, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(350, 200)
        self.init_ui(x, y, width, height)
        
    def init_ui(self, x, y, width, height):
        """初始化UI"""
        layout = QGridLayout()
        
        # X坐标
        layout.addWidget(QLabel("X坐标："), 0, 0)
        self.x_spin = QSpinBox()
        self.x_spin.setRange(0, 9999)
        self.x_spin.setValue(x)
        layout.addWidget(self.x_spin, 0, 1)
        
        # Y坐标
        layout.addWidget(QLabel("Y坐标："), 0, 2)
        self.y_spin = QSpinBox()
        self.y_spin.setRange(0, 9999)
        self.y_spin.setValue(y)
        layout.addWidget(self.y_spin, 0, 3)
        
        # 宽度
        layout.addWidget(QLabel("宽度："), 1, 0)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(100, 9999)
        self.width_spin.setValue(width)
        layout.addWidget(self.width_spin, 1, 1)
        
        # 高度
        layout.addWidget(QLabel("高度："), 1, 2)
        self.height_spin = QSpinBox()
        self.height_spin.setRange(100, 9999)
        self.height_spin.setValue(height)
        layout.addWidget(self.height_spin, 1, 3)
        
        # 按钮
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("确定")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout, 2, 0, 1, 4)
        
        self.setLayout(layout)
    
    def get_values(self):
        """获取设置值"""
        return (
            self.x_spin.value(),
            self.y_spin.value(),
            self.width_spin.value(),
            self.height_spin.value()
        )


# ============== 主窗口 ==============

class MainWindow(QMainWindow):
    """主控制窗口"""
    
    def __init__(self):
        super().__init__()
        
        # 初始化配置管理器
        self.config_manager = ConfigManager()
        self.config_manager.load_config()
        
        # 防抖保存定时器
        self._config_save_timer = QTimer(self)
        self._config_save_timer.setSingleShot(True)
        self._config_save_timer.timeout.connect(self.save_config)
        
        # 窗口设置
        self.is_minimized_to_tray = False
        self.video_windows = {}  # {window_id: VideoWindow}
        self.current_window_id = 1
        
        # 网络和串口
        self.network_manager = NetworkManager(self)
        self.serial_manager = SerialManager(self)
        
        # 初始化UI
        self.init_ui()
        
        # 连接信号
        self.connect_signals()
        
        # 启动网络服务
        self.network_manager.start_network()
        
        # 检查授权
        self.check_license()
        
        # 注册全局快捷键
        self.register_global_hotkeys()
        
        # 加载配置
        self.apply_config()
        
    def init_ui(self):
        """初始化UI"""
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.resize(1100, 800)
        
        # 设置窗口图标
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f5f5;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #ccc;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QPushButton {
                min-height: 28px;
                border-radius: 4px;
            }
            QPushButton:enabled {
                background-color: #0078d4;
                color: white;
                border: none;
            }
            QPushButton:enabled:hover {
                background-color: #106ebe;
            }
            QPushButton:enabled:pressed {
                background-color: #005a9e;
            }
            QPushButton:disabled {
                background-color: #e0e0e0;
                color: #999;
            }
            QLineEdit, QSpinBox, QComboBox {
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 4px;
                background-color: white;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #ccc;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                width: 16px;
                background: #0078d4;
                border-radius: 8px;
                margin: -5px 0;
            }
        """)
        
        # 创建中心部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QHBoxLayout()
        central_widget.setLayout(main_layout)
        
        # 左侧控制区
        left_widget = self.create_left_panel()
        main_layout.addWidget(left_widget, 1)
        
        # 右侧通信区
        right_widget = self.create_right_panel()
        main_layout.addWidget(right_widget, 0)
        
        # 创建系统托盘
        self.create_tray_icon()
        
        # 状态栏
        self.statusBar().showMessage("就绪")
        
    def create_left_panel(self):
        """创建左侧控制面板"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)
        
        # ===== 顶部信息区（紧凑两栏布局）=====
        info_group = QGroupBox("软件信息")
        info_layout = QGridLayout()
        info_layout.setSpacing(4)
        
        # 左列：公司信息
        info_layout.addWidget(QLabel(f"公司：{COMPANY_NAME}"), 0, 0)
        
        # 右列：桌面分辨率
        desktop = QDesktopWidget()
        screen = desktop.screenGeometry()
        info_layout.addWidget(QLabel(f"分辨率：{screen.width()}×{screen.height()}"), 0, 1)
        
        # 左列：电话
        info_layout.addWidget(QLabel(f"电话：{CONTACT_PHONE}"), 1, 0)
        
        # 右列：支持格式
        format_label = QLabel("格式：视频/图片/PPT")
        format_label.setStyleSheet("color: #666; font-size: 11px;")
        info_layout.addWidget(format_label, 1, 1)
        
        # 左列：最小化到托盘
        self.minimize_to_tray_check = QCheckBox("启动时最小化到托盘")
        self.minimize_to_tray_check.stateChanged.connect(self._on_minimize_to_tray_changed)
        info_layout.addWidget(self.minimize_to_tray_check, 2, 0)
        
        # 右列：快捷键
        hotkey_label = QLabel("快捷键：PageUp 呼出 | PageDown 锁定")
        hotkey_label.setStyleSheet("color: #666; font-size: 11px;")
        hotkey_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        info_layout.addWidget(hotkey_label, 2, 1)
        
        # 底部：试用期+激活按钮
        trial_layout = QHBoxLayout()
        self.trial_label = QLabel("剩余30天试用期")
        trial_layout.addWidget(self.trial_label)
        
        self.activate_btn = QPushButton("激活授权")
        self.activate_btn.clicked.connect(self.show_activation_dialog)
        trial_layout.addWidget(self.activate_btn)
        
        about_btn = QPushButton("关于")
        about_btn.clicked.connect(self.show_about_dialog)
        trial_layout.addWidget(about_btn)
        info_layout.addLayout(trial_layout, 3, 0, 1, 2)
        
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)
        
        # ===== 窗口选择和位置设置 =====
        window_group = QGroupBox("窗口设置")
        window_layout = QVBoxLayout()
        
        # 窗口标签
        tab_layout = QHBoxLayout()
        self.window_tabs = QButtonGroup()
        for i in range(1, 5):
            btn = QPushButton(f"窗口{i}")
            btn.setCheckable(True)
            btn.setMinimumWidth(60)
            if i == 1:
                btn.setChecked(True)
            btn.clicked.connect(lambda checked, w=i: self.select_window(w))
            self.window_tabs.addButton(btn, i)
            tab_layout.addWidget(btn)
        window_layout.addLayout(tab_layout)
        
        # 位置设置
        pos_layout = QGridLayout()
        pos_layout.addWidget(QLabel("X:"), 0, 0)
        self.x_spin = QSpinBox()
        self.x_spin.setRange(0, 9999)
        self.x_spin.setValue(100)
        self.x_spin.valueChanged.connect(self.on_position_changed)
        pos_layout.addWidget(self.x_spin, 0, 1)
        
        pos_layout.addWidget(QLabel("Y:"), 0, 2)
        self.y_spin = QSpinBox()
        self.y_spin.setRange(0, 9999)
        self.y_spin.setValue(100)
        self.y_spin.valueChanged.connect(self.on_position_changed)
        pos_layout.addWidget(self.y_spin, 0, 3)
        
        pos_layout.addWidget(QLabel("宽:"), 1, 0)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(100, 9999)
        self.width_spin.setValue(800)
        self.width_spin.valueChanged.connect(self.on_position_changed)
        pos_layout.addWidget(self.width_spin, 1, 1)
        
        pos_layout.addWidget(QLabel("高:"), 1, 2)
        self.height_spin = QSpinBox()
        self.height_spin.setRange(100, 9999)
        self.height_spin.setValue(600)
        self.height_spin.valueChanged.connect(self.on_position_changed)
        pos_layout.addWidget(self.height_spin, 1, 3)
        window_layout.addLayout(pos_layout)
        
        # 全屏铺满按钮
        fullscreen_btn = QPushButton("全屏铺满桌面")
        fullscreen_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff6600;
            }
            QPushButton:hover {
                background-color: #cc5500;
            }
        """)
        fullscreen_btn.clicked.connect(self.fullscreen_current_window)
        window_layout.addWidget(fullscreen_btn)
        
        window_group.setLayout(window_layout)
        layout.addWidget(window_group)
        
        # ===== 媒体列表（跟随当前窗口）=====
        self.media_group_title = "窗口{self.current_window_id} 媒体列表"
        media_group = QGroupBox("窗口1 媒体列表")
        media_group.setObjectName("media_group")
        self.media_group = media_group
        media_layout = QVBoxLayout()
        
        self.media_list = QTableWidget()
        self.media_list.setColumnCount(6)
        self.media_list.setHorizontalHeaderLabels(["编号", "文件名", "类型", "控制指令", "默认", "模式"])
        self.media_list.horizontalHeader().hide()
        self.media_list.verticalHeader().hide()
        self.media_list.setShowGrid(False)
        self.media_list.setSelectionBehavior(QTableWidget.SelectRows)
        self.media_list.setSelectionMode(QTableWidget.SingleSelection)
        self.media_list.setEditTriggers(QTableWidget.NoEditTriggers)
        self.media_list.setMaximumHeight(180)
        # 编号/类型/默认用Fixed紧凑，文件名/控制指令/模式用Stretch均分剩余空间，间距均匀
        self.media_list.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.media_list.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.media_list.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.media_list.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.media_list.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        self.media_list.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.media_list.setColumnWidth(0, 22)   # 编号
        self.media_list.setColumnWidth(2, 28)   # 类型
        self.media_list.setColumnWidth(4, 32)   # 默认
        self.media_list.setStyleSheet("""
            QTableWidget {
                font-size: 12px;
                border: 1px solid #ddd;
                background-color: white;
            }
            QTableWidget::item {
                padding: 0px 2px;
            }
            QTableWidget::item:selected {
                background-color: #e3f2fd;
                color: #1565c0;
            }
        """)
        # 默认播放单选按钮组（每个窗口各自一组，更新时重建）
        self._default_btn_group = QButtonGroup(self)
        self._default_btn_group.setExclusive(True)
        self.media_list.itemDoubleClicked.connect(self.play_selected_media)
        self.media_list.cellDoubleClicked.connect(self._on_media_cell_double_clicked)
        media_layout.addWidget(self.media_list)
        
        # 按钮行：添加视频 | 移除选中 | 自动打开
        btn_row = QHBoxLayout()
        add_btn = QPushButton(" 添加视频")
        add_btn.setIcon(self.style().standardIcon(QStyle.SP_DialogOpenButton))
        add_btn.clicked.connect(self.add_media_file)
        btn_row.addWidget(add_btn)
        
        remove_btn = QPushButton("移除选中")
        remove_btn.clicked.connect(self.remove_selected_media)
        btn_row.addWidget(remove_btn)
        
        self.auto_open_cb = QCheckBox("自动打开此窗口")
        self.auto_open_cb.stateChanged.connect(self.toggle_auto_open)
        btn_row.addWidget(self.auto_open_cb)
        media_layout.addLayout(btn_row)
        
        # 打开/删除窗口按钮
        window_btn_layout = QHBoxLayout()
        self.open_window_btn = QPushButton("打开窗口1")
        self.open_window_btn.clicked.connect(self.open_current_window)
        window_btn_layout.addWidget(self.open_window_btn)
        
        self.delete_window_btn = QPushButton("关闭窗口1")
        self.delete_window_btn.clicked.connect(self.delete_current_window)
        self.delete_window_btn.setStyleSheet("QPushButton { background-color: #ff6b6b; color: white; }")
        window_btn_layout.addWidget(self.delete_window_btn)
        
        media_layout.addLayout(window_btn_layout)
        
        media_group.setLayout(media_layout)
        layout.addWidget(media_group)
        
        # ===== 通信设置 =====
        comm_group = QGroupBox("通信设置")
        comm_layout = QGridLayout()
        
        comm_layout.addWidget(QLabel("目标IP:"), 0, 0)
        self.target_ip_edit = QLineEdit("192.168.1.3")
        comm_layout.addWidget(self.target_ip_edit, 0, 1)
        
        comm_layout.addWidget(QLabel("UDP端口:"), 1, 0)
        self.udp_port_spin = QSpinBox()
        self.udp_port_spin.setRange(1, 65535)
        self.udp_port_spin.setValue(8888)
        comm_layout.addWidget(self.udp_port_spin, 1, 1)
        
        comm_layout.addWidget(QLabel("TCP端口:"), 2, 0)
        self.tcp_port_spin = QSpinBox()
        self.tcp_port_spin.setRange(1, 65535)
        self.tcp_port_spin.setValue(8889)
        comm_layout.addWidget(self.tcp_port_spin, 2, 1)
        
        # 串口设置
        serial_layout = QHBoxLayout()
        self.serial_port_combo = QComboBox()
        self.serial_port_combo.addItems(["COM1", "COM2", "COM3", "COM4"])
        serial_layout.addWidget(self.serial_port_combo)
        
        self.serial_connect_btn = QPushButton("连接串口")
        self.serial_connect_btn.clicked.connect(self.toggle_serial_connection)
        serial_layout.addWidget(self.serial_connect_btn)
        comm_layout.addLayout(serial_layout, 3, 0, 1, 2)
        
        comm_group.setLayout(comm_layout)
        layout.addWidget(comm_group)
        
        layout.addStretch()
        scroll.setWidget(widget)
        
        container = QWidget()
        container_layout = QHBoxLayout()
        container_layout.addWidget(scroll)
        container.setLayout(container_layout)
        
        return container
    
    def create_right_panel(self):
        """创建右侧通信面板"""
        widget = QWidget()
        widget.setMinimumWidth(350)
        widget.setStyleSheet("""
            QGroupBox {
                margin-top: 15px;
            }
        """)
        layout = QVBoxLayout()
        widget.setLayout(layout)
        
        # ===== 播放控制（跟随当前窗口，仅窗口打开后显示）=====
        control_group = QGroupBox("播放控制 → 窗口1")
        control_group.setObjectName("control_group")
        self.control_group = control_group
        control_layout = QVBoxLayout()
        
        # 第一行按钮
        btn_row1 = QHBoxLayout()
        self.play_btn = QPushButton("▶ 播放")
        self.play_btn.setToolTip("UDP指令: play")
        self.play_btn.clicked.connect(self.play_current)
        btn_row1.addWidget(self.play_btn)
        play_cmd_label = QLabel("play")
        play_cmd_label.setStyleSheet("color: #888; font-size: 10px;")
        play_cmd_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        btn_row1.addWidget(play_cmd_label)
        
        self.pause_btn = QPushButton("⏸ 暂停")
        self.pause_btn.setToolTip("UDP指令: pause")
        self.pause_btn.clicked.connect(self.pause_current)
        btn_row1.addWidget(self.pause_btn)
        pause_cmd_label = QLabel("pause")
        pause_cmd_label.setStyleSheet("color: #888; font-size: 10px;")
        pause_cmd_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        btn_row1.addWidget(pause_cmd_label)
        
        self.stop_btn = QPushButton("⏹ 停止")
        self.stop_btn.setToolTip("UDP指令: stop")
        self.stop_btn.clicked.connect(self.stop_current)
        btn_row1.addWidget(self.stop_btn)
        stop_cmd_label = QLabel("stop")
        stop_cmd_label.setStyleSheet("color: #888; font-size: 10px;")
        stop_cmd_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        btn_row1.addWidget(stop_cmd_label)
        
        self.replay_btn = QPushButton("🔄 重播")
        self.replay_btn.setToolTip("UDP指令: replay")
        self.replay_btn.clicked.connect(self.replay_current)
        btn_row1.addWidget(self.replay_btn)
        replay_cmd_label = QLabel("replay")
        replay_cmd_label.setStyleSheet("color: #888; font-size: 10px;")
        replay_cmd_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        play_cmd_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        btn_row1.addWidget(replay_cmd_label)
        control_layout.addLayout(btn_row1)
        
        # 第二行按钮
        btn_row2 = QHBoxLayout()
        self.fullscreen_btn2 = QPushButton("全屏")
        self.fullscreen_btn2.setToolTip("UDP指令: fullscreen")
        self.fullscreen_btn2.clicked.connect(self.toggle_fullscreen_current)
        btn_row2.addWidget(self.fullscreen_btn2)
        fs_cmd_label = QLabel("fullscreen")
        fs_cmd_label.setStyleSheet("color: #888; font-size: 10px;")
        fs_cmd_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        btn_row2.addWidget(fs_cmd_label)
        
        self.loop_btn = QPushButton("🔁 循环")
        self.loop_btn.setToolTip("UDP指令: loop")
        self.loop_btn.setCheckable(True)
        self.loop_btn.clicked.connect(self.toggle_loop_current)
        btn_row2.addWidget(self.loop_btn)
        loop_cmd_label = QLabel("loop")
        loop_cmd_label.setStyleSheet("color: #888; font-size: 10px;")
        loop_cmd_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        btn_row2.addWidget(loop_cmd_label)
        
        self.mute_btn2 = QPushButton("🔊 静音")
        self.mute_btn2.setToolTip("UDP指令: mute / unmute")
        self.mute_btn2.clicked.connect(self.toggle_mute_current)
        btn_row2.addWidget(self.mute_btn2)
        mute_cmd_label = QLabel("mute/unmute")
        mute_cmd_label.setStyleSheet("color: #888; font-size: 10px;")
        mute_cmd_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        btn_row2.addWidget(mute_cmd_label)
        control_layout.addLayout(btn_row2)
        
        # UDP端口显示
        self.cmd_port_label = QLabel("UDP端口: 8888 | TCP端口: 8892")
        self.cmd_port_label.setStyleSheet("color: #666; font-size: 11px; padding: 2px;")
        control_layout.addWidget(self.cmd_port_label)
        
        # 按编号播放指令提示
        play_num_label = QLabel("按编号播放: {窗口ID}_play_{编号} (如 1_play_2 表示窗口1播放第2个)")
        play_num_label.setStyleSheet("color: #888; font-size: 10px; padding: 2px;")
        play_num_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        control_layout.addWidget(play_num_label)
        
        control_group.setLayout(control_layout)
        # 默认隐藏，窗口打开后才显示
        control_group.setVisible(False)
        layout.addWidget(control_group)
        
        # ===== 视频切换（仅窗口打开后显示）=====
        switch_group = QGroupBox("视频切换")
        switch_group.setObjectName("switch_group")
        self.switch_group = switch_group
        switch_layout = QHBoxLayout()
        
        prev_btn = QPushButton("◀ 上一个")
        prev_btn.setToolTip("UDP指令: prev")
        prev_btn.clicked.connect(self.prev_media)
        switch_layout.addWidget(prev_btn)
        prev_cmd_label = QLabel("prev")
        prev_cmd_label.setStyleSheet("color: #888; font-size: 10px;")
        prev_cmd_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        switch_layout.addWidget(prev_cmd_label)
        
        next_btn = QPushButton("下一个 ▶")
        next_btn.setToolTip("UDP指令: next")
        next_btn.clicked.connect(self.next_media)
        switch_layout.addWidget(next_btn)
        next_cmd_label = QLabel("next")
        next_cmd_label.setStyleSheet("color: #888; font-size: 10px;")
        next_cmd_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        switch_layout.addWidget(next_cmd_label)
        
        self.media_combo = QComboBox()
        self.media_combo.currentIndexChanged.connect(self.on_media_combo_changed)
        switch_layout.addWidget(self.media_combo, 1)
        
        switch_group.setLayout(switch_layout)
        # 默认隐藏，窗口打开后才显示
        switch_group.setVisible(False)
        layout.addWidget(switch_group)
        
        # ===== 音量控制（仅窗口打开后显示）=====
        volume_group = QGroupBox("独立音量控制")
        volume_group.setObjectName("volume_group")
        self.volume_group = volume_group
        volume_layout = QHBoxLayout()
        
        self.mute_btn = QPushButton("🔊 静音")
        self.mute_btn.setToolTip("UDP指令: mute / unmute")
        self.mute_btn.clicked.connect(self.toggle_mute_current)
        volume_layout.addWidget(self.mute_btn)
        
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(80)
        self.volume_slider.setToolTip("UDP指令: volume 0-100")
        self.volume_slider.valueChanged.connect(self.on_volume_changed)
        volume_layout.addWidget(self.volume_slider, 1)
        
        self.volume_label = QLabel("80%")
        self.volume_label.setMinimumWidth(40)
        volume_layout.addWidget(self.volume_label)
        
        vol_cmd_label = QLabel("volume 0-100")
        vol_cmd_label.setStyleSheet("color: #888; font-size: 10px;")
        vol_cmd_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        volume_layout.addWidget(vol_cmd_label)
        
        volume_group.setLayout(volume_layout)
        # 默认隐藏，窗口打开后才显示
        volume_group.setVisible(False)
        layout.addWidget(volume_group)
        
        # ===== 全控指令 =====
        full_control_group = QGroupBox("全控指令")
        full_control_layout = QVBoxLayout()
        
        # 第一行：播放/暂停
        row1 = QHBoxLayout()
        play_all_btn = QPushButton("▶全部播放")
        play_all_btn.setStyleSheet("background-color: #28a745; min-height: 28px;")
        play_all_btn.clicked.connect(self.broadcast_play_all)
        row1.addWidget(play_all_btn)
        play_cmd = QLabel("play_all")
        play_cmd.setStyleSheet("color: #0066cc; font-size: 11px; font-family: Consolas, monospace;")
        play_cmd.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row1.addWidget(play_cmd)
        
        pause_all_btn = QPushButton("⏸全部暂停")
        pause_all_btn.setStyleSheet("background-color: #ffc107; min-height: 28px;")
        pause_all_btn.clicked.connect(self.broadcast_pause_all)
        row1.addWidget(pause_all_btn)
        pause_cmd = QLabel("pause_all")
        pause_cmd.setStyleSheet("color: #0066cc; font-size: 11px; font-family: Consolas, monospace;")
        pause_cmd.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row1.addWidget(pause_cmd)
        full_control_layout.addLayout(row1)
        
        # 第二行：停止/重播
        row2 = QHBoxLayout()
        stop_all_btn = QPushButton("⏹全部停止")
        stop_all_btn.setStyleSheet("background-color: #dc3545; color: white; min-height: 28px;")
        stop_all_btn.clicked.connect(self.broadcast_stop_all)
        row2.addWidget(stop_all_btn)
        stop_cmd = QLabel("stop_all")
        stop_cmd.setStyleSheet("color: #0066cc; font-size: 11px; font-family: Consolas, monospace;")
        stop_cmd.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row2.addWidget(stop_cmd)
        
        replay_all_btn = QPushButton("🔄全部重播")
        replay_all_btn.setStyleSheet("min-height: 28px;")
        replay_all_btn.clicked.connect(self.broadcast_replay_all)
        row2.addWidget(replay_all_btn)
        replay_cmd = QLabel("replay_all")
        replay_cmd.setStyleSheet("color: #0066cc; font-size: 11px; font-family: Consolas, monospace;")
        replay_cmd.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row2.addWidget(replay_cmd)
        full_control_layout.addLayout(row2)
        
        # 第三行：上一个/下一个
        row3 = QHBoxLayout()
        prev_all_btn = QPushButton("◀全部上一个")
        prev_all_btn.setStyleSheet("background-color: #6f42c1; color: white; min-height: 28px;")
        prev_all_btn.clicked.connect(self.broadcast_prev_all)
        row3.addWidget(prev_all_btn)
        prev_cmd = QLabel("prev_all")
        prev_cmd.setStyleSheet("color: #0066cc; font-size: 11px; font-family: Consolas, monospace;")
        prev_cmd.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row3.addWidget(prev_cmd)
        
        next_all_btn = QPushButton("全部下一个▶")
        next_all_btn.setStyleSheet("background-color: #6f42c1; color: white; min-height: 28px;")
        next_all_btn.clicked.connect(self.broadcast_next_all)
        row3.addWidget(next_all_btn)
        next_cmd = QLabel("next_all")
        next_cmd.setStyleSheet("color: #0066cc; font-size: 11px; font-family: Consolas, monospace;")
        next_cmd.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row3.addWidget(next_cmd)
        full_control_layout.addLayout(row3)
        
        # 第四行：静音/取消静音
        row4 = QHBoxLayout()
        mute_all_btn = QPushButton("🔊全部静音")
        mute_all_btn.setStyleSheet("min-height: 28px;")
        mute_all_btn.clicked.connect(self.broadcast_mute_all)
        row4.addWidget(mute_all_btn)
        mute_cmd = QLabel("mute_all")
        mute_cmd.setStyleSheet("color: #0066cc; font-size: 11px; font-family: Consolas, monospace;")
        mute_cmd.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row4.addWidget(mute_cmd)
        
        unmute_all_btn = QPushButton("🔇全部取消静音")
        unmute_all_btn.setStyleSheet("min-height: 28px;")
        unmute_all_btn.clicked.connect(self.broadcast_unmute_all)
        row4.addWidget(unmute_all_btn)
        unmute_cmd = QLabel("unmute_all")
        unmute_cmd.setStyleSheet("color: #0066cc; font-size: 11px; font-family: Consolas, monospace;")
        unmute_cmd.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row4.addWidget(unmute_cmd)
        full_control_layout.addLayout(row4)
        
        # 第五行：全部音量滑块
        row5 = QHBoxLayout()
        volume_all_label = QLabel("全部音量:")
        volume_all_label.setStyleSheet("font-size: 11px;")
        row5.addWidget(volume_all_label)
        
        self.volume_all_slider = QSlider(Qt.Horizontal)
        self.volume_all_slider.setRange(0, 100)
        self.volume_all_slider.setValue(80)
        self.volume_all_slider.setToolTip("设置所有窗口的音量")
        self.volume_all_slider.valueChanged.connect(self.on_volume_all_changed)
        row5.addWidget(self.volume_all_slider, 1)
        
        self.volume_all_value_label = QLabel("80%")
        self.volume_all_value_label.setMinimumWidth(35)
        row5.addWidget(self.volume_all_value_label)
        
        vol_all_cmd = QLabel("volume 0-100")
        vol_all_cmd.setStyleSheet("color: #0066cc; font-size: 11px; font-family: Consolas, monospace;")
        vol_all_cmd.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row5.addWidget(vol_all_cmd)
        full_control_layout.addLayout(row5)
        
        # 第六行：广播打开/关闭
        row6 = QHBoxLayout()
        open_all_btn = QPushButton("广播打开")
        open_all_btn.setStyleSheet("background-color: #17a2b8; color: white; min-height: 28px;")
        open_all_btn.clicked.connect(self.broadcast_open_all)
        row6.addWidget(open_all_btn)
        open_cmd = QLabel("open_all")
        open_cmd.setStyleSheet("color: #0066cc; font-size: 11px; font-family: Consolas, monospace;")
        open_cmd.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row6.addWidget(open_cmd)
        
        close_all_btn = QPushButton("广播关闭")
        close_all_btn.setStyleSheet("background-color: #6c757d; color: white; min-height: 28px;")
        close_all_btn.clicked.connect(self.broadcast_close_all)
        row6.addWidget(close_all_btn)
        close_cmd = QLabel("close_all")
        close_cmd.setStyleSheet("color: #0066cc; font-size: 11px; font-family: Consolas, monospace;")
        close_cmd.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row6.addWidget(close_cmd)
        full_control_layout.addLayout(row6)
        
        full_control_group.setLayout(full_control_layout)
        layout.addWidget(full_control_group)
        
        # ===== 日志显示 =====
        log_group = QGroupBox("通信日志")
        log_layout = QVBoxLayout()
        
        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(100)
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        
        clear_log_btn = QPushButton("清除日志")
        clear_log_btn.clicked.connect(self.log_text.clear)
        log_layout.addWidget(clear_log_btn)
        
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)
        
        layout.addStretch()
        
        return widget
    
    def create_tray_icon(self):
        """创建系统托盘图标"""
        self.tray_icon = QSystemTrayIcon(self)
        
        # 创建托盘菜单
        tray_menu = QMenu()
        
        show_action = QAction("显示主窗口", self)
        show_action.triggered.connect(self.show_main_window)
        tray_menu.addAction(show_action)
        
        hide_action = QAction("隐藏到托盘", self)
        hide_action.triggered.connect(self.hide_to_tray)
        tray_menu.addAction(hide_action)
        
        tray_menu.addSeparator()
        
        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self.quit_application)
        tray_menu.addAction(exit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.on_tray_activated)
        
        # 设置图标
        try:
            icon_path = get_resource_path("Kunzhancheng.ico")
            if os.path.exists(icon_path):
                self.tray_icon.setIcon(QIcon(icon_path))
            else:
                self.tray_icon.setIcon(self.style().standardIcon(QStyle.SP_ComputerIcon))
        except:
            pass
        
        self.tray_icon.setToolTip(APP_NAME)
        self.tray_icon.show()
    
    def connect_signals(self):
        """连接信号"""
        # 网络命令
        self.network_manager.command_received.connect(self.on_network_command)
        self.network_manager.udp_message.connect(self.on_udp_message)
        
        # 串口数据
        self.serial_manager.data_received.connect(self.on_serial_data)
    
    def register_global_hotkeys(self):
        """注册全局快捷键"""
        # 使用定时器检查按键（简化实现）
        self.hotkey_timer = QTimer()
        self.hotkey_timer.timeout.connect(self.check_hotkeys)
        if platform.system() == 'Windows':
            self.hotkey_timer.start(100)
        
        # 记录上一个状态
        self.last_pageup_state = False
        self.last_pagedown_state = False
        self.last_v_state = False
    
    def check_hotkeys(self):
        """检查全局快捷键"""
        try:
            # 获取键盘状态
            from ctypes import windll
            VK_PRIOR = 0x21  # PageUp
            VK_NEXT = 0x22   # PageDown
            VK_V = 0x56      # V键
            
            # 检查PageUp
            pageup_state = windll.user32.GetAsyncKeyState(VK_PRIOR) & 0x8000
            if pageup_state and not self.last_pageup_state:
                self.toggle_main_window()
            self.last_pageup_state = pageup_state
            
            # 检查PageDown
            pagedown_state = windll.user32.GetAsyncKeyState(VK_NEXT) & 0x8000
            if pagedown_state and not self.last_pagedown_state:
                self.toggle_current_window_lock()
            self.last_pagedown_state = pagedown_state
            
            # 检查V键
            v_state = windll.user32.GetAsyncKeyState(VK_V) & 0x8000
            if v_state and not self.last_v_state:
                self.toggle_current_window_lock()
            self.last_v_state = v_state
        except:
            pass
    
    def check_license(self):
        """检查授权状态"""
        licensed, status, remaining = LicenseManager.check_license_status()
        
        if licensed:
            self.trial_label.setText("已授权")
            self.trial_label.setStyleSheet("color: green; font-weight: bold;")
            self.activate_btn.setEnabled(False)
        else:
            self.trial_label.setText(f"剩余{remaining}天试用期")
            if remaining <= 0:
                QMessageBox.warning(self, "试用期结束", "试用期已结束，请激活软件！")
    
    def show_activation_dialog(self):
        """显示激活对话框"""
        dialog = ActivationDialog(self)
        if dialog.exec_():
            self.check_license()
    
    def show_about_dialog(self):
        """显示关于对话框"""
        dialog = AboutDialog(self)
        dialog.exec_()
    
    def create_window_settings_dialog(self, window_id):
        """创建窗口设置对话框"""
        dialog = WindowSettingsDialog(
            f"窗口{window_id}设置",
            self.x_spin.value(),
            self.y_spin.value(),
            self.width_spin.value(),
            self.height_spin.value(),
            self
        )
        return dialog
    
    def select_window(self, window_id):
        """选择窗口"""
        self.current_window_id = window_id
        self.open_window_btn.setText(f"打开窗口{window_id}")
        self.delete_window_btn.setText(f"关闭窗口{window_id}")
        
        # 根据窗口是否打开，显示/隐藏控制面板
        is_open = window_id in self.video_windows
        self.control_group.setVisible(is_open)
        self.switch_group.setVisible(is_open)
        self.volume_group.setVisible(is_open)
        
        # 更新位置显示
        if is_open:
            x, y, w, h = self.video_windows[window_id].get_position()
            self.x_spin.blockSignals(True)
            self.y_spin.blockSignals(True)
            self.width_spin.blockSignals(True)
            self.height_spin.blockSignals(True)
            
            self.x_spin.setValue(x)
            self.y_spin.setValue(y)
            self.width_spin.setValue(w)
            self.height_spin.setValue(h)
            
            self.x_spin.blockSignals(False)
            self.y_spin.blockSignals(False)
            self.width_spin.blockSignals(False)
            self.height_spin.blockSignals(False)
        
        # 更新媒体列表显示（显示当前窗口的媒体列表）
        self.update_media_list_display()
        
        # 更新媒体列表标题，显示当前窗口
        self.media_group.setTitle(f"窗口{window_id} 媒体列表")
        
        # 更新播放控制标题
        self.control_group.setTitle(f"播放控制 → 窗口{window_id}")
        
        # 更新UDP/TCP端口显示
        udp_port = WINDOW_UDP_PORTS[window_id - 1]
        tcp_port = WINDOW_TCP_PORTS[window_id - 1]
        self.cmd_port_label.setText(f"UDP端口: {udp_port} | TCP端口: {tcp_port}")
        
        # 更新自动打开复选框状态
        auto_open = self.config_manager.get_window_auto_open(window_id)
        self.auto_open_cb.blockSignals(True)
        self.auto_open_cb.setChecked(auto_open)
        self.auto_open_cb.blockSignals(False)
        
        # 默认循环设置现在在表格每行的下拉框中，无需单独恢复
    
    def on_position_changed(self):
        """位置设置改变"""
        if self.current_window_id in self.video_windows:
            window = self.video_windows[self.current_window_id]
            x = self.x_spin.value()
            y = self.y_spin.value()
            w = self.width_spin.value()
            h = self.height_spin.value()
            window.set_position(x, y, w, h)
            # 防抖保存配置
            self._schedule_save_config()
    
    def fullscreen_current_window(self):
        """全屏铺满当前窗口"""
        desktop = QDesktopWidget()
        screen = desktop.screenGeometry()
        
        if self.current_window_id in self.video_windows:
            window = self.video_windows[self.current_window_id]
            window.set_position(0, 0, screen.width(), screen.height())
            
            # 更新显示
            self.x_spin.setValue(0)
            self.y_spin.setValue(0)
            self.width_spin.setValue(screen.width())
            self.height_spin.setValue(screen.height())
    
    def open_current_window(self):
        """打开当前窗口"""
        dialog = self.create_window_settings_dialog(self.current_window_id)
        if dialog.exec_():
            x, y, w, h = dialog.get_values()
            
            # 更新显示
            self.x_spin.setValue(x)
            self.y_spin.setValue(y)
            self.width_spin.setValue(w)
            self.height_spin.setValue(h)
            
            # 创建或移动窗口
            if self.current_window_id not in self.video_windows:
                window = VideoWindow(self.current_window_id)
                window.clicked.connect(self.on_video_window_clicked)
                window.window_closed.connect(self.on_video_window_closed)
                self.video_windows[self.current_window_id] = window
                
                # 从配置加载该窗口保存的媒体文件
                saved_files = self.config_manager.get_window_media_files(self.current_window_id)
                window.set_media_files(saved_files)
                
                # 更新主界面显示
                self.update_media_list_display()
                
                # 设置音量
                window.set_volume(self.volume_slider.value())
            else:
                window = self.video_windows[self.current_window_id]
            
            window.set_position(x, y, w, h)
            window.show()
            window.raise_()
            window.activateWindow()
            
            # 窗口已打开，显示控制面板
            self.control_group.setVisible(True)
            self.switch_group.setVisible(True)
            self.volume_group.setVisible(True)
            
            # 实时保存配置
            self.save_config()
            
            self.log(f"窗口{self.current_window_id}已打开")
    
    def on_video_window_clicked(self, window_id):
        """视频窗口被点击 - 加防抖保护"""
        import time
        now = time.time()
        if hasattr(self, '_last_click_time') and now - self._last_click_time < 0.3:
            return  # 300ms防抖
        self._last_click_time = now
        
        try:
            self.select_window(window_id)
            # 更新标签选中状态
            btn = self.window_tabs.button(window_id)
            if btn:
                btn.setChecked(True)
        except Exception as e:
            print(f"窗口点击处理异常: {e}")
    
    def on_video_window_closed(self, window_id):
        """视频窗口被关闭"""
        if window_id in self.video_windows:
            del self.video_windows[window_id]
            # 实时保存配置
            self.save_config()
            self.log(f"窗口{window_id}已关闭")
            # 如果关闭的是当前选中的窗口，切换到其他窗口
            if self.current_window_id == window_id:
                if self.video_windows:
                    self.select_window(list(self.video_windows.keys())[0])
                else:
                    self.current_window_id = 1
                    # 所有窗口都关了，隐藏控制面板
                    self.control_group.setVisible(False)
                    self.switch_group.setVisible(False)
                    self.volume_group.setVisible(False)
                    self.update_media_list_display()
    
    def delete_current_window(self):
        """删除当前窗口（只关闭窗口，保留媒体内容）"""
        window_id = self.current_window_id
        
        if window_id in self.video_windows:
            # 关闭窗口
            window = self.video_windows[window_id]
            
            # 先断开信号连接，避免close()触发on_video_window_closed导致重复处理
            try:
                window.window_closed.disconnect(self.on_video_window_closed)
            except:
                pass
            
            window.stop()
            window.close()
            del self.video_windows[window_id]
            
            # 实时保存配置
            self.save_config()
            
            # 注意：不清除媒体配置，下次打开窗口时媒体内容还在
            
            self.log(f"窗口{window_id}已关闭（媒体内容已保留）")
            
            # 切换到其他窗口
            if self.video_windows:
                self.select_window(list(self.video_windows.keys())[0])
            else:
                self.current_window_id = 1
                # 所有窗口都关了，隐藏控制面板
                self.control_group.setVisible(False)
                self.switch_group.setVisible(False)
                self.volume_group.setVisible(False)
                self.update_media_list_display()
        else:
            self.log(f"窗口{window_id}未打开，无需关闭")
    
    def add_media_file(self):
        """添加媒体文件"""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择媒体文件",
            "",
            "媒体文件 (*.mp4 *.avi *.mkv *.mov *.wmv *.flv *.webm *.mp3 *.wav *.jpg *.jpeg *.png *.bmp *.ppt *.pptx);;所有文件 (*.*)"
        )
        
        if files:
            # 获取当前窗口已有的媒体列表
            if self.current_window_id in self.video_windows:
                window = self.video_windows[self.current_window_id]
                existing_files = window.media_files
            else:
                # 窗口未打开时，从配置加载已有列表
                existing_files = self.config_manager.get_window_media_files(self.current_window_id)
            
            # 添加新文件
            added_count = 0
            for file_path in files:
                if file_path not in existing_files:
                    existing_files.append(file_path)
                    added_count += 1
            
            # 更新窗口和配置
            if self.current_window_id in self.video_windows:
                self.video_windows[self.current_window_id].media_files = existing_files
            
            # 直接保存到配置
            self.config_manager.set_window_media_files(self.current_window_id, existing_files)
            
            # 更新显示
            self.update_media_list_display()
            
            # 保存配置到文件
            self.config_manager.save_config()
            
            self.log(f"已添加 {added_count} 个文件到窗口{self.current_window_id}")
    
    def update_media_list_display(self):
        """更新媒体列表显示（表格形式，带编号、类型、控制指令、默认、模式）"""
        self.media_list.setRowCount(0)
        self.media_combo.clear()
        
        # 重建默认播放单选按钮组
        self._default_btn_group = QButtonGroup(self)
        self._default_btn_group.setExclusive(True)
        
        wid = self.current_window_id
        
        if wid in self.video_windows:
            media_files = self.video_windows[wid].media_files
        else:
            media_files = self.config_manager.get_window_media_files(wid)
        
        default_media = self.config_manager.get_window_default_media(wid)
        media_settings = self.config_manager.get_media_settings(wid)
        
        self.media_list.setRowCount(len(media_files))
        
        for idx, file_path in enumerate(media_files):
            row = idx  # 0-based row
            file_name = os.path.basename(file_path)
            ext = os.path.splitext(file_name)[1].lower()
            
            # 类型
            if ext in ['.jpg','.jpeg','.png','.bmp','.gif','.webp']:
                type_text = "图"
            elif ext in ['.ppt','.pptx']:
                type_text = "PPT"
            else:
                type_text = "视频"
            
            # 控制指令
            cmd = f"{wid}_play_{idx+1}"
            
            # 获取该项媒体独立配置
            item_setting = media_settings.get(str(idx + 1), {"default": False, "loop": False})
            is_default = (file_path == default_media) or item_setting.get("default", False)
            is_loop = item_setting.get("loop", False)
            
            # 编号列
            num_item = QTableWidgetItem(str(idx + 1))
            num_item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            num_item.setData(Qt.UserRole, file_path)
            num_item.setData(Qt.UserRole + 1, idx + 1)
            if is_default:
                num_item.setBackground(QColor("#E8F5E9"))
            
            # 文件名列
            name_text = file_name + (" ★" if is_default else "")
            name_item = QTableWidgetItem(name_text)
            name_item.setData(Qt.UserRole, file_path)
            name_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            if is_default:
                name_item.setForeground(QColor("#4CAF50"))
                name_item.setBackground(QColor("#E8F5E9"))
            
            # 类型列 - 左对齐，更紧凑
            type_item = QTableWidgetItem(type_text)
            type_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            if is_default:
                type_item.setBackground(QColor("#E8F5E9"))
            
            # 控制指令列 - 用QLabel实现可选中复制
            cmd_label = QLabel(cmd)
            cmd_label.setStyleSheet("color: #1565c0; font-size: 11px; padding: 0px; margin: 0px;")
            cmd_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            cmd_label.setCursor(Qt.IBeamCursor)
            cmd_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            if is_default:
                cmd_label.setStyleSheet("color: #1565c0; font-size: 11px; padding: 0px; margin: 0px; background-color: #E8F5E9;")
            
            # 默认播放列 - QRadioButton
            default_radio = QRadioButton()
            default_radio.setChecked(is_default)
            default_radio.setStyleSheet("QRadioButton { spacing: 0px; margin: 0px; padding: 0px; } QRadioButton::indicator { width: 12px; height: 12px; }")
            default_radio.setCursor(Qt.PointingHandCursor)
            self._default_btn_group.addButton(default_radio, idx)
            default_radio.toggled.connect(lambda checked, r=row, w=wid: self._on_default_radio_changed(r, w, checked))
            
            # 播放模式列 - QComboBox
            mode_combo = QComboBox()
            mode_combo.addItem("播放一遍")
            mode_combo.addItem("循环播放")
            mode_combo.setCurrentIndex(1 if is_loop else 0)
            mode_combo.setStyleSheet("QComboBox { font-size: 11px; padding: 0px 1px; border: 1px solid #ccc; border-radius: 2px; min-height: 16px; } QComboBox::drop-down { width: 14px; } QComboBox QAbstractItemView { font-size: 11px; }")
            mode_combo.setCursor(Qt.PointingHandCursor)
            mode_combo.currentIndexChanged.connect(lambda index, r=row, w=wid: self._on_mode_changed(r, w, index))
            
            self.media_list.setItem(row, 0, num_item)
            self.media_list.setItem(row, 1, name_item)
            self.media_list.setItem(row, 2, type_item)
            self.media_list.setCellWidget(row, 3, cmd_label)
            self.media_list.setCellWidget(row, 4, default_radio)
            self.media_list.setCellWidget(row, 5, mode_combo)
            
            # 下拉框也带编号
            self.media_combo.addItem(f"{idx+1}. {file_name}", file_path)
        
        # 设置行高
        for row in range(len(media_files)):
            self.media_list.setRowHeight(row, 26)
    
    def play_selected_media(self, item):
        """播放选中的媒体"""
        # 兼容QTableWidget：从当前行获取数据
        row = self.media_list.row(item) if item else self.media_list.currentRow()
        if row >= 0:
            num_item = self.media_list.item(row, 0)
            if num_item:
                file_path = num_item.data(Qt.UserRole)
                self.play_media(file_path)

    def _on_media_cell_double_clicked(self, row, col):
        """表格单元格双击"""
        num_item = self.media_list.item(row, 0)
        if num_item:
            file_path = num_item.data(Qt.UserRole)
            self.play_media(file_path)
    
    def remove_selected_media(self):
        """移除选中的媒体"""
        row = self.media_list.currentRow()
        if row >= 0:
            num_item = self.media_list.item(row, 0)
            if num_item:
                file_path = num_item.data(Qt.UserRole)
            
                # 从窗口列表中移除
                if self.current_window_id in self.video_windows:
                    window = self.video_windows[self.current_window_id]
                    if file_path in window.media_files:
                        window.media_files.remove(file_path)
                
                # 从配置中移除
                media_files = self.config_manager.get_window_media_files(self.current_window_id)
                if file_path in media_files:
                    media_files.remove(file_path)
                    self.config_manager.set_window_media_files(self.current_window_id, media_files)
                
                # 如果移除的是默认播放，清除默认
                if self.config_manager.get_window_default_media(self.current_window_id) == file_path:
                    self.config_manager.set_window_default_media(self.current_window_id, "")
                
                self.config_manager.save_config()
                self.update_media_list_display()
                self.log(f"已移除: {os.path.basename(file_path)}")
    
    def set_default_media(self):
        """设置默认播放的媒体"""
        row = self.media_list.currentRow()
        if row >= 0:
            num_item = self.media_list.item(row, 0)
            if num_item:
                file_path = num_item.data(Qt.UserRole)
                self.config_manager.set_window_default_media(self.current_window_id, file_path)
                self.config_manager.save_config()
                
                # 更新显示
                self.update_media_list_display()
                # 同步循环按钮状态
                default_loop = self.config_manager.get_window_default_loop(self.current_window_id)
                if self.current_window_id in self.video_windows:
                    self.video_windows[self.current_window_id].loop_play = default_loop
                    self.loop_btn.setChecked(default_loop)
                self.log(f"窗口{self.current_window_id}默认播放已设置: {os.path.basename(file_path)}")
    
    def _on_default_radio_changed(self, row, window_id, checked):
        """表格中默认播放单选按钮变化"""
        if not checked:
            return
        if getattr(self, '_updating_media_list', False):
            return
        # 获取该行对应的文件
        num_item = self.media_list.item(row, 0)
        if num_item:
            file_path = num_item.data(Qt.UserRole)
            self.config_manager.set_window_default_media(window_id, file_path)
            # 同时设置媒体项配置
            idx = num_item.data(Qt.UserRole + 1)
            self.config_manager.set_media_item_setting(window_id, idx, "default", True)
            self.config_manager.save_config()
            # 重建表格
            self._updating_media_list = True
            try:
                self.update_media_list_display()
            finally:
                self._updating_media_list = False
    
    def _on_mode_changed(self, row, window_id, index):
        """表格中播放模式下拉变化 (0=播放一遍, 1=循环播放)"""
        if getattr(self, '_updating_media_list', False):
            return
        num_item = self.media_list.item(row, 0)
        if num_item:
            idx = num_item.data(Qt.UserRole + 1)
            is_loop = (index == 1)
            self.config_manager.set_media_item_setting(window_id, idx, "loop", is_loop)
            self.config_manager.save_config()
            # 如果是当前正在播放的媒体，同步循环状态
            if window_id in self.video_windows:
                window = self.video_windows[window_id]
                # 如果这个媒体正在播放，更新循环设置
                if window.current_index == idx - 1:
                    window.loop_play = is_loop
                    self.loop_btn.setChecked(is_loop)
    
    def _on_minimize_to_tray_changed(self, state):
        """最小化到托盘设置变化"""
        minimize = state == Qt.Checked
        self.config_manager.set_minimize_to_tray(minimize)
        self.config_manager.save_config()
    
    def toggle_auto_open(self, state):
        """切换窗口自动打开"""
        auto_open = state == Qt.Checked
        self.config_manager.set_window_auto_open(self.current_window_id, auto_open)
        self.config_manager.save_config()
        
        status = "开启" if auto_open else "关闭"
        self.log(f"窗口{self.current_window_id}自动打开已{status}")
    
    def play_media(self, file_path):
        """播放指定媒体"""
        if self.current_window_id in self.video_windows:
            self.video_windows[self.current_window_id].play(file_path)
            self.log(f"播放: {os.path.basename(file_path)}")
    
    def play_current(self):
        """播放当前窗口"""
        if self.current_window_id in self.video_windows:
            window = self.video_windows[self.current_window_id]
            if window.current_index >= 0:
                window.play()
            else:
                # 播放第一个
                if window.media_files:
                    window.current_index = 0
                    window.play()
            self.log(f"窗口{self.current_window_id}播放")
    
    def pause_current(self):
        """暂停当前窗口"""
        if self.current_window_id in self.video_windows:
            self.video_windows[self.current_window_id].pause()
            self.log(f"窗口{self.current_window_id}暂停")
    
    def stop_current(self):
        """停止当前窗口"""
        if self.current_window_id in self.video_windows:
            self.video_windows[self.current_window_id].stop()
            self.log(f"窗口{self.current_window_id}停止")
    
    def replay_current(self):
        """重播当前窗口"""
        if self.current_window_id in self.video_windows:
            self.video_windows[self.current_window_id].replay()
            self.log(f"窗口{self.current_window_id}重播")
    
    def toggle_fullscreen_current(self):
        """切换当前窗口全屏"""
        if self.current_window_id in self.video_windows:
            self.video_windows[self.current_window_id].toggle_fullscreen()
    
    def toggle_loop_current(self):
        """切换当前窗口循环播放"""
        if self.current_window_id in self.video_windows:
            is_loop = self.video_windows[self.current_window_id].toggle_loop()
            self.loop_btn.setChecked(is_loop)
            self.log(f"窗口{self.current_window_id} 循环播放: {'开启' if is_loop else '关闭'}")
    
    def prev_media(self):
        """上一个媒体"""
        if self.current_window_id in self.video_windows:
            self.video_windows[self.current_window_id].prev_media()
    
    def next_media(self):
        """下一个媒体"""
        if self.current_window_id in self.video_windows:
            self.video_windows[self.current_window_id].next_media()
    
    def on_media_combo_changed(self, index):
        """媒体下拉框改变"""
        if index >= 0 and self.current_window_id in self.video_windows:
            file_path = self.media_combo.itemData(index)
            if file_path:
                self.play_media(file_path)
    
    def on_volume_changed(self, value):
        """音量改变"""
        self.volume_label.setText(f"{value}%")
        if self.current_window_id in self.video_windows:
            self.video_windows[self.current_window_id].set_volume(value)
        # 防抖保存配置
        self._schedule_save_config()
    
    def toggle_mute_current(self):
        """切换当前窗口静音"""
        if self.current_window_id in self.video_windows:
            is_muted = self.video_windows[self.current_window_id].toggle_mute()
            self.mute_btn.setText("🔇 取消静音" if is_muted else "🔊 静音")
    
    def play_window(self, window_id):
        """播放指定窗口"""
        if window_id in self.video_windows:
            self.video_windows[window_id].play()
            self.log(f"窗口{window_id}播放")
    
    def stop_window(self, window_id):
        """停止指定窗口"""
        if window_id in self.video_windows:
            self.video_windows[window_id].stop()
            self.log(f"窗口{window_id}停止")
    
    def send_command_to_current(self, command):
        """发送命令到当前窗口"""
        self.execute_command(command, self.current_window_id)
    
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
        elif cmd == "fullscreen":
            window.toggle_fullscreen()
        elif cmd == "loop":
            window.toggle_loop()
        elif cmd.isdigit():
            # 按编号播放: 如 "3" 表示播放第3个媒体
            idx = int(cmd) - 1
            if 0 <= idx < len(window.media_files):
                window.play(window.media_files[idx])
        elif cmd.startswith("play_") and cmd[5:].isdigit():
            # play_3 格式: 播放第3个
            idx = int(cmd[5:]) - 1
            if 0 <= idx < len(window.media_files):
                window.play(window.media_files[idx])
        elif cmd == "all":
            window.play()
    
    def on_network_command(self, command, window_id):
        """网络命令接收"""
        self.log(f"收到命令: {command} (窗口{window_id})")
        self.execute_command(command, window_id)
    
    def on_udp_message(self, message, addr, port):
        """UDP消息接收"""
        self.log(f"UDP[{port}] <- {addr}: {message}")
    
    def on_serial_data(self, data):
        """串口数据接收"""
        self.log(f"串口 <- {data}")
        # 解析并执行命令
        self.parse_serial_command(data)
    
    def parse_serial_command(self, data):
        """解析串口命令"""
        try:
            # 格式: windowid_command 或 windowid:command
            parts = re.split(r'[_,:]', data.strip())
            if len(parts) >= 2:
                if parts[0].isdigit():
                    window_id = int(parts[0])
                    command = parts[1].lower()
                    self.execute_command(command, window_id)
                else:
                    command = parts[0].lower()
                    self.execute_command(command, self.current_window_id)
            else:
                command = data.strip().lower()
                self.execute_command(command, self.current_window_id)
        except Exception as e:
            self.log(f"命令解析错误: {e}")
    
    def toggle_serial_connection(self):
        """切换串口连接"""
        if self.serial_manager.is_connected():
            self.serial_manager.disconnect()
            self.serial_connect_btn.setText("连接串口")
            self.log("串口已断开")
        else:
            port = self.serial_port_combo.currentText()
            self.serial_manager.configure(port)
            if self.serial_manager.connect():
                self.serial_connect_btn.setText("断开串口")
                self.log(f"串口已连接: {port}")
            else:
                self.log(f"串口连接失败: {port}")
    
    def broadcast_command(self, protocol, command):
        """广播命令"""
        target_ip = self.target_ip_edit.text()
        
        if protocol == "udp":
            port = self.udp_port_spin.value()
            self.network_manager.send_udp(command, target_ip, port)
            self.log(f"UDP广播 -> {target_ip}:{port}")
        else:
            port = self.tcp_port_spin.value()
            self.network_manager.send_tcp(command, target_ip, port)
            self.log(f"TCP广播 -> {target_ip}:{port}")
    
    def broadcast_play_all(self):
        """广播控制 - 全部播放"""
        for window_id, window in self.video_windows.items():
            if window.media_files:
                if window.current_index < 0:
                    window.current_index = 0
                window.play()
                self.log(f"窗口{window_id}播放")
    
    def broadcast_pause_all(self):
        """广播控制 - 全部暂停"""
        for window_id, window in self.video_windows.items():
            window.pause()
            self.log(f"窗口{window_id}暂停")
    
    def broadcast_stop_all(self):
        """广播控制 - 全部停止"""
        for window_id, window in self.video_windows.items():
            window.stop()
            self.log(f"窗口{window_id}停止")
    
    def broadcast_replay_all(self):
        """广播控制 - 全部重播"""
        for window_id, window in self.video_windows.items():
            window.replay()
            self.log(f"窗口{window_id}重播")
    
    def broadcast_prev_all(self):
        """广播控制 - 全部切换上一个"""
        for window_id, window in self.video_windows.items():
            window.prev_media()
            self.log(f"窗口{window_id}上一个")
    
    def broadcast_next_all(self):
        """广播控制 - 全部切换下一个"""
        for window_id, window in self.video_windows.items():
            window.next_media()
            self.log(f"窗口{window_id}下一个")
    
    def broadcast_mute_all(self):
        """广播控制 - 全部静音"""
        for window_id, window in self.video_windows.items():
            if not window.is_muted:
                window.toggle_mute()
            self.log(f"窗口{window_id}静音")
    
    def broadcast_unmute_all(self):
        """广播控制 - 全部取消静音"""
        for window_id, window in self.video_windows.items():
            if window.is_muted:
                window.toggle_mute()
            self.log(f"窗口{window_id}取消静音")
    
    def broadcast_set_volume(self, volume):
        """广播控制 - 设置所有窗口音量"""
        for window_id, window in self.video_windows.items():
            window.set_volume(volume)
            self.log(f"窗口{window_id}音量{volume}")
    
    def broadcast_open_all(self):
        """广播控制 - 打开所有窗口"""
        for window_id in range(1, 5):
            if window_id not in self.video_windows:
                # 获取保存的窗口位置，或使用默认值
                saved_pos = self.config_manager.get_window_position(window_id)
                x = saved_pos.get("x", 100 + (window_id - 1) * 50)
                y = saved_pos.get("y", 100 + (window_id - 1) * 50)
                w = saved_pos.get("width", 800)
                h = saved_pos.get("height", 600)
                
                # 创建窗口
                window = VideoWindow(window_id)
                window.clicked.connect(self.on_video_window_clicked)
                window.window_closed.connect(self.on_video_window_closed)
                self.video_windows[window_id] = window
                
                # 从配置加载该窗口保存的媒体文件
                saved_files = self.config_manager.get_window_media_files(window_id)
                window.set_media_files(saved_files)
                
                # 设置位置和显示
                window.set_position(x, y, w, h)
                window.show()
                
                # 设置音量
                window.set_volume(self.volume_all_slider.value())
                
                self.log(f"窗口{window_id}已打开")
    
    def broadcast_close_all(self):
        """广播控制 - 关闭所有窗口"""
        for window_id, window in list(self.video_windows.items()):
            window.close()
            self.log(f"窗口{window_id}已关闭")
    
    def on_volume_all_changed(self, value):
        """全部音量滑块改变"""
        self.volume_all_value_label.setText(f"{value}%")
        self.broadcast_set_volume(value)
    
    def toggle_main_window(self):
        """切换主窗口显示"""
        if self.isVisible():
            self.hide_to_tray()
        else:
            self.show_main_window()
    
    def show_main_window(self):
        """显示主窗口（置顶显示在所有窗口之上）"""
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.show()
        self.showNormal()
        self.raise_()
        self.activateWindow()
        # 短暂延迟后取消置顶，避免主窗口一直遮挡视频窗口
        QTimer.singleShot(500, self._remove_stays_on_top)
    
    def _remove_stays_on_top(self):
        """取消主窗口置顶（延迟执行，确保窗口已经显示到最前面）"""
        try:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)
            self.show()
        except:
            pass
    
    def hide_to_tray(self):
        """隐藏到托盘"""
        self.hide()
        self.is_minimized_to_tray = True
    
    def on_tray_activated(self, reason):
        """托盘图标激活"""
        if reason == QSystemTrayIcon.Trigger:
            self.show_main_window()
    
    def toggle_current_window_lock(self):
        """切换当前窗口锁定 - 锁定最后点击的窗口"""
        if self.current_window_id in self.video_windows:
            window = self.video_windows[self.current_window_id]
            if window.isVisible():
                is_locked = window.toggle_lock()
                self.log(f"窗口{self.current_window_id} {'锁定' if is_locked else '解锁'}")
    
    def log(self, message):
        """记录日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
        self.statusBar().showMessage(message, 3000)
    
    def closeEvent(self, event):
        """关闭事件"""
        # 隐藏到托盘而不是关闭
        reply = QMessageBox.question(
            self,
            "确认退出",
            "确定要退出程序吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # 保存配置
            self.save_config()
            
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
        # 保存配置
        self.save_config()
        
        # 关闭所有视频窗口
        for window in list(self.video_windows.values()):
            window.close()
        
        # 停止网络和串口
        self.network_manager.stop_network()
        if self.serial_manager.is_connected():
            self.serial_manager.disconnect()
        
        # 关闭托盘图标
        self.tray_icon.hide()
        
        QApplication.quit()
    
    def _schedule_save_config(self):
        """延迟保存配置，避免频繁写文件"""
        self._config_save_timer.start(1000)  # 1秒后保存
    
    def save_config(self):
        """保存配置"""
        # 保存主窗口几何
        geometry = self.geometry()
        self.config_manager.set_main_window_geometry(
            geometry.x(), geometry.y(), geometry.width(), geometry.height()
        )
        
        # 先清除所有窗口的打开状态
        for window_id in range(1, 5):
            self.config_manager.set_window_is_open(window_id, False)
        
        # 保存各窗口的媒体列表、位置和打开状态
        for window_id, window in self.video_windows.items():
            self.config_manager.set_window_media_files(window_id, window.media_files)
            # 保存窗口位置
            pos = window.pos()
            size = window.size()
            self.config_manager.set_window_position(window_id, pos.x(), pos.y(), size.width(), size.height())
            # 标记窗口为打开状态
            self.config_manager.set_window_is_open(window_id, True)
        
        # 保存最小化到托盘设置
        self.config_manager.set_minimize_to_tray(self.minimize_to_tray_check.isChecked())
        
        # 保存音量
        self.config_manager.set_global_volume(self.volume_slider.value())
        
        # 保存到文件
        self.config_manager.save_config()
        print("配置已保存")
    
    def apply_config(self):
        """应用加载的配置"""
        # 应用主窗口几何
        geometry = self.config_manager.get_main_window_geometry()
        if geometry:
            self.setGeometry(
                geometry.get("x", 100),
                geometry.get("y", 100),
                geometry.get("width", 1100),
                geometry.get("height", 800)
            )
        
        # 应用音量
        volume = self.config_manager.get_global_volume()
        self.volume_slider.setValue(volume)
        
        # 恢复最小化到托盘设置
        minimize = self.config_manager.get_minimize_to_tray()
        self.minimize_to_tray_check.setChecked(minimize)
        
        # 自动打开配置的窗口
        self._auto_open_windows()
        
        print("配置已应用")
    
    def _auto_open_windows(self):
        """自动恢复上次打开的窗口（记忆还原）"""
        for window_id in range(1, 5):
            # 同时检查 is_open 和 auto_open，满足任一条件就恢复窗口
            is_open = self.config_manager.get_window_is_open(window_id)
            auto_open = self.config_manager.get_window_auto_open(window_id)
            if is_open or auto_open:
                # 获取窗口位置
                pos = self.config_manager.get_window_position(window_id)
                # 获取媒体列表
                media_files = self.config_manager.get_window_media_files(window_id)
                # 获取默认播放
                default_media = self.config_manager.get_window_default_media(window_id)
                
                if media_files:
                    # 创建窗口
                    window = VideoWindow(window_id)
                    window.clicked.connect(self.on_video_window_clicked)
                    window.window_closed.connect(self.on_video_window_closed)
                    window.set_media_files(media_files)
                    window.set_volume(self.volume_slider.value())
                    window.set_position(pos.get("x", 100), pos.get("y", 100), 
                                        pos.get("width", 800), pos.get("height", 600))
                    window.show()
                    
                    self.video_windows[window_id] = window
                    
                    # 应用默认媒体的播放模式
                    if default_media and default_media in media_files:
                        default_idx = media_files.index(default_media) + 1
                        media_setting = self.config_manager.get_media_item_setting(window_id, default_idx)
                        window.loop_play = media_setting.get("loop", False)
                    
                    # 自动播放默认媒体
                    if default_media and default_media in media_files:
                        window.play(default_media)
                    elif media_files:
                        window.play(media_files[0])
                    
                    self.log(f"窗口{window_id}已自动恢复")


# ============== 程序入口 ==============

def main():
    # 启用高DPI支持
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(COMPANY_NAME)
    
    # 设置应用图标（使用正确路径，兼容PyInstaller打包）
    icon_path = get_resource_path("Kunzhancheng.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    else:
        print(f"图标文件未找到: {icon_path}")
        try:
            app.setWindowIcon(QIcon.fromTheme("media-player"))
        except:
            pass
    
    # 创建并显示主窗口
    window = MainWindow()
    
    # 设置主窗口图标
    if os.path.exists(icon_path):
        window.setWindowIcon(QIcon(icon_path))
    
    # 检查启动时最小化
    if window.config_manager.get_minimize_to_tray():
        window.hide()
        window.tray_icon.showMessage(
            APP_NAME, "程序已最小化到托盘，点击图标可恢复",
            QSystemTrayIcon.Information, 2000
        )
    else:
        window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()


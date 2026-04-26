# -*- coding: utf-8 -*-
"""
坤展成-中控多窗口播放器
开发公司：北京方桑兄弟科技有限公司
联系方式：18210234280
版本：v1.0
"""

import sys
import os
import socket
import struct
import threading
import time
import hashlib
import json
import base64
import re
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
APP_VERSION = "v1.0"
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
        
        # 窗口编号标签
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
        self.label_id.show()
        
        # 设置初始大小和位置
        self.resize(800, 600)
        
    def init_player(self):
        """初始化播放器"""
        if VLC_AVAILABLE:
            # VLC播放器
            self.vlc_instance = vlc.Instance()
            self.vlc_player = self.vlc_instance.media_player_new()
            self.vlc_player.set_hwnd(int(self.winId()))
            self.use_vlc = True
        else:
            # PyQt5播放器
            self.media_player = QMediaPlayer()
            self.use_vlc = False
        
    def set_position(self, x, y, width, height):
        """设置窗口位置和大小"""
        self.move(int(x), int(y))
        self.resize(int(width), int(height))
        
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
        """播放视频"""
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
        
        try:
            if self.use_vlc:
                media = self.vlc_instance.media_new(file_path)
                self.vlc_player.set_media(media)
                self.vlc_player.play()
                self.is_playing = True
            else:
                self.media_player.setMedia(QMediaContent(QUrl.fromLocalFile(file_path)))
                self.media_player.play()
                self.is_playing = True
            return True
        except Exception as e:
            print(f"播放失败: {e}")
            return False
    
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
        self.play()
        
    def next_media(self):
        """下一个媒体"""
        if self.media_files:
            self.current_index = (self.current_index + 1) % len(self.media_files)
            return self.play()
        return False
    
    def prev_media(self):
        """上一个媒体"""
        if self.media_files:
            self.current_index = (self.current_index - 1) % len(self.media_files)
            return self.play()
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
    
    def mousePressEvent(self, event):
        """鼠标按下"""
        if event.button() == Qt.LeftButton:
            if not self.is_locked:
                self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
                self.is_dragging = True
                event.accept()
            self.clicked.emit(self.window_id)
    
    def mouseMoveEvent(self, event):
        """鼠标移动"""
        if event.buttons() == Qt.LeftButton and self.is_dragging and not self.is_locked:
            self.move(event.globalPos() - self.drag_position)
            event.accept()
    
    def mouseReleaseEvent(self, event):
        """鼠标释放"""
        self.is_dragging = False
        self.drag_position = None
    
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
        else:
            super().keyPressEvent(event)
    
    def closeEvent(self, event):
        """关闭事件"""
        self.stop()
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
        """解析命令"""
        # 支持格式: windowid_command_param 或 windowid:command:param
        parts = re.split(r'[_,:]', message)
        if len(parts) >= 2:
            # 第一个部分可能是窗口ID
            if parts[0].isdigit():
                wid = int(parts[0])
                cmd = parts[1].lower()
                param = parts[2] if len(parts) > 2 else None
                self.command_received.emit(cmd, wid)
            else:
                cmd = parts[0].lower()
                param = parts[1] if len(parts) > 1 else None
                self.command_received.emit(cmd, window_id)
        else:
            # 简单命令
            self.command_received.emit(message.lower(), window_id)
    
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
        
        # ===== 顶部信息区 =====
        info_group = QGroupBox("软件信息")
        info_layout = QVBoxLayout()
        
        # 公司信息
        info_layout.addWidget(QLabel(f"公司：{COMPANY_NAME}"))
        info_layout.addWidget(QLabel(f"电话：{CONTACT_PHONE}"))
        
        # 桌面分辨率
        desktop = QDesktopWidget()
        screen = desktop.screenGeometry()
        info_layout.addWidget(QLabel(f"桌面分辨率：{screen.width()} × {screen.height()} px"))
        
        # 启动时最小化到托盘
        self.minimize_to_tray_check = QCheckBox("启动时最小化到托盘")
        info_layout.addWidget(self.minimize_to_tray_check)
        
        # 快捷键说明
        hotkey_label = QLabel("全局快捷键：PageUp 呼出/隐藏+置顶 | PageDown 窗口锁定/解锁")
        hotkey_label.setStyleSheet("color: #666; font-size: 11px;")
        info_layout.addWidget(hotkey_label)
        
        # 支持格式
        format_label = QLabel("支持格式：视频/图片(JPG/PNG/BMP)/PPT/PPTX")
        format_label.setStyleSheet("color: #666; font-size: 11px;")
        info_layout.addWidget(format_label)
        
        # 试用期和激活按钮
        trial_layout = QHBoxLayout()
        self.trial_label = QLabel("剩余30天试用期")
        trial_layout.addWidget(self.trial_label)
        
        self.activate_btn = QPushButton("激活授权")
        self.activate_btn.clicked.connect(self.show_activation_dialog)
        trial_layout.addWidget(self.activate_btn)
        
        about_btn = QPushButton("关于")
        about_btn.clicked.connect(self.show_about_dialog)
        trial_layout.addWidget(about_btn)
        info_layout.addLayout(trial_layout)
        
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
        
        # ===== 媒体列表 =====
        media_group = QGroupBox("媒体列表")
        media_layout = QVBoxLayout()
        
        self.media_list = QListWidget()
        self.media_list.setMaximumHeight(120)
        self.media_list.itemDoubleClicked.connect(self.play_selected_media)
        media_layout.addWidget(self.media_list)
        
        # 按钮行
        btn_row = QHBoxLayout()
        add_btn = QPushButton("添加视频")
        add_btn.clicked.connect(self.add_media_file)
        btn_row.addWidget(add_btn)
        
        self.open_window_btn = QPushButton("打开窗口1")
        self.open_window_btn.clicked.connect(self.open_current_window)
        btn_row.addWidget(self.open_window_btn)
        media_layout.addLayout(btn_row)
        
        media_group.setLayout(media_layout)
        layout.addWidget(media_group)
        
        # ===== 播放控制 =====
        control_group = QGroupBox("手动控制（发送到当前窗口）")
        control_layout = QHBoxLayout()
        
        self.play_btn = QPushButton("▶ 播放")
        self.play_btn.clicked.connect(self.play_current)
        control_layout.addWidget(self.play_btn)
        
        self.pause_btn = QPushButton("⏸ 暂停")
        self.pause_btn.clicked.connect(self.pause_current)
        control_layout.addWidget(self.pause_btn)
        
        self.stop_btn = QPushButton("⏹ 停止")
        self.stop_btn.clicked.connect(self.stop_current)
        control_layout.addWidget(self.stop_btn)
        
        self.replay_btn = QPushButton("🔄 重播")
        self.replay_btn.clicked.connect(self.replay_current)
        control_layout.addWidget(self.replay_btn)
        
        self.fullscreen_btn2 = QPushButton("全屏")
        self.fullscreen_btn2.clicked.connect(self.toggle_fullscreen_current)
        control_layout.addWidget(self.fullscreen_btn2)
        
        control_group.setLayout(control_layout)
        layout.addWidget(control_group)
        
        # ===== 视频切换 =====
        switch_group = QGroupBox("视频切换")
        switch_layout = QHBoxLayout()
        
        prev_btn = QPushButton("◀ 上一个")
        prev_btn.clicked.connect(self.prev_media)
        switch_layout.addWidget(prev_btn)
        
        next_btn = QPushButton("下一个 ▶")
        next_btn.clicked.connect(self.next_media)
        switch_layout.addWidget(next_btn)
        
        self.media_combo = QComboBox()
        self.media_combo.currentIndexChanged.connect(self.on_media_combo_changed)
        switch_layout.addWidget(self.media_combo, 1)
        
        switch_group.setLayout(switch_layout)
        layout.addWidget(switch_group)
        
        # ===== 音量控制 =====
        volume_group = QGroupBox("独立音量控制")
        volume_layout = QHBoxLayout()
        
        self.mute_btn = QPushButton("🔊 静音")
        self.mute_btn.clicked.connect(self.toggle_mute_current)
        volume_layout.addWidget(self.mute_btn)
        
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(80)
        self.volume_slider.valueChanged.connect(self.on_volume_changed)
        volume_layout.addWidget(self.volume_slider, 1)
        
        self.volume_label = QLabel("80%")
        self.volume_label.setMinimumWidth(40)
        volume_layout.addWidget(self.volume_label)
        
        volume_group.setLayout(volume_layout)
        layout.addWidget(volume_group)
        
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
        widget.setMaximumWidth(280)
        widget.setStyleSheet("""
            QGroupBox {
                margin-top: 15px;
            }
        """)
        layout = QVBoxLayout()
        widget.setLayout(layout)
        
        # ===== 广播控制 =====
        broadcast_group = QGroupBox("广播控制全部")
        broadcast_layout = QVBoxLayout()
        
        # UDP广播
        udp_layout = QHBoxLayout()
        udp_layout.addWidget(QLabel(f"UDP {UDP_BROADCAST_PORT}"))
        udp_broadcast_btn = QPushButton("广播UDP")
        udp_broadcast_btn.clicked.connect(lambda: self.broadcast_command("udp", ""))
        udp_layout.addWidget(udp_broadcast_btn)
        broadcast_layout.addLayout(udp_layout)
        
        # TCP广播
        tcp_layout = QHBoxLayout()
        tcp_layout.addWidget(QLabel(f"TCP {TCP_BROADCAST_PORT}"))
        tcp_broadcast_btn = QPushButton("广播TCP")
        tcp_broadcast_btn.clicked.connect(lambda: self.broadcast_command("tcp", ""))
        tcp_layout.addWidget(tcp_broadcast_btn)
        broadcast_layout.addLayout(tcp_layout)
        
        broadcast_group.setLayout(broadcast_layout)
        layout.addWidget(broadcast_group)
        
        # ===== 各窗口独立控制 =====
        window_control_group = QGroupBox("各窗口独立控制")
        window_control_layout = QVBoxLayout()
        
        for i in range(1, 5):
            row_layout = QHBoxLayout()
            
            # 窗口标签
            label = QLabel(f"窗口{i}")
            label.setMinimumWidth(50)
            row_layout.addWidget(label)
            
            # UDP端口
            udp_label = QLabel(f"UDP:{WINDOW_UDP_PORTS[i-1]}")
            udp_label.setStyleSheet("color: #666; font-size: 11px;")
            row_layout.addWidget(udp_label)
            
            # TCP端口
            tcp_label = QLabel(f"TCP:{WINDOW_TCP_PORTS[i-1]}")
            tcp_label.setStyleSheet("color: #666; font-size: 11px;")
            row_layout.addWidget(tcp_label)
            
            window_control_layout.addLayout(row_layout)
            
            # 控制按钮
            btn_row = QHBoxLayout()
            play_btn = QPushButton(f"播放")
            play_btn.clicked.connect(lambda checked, w=i: self.play_window(w))
            btn_row.addWidget(play_btn)
            
            stop_btn = QPushButton("停止")
            stop_btn.clicked.connect(lambda checked, w=i: self.stop_window(w))
            btn_row.addWidget(stop_btn)
            
            window_control_layout.addLayout(btn_row)
        
        window_control_group.setLayout(window_control_layout)
        layout.addWidget(window_control_group)
        
        # ===== 快速命令 =====
        quick_group = QGroupBox("快速命令")
        quick_layout = QVBoxLayout()
        
        # 命令按钮网格
        commands = [
            ("播放", "play"),
            ("暂停", "pause"),
            ("停止", "stop"),
            ("重播", "replay"),
            ("下一个", "next"),
            ("上一个", "prev"),
            ("静音", "mute"),
            ("取消静音", "unmute")
        ]
        
        for text, cmd in commands:
            btn = QPushButton(text)
            btn.clicked.connect(lambda checked, c=cmd: self.send_command_to_current(c))
            quick_layout.addWidget(btn)
        
        quick_group.setLayout(quick_layout)
        layout.addWidget(quick_group)
        
        # ===== 日志显示 =====
        log_group = QGroupBox("通信日志")
        log_layout = QVBoxLayout()
        
        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(200)
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
        self.hotkey_timer.start(100)
        
        # 记录上一个状态
        self.last_pageup_state = False
        self.last_pagedown_state = False
    
    def check_hotkeys(self):
        """检查全局快捷键"""
        try:
            # 获取键盘状态
            from ctypes import windll
            VK_PRIOR = 0x21  # PageUp
            VK_NEXT = 0x22   # PageDown
            
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
        
        # 更新位置显示
        if window_id in self.video_windows:
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
    
    def on_position_changed(self):
        """位置设置改变"""
        if self.current_window_id in self.video_windows:
            window = self.video_windows[self.current_window_id]
            x = self.x_spin.value()
            y = self.y_spin.value()
            w = self.width_spin.value()
            h = self.height_spin.value()
            window.set_position(x, y, w, h)
    
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
                self.video_windows[self.current_window_id] = window
                
                # 设置媒体文件
                files = [self.media_list.item(i).text() for i in range(self.media_list.count())]
                window.set_media_files(files)
                
                # 设置音量
                window.set_volume(self.volume_slider.value())
            else:
                window = self.video_windows[self.current_window_id]
            
            window.set_position(x, y, w, h)
            window.show()
            window.raise_()
            window.activateWindow()
            
            self.log(f"窗口{self.current_window_id}已打开")
    
    def on_video_window_clicked(self, window_id):
        """视频窗口被点击"""
        self.select_window(window_id)
        # 更新标签选中状态
        btn = self.window_tabs.button(window_id)
        if btn:
            btn.setChecked(True)
    
    def add_media_file(self):
        """添加媒体文件"""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择媒体文件",
            "",
            "媒体文件 (*.mp4 *.avi *.mkv *.mov *.wmv *.flv *.webm *.mp3 *.wav *.jpg *.jpeg *.png *.bmp *.ppt *.pptx);;所有文件 (*.*)"
        )
        
        if files:
            for file_path in files:
                # 检查是否已存在
                items = [self.media_list.item(i).text() for i in range(self.media_list.count())]
                if file_path not in items:
                    # 添加到列表
                    item = QListWidgetItem(file_path)
                    self.media_list.addItem(item)
                    
                    # 添加到下拉框
                    file_name = os.path.basename(file_path)
                    self.media_combo.addItem(file_name, file_path)
                
                # 添加到当前窗口
                if self.current_window_id in self.video_windows:
                    self.video_windows[self.current_window_id].add_media_file(file_path)
            
            self.log(f"已添加 {len(files)} 个文件")
    
    def play_selected_media(self, item):
        """播放选中的媒体"""
        file_path = item.text()
        self.play_media(file_path)
    
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
    
    def toggle_main_window(self):
        """切换主窗口显示"""
        if self.isVisible():
            self.hide_to_tray()
        else:
            self.show_main_window()
    
    def show_main_window(self):
        """显示主窗口"""
        self.show()
        self.showNormal()
        self.raise_()
        self.activateWindow()
    
    def hide_to_tray(self):
        """隐藏到托盘"""
        self.hide()
        self.is_minimized_to_tray = True
    
    def on_tray_activated(self, reason):
        """托盘图标激活"""
        if reason == QSystemTrayIcon.Trigger:
            self.show_main_window()
    
    def toggle_current_window_lock(self):
        """切换当前窗口锁定"""
        if self.current_window_id in self.video_windows:
            is_locked = self.video_windows[self.current_window_id].toggle_lock()
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
    
    # 检查启动时最小化
    # 注意：这里不自动最小化，首次运行时显示主窗口
    
    window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

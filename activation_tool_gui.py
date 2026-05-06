"""
坤展成-中控多窗口播放器 激活码生成工具（GUI版本）
生成激活码并自动保存license.dat到D:\xiongdi
"""
import sys
import os
import json
import hashlib
import base64
from datetime import datetime
from PyQt5.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QMessageBox)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont

SALT = "KZC-MEDIA-PLAYER-2026-ACTIVATION"
SECRET_KEY = b"KZC_LICENSE_2026_XOR_KEY"
SAVE_DIR = r"D:\xiongdi"

def xor_crypt(data_bytes, key):
    """XOR加密/解密"""
    key_len = len(key)
    return bytes([b ^ key[i % key_len] for i, b in enumerate(data_bytes)])

def generate_activation_code(registration_code):
    """根据注册码生成激活码"""
    raw = f"{registration_code}-{SALT}"
    code = hashlib.sha256(raw.encode('utf-8')).hexdigest().upper()[:16]
    return f"{code[:4]}-{code[4:8]}-{code[8:12]}-{code[12:16]}"

def generate_license_dat(registration_code, activation_code, save_dir):
    """生成加密的license.dat并保存到指定目录"""
    data = {
        "activated": True,
        "registration_code": registration_code,
        "activation_code": activation_code
    }
    # 加密
    json_str = json.dumps(data, sort_keys=True)
    encrypted = xor_crypt(json_str.encode('utf-8'), SECRET_KEY)
    encoded = base64.b64encode(encrypted).decode('utf-8')
    # 保存
    os.makedirs(save_dir, exist_ok=True)
    filepath = os.path.join(save_dir, "license.dat")
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(encoded)
    return filepath

def save_record(registration_code, activation_code, save_dir):
    """保存激活记录"""
    try:
        os.makedirs(save_dir, exist_ok=True)
        filename = os.path.join(save_dir, "activation_records.txt")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(filename, "a", encoding="utf-8") as f:
            f.write(f"{timestamp}  注册码: {registration_code}  激活码: {activation_code}\n")
        return True
    except Exception as e:
        print(f"保存记录失败: {e}")
        return False

class ActivationToolDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("坤展成-中控播放器 激活码生成工具")
        self.setFixedSize(450, 340)
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(12)
        
        # 标题
        title = QLabel("激活码生成工具")
        title.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # 注册码输入
        reg_label = QLabel("注册码：")
        layout.addWidget(reg_label)
        
        reg_layout = QHBoxLayout()
        self.reg_edit = QLineEdit()
        self.reg_edit.setPlaceholderText("输入客户提供的注册码（XXXX-XXXX）")
        self.reg_edit.setStyleSheet("font-size: 16px; letter-spacing: 2px;")
        self.reg_edit.textChanged.connect(self.on_reg_changed)
        reg_layout.addWidget(self.reg_edit)
        layout.addLayout(reg_layout)
        
        # 激活码输出
        act_label = QLabel("激活码：")
        layout.addWidget(act_label)
        
        act_layout = QHBoxLayout()
        self.act_edit = QLineEdit()
        self.act_edit.setReadOnly(True)
        self.act_edit.setStyleSheet("background-color: #f0f0f0; font-size: 16px; letter-spacing: 2px; font-weight: bold;")
        act_layout.addWidget(self.act_edit)
        
        self.copy_btn = QPushButton("复制")
        self.copy_btn.setFixedWidth(60)
        self.copy_btn.clicked.connect(self.copy_activation_code)
        self.copy_btn.setEnabled(False)
        act_layout.addWidget(self.copy_btn)
        layout.addLayout(act_layout)
        
        # 保存路径提示
        save_hint = QLabel(f"license.dat 自动保存至：D:\\xiongdi\\license.dat")
        save_hint.setStyleSheet("color: #28a745; font-size: 11px; font-weight: bold;")
        save_hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(save_hint)
        
        # 生成按钮
        self.gen_btn = QPushButton("生成激活码")
        self.gen_btn.setStyleSheet("background-color: #4488ff; color: white; font-size: 14px; padding: 10px; border-radius: 4px;")
        self.gen_btn.clicked.connect(self.generate)
        layout.addWidget(self.gen_btn)
        
        self.setLayout(layout)
    
    def on_reg_changed(self, text):
        """注册码变化时清空激活码"""
        self.act_edit.clear()
        self.copy_btn.setEnabled(False)
    
    def generate(self):
        """生成激活码并保存license.dat"""
        reg_code = self.reg_edit.text().strip().upper()
        if not reg_code:
            QMessageBox.warning(self, "提示", "请输入注册码")
            return
        
        act_code = generate_activation_code(reg_code)
        self.act_edit.setText(act_code)
        self.copy_btn.setEnabled(True)
        
        # 生成license.dat到D:\xiongdi
        try:
            filepath = generate_license_dat(reg_code, act_code, SAVE_DIR)
            save_record(reg_code, act_code, SAVE_DIR)
            self.gen_btn.setText(f"已生成 → {filepath}")
            self.gen_btn.setStyleSheet("background-color: #28a745; color: white; font-size: 13px; padding: 10px; border-radius: 4px;")
        except Exception as e:
            self.gen_btn.setText(f"生成成功但保存失败: {e}")
            self.gen_btn.setStyleSheet("background-color: #dc3545; color: white; font-size: 12px; padding: 10px; border-radius: 4px;")
        
        QTimer.singleShot(3000, lambda: (self.gen_btn.setText("生成激活码"), self.gen_btn.setStyleSheet("background-color: #4488ff; color: white; font-size: 14px; padding: 10px; border-radius: 4px;")))
    
    def copy_activation_code(self):
        """复制激活码到剪贴板"""
        clipboard = QApplication.clipboard()
        clipboard.setText(self.act_edit.text())
        self.copy_btn.setText("已复制")
        QTimer.singleShot(1500, lambda: self.copy_btn.setText("复制"))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    dialog = ActivationToolDialog()
    dialog.show()
    sys.exit(app.exec_())

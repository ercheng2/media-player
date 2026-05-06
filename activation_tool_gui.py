"""
坤展成-中控多窗口播放器 激活码生成工具（GUI版本）
"""
import sys
import os
import hashlib
from datetime import datetime
from PyQt5.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QMessageBox)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont

SALT = "KZC-MEDIA-PLAYER-2026-ACTIVATION"
SAVE_DIR = r"D:\xiongdi"

def generate_activation_code(registration_code):
    """根据注册码生成激活码"""
    raw = f"{registration_code}-{SALT}"
    code = hashlib.sha256(raw.encode('utf-8')).hexdigest().upper()[:16]
    return f"{code[:4]}-{code[4:8]}-{code[8:12]}-{code[12:16]}"

def save_record(registration_code, activation_code):
    """保存激活记录到D:\xiongdi"""
    try:
        os.makedirs(SAVE_DIR, exist_ok=True)
        filename = os.path.join(SAVE_DIR, "activation_records.txt")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(filename, "a", encoding="utf-8") as f:
            f.write(f"{timestamp}  注册码: {registration_code}  激活码: {activation_code}
")
        return True
    except Exception as e:
        print(f"保存记录失败: {e}")
        return False

class ActivationToolDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("坤展成-中控播放器 激活码生成工具")
        self.setFixedSize(450, 320)
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
        save_hint = QLabel(f"激活记录自动保存至：D:\xiongdi\activation_records.txt")
        save_hint.setStyleSheet("color: #888; font-size: 11px;")
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
        """生成激活码"""
        reg_code = self.reg_edit.text().strip().upper()
        if not reg_code:
            QMessageBox.warning(self, "提示", "请输入注册码")
            return
        
        act_code = generate_activation_code(reg_code)
        self.act_edit.setText(act_code)
        self.copy_btn.setEnabled(True)
        
        # 保存记录到D盘
        if save_record(reg_code, act_code):
            self.gen_btn.setText("已生成并保存")
            self.gen_btn.setStyleSheet("background-color: #28a745; color: white; font-size: 14px; padding: 10px; border-radius: 4px;")
        else:
            self.gen_btn.setText("已生成（保存失败）")
            self.gen_btn.setStyleSheet("background-color: #dc3545; color: white; font-size: 14px; padding: 10px; border-radius: 4px;")
        QTimer.singleShot(2000, lambda: (self.gen_btn.setText("生成激活码"), self.gen_btn.setStyleSheet("background-color: #4488ff; color: white; font-size: 14px; padding: 10px; border-radius: 4px;")))
    
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

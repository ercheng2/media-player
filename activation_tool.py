"""
坤展成-中控多窗口播放器 激活码生成工具
输入注册码 → 输出激活码
"""
import sys
import hashlib

SALT = "KZC-MEDIA-PLAYER-2026-ACTIVATION"

def generate_activation_code(registration_code):
    """根据注册码生成激活码"""
    raw = f"{registration_code}-{SALT}"
    code = hashlib.sha256(raw.encode('utf-8')).hexdigest().upper()[:16]
    return f"{code[:4]}-{code[4:8]}-{code[8:12]}-{code[12:16]}"

def main():
    if len(sys.argv) > 1:
        reg_code = sys.argv[1].strip().upper()
    else:
        print("=" * 50)
        print("坤展成-中控多窗口播放器 激活码生成工具")
        print("=" * 50)
        reg_code = input("请输入注册码（格式 XXXX-XXXX）: ").strip().upper()
    
    if not reg_code:
        print("错误：注册码不能为空")
        sys.exit(1)
    
    act_code = generate_activation_code(reg_code)
    print()
    print(f"注册码: {reg_code}")
    print(f"激活码: {act_code}")
    print()

if __name__ == "__main__":
    main()

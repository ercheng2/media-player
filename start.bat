@echo off
chcp 65001 >nul
echo ==========================================
echo   坤展成-中控多窗口播放器
echo   开发公司：北京方桑兄弟科技有限公司
echo   联系方式：18210234280
echo ==========================================
echo.

:: 检查Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到Python，请先安装Python 3.8+
    pause
    exit /b 1
)

:: 检查依赖
echo [检查依赖...]
python -c "import PyQt5" 2>nul
if errorlevel 1 (
    echo [提示] 正在安装 PyQt5...
    pip install PyQt5>=5.15.0 -q
)

python -c "import vlc" 2>nul
if errorlevel 1 (
    echo [提示] python-vlc 未安装，视频播放功能可能受限
)

python -c "import serial" 2>nul
if errorlevel 1 (
    echo [提示] pyserial 未安装，串口功能不可用
)

echo [启动程序...]
echo.
python main.py

if errorlevel 1 (
    echo.
    echo [错误] 程序启动失败！
    pause
)

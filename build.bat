@echo off
chcp 65001 >nul
echo ==========================================
echo   坤展成-中控多窗口播放器 打包工具
echo ==========================================
echo.

echo [1/4] 检查依赖...
python -c "import PyQt5" 2>nul
if errorlevel 1 (
    echo [错误] 请先安装依赖: pip install -r requirements.txt
    pause
    exit /b 1
)

echo [2/4] 安装 PyInstaller...
pip install pyinstaller -q

echo [3/4] 开始打包...
pyinstaller --name="坤展成中控播放器" ^
            --windowed ^
            --onefile ^
            --hidden-import=PyQt5 ^
            --hidden-import=PyQt5.QtCore ^
            --hidden-import=PyQt5.QtGui ^
            --hidden-import=PyQt5.QtWidgets ^
            --hidden-import=PyQt5.QtMultimedia ^
            --hidden-import=PyQt5.QtNetwork ^
            --hidden-import=vlc ^
            --hidden-import=serial ^
            --hidden-import=serial.tools.list_ports ^
            main.py

echo [4/4] 打包完成!
echo.
echo 输出目录: dist\
echo 可执行文件: dist\坤展成中控播放器.exe
echo.
echo 提示: 如果VLC视频无法播放，请确保系统已安装VLC播放器
echo.
pause

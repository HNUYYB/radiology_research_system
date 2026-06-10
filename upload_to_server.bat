@echo off
chcp 65001 >nul
echo ============================================
echo   上传文件到服务器
echo ============================================

set SERVER=3.tcp.vip.cpolor.cn
set USER=user01

echo.
echo 即将连接到 %SERVER% ...
echo 请在弹出的窗口中输入密码
echo.

:: 上传整个项目目录（排除 .git, node_modules, __pycache__, venv）
pscp -r -P 22 -l %USER% -pw "你的密码" ^
    backend ^
    frontend/build ^
    frontend/package.json ^
    .env.example ^
    deploy.sh ^
    %SERVER%:/home/user01/radiology_research_system/

echo.
echo 上传完成！
pause

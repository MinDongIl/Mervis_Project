@echo off
echo [MERVIS] EXE 파일 생성을 시작합니다...
python -m PyInstaller --noconsole --onefile --icon=mervis.ico --name="Mervis_Pro" --clean main_gui.py
echo.
echo 생성 완료! dist 폴더를 확인하세요.
pause
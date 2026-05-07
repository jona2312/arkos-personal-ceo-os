@echo off
echo ============================================
echo   ARKOS - Pushing to GitHub...
echo ============================================
cd /d "%~dp0"
git init
git add .
git commit -m "feat: Initial commit - ARKOS Personal CEO OS v0.1"
git branch -M main
git remote add origin https://github.com/jona2312/arkos-personal-ceo-os.git
git push -u origin main
echo ============================================
echo   DONE! Repo pushed to GitHub.
echo   https://github.com/jona2312/arkos-personal-ceo-os
echo ============================================
pause

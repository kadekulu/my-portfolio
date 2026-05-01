@echo off
echo Starting GitHub Setup...

git init
git remote add origin https://github.com/kadekulu/my-portfolio.git
git branch -M main
git add .
git commit -m "Initial Deploy"
git push -u origin main

echo Done!
pause

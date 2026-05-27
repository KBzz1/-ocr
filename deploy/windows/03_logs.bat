@echo off
setlocal
pushd "%~dp0" || exit /b 1

docker compose logs --tail 200 -f

popd
exit /b 0
